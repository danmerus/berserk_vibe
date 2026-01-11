"""
Commands and Events for game state management.

Commands represent player intents (inputs to the game engine).
Events represent state changes (outputs from the game engine).

This separation is essential for:
- Network play (commands sent to server, events broadcast to clients)
- Replays (store commands, replay to recreate game)
- Testing (apply commands, verify events)
"""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List, Dict, Any


# =============================================================================
# COMMANDS - Player Intents
# =============================================================================

class CommandType(Enum):
    """Types of commands players can issue."""
    # Card selection
    SELECT_CARD = auto()      # Select by card_id (for network/replay)
    SELECT_POSITION = auto()  # Select by position (for UI clicks)
    DESELECT = auto()

    # Board interaction (high-level click that engine routes)
    CLICK_BOARD = auto()      # Click on board position - engine determines action

    # Movement and attacks
    MOVE = auto()
    ATTACK = auto()
    TOGGLE_ATTACK_MODE = auto()
    PREPARE_FLYER_ATTACK = auto()  # Tap to prepare for attacking flyers

    # Abilities
    USE_ABILITY = auto()
    USE_INSTANT = auto()  # Luck ability during priority

    # Interaction responses
    CONFIRM = auto()
    CANCEL = auto()
    CHOOSE_POSITION = auto()
    CHOOSE_CARD = auto()
    CHOOSE_AMOUNT = auto()

    # Turn management
    PASS_PRIORITY = auto()
    SKIP = auto()  # Skip optional action (defender, movement shot)
    END_TURN = auto()


