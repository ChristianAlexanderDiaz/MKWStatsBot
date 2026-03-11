"""Name resolution for OCR - finding valid player names in OCR token streams."""

import logging
import re


def extract_score_from_corrupted_token(token: str) -> int | None:
    """Extract score (1-180) from a corrupted token containing mixed text and numbers."""
    numbers = re.findall(r'\d+', token)
    for num_str in numbers:
        try:
            num = int(num_str)
            if 1 <= num <= 180:
                return num
        except ValueError:
            continue
    return None


class NameResolver:
    """Resolves player names from OCR token streams using pre-fetched roster data.

    Designed to run inside sync executor contexts. All DB data must be
    pre-fetched and passed in — this class never makes DB calls itself.

    Roster data is stored per guild_id for multi-tenant isolation.
    """

    def __init__(self, db_manager: object = None, *, roster_data: list[dict] | None = None, guild_id: int = 0) -> None:
        self.db_manager = db_manager  # Kept for backward compat; unused when roster_data supplied
        self._roster_data_by_guild: dict[int, list[dict]] = {}
        # Build lookup structures per guild
        self._name_set_by_guild: dict[int, set[str]] = {}
        self._nickname_map_by_guild: dict[int, dict[str, str]] = {}
        if roster_data:
            self.set_roster_data(guild_id, roster_data)

    def set_roster_data(self, guild_id: int, roster_data: list[dict]) -> None:
        """Update pre-fetched roster data for a specific guild (call before executor work)."""
        self._roster_data_by_guild[guild_id] = roster_data
        self._build_lookups(guild_id, roster_data)

    def _build_lookups(self, guild_id: int, roster_data: list[dict]) -> None:
        """Build fast lookup structures from roster data for a specific guild."""
        name_set: set[str] = set()
        nickname_map: dict[str, str] = {}
        for player in roster_data:
            pname = player.get('player_name', '')
            if pname:
                name_set.add(pname.lower())
            for nick in (player.get('nicknames') or []):
                nick_lower = nick.lower()
                if nick_lower in nickname_map:
                    existing_player = nickname_map[nick_lower]
                    logging.warning(
                        f"Nickname collision in guild {guild_id}: '{nick}' maps to both "
                        f"'{existing_player}' and '{pname}' — keeping '{existing_player}'"
                    )
                else:
                    nickname_map[nick_lower] = pname
        self._name_set_by_guild[guild_id] = name_set
        self._nickname_map_by_guild[guild_id] = nickname_map

    def _get_roster_data(self, guild_id: int) -> list[dict]:
        """Return pre-fetched roster data for the given guild."""
        roster = self._roster_data_by_guild.get(guild_id)
        if roster is not None:
            return roster
        logging.warning(f"No pre-fetched roster data available for guild {guild_id} — OCR name resolution will be limited")
        return []

    def _resolve_name(self, name: str, guild_id: int) -> str | None:
        """Resolve a name/nickname to canonical player name using pre-fetched data."""
        roster_data = self._roster_data_by_guild.get(guild_id)
        if roster_data is None:
            return None

        name_lower = name.lower()
        name_set = self._name_set_by_guild.get(guild_id, set())
        nickname_map = self._nickname_map_by_guild.get(guild_id, {})

        # Exact player name match
        if name_lower in name_set:
            for player in roster_data:
                if player.get('player_name', '').lower() == name_lower:
                    return player['player_name']
        # Nickname match
        if name_lower in nickname_map:
            canonical = nickname_map[name_lower]
            for player in roster_data:
                if player.get('player_name', '').lower() == canonical.lower():
                    return player['player_name']
            return canonical
        return None

    def find_guild_name_in_substring(self, corrupted_token: str, guild_id: int) -> tuple[str | None, str | None]:
        """Find guild member names as substrings within corrupted OCR tokens."""
        try:
            guild_players = self._get_roster_data(guild_id)
            if not guild_players:
                return None, None

            best_match = None
            best_match_name = None
            longest_length = 0

            for player in guild_players:
                player_name = player.get('player_name', '')
                nicknames = player.get('nicknames', [])
                all_names = [player_name] + (nicknames if nicknames else [])

                for name in all_names:
                    if len(name) >= 3 and name.lower() in corrupted_token.lower():
                        if len(name) > longest_length:
                            best_match = player_name
                            best_match_name = name
                            longest_length = len(name)

            if best_match:
                logging.debug(f"🔍 Substring match: Found '{best_match}' (via '{best_match_name}') in corrupted token '{corrupted_token}'")
                return best_match, best_match_name

            return None, None

        except Exception as e:
            logging.error(f"❌ Error in substring matching: {e}")
            return None, None

    def find_valid_names_with_window(self, tokens: list[str], guild_id: int) -> list[tuple]:
        """Find valid player names using sliding window approach with substring fallback for corrupted OCR."""
        valid_names = []
        i = 0

        while i < len(tokens):
            # Skip tokens that are clearly scores
            if tokens[i].isdigit() and 1 <= int(tokens[i]) <= 180:
                i += 1
                continue

            # Try 2-word combination first (for "No name", "kyle christian")
            if i < len(tokens) - 1:
                two_word = f"{tokens[i]} {tokens[i+1]}"
                race_count_2word = 12  # Default
                two_word_to_check = two_word
                raw_name_2word = two_word
                tokens_consumed_2word = 2

                # Check if the 2-word combination has race count patterns
                race_patterns = [
                    r'^(.+?)\s*\((\d+)\)$',  # Name (5)
                    r'^(.+?)\s*\((\d+)$',    # Name (5
                    r'^(.+?)\s*(\d+)\)$'     # Name 5)
                ]

                for pattern in race_patterns:
                    match = re.match(pattern, two_word.strip())
                    if match:
                        clean_2word_name = match.group(1).strip()
                        extracted_races = int(match.group(2))
                        if 1 <= extracted_races <= 11:
                            two_word_to_check = clean_2word_name
                            race_count_2word = extracted_races
                            logging.debug(f"🏁 Extracted race count from 2-word token '{two_word}': {clean_2word_name} → {race_count_2word} races")
                        break

                # If no race count in 2-word combo, check if next token (i+2) has race count
                if race_count_2word == 12 and i < len(tokens) - 2:
                    next_token = tokens[i + 2]
                    pair_patterns = [
                        r'^\((\d+)\)$',  # (5)
                        r'^\((\d+)$',    # (5
                        r'^(\d+)\)$'     # 5)
                    ]

                    for pattern in pair_patterns:
                        match = re.match(pattern, next_token.strip())
                        if match:
                            extracted_races = int(match.group(1))
                            if 1 <= extracted_races <= 11:
                                race_count_2word = extracted_races
                                raw_name_2word = f"{two_word} {next_token}"
                                tokens_consumed_2word = 3
                                logging.debug(f"🏁 Extracted race count from 2-word + token '{two_word}' + '{next_token}': {two_word_to_check} → {race_count_2word} races")
                            break

                resolved = self._resolve_name(two_word_to_check, guild_id)
                if resolved:
                    valid_names.append((i, resolved, raw_name_2word, None, race_count_2word))
                    logging.info(f"✅ Found 2-word name: '{raw_name_2word}' → '{resolved}' at position {i} ({race_count_2word} races)")
                    i += tokens_consumed_2word
                    continue
                else:
                    logging.debug(f"Player '{two_word}' not found in guild roster (likely opponent)")

            # Try single word exact match (check for race count patterns first)
            token_to_check = tokens[i]
            race_count = 12  # Default race count
            raw_name = tokens[i]
            tokens_consumed = 1

            # Check current token for race count patterns like "Cynical (5)" or "Cynical (5"
            race_patterns = [
                r'^(.+?)\s*\((\d+)\)$',  # Name (5)
                r'^(.+?)\s*\((\d+)$',    # Name (5
                r'^(.+?)\s*(\d+)\)$'     # Name 5)
            ]

            for pattern in race_patterns:
                match = re.match(pattern, token_to_check.strip())
                if match:
                    clean_name = match.group(1).strip()
                    extracted_races = int(match.group(2))
                    if 1 <= extracted_races <= 11:
                        token_to_check = clean_name
                        race_count = extracted_races
                        logging.debug(f"🏁 Extracted race count from token '{raw_name}': {clean_name} → {race_count} races")
                    break

            # If no race count in current token, check if next token has race count pattern
            if race_count == 12 and i < len(tokens) - 1:
                next_token = tokens[i + 1]
                pair_patterns = [
                    r'^\((\d+)\)$',  # (5)
                    r'^\((\d+)$',    # (5
                    r'^(\d+)\)$'     # 5)
                ]

                for pattern in pair_patterns:
                    match = re.match(pattern, next_token.strip())
                    if match:
                        extracted_races = int(match.group(1))
                        if 1 <= extracted_races <= 11:
                            race_count = extracted_races
                            raw_name = f"{tokens[i]} {next_token}"
                            tokens_consumed = 2
                            logging.debug(f"🏁 Extracted race count from token pair '{tokens[i]}' + '{next_token}': {token_to_check} → {race_count} races")
                        break

            # Now try to resolve the clean name
            resolved = self._resolve_name(token_to_check, guild_id)
            if resolved:
                valid_names.append((i, resolved, raw_name, None, race_count))
                logging.info(f"✅ Found 1-word name: '{raw_name}' → '{resolved}' at position {i} ({race_count} races)")
                if tokens_consumed == 2:
                    i += 1  # Skip the next token if we consumed it
            else:
                # Fallback: substring matching disabled (6v6 splitting handles it post-team-detection)
                substring_match = None
                if False and len(tokens[i]) >= 5:
                    substring_match, _ = self.find_guild_name_in_substring(tokens[i], guild_id)
                    if substring_match:
                        consumed_tokens = 1
                        embedded_score = None
                        raw_name_parts = [tokens[i]]

                        for lookahead in range(1, min(3, len(tokens) - i)):
                            next_token = tokens[i + lookahead]
                            if len(next_token) < 3 or next_token.lower() in ['go', 'and', 'vs']:
                                continue

                            token_has_following_score = False
                            if i + lookahead < len(tokens) - 1:
                                following_token = tokens[i + lookahead + 1]
                                if following_token.isdigit() and 1 <= int(following_token) <= 180:
                                    token_has_following_score = True

                            if not token_has_following_score:
                                potential_score = extract_score_from_corrupted_token(next_token)
                                if potential_score:
                                    logging.debug(f"🔍 Multi-token corrupted sequence detected: '{tokens[i]}' + '{next_token}' contains score {potential_score}")
                                    embedded_score = potential_score
                                    raw_name_parts.append(next_token)
                                    consumed_tokens += lookahead
                                    break
                            else:
                                logging.debug(f"🔍 Skipping multi-token sequence for '{next_token}' because followed by valid score '{following_token}'")

                        raw_name = " ".join(raw_name_parts)
                        if embedded_score:
                            match_info = (i, substring_match, raw_name, embedded_score, 12)
                            logging.info(f"✅ Found multi-token corrupted match: '{raw_name}' → '{substring_match}' with embedded score {embedded_score} (12 races)")
                        else:
                            match_info = (i, substring_match, raw_name, None, 12)
                            logging.info(f"✅ Found substring match: '{tokens[i]}' contains '{substring_match}' at position {i} (12 races)")

                        valid_names.append(match_info)
                        i += consumed_tokens
                        continue
                    else:
                        logging.debug(f"Player '{tokens[i]}' not found in guild roster (likely opponent)")
                else:
                    logging.debug(f"Player '{tokens[i]}' not found in guild roster (likely opponent)")

            i += 1

        return valid_names
