"""
Discord UI Modals for OCR War Result Editing
"""

import discord
from discord import ui
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bot import OCRConfirmationView


class EditPlayerModal(ui.Modal, title="Edit Player"):
    """Modal for editing player name, score, and races played."""

    player_name = ui.TextInput(
        label="Player Name",
        placeholder="Enter player name",
        required=True,
        max_length=50
    )

    player_score = ui.TextInput(
        label="Score",
        placeholder="Enter score (1-180)",
        required=True,
        max_length=3
    )

    races_played = ui.TextInput(
        label="Races Played",
        placeholder="Enter races played (1-12)",
        required=True,
        max_length=2
    )

    def __init__(self, view: 'OCRConfirmationView', player_index: int):
        super().__init__()
        self.view = view
        self.player_index = player_index

        # Pre-fill with current values
        current_player = view.results[player_index]
        self.player_name.default = current_player['name']
        self.player_score.default = str(current_player['score'])
        self.races_played.default = str(current_player.get('races', 12))

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            # Validate score
            score = int(self.player_score.value)
            if not (1 <= score <= 180):
                await interaction.response.send_message(
                    "❌ Score must be between 1 and 180",
                    ephemeral=True
                )
                return

            # Validate races played
            races = int(self.races_played.value)
            if not (1 <= races <= 12):
                await interaction.response.send_message(
                    "❌ Races played must be between 1 and 12",
                    ephemeral=True
                )
                return

            # Update player in results
            self.view.results[self.player_index]['name'] = self.player_name.value.strip()
            self.view.results[self.player_index]['score'] = score
            self.view.results[self.player_index]['races'] = races
            self.view.results[self.player_index]['raw_name'] = self.player_name.value.strip()

            # Refresh the view
            await self.view.update_message(interaction)

        except ValueError:
            await interaction.response.send_message(
                "❌ Score and races must be valid numbers",
                ephemeral=True
            )


class AddPlayerModal(ui.Modal, title="Add Player"):
    """Modal for adding a new player to results."""

    player_name = ui.TextInput(
        label="Player Name",
        placeholder="Enter player name",
        required=True,
        max_length=50
    )

    player_score = ui.TextInput(
        label="Score",
        placeholder="Enter score (1-180)",
        required=True,
        max_length=3
    )

    races_played = ui.TextInput(
        label="Races Played",
        placeholder="Enter races played (1-12)",
        required=True,
        max_length=2,
        default="12"
    )

    def __init__(self, view: 'OCRConfirmationView'):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            # Validate score
            score = int(self.player_score.value)
            if not (1 <= score <= 180):
                await interaction.response.send_message(
                    "❌ Score must be between 1 and 180",
                    ephemeral=True
                )
                return

            # Validate races played
            races = int(self.races_played.value)
            if not (1 <= races <= 12):
                await interaction.response.send_message(
                    "❌ Races played must be between 1 and 12",
                    ephemeral=True
                )
                return

            # Check for duplicate names
            name = self.player_name.value.strip()
            if any(r['name'].lower() == name.lower() for r in self.view.results):
                await interaction.response.send_message(
                    f"❌ Player '{name}' already exists in results",
                    ephemeral=True
                )
                return

            # Ensure player exists in database before adding to war results
            guild_id = self.view.guild_id
            db = self.view.bot.db

            # Check if player already exists in roster
            existing_player = db.get_player_info(name, guild_id)
            if not existing_player:
                # Add player to roster with default team 'Unassigned'
                added = db.add_roster_player(
                    name,
                    added_by=str(interaction.user),
                    guild_id=guild_id,
                    member_status='member'
                )
                if not added:
                    await interaction.response.send_message(
                        f"❌ Failed to add player '{name}' to roster. Please try again or contact an admin.",
                        ephemeral=True
                    )
                    return

            # Add new player to results (now safe because player exists in DB)
            new_player = {
                'name': name,
                'raw_name': name,
                'score': score,
                'races': races,
                'raw_line': f"{name} {score}",
                'preset_used': 'manual_add',
                'confidence': 1.0,
                'is_roster_member': True
            }
            self.view.results.append(new_player)

            # Refresh the view
            await self.view.update_message(interaction)

        except ValueError:
            await interaction.response.send_message(
                "❌ Score and races must be valid numbers",
                ephemeral=True
            )


class ReportIssueModal(ui.Modal, title="Report OCR Issue"):
    """Modal for reporting incorrect OCR scan results."""

    issue_description = ui.TextInput(
        label="What was incorrect with the scan?",
        style=discord.TextStyle.paragraph,
        placeholder="Example: OCR read 'Null' instead of 'Chez', or missed a player entirely",
        required=True,
        max_length=500
    )

    def __init__(self, ocr_view: 'OCRConfirmationView', report_view: 'ReportIssueView' = None, button: 'discord.ui.Button' = None):
        super().__init__()
        self.ocr_view = ocr_view
        self.report_view = report_view
        self.button = button

    async def on_submit(self, interaction: discord.Interaction):
        """Handle report submission."""
        try:
            # Send report to admin
            await self.ocr_view.bot.send_ocr_report(
                guild_id=self.ocr_view.guild_id,
                user=interaction.user,
                original_image=self.ocr_view.original_message_obj.attachments[0] if self.ocr_view.original_message_obj.attachments else None,
                ocr_results=self.ocr_view.results,
                user_description=self.issue_description.value
            )

            await interaction.response.send_message(
                "✅ **Report sent!** Thank you for helping improve OCR accuracy.",
                ephemeral=True
            )

            # Disable the button so it can only be used once
            if self.button:
                self.button.disabled = True

            # Update the message to show button is disabled, then delete after countdown
            if self.report_view and self.report_view.message:
                try:
                    await self.report_view.message.edit(view=self.report_view)
                    # Schedule deletion with countdown
                    import asyncio
                    asyncio.create_task(self.ocr_view.bot._countdown_and_delete_message(
                        self.report_view.message,
                        self.report_view.message.embeds[0] if self.report_view.message.embeds else None,
                        countdown_seconds=10
                    ))
                except:
                    pass

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to send report: {str(e)}",
                ephemeral=True
            )