@dataclass(frozen=True)
class Command:
    """
    A player command - immutable and serializable.

    All commands can be serialized to JSON for network transmission.
    """
    type: CommandType
    player: int  # Which player issued this command

    # Optional parameters (depending on command type)
    card_id: Optional[int] = None
    position: Optional[int] = None
    ability_id: Optional[str] = None
    target_id: Optional[int] = None
    amount: Optional[int] = None
    option: Optional[str] = None  # For instant abilities (e.g., "+1", "-1", "reroll")
    confirmed: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for network/storage."""
        return {
            'type': self.type.name,
            'player': self.player,
            'card_id': self.card_id,
            'position': self.position,
            'ability_id': self.ability_id,
            'target_id': self.target_id,
            'amount': self.amount,
            'option': self.option,
            'confirmed': self.confirmed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Command':
        """Deserialize from dictionary."""
        return cls(
            type=CommandType[data['type']],
            player=data['player'],
            card_id=data.get('card_id'),
            position=data.get('position'),
            ability_id=data.get('ability_id'),
            target_id=data.get('target_id'),
            amount=data.get('amount'),
            option=data.get('option'),
            confirmed=data.get('confirmed'),
        )


# Command factory functions for cleaner API
def cmd_select_card(player: int, card_id: int) -> Command:
    """Select a card by its ID (for network/replay - stable identifier)."""
    return Command(CommandType.SELECT_CARD, player, card_id=card_id)

def cmd_select_position(player: int, position: int) -> Command:
    """Select card at position (for UI clicks)."""
    return Command(CommandType.SELECT_POSITION, player, position=position)

def cmd_click_board(player: int, position: int) -> Command:
    """Click on board position - engine determines appropriate action."""
    return Command(CommandType.CLICK_BOARD, player, position=position)

def cmd_deselect(player: int) -> Command:
    return Command(CommandType.DESELECT, player)

def cmd_move(player: int, card_id: int, position: int) -> Command:
    """Move a card to a position. card_id specifies which card to move."""
    return Command(CommandType.MOVE, player, card_id=card_id, position=position)

def cmd_attack(player: int, card_id: int, position: int) -> Command:
    """Attack with a card at a target position. card_id specifies the attacker."""
    return Command(CommandType.ATTACK, player, card_id=card_id, position=position)

def cmd_toggle_attack_mode(player: int, card_id: Optional[int] = None) -> Command:
    """Toggle attack mode. card_id makes command self-contained for network play."""
    return Command(CommandType.TOGGLE_ATTACK_MODE, player, card_id=card_id)

def cmd_prepare_flyer_attack(player: int, card_id: int) -> Command:
    """Tap a ground card to prepare it to attack flyers (when opponent has only flyers)."""
    return Command(CommandType.PREPARE_FLYER_ATTACK, player, card_id=card_id)

def cmd_use_ability(player: int, card_id: int, ability_id: str, target_id: Optional[int] = None) -> Command:
    return Command(CommandType.USE_ABILITY, player, card_id=card_id, ability_id=ability_id, target_id=target_id)

def cmd_use_instant(player: int, card_id: int, ability_id: str, option: str) -> Command:
    return Command(CommandType.USE_INSTANT, player, card_id=card_id, ability_id=ability_id, option=option)

def cmd_confirm(player: int, confirmed: bool) -> Command:
    return Command(CommandType.CONFIRM, player, confirmed=confirmed)

def cmd_cancel(player: int) -> Command:
    return Command(CommandType.CANCEL, player)

def cmd_choose_position(player: int, position: int) -> Command:
    return Command(CommandType.CHOOSE_POSITION, player, position=position)

def cmd_choose_card(player: int, card_id: int) -> Command:
    return Command(CommandType.CHOOSE_CARD, player, card_id=card_id)

def cmd_choose_amount(player: int, amount: int) -> Command:
    return Command(CommandType.CHOOSE_AMOUNT, player, amount=amount)

def cmd_pass_priority(player: int) -> Command:
    return Command(CommandType.PASS_PRIORITY, player)

def cmd_skip(player: int) -> Command:
    return Command(CommandType.SKIP, player)

def cmd_end_turn(player: int) -> Command:
    return Command(CommandType.END_TURN, player)


# =============================================================================
# EVENTS - State Changes
# =============================================================================

class EventType(Enum):
    """Types of events the game can emit."""
    # Game flow
    GAME_STARTED = auto()
    TURN_STARTED = auto()
    TURN_ENDED = auto()
    PHASE_CHANGED = auto()
    GAME_OVER = auto()

    # Card state changes
    CARD_MOVED = auto()
    CARD_DAMAGED = auto()
    CARD_HEALED = auto()
    CARD_TAPPED = auto()
    CARD_UNTAPPED = auto()
    CARD_DIED = auto()
    CARD_SPAWNED = auto()  # For summoning

    # Combat
    COMBAT_STARTED = auto()
    DICE_ROLLED = auto()
    COMBAT_RESOLVED = auto()

    # Abilities
    ABILITY_ACTIVATED = auto()
    ABILITY_RESOLVED = auto()
    INSTANT_USED = auto()

    # Interactions (prompts for player input)
    INTERACTION_STARTED = auto()
    INTERACTION_ENDED = auto()

    # Priority system
    PRIORITY_CHANGED = auto()
    PRIORITY_PASSED = auto()

    # UI hints (not state changes, but useful for rendering)
    ARROW_ADDED = auto()
    ARROWS_CLEARED = auto()
    LOG_MESSAGE = auto()


@dataclass
class Event:
    """
    A game event - represents a state change.

    Events are broadcast to all clients and can be used for:
    - Updating remote game state
    - Triggering animations/sounds
    - Building replay logs
    """
    type: EventType

    # Common fields
    card_id: Optional[int] = None
    player: Optional[int] = None
    position: Optional[int] = None

    # Combat/damage
    amount: Optional[int] = None
    source_id: Optional[int] = None
    attacker_id: Optional[int] = None
    defender_id: Optional[int] = None
    attacker_roll: Optional[int] = None
    defender_roll: Optional[int] = None

    # Ability
    ability_id: Optional[str] = None
    target_id: Optional[int] = None
    option: Optional[str] = None

    # Movement
    from_position: Optional[int] = None
    to_position: Optional[int] = None

    # Game state
    winner: Optional[int] = None
    phase: Optional[str] = None
    turn_number: Optional[int] = None

    # Interaction
    interaction_kind: Optional[str] = None
    valid_positions: Optional[List[int]] = None
    valid_card_ids: Optional[List[int]] = None

    # UI hints
    arrow_type: Optional[str] = None
    message: Optional[str] = None

    # Generic context for complex events
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for network/storage."""
        result = {'type': self.type.name}
        for key, value in self.__dict__.items():
            if key != 'type' and value is not None:
                if isinstance(value, Enum):
                    result[key] = value.name
                else:
                    result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """Deserialize from dictionary."""
        data = data.copy()
        data['type'] = EventType[data['type']]
        return cls(**data)


