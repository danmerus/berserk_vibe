"""Settings state handler."""

import pygame
from typing import Optional, TYPE_CHECKING

from .base import StateHandler

if TYPE_CHECKING:
    from ..app_context import AppContext
    from ..constants import AppState


class SettingsHandler(StateHandler):
    """Handler for the settings screen.

    Handles:
    - Nickname input
    - Resolution selection
    - Back button
    """

    def __init__(self, ctx: 'AppContext'):
        super().__init__(ctx)

    def handle_event(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle settings events."""
        from ..constants import AppState

        if event.type == pygame.KEYDOWN:
            return self._handle_keydown(event)

        elif event.type == pygame.TEXTINPUT:
            return self._handle_textinput(event)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_click(mx, my, event)

        return None

    def _handle_keydown(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle key press in settings."""
        from ..constants import AppState
        from ..settings import set_nickname

        renderer = self.ctx.renderer

        if event.key == pygame.K_ESCAPE:
            # Save nickname and go back to menu
            if renderer.settings_nickname_input.active:
                renderer.settings_nickname_input.deactivate()
            set_nickname(renderer.settings_nickname_input.value)
            return AppState.MENU

        elif renderer.settings_nickname_input.active:
            renderer.settings_nickname_input.handle_event(event)

        return None

    def _handle_textinput(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle text input in settings."""
        renderer = self.ctx.renderer
        if renderer.settings_nickname_input.active:
            renderer.settings_nickname_input.handle_event(event)
        return None

    def _handle_click(self, mx: int, my: int, event: pygame.event.Event) -> Optional['AppState']:
        """Handle mouse click in settings."""
        from ..constants import AppState
        from ..settings import set_nickname, set_resolution, get_sound_enabled, set_sound_enabled
        from ..renderer import Renderer

        renderer = self.ctx.renderer

        # Check if clicking on nickname input
        if (renderer.settings_nickname_rect and
            renderer.settings_nickname_rect.collidepoint(mx, my)):
            if not renderer.settings_nickname_input.active:
                renderer.settings_nickname_input.activate(renderer.settings_nickname_input.value)
            renderer.settings_nickname_input.handle_mouse_event(
                pygame.event.Event(event.type, pos=(mx, my), button=event.button),
                renderer.settings_nickname_rect, renderer.font_medium
            )
        else:
            # Clicked outside input - deactivate and save
            if renderer.settings_nickname_input.active:
                renderer.settings_nickname_input.deactivate()
                set_nickname(renderer.settings_nickname_input.value)

        # Check button clicks
        btn = renderer.get_clicked_settings_button(mx, my)
        if btn == 'back':
            # Save nickname when leaving settings
            if renderer.settings_nickname_input.active:
                renderer.settings_nickname_input.deactivate()
            set_nickname(renderer.settings_nickname_input.value)
            return AppState.MENU

        elif btn and btn.startswith('res_'):
            # Parse resolution from button id (res_WIDTH_HEIGHT)
            parts = btn.split('_')
            try:
                new_width = int(parts[1])
                new_height = int(parts[2])
            except (IndexError, ValueError):
                return None

            current_size = renderer.window.get_size()
            if (new_width, new_height) != current_size:
                # Update resolution
                self.ctx.current_resolution = (new_width, new_height)
                self.ctx.screen = pygame.display.set_mode(
                    self.ctx.current_resolution,
                    pygame.RESIZABLE
                )
                # Use handle_resize to update existing renderer (preserves state)
                self.ctx.renderer.handle_resize(self.ctx.screen)
                self.ctx.fullscreen = False
                set_resolution(new_width, new_height)

        elif btn == 'toggle_sound':
            # Toggle sound on/off
            set_sound_enabled(not get_sound_enabled())

        return None

    def update(self, dt: float) -> Optional['AppState']:
        """Update settings state."""
        return None

    def render(self) -> None:
        """Render the settings screen."""
        current_res = (
            self.ctx.renderer.window.get_width(),
            self.ctx.renderer.window.get_height()
        )
        self.ctx.renderer.draw_settings(current_res)
