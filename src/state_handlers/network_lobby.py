"""Network lobby state handler."""

import pygame
from typing import Optional, TYPE_CHECKING

from .base import StateHandler

if TYPE_CHECKING:
    from ..app_context import AppContext
    from ..constants import AppState


class NetworkLobbyHandler(StateHandler):
    """Handler for network lobby state.

    Handles:
    - Server/client connection
    - Match creation/joining
    - Ready status
    - Transition to deck selection when both ready
    """

    def __init__(self, ctx: 'AppContext'):
        super().__init__(ctx)
        self._callbacks_set = False

    def on_enter(self) -> None:
        """Called when entering network lobby."""
        from ..network_ui import NetworkUI
        from ..deck_builder import DeckBuilder
        from ..deck_builder_renderer import DeckBuilderRenderer
        from ..app_context import create_network_prep_state
        from ..game import Game
        from ..ui_state import GameClient
        from ..chat import ChatUI
        from ..constants import UILayout

        # Create NetworkUI if not exists
        if not self.ctx.network_ui:
            self.ctx.network_ui = NetworkUI(
                screen=self.ctx.renderer.screen,
                font_large=self.ctx.renderer.font_large,
                font_medium=self.ctx.renderer.font_medium,
                font_small=self.ctx.renderer.font_small,
            )

        # Set up callbacks
        self._setup_callbacks()

    def _setup_callbacks(self):
        """Set up network callbacks."""
        from ..constants import AppState
        from ..deck_builder import DeckBuilder
        from ..deck_builder_renderer import DeckBuilderRenderer
        from ..app_context import create_network_prep_state
        from ..game import Game
        from ..ui_state import GameClient
        from ..chat import ChatUI
        from ..constants import UILayout
        from .helpers import process_game_events

        ctx = self.ctx

        def on_both_ready():
            """Called when both players are ready."""
            ctx.network_prep_state = create_network_prep_state()
            ctx.deck_builder = DeckBuilder()
            s, ci, _, f = ctx.renderer.get_deck_builder_resources()
            ctx.deck_builder_renderer = DeckBuilderRenderer(s, ci, f)
            ctx.deck_builder_renderer.selection_mode = True
            ctx.deck_builder_renderer.custom_header = "Выбор колоды - Сетевая игра"
            # State transition will be handled by checking network_prep_state

        def on_game_start(player: int, snapshot: dict):
            """Called when game actually starts."""
            ctx.network_player = player
            ctx.network_game = Game.from_dict(snapshot)
            ctx.network_game_client = GameClient(ctx.network_game, player)
            ctx.network_client = ctx.network_ui.client
            ctx.network_prep_state = None

            # Create chat UI
            ctx.network_chat = ChatUI()
            ctx.network_chat.x = UILayout.CHAT_X
            ctx.network_chat.y = UILayout.CHAT_Y
            ctx.network_chat.width = UILayout.CHAT_WIDTH
            ctx.network_chat.height = UILayout.CHAT_HEIGHT
            ctx.network_chat.input_height = UILayout.CHAT_INPUT_HEIGHT
            ctx.network_chat.set_fonts(ctx.renderer.font_medium, ctx.renderer.font_small)
            ctx.network_chat.my_player_number = ctx.network_player
            ctx.network_chat.on_send = lambda text: ctx.network_client.send_chat(text) if ctx.network_client else None

            # Set up callbacks
            if ctx.network_client:
                ctx.network_client.on_chat = lambda name, text, pnum: ctx.network_chat.add_message(name, text, pnum)

                def on_draw_offered(pnum):
                    ctx.draw_offered_by_opponent = True
                    ctx.draw_button_flash_timer = 120
                ctx.network_client.on_draw_offered = on_draw_offered

                def on_resync_requested():
                    pass  # Silent resync
                ctx.network_client.on_resync_requested = on_resync_requested

                def on_resync_received(snapshot):
                    if ctx.network_ui.client and ctx.network_ui.client.game:
                        ctx.network_game = ctx.network_ui.client.game
                        if ctx.network_game_client:
                            ctx.network_game_client.game = ctx.network_game
                            ctx.network_game_client.refresh_selection()
                ctx.network_client.on_resync = on_resync_received

                def on_player_left(player_num, player_name, reason):
                    if ctx.network_chat:
                        if reason == "left":
                            ctx.network_chat.add_system_message(f"{player_name} покинул игру")
                        elif reason == "timeout":
                            ctx.network_chat.add_system_message(f"{player_name} отключился (таймаут)")
                        else:
                            ctx.network_chat.add_system_message(f"{player_name} отключился")
                ctx.network_client.on_player_left = on_player_left

            # Reset draw state
            ctx.draw_offered_by_us = False
            ctx.draw_offered_by_opponent = False
            ctx.draw_button_flash_timer = 0

        def on_network_update(result):
            """Called when game update received."""
            if ctx.network_ui.client and ctx.network_ui.client.game:
                ctx.network_game = ctx.network_ui.client.game
                if ctx.network_game_client:
                    ctx.network_game_client.game = ctx.network_game
                    ctx.network_game_client.refresh_selection()
            if result.events and ctx.network_game:
                process_game_events(ctx.network_game, ctx.renderer, result.events)

        def on_client_connected():
            """Called when client connects."""
            if ctx.network_ui.client:
                ctx.network_ui.client.on_update = on_network_update

        ctx.network_ui.on_connected = on_client_connected
        ctx.network_ui.on_both_ready = on_both_ready
        ctx.network_ui.on_game_start = on_game_start

        self._callbacks_set = True

    def handle_event(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle network lobby events."""
        from ..constants import AppState

        if not self.ctx.network_ui:
            return None

        if event.type == pygame.KEYDOWN:
            return self._handle_keydown(event)

        elif event.type == pygame.TEXTINPUT:
            self.ctx.network_ui.handle_text_input(event)
            return None

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_click(mx, my, event)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            mouse_event = pygame.event.Event(event.type, pos=(mx, my), button=event.button)
            self.ctx.network_ui.handle_mouse_event(mouse_event)
            return None

        elif event.type == pygame.MOUSEMOTION:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            mouse_event = pygame.event.Event(event.type, pos=(mx, my), rel=event.rel, buttons=event.buttons)
            self.ctx.network_ui.handle_mouse_event(mouse_event)
            return None

        return None

    def _handle_keydown(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle key press in network lobby."""
        from ..constants import AppState

        if event.key == pygame.K_ESCAPE:
            self.ctx.network_ui = None
            return AppState.MENU

        # Pass key events (backspace, arrows, etc.) to text input handler
        self.ctx.network_ui.handle_text_input(event)
        return None

    def _handle_click(self, mx: int, my: int, event: pygame.event.Event) -> Optional['AppState']:
        """Handle click in network lobby."""
        from ..constants import AppState

        action = self.ctx.network_ui.handle_click(mx, my)
        if action:
            result = self.ctx.network_ui.process_action(action)
            if result == 'back':
                self.ctx.network_ui = None
                return AppState.MENU

        # Handle mouse for text input
        mouse_event = pygame.event.Event(event.type, pos=(mx, my), button=event.button)
        self.ctx.network_ui.handle_mouse_event(mouse_event)

        return None

    def update(self, dt: float) -> Optional['AppState']:
        """Update network lobby state."""
        from ..constants import AppState

        if self.ctx.network_ui:
            self.ctx.network_ui.update()

        # Check if we should transition to deck select (both ready)
        if self.ctx.network_prep_state is not None:
            return AppState.DECK_SELECT

        # Check if game started
        if self.ctx.network_game is not None:
            return AppState.NETWORK_GAME

        return None

    def render(self) -> None:
        """Render the network lobby."""
        if self.ctx.network_ui:
            self.ctx.network_ui.draw()
            self.ctx.renderer.finalize_frame()

    def on_exit(self) -> None:
        """Called when leaving network lobby."""
        pass
