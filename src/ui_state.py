"""UI State management for client-side rendering.

UIState holds all client-specific state that doesn't need to be synchronized
with the server. In a networked game:
- Server maintains Game state (authoritative)
- Client maintains UIState locally for responsive UI

This separation allows:
- Clean client/server split
- Optimistic UI updates
- Reduced network traffic (UI state changes don't need sync)
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .game import Game
    from .card import Card
    from .commands import Event


@dataclass
class UIState:
    """Client-side UI state (not synchronized with server).

    This state is:
    - Local to each client
    - Computed from server state where needed
    - Not included in game serialization
    """
    # Which player this client is viewing as (1 or 2)
    viewing_player: int = 1

    # Selection state
    selected_card_id: Optional[int] = None
    valid_moves: List[int] = field(default_factory=list)
    valid_attacks: List[int] = field(default_factory=list)
    attack_mode: bool = False

    # Visual effects (arrows, floating numbers)
    arrows: List[Dict[str, Any]] = field(default_factory=list)
    floating_texts: List[Dict[str, Any]] = field(default_factory=list)

    # Arrow persistence (minimum display time after action)
    arrow_min_time: float = 1.0
    arrow_clear_pending: bool = False
    arrow_clear_time: float = 0.0

    # Animation timers
    animation_timer: float = 0.0

    # Panel states (expanded/collapsed)
    flying_panel_p1_expanded: bool = False
    flying_panel_p2_expanded: bool = False

    # Scroll positions
    log_scroll: int = 0
    library_scroll: int = 0
    deck_scroll: int = 0

    def clear_selection(self):
        """Clear all selection state."""
        self.selected_card_id = None
        self.valid_moves = []
        self.valid_attacks = []
        self.attack_mode = False

    def select_card(self, card_id: int, moves: List[int] = None, attacks: List[int] = None):
        """Select a card and set valid actions."""
        self.selected_card_id = card_id
        self.valid_moves = moves or []
        self.valid_attacks = attacks or []
        self.attack_mode = False

    def toggle_attack_mode(self, attacks: List[int] = None) -> bool:
        """Toggle attack mode. Returns new state."""
        if self.attack_mode:
            self.attack_mode = False
            self.valid_attacks = []
        else:
            self.attack_mode = True
            self.valid_attacks = attacks or []
        return self.attack_mode

    def add_arrow(self, from_pos: int, to_pos: int, arrow_type: str = 'attack'):
        """Add an arrow to display."""
        self.arrows.append({
            'from_pos': from_pos,
            'to_pos': to_pos,
            'type': arrow_type,
            'time': 0.0
        })
        # Reset clear pending when adding new arrow
        self.arrow_clear_pending = False

    def clear_arrows(self, immediate: bool = False):
        """Clear arrows (with optional delay for visibility)."""
        if immediate:
            self.arrows.clear()
            self.arrow_clear_pending = False
        else:
            # Schedule clear after minimum display time
            self.arrow_clear_pending = True
            self.arrow_clear_time = 0.0

    def add_floating_text(self, pos: int, text: str, color: str = 'damage'):
        """Add floating text (damage/heal numbers)."""
        self.floating_texts.append({
            'pos': pos,
            'text': text,
            'color': color,
            'time': 0.0
        })

    def update(self, dt: float):
        """Update animations and timers."""
        self.animation_timer += dt

        # Update arrow timers
        for arrow in self.arrows:
            arrow['time'] += dt

        # Handle arrow clearing with minimum display time
        if self.arrow_clear_pending:
            self.arrow_clear_time += dt
            # Check if all arrows have been displayed long enough
            if self.arrows:
                min_arrow_time = min(a['time'] for a in self.arrows)
                if min_arrow_time >= self.arrow_min_time:
                    self.arrows.clear()
                    self.arrow_clear_pending = False
            else:
                self.arrow_clear_pending = False

        # Update floating text timers and remove old ones
        for text in self.floating_texts:
            text['time'] += dt
        self.floating_texts = [t for t in self.floating_texts if t['time'] < 1.5]


# =============================================================================
# PURE FUNCTIONS - Compute UI state from game state
# =============================================================================

def compute_valid_moves(game: 'Game', card_id: int) -> List[int]:
    """Compute valid move positions for a card.

    Pure function - doesn't modify any state.
    """
    card = game.get_card_by_id(card_id)
    if card is None or not card.can_act:
        return []
    return game.board.get_valid_moves(card)


def compute_attack_targets(game: 'Game', card_id: int) -> List[int]:
    """Compute valid attack target positions for a card.

    Pure function - doesn't modify any state.
    """
    card = game.get_card_by_id(card_id)
    if card is None:
        return []
    return game.get_attack_targets(card)


def compute_forced_attacks(game: 'Game', card_id: int) -> List[int]:
    """Check if card has forced attack targets (must_attack_tapped ability).

    Pure function - doesn't modify any state.
    """
    return game.forced_attackers.get(card_id, [])


def can_card_act(game: 'Game', card_id: int) -> bool:
    """Check if a card can perform actions.

    Pure function - doesn't modify any state.
    """
    card = game.get_card_by_id(card_id)
    if card is None:
        return False
    return card.can_act and card.player == game.current_player


def get_card_active_abilities(game: 'Game', card_id: int) -> List[str]:
    """Get list of active ability IDs the card can use.

    Pure function - doesn't modify any state.
    """
    from .abilities import get_ability, AbilityType

    card = game.get_card_by_id(card_id)
    if card is None or not card.can_act:
        return []

    result = []
    for ability_id in card.stats.ability_ids:
        ability = get_ability(ability_id)
        if ability and ability.ability_type == AbilityType.ACTIVE:
            if card.can_use_ability(ability_id):
                result.append(ability_id)
    return result


def get_card_instant_abilities(game: 'Game', card_id: int) -> List[str]:
    """Get list of instant ability IDs the card can use during priority.

    Pure function - doesn't modify any state.
    """
    from .abilities import get_ability

    card = game.get_card_by_id(card_id)
    if card is None:
        return []

    result = []
    for ability_id in card.stats.ability_ids:
        ability = get_ability(ability_id)
        if ability and ability.is_instant:
            if card.can_use_ability(ability_id):
                result.append(ability_id)
    return result


# =============================================================================
# EVENT HANDLERS - Build visuals from network events
# =============================================================================

def apply_event_to_ui(ui: UIState, event: 'Event', game: 'Game' = None):
    """Apply a game event to UI state (visuals, arrows, etc.).

    This is how clients build visuals from the event stream.

    Args:
        ui: UIState to update
        event: Event to process
        game: Optional Game for looking up card positions
    """
    from .commands import EventType

    if event.type == EventType.CARD_DAMAGED:
        # Look up card position from game state
        pos = event.position
        if pos is None and game and event.card_id:
            card = game.get_card_by_id(event.card_id)
            if card:
                pos = card.position
        if pos is not None and event.amount:
            ui.add_floating_text(pos, f"-{event.amount}", 'damage')

    elif event.type == EventType.CARD_HEALED:
        # Look up card position from game state
        pos = event.position
        if pos is None and game and event.card_id:
            card = game.get_card_by_id(event.card_id)
            if card:
                pos = card.position
        if pos is not None and event.amount:
            ui.add_floating_text(pos, f"+{event.amount}", 'heal')

    elif event.type == EventType.ARROW_ADDED:
        if event.from_position is not None and event.to_position is not None:
            ui.add_arrow(event.from_position, event.to_position, event.arrow_type or 'attack')

    elif event.type == EventType.ARROWS_CLEARED:
        ui.clear_arrows(immediate=False)


# =============================================================================
# GAME CLIENT - Wraps Game + UIState for client-side usage
# =============================================================================

class GameClient:
    """Client-side wrapper that combines Game state with local UI state.

    Responsibilities:
    - Maintain local UIState
    - Translate UI actions (clicks) into effectful commands
    - Apply events to update visuals
    - Recompute valid moves/attacks after state changes

    In network mode:
    - Game state is synced from server via events
    - Commands are sent to server for validation
    - UIState is purely local

    In local/hotseat mode:
    - Game state is authoritative locally
    - Commands are applied directly
    - UIState is maintained per current player
    """

    def __init__(self, game: 'Game', player: int = 1):
        self.game = game
        self.ui = UIState(viewing_player=player)

    @property
    def selected_card(self) -> Optional['Card']:
        """Get the currently selected card."""
        if self.ui.selected_card_id is None:
            return None
        return self.game.get_card_by_id(self.ui.selected_card_id)

    def _apply_forced_attack_constraints(self, card_id: int) -> bool:
        """Apply forced attack constraints to UI state. Returns True if constraints applied."""
        # Check for forced attacks on THIS card
        forced = compute_forced_attacks(self.game, card_id)
        if forced:
            self.ui.valid_moves = []
            self.ui.valid_attacks = forced
            self.ui.attack_mode = True
            return True

        # Check if ANY card has forced attacks - block moves
        if self.game.has_forced_attack:
            self.ui.valid_moves = []
            return True

        return False

    def select_card(self, card_id: int):
        """Select a card and compute valid actions."""
        card = self.game.get_card_by_id(card_id)
        if card is None:
            self.deselect()
            return

        # Clear arrows when selecting new card
        self.ui.clear_arrows(immediate=True)
        self.ui.selected_card_id = card_id

        # Check forced attack constraints
        if self._apply_forced_attack_constraints(card_id):
            return

        # Normal selection
        moves = compute_valid_moves(self.game, card_id) if can_card_act(self.game, card_id) else []
        self.ui.valid_moves = moves
        self.ui.valid_attacks = []
        self.ui.attack_mode = False

    def deselect(self):
        """Clear selection."""
        self.ui.clear_selection()
        self.ui.clear_arrows(immediate=True)

    def toggle_attack_mode(self):
        """Toggle between move and attack mode."""
        if self.ui.selected_card_id is None:
            return

        # Check forced attack constraints first
        if self._apply_forced_attack_constraints(self.ui.selected_card_id):
            return

        if self.ui.attack_mode:
            # Switch to move mode
            self.ui.valid_moves = compute_valid_moves(self.game, self.ui.selected_card_id)
            self.ui.valid_attacks = []
            self.ui.attack_mode = False
        else:
            # Switch to attack mode
            self.ui.valid_moves = []
            self.ui.valid_attacks = compute_attack_targets(self.game, self.ui.selected_card_id)
            self.ui.attack_mode = True

    def refresh_selection(self):
        """Recompute valid moves/attacks for current selection.

        Call this after game state changes (move, attack, turn change, etc.).
        """
        if self.ui.selected_card_id is None:
            return

        card = self.game.get_card_by_id(self.ui.selected_card_id)
        if card is None or card.player != self.game.current_player:
            self.deselect()
            return

        # Check forced attack constraints first
        if self._apply_forced_attack_constraints(self.ui.selected_card_id):
            return

        # Recompute based on current mode
        if self.ui.attack_mode:
            self.ui.valid_attacks = compute_attack_targets(self.game, self.ui.selected_card_id)
        else:
            self.ui.valid_moves = compute_valid_moves(self.game, self.ui.selected_card_id)

    def apply_events(self, events: List['Event']):
        """Apply events to update UI visuals."""
        for event in events:
            apply_event_to_ui(self.ui, event, self.game)

    def update(self, dt: float):
        """Update UI animations."""
        self.ui.update(dt)

    # =========================================================================
    # COMMAND GENERATION - Translate UI actions to effectful commands
    # =========================================================================

    def get_move_command(self, position: int):
        """Generate MOVE command for selected card to position."""
        from .commands import cmd_move
        if self.ui.selected_card_id is None:
            return None
        return cmd_move(self.game.current_player, self.ui.selected_card_id, position)

    def get_attack_command(self, position: int):
        """Generate ATTACK command for selected card to target position."""
        from .commands import cmd_attack
        if self.ui.selected_card_id is None:
            return None
        return cmd_attack(self.game.current_player, self.ui.selected_card_id, position)

    def get_ability_command(self, ability_id: str, target_id: int = None):
        """Generate USE_ABILITY command."""
        from .commands import cmd_use_ability
        if self.ui.selected_card_id is None:
            return None
        return cmd_use_ability(
            self.game.current_player,
            self.ui.selected_card_id,
            ability_id,
            target_id
        )
