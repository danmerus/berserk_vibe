"""Pytest fixtures for Berserk game testing."""
import pytest
from typing import Optional, List

from src.game import Game
from src.card import Card
from src.board import Board
from src.card_database import CARD_DATABASE
from src.constants import GamePhase


@pytest.fixture
def game() -> Game:
    """Create a fresh game in MAIN phase ready for testing.

    The game has an empty board and is set to Player 1's turn.
    Use place_card fixture to add cards.
    """
    g = Game()
    g.phase = GamePhase.MAIN
    g.current_player = 1
    g.turn_number = 1
    return g


@pytest.fixture
def place_card(game: Game):
    """Factory fixture to place cards on the board.

    Usage:
        attacker = place_card("Циклоп", player=1, pos=10)
        defender = place_card("Гном-басаарг", player=2, pos=15, tapped=True)
    """
    def _place(
        card_name: str,
        player: int,
        pos: int,
        tapped: bool = False,
        damage: int = 0,
        curr_move: Optional[int] = None,
    ) -> Card:
        if card_name not in CARD_DATABASE:
            raise ValueError(f"Unknown card: {card_name}")

        card = Card(def_id=card_name, player=player)
        card.id = game._next_card_id
        game._next_card_id += 1
        card.curr_life = card.stats.life - damage
        card.curr_move = curr_move if curr_move is not None else card.stats.move
        card.tapped = tapped
        card.position = pos

        # Place on board
        if pos >= Board.FLYING_P1_START:
            # Flying zone
            if pos < Board.FLYING_P2_START:
                slot = pos - Board.FLYING_P1_START
                game.board.flying_p1[slot] = card
            else:
                slot = pos - Board.FLYING_P2_START
                game.board.flying_p2[slot] = card
        else:
            game.board.cells[pos] = card

        return card

    return _place


@pytest.fixture
def set_rolls(game: Game):
    """Factory fixture to set deterministic dice rolls.

    Usage:
        set_rolls(6, 1)  # Attacker rolls 6, defender rolls 1
        set_rolls(3, 3, 5, 2)  # Multiple rolls for complex scenarios
    """
    def _set(*rolls: int):
        game.inject_rolls(list(rolls))
    return _set


@pytest.fixture
def attack(game: Game, set_rolls):
    """Helper fixture to perform an attack with specific dice rolls.

    Usage:
        result = attack(attacker, defender.position, atk_roll=6, def_roll=1)
    """
    def _attack(
        attacker: Card,
        target_pos: int,
        atk_roll: int = 4,
        def_roll: int = 3,
    ) -> bool:
        set_rolls(atk_roll, def_roll)
        return game.perform_attack(attacker, target_pos)

    return _attack


@pytest.fixture
def start_turn(game: Game):
    """Helper fixture to start a turn for a specific player.

    Usage:
        start_turn(1)  # Start Player 1's turn
        start_turn(2)  # Start Player 2's turn
    """
    def _start(player: int):
        game.current_player = player
        game.start_turn()
    return _start


# =============================================================================
# COMMON CARD FIXTURES
# =============================================================================

@pytest.fixture
def cyclops(place_card) -> Card:
    """Place a Циклоп for Player 1 at position 10."""
    return place_card("Циклоп", player=1, pos=10)


@pytest.fixture
def dwarf(place_card) -> Card:
    """Place a Гном-басаарг for Player 2 at position 15."""
    return place_card("Гном-басаарг", player=2, pos=15)


@pytest.fixture
def druid(place_card) -> Card:
    """Place a Друид (healer) for Player 1 at position 11."""
    return place_card("Друид", player=1, pos=11)


@pytest.fixture
def lovets(place_card) -> Card:
    """Place a Ловец удачи (luck ability) for Player 1 at position 12."""
    return place_card("Ловец удачи", player=1, pos=12)


@pytest.fixture
def korpit(place_card) -> Card:
    """Place a Корпит (flying, scavenging) for Player 1 in flying zone."""
    return place_card("Корпит", player=1, pos=30)  # Flying P1 slot 0


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_damage_for_tier(card: Card, tier: int) -> int:
    """Get damage value for a tier (0=weak, 1=medium, 2=strong)."""
    return card.stats.attack[tier]


def assert_card_alive(card: Card, msg: str = ""):
    """Assert that a card is alive."""
    assert card.is_alive, f"Card {card.name} should be alive. {msg}"


def assert_card_dead(card: Card, msg: str = ""):
    """Assert that a card is dead."""
    assert not card.is_alive, f"Card {card.name} should be dead. {msg}"


def assert_hp(card: Card, expected: int, msg: str = ""):
    """Assert card has specific HP."""
    assert card.curr_life == expected, \
        f"Card {card.name} HP: expected {expected}, got {card.curr_life}. {msg}"


def assert_tapped(card: Card, msg: str = ""):
    """Assert that a card is tapped."""
    assert card.tapped, f"Card {card.name} should be tapped. {msg}"


def assert_untapped(card: Card, msg: str = ""):
    """Assert that a card is untapped."""
    assert not card.tapped, f"Card {card.name} should be untapped. {msg}"


def resolve_combat(game: 'Game'):
    """Resolve any pending combat interactions (priority, exchange)."""
    # Pass priority if in priority phase
    while game.priority_phase:
        game.pass_priority()

    # Accept exchange if waiting for exchange choice (take full damage)
    if game.awaiting_exchange_choice:
        game.resolve_exchange_choice(reduce_damage=False)
        # Might re-enter priority, so pass again
        while game.priority_phase:
            game.pass_priority()
