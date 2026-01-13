"""Core game state and base class for mixins."""
from typing import List, Optional, Dict, Any, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field

from ..board import Board
from ..card import Card
from ..constants import GamePhase
from ..player_state import PlayerState
from ..commands import (
    Event, evt_log_message, evt_card_damaged, evt_card_healed,
    evt_arrow_added, evt_arrows_cleared, evt_card_died, evt_game_over,
    evt_interaction_started, evt_interaction_ended
)

if TYPE_CHECKING:
    from ..interaction import Interaction


@dataclass
class CombatResult:
    """Result of combat between two cards."""
    attacker_roll: int
    defender_roll: int
    attacker_damage_dealt: int
    defender_damage_dealt: int
    attacker_bonus: int = 0
    defender_bonus: int = 0
    attacker_name: str = ""
    defender_name: str = ""
    attacker_player: int = 1
    defender_player: int = 2

    @property
    def attacker_total(self) -> int:
        return self.attacker_roll + self.attacker_bonus

    @property
    def defender_total(self) -> int:
        return self.defender_roll + self.defender_bonus

    def to_dict(self) -> dict:
        return {
            'attacker_roll': self.attacker_roll,
            'defender_roll': self.defender_roll,
            'attacker_damage_dealt': self.attacker_damage_dealt,
            'defender_damage_dealt': self.defender_damage_dealt,
            'attacker_bonus': self.attacker_bonus,
            'defender_bonus': self.defender_bonus,
            'attacker_name': self.attacker_name,
            'defender_name': self.defender_name,
            'attacker_player': self.attacker_player,
            'defender_player': self.defender_player,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'CombatResult':
        return cls(**data)


@dataclass
class DiceContext:
    """Context for dice rolls during priority phase - uses IDs for serializability."""
    type: str  # 'combat' or 'ranged'
    attacker_id: int
    atk_roll: int
    atk_modifier: int = 0  # Luck can modify this

    # Combat-specific fields
    defender_id: Optional[int] = None
    def_roll: int = 0
    def_modifier: int = 0
    atk_bonus: int = 0
    def_bonus: int = 0
    dice_matter: bool = True
    defender_was_tapped: bool = False

    # Ranged-specific fields
    target_id: Optional[int] = None
    ability_id: Optional[str] = None
    ranged_type: Optional[str] = None  # 'shot' or 'throw'

    # Exchange handling flag - set to True after exchange choice is made
    exchange_resolved: bool = False

    # Extra context for abilities (e.g., counters_spent for axe_strike)
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            'type': self.type,
            'attacker_id': self.attacker_id,
            'atk_roll': self.atk_roll,
            'atk_modifier': self.atk_modifier,
            'defender_id': self.defender_id,
            'def_roll': self.def_roll,
            'def_modifier': self.def_modifier,
            'atk_bonus': self.atk_bonus,
            'def_bonus': self.def_bonus,
            'dice_matter': self.dice_matter,
            'defender_was_tapped': self.defender_was_tapped,
            'target_id': self.target_id,
            'ability_id': self.ability_id,
            'ranged_type': self.ranged_type,
            'exchange_resolved': self.exchange_resolved,
            'extra': self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DiceContext':
        return cls(**data)


@dataclass
class StackItem:
    """An instant ability on the stack - uses IDs for serializability."""
    card_id: int
    ability_id: str
    option: str  # '+1', '-1', or 'reroll'

    def to_dict(self) -> dict:
        return {
            'card_id': self.card_id,
            'ability_id': self.ability_id,
            'option': self.option,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'StackItem':
        return cls(**data)


class GameBase:
    """Base game state - core initialization and serialization."""

    def __init__(self):
        self.board = Board()
        self.phase = GamePhase.SETUP
        self.current_player = 1
        self.turn_number = 0
        self.winner: Optional[int] = None  # Set when game ends (by concede or elimination)

        # Player states (encapsulates per-player data)
        self.player_states: Dict[int, PlayerState] = {
            1: PlayerState(player=1),
            2: PlayerState(player=2),
        }

        # Combat state
        self.last_combat: Optional[CombatResult] = None

        # Valhalla targeting state (queue of pending triggers) - IDs only for serializability
        self.pending_valhalla: List[Tuple[int, str]] = []  # Queue of (dead_card_id, ability_id)

        # Friendly fire confirmation
        self.friendly_fire_target: Optional[int] = None

        # Priority system for instant abilities (внезапные действия)
        self.priority_phase: bool = False       # True when in priority window
        self.priority_player: int = 0           # Player who has priority (1 or 2)
        self.priority_passed: List[int] = []    # Players who have passed priority
        self.pending_dice_roll: Optional[DiceContext] = None  # Dice roll waiting for resolution
        self.instant_stack: List[StackItem] = []     # Stack of instant abilities to resolve

        # Card ID counter
        self._next_card_id = 1

        # Message log
        self.messages: List[str] = []

        # Network-transmissible events (Event objects from commands.py)
        self.events: List[Event] = []

        # Forced attack state (must_attack_tapped ability) - IDs only for serializability
        self.forced_attackers: Dict[int, List[int]] = {}  # {card_id: [positions]}

        # Unified interaction state (replaces all awaiting_*/pending_* patterns)
        from ..interaction import Interaction
        self.interaction: Optional[Interaction] = None

        # Server-authoritative dice rolls
        self._pending_rolls: List[int] = []

        # Track cards that have been offered untap this turn (to avoid re-prompting)
        self._untap_offered_this_turn: set = set()

    def log(self, msg: str, emit_event: bool = True):
        """Add a message to the log."""
        self.messages.append(msg)
        if len(self.messages) > 100:  # Keep last 100 messages
            self.messages.pop(0)
        if emit_event:
            self.emit_event(evt_log_message(msg))

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self, include_ui_state: bool = True) -> dict:
        """Serialize game state to dictionary for network/storage."""
        result = {
            'board': self.board.to_dict(),
            'phase': self.phase.name,
            'current_player': self.current_player,
            'turn_number': self.turn_number,
            'winner': self.winner,
            'pending_valhalla': [[card_id, ability_id] for card_id, ability_id in self.pending_valhalla],
            'friendly_fire_target': self.friendly_fire_target,
            'priority_phase': self.priority_phase,
            'priority_player': self.priority_player,
            'priority_passed': self.priority_passed,
            'pending_dice_roll': self.pending_dice_roll.to_dict() if self.pending_dice_roll else None,
            'instant_stack': [item.to_dict() for item in self.instant_stack],
            '_next_card_id': self._next_card_id,
            'forced_attackers': {str(k): v for k, v in self.forced_attackers.items()},
            'interaction': self.interaction.to_dict() if self.interaction else None,
            '_pending_rolls': self._pending_rolls,
            'messages': self.messages,
            'last_combat': self.last_combat.to_dict() if self.last_combat else None,
            '_untap_offered_this_turn': list(self._untap_offered_this_turn),
        }

        if include_ui_state:
            result.update({
                'player_states': {
                    str(k): v.to_dict() for k, v in self.player_states.items()
                },
            })

        return result

    def snapshot_for_player(self, player: int) -> dict:
        """Get game state snapshot filtered for a specific player."""
        import copy
        opponent = 3 - player

        snapshot = self.to_dict(include_ui_state=False)
        snapshot.pop('_pending_rolls', None)
        snapshot.pop('_next_card_id', None)

        # Redact face_down opponent cards (hide their info)
        for i, card_data in enumerate(snapshot['board']['cells']):
            if card_data and card_data.get('player') == opponent:
                if card_data.get('face_down', False):
                    snapshot['board']['cells'][i] = {
                        'id': card_data['id'],
                        'player': opponent,
                        'face_down': True,
                        'position': card_data.get('position'),
                        'hidden': True,
                    }

        player_state = self.player_states.get(player)
        if player_state:
            snapshot['hand'] = [card.to_dict() for card in player_state.hand]
        else:
            snapshot['hand'] = []

        return snapshot

    @classmethod
    def from_dict(cls, data: dict) -> 'GameBase':
        """Deserialize game state from dictionary."""
        game = cls.__new__(cls)

        game.board = Board.from_dict(data['board'])
        game.phase = GamePhase[data['phase']]
        game.current_player = data['current_player']
        game.turn_number = data['turn_number']
        game.winner = data.get('winner')

        # Build card lookup
        cards_by_id = {}
        for pos in range(36):
            card = game.board.get_card(pos)
            if card:
                cards_by_id[card.id] = card
        for card in game.board.graveyard_p1 + game.board.graveyard_p2:
            cards_by_id[card.id] = card

        if 'player_states' in data:
            game.player_states = {}
            for k, v in data['player_states'].items():
                player_num = int(k)
                game.player_states[player_num] = PlayerState.from_dict(v, cards_by_id)
                for card in game.player_states[player_num].hand:
                    cards_by_id[card.id] = card
        else:
            game.player_states = {
                1: PlayerState(player=1),
                2: PlayerState(player=2),
            }

        game.last_combat = CombatResult.from_dict(data['last_combat']) if data.get('last_combat') else None
        game.pending_valhalla = [tuple(item) for item in data.get('pending_valhalla', [])]
        game.friendly_fire_target = data.get('friendly_fire_target')
        game.priority_phase = data.get('priority_phase', False)
        game.priority_player = data.get('priority_player', 0)
        game.priority_passed = data.get('priority_passed', [])
        game.pending_dice_roll = DiceContext.from_dict(data['pending_dice_roll']) if data.get('pending_dice_roll') else None
        game.instant_stack = [StackItem.from_dict(item) for item in data.get('instant_stack', [])]
        game._next_card_id = data.get('_next_card_id', 1)
        game.messages = data.get('messages', [])
        game.events = []
        game.forced_attackers = {int(k): v for k, v in data.get('forced_attackers', {}).items()}

        from ..interaction import Interaction
        game.interaction = Interaction.from_dict(data['interaction']) if data.get('interaction') else None
        game._pending_rolls = data.get('_pending_rolls', [])
        game._untap_offered_this_turn = set(data.get('_untap_offered_this_turn', []))

        return game

    def get_card_by_id(self, card_id: int) -> Optional[Card]:
        """Look up a card by its ID across all locations."""
        if card_id is None:
            return None
        # Check main board (0-29) and all flying zones (30-39)
        max_pos = Board.FLYING_P2_START + Board.FLYING_SLOTS
        for pos in range(max_pos):
            card = self.board.get_card(pos)
            if card and card.id == card_id:
                return card
        for card in self.board.graveyard_p1:
            if card.id == card_id:
                return card
        for card in self.board.graveyard_p2:
            if card.id == card_id:
                return card
        for card in self.hand_p1:
            if card.id == card_id:
                return card
        for card in self.hand_p2:
            if card.id == card_id:
                return card
        return None

    # =========================================================================
    # PLAYER STATE PROPERTIES
    # =========================================================================

    @property
    def current_player_state(self) -> PlayerState:
        """Get the current player's state."""
        return self.player_states[self.current_player]

    def get_player_state(self, player: int) -> PlayerState:
        """Get a specific player's state."""
        return self.player_states[player]

    @property
    def hand_p1(self) -> List[Card]:
        return self.player_states[1].hand

    @hand_p1.setter
    def hand_p1(self, value: List[Card]):
        self.player_states[1].hand = value

    @property
    def hand_p2(self) -> List[Card]:
        return self.player_states[2].hand

    @hand_p2.setter
    def hand_p2(self, value: List[Card]):
        self.player_states[2].hand = value

    # =========================================================================
    # EVENT EMISSION
    # =========================================================================

    def emit_event(self, event: Event):
        """Emit a network-transmissible event."""
        self.events.append(event)

    def pop_events(self) -> List[Event]:
        """Pop and return all pending network events."""
        events = self.events
        self.events = []
        return events

    def emit_damage(self, pos: int, amount: int, card_id: Optional[int] = None,
                    source_id: Optional[int] = None):
        """Emit a damage event for network sync."""
        if amount > 0 and card_id is not None:
            self.emit_event(evt_card_damaged(card_id, amount, pos, source_id))

    def emit_heal(self, pos: int, amount: int, card_id: Optional[int] = None,
                  source_id: Optional[int] = None):
        """Emit a heal event for network sync."""
        if amount > 0 and card_id is not None:
            self.emit_event(evt_card_healed(card_id, amount, pos, source_id))

    def emit_arrow(self, from_pos: int, to_pos: int, arrow_type: str = 'attack'):
        """Emit an arrow event for network sync."""
        if from_pos is not None and to_pos is not None:
            self.emit_event(evt_arrow_added(from_pos, to_pos, arrow_type))

    def emit_clear_arrows(self):
        """Emit event to clear all arrows."""
        self.emit_event(evt_arrows_cleared())

    def emit_clear_arrows_immediate(self):
        """Emit event to clear arrows immediately."""
        self.emit_event(evt_arrows_cleared())

    # =========================================================================
    # INTERACTION MANAGEMENT
    # =========================================================================

    def set_interaction(self, interaction: 'Interaction'):
        """Set the current interaction and emit event."""
        self.interaction = interaction
        self.emit_event(evt_interaction_started(
            kind=interaction.kind.name,
            valid_positions=list(interaction.valid_positions) if interaction.valid_positions else None,
            valid_card_ids=list(interaction.valid_card_ids) if interaction.valid_card_ids else None,
            context=interaction.context
        ))

    def clear_interaction(self):
        """Clear the current interaction and emit event."""
        if self.interaction is not None:
            self.interaction = None
            self.emit_event(evt_interaction_ended())

    # =========================================================================
    # INTERACTION AWAITING PROPERTIES (convenience)
    # =========================================================================

    @property
    def awaiting_defender(self) -> bool:
        """Check if waiting for defender selection."""
        from ..interaction import InteractionKind
        return self.interaction is not None and self.interaction.kind == InteractionKind.SELECT_DEFENDER

    @property
    def awaiting_priority(self) -> bool:
        """Check if in priority phase (dice roll pending)."""
        return self.priority_phase and self.pending_dice_roll is not None

    @property
    def has_blocking_interaction(self) -> bool:
        """Check if there's an interaction blocking normal play."""
        return self.interaction is not None
