"""Menu state handler."""

import pygame
from typing import Optional, TYPE_CHECKING

from .base import StateHandler

if TYPE_CHECKING:
    from ..app_context import AppContext
    from ..constants import AppState


class MenuHandler(StateHandler):
    """Handler for the main menu state.

    Handles:
    - Menu button clicks (test game, local game, network, settings, exit)
    - State transitions to other screens
    """

    def __init__(self, ctx: 'AppContext'):
        super().__init__(ctx)
        self._should_exit = False

    def handle_event(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle menu events."""
        from ..constants import AppState

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_click(mx, my)

        return None

    def _handle_click(self, mx: int, my: int) -> Optional['AppState']:
        """Handle mouse click on menu."""
        from ..constants import AppState
        from ..match import MatchServer, LocalMatchClient
        from ..deck_builder import DeckBuilder
        from ..deck_builder_renderer import DeckBuilderRenderer
        from ..app_context import create_local_game_state

        btn = self.ctx.renderer.get_clicked_menu_button(mx, my)
        if not btn:
            return None

        if btn == 'test_game':
            return self._start_test_game()

        elif btn == 'local_game':
            return self._start_local_game_flow()

        elif btn == 'deck_builder':
            return self._open_deck_builder()

        elif btn == 'network_game':
            return AppState.NETWORK_LOBBY

        elif btn == 'settings':
            return AppState.SETTINGS

        elif btn == 'exit':
            self._should_exit = True

        return None

    def _start_test_game(self) -> 'AppState':
        """Start a test game with auto-placement."""
        from ..constants import AppState
        from ..match import MatchServer, LocalMatchClient

        server = MatchServer()
        server.setup_game()
        server.game.auto_place_for_testing()

        client_p1 = LocalMatchClient(server, player=1)
        client_p2 = LocalMatchClient(server, player=2)

        self.ctx.server = server
        self.ctx.client_p1 = client_p1
        self.ctx.client_p2 = client_p2
        self.ctx.game = server.game
        self.ctx.match_client = client_p1  # P1 starts
        self.ctx.client = client_p1.game_client
        self.ctx.is_test_game = False  # Don't show test mode indicator

        return AppState.GAME

    def _start_local_game_flow(self) -> 'AppState':
        """Start local game flow (deck selection -> squad -> placement)."""
        from ..constants import AppState
        from ..deck_builder import DeckBuilder
        from ..deck_builder_renderer import DeckBuilderRenderer
        from ..app_context import create_local_game_state

        self.ctx.local_game_state = create_local_game_state()

        # Set up deck builder for player 1 selection
        self.ctx.deck_builder = DeckBuilder()
        s, ci, _, f = self.ctx.renderer.get_deck_builder_resources()
        self.ctx.deck_builder_renderer = DeckBuilderRenderer(s, ci, f)
        self.ctx.deck_builder_renderer.selection_mode = True
        self.ctx.deck_builder_renderer.custom_header = "Выбор колоды - Игрок 1"

        return AppState.DECK_SELECT

    def _open_deck_builder(self) -> 'AppState':
        """Open the deck builder screen."""
        from ..constants import AppState
        from ..deck_builder import DeckBuilder
        from ..deck_builder_renderer import DeckBuilderRenderer

        self.ctx.deck_builder = DeckBuilder()
        s, ci, _, f = self.ctx.renderer.get_deck_builder_resources()
        self.ctx.deck_builder_renderer = DeckBuilderRenderer(s, ci, f)

        return AppState.DECK_BUILDER

    def update(self, dt: float) -> Optional['AppState']:
        """Update menu state."""
        return None

    def render(self) -> None:
        """Render the menu."""
        self.ctx.renderer.draw_menu()

    @property
    def should_exit(self) -> bool:
        """Check if exit was requested."""
        return self._should_exit
