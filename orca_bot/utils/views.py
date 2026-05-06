"""Discord UI views for queue pagination and playback controls."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from orca_bot.utils.voice_state import VoiceState

VIEW_TIMEOUT_SEC = 1800
AUTHOR_ONLY_CONTROLS_MESSAGE = (
    "Only the command author can use these controls."
)
INACTIVE_CONTROLS_MESSAGE = (
    "These controls are no longer active. Start playback again."
)
CLEAR_QUEUE_PROMPT = "Are you sure you want to clear the queue?"
QUEUE_CLEARED_MESSAGE = "The queue has been cleared."
QUEUE_CLEAR_CANCELLED_MESSAGE = "Cancelled clearing the queue."
PREVIOUS_BUTTON_LABEL = "Previous"
NEXT_BUTTON_LABEL = "Next"
PREVIOUS_BUTTON_ID = "previous"
NEXT_BUTTON_ID = "next"
VOLUME_STEP_PERCENT = 10
NOW_PLAYING_BUTTON_SPECS = (
    ("Pause", "⏸️", "now-playing:pause", "pause_callback"),
    ("Resume", "▶️", "now-playing:resume", "resume_callback"),
    ("Shuffle", "🔀", "now-playing:shuffle", "shuffle_callback"),
    ("Queue", "📜", "now-playing:queue", "queue_callback"),
    ("Skip", "⏭️", "now-playing:skip", "skip_callback"),
    ("Clear", "🧹", "now-playing:clear", "clear_callback"),
    ("Volume Up", "🔊", "now-playing:volume-up", "volume_up_callback"),
    (
        "Volume Down",
        "🔉",
        "now-playing:volume-down",
        "volume_down_callback",
    ),
)


async def _check_view_access(
    ctx: commands.Context,
    interaction: discord.Interaction,
) -> bool:
    """Allow only the original command author to use a view."""

    voice_state = getattr(ctx, "voice_state", None)
    if voice_state is not None:
        voice_state.last_activity = datetime.now(timezone.utc)

    if interaction.user == ctx.author:
        return True

    if not interaction.response.is_done():
        await interaction.response.send_message(
            AUTHOR_ONLY_CONTROLS_MESSAGE,
            ephemeral=True,
        )
    return False


class QueuePages(discord.ui.View):
    """Pagination controls for queue embeds."""

    def __init__(
        self,
        ctx: commands.Context,
        pages: list[discord.Embed],
        current_page: int = 0,
    ) -> None:
        """Initialize queue pagination buttons and state."""

        super().__init__(timeout=VIEW_TIMEOUT_SEC)
        self.ctx = ctx
        self.pages = pages
        self.current_page = current_page
        self.message: discord.Message | None = None

        self.previous_button = discord.ui.Button(
            label=PREVIOUS_BUTTON_LABEL,
            style=discord.ButtonStyle.primary,
            custom_id=PREVIOUS_BUTTON_ID,
        )
        self.next_button = discord.ui.Button(
            label=NEXT_BUTTON_LABEL,
            style=discord.ButtonStyle.primary,
            custom_id=NEXT_BUTTON_ID,
        )
        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page

        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.update_buttons()

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """Restrict queue pagination controls to the original caller."""

        return await _check_view_access(self.ctx, interaction)

    def update_buttons(self) -> None:
        """Enable or disable pagination buttons for the current page."""

        self.previous_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= len(self.pages) - 1

    async def previous_page(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Show the previous queue page."""

        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            self.message = interaction.message
            await interaction.response.edit_message(
                embed=self.pages[self.current_page],
                view=self,
            )

    async def next_page(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Show the next queue page."""

        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            self.message = interaction.message
            await interaction.response.edit_message(
                embed=self.pages[self.current_page],
                view=self,
            )

    async def on_timeout(self) -> None:
        """Disable pagination controls when the view expires."""

        for child in self.children:
            child.disabled = True
        if self.message is not None:
            await self.message.edit(view=self)


class NowPlayingButtons(discord.ui.View):
    """Playback controls for the now-playing embed."""

    def __init__(self, ctx: commands.Context | None = None) -> None:
        """Initialize the playback control buttons."""

        super().__init__(timeout=None)
        self.ctx = ctx
        self.message: discord.Message | None = None

        for label, emoji, custom_id, callback_name in NOW_PLAYING_BUTTON_SPECS:
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
                emoji=emoji,
                custom_id=custom_id,
            )
            button.callback = getattr(self, callback_name)
            self.add_item(button)

    @staticmethod
    def _build_action_message(
        display_name: str,
        action: str,
    ) -> str:
        """Return a standardized action message for the now-playing embed."""

        return f"**{display_name} {action}.**"

    def _get_voice_state(
        self,
        interaction: discord.Interaction,
    ) -> VoiceState | None:
        """Return the voice state associated with this interaction."""

        if self.ctx is not None:
            voice_state = getattr(self.ctx, "voice_state", None)
            if voice_state is not None:
                return voice_state

        if interaction.guild is None:
            return None

        music_cog = interaction.client.get_cog("Music")
        if music_cog is None:
            return None

        return music_cog.voice_states.get(interaction.guild.id)

    def _get_active_voice_state(
        self,
        interaction: discord.Interaction,
    ) -> VoiceState | None:
        """Return the active voice state for the now-playing message."""

        voice_state = self._get_voice_state(interaction)
        if voice_state is None:
            return None

        active_message = getattr(voice_state, "now_playing_message", None)
        if active_message is None:
            return None

        if (
            interaction.message is None
            or active_message.id != interaction.message.id
        ):
            return None

        return voice_state

    async def _get_checked_voice_state(
        self,
        interaction: discord.Interaction,
    ) -> VoiceState | None:
        """Return the active voice state or notify the user if inactive."""

        voice_state = self._get_active_voice_state(interaction)
        if voice_state is None:
            await self._send_inactive_message(interaction)
        return voice_state

    async def _send_inactive_message(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Send an ephemeral message when a control view is stale."""

        if interaction.response.is_done():
            await interaction.followup.send(
                INACTIVE_CONTROLS_MESSAGE,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                INACTIVE_CONTROLS_MESSAGE,
                ephemeral=True,
            )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """Reject interactions that target stale controls or the wrong user."""

        voice_state = self._get_active_voice_state(interaction)
        if voice_state is None:
            await self._send_inactive_message(interaction)
            return False

        if self.ctx is None:
            voice_state.last_activity = datetime.now(timezone.utc)
            return True

        return await _check_view_access(self.ctx, interaction)

    async def _defer(self, interaction: discord.Interaction) -> None:
        """Defer an interaction response when no immediate message is sent."""

        if not interaction.response.is_done():
            await interaction.response.defer()

    async def pause_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Pause the current player."""

        voice_state = await self._get_checked_voice_state(interaction)
        if voice_state is None:
            return

        player = interaction.guild.voice_client if interaction.guild else None
        await self._defer(interaction)
        if player and player.is_playing():
            player.pause()
            voice_state.action_message = self._build_action_message(
                interaction.user.display_name,
                "paused the player",
            )
            await voice_state.update_now_playing_embed()

    async def resume_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Resume the paused player."""

        voice_state = await self._get_checked_voice_state(interaction)
        if voice_state is None:
            return

        player = interaction.guild.voice_client if interaction.guild else None
        await self._defer(interaction)
        if player and player.is_paused():
            player.resume()
            voice_state.action_message = self._build_action_message(
                interaction.user.display_name,
                "resumed the player",
            )
            await voice_state.update_now_playing_embed()

    async def shuffle_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Shuffle the queue and refresh the related views."""

        voice_state = await self._get_checked_voice_state(interaction)
        if voice_state is None:
            return

        await self._defer(interaction)
        if voice_state.is_playing:
            voice_state.songs.shuffle()
            await voice_state.update_queue_message()
            voice_state.action_message = self._build_action_message(
                interaction.user.display_name,
                "shuffled the queue",
            )
            await voice_state.update_now_playing_embed()

    async def queue_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Show the current queue."""

        voice_state = await self._get_checked_voice_state(interaction)
        if voice_state is None:
            return

        await self._defer(interaction)
        await voice_state.show_queue(page=1)

    async def skip_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Skip the current song."""

        voice_state = await self._get_checked_voice_state(interaction)
        if voice_state is None:
            return

        await self._defer(interaction)
        if voice_state.is_playing:
            voice_state.action_message = self._build_action_message(
                interaction.user.display_name,
                "skipped the song",
            )
            await voice_state.update_now_playing_embed()
            voice_state.skip()

    async def clear_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Prompt the user to confirm clearing the queue."""

        voice_state = await self._get_checked_voice_state(interaction)
        if voice_state is None:
            return

        ctx = self.ctx or await commands.Context.from_interaction(interaction)
        if voice_state.is_playing:
            view = ClearQueueConfirmation(ctx, voice_state)
            if interaction.response.is_done():
                view.message = await interaction.followup.send(
                    CLEAR_QUEUE_PROMPT,
                    view=view,
                    wait=True,
                )
            else:
                await interaction.response.send_message(
                    CLEAR_QUEUE_PROMPT,
                    view=view,
                )
                view.message = await interaction.original_response()
            return

        if not interaction.response.is_done():
            await interaction.response.defer()

    async def volume_up_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Increase the player volume."""

        voice_state = await self._get_checked_voice_state(interaction)
        if voice_state is None:
            return

        await self._defer(interaction)
        await voice_state.change_volume(VOLUME_STEP_PERCENT, interaction)

    async def volume_down_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Decrease the player volume."""

        voice_state = await self._get_checked_voice_state(interaction)
        if voice_state is None:
            return

        await self._defer(interaction)
        await voice_state.change_volume(-VOLUME_STEP_PERCENT, interaction)


class ClearQueueConfirmation(discord.ui.View):
    """Confirmation dialog for clearing the queue."""

    def __init__(
        self,
        ctx: commands.Context,
        voice_state: VoiceState,
    ) -> None:
        """Store the command context and current voice state."""

        super().__init__(timeout=VIEW_TIMEOUT_SEC)
        self.ctx = ctx
        self.voice_state = voice_state
        self.message: discord.Message | None = None

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """Restrict confirmation interactions to the command author."""

        return await _check_view_access(self.ctx, interaction)

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        """Clear the queue after the user confirms the action."""

        self.voice_state.songs.clear()
        await self.voice_state.update_queue_message()
        await interaction.response.edit_message(
            content=QUEUE_CLEARED_MESSAGE,
            view=None,
        )

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        """Dismiss the confirmation dialog without clearing the queue."""

        await interaction.response.edit_message(
            content=QUEUE_CLEAR_CANCELLED_MESSAGE,
            view=None,
        )

    async def on_timeout(self) -> None:
        """Disable confirmation buttons when the view expires."""

        for child in self.children:
            child.disabled = True
        if self.message is not None:
            await self.message.edit(view=self)
