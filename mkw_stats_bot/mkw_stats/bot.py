import discord
from discord.ext import commands
import asyncio
from typing import Optional, Dict, List
from dotenv import load_dotenv
from . import config
from .database import DatabaseManager
from .ocr_processor import OCRProcessor
from .services import WarService
from .handlers import OCRHandler, BulkScanHandler, ConfirmationManager, MessageManager
from .logging_config import get_logger, setup_logging
from .ocr_modals import EditPlayerModal, AddPlayerModal, ReportIssueModal

# Load environment variables from .env file if it exists
load_dotenv()

# Setup centralized logging
setup_logging()
logger = get_logger(__name__)


class OCRConfirmationView(discord.ui.View):
    """Interactive view for OCR war result confirmation with inline editing."""

    def __init__(self, results: List[Dict], guild_id: int, user_id: int, original_message_obj: discord.Message, bot):
        super().__init__(timeout=300)  # 5 minute timeout
        self.results = results
        self.guild_id = guild_id
        self.user_id = user_id
        self.original_message_obj = original_message_obj
        self.bot = bot
        self.message = None  # Set after message is sent

        # Build dropdown selects and action buttons
        self._build_view_components()

    async def _check_member_permission(self, interaction: discord.Interaction) -> bool:
        """
        Check if user has permission to interact with war menu.
        Returns True if user has member role, False otherwise.
        Sends error message to user if permission denied.
        """
        # Check if interaction is in a guild
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server",
                ephemeral=True
            )
            return False

        # Get guild role configuration
        role_config = self.bot.db.get_guild_role_config(self.guild_id)

        # If no role config is set, prompt user to set it up
        if not role_config or not role_config.get('role_member_id'):
            await interaction.response.send_message(
                "❌ No member role configured. An admin needs to run `/setroles` first to set up member/trial roles.",
                ephemeral=True
            )
            return False

        # Check if user has the member role
        member_role_id = role_config['role_member_id']
        user_role_ids = [role.id for role in interaction.user.roles]

        if member_role_id not in user_role_ids:
            # Get role name for error message
            member_role = interaction.guild.get_role(member_role_id)
            role_name = member_role.name if member_role else "Member"
            await interaction.response.send_message(
                f"❌ You need the **{role_name}** role to interact with war results",
                ephemeral=True
            )
            return False

        return True

    def _build_view_components(self):
        """Build dropdown selects and action buttons."""
        # Clear existing items
        self.clear_items()

        # Create dropdown for editing players
        if self.results:
            edit_select = discord.ui.Select(
                placeholder="Select player to edit",
                options=[
                    discord.SelectOption(
                        label=f"{i+1}. {result['name']} ({result['score']} pts, {result.get('races', 12)} races)",
                        value=str(i),
                        description=f"Edit {result['name']}'s name, score, or races"
                    )
                    for i, result in enumerate(self.results)
                ],
                row=0
            )
            edit_select.callback = self._edit_select_callback
            self.add_item(edit_select)

            # Create dropdown for removing players
            remove_select = discord.ui.Select(
                placeholder="Select player to remove",
                options=[
                    discord.SelectOption(
                        label=f"{i+1}. {result['name']} ({result['score']} pts, {result.get('races', 12)} races)",
                        value=str(i),
                        description=f"Remove {result['name']} from results"
                    )
                    for i, result in enumerate(self.results)
                ],
                row=1
            )
            remove_select.callback = self._remove_select_callback
            self.add_item(remove_select)

        # Add action buttons (row 2)
        # Add Player button
        add_btn = discord.ui.Button(
            label="+ Add Player",
            style=discord.ButtonStyle.success,
            custom_id="add_player",
            row=2
        )
        add_btn.callback = self._add_player_callback
        self.add_item(add_btn)

        # Save button
        save_btn = discord.ui.Button(
            label="✅ Save War",
            style=discord.ButtonStyle.primary,
            custom_id="save_war",
            row=2
        )
        save_btn.callback = self._save_war_callback
        self.add_item(save_btn)

        # Cancel button
        cancel_btn = discord.ui.Button(
            label="❌ Cancel",
            style=discord.ButtonStyle.danger,
            custom_id="cancel_war",
            row=2
        )
        cancel_btn.callback = self._cancel_war_callback
        self.add_item(cancel_btn)

    async def _edit_select_callback(self, interaction: discord.Interaction):
        """Callback for edit player dropdown."""
        if not await self._check_member_permission(interaction):
            return

        select = [item for item in self.children if isinstance(item, discord.ui.Select) and item.placeholder == "Select player to edit"][0]
        player_index = int(select.values[0])

        modal = EditPlayerModal(self, player_index)
        await interaction.response.send_modal(modal)

    async def _remove_select_callback(self, interaction: discord.Interaction):
        """Callback for remove player dropdown."""
        if not await self._check_member_permission(interaction):
            return

        select = [item for item in self.children if isinstance(item, discord.ui.Select) and item.placeholder == "Select player to remove"][0]
        player_index = int(select.values[0])

        removed_player = self.results.pop(player_index)
        logger.info(f"Removed player {removed_player['name']} from OCR results")

        await self.update_message(interaction)

    async def _add_player_callback(self, interaction: discord.Interaction):
        """Callback for add player button."""
        if not await self._check_member_permission(interaction):
            return

        modal = AddPlayerModal(self)
        await interaction.response.send_modal(modal)

    async def _save_war_callback(self, interaction: discord.Interaction):
        """Callback for save war button."""
        if not await self._check_member_permission(interaction):
            return

        await self.bot.ocr_handler.handle_war_submission_from_view(interaction, self)

    async def _cancel_war_callback(self, interaction: discord.Interaction):
        """Callback for cancel button."""
        if not await self._check_member_permission(interaction):
            return

        try:
            await self.original_message_obj.add_reaction("❌")
        except:
            pass

        embed = discord.Embed(
            title="❌ Results Cancelled",
            description="Results were not saved to the database.\n\n💡 **Found an issue with OCR detection?**\nYou can report it below to help improve accuracy.",
            color=0xff6600
        )

        report_view = ReportIssueView(self)
        report_view.message = interaction.message

        await interaction.response.edit_message(embed=embed, view=report_view)

    def create_embed(self) -> discord.Embed:
        """Create modern minimalistic embed for OCR confirmation."""
        filename = "image"
        if self.original_message_obj and self.original_message_obj.attachments:
            filename = self.original_message_obj.attachments[0].filename

        embed = discord.Embed(
            title="🏁 War Results from OCR",
            description=f"**{filename}**",
            color=0x00ff00
        )

        player_count = len(self.results)
        players_text = f"```\n📊 Detected Players ({player_count})\n\n"

        for i, result in enumerate(self.results, 1):
            name = result['name']
            score = result['score']
            races = result.get('races', 12)
            padded_name = name[:12].ljust(12)
            players_text += f"{i}. {padded_name} {score} pts ({races} races)\n"

        players_text += "```"

        embed.add_field(name="\u200b", value=players_text, inline=False)
        embed.set_footer(text="⏱️ Confirmation expires in 5 minutes • Use dropdowns to select players to edit or remove")

        return embed

    async def update_message(self, interaction: discord.Interaction):
        """Update the message with refreshed embed and view components."""
        self._build_view_components()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        """Handle view timeout."""
        if self.message:
            try:
                embed = discord.Embed(
                    title="⏱️ Confirmation Expired",
                    description="Results were not saved (timed out after 5 minutes).",
                    color=0x95a5a6
                )
                await self.message.edit(embed=embed, view=None)

                asyncio.create_task(self.bot.messages.countdown_and_delete_message(self.message, embed, 30))
            except discord.NotFound:
                pass
            except discord.Forbidden:
                logger.warning("Missing permissions to edit OCR confirmation message on timeout")
            except discord.HTTPException as e:
                logger.error(f"Failed to edit OCR confirmation message on timeout: {e}")
            except Exception as e:
                logger.error(f"Unexpected error editing OCR confirmation message on timeout: {e}", exc_info=True)


