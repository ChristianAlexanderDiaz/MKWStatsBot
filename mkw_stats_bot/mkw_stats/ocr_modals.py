"""
Discord UI Modals for OCR War Result Editing
"""

import discord
from discord import ui
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bot import OCRConfirmationView


class EditPlayerModal(ui.Modal, title="Edit Player"):
    """Modal for editing player name and score."""

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

    def __init__(self, view: 'OCRConfirmationView', player_index: int):
        super().__init__()
        self.view = view
        self.player_index = player_index

        # Pre-fill with current values
        current_player = view.results[player_index]
        self.player_name.default = current_player['name']
        self.player_score.default = str(current_player['score'])

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

            # Update player in results
            self.view.results[self.player_index]['name'] = self.player_name.value.strip()
            self.view.results[self.player_index]['score'] = score
            self.view.results[self.player_index]['raw_name'] = self.player_name.value.strip()

            # Refresh the view
            await self.view.update_message(interaction)

        except ValueError:
            await interaction.response.send_message(
                "❌ Score must be a valid number",
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

            # Check for duplicate names
            name = self.player_name.value.strip()
            if any(r['name'].lower() == name.lower() for r in self.view.results):
                await interaction.response.send_message(
                    f"❌ Player '{name}' already exists in results",
                    ephemeral=True
                )
                return

            # Add new player to results
            new_player = {
                'name': name,
                'raw_name': name,
                'score': score,
                'races': 12,
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
                "❌ Score must be a valid number",
                ephemeral=True
            )
