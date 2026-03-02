"""Team splitting for OCR - identifying which players belong to the guild's team."""

import logging
import traceback

from .name_resolver import extract_score_from_corrupted_token


class TeamSplitter:
    """Splits multi-team OCR results to isolate the guild's own team."""

    def __init__(self, db_manager):
        self.db_manager = db_manager

    def extract_all_players_from_tokens(self, tokens: list[str], guild_id: int = 0) -> list[tuple]:
        """Extract all player-score pairs using database-first approach for proper 6v6 splitting."""
        if not self.db_manager:
            logging.error("❌ No database manager available for guild member lookup")
            return []

        guild_players = self.db_manager.players.get_all_players_stats(guild_id)
        if not guild_players:
            logging.warning("⚠️ No guild players found in database")
            return []

        guild_names = set()
        guild_nicknames = {}
        for player in guild_players:
            player_name = player.get('player_name', '').lower()
            guild_names.add(player_name)
            nicknames = player.get('nicknames', [])
            if nicknames:
                for nickname in nicknames:
                    guild_nicknames[nickname.lower()] = player_name

        logging.debug(f"🔍 Database lookup ready: {len(guild_names)} guild members, {len(guild_nicknames)} nicknames")

        players = []
        i = 0

        def find_guild_member_in_token(token: str, allow_substring_match: bool = True) -> str:
            """Check if token contains a guild member name or nickname."""
            token_lower = token.lower()

            if token_lower in guild_names:
                return token_lower

            if token_lower in guild_nicknames:
                return guild_nicknames[token_lower]

            if not allow_substring_match:
                return None

            for name in guild_names:
                if len(name) >= 2 and name in token_lower:
                    return name

            for nickname, real_name in guild_nicknames.items():
                if len(nickname) >= 2 and nickname in token_lower:
                    return real_name

            return None

        while i < len(tokens):
            current_token = tokens[i]

            # Case 1: Current token is a standalone score - look ahead for name
            if current_token.isdigit() and 1 <= int(current_token) <= 180:
                score = int(current_token)

                if i < len(tokens) - 1:
                    next_token = tokens[i + 1]
                    guild_member = find_guild_member_in_token(next_token, allow_substring_match=False)

                    if guild_member:
                        players.append((guild_member, score))
                        logging.debug(f"🔍 Found reversed pattern (guild): '{current_token} {next_token}' -> {guild_member}: {score}")
                        i += 2
                        continue
                    else:
                        players.append((next_token, score))
                        logging.debug(f"🔍 Found reversed pattern (opponent): '{current_token} {next_token}' -> {next_token}: {score}")
                        i += 2
                        continue
                else:
                    logging.warning(f"⚠️ Standalone score '{current_token}' at end of tokens")
                    i += 1
                    continue

            # Case 2: Current token contains letters - check for guild member
            if not current_token.isdigit():
                guild_member = find_guild_member_in_token(current_token, allow_substring_match=False)

                if guild_member:
                    score = None
                    consumed_tokens = 1

                    if i < len(tokens) - 1:
                        next_token = tokens[i + 1]
                        if next_token.isdigit() and 1 <= int(next_token) <= 180:
                            score = int(next_token)
                            consumed_tokens = 2
                            logging.debug(f"🔍 Found guild member with following score: '{current_token}' -> {guild_member}: {score}")

                    if score is None:
                        embedded_score = extract_score_from_corrupted_token(current_token)
                        if embedded_score:
                            score = embedded_score
                            logging.debug(f"🔍 Found guild member with embedded score: '{current_token}' -> {guild_member}: {score}")
                        else:
                            for lookahead in range(2, min(4, len(tokens) - i)):
                                next_token = tokens[i + lookahead]

                                if next_token.isdigit() and 1 <= int(next_token) <= 180:
                                    score = int(next_token)
                                    consumed_tokens = lookahead + 1
                                    logging.debug(f"🔍 Found guild member with distant score: '{current_token}' -> {guild_member}: {score}")
                                    break

                                embedded_score = extract_score_from_corrupted_token(next_token)
                                if embedded_score:
                                    score = embedded_score
                                    consumed_tokens = lookahead + 1
                                    logging.debug(f"🔍 Found guild member with embedded score in next token: '{current_token} {next_token}' -> {guild_member}: {score}")
                                    break

                    if score:
                        players.append((guild_member, score))
                        i += consumed_tokens
                        continue
                    else:
                        logging.warning(f"⚠️ Guild member '{current_token}' found but no score located")
                        i += 1
                        continue

                # Case 3: Not a guild member - check for opponent player patterns
                if len(current_token) <= 2 and not any(c.isalnum() for c in current_token):
                    logging.debug(f"🔍 Skipping symbol token: '{current_token}'")
                    i += 1
                    continue

                if (i < len(tokens) - 1 and
                        tokens[i + 1].isdigit() and
                        1 <= int(tokens[i + 1]) <= 180):
                    score = int(tokens[i + 1])
                    players.append((current_token, score))
                    logging.debug(f"🔍 Found opponent player: '{current_token}' -> {current_token}: {score}")
                    i += 2
                    continue

                if (i < len(tokens) - 2 and
                        not tokens[i + 1].isdigit() and
                        tokens[i + 2].isdigit() and
                        1 <= int(tokens[i + 2]) <= 180):
                    opponent_name = f"{current_token} {tokens[i + 1]}"
                    score = int(tokens[i + 2])
                    players.append((opponent_name, score))
                    logging.debug(f"🔍 Found 2-word opponent: '{opponent_name}' -> {opponent_name}: {score}")
                    i += 3
                    continue

                embedded_score = extract_score_from_corrupted_token(current_token)
                if embedded_score:
                    players.append((current_token, embedded_score))
                    logging.debug(f"🔍 Found opponent with embedded score: '{current_token}' -> {current_token}: {embedded_score}")
                    i += 1
                    continue

            # Case 4: No pattern found - skip token
            logging.debug(f"🔍 No pattern found for token '{current_token}', skipping")
            i += 1

        logging.info(f"🔍 Extracted {len(players)} player-score pairs: {[f'{name}:{score}' for name, score in players]}")
        return players

    def map_guild_positions(self, guild_results: list[dict], all_players: list[tuple]) -> dict[str, int]:
        """Map each guild member to their position in the full player list."""
        guild_member_positions = {}

        for result in guild_results:
            result_name = result['name']
            result_score = result['score']
            result_raw = result.get('raw_name', result_name)

            for pos, (player_name, score) in enumerate(all_players):
                score_match = (score == result_score)
                name_match1 = (player_name.lower() == result_raw.lower())
                name_match2 = (player_name.lower() == result_name.lower())
                name_match3 = (result_name.lower() in player_name.lower())

                if score_match and (name_match1 or name_match2 or name_match3):
                    guild_member_positions[result_name] = pos
                    logging.debug(f"🎯 {result_name} mapped to position {pos}")
                    break

            if result_name not in guild_member_positions:
                logging.warning(f"⚠️ Could not map {result_name} to position - defaulting to 0")
                guild_member_positions[result_name] = 0

        return guild_member_positions

    def apply_6v6_team_splitting(self, guild_results: list[dict], tokens: list[str], guild_id: int) -> list[dict]:
        """Apply 6v6 team splitting using majority rule based on player positions in raw OCR."""
        try:
            logging.debug("🔀 Starting 6v6 team splitting analysis")

            all_players = self.extract_all_players_from_tokens(tokens, guild_id)
            logging.info(f"📊 Extracted {len(all_players)} total players from OCR tokens")

            if len(all_players) != 12:
                logging.warning(f"⚠️ Expected 12 players for 6v6 split, found {len(all_players)}. Skipping split.")
                return guild_results

            guild_member_positions = {}

            for result in guild_results:
                result_name = result['name']
                result_score = result['score']
                result_raw = result.get('raw_name', result_name)

                for pos, (player_name, score) in enumerate(all_players):
                    score_match = (score == result_score)
                    name_match1 = (player_name.lower() == result_raw.lower())
                    name_match2 = (player_name.lower() == result_name.lower())
                    name_match3 = (result_name.lower() in player_name.lower())

                    if (score_match and (name_match1 or name_match2 or name_match3)):
                        guild_member_positions[result_name] = pos
                        logging.info(f"🎯 {result_name} found at position {pos}")
                        break

            team1_guild_members = []  # Positions 0-5
            team2_guild_members = []  # Positions 6-11

            for result in guild_results:
                member_name = result['name']
                if member_name in guild_member_positions:
                    pos = guild_member_positions[member_name]
                    if pos < 6:
                        team1_guild_members.append(result)
                    else:
                        team2_guild_members.append(result)
                else:
                    logging.warning(f"⚠️ Could not find position for guild member {member_name}")
                    team1_guild_members.append(result)

            team1_guild_count = len(team1_guild_members)
            team2_guild_count = len(team2_guild_members)

            team1_names = [m['name'] for m in team1_guild_members]
            team2_names = [m['name'] for m in team2_guild_members]
            logging.info(f"🏁 Team split - First 6: {team1_guild_count} guild members ({', '.join(team1_names)})")
            logging.info(f"🏁 Team split - Last 6: {team2_guild_count} guild members ({', '.join(team2_names)})")

            if team1_guild_count > team2_guild_count:
                winning_team = team1_guild_members
                excluded_team = team2_guild_members
                winning_team_num = 1
            elif team2_guild_count > team1_guild_count:
                winning_team = team2_guild_members
                excluded_team = team1_guild_members
                winning_team_num = 2
            else:
                logging.info(f"🤝 Team split tie: {team1_guild_count} vs {team2_guild_count} guild members - recording all players")
                return guild_results

            winning_names = [r['name'] for r in winning_team]
            excluded_names = [r['name'] for r in excluded_team]

            logging.info(f"🏆 6v6 Result - Team {winning_team_num} selected: {', '.join(winning_names)}")
            if excluded_team:
                logging.info(f"❌ Excluded opposing team: {', '.join(excluded_names)}")

            logging.debug("🔍 Attempting to recover corrupted names in winning team...")
            winning_team_start = 0 if winning_team_num == 1 else 6
            winning_team_end = 6 if winning_team_num == 1 else 12

            guild_players = self.db_manager.players.get_all_players_stats(guild_id) if self.db_manager else []
            guild_names_list = {p.get('player_name', '').lower(): p.get('player_name', '') for p in guild_players}

            for result in winning_team:
                result_name = result['name']
                result_score = result['score']

                for pos, (token_name, token_score) in enumerate(all_players):
                    if winning_team_start <= pos < winning_team_end and token_score == result_score:
                        token_lower = token_name.lower()
                        for guild_name in guild_names_list.keys():
                            if len(guild_name) >= 2 and guild_name in token_lower and guild_name != result_name.lower():
                                logging.debug(f"🔧 Potential corruption recovery: '{token_name}' might be '{guild_name}' for score {result_score}")
                                break

            return winning_team

        except Exception as e:
            logging.error(f"❌ Error applying 6v6 team splitting: {e}")
            return guild_results

    def apply_dynamic_team_splitting(
        self,
        guild_results: list[dict],
        tokens: list[str],
        guild_id: int,
        total_players: int
    ) -> list[dict]:
        """
        Universal team splitting for any player count (11-20 players).
        Uses majority rule to identify guild team regardless of split (6v6, 7v6, 8v7, etc.)
        """
        try:
            logging.debug(f"🔀 Starting dynamic team split for {total_players} players")

            all_players = self.extract_all_players_from_tokens(tokens, guild_id)

            if len(all_players) != total_players:
                logging.warning(f"⚠️ Expected {total_players} players, extracted {len(all_players)}. Skipping split.")
                return guild_results

            guild_member_positions = self.map_guild_positions(guild_results, all_players)

            split_point1 = total_players // 2
            split_point2 = (total_players + 1) // 2

            split_candidates = []

            team1_sp1 = [r for r in guild_results if guild_member_positions.get(r['name'], -1) < split_point1]
            team2_sp1 = [r for r in guild_results if guild_member_positions.get(r['name'], -1) >= split_point1]

            count1_sp1 = len(team1_sp1)
            count2_sp1 = len(team2_sp1)

            if count1_sp1 > count2_sp1:
                margin = count1_sp1 - count2_sp1
                split_candidates.append({
                    'team': team1_sp1,
                    'margin': margin,
                    'description': f"First {split_point1} ({count1_sp1} guild) vs Last {total_players-split_point1} ({count2_sp1} guild)",
                    'winner': f"first {split_point1}"
                })
            elif count2_sp1 > count1_sp1:
                margin = count2_sp1 - count1_sp1
                split_candidates.append({
                    'team': team2_sp1,
                    'margin': margin,
                    'description': f"Last {total_players-split_point1} ({count2_sp1} guild) vs First {split_point1} ({count1_sp1} guild)",
                    'winner': f"last {total_players-split_point1}"
                })

            if split_point2 != split_point1:
                team1_sp2 = [r for r in guild_results if guild_member_positions.get(r['name'], -1) < split_point2]
                team2_sp2 = [r for r in guild_results if guild_member_positions.get(r['name'], -1) >= split_point2]

                count1_sp2 = len(team1_sp2)
                count2_sp2 = len(team2_sp2)

                if count1_sp2 > count2_sp2:
                    margin = count1_sp2 - count2_sp2
                    split_candidates.append({
                        'team': team1_sp2,
                        'margin': margin,
                        'description': f"First {split_point2} ({count1_sp2} guild) vs Last {total_players-split_point2} ({count2_sp2} guild)",
                        'winner': f"first {split_point2}"
                    })
                elif count2_sp2 > count1_sp2:
                    margin = count2_sp2 - count1_sp2
                    split_candidates.append({
                        'team': team2_sp2,
                        'margin': margin,
                        'description': f"Last {total_players-split_point2} ({count2_sp2} guild) vs First {split_point2} ({count1_sp2} guild)",
                        'winner': f"last {total_players-split_point2}"
                    })

            if not split_candidates:
                logging.info("🤝 No clear majority in any split - returning all players")
                return guild_results

            best_split = max(split_candidates, key=lambda x: x['margin'])
            winning_team = best_split['team']
            excluded_team = [r for r in guild_results if r not in winning_team]

            winning_names = [r['name'] for r in winning_team]
            excluded_names = [r['name'] for r in excluded_team]

            logging.info(f"🏆 Split Result: {best_split['description']}")
            logging.info(f"✅ Winner ({best_split['winner']}): {', '.join(winning_names)}")
            if excluded_names:
                logging.info(f"❌ Excluded: {', '.join(excluded_names)}")

            return winning_team

        except Exception as e:
            logging.error(f"❌ Error in dynamic team splitting: {e}")
            logging.error(traceback.format_exc())
            return guild_results
