"""Application context - holds all shared application state.

This module provides a centralized container for all state that needs to be
shared between different parts of the application, particularly state handlers.
"""

import pygame
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .renderer import Renderer
    from .game import Game
    from .ui_state import GameClient
    from .match import MatchServer, LocalMatchClient
    from .deck_builder import DeckBuilder
    from .deck_builder_renderer import DeckBuilderRenderer
    from .network_ui import NetworkUI
    from .network.client import NetworkClient
    from .chat import ChatUI
    from .ai import AIPlayer


def create_local_game_state() -> Dict[str, Any]:
    """Create initial local game state dictionary."""
    return {
        'current_player': 1,          # Which player we're building for (1 or 2)
        'deck_p1': None,              # P1's selected deck
        'deck_p2': None,              # P2's selected deck
        'squad_builder': None,        # Current squad builder instance
        'squad_renderer': None,       # Current squad renderer instance
        'squad_p1': None,             # P1's finalized squad (card names)
        'squad_p2': None,             # P2's finalized squad (card names)
        'placement_state': None,      # Current placement state
        'placement_renderer': None,   # Current placement renderer
        'placed_cards_p1': None,      # P1's placed cards with positions
        'placed_cards_p2': None,      # P2's placed cards with positions
    }


def create_network_prep_state() -> Dict[str, Any]:
    """Create initial network prep state dictionary."""
    return {
        'deck': None,                 # Selected deck cards (list of card names)
        'squad': None,                # Built squad (card names)
        'placed_cards': None,         # Placed cards with positions
        'squad_builder': None,        # Squad builder instance
        'squad_renderer': None,       # Squad renderer instance
        'placement_state': None,      # Placement state instance
        'placement_renderer': None,   # Placement renderer instance
        'waiting_for_opponent': False,# Flag for post-placement waiting
    }


@dataclass
class AppContext:
    """Holds all shared application state.

    This is passed to state handlers so they can access and modify
    the application state without needing global variables.
    """

    # Core pygame objects
    screen: pygame.Surface
    clock: pygame.time.Clock
    renderer: 'Renderer'

    # Window state
    fullscreen: bool = False
    current_resolution: Tuple[int, int] = (1280, 720)

    # Local game flow state
    local_game_state: Dict[str, Any] = field(default_factory=create_local_game_state)

    # Deck builder
    deck_builder: Optional['DeckBuilder'] = None
    deck_builder_renderer: Optional['DeckBuilderRenderer'] = None

    # Local match state
    server: Optional['MatchServer'] = None
    client_p1: Optional['LocalMatchClient'] = None
    client_p2: Optional['LocalMatchClient'] = None
    match_client: Optional['LocalMatchClient'] = None  # Currently active client
    game: Optional['Game'] = None
    client: Optional['GameClient'] = None  # Currently active GameClient

    # Test game flags
    is_test_game: bool = False
    test_game_controlled_player: int = 1

    # AI opponent
    ai_player: Optional['AIPlayer'] = None
    ai_player_2: Optional['AIPlayer'] = None  # Second AI for AI vs AI mode
    human_player: int = 1  # Which player number is human (1 or 2)
    ai_delay: float = 0.5  # Delay between AI actions in seconds
    is_ai_vs_ai: bool = False  # True if watching AI vs AI

    # AI setup popup state
    show_ai_setup: bool = False
    ai_setup_state: Dict[str, Any] = field(default_factory=lambda: {
        'mode': 'vs_ai',  # 'vs_ai' or 'ai_vs_ai'
        'ai_delay': 0.5,
        'ai_type_p1': 'rulebased',
        'ai_type_p2': 'rulebased',
    })

    # Network prep state
    network_prep_state: Optional[Dict[str, Any]] = None

    # Network game state
    network_ui: Optional['NetworkUI'] = None
    network_client: Optional['NetworkClient'] = None
    network_game: Optional['Game'] = None
    network_game_client: Optional['GameClient'] = None
    network_player: int = 0
    network_chat: Optional['ChatUI'] = None

    # UI flags
    show_pause_menu: bool = False

    # Draw offer state (network game)
    draw_offered_by_us: bool = False
    draw_offered_by_opponent: bool = False
    draw_button_flash_timer: int = 0

    def reset_local_game(self):
        """Reset local game state for a new game."""
        self.local_game_state = create_local_game_state()
        self.server = None
        self.client_p1 = None
        self.client_p2 = None
        self.match_client = None
        self.game = None
        self.client = None
        self.is_test_game = False
        self.test_game_controlled_player = 1
        self.ai_player = None
        self.ai_player_2 = None
        self.human_player = 1
        self.is_ai_vs_ai = False
        self.show_pause_menu = False
        self.show_ai_setup = False
        # Clear renderer state
        if self.renderer:
            self.renderer.clear_dice_display()

    def reset_network_game(self):
        """Reset network game state."""
        self.network_prep_state = None
        self.network_game = None
        self.network_game_client = None
        self.network_player = 0
        self.network_chat = None
        self.draw_offered_by_us = False
        self.draw_offered_by_opponent = False
        self.draw_button_flash_timer = 0
        self.show_pause_menu = False
        # Clear renderer state
        if self.renderer:
            self.renderer.clear_dice_display()

    def reset_deck_builder(self):
        """Reset deck builder state."""
        self.deck_builder = None
        self.deck_builder_renderer = None

    def get_active_game(self) -> Optional['Game']:
        """Get the currently active game (local or network)."""
        return self.network_game if self.network_game else self.game

    def get_active_client(self) -> Optional['GameClient']:
        """Get the currently active GameClient (local or network)."""
        return self.network_game_client if self.network_game_client else self.client
