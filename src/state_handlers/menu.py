"""Menu state handler."""

import random
import time
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

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and self.ctx.show_ai_setup:
                self.ctx.show_ai_setup = False
                return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)

            # Handle AI setup popup if open
            if self.ctx.show_ai_setup:
                return self._handle_ai_setup_click(mx, my)

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

        elif btn == 'vs_ai':
            # Show AI setup popup instead of directly starting
            self.ctx.show_ai_setup = True
            return None

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

    def _handle_ai_setup_click(self, mx: int, my: int) -> Optional['AppState']:
        """Handle clicks in AI setup popup."""
        from ..constants import AppState

        btn = self.ctx.renderer.get_clicked_ai_setup_button(mx, my)
        if not btn:
            return None

        state = self.ctx.ai_setup_state

        # Mode selection
        if btn == 'mode_vs_ai':
            state['mode'] = 'vs_ai'
        elif btn == 'mode_ai_vs_ai':
            state['mode'] = 'ai_vs_ai'

        # AI type selection
        elif btn == 'ai_p1_random':
            state['ai_type_p1'] = 'random'
        elif btn == 'ai_p1_rulebased':
            state['ai_type_p1'] = 'rulebased'
        elif btn == 'ai_p2_random':
            state['ai_type_p2'] = 'random'
        elif btn == 'ai_p2_rulebased':
            state['ai_type_p2'] = 'rulebased'

        # Delay presets
        elif btn.startswith('delay_'):
            try:
                delay_val = float(btn.split('_')[1])
                state['ai_delay'] = delay_val
            except (ValueError, IndexError):
                pass

        # Delay slider
        elif btn == 'delay_slider':
            # Find the slider rect and calculate delay
            for btn_id, rect in self.ctx.renderer.ai_setup_buttons:
                if btn_id == 'delay_slider':
                    delay = self.ctx.renderer.get_ai_delay_from_slider(mx, my, rect)
                    if delay is not None:
                        state['ai_delay'] = delay
                    break

        # Cancel
        elif btn == 'cancel':
            self.ctx.show_ai_setup = False

        # Start game
        elif btn == 'start':
            self.ctx.show_ai_setup = False
            return self._start_ai_game_with_settings()

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
        # Clear AI names for hotseat mode
        self.ctx.renderer.ai_name_p1 = None
        self.ctx.renderer.ai_name_p2 = None

        return AppState.GAME

    def _start_ai_game_with_settings(self) -> 'AppState':
        """Start a game with AI based on setup settings."""
        from ..constants import AppState
        from ..match import MatchServer, LocalMatchClient
        from ..ai import RandomAI, RuleBasedAI, build_ai_squad
        from ..card_database import create_starter_deck, create_starter_deck_p2
        from ..game import Game
        from ..deck_builder import DeckBuilder
        from ..deck_builder_renderer import DeckBuilderRenderer
        from ..app_context import create_local_game_state

        state = self.ctx.ai_setup_state
        mode = state.get('mode', 'vs_ai')
        ai_delay = state.get('ai_delay', 0.5)
        ai_type_p1 = state.get('ai_type_p1', 'rulebased')
        ai_type_p2 = state.get('ai_type_p2', 'rulebased')

        if mode == 'vs_ai':
            # Human vs AI - human goes through deck/squad/placement flow
            self.ctx.local_game_state = create_local_game_state()
            self.ctx.local_game_state['vs_ai'] = True
            self.ctx.local_game_state['ai_type'] = ai_type_p2
            self.ctx.local_game_state['ai_delay'] = ai_delay

            # Set up deck builder for player 1 selection
            self.ctx.deck_builder = DeckBuilder()
            s, ci, _, f = self.ctx.renderer.get_deck_builder_resources()
            self.ctx.deck_builder_renderer = DeckBuilderRenderer(s, ci, f)
            self.ctx.deck_builder_renderer.selection_mode = True
            self.ctx.deck_builder_renderer.custom_header = "Выбор колоды - Игрок 1"

            return AppState.DECK_SELECT

        # AI vs AI - both players use automated squad building
        # Seed random for variety in each game
        random.seed(time.time_ns())

        deck_p1 = create_starter_deck()
        deck_p2 = create_starter_deck_p2()

        squad_names_p1, placement_p1 = build_ai_squad(player=1, deck_cards=deck_p1)
        squad_names_p2, placement_p2 = build_ai_squad(player=2, deck_cards=deck_p2)

        server = MatchServer()
        game = Game()
        server.game = game

        p1_cards = list(placement_p1.values())
        p2_cards = list(placement_p2.values())
        game.setup_game_with_placement(p1_cards, p2_cards)

        client_p1 = LocalMatchClient(server, player=1)
        client_p2 = LocalMatchClient(server, player=2)

        self.ctx.server = server
        self.ctx.client_p1 = client_p1
        self.ctx.client_p2 = client_p2
        self.ctx.game = server.game
        self.ctx.ai_delay = ai_delay
        self.ctx.is_test_game = False

        def create_ai(ai_type: str, player: int):
            if ai_type == 'random':
                return RandomAI(server, player)
            else:
                return RuleBasedAI(server, player)

        ai1 = create_ai(ai_type_p1, player=1)
        ai2 = create_ai(ai_type_p2, player=2)
        self.ctx.ai_player = ai1
        self.ctx.ai_player_2 = ai2
        self.ctx.human_player = 0
        self.ctx.is_ai_vs_ai = True
        self.ctx.match_client = client_p1
        self.ctx.client = client_p1.game_client
        self.ctx.renderer.ai_name_p1 = ai1.name
        self.ctx.renderer.ai_name_p2 = ai2.name

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
        if self.ctx.show_ai_setup:
            self.ctx.renderer.draw_ai_setup_popup(self.ctx.ai_setup_state)
        else:
            self.ctx.renderer.draw_menu()

    @property
    def should_exit(self) -> bool:
        """Check if exit was requested."""
        return self._should_exit
