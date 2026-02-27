"""
Guild repository: Guild configuration, teams, tags, roles, and OCR channel settings.
"""

import json
import logging
from typing import List, Dict, Optional

from .base import BaseRepository


class GuildRepository(BaseRepository):
    """Handles all guild configuration database operations."""

    def set_ocr_channel(self, guild_id: int, channel_id: int) -> bool:
        """Set the OCR channel for automatic image processing in a guild."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO guild_configs (guild_id, ocr_channel_id, is_active)
                    VALUES (%s, %s, TRUE)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        ocr_channel_id = EXCLUDED.ocr_channel_id,
                        updated_at = CURRENT_TIMESTAMP
                """, (guild_id, channel_id))

                conn.commit()
                logging.info(f"✅ Set OCR channel {channel_id} for guild {guild_id}")
                return True

        except Exception as e:
            logging.error(f"❌ Error setting OCR channel: {e}")
            return False

    def get_ocr_channel(self, guild_id: int) -> Optional[int]:
        """Get the OCR channel ID for a guild."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT ocr_channel_id
                    FROM guild_configs
                    WHERE guild_id = %s AND is_active = TRUE
                """, (guild_id,))

                result = cursor.fetchone()
                return result[0] if result and result[0] else None

        except Exception as e:
            logging.error(f"❌ Error getting OCR channel: {e}")
            return None

    def get_guild_config(self, guild_id: int) -> Optional[Dict]:
        """Get guild configuration settings."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT guild_id, guild_name, team_names, is_active, created_at, updated_at
                    FROM guild_configs WHERE guild_id = %s
                """, (guild_id,))

                result = cursor.fetchone()
                if not result:
                    return None

                return {
                    'guild_id': result[0],
                    'guild_name': result[1],
                    'team_names': result[2] if result[2] else [],
                    'is_active': result[3],
                    'created_at': result[4].isoformat() if result[4] else None,
                    'updated_at': result[5].isoformat() if result[5] else None
                }

        except Exception as e:
            logging.error(f"❌ Error getting guild config: {e}")
            return None

    def create_guild_config(self, guild_id: int, guild_name: str = None, team_names: List[str] = None) -> bool:
        """Create a new guild configuration."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                if team_names is None:
                    team_names = []

                cursor.execute("""
                    INSERT INTO guild_configs (guild_id, guild_name, team_names)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        guild_name = EXCLUDED.guild_name,
                        team_names = EXCLUDED.team_names,
                        is_active = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                """, (guild_id, guild_name, json.dumps(team_names)))

                conn.commit()
                logging.info(f"✅ Created/updated guild config for {guild_id}")
                return True

        except Exception as e:
            logging.error(f"❌ Error creating guild config: {e}")
            return False

    def update_guild_config(self, guild_id: int, **kwargs) -> bool:
        """Update guild configuration settings."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                update_fields = []
                values = []

                for key, value in kwargs.items():
                    if key in ['guild_name', 'team_names', 'is_active']:
                        if key in ['team_names']:
                            update_fields.append(f"{key} = %s")
                            values.append(json.dumps(value))
                        else:
                            update_fields.append(f"{key} = %s")
                            values.append(value)

                if not update_fields:
                    return False

                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                values.append(guild_id)

                query = f"UPDATE guild_configs SET {', '.join(update_fields)} WHERE guild_id = %s"
                cursor.execute(query, values)

                conn.commit()
                logging.info(f"✅ Updated guild config for {guild_id}")
                return True

        except Exception as e:
            logging.error(f"❌ Error updating guild config: {e}")
            return False

    def get_guild_team_names(self, guild_id: int) -> List[str]:
        """Get valid team names for a guild."""
        config = self.get_guild_config(guild_id)
        if config:
            return config.get('team_names', [])
        return []

    def is_channel_allowed(self, guild_id: int, channel_id: int) -> bool:
        """Check if a channel is allowed for bot commands."""
        return True

    # Team Management Methods

    def add_guild_team(self, guild_id: int, team_name: str) -> bool:
        """Add a new team to a guild's configuration."""
        try:
            if not self.validate_team_name(team_name):
                return False

            current_teams = self.get_guild_team_names(guild_id)

            if any(team.lower() == team_name.lower() for team in current_teams):
                logging.error(f"Team '{team_name}' already exists in guild {guild_id}")
                return False

            if len(current_teams) >= 5:
                logging.error(f"Guild {guild_id} has reached maximum team limit (5)")
                return False

            new_teams = current_teams + [team_name]
            success = self.update_guild_config(guild_id, team_names=new_teams)

            if success:
                logging.info(f"✅ Added team '{team_name}' to guild {guild_id}")

            return success

        except Exception as e:
            logging.error(f"❌ Error adding team to guild: {e}")
            return False

    def remove_guild_team(self, guild_id: int, team_name: str) -> bool:
        """Remove a team from a guild's configuration and move players to Unassigned."""
        try:
            current_teams = self.get_guild_team_names(guild_id)

            team_to_remove = None
            for team in current_teams:
                if team.lower() == team_name.lower():
                    team_to_remove = team
                    break

            if not team_to_remove:
                logging.error(f"Team '{team_name}' not found in guild {guild_id}")
                return False

            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE players
                    SET team = 'Unassigned', updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = %s AND team = %s
                """, (guild_id, team_to_remove))

                moved_players = cursor.rowcount

                new_teams = [team for team in current_teams if team != team_to_remove]
                success = self.update_guild_config(guild_id, team_names=new_teams)

                if success:
                    conn.commit()
                    logging.info(f"✅ Removed team '{team_to_remove}' from guild {guild_id}, moved {moved_players} players to Unassigned")
                    return True
                else:
                    conn.rollback()
                    return False

        except Exception as e:
            logging.error(f"❌ Error removing team from guild: {e}")
            return False

    def rename_guild_team(self, guild_id: int, old_name: str, new_name: str) -> bool:
        """Rename a team in a guild's configuration and update player assignments."""
        try:
            if not self.validate_team_name(new_name):
                return False

            current_teams = self.get_guild_team_names(guild_id)

            team_to_rename = None
            for team in current_teams:
                if team.lower() == old_name.lower():
                    team_to_rename = team
                    break

            if not team_to_rename:
                logging.error(f"Team '{old_name}' not found in guild {guild_id}")
                return False

            if any(team.lower() == new_name.lower() for team in current_teams if team != team_to_rename):
                logging.error(f"Team '{new_name}' already exists in guild {guild_id}")
                return False

            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE players
                    SET team = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = %s AND team = %s
                """, (new_name, guild_id, team_to_rename))

                updated_players = cursor.rowcount

                new_teams = [new_name if team == team_to_rename else team for team in current_teams]
                success = self.update_guild_config(guild_id, team_names=new_teams)

                if success:
                    conn.commit()
                    logging.info(f"✅ Renamed team '{team_to_rename}' to '{new_name}' in guild {guild_id}, updated {updated_players} players")
                    return True
                else:
                    conn.rollback()
                    return False

        except Exception as e:
            logging.error(f"❌ Error renaming team in guild: {e}")
            return False

    def validate_team_name(self, team_name: str) -> bool:
        """Validate a team name according to rules."""
        if not team_name or not team_name.strip():
            logging.error("Team name cannot be empty or whitespace-only")
            return False

        if len(team_name) < 1 or len(team_name) > 50:
            logging.error(f"Team name must be 1-50 characters long, got {len(team_name)}")
            return False

        if team_name.lower() == 'unassigned':
            logging.error("'Unassigned' is a reserved team name")
            return False

        return True

    def get_guild_teams_with_counts(self, guild_id: int) -> Dict[str, int]:
        """Get all teams for a guild with player counts."""
        try:
            teams = self._db.players.get_players_by_team(guild_id=guild_id)
            return {team_name: len(players) for team_name, players in teams.items()}

        except Exception as e:
            logging.error(f"❌ Error getting guild teams with counts: {e}")
            return {}

    # Team Tag Management Methods

    def set_team_tag(self, guild_id: int, team_name: str, tag: str) -> bool:
        """Set a tag for a team in a guild's configuration."""
        try:
            self._validate_guild_id(guild_id, "set_team_tag")

            if not tag or not tag.strip():
                logging.error("Tag cannot be empty or whitespace-only")
                return False

            tag = tag.strip()

            if len(tag) < 1 or len(tag) > 8:
                logging.error(f"Tag must be 1-8 characters long, got {len(tag)}")
                return False

            if '\n' in tag or '\r' in tag:
                logging.error("Tag cannot contain newline characters")
                return False

            current_teams = self.get_guild_team_names(guild_id)

            team_to_tag = None
            for team in current_teams:
                if team.lower() == team_name.lower():
                    team_to_tag = team
                    break

            if not team_to_tag:
                logging.error(f"Team '{team_name}' not found in guild {guild_id}")
                return False

            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT team_tags FROM guild_configs WHERE guild_id = %s
                """, (guild_id,))

                result = cursor.fetchone()
                if not result:
                    logging.error(f"Guild {guild_id} not found in guild_configs")
                    return False

                team_tags = result[0] if result[0] else {}
                team_tags[team_to_tag] = tag

                cursor.execute("""
                    UPDATE guild_configs
                    SET team_tags = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = %s
                """, (json.dumps(team_tags), guild_id))

                conn.commit()
                logging.info(f"✅ Set tag '{tag}' for team '{team_to_tag}' in guild {guild_id}")
                return True

        except Exception as e:
            logging.error(f"❌ Error setting team tag: {e}")
            return False

    def get_team_tag(self, guild_id: int, team_name: str) -> Optional[str]:
        """Get the tag for a team in a guild."""
        try:
            self._validate_guild_id(guild_id, "get_team_tag")

            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT team_tags FROM guild_configs WHERE guild_id = %s
                """, (guild_id,))

                result = cursor.fetchone()
                if not result or not result[0]:
                    return None

                team_tags = result[0]

                if team_name in team_tags:
                    return team_tags[team_name]

                for team, tag in team_tags.items():
                    if team.lower() == team_name.lower():
                        return tag

                return None

        except Exception as e:
            logging.error(f"❌ Error getting team tag: {e}")
            return None

    def remove_team_tag(self, guild_id: int, team_name: str) -> bool:
        """Remove the tag from a team in a guild's configuration."""
        try:
            self._validate_guild_id(guild_id, "remove_team_tag")

            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT team_tags FROM guild_configs WHERE guild_id = %s
                """, (guild_id,))

                result = cursor.fetchone()
                if not result:
                    logging.error(f"Guild {guild_id} not found in guild_configs")
                    return False

                team_tags = result[0] if result[0] else {}

                team_to_remove = None
                for team in team_tags.keys():
                    if team.lower() == team_name.lower():
                        team_to_remove = team
                        break

                if not team_to_remove:
                    logging.error(f"No tag set for team '{team_name}' in guild {guild_id}")
                    return False

                del team_tags[team_to_remove]

                cursor.execute("""
                    UPDATE guild_configs
                    SET team_tags = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = %s
                """, (json.dumps(team_tags), guild_id))

                conn.commit()
                logging.info(f"✅ Removed tag from team '{team_to_remove}' in guild {guild_id}")
                return True

        except Exception as e:
            logging.error(f"❌ Error removing team tag: {e}")
            return False

    def get_all_team_tags(self, guild_id: int) -> Dict[str, str]:
        """Get all team tags for a guild."""
        try:
            self._validate_guild_id(guild_id, "get_all_team_tags")

            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT team_tags FROM guild_configs WHERE guild_id = %s
                """, (guild_id,))

                result = cursor.fetchone()
                if not result or not result[0]:
                    return {}

                return result[0]

        except Exception as e:
            logging.error(f"❌ Error getting all team tags: {e}")
            return {}

    # Role Configuration Methods

    def get_guild_role_config(self, guild_id: int) -> Optional[Dict]:
        """Get the role configuration for a guild."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT role_member_id, role_trial_id, role_ally_id
                    FROM guild_configs
                    WHERE guild_id = %s AND is_active = TRUE
                """, (guild_id,))

                result = cursor.fetchone()
                if result:
                    return {
                        'role_member_id': result[0],
                        'role_trial_id': result[1],
                        'role_ally_id': result[2]
                    }
                return None

        except Exception as e:
            logging.error(f"❌ Error getting guild role config: {e}")
            return None

    def set_guild_role_config(
        self,
        guild_id: int,
        role_member_id: int,
        role_trial_id: int,
        role_ally_id: int
    ) -> bool:
        """Set the role configuration for a guild."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id FROM guild_configs WHERE guild_id = %s
                """, (guild_id,))

                if cursor.fetchone():
                    cursor.execute("""
                        UPDATE guild_configs
                        SET role_member_id = %s,
                            role_trial_id = %s,
                            role_ally_id = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE guild_id = %s
                    """, (role_member_id, role_trial_id, role_ally_id, guild_id))
                else:
                    cursor.execute("""
                        INSERT INTO guild_configs (
                            guild_id, role_member_id, role_trial_id, role_ally_id, is_active
                        )
                        VALUES (%s, %s, %s, %s, TRUE)
                    """, (guild_id, role_member_id, role_trial_id, role_ally_id))

                conn.commit()
                logging.info(f"✅ Set role config for guild {guild_id}")
                return True

        except Exception as e:
            logging.error(f"❌ Error setting guild role config: {e}")
            return False
