"""Game state management and logic."""
import random
from typing import List, Optional, Tuple, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass, field

from .board import Board
from .card import Card, create_card
from .card_database import create_starter_deck, create_starter_deck_p2
from .constants import GamePhase
from .abilities import get_ability, AbilityType, AbilityTrigger, TargetType, Ability
from .ability_handlers import get_handler, has_handler, get_targeter, get_trigger_handler
from .interaction import (
    Interaction, InteractionKind,
    interaction_select_defender, interaction_select_target,
    interaction_counter_shot, interaction_movement_shot,
    interaction_valhalla, interaction_confirm_heal,
    interaction_choose_stench, interaction_choose_exchange,
    interaction_select_counters
)
from .player_state import PlayerState
from .commands import (
    Command, CommandType, Event,
    evt_log_message, evt_card_damaged, evt_card_healed, evt_card_tapped,
    evt_card_untapped, evt_card_died, evt_card_moved, evt_dice_rolled,
    evt_turn_started, evt_turn_ended, evt_game_over, evt_ability_activated,
    evt_arrow_added, evt_arrows_cleared,
    evt_interaction_started, evt_interaction_ended
)


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


class Game:
    """Main game state and logic."""

    def __init__(self):
        self.board = Board()
        self.phase = GamePhase.SETUP
        self.current_player = 1
        self.turn_number = 0

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
        # These are emitted by state-changing actions for network/replay
        # Clients should use pop_events() and apply_event_to_ui() for visuals
        self.events: List[Event] = []

        # Forced attack state (must_attack_tapped ability) - IDs only for serializability
        # Maps card_id -> [positions] for cards that must attack tapped enemies
        self.forced_attackers: Dict[int, List[int]] = {}  # {card_id: [positions]}

        # Unified interaction state (replaces all awaiting_*/pending_* patterns)
        # Counter selection uses interaction.selected_amount, target selection uses context['counters_spent']
        # See interaction.py for InteractionKind enum and Interaction dataclass
        self.interaction: Optional[Interaction] = None

        # Server-authoritative dice rolls
        # In network mode, server injects rolls via inject_rolls() before commands
        # In local mode, roll_dice() generates rolls normally
        self._pending_rolls: List[int] = []

    def log(self, msg: str, emit_event: bool = True):
        """Add a message to the log.

        Args:
            msg: The message to log
            emit_event: If True, also emit a LOG_MESSAGE event for network sync
        """
        self.messages.append(msg)
        if len(self.messages) > 100:  # Keep last 100 messages
            self.messages.pop(0)
        if emit_event:
            self.emit_event(evt_log_message(msg))

    # =========================================================================
    # SERIALIZATION (for network play and save/load)
    # =========================================================================
    #
    # State Categories:
    # - SERVER STATE: Authoritative game state that must be synchronized
    # - UI STATE: Client-local state (selection, valid moves, visual effects)
    #
    # In network mode:
    # - Server sends only SERVER STATE to clients
    # - Each client maintains its own UI STATE locally
    # - See src/ui_state.py for the UIState class
    # =========================================================================

    def to_dict(self, include_ui_state: bool = True) -> dict:
        """Serialize game state to dictionary for network/storage.

        Args:
            include_ui_state: If True, include UI state (for save/load).
                              If False, only include server state (for network sync).
        """
        # SERVER STATE - authoritative, must be synchronized
        result = {
            'board': self.board.to_dict(),
            'phase': self.phase.name,
            'current_player': self.current_player,
            'turn_number': self.turn_number,

            # Valhalla queue (list of tuples -> list of lists for JSON)
            'pending_valhalla': [[card_id, ability_id] for card_id, ability_id in self.pending_valhalla],

            # Friendly fire
            'friendly_fire_target': self.friendly_fire_target,

            # Priority system
            'priority_phase': self.priority_phase,
            'priority_player': self.priority_player,
            'priority_passed': self.priority_passed,
            'pending_dice_roll': self.pending_dice_roll.to_dict() if self.pending_dice_roll else None,
            'instant_stack': [item.to_dict() for item in self.instant_stack],

            # Card ID counter (needed to preserve ID uniqueness after load)
            '_next_card_id': self._next_card_id,

            # Forced attackers
            'forced_attackers': {str(k): v for k, v in self.forced_attackers.items()},

            # Unified interaction (what the game is asking for)
            'interaction': self.interaction.to_dict() if self.interaction else None,

            # Server-authoritative dice rolls (pending injected rolls)
            '_pending_rolls': self._pending_rolls,
        }

        # UI STATE - client-local, included for save/load but not network sync
        if include_ui_state:
            result.update({
                # Player states (include hand for setup, selection for save/load)
                'player_states': {
                    str(k): v.to_dict() for k, v in self.player_states.items()
                },

                # Combat result display
                'last_combat': self.last_combat.to_dict() if self.last_combat else None,

                # Message log
                'messages': self.messages,
            })

        return result

    def snapshot_for_player(self, player: int) -> dict:
        """Get game state snapshot filtered for a specific player.

        Hides information the player shouldn't see:
        - Opponent's hand cards (during setup)
        - Face-down card identities (setup phase)
        - Server-only data like pending rolls

        Args:
            player: 1 or 2, the player who will receive this snapshot

        Returns:
            Filtered game state dictionary
        """
        import copy
        opponent = 3 - player  # 1 -> 2, 2 -> 1

        # Start with server state (no UI state)
        snapshot = self.to_dict(include_ui_state=False)

        # Remove server-only data that clients shouldn't see
        snapshot.pop('_pending_rolls', None)
        snapshot.pop('_next_card_id', None)

        # During SETUP phase, hide face-down card identities
        if self.phase == GamePhase.SETUP:
            # Replace opponent's board cards with hidden versions
            for i, card_data in enumerate(snapshot['board']['cells']):
                if card_data and card_data.get('player') == opponent:
                    if card_data.get('face_down', False):
                        # Replace with minimal info (position, player, face_down)
                        snapshot['board']['cells'][i] = {
                            'id': card_data['id'],
                            'player': opponent,
                            'face_down': True,
                            'position': card_data.get('position'),
                            # Hidden card placeholder - client can show card back
                            'hidden': True,
                        }

        # Add this player's hand only
        player_state = self.player_states.get(player)
        if player_state:
            snapshot['hand'] = [card.to_dict() for card in player_state.hand]
        else:
            snapshot['hand'] = []

        # Don't include opponent's hand at all

        return snapshot

    @classmethod
    def from_dict(cls, data: dict) -> 'Game':
        """Deserialize game state from dictionary.

        Handles both full serialization (with UI state) and server-only
        serialization (without UI state) gracefully.
        """
        game = cls.__new__(cls)  # Create without calling __init__

        # Board
        game.board = Board.from_dict(data['board'])

        # Basic state
        game.phase = GamePhase[data['phase']]
        game.current_player = data['current_player']
        game.turn_number = data['turn_number']

        # Build card lookup for player state hand reconstruction
        cards_by_id = {}
        for pos in range(36):
            card = game.board.get_card(pos)
            if card:
                cards_by_id[card.id] = card
        for card in game.board.graveyard_p1 + game.board.graveyard_p2:
            cards_by_id[card.id] = card

        # Player states (UI STATE - may be missing in server-only data)
        if 'player_states' in data:
            game.player_states = {}
            for k, v in data['player_states'].items():
                player_num = int(k)
                game.player_states[player_num] = PlayerState.from_dict(v, cards_by_id)
                # Add hand cards to lookup
                for card in game.player_states[player_num].hand:
                    cards_by_id[card.id] = card
        else:
            # Create default empty player states (server-only mode)
            game.player_states = {
                1: PlayerState(player=1),
                2: PlayerState(player=2),
            }

        # Combat state
        game.last_combat = CombatResult.from_dict(data['last_combat']) if data.get('last_combat') else None

        # Valhalla queue (list of lists -> list of tuples)
        game.pending_valhalla = [tuple(item) for item in data.get('pending_valhalla', [])]

        # Friendly fire
        game.friendly_fire_target = data.get('friendly_fire_target')

        # Priority system
        game.priority_phase = data.get('priority_phase', False)
        game.priority_player = data.get('priority_player', 0)
        game.priority_passed = data.get('priority_passed', [])
        game.pending_dice_roll = DiceContext.from_dict(data['pending_dice_roll']) if data.get('pending_dice_roll') else None
        game.instant_stack = [StackItem.from_dict(item) for item in data.get('instant_stack', [])]

        # Card ID counter
        game._next_card_id = data.get('_next_card_id', 1)

        # Message log
        game.messages = data.get('messages', [])

        # Network events (not serialized - cleared each frame)
        game.events = []

        # Forced attackers (convert string keys back to int)
        game.forced_attackers = {int(k): v for k, v in data.get('forced_attackers', {}).items()}

        # Unified interaction
        from .interaction import Interaction
        game.interaction = Interaction.from_dict(data['interaction']) if data.get('interaction') else None

        # Server-authoritative dice rolls
        game._pending_rolls = data.get('_pending_rolls', [])

        return game

    def get_card_by_id(self, card_id: int) -> Optional[Card]:
        """Look up a card by its ID across all locations (board, flying, graveyard, hands)."""
        if card_id is None:
            return None
        # Check board positions (including flying zones)
        for pos in range(36):  # 0-29 ground, 30-35 flying
            card = self.board.get_card(pos)
            if card and card.id == card_id:
                return card
        # Check graveyards
        for card in self.board.graveyard_p1:
            if card.id == card_id:
                return card
        for card in self.board.graveyard_p2:
            if card.id == card_id:
                return card
        # Check hands
        for card in self.hand_p1:
            if card.id == card_id:
                return card
        for card in self.hand_p2:
            if card.id == card_id:
                return card
        return None

    # =========================================================================
    # PLAYER STATE PROPERTIES (backwards compatibility + delegation)
    # =========================================================================

    @property
    def current_player_state(self) -> PlayerState:
        """Get the current player's state."""
        return self.player_states[self.current_player]

    def get_player_state(self, player: int) -> PlayerState:
        """Get a specific player's state."""
        return self.player_states[player]

    # Hand properties (delegate to PlayerState)
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
        """Emit a network-transmissible event for replay/network sync."""
        self.events.append(event)

    def pop_events(self) -> List[Event]:
        """Pop and return all pending network events (for transmission)."""
        events = self.events
        self.events = []
        return events

    def emit_damage(self, pos: int, amount: int, card_id: Optional[int] = None,
                    source_id: Optional[int] = None):
        """Emit a damage event for network sync. Clients build visuals from events."""
        if amount > 0 and card_id is not None:
            self.emit_event(evt_card_damaged(card_id, amount, source_id))

    def emit_heal(self, pos: int, amount: int, card_id: Optional[int] = None,
                  source_id: Optional[int] = None):
        """Emit a heal event for network sync. Clients build visuals from events."""
        if amount > 0 and card_id is not None:
            self.emit_event(evt_card_healed(card_id, amount, source_id))

    def emit_arrow(self, from_pos: int, to_pos: int, arrow_type: str = 'attack'):
        """Emit an arrow event for network sync. Clients build visuals from events."""
        if from_pos is not None and to_pos is not None:
            self.emit_event(evt_arrow_added(from_pos, to_pos, arrow_type))

    def emit_clear_arrows(self):
        """Emit event to clear all arrows (after damage is dealt)."""
        self.emit_event(evt_arrows_cleared())

    def emit_clear_arrows_immediate(self):
        """Emit event to clear arrows immediately (for cancellation)."""
        self.emit_event(evt_arrows_cleared())

    def set_interaction(self, interaction: 'Interaction'):
        """Set the current interaction and emit event for network sync.

        Use this instead of directly setting self.interaction for consistent events.
        """
        self.interaction = interaction
        self.emit_event(evt_interaction_started(
            kind=interaction.kind.name,
            valid_positions=list(interaction.valid_positions) if interaction.valid_positions else None,
            valid_card_ids=list(interaction.valid_card_ids) if interaction.valid_card_ids else None,
            context=interaction.context
        ))

    def clear_interaction(self):
        """Clear the current interaction and emit event for network sync.

        Use this instead of directly setting self.interaction = None for consistent events.
        """
        if self.interaction is not None:
            self.interaction = None
            self.emit_event(evt_interaction_ended())

    def _handle_death(self, card: Card, killer: Optional[Card] = None) -> bool:
        """Handle card death, graveyard, and return True if card died."""
        if card.is_alive:
            return False
        self.log(f"{card.name} погиб!")
        self.emit_event(evt_card_died(card.id))
        # Reset tapped state for graveyard display
        card.tapped = False
        if killer and killer.player != card.player:
            card.killed_by_enemy = True
            # Process ON_KILL triggers for the killer
            self._process_kill_triggers(killer, card)
        self.board.send_to_graveyard(card)
        # Recalculate formations after a card dies
        self.recalculate_formations()
        return True

    def _deal_damage(self, target: Card, amount: int, is_magical: bool = False,
                     source_id: Optional[int] = None) -> Tuple[int, bool]:
        """Deal damage to target. Returns (actual_damage, was_web_blocked).

        Args:
            target: Card receiving damage
            amount: Damage amount
            is_magical: If True, bypasses armor
            source_id: ID of the card dealing damage (for network events)
        """
        if target.webbed:
            target.webbed = False
            self.log(f"  -> Паутина блокирует и спадает!")
            self.emit_clear_arrows()
            return 0, True

        # Apply formation armor for non-magical damage (depletes like base armor)
        if not is_magical and target.formation_armor_remaining > 0:
            absorbed = min(amount, target.formation_armor_remaining)
            target.formation_armor_remaining -= absorbed
            amount -= absorbed
            if absorbed > 0:
                self.log(f"  -> Броня строя поглощает {absorbed} урона")

        # Apply base armor for non-magical damage
        actual, armor_absorbed = target.take_damage_with_armor(amount, is_magical)
        if armor_absorbed > 0:
            self.log(f"  -> Броня поглощает {armor_absorbed} урона")

        self.emit_damage(target.position, actual, card_id=target.id, source_id=source_id)
        return actual, False

    def _process_kill_triggers(self, killer: Card, victim: Card):
        """Process ON_KILL triggered abilities when killer defeats enemy."""
        if not killer.is_alive:
            return

        ctx = {'victim': victim}
        for ability_id in killer.stats.ability_ids:
            ability = get_ability(ability_id)
            if not ability or ability.trigger != AbilityTrigger.ON_KILL:
                continue

            # Try registered trigger handler first
            handler = get_trigger_handler(ability_id)
            if handler:
                handler(self, killer, ability, ctx)

    def _check_winner(self) -> bool:
        """Check for winner and update game state. Returns True if game ended."""
        winner = self.board.check_winner()
        if winner is not None:
            self.phase = GamePhase.GAME_OVER
            if winner == 0:
                self.log("Ничья!")
            else:
                self.log(f"Победа игрока {winner}!")
            self.emit_event(evt_game_over(winner))
            return True
        return False

    def _get_orthogonal_neighbors(self, pos: int) -> List[int]:
        """Get orthogonally adjacent positions (up/down/left/right, not diagonal)."""
        col, row = pos % 5, pos // 5
        neighbors = []
        for dc, dr in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            nc, nr = col + dc, row + dr
            if 0 <= nc < 5 and 0 <= nr < 6:
                neighbors.append(nr * 5 + nc)
        return neighbors

    def _has_formation_ability(self, card: Card) -> bool:
        """Check if card has any formation ability."""
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.is_formation:
                return True
        return False

    def _has_elite_ally_in_formation(self, card: Card) -> bool:
        """Check if card has an elite formation partner (adjacent ally with formation ability)."""
        if card.position is None:
            return False
        for neighbor_pos in self._get_orthogonal_neighbors(card.position):
            neighbor = self.board.get_card(neighbor_pos)
            if neighbor and neighbor.player == card.player and neighbor.is_alive:
                # Must be a formation partner (has formation ability) AND elite
                if self._has_formation_ability(neighbor) and neighbor.stats.is_elite:
                    return True
        return False

    def _has_common_ally_in_formation(self, card: Card) -> bool:
        """Check if card has a common (non-elite) formation partner (adjacent ally with formation ability)."""
        if card.position is None:
            return False
        for neighbor_pos in self._get_orthogonal_neighbors(card.position):
            neighbor = self.board.get_card(neighbor_pos)
            if neighbor and neighbor.player == card.player and neighbor.is_alive:
                # Must be a formation partner (has formation ability) AND non-elite
                if self._has_formation_ability(neighbor) and not neighbor.stats.is_elite:
                    return True
        return False

    def recalculate_formations(self):
        """Recalculate formation status for all cards on board.

        A card is 'in formation' if:
        1. It has a formation ability
        2. It's orthogonally adjacent to an ALLY with a formation ability
        """
        all_cards = self.board.get_all_cards(include_flying=False)  # Formation only for ground

        # First pass: clear all formation status and track previous state
        old_state = {}
        for card in all_cards:
            old_state[card.id] = (card.in_formation, card.formation_armor_remaining)
            card.in_formation = False

        # Second pass: check each card with formation ability
        for card in all_cards:
            if card.position is None or not card.is_alive:
                continue
            if not self._has_formation_ability(card):
                continue

            # Check orthogonal neighbors for allied cards with formation
            for neighbor_pos in self._get_orthogonal_neighbors(card.position):
                neighbor = self.board.get_card(neighbor_pos)
                if neighbor and neighbor.player == card.player and neighbor.is_alive:
                    if self._has_formation_ability(neighbor):
                        # Both have formation abilities and are adjacent
                        card.in_formation = True
                        neighbor.in_formation = True
                        break

        # Third pass: update formation armor immediately based on new formation state
        for card in all_cards:
            was_in, _ = old_state.get(card.id, (False, 0))
            if card.in_formation:
                new_bonus = self._get_formation_armor_bonus(card)
                if not was_in or new_bonus != card.formation_armor_max:
                    # Entered formation or bonus changed - set new armor
                    card.formation_armor_remaining = new_bonus
                    card.formation_armor_max = new_bonus
                # If same bonus and was in formation, keep remaining armor
            else:
                # Not in formation - clear formation armor
                card.formation_armor_remaining = 0
                card.formation_armor_max = 0

    def _update_forced_attackers(self):
        """Update list of cards that must attack adjacent tapped enemies.

        Cards with must_attack_tapped ability must attack an adjacent tapped
        enemy before any other action can be taken.

        Stores card_id -> [positions] for serializability.
        """
        self.forced_attackers = {}  # {card_id: [positions]}

        for card in self.board.get_all_cards(self.current_player):
            if not card.is_alive or not card.can_act:
                continue
            if not card.has_ability("must_attack_tapped"):
                continue

            # Check adjacent cells for tapped enemies
            adjacent_tapped = []
            for adj_pos in self.board.get_adjacent_cells(card.position, include_diagonals=True):
                adj_card = self.board.get_card(adj_pos)
                if adj_card and adj_card.player != card.player and adj_card.tapped:
                    adjacent_tapped.append(adj_pos)

            if adjacent_tapped:
                self.forced_attackers[card.id] = adjacent_tapped

    @property
    def has_forced_attack(self) -> bool:
        """True if there's a card that must attack a tapped enemy."""
        return len(self.forced_attackers) > 0

    def get_forced_attacker_card(self, card: Card) -> Optional[List[int]]:
        """Get forced attack targets for a card, or None if not a forced attacker."""
        if card.id in self.forced_attackers:
            return self.forced_attackers[card.id]  # Return positions list directly
        return None

    def opponent_has_only_flyers(self, player: int) -> bool:
        """Check if the opponent of given player has only flying creatures left.

        When this is true, ground creatures can tap to gain a one-time ability
        to attack any flying creature with a simple strike.
        """
        opponent = 2 if player == 1 else 1
        ground_cards = self.board.get_all_cards(opponent, include_flying=False)
        flying_cards = self.board.get_flying_cards(opponent)
        return len(ground_cards) == 0 and len(flying_cards) > 0

    def can_prepare_flyer_attack(self, card: Card) -> bool:
        """Check if a ground card can tap to prepare for flyer attack.

        Requirements:
        - It's the card owner's turn
        - Card is not flying
        - Card is not already tapped
        - Card doesn't already have flyer attack prepared
        - Opponent has only flying creatures (no ground cards left)
        """
        # Must be card owner's turn
        if self.current_player != card.player:
            return False
        if card.stats.is_flying:
            return False
        if card.tapped:
            return False
        if card.can_attack_flyer:
            return False  # Already prepared
        return self.opponent_has_only_flyers(card.player)

    def prepare_flyer_attack(self, card: Card) -> bool:
        """Tap a ground card to prepare it to attack flyers.

        The card gains the ability to attack one flying creature until
        the end of the owner's next turn.
        """
        if not self.can_prepare_flyer_attack(card):
            return False

        card.tap()
        card.can_attack_flyer = True
        # Calculate when this expires: end of owner's next turn
        # turn_number increments after P2's turn, expiration check runs before increment
        # Both players get exactly one full turn to use this ability
        card.can_attack_flyer_until_turn = self.turn_number + 1

        self.log(f"{card.name} готовится атаковать летающих!")
        return True

    def get_attack_targets(self, card: Card, include_allies: bool = True) -> List[int]:
        """Get valid attack targets for a card.

        Extends board.get_attack_targets with game-specific rules:
        - If card has can_attack_flyer, adds enemy flying creatures as targets
        """
        targets = self.board.get_attack_targets(card, include_allies)

        # If card has prepared flyer attack, add enemy flyers as targets
        if card.can_attack_flyer and not card.stats.is_flying:
            enemy_player = 2 if card.player == 1 else 1
            for flying_card in self.board.get_flying_cards(enemy_player):
                if flying_card.is_alive and flying_card.position is not None:
                    if flying_card.position not in targets:
                        targets.append(flying_card.position)

        return targets

    def setup_game(self, p1_squad: list = None, p2_squad: list = None):
        """Initialize a new game.

        Args:
            p1_squad: List of card names for player 1's squad. If None, uses starter deck.
            p2_squad: List of card names for player 2's squad. If None, uses starter deck.
        """
        # Use provided squads or fall back to starter decks
        deck_p1 = p1_squad if p1_squad else create_starter_deck()
        deck_p2 = p2_squad if p2_squad else create_starter_deck_p2()

        # Create cards for both players
        for name in deck_p1:
            card = create_card(name, player=1, card_id=self._next_card_id)
            self._next_card_id += 1
            self.hand_p1.append(card)

        for name in deck_p2:
            card = create_card(name, player=2, card_id=self._next_card_id)
            self._next_card_id += 1
            self.hand_p2.append(card)

        # Sort hands by cost (descending) for easier placement
        self.hand_p1.sort(key=lambda c: c.stats.cost, reverse=True)
        self.hand_p2.sort(key=lambda c: c.stats.cost, reverse=True)

        self.phase = GamePhase.SETUP
        self.current_player = 1
        self.log("Игра началась! Расставьте существ.")

    def setup_game_with_placement(self, p1_cards: List[Card], p2_cards: List[Card]):
        """Initialize game with pre-placed cards from placement phase.

        Args:
            p1_cards: List of Card objects for player 1, with positions already set.
            p2_cards: List of Card objects for player 2, with positions already set.
        """
        # Separate flying and ground cards
        p1_ground = [c for c in p1_cards if not c.stats.is_flying]
        p1_flying = [c for c in p1_cards if c.stats.is_flying]
        p2_ground = [c for c in p2_cards if not c.stats.is_flying]
        p2_flying = [c for c in p2_cards if c.stats.is_flying]

        # Place ground cards at their assigned positions
        for card in p1_ground:
            self.board.place_card(card, card.position)

        for card in p2_ground:
            self.board.place_card(card, card.position)

        # Place flying cards in flying zones
        for i, card in enumerate(p1_flying[:self.board.FLYING_SLOTS]):
            flying_pos = self.board.FLYING_P1_START + i
            card.position = flying_pos
            self.board.place_card(card, flying_pos)

        for i, card in enumerate(p2_flying[:self.board.FLYING_SLOTS]):
            flying_pos = self.board.FLYING_P2_START + i
            card.position = flying_pos
            self.board.place_card(card, flying_pos)

        # Set up game state
        self.phase = GamePhase.MAIN
        self.turn_number = 1
        self.current_player = 1

        # Calculate initial formations
        self.recalculate_formations()

        self.log("Карты расставлены!")

        # Start the first turn (triggers ON_TURN_START abilities)
        self.start_turn()

    def auto_place_for_testing(self):
        """Auto-place some cards for quick testing, prioritizing cards with abilities."""
        positions_p1 = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]  # All 3 rows
        positions_p2 = [29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15]  # All 3 rows

        def select_cards(hand, count):
            """Select cards prioritizing those with abilities (excluding flying)."""
            # Separate flying cards first
            flying = [c for c in hand if c.stats.is_flying]
            ground = [c for c in hand if not c.stats.is_flying]

            # Priority cards for testing
            priority_names = ("Оури", "Паук-пересмешник", "Матросы Аделаиды", "Эльфийский воин", "Ловец удачи", "Горный великан", "Ледовый охотник", "Костедробитель", "Борг", "Гном-басаарг", "Мастер топора", "Повелитель молний", "Смотритель горнила", "Хранитель гор", "Мразень", "Овражный гном")
            giants = [c for c in ground if c.name == "Горный великан"]  # Formation cards
            hunters = [c for c in ground if c.name == "Ледовый охотник"]  # Valhalla OVA
            crushers = [c for c in ground if c.name == "Костедробитель"]  # Valhalla strike
            borgs = [c for c in ground if c.name == "Борг"]  # Stun ability (elite)
            dwarves = [c for c in ground if c.name == "Гном-басаарг"]  # Tapped bonus
            axe_masters = [c for c in ground if c.name == "Мастер топора"]  # Armor + counter strike
            lightning = [c for c in ground if c.name == "Повелитель молний"]  # Discharge ability
            furnace = [c for c in ground if c.name == "Смотритель горнила"]  # Formation armor/ovz
            keepers = [c for c in ground if c.name == "Хранитель гор"]  # Anti-swamp bonus
            frost = [c for c in ground if c.name == "Мразень"]  # Icicle ranged attack
            ravine = [c for c in ground if c.name == "Овражный гном"]  # Hellish stench + tapped bonus
            ouri = [c for c in ground if c.name == "Оури"]
            spider = [c for c in ground if c.name == "Паук-пересмешник"]
            sailors = [c for c in ground if c.name == "Матросы Аделаиды"]
            elf = [c for c in ground if c.name == "Эльфийский воин"]
            luck = [c for c in ground if c.name == "Ловец удачи"]  # Card with instant ability
            expensive = [c for c in ground if c.stats.cost >= 7 and c.name not in priority_names]
            with_abilities = [c for c in ground if c.stats.ability_ids and c.name not in priority_names and c.stats.cost < 7]
            without_abilities = [c for c in ground if not c.stats.ability_ids and c.stats.cost < 7]
            without_abilities.sort(key=lambda c: c.stats.cost, reverse=True)

            # Order: Giants, lightning, axe masters, dwarves, borgs, furnace (next to borg for formation), keepers, frost, ravine, luck (instant ability), hunters, crushers, then others
            selected_ground = (giants + lightning + axe_masters + dwarves + borgs + furnace + keepers + frost + ravine + luck + hunters[:1] + crushers[:1] + ouri[:1] + expensive[:1] + spider + sailors + elf + hunters[1:] + crushers[1:] + ouri[1:] + expensive[1:] + with_abilities + without_abilities)[:count]
            return selected_ground, flying

        ground_p1, flying_p1 = select_cards(self.hand_p1, len(positions_p1))
        ground_p2, flying_p2 = select_cards(self.hand_p2, len(positions_p2))

        # Place ground cards
        for card, pos in zip(ground_p1, positions_p1):
            self.board.place_card(card, pos)

        for card, pos in zip(ground_p2, positions_p2):
            self.board.place_card(card, pos)

        # Place flying cards
        for i, card in enumerate(flying_p1[:self.board.FLYING_SLOTS]):
            self.board.place_card(card, self.board.FLYING_P1_START + i)

        for i, card in enumerate(flying_p2[:self.board.FLYING_SLOTS]):
            self.board.place_card(card, self.board.FLYING_P2_START + i)

        # Clear hands (remaining cards not placed)
        self.hand_p1.clear()
        self.hand_p2.clear()

        self.phase = GamePhase.MAIN
        self.turn_number = 1
        self.current_player = 1

        # Calculate initial formations
        self.recalculate_formations()

        self.log("Карты расставлены!")

        # Start the first turn (triggers ON_TURN_START abilities)
        self.start_turn()

    def get_current_hand(self) -> List[Card]:
        """Get hand for current player."""
        return self.hand_p1 if self.current_player == 1 else self.hand_p2

    def place_card_from_hand(self, card: Card, pos: int) -> bool:
        """Place a card from hand onto the board during setup."""
        if self.phase != GamePhase.SETUP:
            return False

        hand = self.get_current_hand()
        if card not in hand:
            return False

        # Flying creatures must go to flying zone
        if card.stats.is_flying:
            valid_positions = self.board.get_flying_placement_zone(card.player)
        else:
            valid_positions = self.board.get_placement_zone(card.player)

        if pos not in valid_positions:
            return False

        if self.board.place_card(card, pos):
            hand.remove(card)
            zone_name = "зону полёта" if card.stats.is_flying else "поле"
            self.log(f"{card.name} размещён в {zone_name}.")
            return True
        return False

    def finish_placement(self) -> bool:
        """Finish placement phase for current player."""
        if self.phase != GamePhase.SETUP:
            return False

        if self.current_player == 1:
            if not self.board.get_all_cards(player=1):
                self.log("Разместите хотя бы одну карту!")
                return False
            self.current_player = 2
            self.log("Игрок 2, расставьте существ!")
        else:
            if not self.board.get_all_cards(player=2):
                self.log("Разместите хотя бы одну карту!")
                return False
            # Both players done - start game
            self.phase = GamePhase.MAIN
            self.turn_number = 1
            self.current_player = 1
            self.start_turn()

        return True

    def start_turn(self):
        """Start a new turn for current player."""
        # Reset armor for ALL cards (both players) at start of each turn
        for card in self.board.get_all_cards():
            card.reset_armor()
            # Reset formation armor based on current formation state
            if card.in_formation:
                bonus = self._get_formation_armor_bonus(card)
                card.formation_armor_remaining = bonus
                card.formation_armor_max = bonus
            else:
                card.formation_armor_remaining = 0
                card.formation_armor_max = 0

        # Reset all cards for current player
        for card in self.board.get_all_cards(self.current_player):
            card.reset_for_turn()

        # Note: UI state (selection, valid moves/attacks) is managed client-side
        self.last_combat = None
        self.cancel_ability()

        self.log(f"Ход {self.turn_number}: Игрок {self.current_player}")
        self.emit_event(evt_turn_started(self.current_player, self.turn_number))

        # Process Valhalla abilities from graveyard
        self._process_valhalla_triggers()

        # Process triggered abilities (ON_TURN_START)
        self._process_turn_start_triggers()

        # Check for forced attacks (must_attack_tapped)
        self._update_forced_attackers()
        if self.has_forced_attack:
            # Log forced attack requirement
            for card_id in self.forced_attackers:
                card = self.get_card_by_id(card_id)
                if card:
                    self.log(f"{card.name} должен атаковать закрытого врага!")

    # =========================================================================
    # ABILITY SYSTEM
    # =========================================================================

    def _process_valhalla_triggers(self):
        """Process Valhalla abilities from graveyard - queues them for target selection."""
        graveyard = self.board.graveyard_p1 if self.current_player == 1 else self.board.graveyard_p2

        # Queue all Valhalla triggers (using IDs for serializability)
        self.pending_valhalla = []
        for card in graveyard:
            # Only trigger if killed by enemy attack
            if not card.killed_by_enemy:
                continue

            # Check for Valhalla abilities
            for ability_id in card.stats.ability_ids:
                ability = get_ability(ability_id)
                if ability and ability.trigger == AbilityTrigger.VALHALLA:
                    self.pending_valhalla.append((card.id, ability_id))

        # Start processing first Valhalla if any
        self._process_next_valhalla()

    def _process_next_valhalla(self):
        """Process the next Valhalla trigger in queue."""
        if not self.pending_valhalla:
            # Clear any Valhalla interaction
            if self.interaction and self.interaction.kind == InteractionKind.SELECT_VALHALLA_TARGET:
                self.interaction = None
            return

        # Get next Valhalla (now stored as IDs)
        dead_card_id, ability_id = self.pending_valhalla.pop(0)
        dead_card = self.get_card_by_id(dead_card_id)
        ability = get_ability(ability_id)

        if not dead_card or not ability:
            self._process_next_valhalla()  # Skip invalid entries
            return

        # Get valid targets (living allies)
        allies = self.board.get_all_cards(dead_card.player)
        allies = [c for c in allies if c.is_alive and c.position is not None]

        if not allies:
            self.log(f"Вальхалла {dead_card.name}: нет союзников!")
            self._process_next_valhalla()  # Process next one
            return

        # Enter Valhalla target selection using unified Interaction (data-only)
        self.interaction = interaction_valhalla(
            source_id=dead_card.id,
            valid_positions=tuple(c.position for c in allies),
            valid_card_ids=tuple(c.id for c in allies),
            acting_player=dead_card.player,
        )
        # Store ability_id in context for network serialization
        self.interaction.context['ability_id'] = ability_id
        self.log(f"Вальхалла {dead_card.name}: выберите существо")

    def select_valhalla_target(self, pos: int) -> bool:
        """Player selects target for Valhalla ability."""
        if not self.awaiting_valhalla:
            return False

        if not self.interaction.can_select_position(pos):
            return False

        dead_card = self.get_card_by_id(self.interaction.actor_id)
        ability_id = self.interaction.context.get('ability_id')
        ability = get_ability(ability_id) if ability_id else None
        target = self.board.get_card(pos)

        if not target or not ability or not dead_card:
            return False

        # Apply Valhalla effect
        if ability.id == "valhalla_ova":
            target.temp_dice_bonus += ability.dice_bonus_attack
            self.log(f"  -> {target.name} получил ОвА+{ability.dice_bonus_attack}")
        elif ability.id == "valhalla_strike":
            target.temp_attack_bonus += ability.damage_bonus
            self.log(f"  -> {target.name} получил +{ability.damage_bonus} к удару")

        # Clear current and process next
        self.interaction = None
        self._process_next_valhalla()

        return True

    @property
    def awaiting_valhalla(self) -> bool:
        """Check if waiting for Valhalla target selection."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.SELECT_VALHALLA_TARGET

    def _process_turn_start_triggers(self):
        """Process all ON_TURN_START triggered abilities."""
        ctx = {}  # No extra context for turn start
        for card in self.board.get_all_cards(self.current_player):
            for ability_id in card.stats.ability_ids:
                ability = get_ability(ability_id)
                if ability and ability.ability_type == AbilityType.TRIGGERED:
                    if ability.trigger == AbilityTrigger.ON_TURN_START:
                        # Try registered trigger handler first
                        handler = get_trigger_handler(ability_id)
                        if handler:
                            handler(self, card, ability, ctx)
                        else:
                            # Fallback for unregistered triggers
                            self._execute_triggered_ability(card, ability)

    def _get_card_row(self, card: Card) -> int:
        """Get the row number (0-5) for a card's position."""
        if card.position is None:
            return -1
        return card.position // 5

    def _is_in_own_row(self, card: Card, row_num: int) -> bool:
        """Check if card is in a specific row (numbered from middle).
        row_num: 1 = first row (closest to middle), 2 = second, 3 = third (back line)

        Board layout:
        Row 5 = P2 third row (back)
        Row 4 = P2 second row
        Row 3 = P2 first row (front)
        --- middle line ---
        Row 2 = P1 first row (front)
        Row 1 = P1 second row
        Row 0 = P1 third row (back)
        """
        if card.position is None:
            return False
        row = self._get_card_row(card)
        if card.player == 1:
            # Player 1: row 2 is first (front), row 0 is third (back)
            return row == (3 - row_num)
        else:
            # Player 2: row 3 is first (front), row 5 is third (back)
            return row == (2 + row_num)

    def _execute_triggered_ability(self, card: Card, ability: Ability):
        """Execute a triggered ability automatically (fallback for unregistered triggers).

        Most triggers are now handled via registered handlers in ability_handlers.py.
        This method handles any remaining generic cases.
        """
        # Generic heal-based triggers (fallback)
        if ability.heal_amount > 0 and card.curr_life < card.life:
            healed = card.heal(ability.heal_amount)
            if healed > 0:
                self.log(f"{card.name}: {ability.name} (+{healed} HP)")
                self.emit_heal(card.position, healed, card_id=card.id, source_id=card.id)

    def get_usable_abilities(self, card: Card) -> List[Ability]:
        """Get list of active abilities the card can use right now."""
        usable = []

        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if not ability or ability.ability_type != AbilityType.ACTIVE:
                continue

            # Check if instant ability during priority phase
            if ability.is_instant and self.priority_phase:
                # Instant abilities only usable by priority player's untapped cards
                if card.player == self.priority_player and not card.tapped:
                    if card.can_use_ability(ability_id):
                        usable.append(ability)
            else:
                # Normal abilities - only current player's can_act cards
                if card.can_act and card.player == self.current_player:
                    if card.can_use_ability(ability_id):
                        usable.append(ability)

        return usable

    def get_ability_display_text(self, card: Card, ability: Ability) -> str:
        """Get dynamic display text for an ability with current values."""
        # Lunge attack - fixed damage
        if ability.id.startswith("lunge"):
            dmg = ability.damage_amount if ability.damage_amount > 0 else 1
            return f"Удар через ряд {dmg}"

        # Ranged attacks with custom damage
        if ability.ranged_damage and ability.id != "lunge":
            bonus = card.temp_ranged_bonus
            dmg = ability.ranged_damage
            d0, d1, d2 = dmg[0] + bonus, dmg[1] + bonus, dmg[2] + bonus
            # Use correct ranged type name
            ranged_name = "Метание" if ability.ranged_type == "throw" else "Выстрел"
            return f"{ranged_name} {d0}-{d1}-{d2}"

        # Heal abilities
        if ability.heal_amount > 0:
            return f"{ability.name} +{ability.heal_amount} HP"

        # Magical strike with dice-based damage
        if ability.id == "magical_strike" and ability.magic_damage:
            dmg = ability.magic_damage
            # Show as single value if all tiers are same, otherwise show range
            if dmg[0] == dmg[1] == dmg[2]:
                return f"Магический удар {dmg[0]}"
            else:
                return f"Магический удар {dmg[0]}-{dmg[1]}-{dmg[2]}"

        # Default - just return the name
        return ability.name

    def use_ability(self, card: Card, ability_id: str) -> bool:
        """Start using an ability (may require target selection)."""
        # Clear previous dice display
        self.last_combat = None

        # Block during priority phase - only instant abilities allowed
        if self.priority_phase:
            return False

        # Block abilities during forced attack
        if self.has_forced_attack:
            self.log("Сначала атакуйте закрытого врага!")
            return False

        ability = get_ability(ability_id)
        if not ability or ability.ability_type != AbilityType.ACTIVE:
            return False

        if not card.can_use_ability(ability_id):
            self.log(f"{ability.name} на перезарядке!")
            return False

        # Axe strike: requires counter selection first (can use with 0 counters)
        if ability.id == "axe_strike":
            if card.counters <= 0:
                # No counters - skip selection, go straight to targeting
                targets = self._get_ability_targets(card, ability)
                if not targets:
                    self.log("Нет доступных целей!")
                    return False
                # Enter ability targeting using unified Interaction (data-only)
                self.interaction = interaction_select_target(
                    actor_id=card.id,
                    ability_id=ability.id,
                    valid_positions=tuple(targets),
                    acting_player=card.player,
                )
                self.interaction.context['counters_spent'] = 0
                self.log(f"Выберите цель для {ability.name} (0 фишек)")
                return True
            # Start counter selection mode using unified Interaction
            self.interaction = interaction_select_counters(
                card_id=card.id,
                min_counters=0,
                max_counters=card.counters,
                acting_player=card.player,
            )
            self.interaction.context['ability_id'] = ability_id
            # selected_amount defaults to 0 in Interaction
            self.log(f"Выберите количество фишек (0-{card.counters})")
            return True

        # Self-targeting abilities execute immediately
        if ability.target_type == TargetType.SELF:
            return self._execute_ability(card, ability, card)

        # Abilities that need targets
        if ability.target_type in (TargetType.ENEMY, TargetType.ALLY, TargetType.ANY):
            targets = self._get_ability_targets(card, ability)
            if not targets:
                self.log("Нет доступных целей!")
                return False

            # Enter ability targeting using unified Interaction (data-only)
            self.interaction = interaction_select_target(
                actor_id=card.id,
                ability_id=ability.id,
                valid_positions=tuple(targets),
                acting_player=card.player,
            )
            self.log(f"Выберите цель для {ability.name}")
            return True

        return False

    def _get_ability_targets(self, card: Card, ability: Ability) -> List[int]:
        """Get valid target positions for an ability."""
        if ability.range == 0:
            # Self only
            return [card.position] if card.position is not None else []

        # Get cells in range
        if card.position is None:
            return []

        # Collect base targets based on range and target_type
        base_targets = self._get_base_ability_targets(card, ability)

        # Apply custom targeter if registered
        custom_targeter = get_targeter(ability.id)
        if custom_targeter:
            return custom_targeter(self, card, ability, base_targets)

        return base_targets

    def _get_base_ability_targets(self, card: Card, ability: Ability) -> List[int]:
        """Get base targets filtered by range and target_type (before custom targeting)."""
        targets = []

        # Determine if this is a true ranged ability that can target flyers
        is_true_ranged = ability.ranged_damage is not None

        if ability.range == 1:
            cells = self.board.get_adjacent_cells(card.position, include_diagonals=True)
        else:
            # Range 2+ - all cells within range (respecting min_range)
            # For ranged abilities, min_range uses Chebyshev distance to exclude
            # all 8 adjacent cells (orthogonal + diagonal)
            cells = set()
            for pos in range(30):  # Only ground positions 0-29
                dist = self._get_distance(card.position, pos)
                chebyshev = self._get_chebyshev_distance(card.position, pos)
                # Use Chebyshev for min_range (excludes adjacent+diagonal)
                if dist <= ability.range and chebyshev >= ability.min_range:
                    cells.add(pos)
            cells = list(cells)

        # Filter by target type
        for pos in cells:
            target_card = self.board.get_card(pos)
            if target_card is None:
                continue

            if ability.target_type == TargetType.ENEMY and target_card.player != card.player:
                targets.append(pos)
            elif ability.target_type == TargetType.ALLY and target_card.player == card.player and target_card != card:
                targets.append(pos)
            elif ability.target_type == TargetType.ANY:
                # ANY includes self, allies, and enemies
                targets.append(pos)

        # Check if ability can target flying creatures (explicit flag on ability)
        if ability.can_target_flying:
            for flying_card in self.board.get_flying_cards():
                if flying_card.position is not None and flying_card.position not in targets:
                    if ability.target_type == TargetType.ENEMY and flying_card.player != card.player:
                        targets.append(flying_card.position)
                    elif ability.target_type == TargetType.ALLY and flying_card.player == card.player and flying_card != card:
                        targets.append(flying_card.position)
                    elif ability.target_type == TargetType.ANY:
                        targets.append(flying_card.position)

        return targets

    def _get_distance(self, pos1: int, pos2: int) -> int:
        """Get Manhattan distance between two positions (horizontal + vertical, no diagonal)."""
        col1, row1 = pos1 % 5, pos1 // 5
        col2, row2 = pos2 % 5, pos2 // 5
        return abs(col1 - col2) + abs(row1 - row2)

    def _get_chebyshev_distance(self, pos1: int, pos2: int) -> int:
        """Get Chebyshev distance (max of horizontal/vertical). Used for ranged min_range."""
        col1, row1 = pos1 % 5, pos1 // 5
        col2, row2 = pos2 % 5, pos2 // 5
        return max(abs(col1 - col2), abs(row1 - row2))

    def select_ability_target(self, pos: int) -> bool:
        """Select a target for the pending ability."""
        if not self.awaiting_ability_target:
            return False

        if not self.interaction.can_select_position(pos):
            return False

        target = self.board.get_card(pos)
        if not target:
            return False

        card = self.get_card_by_id(self.interaction.actor_id)
        ability_id = self.interaction.context.get('ability_id')
        ability = get_ability(ability_id) if ability_id else None
        if not card or not ability:
            return False

        result = self._execute_ability(card, ability, target)
        self.cancel_ability()
        return result

    @property
    def awaiting_ability_target(self) -> bool:
        """Check if waiting for ability target selection."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.SELECT_ABILITY_TARGET

    def _execute_ability(self, card: Card, ability: Ability, target: Card) -> bool:
        """Execute an ability on a target."""
        # Check for registered handler first
        handler = get_handler(ability.id)
        if handler:
            return handler(self, card, target, ability)

        # Heal
        if ability.heal_amount > 0:
            # Emit heal arrow (only if targeting another card)
            if card != target:
                self.emit_arrow(card.position, target.position, 'heal')
            healed = target.heal(ability.heal_amount)
            self.log(f"{card.name} использует {ability.name}: {target.name} +{healed} HP")
            self.emit_heal(target.position, healed, card_id=target.id, source_id=card.id)
            self.emit_clear_arrows()

        # Damage (for ranged attacks with ranged_damage)
        if ability.ranged_damage:
            # Use ranged attack with ability's damage values
            return self._ranged_attack(card, target, ability)

        # Generic active ability - tap and cooldown
        if ability.ability_type == AbilityType.ACTIVE and ability.heal_amount > 0:
            card.tap()
            card.put_ability_on_cooldown(ability.id, ability.cooldown)

        return True

    def _has_magic_abilities(self, card: Card) -> bool:
        """Check if card has magical abilities (discharge, spells, etc.)."""
        magic_ability_ids = {"discharge", "magical_strike", "spell"}
        for ability_id in card.stats.ability_ids:
            if ability_id in magic_ability_ids:
                return True
            # Also check if ability name contains magic-related terms
            ability = get_ability(ability_id)
            if ability and ("разряд" in ability.name.lower() or "магия" in ability.name.lower()):
                return True
        return False

    def _get_card_column(self, card: Card) -> int:
        """Get column (0-4) for a card, or -1 if not on ground board."""
        if card.position is None or card.position >= 30:
            return -1
        return card.position % 5

    def _get_attack_dice_bonus(self, card: Card, target: Card = None) -> int:
        """Get dice bonus for attacking (passive abilities + temporary buffs like ОвА)."""
        bonus = card.temp_dice_bonus  # Temporary buff (e.g., from Valhalla)
        bonus += card.defender_buff_dice  # Defender buff (lasts until end of next turn)
        col = self._get_card_column(card)
        # Add passive ability bonuses
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.ability_type == AbilityType.PASSIVE:
                # Add dice_bonus_attack from any passive ability that has it
                if ability.dice_bonus_attack > 0:
                    # Edge column attack only applies on flanks (columns 0 or 4)
                    if ability.id == "edge_column_attack":
                        if col in (0, 4):
                            bonus += ability.dice_bonus_attack
                    else:
                        bonus += ability.dice_bonus_attack
        return bonus

    def _get_defense_dice_bonus(self, card: Card) -> int:
        """Get dice bonus for defending (passive abilities like ОвЗ)."""
        bonus = 0
        col = self._get_card_column(card)
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.ability_type == AbilityType.PASSIVE:
                # Add dice_bonus_defense from any passive ability that has it
                if ability.dice_bonus_defense > 0:
                    bonus += ability.dice_bonus_defense
                # Center column defense: +1 ОвЗ in center (column 2)
                elif ability.id == "center_column_defense" and col == 2:
                    bonus += 1
                # Formation bonus: add dice bonus when in formation
                elif ability.is_formation and card.in_formation and ability.formation_dice_bonus > 0:
                    # Check rarity requirements
                    if ability.requires_elite_ally:
                        if self._has_elite_ally_in_formation(card):
                            bonus += ability.formation_dice_bonus
                    elif ability.requires_common_ally:
                        if self._has_common_ally_in_formation(card):
                            bonus += ability.formation_dice_bonus
                    else:
                        # No rarity requirement
                        bonus += ability.formation_dice_bonus
        return bonus

    def _get_formation_armor_bonus(self, card: Card) -> int:
        """Get armor bonus from formation abilities."""
        bonus = 0
        if not card.in_formation:
            return 0
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.is_formation and ability.formation_armor_bonus > 0:
                # Check rarity requirements
                if ability.requires_elite_ally:
                    if self._has_elite_ally_in_formation(card):
                        bonus += ability.formation_armor_bonus
                elif ability.requires_common_ally:
                    if self._has_common_ally_in_formation(card):
                        bonus += ability.formation_armor_bonus
                else:
                    # No rarity requirement
                    bonus += ability.formation_armor_bonus
        return bonus

    def _is_diagonal_attack(self, attacker: Card, defender: Card) -> bool:
        """Check if attack is diagonal."""
        if attacker.position is None or defender.position is None:
            return False
        atk_col, atk_row = attacker.position % 5, attacker.position // 5
        def_col, def_row = defender.position % 5, defender.position // 5
        return atk_col != def_col and atk_row != def_row

    def _get_opposite_position(self, card: Card) -> Optional[int]:
        """Get position directly opposite (same column, adjacent row toward enemy)."""
        if card.position is None:
            return None
        col = card.position % 5
        row = card.position // 5
        if card.player == 1:
            opp_row = row + 1  # P1 faces up
        else:
            opp_row = row - 1  # P2 faces down
        if 0 <= opp_row <= 5:
            return opp_row * 5 + col
        return None

    def _get_damage_reduction(self, defender: Card, attacker: Card, attack_tier: int = -1) -> int:
        """Get damage reduction for defender vs this attacker.

        Args:
            defender: Card receiving damage
            attacker: Card dealing damage
            attack_tier: 0=weak, 1=medium, 2=strong, -1=unknown (skip tier-based reductions)
        """
        from .constants import Element
        reduction = 0
        is_diagonal = self._is_diagonal_attack(attacker, defender)
        col = self._get_card_column(defender)

        for ability_id in defender.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.ability_type == AbilityType.PASSIVE:
                # Center column: -1 incoming weak damage
                if ability.id == "center_column_defense" and col == 2 and attack_tier == 0:
                    reduction += 1
                elif ability.damage_reduction > 0:
                    # Diagonal defense only works on diagonal attacks
                    if ability.id == "diagonal_defense":
                        if is_diagonal:
                            reduction += ability.damage_reduction
                    # Steppe defense only works vs steppe creatures
                    elif ability.id == "steppe_defense":
                        if attacker.stats.element == Element.PLAINS:
                            reduction += ability.damage_reduction
                    # Cost threshold check (0 = applies to all)
                    elif ability.cost_threshold == 0 or attacker.stats.cost <= ability.cost_threshold:
                        reduction += ability.damage_reduction
        return reduction

    def _get_element_damage_bonus(self, attacker: Card, defender: Card) -> int:
        """Get bonus damage from abilities that target specific elements."""
        from .constants import Element
        bonus = 0
        for ability_id in attacker.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.bonus_damage_vs_element > 0 and ability.target_element:
                # Check if defender's element matches
                target_elem = getattr(Element, ability.target_element, None)
                if target_elem and defender.stats.element == target_elem:
                    bonus += ability.bonus_damage_vs_element
        return bonus

    def _has_defensive_ability(self, card: Card) -> bool:
        """Check if card has OVA, OVZ, or armor abilities that are currently active."""
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability:
                # Check for OVA (attack dice bonus) - permanent abilities
                if ability.dice_bonus_attack > 0:
                    return True
                # Check for OVZ (defense dice bonus) - permanent abilities
                if ability.dice_bonus_defense > 0:
                    return True
                # Check for formation-based OVZ - only counts if card is in formation
                if ability.formation_dice_bonus > 0 and card.in_formation:
                    return True
        # Check for armor
        if card.stats.armor > 0:
            return True
        # Check for formation armor (only if in formation)
        if card.in_formation and card.formation_armor_max > 0:
            return True
        return False

    def _get_ranged_defensive_bonus(self, attacker: Card, target: Card, ability: Ability) -> int:
        """Get bonus ranged damage vs cards with OVA/OVZ/armor."""
        if ability and ability.bonus_ranged_vs_defensive > 0:
            if self._has_defensive_ability(target):
                return ability.bonus_ranged_vs_defensive
        return 0

    def _has_direct_attack(self, card: Card) -> bool:
        """Check if card has permanent direct attack (cannot be redirected)."""
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.ability_type == AbilityType.PASSIVE:
                if ability.grants_direct:
                    return True
        return False

    def _process_defender_triggers(self, defender: Card, attacker: Card = None):
        """Process ON_DEFEND triggered abilities when card becomes a defender."""
        ctx = {'attacker': attacker}
        for ability_id in defender.stats.ability_ids:
            ability = get_ability(ability_id)
            if not ability or ability.trigger != AbilityTrigger.ON_DEFEND:
                continue

            # Try registered trigger handler first
            handler = get_trigger_handler(ability_id)
            if handler:
                handler(self, defender, ability, ctx)

    def _process_counter_shot(self, attacker: Card, original_target: Card):
        """Process counter_shot ability - enter targeting mode for ranged shot."""
        if "counter_shot" not in attacker.stats.ability_ids:
            return

        if attacker.position is None:
            return

        # Get valid targets (any creature at Chebyshev distance >= 2, i.e. not adjacent/diagonal)
        valid_targets = []
        for card in self.board.get_all_cards():
            if not card.is_alive or card.position is None or card == attacker:
                continue
            # Ranged shot cannot target adjacent cells (Chebyshev distance < 2)
            if self._get_chebyshev_distance(attacker.position, card.position) >= 2:
                valid_targets.append(card.position)

        # Also include flying creatures (ranged can always target flyers)
        for flying_card in self.board.get_flying_cards():
            if flying_card.is_alive and flying_card.position not in valid_targets:
                valid_targets.append(flying_card.position)

        if not valid_targets:
            return

        # Enter counter shot targeting mode using unified Interaction (data-only)
        self.interaction = interaction_counter_shot(
            shooter_id=attacker.id,
            valid_positions=tuple(valid_targets),
            acting_player=attacker.player,
        )
        self.log(f"{attacker.name}: выберите цель для выстрела")

    def select_counter_shot_target(self, pos: int) -> bool:
        """Player selects target for counter shot."""
        if not self.awaiting_counter_shot:
            return False

        if not self.interaction.can_select_position(pos):
            return False

        attacker = self.get_card_by_id(self.interaction.actor_id)
        target = self.board.get_card(pos)

        if not target:
            return False

        self.emit_arrow(attacker.position, target.position, 'shot')

        # Check shot immunity
        if "shot_immune" in target.stats.ability_ids:
            self.log(f"{target.name} защищён от выстрелов!")
            self.emit_clear_arrows()
        else:
            ability = get_ability("counter_shot")
            damage = ability.damage_amount if ability else 2
            dealt, _ = self._deal_damage(target, damage)
            if dealt > 0:
                self.log(f"  -> {attacker.name} выстрел: {target.name} -{dealt} HP")
            self._handle_death(target, attacker)
            self._check_winner()

        self.interaction = None
        return True

    @property
    def awaiting_counter_shot(self) -> bool:
        """Check if waiting for counter shot target selection."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.SELECT_COUNTER_SHOT

    @property
    def awaiting_movement_shot(self) -> bool:
        """Check if waiting for movement shot target selection."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.SELECT_MOVEMENT_SHOT

    def _process_movement_shot(self, card: Card):
        """Process movement_shot ability - check for adjacent expensive ally and offer shot."""
        if "movement_shot" not in card.stats.ability_ids:
            return
        if card.position is None or card.tapped:
            return

        # Check adjacent cells for ally with cost >= 7 (orthogonal only)
        has_expensive_ally = False
        for adj_pos in self.board.get_adjacent_cells(card.position, include_diagonals=False):
            adj_card = self.board.get_card(adj_pos)
            if adj_card and adj_card.player == card.player and adj_card.stats.cost >= 7:
                has_expensive_ally = True
                break

        if not has_expensive_ally:
            return

        # Get valid targets (range 3, not adjacent/diagonal, includes flyers)
        valid_targets = []

        # Ground enemy targets within Manhattan range 3, but Chebyshev >= 2 (not adjacent)
        for target_card in self.board.get_all_cards(include_flying=False):
            if not target_card.is_alive or target_card.position is None or target_card == card:
                continue
            # Only target enemies
            if target_card.player == card.player:
                continue
            manhattan = self._get_distance(card.position, target_card.position)
            chebyshev = self._get_chebyshev_distance(card.position, target_card.position)
            if manhattan <= 3 and chebyshev >= 2:
                valid_targets.append(target_card.position)

        # Flying enemy targets (ranged attacks can always target flyers)
        for target_card in self.board.get_flying_cards():
            if target_card.is_alive and target_card.player != card.player and target_card.position not in valid_targets:
                valid_targets.append(target_card.position)

        if not valid_targets:
            return

        # Enter movement shot targeting mode using unified Interaction (data-only, optional shot)
        self.interaction = interaction_movement_shot(
            shooter_id=card.id,
            valid_positions=tuple(valid_targets),
            acting_player=card.player,
        )
        self.log(f"{card.name}: можно выстрелить (необязательно)")

    def select_movement_shot_target(self, pos: int) -> bool:
        """Player selects target for movement shot."""
        if not self.awaiting_movement_shot:
            return False

        if not self.interaction.can_select_position(pos):
            return False

        shooter = self.get_card_by_id(self.interaction.actor_id)
        target = self.board.get_card(pos)

        if not target or not shooter:
            return False

        self.emit_arrow(shooter.position, target.position, 'shot')

        # Check shot immunity
        if "shot_immune" in target.stats.ability_ids:
            self.log(f"{target.name} защищён от выстрелов!")
            self.emit_clear_arrows()
        else:
            dealt, _ = self._deal_damage(target, 1)
            if dealt > 0:
                self.log(f"  -> {shooter.name} выстрел: {target.name} -{dealt} HP")
            self._handle_death(target, shooter)
            self._check_winner()

        self.interaction = None
        return True

    def skip_movement_shot(self):
        """Skip the movement shot opportunity."""
        if self.awaiting_movement_shot:
            shooter = self.get_card_by_id(self.interaction.actor_id)
            if shooter:
                self.log(f"{shooter.name}: выстрел пропущен")
            self.interaction = None

    def _process_heal_on_attack(self, attacker: Card, target: Card):
        """Process heal_on_attack ability - prompt for optional heal."""
        if "heal_on_attack" not in attacker.stats.ability_ids:
            return
        if not attacker.is_alive or attacker.position is None:
            return

        # Find the card directly in front of attacker
        # Player 1 moves toward higher rows (+5), Player 2 toward lower rows (-5)
        front_offset = 5 if attacker.player == 1 else -5
        front_pos = attacker.position + front_offset

        # Check bounds
        if front_pos < 0 or front_pos >= 30:
            return

        front_card = self.board.get_card(front_pos)
        if not front_card:
            return  # No card in front, no heal

        # Heal amount = front card's medium damage value
        heal_amount = front_card.stats.attack[1]
        if heal_amount <= 0:
            return
        # Only offer heal if attacker is damaged
        if attacker.curr_life >= attacker.life:
            return
        # Enter heal confirmation mode using unified Interaction (data-only)
        self.interaction = interaction_confirm_heal(
            healer_id=attacker.id,
            target_id=front_card.id,
            heal_amount=heal_amount,
            acting_player=attacker.player,
        )
        self.log(f"{attacker.name}: лечиться на {heal_amount}? (напротив: {front_card.name})")

    def confirm_heal_on_attack(self, accept: bool) -> bool:
        """Player confirms or declines optional heal."""
        if not self.awaiting_heal_confirm:
            return False
        attacker = self.get_card_by_id(self.interaction.actor_id)
        heal_amount = self.interaction.context.get('heal_amount', 0)
        if not attacker:
            return False
        if accept and attacker.is_alive:
            healed = attacker.heal(heal_amount)
            if healed > 0:
                self.emit_heal(attacker.position, healed, card_id=attacker.id, source_id=attacker.id)
                self.log(f"  -> {attacker.name} +{healed} HP")
        else:
            self.log(f"  -> {attacker.name} отказался от лечения")
        self.interaction = None
        return True

    @property
    def awaiting_heal_confirm(self) -> bool:
        """Check if waiting for heal confirmation."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.CONFIRM_HEAL

    def _process_hellish_stench(self, attacker: Card, target: Card, was_target_tapped: bool, attack_hit: bool):
        """Process hellish_stench ability - target must tap or take 2 damage.

        Triggers if the attack hit (didn't miss), even if damage was reduced to 0.
        """
        if "hellish_stench" not in attacker.stats.ability_ids:
            return
        # Only triggers when attacking an untapped (open) creature
        if was_target_tapped:
            return
        # Only triggers if the attack hit (not a miss)
        if not attack_hit:
            return
        if not target.is_alive or target.position is None:
            return
        # If target is already tapped (from combat or other effect), no choice needed
        if target.tapped:
            return

        ability = get_ability("hellish_stench")
        damage = ability.damage_amount if ability else 2

        # Enter stench choice mode using unified Interaction (data-only)
        self.interaction = interaction_choose_stench(
            target_id=target.id,
            damage_amount=damage,
            acting_player=target.player,
        )
        self.interaction.context['attacker_id'] = attacker.id
        self.log(f"{attacker.name}: Адское зловоние! {target.name} закрывается или получает {damage} урона")

    def resolve_stench_choice(self, tap: bool) -> bool:
        """Target's controller chooses: tap or take damage."""
        if not self.awaiting_stench_choice:
            return False

        attacker = self.get_card_by_id(self.interaction.context.get('attacker_id'))
        target = self.get_card_by_id(self.interaction.target_id)
        damage = self.interaction.context.get('damage_amount', 2)

        if not target:
            self.interaction = None
            return False

        if tap:
            # Target chooses to tap
            target.tap()
            self.log(f"  -> {target.name} закрывается от зловония")
        else:
            # Target chooses to take damage
            dealt, _ = self._deal_damage(target, damage)
            self.log(f"  -> {target.name} получил {dealt} урона от зловония")
            self._handle_death(target, attacker)
            self._check_winner()

        self.interaction = None
        return True

    @property
    def awaiting_stench_choice(self) -> bool:
        """Check if waiting for stench choice."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.CHOOSE_STENCH

    @property
    def awaiting_exchange_choice(self) -> bool:
        """Check if waiting for exchange choice."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.CHOOSE_EXCHANGE

    @property
    def awaiting_defender(self) -> bool:
        """Check if waiting for defender selection."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.SELECT_DEFENDER

    @property
    def has_blocking_interaction(self) -> bool:
        """Check if any popup/decision is blocking normal actions."""
        return (self.awaiting_counter_selection or self.awaiting_heal_confirm or
                self.awaiting_stench_choice or self.awaiting_exchange_choice or
                self.awaiting_defender or self.awaiting_valhalla or
                self.awaiting_counter_shot or self.awaiting_movement_shot or
                self.awaiting_ability_target or self.priority_phase)

    def _lunge_attack(self, attacker: Card, target: Card, ability: Ability) -> bool:
        """Execute a lunge attack (fixed damage, no counter)."""
        self.emit_arrow(attacker.position, target.position, 'attack')
        self.log(f"{attacker.name} бьёт через ряд")

        damage = ability.damage_amount if ability.damage_amount > 0 else 1
        dealt, webbed = self._deal_damage(target, damage)

        self.last_combat = CombatResult(
            attacker_roll=0, defender_roll=0,
            attacker_damage_dealt=dealt, defender_damage_dealt=0,
            attacker_name=attacker.name, defender_name=target.name
        )

        if not webbed:
            self.emit_clear_arrows()
            self.log(f"  -> {target.name} получил {dealt} урона")
            # Check for lunge_front_buff ability
            if attacker.has_ability("lunge_front_buff"):
                self._apply_lunge_front_buff(attacker)
            self._process_heal_on_attack(attacker, target)

        self._handle_death(target, attacker)
        attacker.tap()
        self._check_winner()
        return True

    def _apply_lunge_front_buff(self, attacker: Card):
        """Apply +1 dice roll buff (ОвА) to allied creature directly in front of attacker."""
        if attacker.position is None:
            return

        col = attacker.position % 5
        row = attacker.position // 5

        # "In front" means toward the enemy side
        if attacker.player == 1:
            front_row = row + 1
        else:
            front_row = row - 1

        if front_row < 0 or front_row > 5:
            return

        front_pos = front_row * 5 + col
        front_card = self.board.get_card(front_pos)

        if front_card and front_card.player == attacker.player:
            front_card.temp_dice_bonus += 1
            self.log(f"  -> {front_card.name} получил ОвА (+1 к броску)")

    def _ranged_attack(self, attacker: Card, target: Card, ability: Ability = None) -> bool:
        """Execute a ranged attack (no defender intercept, no counter)."""
        # Determine ranged type (shot or throw)
        ranged_type = ability.ranged_type if ability else "shot"
        arrow_type = 'throw' if ranged_type == "throw" else 'shot'
        self.emit_arrow(attacker.position, target.position, arrow_type)

        # Check shot immunity (only applies to shots, not throws)
        if ranged_type == "shot" and "shot_immune" in target.stats.ability_ids:
            self.log(f"{target.name} защищён от выстрелов!")
            self.emit_clear_arrows()
            attacker.tap()
            return True

        atk_roll = self.roll_dice()

        # Create dice context for priority phase (luck can modify)
        dice_context = DiceContext(
            type='ranged',
            attacker_id=attacker.id,
            atk_roll=atk_roll,
            target_id=target.id,
            ability_id=ability.id,
            ranged_type=ranged_type,
        )

        # Check if we should enter priority phase
        if self._enter_priority_phase(dice_context):
            # Priority phase started - ranged attack will continue after priority resolves
            return True

        # No priority phase needed - continue immediately
        return self._finish_ranged_attack(dice_context)

    def _finish_ranged_attack(self, dice_context: DiceContext) -> bool:
        """Finish ranged attack after priority phase (or immediately if no priority)."""
        attacker = self.board.get_card_by_id(dice_context.attacker_id)
        target = self.board.get_card_by_id(dice_context.target_id)
        if not attacker or not target:
            return False
        ability = get_ability(dice_context.ability_id) if dice_context.ability_id else None
        ranged_type = dice_context.ranged_type

        # Apply modifiers from luck
        atk_roll = dice_context.atk_roll + dice_context.atk_modifier
        # Clamp roll to 1-6 range after modifiers
        atk_roll = max(1, min(6, atk_roll))

        tier = self._get_attack_tier(atk_roll)
        tier_names = ["слабый", "средний", "сильный"]

        if ability and ability.ranged_damage:
            base_damage = ability.ranged_damage[tier]
        else:
            base_damage = attacker.get_effective_attack()[tier]

        # Add bonus vs defensive abilities (OVA/OVZ/armor)
        defensive_bonus = self._get_ranged_defensive_bonus(attacker, target, ability)

        damage = base_damage + attacker.temp_ranged_bonus + defensive_bonus
        dealt, webbed = self._deal_damage(target, damage)

        self.last_combat = CombatResult(
            attacker_roll=atk_roll, defender_roll=0,
            attacker_damage_dealt=dealt, defender_damage_dealt=0,
            attacker_name=attacker.name, defender_name=target.name
        )

        total_bonus = attacker.temp_ranged_bonus + defensive_bonus
        bonus_str = f" (+{total_bonus})" if total_bonus > 0 else ""
        action_verb = "метает в" if ranged_type == "throw" else "стреляет в"
        self.log(f"{attacker.name} {action_verb} {target.name} [{atk_roll}] - {tier_names[tier]}{bonus_str}")
        if not webbed:
            self.emit_clear_arrows()
            self.log(f"  -> {target.name} получил {dealt} урона")

        self._handle_death(target, attacker)
        attacker.tap()
        self._check_winner()
        return True

    def _magic_attack(self, attacker: Card, target: Card, ability_id: str, counters_spent: int = 0) -> bool:
        """Execute a magic attack with dice roll. Generic handler for all magic abilities.

        Args:
            attacker: The attacking card
            target: The target card
            ability_id: ID of the ability being used
            counters_spent: Number of counters to spend (for counter-based abilities)
        """
        from .abilities import get_ability

        self.emit_arrow(attacker.position, target.position, 'magic')
        ability = get_ability(ability_id)

        # Check magic immunity first - skip dice if immune
        if "magic_immune" in target.stats.ability_ids:
            self.log(f"{attacker.name} магический удар!")
            self.log(f"  -> {target.name}: защита от магии!")
            self.emit_clear_arrows()
            # Still spend counters if applicable
            if counters_spent > 0:
                attacker.counters -= counters_spent
            self.last_combat = CombatResult(0, 0, 0, 0, attacker_name=attacker.name, defender_name=target.name)
            attacker.tap()
            self._check_winner()
            return True

        # Roll dice for damage tier
        atk_roll = self.roll_dice()

        # Create dice context for priority phase (luck can modify)
        dice_context = DiceContext(
            type='magic',
            attacker_id=attacker.id,
            atk_roll=atk_roll,
            target_id=target.id,
            ability_id=ability_id,
            extra={'counters_spent': counters_spent} if counters_spent > 0 else None,
        )

        # Check if we should enter priority phase
        if self._enter_priority_phase(dice_context):
            return True

        # No priority phase needed - continue immediately
        return self._finish_magic_attack(dice_context)

    def _finish_magic_attack(self, dice_context: DiceContext) -> bool:
        """Finish magic attack after priority phase. Generic handler for all magic abilities."""
        from .abilities import get_ability

        attacker = self.board.get_card_by_id(dice_context.attacker_id)
        target = self.board.get_card_by_id(dice_context.target_id)
        if not attacker or not target:
            return False

        ability = get_ability(dice_context.ability_id) if dice_context.ability_id else None
        counters_spent = dice_context.extra.get('counters_spent', 0) if dice_context.extra else 0

        # Apply modifiers from luck
        atk_roll = dice_context.atk_roll + dice_context.atk_modifier
        atk_roll = max(1, min(6, atk_roll))

        tier = self._get_attack_tier(atk_roll)
        tier_names = ["слабый", "средний", "сильный"]

        # Calculate damage from ability's magic_damage tuple
        if ability and ability.magic_damage:
            base_damage = ability.magic_damage[tier]
        else:
            base_damage = 2  # Fallback

        # Add counter bonus if ability uses counters
        counter_bonus = 0
        if ability and ability.magic_counter_bonus > 0 and counters_spent > 0:
            counter_bonus = ability.magic_counter_bonus * counters_spent
            attacker.counters -= counters_spent

        total_damage = base_damage + counter_bonus

        # Log with appropriate format
        if counter_bonus > 0:
            self.log(f"{attacker.name} маг. удар [{atk_roll}] - {tier_names[tier]}: {base_damage}+{counters_spent} = {total_damage}")
        else:
            self.log(f"{attacker.name} магический удар [{atk_roll}] - {tier_names[tier]}")

        dealt, webbed = self._deal_damage(target, total_damage, is_magical=True)
        if not webbed:
            self.emit_clear_arrows()
            self.log(f"  -> {target.name}: -{dealt} HP (магия)")

        self.last_combat = CombatResult(
            attacker_roll=atk_roll, defender_roll=0,
            attacker_damage_dealt=dealt, defender_damage_dealt=0,
            attacker_name=attacker.name, defender_name=target.name
        )
        self._handle_death(target, attacker)
        attacker.tap()
        self._check_winner()
        return True

    def cancel_ability(self):
        """Cancel pending ability targeting."""
        if self.awaiting_ability_target or self.awaiting_counter_selection:
            self.interaction = None

    @property
    def awaiting_counter_selection(self) -> bool:
        """Check if waiting for counter selection."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.SELECT_COUNTERS

    @property
    def counter_selection_card(self) -> Optional[Card]:
        """Get the card for counter selection (derived from interaction)."""
        if self.awaiting_counter_selection and self.interaction:
            return self.get_card_by_id(self.interaction.actor_id)
        return None

    def set_counter_selection(self, count: int):
        """Set the number of counters to spend."""
        if not self.awaiting_counter_selection or not self.interaction:
            return
        card = self.get_card_by_id(self.interaction.actor_id)
        if not card:
            return
        max_counters = card.counters
        self.interaction.selected_amount = max(0, min(count, max_counters))

    def confirm_counter_selection(self) -> bool:
        """Confirm counter selection and proceed to target selection."""
        if not self.awaiting_counter_selection or not self.interaction:
            return False

        card = self.get_card_by_id(self.interaction.actor_id)
        ability_id = self.interaction.context.get('ability_id')
        ability = get_ability(ability_id) if ability_id else None
        counters_spent = self.interaction.selected_amount

        if not card or not ability:
            self.cancel_ability()
            return False

        # Proceed to target selection
        targets = self._get_ability_targets(card, ability)
        if not targets:
            self.log("Нет доступных целей!")
            self.cancel_ability()
            return False

        # Enter ability targeting, passing counters_spent via context
        self.interaction = interaction_select_target(
            actor_id=card.id,
            ability_id=ability.id,
            valid_positions=tuple(targets),
            acting_player=card.player,
        )
        self.interaction.context['counters_spent'] = counters_spent
        self.log(f"Выберите цель для {ability.name} ({counters_spent} фишек)")
        return True

    # =========================================================================
    # PRIORITY SYSTEM (Instant Abilities - Внезапные действия)
    # =========================================================================

    def _get_instant_cards(self, player: int, debug: bool = False) -> List[Tuple[Card, Ability]]:
        """Get all cards with instant abilities for a player (internal, no state check)."""
        # Get card IDs already on the stack (can't use instant twice)
        card_ids_on_stack = {instant.card_id for instant in self.instant_stack}

        # Get attacker and defender IDs - they can't use instants on their own combat
        # Note: target of ranged attack CAN use instants (they're not actively attacking/defending)
        combat_card_ids = set()
        if self.pending_dice_roll:
            dice = self.pending_dice_roll
            if dice.attacker_id:
                combat_card_ids.add(dice.attacker_id)
            if dice.defender_id:
                combat_card_ids.add(dice.defender_id)
            # target_id is NOT excluded - ranged targets can react with instants

        result = []
        for card in self.board.get_all_cards(player):
            # Check for luck ability
            if "luck" not in card.stats.ability_ids:
                continue
            # Debug: log why card is excluded
            if not card.is_alive:
                if debug:
                    self.log(f"  [{card.name}: мёртв]")
                continue
            if card.tapped:
                if debug:
                    self.log(f"  [{card.name}: закрыт]")
                continue
            if card.webbed:
                if debug:
                    self.log(f"  [{card.name}: опутан]")
                continue
            if card.id in card_ids_on_stack:
                if debug:
                    self.log(f"  [{card.name}: уже на стеке]")
                continue
            if card.id in combat_card_ids:
                if debug:
                    self.log(f"  [{card.name}: участвует в бою]")
                continue
            for ability_id in card.stats.ability_ids:
                ability = get_ability(ability_id)
                if ability and ability.is_instant and ability.trigger == AbilityTrigger.ON_DICE_ROLL:
                    if card.can_use_ability(ability_id):
                        result.append((card, ability))
        return result

    def get_legal_instants(self, player: int) -> List[Tuple[Card, Ability]]:
        """Get all cards with legal instant abilities for a player during priority."""
        if not self.priority_phase or not self.pending_dice_roll:
            return []
        return self._get_instant_cards(player)

    def _enter_priority_phase(self, dice_context: dict):
        """Enter priority phase after a dice roll."""
        # Store the dice roll context FIRST so _get_instant_cards can exclude attacker/defender
        self.pending_dice_roll = dice_context

        # Check if any player has legal instant abilities
        p1_instants = self._get_instant_cards(1)
        p2_instants = self._get_instant_cards(2)

        if not p1_instants and not p2_instants:
            # No instants available - skip priority phase
            # Log why each luck card is excluded (with debug=True) BEFORE clearing pending_dice_roll
            found_any = False
            for card in self.board.get_all_cards():
                if card.has_ability("luck"):
                    found_any = True
                    break
            if found_any:
                self._get_instant_cards(1, debug=True)
                self._get_instant_cards(2, debug=True)
            self.pending_dice_roll = None  # Clear it since we're not entering priority
            return False

        # Enter priority phase
        self.priority_phase = True
        self.priority_passed = []
        self.instant_stack = []

        # Find who has instants and give them priority directly
        current_has_instants = p1_instants if self.current_player == 1 else p2_instants
        opponent = 2 if self.current_player == 1 else 1
        opponent_has_instants = p2_instants if self.current_player == 1 else p1_instants

        if current_has_instants:
            # Current player has instants - they get priority
            self.priority_player = self.current_player
        elif opponent_has_instants:
            # Only opponent has instants - they get priority, current auto-passes
            self.priority_passed.append(self.current_player)
            self.priority_player = opponent

        self.log(f"Приоритет: Игрок {self.priority_player}")
        return True

    def pass_priority(self) -> bool:
        """Current priority player passes. Returns True if priority resolved."""
        if not self.priority_phase:
            return False

        # Add current player to passed list
        if self.priority_player not in self.priority_passed:
            self.priority_passed.append(self.priority_player)

        # Switch priority to other player
        other_player = 2 if self.priority_player == 1 else 1

        # Check if other player has instants and hasn't passed
        if other_player not in self.priority_passed:
            other_instants = self.get_legal_instants(other_player)
            if other_instants:
                self.priority_player = other_player
                self.log(f"Приоритет: Игрок {self.priority_player}")
                return False
            else:
                # Other player has no instants - auto-pass for them
                self.priority_passed.append(other_player)

        # Both players passed (or no valid responses) - resolve
        self._resolve_priority_stack()
        return True

    def _resolve_priority_stack(self):
        """Resolve all instant abilities on the stack and the original dice roll."""
        # Resolve stack in LIFO order (last in, first out)
        while self.instant_stack:
            instant = self.instant_stack.pop()
            self._apply_instant_effect(instant)

        # Priority phase ends
        self.priority_phase = False
        self.priority_player = 0
        self.priority_passed = []

        # The pending_dice_roll is kept and used by the caller to continue combat

    def _apply_instant_effect(self, instant: StackItem):
        """Apply the effect of a resolved instant ability."""
        card = self.board.get_card_by_id(instant.card_id)
        if not card:
            return

        if instant.ability_id == "luck":
            # Parse option: atk_plus1, atk_minus1, atk_reroll, def_plus1, def_minus1, def_reroll
            target = 'atk' if instant.option.startswith('atk_') else 'def'
            action = instant.option.split('_')[1]  # plus1, minus1, reroll

            dice = self.pending_dice_roll
            if not dice:
                return

            # For ranged/magic attacks, there's only attacker roll (target is 'target', not 'defender')
            is_single_roll = dice.type in ('ranged', 'magic')

            # Ranged/magic attacks only have attacker roll, ignore defender modifications
            if is_single_roll and target == 'def':
                self.log(f"  -> {card.name}: Нет броска защитника для изменения")
                return

            # Check if defender roll is 0 (tapped defender - no roll to modify)
            if target == 'def' and dice.def_roll == 0:
                self.log(f"  -> {card.name}: Защитник закрыт - нет броска для изменения")
                return

            if target == 'atk':
                atk_card = self.board.get_card_by_id(dice.attacker_id)
                target_name = atk_card.name if atk_card else "атакующий"
            else:
                # For combat, use defender_id; for ranged, use target_id
                def_id = dice.defender_id if dice.defender_id else dice.target_id
                def_card = self.board.get_card_by_id(def_id) if def_id else None
                target_name = def_card.name if def_card else "защитник"

            if action == 'plus1':
                if target == 'atk':
                    dice.atk_modifier += 1
                else:
                    dice.def_modifier += 1
                self.log(f"  -> {card.name}: Удача +1 к броску {target_name}")
            elif action == 'minus1':
                if target == 'atk':
                    dice.atk_modifier -= 1
                else:
                    dice.def_modifier -= 1
                self.log(f"  -> {card.name}: Удача -1 к броску {target_name}")
            elif action == 'reroll':
                new_roll = self.roll_dice()
                if target == 'atk':
                    old_roll = dice.atk_roll
                    dice.atk_roll = new_roll
                else:
                    old_roll = dice.def_roll
                    dice.def_roll = new_roll
                self.log(f"  -> {card.name}: Удача переброс {target_name} [{old_roll}] -> [{new_roll}]")

            # Tap the card that used the instant
            card.tap()

    def use_instant_ability(self, card: Card, ability_id: str, option: str) -> bool:
        """Use an instant ability during priority phase."""
        if not self.priority_phase:
            return False

        # Verify it's the priority player's card
        if card.player != self.priority_player:
            return False

        ability = get_ability(ability_id)
        if not ability or not ability.is_instant:
            return False

        # Verify the card can use this ability
        if not card.can_use_ability(ability_id):
            return False

        # Combat participants can't use instants on their own combat
        # Note: target of ranged attack CAN use instants (they're not actively attacking/defending)
        if self.pending_dice_roll:
            dice = self.pending_dice_roll
            combat_card_ids = set()
            if dice.attacker_id:
                combat_card_ids.add(dice.attacker_id)
            if dice.defender_id:
                combat_card_ids.add(dice.defender_id)
            # target_id is NOT excluded - ranged targets can react with instants
            if card.id in combat_card_ids:
                self.log(f"{card.name}: участвует в бою")
                return False

        # Check if this card already has an instant on the stack (can only use once per stack)
        for instant in self.instant_stack:
            if instant.card_id == card.id:
                self.log(f"{card.name}: уже использовал способность")
                return False

        # Add to stack
        self.instant_stack.append(StackItem(
            card_id=card.id,
            ability_id=ability.id,
            option=option
        ))

        self.log(f"{card.name}: Удача ({option})")

        # Check if opponent can respond
        opponent = 2 if card.player == 1 else 1
        opponent_instants = self.get_legal_instants(opponent)

        if opponent_instants:
            # Opponent has instants - give them priority to respond
            self.priority_passed = []
            self.priority_player = opponent
            self.log(f"Приоритет: Игрок {self.priority_player}")
        else:
            # Opponent has no instants - resolve immediately and finish combat
            self._resolve_priority_stack()
            self.continue_after_priority()

        return True

    @property
    def awaiting_priority(self) -> bool:
        """Check if waiting for priority response."""
        return self.priority_phase

    def move_card(self, card: Card, to_pos: int) -> bool:
        """Move card to position. Card is passed explicitly (not from selected_card)."""
        # Clear previous dice display
        self.last_combat = None

        # Block during any popup/decision state
        if self.has_blocking_interaction:
            return False

        # Block movement during forced attack
        if self.has_forced_attack:
            self.log("Сначала атакуйте закрытого врага!")
            return False

        if not card or not card.can_act:
            return False

        from_pos = card.position

        # Calculate actual distance moved (Manhattan distance for orthogonal movement)
        from_col, from_row = from_pos % 5, from_pos // 5
        to_col, to_row = to_pos % 5, to_pos // 5
        distance = abs(to_col - from_col) + abs(to_row - from_row)

        if self.board.move_card(from_pos, to_pos):
            # Emit move event for network/replay
            self.emit_event(evt_card_moved(card.id, from_pos, to_pos))

            # Jump consumes all movement, normal movement consumes distance
            if card.has_ability("jump"):
                card.curr_move = 0
                self.log(f"{card.name} прыгнул.")
            else:
                card.curr_move -= distance
                self.log(f"{card.name} переместился.")

            # Recalculate formations after movement
            self.recalculate_formations()

            # Check for movement_shot ability trigger
            self._process_movement_shot(card)

            # Check for forced attack after movement (must_attack_tapped ability)
            self._update_forced_attackers()
            forced_targets = self.get_forced_attacker_card(card)
            if forced_targets:
                # Card moved next to tapped enemy - must attack
                self.log(f"{card.name} должен атаковать закрытого врага!")

            # NOTE: UI state (valid_moves, valid_attacks, attack_mode) is now
            # managed by GameClient, not the engine. Client should call
            # refresh_selection() after move completes.
            return True
        return False

    def roll_dice(self) -> int:
        """Roll a D6.

        In network mode: Uses pre-injected rolls from server via inject_rolls().
        In local mode: Generates random roll if no injected rolls available.

        Returns:
            int: Roll result (1-6)
        """
        if self._pending_rolls:
            return self._pending_rolls.pop(0)
        return random.randint(1, 6)

    def inject_rolls(self, rolls: List[int]):
        """Inject dice rolls for server-authoritative gameplay.

        In network mode, the server calls this before processing a command
        to provide the exact dice rolls that will be used.

        Args:
            rolls: List of D6 results (1-6) to use in order
        """
        self._pending_rolls.extend(rolls)

    def clear_pending_rolls(self):
        """Clear any unused injected rolls (e.g., on command failure)."""
        self._pending_rolls.clear()

    def _get_attack_tier(self, roll: int) -> int:
        """Get attack tier from roll. Returns 0=weak, 1=medium, 2=strong."""
        if roll >= 6:
            return 2
        elif roll >= 4:
            return 1
        return 0

    def _get_opposed_tiers(self, roll_diff: int, atk_roll: int = 0) -> Tuple[int, int, bool]:
        """
        Get attack and counter tiers from roll difference.
        Returns (atk_tier, def_tier, is_exchange) where -1 = miss/no counter.
        is_exchange=True means attacker can choose to reduce tier to avoid counter.

        Combat table:
        Diff 5+: Strong, no counter
        Diff 4: Strong + weak counter (EXCHANGE)
        Diff 3: Medium, no counter
        Diff 2: Medium + weak counter (EXCHANGE)
        Diff 1: Weak, no counter
        Diff 0: Tie (1-4 = attacker weak, 5-6 = defender weak)
        Diff -1, -2: Attacker weak, no counter (attacker still hits!)
        Diff -3, -4: Miss, defender weak
        Diff -5+: Miss, defender medium
        """
        if roll_diff >= 5:
            return 2, -1, False  # Strong hit, no counter
        elif roll_diff == 4:
            return 2, 0, True   # Strong + weak counter (EXCHANGE - can reduce to medium)
        elif roll_diff == 3:
            return 1, -1, False  # Medium hit, no counter
        elif roll_diff == 2:
            return 1, 0, True   # Medium + weak counter (EXCHANGE - can reduce to weak)
        elif roll_diff == 1:
            return 0, -1, False  # Weak hit, no counter
        elif roll_diff == 0:
            # Tie - depends on actual dice value
            if atk_roll >= 5:
                return -1, 0, False  # Defender weak counter
            else:
                return 0, -1, False  # Attacker weak hit
        elif roll_diff == -1:
            return 0, -1, False  # Attacker weak, no counter (attacker still hits!)
        elif roll_diff == -2:
            return -1, -1, False  # Both miss
        elif roll_diff == -3:
            return -1, 0, False  # Miss, defender weak
        elif roll_diff == -4:
            return 0, 1, True   # Attacker weak + medium counter (EXCHANGE - defender can reduce)
        return -1, 1, False  # Miss, defender medium

    def calculate_damage_vs_tapped_with_tier(self, atk_roll: int, attacker: Card, defender: Card = None) -> Tuple[int, str, int]:
        """Calculate damage vs tapped card. Returns (damage, tier_name, tier)."""
        tier_names = ["слабая", "средняя", "сильная"]
        tier = self._get_attack_tier(atk_roll)
        damage = attacker.get_effective_attack()[tier] + self._get_positional_damage_modifier(attacker, tier)
        # Bonus damage vs tapped (tapped_bonus and closed_attack_bonus abilities)
        if attacker.has_ability("tapped_bonus"):
            damage += 1
        if attacker.has_ability("closed_attack_bonus"):
            damage += 1
        # Element bonus damage
        if defender:
            damage += self._get_element_damage_bonus(attacker, defender)
        damage = max(0, damage)
        return damage, tier_names[tier], tier

    def calculate_damage_vs_tapped(self, atk_roll: int, attacker: Card, defender: Card = None) -> int:
        """Calculate damage vs tapped card - no opposed roll."""
        damage, _, _ = self.calculate_damage_vs_tapped_with_tier(atk_roll, attacker, defender)
        return damage

    def _get_positional_damage_modifier(self, card: Card, tier: int) -> int:
        """Get OUTGOING damage modifier based on card position and tier (0=weak, 1=medium, 2=strong)."""
        col = self._get_card_column(card)
        modifier = 0

        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability:
                # Edge columns: +1 to medium and strong strikes
                if ability_id == "edge_column_attack" and col in (0, 4) and tier >= 1:
                    modifier += 1
                # Formation attack bonus: +N damage when in formation
                if ability.is_formation and card.in_formation and ability.formation_attack_bonus > 0:
                    modifier += ability.formation_attack_bonus

        return modifier

    def get_display_attack(self, card: Card) -> Tuple[int, int, int]:
        """Get attack values for display, including all bonuses.

        This includes: base attack, temp bonuses, defender buff, formation bonus,
        and position-based bonuses (like edge column +1 to medium/strong).
        """
        base = card.get_effective_attack()  # Already includes temp_attack_bonus and defender_buff

        # Add formation attack bonus and positional bonuses per tier
        bonuses = [0, 0, 0]  # weak, medium, strong
        col = self._get_card_column(card)

        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability:
                # Formation attack bonus (all tiers)
                if ability.is_formation and card.in_formation:
                    for i in range(3):
                        bonuses[i] += ability.formation_attack_bonus

                # Edge columns: +1 to medium and strong strikes only
                if ability_id == "edge_column_attack" and col in (0, 4):
                    bonuses[1] += 1  # medium
                    bonuses[2] += 1  # strong

        return (base[0] + bonuses[0], base[1] + bonuses[1], base[2] + bonuses[2])

    def calculate_damage_with_tier(self, roll_diff: int, attacker: Card, defender: Card,
                                   defender_can_counter: bool, atk_roll: int = 0) -> Tuple[int, int, str, str, int, int, bool]:
        """
        Calculate damage from opposed roll (before reductions).
        Returns (damage_to_defender, damage_to_attacker, atk_tier_name, def_tier_name, atk_tier, def_tier, is_exchange).
        atk_roll is needed for tie resolution (1-4 = attacker wins, 5-6 = defender wins).
        is_exchange=True means attacker can choose to reduce attack to avoid counter.
        """
        tier_names = ["слабая", "средняя", "сильная"]
        atk = attacker.get_effective_attack()
        def_atk = defender.get_effective_attack()

        atk_tier, def_tier, is_exchange = self._get_opposed_tiers(roll_diff, atk_roll)

        # Attacker damage (with outgoing positional modifier and element bonus)
        if atk_tier >= 0:
            damage_to_defender = atk[atk_tier] + self._get_positional_damage_modifier(attacker, atk_tier)
            damage_to_defender += self._get_element_damage_bonus(attacker, defender)
            damage_to_defender = max(0, damage_to_defender)
            atk_tier_name = tier_names[atk_tier]
        else:
            damage_to_defender = 0
            atk_tier_name = "промах"

        # Defender counter (with outgoing positional modifier and element bonus)
        damage_to_attacker = 0
        def_tier_name = ""
        if defender_can_counter and def_tier >= 0:
            damage_to_attacker = def_atk[def_tier] + self._get_positional_damage_modifier(defender, def_tier)
            damage_to_attacker += self._get_element_damage_bonus(defender, attacker)
            damage_to_attacker = max(0, damage_to_attacker)
            def_tier_name = tier_names[def_tier]

        return damage_to_defender, damage_to_attacker, atk_tier_name, def_tier_name, atk_tier, def_tier, is_exchange

    def calculate_damage(self, roll_diff: int, attacker: Card, defender: Card,
                         defender_can_counter: bool, atk_roll: int = 0) -> Tuple[int, int]:
        """Calculate damage from opposed roll. Returns (damage_to_defender, damage_to_attacker)."""
        dmg_def, dmg_atk, _, _, _, _, _ = self.calculate_damage_with_tier(roll_diff, attacker, defender, defender_can_counter, atk_roll)
        return dmg_def, dmg_atk

    def attack(self, attacker: Card, target_pos: int) -> bool:
        """Initiate attack - may trigger defender choice or friendly fire confirmation.
        Attacker is passed explicitly (not from selected_card)."""
        # Clear previous dice display
        self.last_combat = None

        # Block during any popup/decision state
        if self.has_blocking_interaction:
            return False

        if not attacker:
            return False

        target = self.board.get_card(target_pos)

        if not target:
            return False

        # Consume flyer attack ability when attacking a flying creature
        # The ability is consumed regardless of hit or miss
        if attacker.can_attack_flyer and target.stats.is_flying:
            attacker.can_attack_flyer = False
            attacker.can_attack_flyer_until_turn = 0
            self.log(f"{attacker.name} использует подготовленную атаку!")

        # Clear any existing arrows before showing new one
        self.emit_clear_arrows_immediate()

        # Emit arrow immediately when attack is declared
        self.emit_arrow(attacker.position, target_pos, 'attack')

        # Friendly fire confirmation
        if target.player == attacker.player:
            if self.friendly_fire_target == target_pos:
                # Confirmed - proceed with attack
                self.friendly_fire_target = None
                self.log(f"{attacker.name} атакует союзника {target.name}!")
                return self._resolve_combat(attacker, target)
            else:
                # First click - ask for confirmation
                self.friendly_fire_target = target_pos
                self.log(f"Атаковать союзника {target.name}? Нажмите ещё раз для подтверждения.")
                return True

        # Clear friendly fire state when attacking enemy
        self.friendly_fire_target = None

        # Check for valid defenders (unless attacker has direct - cannot be redirected)
        valid_defenders = []
        has_direct = attacker.has_direct or self._has_direct_attack(attacker)
        # tapped_bonus grants direct vs tapped targets
        if attacker.has_ability("tapped_bonus") and target.tapped:
            has_direct = True
        if has_direct:
            self.log(f"  [{attacker.name}: направленный удар]")
        else:
            valid_defenders = self.board.get_valid_defenders(attacker, target)

        if valid_defenders:
            # Enter defender choice mode using unified Interaction (data-only)
            self.interaction = interaction_select_defender(
                attacker_id=attacker.id,
                target_id=target.id,
                valid_defender_ids=tuple(d.id for d in valid_defenders),
                valid_positions=tuple(d.position for d in valid_defenders if d.position is not None),
                defending_player=target.player,
            )
            self.log(f"{attacker.name} атакует {target.name}!")
            self.log(f"Игрок {target.player}: выберите защитника")
            return True
        else:
            # No defenders available - resolve immediately
            return self._resolve_combat(attacker, target)

    def choose_defender(self, defender: Card) -> bool:
        """Defender player chooses to intercept with this card."""
        if not self.awaiting_defender:
            return False

        if not self.interaction.can_select_card_id(defender.id):
            return False

        attacker = self.get_card_by_id(self.interaction.actor_id)
        if not attacker:
            return False
        self.log(f"{defender.name} перехватывает атаку!")

        # Trigger ON_DEFEND abilities before combat
        self._process_defender_triggers(defender, attacker)

        # Clear defender state
        self.interaction = None

        # Resolve combat with the intercepting defender
        result = self._resolve_combat(attacker, defender)

        # Intercepting defender taps after combat (if still alive)
        # Unless they have defender_no_tap ability
        if defender.is_alive and "defender_no_tap" not in defender.stats.ability_ids:
            defender.tap()

        return result

    def skip_defender(self) -> bool:
        """Defender player chooses not to intercept."""
        if not self.awaiting_defender:
            return False

        attacker = self.get_card_by_id(self.interaction.actor_id)
        target = self.get_card_by_id(self.interaction.target_id)
        if not attacker or not target:
            self.interaction = None
            return False
        self.log("Защита не выставлена.")

        # Clear defender state
        self.interaction = None

        # Resolve combat with original target
        return self._resolve_combat(attacker, target)

    def _resolve_combat(self, attacker: Card, defender: Card) -> bool:
        """Resolve combat between attacker and defender."""
        # If defender is webbed, skip dice rolls entirely
        if defender.webbed:
            dealt, _ = self._deal_damage(defender, 0)  # Just triggers web removal
            self.last_combat = CombatResult(0, 0, 0, 0, attacker_name=attacker.name, defender_name=defender.name)
            attacker.tap()
            self._check_winner()
            return True

        # Always roll dice
        atk_roll = self.roll_dice()
        def_roll = 0 if defender.tapped else self.roll_dice()
        atk_bonus = self._get_attack_dice_bonus(attacker, defender)
        def_bonus = 0 if defender.tapped else self._get_defense_dice_bonus(defender)

        # Log the initial rolls
        self.log(f"{attacker.name} [{atk_roll}] vs {defender.name} [{def_roll}]")
        self.emit_event(evt_dice_rolled(attacker.id, defender.id, atk_roll, def_roll))

        # Check if dice modifications matter (constant damage = all attack values equal)
        atk_values = attacker.get_effective_attack()
        atk_is_constant = atk_values[0] == atk_values[1] == atk_values[2]
        def_values = defender.get_effective_attack()
        def_is_constant = def_values[0] == def_values[1] == def_values[2]
        dice_matter = not (atk_is_constant and (defender.tapped or def_is_constant))

        # Create dice context for priority phase
        dice_context = DiceContext(
            type='combat',
            attacker_id=attacker.id,
            atk_roll=atk_roll,
            atk_bonus=atk_bonus,
            defender_id=defender.id,
            def_roll=def_roll,
            def_bonus=def_bonus,
            dice_matter=dice_matter,
            defender_was_tapped=defender.tapped,
        )

        # Check if we should enter priority phase (only if dice matter)
        if not dice_matter:
            self.log("  [Броски не влияют на исход]")
        elif self._enter_priority_phase(dice_context):
            # Priority phase started - combat will continue after priority resolves
            return True

        # No priority phase needed - continue immediately
        return self._finish_combat(dice_context)

    def _finish_combat(self, dice_context: DiceContext, force_reduced: bool = False) -> bool:
        """Finish combat after priority phase (or immediately if no priority).

        Args:
            dice_context: Combat context with rolls, cards, etc.
            force_reduced: If True, use reduced attack tier (exchange choice to avoid counter)
        """
        attacker = self.board.get_card_by_id(dice_context.attacker_id)
        defender = self.board.get_card_by_id(dice_context.defender_id)
        if not attacker or not defender:
            self.pending_dice_roll = None
            return False
        atk_roll = dice_context.atk_roll + dice_context.atk_modifier
        atk_bonus = dice_context.atk_bonus
        def_roll = dice_context.def_roll + dice_context.def_modifier
        def_bonus = dice_context.def_bonus

        # Clear pending dice roll
        self.pending_dice_roll = None

        # Use tapped state from when dice were rolled (not current state)
        defender_was_tapped = dice_context.defender_was_tapped

        # Tapped cards don't roll or counter
        if defender_was_tapped:
            total_roll = atk_roll + atk_bonus
            dmg_to_def, atk_strength, atk_tier = self.calculate_damage_vs_tapped_with_tier(total_roll, attacker, defender)
            dmg_to_atk = 0
            def_strength = ""
            def_tier = -1
            is_exchange = False
        else:
            total_atk = atk_roll + atk_bonus
            roll_diff = total_atk - (def_roll + def_bonus)
            dmg_to_def, dmg_to_atk, atk_strength, def_strength, atk_tier, def_tier, is_exchange = self.calculate_damage_with_tier(
                roll_diff, attacker, defender, True, total_atk
            )

            # Check for exchange situation (skip if already resolved)
            # exchange_resolved is now stored in dice_context to survive interaction clearing
            if is_exchange and not force_reduced and not self.awaiting_exchange_choice and not dice_context.exchange_resolved:
                # Determine who chooses: attacker if they have advantage, defender otherwise
                choosing_player = attacker.player if roll_diff > 0 else defender.player
                # Enter exchange choice state using unified Interaction (data-only)
                self.interaction = interaction_choose_exchange(
                    attacker_id=attacker.id,
                    defender_id=defender.id,
                    full_damage=dmg_to_def,
                    reduced_damage=dmg_to_def - 1 if dmg_to_def > 0 else 0,
                    acting_player=choosing_player,
                )
                # Store dice_context in pending_dice_roll (not in interaction.context for serializability)
                self.pending_dice_roll = dice_context
                # Store only serializable primitives in interaction.context
                self.interaction.context['attacker_advantage'] = roll_diff > 0
                self.interaction.context['roll_diff'] = roll_diff
                tier_names = ["слабая", "средняя", "сильная"]

                if roll_diff > 0:
                    # Attacker advantage - attacker can reduce their attack to avoid counter
                    reduced_tier = atk_tier - 1
                    self.log(f"Обмен ударами! {atk_strength} + контратака")
                    self.log(f"Можете ослабить до {tier_names[reduced_tier]} без контратаки")
                else:
                    # Defender advantage - defender can reduce counter to cancel attacker's hit
                    reduced_tier = def_tier - 1
                    self.log(f"Обмен ударами! {def_strength} контратака + {atk_strength} атака")
                    self.log(f"Защитник может ослабить до {tier_names[reduced_tier]} без удара атакующего")
                return False  # Wait for player choice

            # If exchange and player chose reduced damage
            if force_reduced and is_exchange:
                tier_names = ["слабая", "средняя", "сильная"]
                if roll_diff > 0:
                    # Attacker-advantage exchange: reduce attack, no counter
                    atk_tier -= 1
                    atk_strength = tier_names[atk_tier]
                    atk = attacker.get_effective_attack()
                    dmg_to_def = atk[atk_tier] + self._get_positional_damage_modifier(attacker, atk_tier)
                    dmg_to_def = max(0, dmg_to_def)
                    dmg_to_atk = 0  # No counter
                    def_strength = ""
                    def_tier = -1
                else:
                    # Defender-advantage exchange: reduce counter, no attacker hit
                    def_tier -= 1
                    def_strength = tier_names[def_tier]
                    def_atk = defender.get_effective_attack()
                    dmg_to_atk = def_atk[def_tier] + self._get_positional_damage_modifier(defender, def_tier)
                    dmg_to_atk = max(0, dmg_to_atk)
                    dmg_to_def = 0  # No attacker hit
                    atk_strength = "промах"
                    atk_tier = -1

        # Apply anti-magic bonus (+1 damage vs magic creatures)
        anti_magic_bonus = 0
        if attacker.has_ability("anti_magic") and self._has_magic_abilities(defender):
            anti_magic_bonus = 1
            dmg_to_def += 1
            self.log(f"  [{attacker.name}: +1 урон vs магия]")

        # Store initial damage before reduction
        initial_dmg_to_def = dmg_to_def
        initial_dmg_to_atk = dmg_to_atk

        # Apply damage reduction (defender's passive vs attacker's attack tier)
        def_reduction = self._get_damage_reduction(defender, attacker, atk_tier)
        reduced_def = False
        if def_reduction > 0 and dmg_to_def > 0:
            dmg_to_def = max(0, dmg_to_def - def_reduction)
            if dmg_to_def < initial_dmg_to_def:
                reduced_def = True

        # Apply damage reduction (attacker's passive vs defender's counter tier)
        atk_reduction = self._get_damage_reduction(attacker, defender, def_tier)
        reduced_atk = False
        if atk_reduction > 0 and dmg_to_atk > 0:
            dmg_to_atk = max(0, dmg_to_atk - atk_reduction)
            if dmg_to_atk < initial_dmg_to_atk:
                reduced_atk = True

        # Apply damage (use _deal_damage for defender, direct for attacker counter)
        dealt, _ = self._deal_damage(defender, dmg_to_def, source_id=attacker.id)
        attacker.take_damage(dmg_to_atk)
        self.emit_damage(attacker.position, dmg_to_atk, card_id=attacker.id, source_id=defender.id)
        self.emit_clear_arrows()

        # Store combat result
        self.last_combat = CombatResult(
            attacker_roll=atk_roll, defender_roll=def_roll,
            attacker_damage_dealt=dealt, defender_damage_dealt=dmg_to_atk,
            attacker_bonus=atk_bonus, defender_bonus=def_bonus,
            attacker_name=attacker.name, defender_name=defender.name
        )

        # Log final result with attack strength
        atk_bonus_str = f"+{atk_bonus}" if atk_bonus > 0 else ""
        def_bonus_str = f"+{def_bonus}" if def_bonus > 0 else ""
        strength_str = f" ({atk_strength})" if atk_strength else " (промах)"
        self.log(f"[{atk_roll}{atk_bonus_str}] vs [{def_roll}{def_bonus_str}]{strength_str}")
        if reduced_def:
            self.log(f"  [{defender.name}: {initial_dmg_to_def}-{def_reduction}={dmg_to_def}]")
        if reduced_atk:
            self.log(f"  [{attacker.name}: {initial_dmg_to_atk}-{atk_reduction}={dmg_to_atk}]")
        if dealt > 0:
            self.log(f"  -> {defender.name}: -{dealt} HP")
        elif reduced_def:
            self.log(f"  -> {defender.name}: 0 урона")
        if dmg_to_atk > 0:
            self.log(f"  -> {attacker.name}: -{dmg_to_atk} HP")
        if def_strength:
            self.log(f"  <- контратака: {def_strength}")

        # Process counter_shot trigger
        if attacker.is_alive:
            self._process_counter_shot(attacker, defender)

        # Process heal_on_attack
        if attacker.is_alive:
            self._process_heal_on_attack(attacker, defender)

        # Process hellish_stench (triggers vs untapped targets if attack hit, even if 0 damage)
        if attacker.is_alive and defender.is_alive:
            attack_hit = atk_tier >= 0  # Hit if tier is weak(0), medium(1), or strong(2)
            self._process_hellish_stench(attacker, defender, defender_was_tapped, attack_hit)

        # Handle deaths
        self._handle_death(defender, attacker)

        if not self._handle_death(attacker, defender):
            attacker.tap()

        # Update forced attackers after combat
        self._update_forced_attackers()

        self._check_winner()
        return True

    def continue_after_priority(self) -> bool:
        """Continue combat/action after priority phase resolves."""
        if not self.pending_dice_roll:
            return False

        dice_context = self.pending_dice_roll
        if dice_context.type == 'combat':
            return self._finish_combat(dice_context)
        elif dice_context.type == 'ranged':
            return self._finish_ranged_attack(dice_context)
        elif dice_context.type == 'magic':
            return self._finish_magic_attack(dice_context)
        return False

    def resolve_exchange_choice(self, reduce_damage: bool) -> bool:
        """Handle player's choice during exchange.

        Args:
            reduce_damage: True to reduce attack tier and avoid counter,
                          False to deal full damage but take counter
        """
        if not self.awaiting_exchange_choice:
            return False

        # Get dice_context from pending_dice_roll (not from interaction.context for serializability)
        dice_context = self.pending_dice_roll
        if not dice_context:
            self.interaction = None
            return False
        # Mark that exchange was handled in the dice context (survives interaction clearing)
        dice_context.exchange_resolved = True
        self.interaction = None

        if reduce_damage:
            self.log("Выбрано: ослабить удар")
        else:
            self.log("Выбрано: полный удар с контратакой")

        return self._finish_combat(dice_context, force_reduced=reduce_damage)

    def end_turn(self):
        """End current player's turn."""
        if self.phase != GamePhase.MAIN:
            return

        # Can't end turn while awaiting defender choice, Valhalla, counter shot, heal confirm, exchange, or stench
        # Note: movement_shot is optional, so it doesn't block ending turn
        if self.awaiting_defender or self.awaiting_valhalla or self.awaiting_counter_shot or self.awaiting_heal_confirm or self.awaiting_exchange_choice or self.awaiting_stench_choice:
            return

        # Can't end turn while forced attack is pending
        if self.has_forced_attack:
            self.log("Сначала атакуйте закрытого врага!")
            return

        # Clear optional movement shot if pending
        if self.awaiting_movement_shot:
            self.interaction = None

        # Note: Selection is now client-side (GameClient), no server deselect needed

        # Tick defender buff duration for current player's cards (expires at end of their turn)
        for card in self.board.get_all_cards(player=self.current_player):
            card.tick_defender_buff()

        # Expire flyer attack ability for current player's cards
        for card in self.board.get_all_cards(player=self.current_player):
            if card.can_attack_flyer and card.can_attack_flyer_until_turn <= self.turn_number:
                card.can_attack_flyer = False
                card.can_attack_flyer_until_turn = 0

        # Remove web status from current player's cards at end of their turn
        for card in self.board.get_all_cards(player=self.current_player):
            if card.webbed:
                card.webbed = False
                self.log(f"{card.name} освобождается от паутины")

        # Emit turn ended event before switching
        self.emit_event(evt_turn_ended(self.current_player))

        # Switch player
        if self.current_player == 1:
            self.current_player = 2
        else:
            self.current_player = 1
            self.turn_number += 1

        self.start_turn()

    # =========================================================================
    # COMMAND PROCESSING - Central entry point for all player commands
    # =========================================================================

    def process_command(self, cmd: Command, server_only: bool = False) -> Tuple[bool, List[Event]]:
        """
        Process a player command. Returns (success, events).

        This is the central entry point for all player actions, designed for:
        - Network play (server receives commands from clients)
        - Replays (replay commands to recreate game state)
        - Testing (inject commands, verify results)

        Args:
            cmd: The command to process
            server_only: If True, reject UI-level commands (SELECT, CLICK_BOARD,
                        TOGGLE_ATTACK_MODE, DESELECT). Use this on the server
                        to ensure clients only send effectful commands.

        Commands are validated and routed to the appropriate handler methods.
        Events are collected during processing via emit_event() and returned via pop_events().

        Supported commands:
            MOVE, ATTACK, USE_ABILITY, USE_INSTANT, PREPARE_FLYER_ATTACK,
            CONFIRM, CANCEL, CHOOSE_POSITION, CHOOSE_CARD, CHOOSE_AMOUNT,
            PASS_PRIORITY, SKIP, END_TURN

        Note: UI commands (SELECT, DESELECT, TOGGLE_ATTACK_MODE) are handled
        client-side by GameClient and are not processed by the server.
        """
        # Game over - no commands accepted
        if self.phase == GamePhase.GAME_OVER:
            return False, self.pop_events()

        # Validate player is allowed to act
        # During priority phase, only the priority_player can act (no exceptions)
        if self.priority_phase and cmd.player != self.priority_player:
            return False, self.pop_events()

        # During main phase, only current_player can act (except during interactions)
        if self.phase == GamePhase.MAIN and not self.priority_phase:
            # During interactions, check who should respond
            if self.interaction:
                expected_player = self.interaction.acting_player
                if expected_player and cmd.player != expected_player:
                    return False, self.pop_events()
            elif cmd.player != self.current_player:
                return False, self.pop_events()

        # Systematic card ownership validation
        # Commands where card_id must belong to cmd.player (acting with own card)
        own_card_commands = (
            CommandType.MOVE, CommandType.ATTACK,
            CommandType.USE_ABILITY, CommandType.USE_INSTANT,
            CommandType.PREPARE_FLYER_ATTACK,
        )
        if cmd.card_id is not None and cmd.type in own_card_commands:
            card = self.board.get_card_by_id(cmd.card_id)
            if not card:
                return False, self.pop_events()  # Card doesn't exist
            if card.player != cmd.player:
                return False, self.pop_events()  # Can't act with opponent's card

        # Validate target_id exists (if provided)
        # Note: target ownership validation depends on the action (e.g., attacking enemy is valid)
        if cmd.target_id is not None:
            target = self.board.get_card_by_id(cmd.target_id)
            if not target:
                return False, self.pop_events()  # Target doesn't exist

        # Route by command type
        if cmd.type == CommandType.MOVE:
            # Card ownership validated at top; check position and can_act here
            if cmd.card_id is not None and cmd.position is not None:
                card = self.board.get_card_by_id(cmd.card_id)
                if card and card.can_act:
                    card_valid_moves = self.board.get_valid_moves(card)
                    if cmd.position in card_valid_moves:
                        return self.move_card(card, cmd.position), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.ATTACK:
            # Card ownership validated at top; check position here
            if cmd.card_id is not None and cmd.position is not None:
                card = self.board.get_card_by_id(cmd.card_id)
                if card:
                    card_valid_attacks = self.get_attack_targets(card)
                    if cmd.position in card_valid_attacks:
                        # Pass card directly - no UI state mutation needed
                        return self.attack(card, cmd.position), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.PREPARE_FLYER_ATTACK:
            # Card ownership validated at top
            if cmd.card_id is not None:
                card = self.board.get_card_by_id(cmd.card_id)
                if card:
                    return self.prepare_flyer_attack(card), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.USE_ABILITY:
            # Card ownership validated at top
            # Pattern A: USE_ABILITY creates interaction if targeting needed,
            # then client responds with CHOOSE_POSITION/CHOOSE_CARD commands.
            if cmd.card_id is not None and cmd.ability_id:
                card = self.board.get_card_by_id(cmd.card_id)
                if card:
                    return self.use_ability(card, cmd.ability_id), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.USE_INSTANT:
            if cmd.card_id is not None and cmd.ability_id and cmd.option:
                card = self.board.get_card_by_id(cmd.card_id)
                if card:
                    return self.use_instant_ability(card, cmd.ability_id, cmd.option), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.CONFIRM:
            if cmd.confirmed is not None:
                # Heal confirmation (Y/N)
                if self.awaiting_heal_confirm:
                    self.confirm_heal_on_attack(cmd.confirmed)
                    return True, self.pop_events()
                # Exchange choice: confirmed=False means reduce damage, True means full
                if self.awaiting_exchange_choice:
                    return self.resolve_exchange_choice(reduce_damage=not cmd.confirmed), self.pop_events()
                # Stench choice: confirmed=True means tap, False means take damage
                if self.awaiting_stench_choice:
                    return self.resolve_stench_choice(tap=cmd.confirmed), self.pop_events()
                # Counter selection confirmation (proceed with selected amount)
                if self.awaiting_counter_selection:
                    return self.confirm_counter_selection(), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.CANCEL:
            if self.awaiting_ability_target or self.awaiting_counter_selection:
                self.cancel_ability()
                return True, self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.CHOOSE_POSITION:
            if cmd.position is not None:
                # Route to appropriate handler based on current interaction
                if self.awaiting_defender:
                    card = self.board.get_card(cmd.position)
                    if card and self.interaction.can_select_card_id(card.id):
                        return self.choose_defender(card), self.pop_events()
                elif self.awaiting_counter_shot:
                    if self.interaction.can_select_position(cmd.position):
                        return self.select_counter_shot_target(cmd.position), self.pop_events()
                elif self.awaiting_movement_shot:
                    if self.interaction.can_select_position(cmd.position):
                        return self.select_movement_shot_target(cmd.position), self.pop_events()
                elif self.awaiting_valhalla:
                    if self.interaction.can_select_position(cmd.position):
                        return self.select_valhalla_target(cmd.position), self.pop_events()
                elif self.awaiting_ability_target:
                    if self.interaction.can_select_position(cmd.position):
                        return self.select_ability_target(cmd.position), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.CHOOSE_CARD:
            if cmd.card_id is not None:
                card = self.board.get_card_by_id(cmd.card_id)
                if card and self.awaiting_defender:
                    if self.interaction.can_select_card_id(cmd.card_id):
                        return self.choose_defender(card), self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.CHOOSE_AMOUNT:
            if cmd.amount is not None and self.awaiting_counter_selection:
                self.set_counter_selection(cmd.amount)
                return True, self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.PASS_PRIORITY:
            if self.awaiting_priority:
                if self.pass_priority():
                    self.continue_after_priority()
                return True, self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.SKIP:
            if self.awaiting_defender:
                self.skip_defender()
                return True, self.pop_events()
            elif self.awaiting_movement_shot:
                self.skip_movement_shot()
                return True, self.pop_events()
            return False, self.pop_events()

        elif cmd.type == CommandType.END_TURN:
            if self.phase == GamePhase.MAIN and not self.awaiting_defender:
                self.end_turn()
                return True, self.pop_events()
            return False, self.pop_events()

        return False, self.pop_events()