class ReportIssueView(discord.ui.View):
    """View for reporting OCR issues."""

    def __init__(self, ocr_view: OCRConfirmationView):
        super().__init__(timeout=300)
        self.ocr_view = ocr_view
        self.message = None

    @discord.ui.button(label="🚩 Report Issue with Scan", style=discord.ButtonStyle.secondary)
    async def report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal to report OCR issue."""
        if not await self.ocr_view._check_member_permission(interaction):
            return

        modal = ReportIssueModal(self.ocr_view, self, button)
        await interaction.response.send_modal(modal)

    async def on_timeout(self):
        """Handle view timeout - delete the message."""
        if self.message:
            try:
                await self.message.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                logger.warning("Missing permissions to delete report issue message on timeout")
            except discord.HTTPException as e:
                logger.error(f"Failed to delete report issue message on timeout: {e}")
            except Exception as e:
                logger.error(f"Unexpected error deleting report issue message on timeout: {e}", exc_info=True)


class MarioKartBot(commands.Bot):
    """Main bot class. Delegates to specialized handlers for OCR, bulk scan, confirmations, and message lifecycle."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        intents.members = True

        super().__init__(command_prefix=None, intents=intents)

        # Core infrastructure
        self.db = DatabaseManager()
        self.war_service = WarService(self.db)
        self.ocr = OCRProcessor(db_manager=self.db)

        # Confirmation state (accessed directly by commands.py)
        self.pending_confirmations = {}  # message_id -> confirmation_data
        self.timeout_tasks = {}  # message_id -> asyncio.Task

        # Handlers
        self.messages = MessageManager(self)
        self.confirmations = ConfirmationManager(self)
        self.ocr_handler = OCRHandler(self)
        self.bulk_scan_handler = BulkScanHandler(self)

    async def on_ready(self) -> None:
        """Event handler called when bot is ready."""
        logger.info(f'{self.user} has connected to Discord!')
        logger.info(f'Bot is in {len(self.guilds)} guilds')
        logger.info(f'🔧 Bot Version: {config.BOT_VERSION}')

        logger.info("🔧 Automatic roster initialization disabled - use /setup command")
        logger.info("🔧 Using slash commands only - prefix commands disabled")

        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"✅ Synced {len(synced)} slash command(s)")
        except Exception as e:
            logger.error(f"❌ Failed to sync slash commands: {e}")

        # Initialize OCR resource management if available
        try:
            if hasattr(self.ocr, 'resource_management_enabled') and self.ocr.resource_management_enabled:
                from .ocr_resource_manager import initialize_ocr_resource_manager
                from .ocr_performance_monitor import get_ocr_performance_monitor

                initialize_ocr_resource_manager()

                performance_monitor = get_ocr_performance_monitor()
                performance_monitor.start_monitoring()

                logger.info("🚀 OCR resource management and performance monitoring started")
            else:
                logger.info("📝 OCR running in basic mode (no resource management)")
        except Exception as e:
            logger.warning(f"Failed to initialize OCR resource management: {e}")

        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for Mario Kart results 🏁"
            )
        )

    async def on_command_error(self, ctx, error):
        """Handle command errors - should not occur with prefix commands disabled."""
        if isinstance(error, commands.CommandNotFound):
            logger.debug(f"Ignored prefix command attempt: {ctx.message.content}")
            return

        logger.error(f"Command error: {error}")
        logger.error(f"Context: {ctx.message.content if ctx.message else 'Unknown'}")

    async def on_message(self, message):
        """Route image messages to OCR handler."""
        if message.author == self.user:
            return

        if message.attachments:
            guild_id = message.guild.id if message.guild else None
            if not guild_id:
                return

            configured_channel_id = self.db.get_ocr_channel(guild_id)
            if not configured_channel_id or message.channel.id != configured_channel_id:
                return

            for attachment in message.attachments:
                if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                    await self.ocr_handler.process_race_results(message, attachment)

    async def on_reaction_add(self, reaction, user):
        """Route reactions to confirmation manager."""
        await self.confirmations.handle_reaction(reaction, user)

    # ── Backward-compatible delegation methods ──────────────────────────
    # These are called by commands.py, ocr_modals.py, and views.
    # They delegate to the appropriate handler instance.

    async def process_ocr_image(self, *args, **kwargs):
        return await self.ocr_handler.process_image(*args, **kwargs)

    async def handle_ocr_war_submission_from_view(self, *args, **kwargs):
        return await self.ocr_handler.handle_war_submission_from_view(*args, **kwargs)

    async def send_ocr_report(self, *args, **kwargs):
        return await self.ocr_handler.send_report(*args, **kwargs)

    def format_enhanced_confirmation(self, *args, **kwargs):
        return self.ocr_handler.format_enhanced_confirmation(*args, **kwargs)

    def cleanup_confirmation(self, *args, **kwargs):
        return self.confirmations.cleanup(*args, **kwargs)

    async def _auto_delete_message(self, *args, **kwargs):
        return await self.messages.auto_delete(*args, **kwargs)

    async def _countdown_and_delete_message(self, *args, **kwargs):
        return await self.messages.countdown_and_delete_message(*args, **kwargs)

    async def _countdown_and_delete_interaction(self, *args, **kwargs):
        return await self.messages.countdown_and_delete_interaction(*args, **kwargs)


async def setup_bot():
    """Setup function that creates the bot and loads the commands cog."""
    bot = MarioKartBot()

    # Load the commands cog
    from .commands import MarioKartCommands
    await bot.add_cog(MarioKartCommands(bot))

    return bot

# Run the bot
if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        print("❌ Please set DISCORD_BOT_TOKEN environment variable")
        exit(1)

    # Use asyncio to run the bot setup and start
    import asyncio

    async def main():
        bot = await setup_bot()
        await bot.start(config.DISCORD_TOKEN)

    asyncio.run(main())