# Event factory functions for cleaner API
def evt_game_started(turn_number: int = 1) -> Event:
    return Event(EventType.GAME_STARTED, turn_number=turn_number)

def evt_turn_started(player: int, turn_number: int) -> Event:
    return Event(EventType.TURN_STARTED, player=player, turn_number=turn_number)

def evt_turn_ended(player: int) -> Event:
    return Event(EventType.TURN_ENDED, player=player)

def evt_game_over(winner: int) -> Event:
    return Event(EventType.GAME_OVER, winner=winner)

def evt_card_moved(card_id: int, from_pos: int, to_pos: int) -> Event:
    return Event(EventType.CARD_MOVED, card_id=card_id, from_position=from_pos, to_position=to_pos)

def evt_card_damaged(card_id: int, amount: int, source_id: Optional[int] = None) -> Event:
    return Event(EventType.CARD_DAMAGED, card_id=card_id, amount=amount, source_id=source_id)

def evt_card_healed(card_id: int, amount: int, source_id: Optional[int] = None) -> Event:
    return Event(EventType.CARD_HEALED, card_id=card_id, amount=amount, source_id=source_id)

def evt_card_tapped(card_id: int) -> Event:
    return Event(EventType.CARD_TAPPED, card_id=card_id)

def evt_card_untapped(card_id: int) -> Event:
    return Event(EventType.CARD_UNTAPPED, card_id=card_id)

def evt_card_died(card_id: int) -> Event:
    return Event(EventType.CARD_DIED, card_id=card_id)

def evt_dice_rolled(attacker_id: int, defender_id: int, atk_roll: int, def_roll: int) -> Event:
    return Event(
        EventType.DICE_ROLLED,
        attacker_id=attacker_id,
        defender_id=defender_id,
        attacker_roll=atk_roll,
        defender_roll=def_roll
    )

def evt_ability_activated(card_id: int, ability_id: str, target_id: Optional[int] = None) -> Event:
    return Event(EventType.ABILITY_ACTIVATED, card_id=card_id, ability_id=ability_id, target_id=target_id)

def evt_instant_used(card_id: int, ability_id: str, option: str) -> Event:
    return Event(EventType.INSTANT_USED, card_id=card_id, ability_id=ability_id, option=option)

def evt_interaction_started(kind: str, valid_positions: Optional[List[int]] = None,
                            valid_card_ids: Optional[List[int]] = None,
                            context: Optional[Dict] = None) -> Event:
    return Event(
        EventType.INTERACTION_STARTED,
        interaction_kind=kind,
        valid_positions=valid_positions,
        valid_card_ids=valid_card_ids,
        context=context or {}
    )

def evt_interaction_ended() -> Event:
    return Event(EventType.INTERACTION_ENDED)

def evt_priority_changed(player: int) -> Event:
    return Event(EventType.PRIORITY_CHANGED, player=player)

def evt_arrow_added(from_pos: int, to_pos: int, arrow_type: str) -> Event:
    return Event(EventType.ARROW_ADDED, from_position=from_pos, to_position=to_pos, arrow_type=arrow_type)

def evt_arrows_cleared() -> Event:
    return Event(EventType.ARROWS_CLEARED)

def evt_log_message(message: str) -> Event:
    return Event(EventType.LOG_MESSAGE, message=message)
