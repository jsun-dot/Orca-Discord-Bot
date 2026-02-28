import discord
from discord.ext import commands
from datetime import datetime
from typing import Optional


async def _check_view_access(ctx: commands.Context, interaction: discord.Interaction) -> bool:
    voice_state = getattr(ctx, "voice_state", None)
    if voice_state:
        voice_state.last_activity = datetime.utcnow()

    if interaction.user == ctx.author:
        return True

    if not interaction.response.is_done():
        await interaction.response.send_message(
            "Only the command author can use these controls.",
            ephemeral=True,
        )
    return False


class QueuePages(discord.ui.View):
    def __init__(self, ctx: commands.Context, pages: list, current_page: int = 0):
        super().__init__(timeout=1800)  # 30 minutes
        self.ctx = ctx
        self.pages = pages
        self.current_page = current_page
        self.message = None  # To store the message object

        self.previous_button = discord.ui.Button(label='Previous', style=discord.ButtonStyle.primary, custom_id='previous')
        self.next_button = discord.ui.Button(label='Next', style=discord.ButtonStyle.primary, custom_id='next')
        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page

        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_view_access(self.ctx, interaction)

    def update_buttons(self):
        self.previous_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= len(self.pages) - 1

    async def previous_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            self.message = interaction.message
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            self.message = interaction.message
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    async def on_timeout(self):
        # Disable all buttons when timeout occurs
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)


class NowPlayingButtons(discord.ui.View):
    def __init__(self, ctx: Optional[commands.Context] = None):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.message = None  # To store the message object

        buttons = [
            ("Pause", self.pause_callback, "⏸️", "now-playing:pause"),
            ("Resume", self.resume_callback, "▶️", "now-playing:resume"),
            ("Shuffle", self.shuffle_callback, "🔀", "now-playing:shuffle"),
            ("Queue", self.queue_callback, "📜", "now-playing:queue"),
            ("Skip", self.skip_callback, "⏭️", "now-playing:skip"),
            ("Clear", self.clear_callback, "🧹", "now-playing:clear"),
            ("Volume Up", self.volume_up_callback, "🔊", "now-playing:volume-up"),
            ("Volume Down", self.volume_down_callback, "🔉", "now-playing:volume-down"),
        ]

        for label, callback, emoji, custom_id in buttons:
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
                emoji=emoji,
                custom_id=custom_id,
            )
            button.callback = callback
            self.add_item(button)

    def _get_voice_state(self, interaction: discord.Interaction):
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

    def _get_active_voice_state(self, interaction: discord.Interaction):
        voice_state = self._get_voice_state(interaction)
        if voice_state is None:
            return None

        active_message = getattr(voice_state, "now_playing_message", None)
        if active_message is None:
            return None

        if interaction.message is None or active_message.id != interaction.message.id:
            return None

        return voice_state

    async def _send_inactive_message(self, interaction: discord.Interaction):
        message = "These controls are no longer active. Start playback again."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        voice_state = self._get_active_voice_state(interaction)
        if voice_state is None:
            await self._send_inactive_message(interaction)
            return False

        if self.ctx is None:
            voice_state.last_activity = datetime.utcnow()
            return True

        return await _check_view_access(self.ctx, interaction)

    async def _defer(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()

    async def pause_callback(self, interaction: discord.Interaction):
        voice_state = self._get_active_voice_state(interaction)
        if voice_state is None:
            await self._send_inactive_message(interaction)
            return

        player = interaction.guild.voice_client if interaction.guild else None
        await self._defer(interaction)
        if player and player.is_playing():
            player.pause()
            voice_state.action_message = f"**{interaction.user.display_name} paused the player.**"
            await voice_state.update_now_playing_embed()

    async def resume_callback(self, interaction: discord.Interaction):
        voice_state = self._get_active_voice_state(interaction)
        if voice_state is None:
            await self._send_inactive_message(interaction)
            return

        player = interaction.guild.voice_client if interaction.guild else None
        await self._defer(interaction)
        if player and player.is_paused():
            player.resume()
            voice_state.action_message = f"**{interaction.user.display_name} resumed the player.**"
            await voice_state.update_now_playing_embed()

    async def shuffle_callback(self, interaction: discord.Interaction):
        voice_state = self._get_active_voice_state(interaction)
        if voice_state is None:
            await self._send_inactive_message(interaction)
            return

        await self._defer(interaction)
        if voice_state.is_playing:
            voice_state.songs.shuffle()
            await voice_state.update_queue_message()
            voice_state.action_message = f"**{interaction.user.display_name} shuffled the queue.**"
            await voice_state.update_now_playing_embed()

    async def queue_callback(self, interaction: discord.Interaction):
        voice_state = self._get_active_voice_state(interaction)
        if voice_state is None:
            await self._send_inactive_message(interaction)
            return

        await self._defer(interaction)
        await voice_state.show_queue(page=1)

    async def skip_callback(self, interaction: discord.Interaction):
        voice_state = self._get_active_voice_state(interaction)
        if voice_state is None:
            await self._send_inactive_message(interaction)
            return

        await self._defer(interaction)
        if voice_state.is_playing:
            voice_state.action_message = f"**{interaction.user.display_name} skipped the song.**"
            await voice_state.update_now_playing_embed()
            voice_state.skip()

    async def clear_callback(self, interaction: discord.Interaction):
        voice_state = self._get_active_voice_state(interaction)
        if voice_state is None:
            await self._send_inactive_message(interaction)
            return

        ctx = self.ctx or await commands.Context.from_interaction(interaction)
        if voice_state.is_playing:
            view = ClearQueueConfirmation(ctx, voice_state)
            # Send via the *current* interaction to avoid expired webhook tokens.
            if interaction.response.is_done():
                view.message = await interaction.followup.send(
                    "Are you sure you want to clear the queue?",
                    view=view,
                    wait=True,
                )
            else:
                await interaction.response.send_message("Are you sure you want to clear the queue?", view=view)
                view.message = await interaction.original_response()
            return
        # Nothing to do; just acknowledge
        if not interaction.response.is_done():
            await interaction.response.defer()

    async def volume_up_callback(self, interaction: discord.Interaction):
        voice_state = self._get_active_voice_state(interaction)
        if voice_state is None:
            await self._send_inactive_message(interaction)
            return

        await self._defer(interaction)
        await voice_state.change_volume(10, interaction)  # Increase volume by 10%

    async def volume_down_callback(self, interaction: discord.Interaction):
        voice_state = self._get_active_voice_state(interaction)
        if voice_state is None:
            await self._send_inactive_message(interaction)
            return

        await self._defer(interaction)
        await voice_state.change_volume(-10, interaction)  # Decrease volume by 10%


class ClearQueueConfirmation(discord.ui.View):
    def __init__(self, ctx: commands.Context, voice_state):
        super().__init__(timeout=1800)  # 30 minutes
        self.ctx = ctx
        self.voice_state = voice_state
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_view_access(self.ctx, interaction)

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.voice_state.songs.clear()
        await self.voice_state.update_queue_message()
        await interaction.response.edit_message(content="The queue has been cleared.", view=None)

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled clearing the queue.", view=None)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)
