"""Game state management and logic."""
import random
from typing import List, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field

from .board import Board
from .card import Card, create_card
from .card_database import create_starter_deck, create_starter_deck_p2
from .constants import GamePhase
from .abilities import get_ability, AbilityType, AbilityTrigger, TargetType, Ability
from .interaction import Interaction, InteractionKind


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


@dataclass
class PendingAttack:
    """Stores info about an attack waiting for defender choice."""
    attacker: Card
    original_target: Card
    valid_defenders: List[Card]


class Game:
    """Main game state and logic."""

    def __init__(self):
        self.board = Board()
        self.phase = GamePhase.SETUP
        self.current_player = 1
        self.turn_number = 0

        # Cards in each player's hand (for placement)
        self.hand_p1: List[Card] = []
        self.hand_p2: List[Card] = []

        # Selected card and available actions
        self.selected_card: Optional[Card] = None
        self.valid_moves: List[int] = []
        self.valid_attacks: List[int] = []
        self.attack_mode: bool = False  # True when attack button is clicked

        # Combat state
        self.last_combat: Optional[CombatResult] = None

        # Defender intercept state
        self.awaiting_defender: bool = False
        self.pending_attack: Optional[PendingAttack] = None

        # Ability targeting state
        self.pending_ability: Optional[Ability] = None
        self.pending_ability_card: Optional[Card] = None
        self.valid_ability_targets: List[int] = []

        # Valhalla targeting state
        self.pending_valhalla: List[Tuple[Card, Ability]] = []  # Queue of (dead_card, ability)
        self.current_valhalla: Optional[Tuple[Card, Ability]] = None
        self.valhalla_targets: List[int] = []

        # Counter shot targeting state
        self.pending_counter_shot: Optional[Card] = None  # Attacker with counter_shot
        self.counter_shot_targets: List[int] = []

        # Movement shot targeting state (Оури ability)
        self.pending_movement_shot: Optional[Card] = None
        self.movement_shot_targets: List[int] = []

        # Heal on attack confirmation state
        self.pending_heal_confirm: Optional[Tuple[Card, int]] = None  # (attacker, heal_amount)

        # Hellish stench choice state (target must tap or take damage)
        self.pending_stench_choice: Optional[Tuple[Card, Card, int]] = None  # (attacker, target, damage)

        # Friendly fire confirmation
        self.friendly_fire_target: Optional[int] = None

        # Priority system for instant abilities (внезапные действия)
        self.priority_phase: bool = False       # True when in priority window
        self.priority_player: int = 0           # Player who has priority (1 or 2)
        self.priority_passed: List[int] = []    # Players who have passed priority
        self.pending_dice_roll: Optional[dict] = None  # Dice roll waiting for resolution
        self.instant_stack: List[dict] = []     # Stack of instant abilities to resolve

        # Exchange choice state (when attacker can reduce damage to avoid counter)
        self.awaiting_exchange_choice: bool = False
        self.exchange_context: Optional[dict] = None  # Stores combat context for exchange

        # Card ID counter
        self._next_card_id = 1

        # Message log
        self.messages: List[str] = []

        # Visual events for renderer (damage/heal floating numbers)
        # Each event: {'type': 'damage'|'heal', 'pos': int, 'amount': int}
        self.visual_events: List[dict] = []

        # Forced attack state (must_attack_tapped ability)
        # Maps card_id -> (card, [positions]) for cards that must attack tapped enemies
        self.forced_attackers: dict = {}  # {card_id: (card, [positions])}

        # Counter selection state (for abilities like axe_strike)
        self.awaiting_counter_selection: bool = False
        self.counter_selection_card: Optional[Card] = None
        self.counter_selection_ability: Optional[str] = None
        self.selected_counters: int = 0  # Number of counters selected to spend

        # Unified interaction state (future: will replace individual awaiting_*/pending_* fields)
        # See interaction.py for InteractionKind enum and Interaction dataclass
        self.interaction: Optional[Interaction] = None

    def log(self, msg: str):
        """Add a message to the log."""
        self.messages.append(msg)
        if len(self.messages) > 100:  # Keep last 100 messages
            self.messages.pop(0)

    def emit_damage(self, pos: int, amount: int):
        """Emit a damage visual event."""
        if amount > 0 and pos is not None:
            self.visual_events.append({'type': 'damage', 'pos': pos, 'amount': amount})

    def emit_heal(self, pos: int, amount: int):
        """Emit a heal visual event."""
        if amount > 0 and pos is not None:
            self.visual_events.append({'type': 'heal', 'pos': pos, 'amount': amount})

    def emit_arrow(self, from_pos: int, to_pos: int, arrow_type: str = 'attack'):
        """Emit an arrow visual event for interactions."""
        if from_pos is not None and to_pos is not None:
            self.visual_events.append({
                'type': 'arrow',
                'from_pos': from_pos,
                'to_pos': to_pos,
                'arrow_type': arrow_type
            })

    def emit_clear_arrows(self):
        """Emit event to clear all arrows (after damage is dealt)."""
        self.visual_events.append({'type': 'clear_arrows'})

    def emit_clear_arrows_immediate(self):
        """Emit event to clear arrows immediately (for cancellation)."""
        self.visual_events.append({'type': 'clear_arrows_immediate'})

    def _handle_death(self, card: Card, killer: Optional[Card] = None) -> bool:
        """Handle card death, graveyard, and return True if card died."""
        if card.is_alive:
            return False
        self.log(f"{card.name} погиб!")
        if killer and killer.player != card.player:
            card.killed_by_enemy = True
            # Process ON_KILL triggers for the killer
            self._process_kill_triggers(killer, card)
        self.board.send_to_graveyard(card)
        # Recalculate formations after a card dies
        self.recalculate_formations()
        return True

    def _deal_damage(self, target: Card, amount: int, is_magical: bool = False) -> Tuple[int, bool]:
        """Deal damage to target. Returns (actual_damage, was_web_blocked).

        Args:
            target: Card receiving damage
            amount: Damage amount
            is_magical: If True, bypasses armor
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

        self.emit_damage(target.position, actual)
        return actual, False

    def _process_kill_triggers(self, killer: Card, victim: Card):
        """Process ON_KILL triggered abilities when killer defeats enemy."""
        if not killer.is_alive:
            return

        for ability_id in killer.stats.ability_ids:
            ability = get_ability(ability_id)
            if not ability or ability.trigger != AbilityTrigger.ON_KILL:
                continue

            # Scavenging: full heal on kill
            if ability.id == "scavenging":
                if killer.curr_life < killer.life:
                    heal_amount = killer.life - killer.curr_life
                    killer.curr_life = killer.life
                    self.emit_heal(killer.position, heal_amount)
                    self.log(f"  -> {killer.name}: трупоедство! Полностью исцелён")

    def _check_winner(self) -> bool:
        """Check for winner and update game state. Returns True if game ended."""
        winner = self.board.check_winner()
        if winner is not None:
            self.phase = GamePhase.GAME_OVER
            if winner == 0:
                self.log("Ничья!")
            else:
                self.log(f"Победа игрока {winner}!")
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

        Uses card.id as key since Card objects are not hashable.
        """
        self.forced_attackers = {}  # {card_id: (card, [positions])}

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
                self.forced_attackers[card.id] = (card, adjacent_tapped)

    @property
    def has_forced_attack(self) -> bool:
        """True if there's a card that must attack a tapped enemy."""
        return len(self.forced_attackers) > 0

    def get_forced_attacker_card(self, card: Card) -> Optional[List[int]]:
        """Get forced attack targets for a card, or None if not a forced attacker."""
        if card.id in self.forced_attackers:
            return self.forced_attackers[card.id][1]  # Return positions list
        return None

    def setup_game(self):
        """Initialize a new game with starter decks."""
        deck_p1 = create_starter_deck()
        deck_p2 = create_starter_deck_p2()

        # Create cards for both players (different decks)
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

            # Order: Giants, lightning, axe masters, dwarves, borgs, furnace (next to borg for formation), keepers, frost, ravine, hunters, crushers, then others
            selected_ground = (giants + lightning + axe_masters + dwarves + borgs + furnace + keepers + frost + ravine + hunters[:1] + crushers[:1] + ouri[:1] + expensive[:1] + luck + spider + sailors + elf + hunters[1:] + crushers[1:] + ouri[1:] + expensive[1:] + with_abilities + without_abilities)[:count]
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

        self.selected_card = None
        self.valid_moves = []
        self.valid_attacks = []
        self.attack_mode = False
        self.last_combat = None
        self.cancel_ability()

        self.log(f"Ход {self.turn_number}: Игрок {self.current_player}")

        # Process Valhalla abilities from graveyard
        self._process_valhalla_triggers()

        # Process triggered abilities (ON_TURN_START)
        self._process_turn_start_triggers()

        # Check for forced attacks (must_attack_tapped)
        self._update_forced_attackers()
        if self.has_forced_attack:
            # Log forced attack requirement
            for card_id, (card, targets) in self.forced_attackers.items():
                self.log(f"{card.name} должен атаковать закрытого врага!")

    def select_card(self, pos: int) -> bool:
        """Select a card at position."""
        card = self.board.get_card(pos)

        if card is None:
            self.deselect_card()
            return False

        # During priority phase, allow selecting priority player's cards for instant abilities
        if self.priority_phase and card.player == self.priority_player:
            self.selected_card = card
            self.valid_moves = []
            self.valid_attacks = []
            self.attack_mode = False
            return True

        # Can only select own cards for actions
        if card.player == self.current_player:
            # Check for forced attack requirement
            if self.has_forced_attack:
                # Only allow selecting cards that must attack
                forced_targets = self.get_forced_attacker_card(card)
                if forced_targets is None:
                    self.log("Сначала атакуйте закрытого врага!")
                    return False
                # Auto-enter attack mode with only forced targets
                self.selected_card = card
                self.valid_moves = []  # No movement allowed
                self.valid_attacks = forced_targets
                self.attack_mode = True
                return True

            self.selected_card = card
            self.valid_moves = self.board.get_valid_moves(card) if card.can_act else []
            # Don't auto-calculate attacks - use attack button instead
            self.valid_attacks = []
            self.attack_mode = False
            return True
        else:
            # Clicking enemy card - check if we're in attack mode and can attack it
            if self.selected_card and self.attack_mode and pos in self.valid_attacks:
                return self.attack(pos)
            # Don't deselect when clicking enemy - just ignore
            return False

    def deselect_card(self):
        """Deselect current card."""
        self.selected_card = None
        self.valid_moves = []
        self.valid_attacks = []
        self.attack_mode = False
        self.friendly_fire_target = None
        self.cancel_ability()
        self.emit_clear_arrows_immediate()

    def toggle_attack_mode(self) -> bool:
        """Toggle attack mode for selected card. Returns True if now in attack mode."""
        if not self.selected_card or not self.selected_card.can_act:
            return False

        # During forced attack, attack mode stays on
        if self.has_forced_attack and self.get_forced_attacker_card(self.selected_card) is not None:
            return True

        if self.attack_mode:
            # Turn off attack mode
            self.attack_mode = False
            self.valid_attacks = []
            return False
        else:
            # Turn on attack mode - calculate valid attacks
            self.attack_mode = True
            self.valid_attacks = self.board.get_attack_targets(self.selected_card)

            # Restricted strike: can only attack card directly opposite
            if "restricted_strike" in self.selected_card.stats.ability_ids:
                opposite_pos = self._get_opposite_position(self.selected_card)
                if opposite_pos is not None and opposite_pos in self.valid_attacks:
                    self.valid_attacks = [opposite_pos]
                else:
                    self.valid_attacks = []

            return True

    # =========================================================================
    # ABILITY SYSTEM
    # =========================================================================

    def _process_valhalla_triggers(self):
        """Process Valhalla abilities from graveyard - queues them for target selection."""
        graveyard = self.board.graveyard_p1 if self.current_player == 1 else self.board.graveyard_p2

        # Queue all Valhalla triggers
        self.pending_valhalla = []
        for card in graveyard:
            # Only trigger if killed by enemy attack
            if not card.killed_by_enemy:
                continue

            # Check for Valhalla abilities
            for ability_id in card.stats.ability_ids:
                ability = get_ability(ability_id)
                if ability and ability.trigger == AbilityTrigger.VALHALLA:
                    self.pending_valhalla.append((card, ability))

        # Start processing first Valhalla if any
        self._process_next_valhalla()

    def _process_next_valhalla(self):
        """Process the next Valhalla trigger in queue."""
        if not self.pending_valhalla:
            self.current_valhalla = None
            self.valhalla_targets = []
            return

        # Get next Valhalla
        dead_card, ability = self.pending_valhalla.pop(0)
        self.current_valhalla = (dead_card, ability)

        # Get valid targets (living allies)
        allies = self.board.get_all_cards(dead_card.player)
        allies = [c for c in allies if c.is_alive and c.position is not None]

        if not allies:
            self.log(f"Вальхалла {dead_card.name}: нет союзников!")
            self._process_next_valhalla()  # Process next one
            return

        # Set valid targets for selection
        self.valhalla_targets = [c.position for c in allies]
        self.log(f"Вальхалла {dead_card.name}: выберите существо")

    def select_valhalla_target(self, pos: int) -> bool:
        """Player selects target for Valhalla ability."""
        if not self.current_valhalla or pos not in self.valhalla_targets:
            return False

        dead_card, ability = self.current_valhalla
        target = self.board.get_card(pos)

        if not target:
            return False

        # Apply Valhalla effect
        if ability.id == "valhalla_ova":
            target.temp_dice_bonus += ability.bonus_attack
            self.log(f"  -> {target.name} получил ОвА+{ability.bonus_attack}")
        elif ability.id == "valhalla_strike":
            target.temp_attack_bonus += ability.bonus_attack
            self.log(f"  -> {target.name} получил +{ability.bonus_attack} к удару")

        # Clear current and process next
        self.current_valhalla = None
        self.valhalla_targets = []
        self._process_next_valhalla()

        return True

    @property
    def awaiting_valhalla(self) -> bool:
        """Check if waiting for Valhalla target selection."""
        return self.current_valhalla is not None

    def _process_turn_start_triggers(self):
        """Process all ON_TURN_START triggered abilities."""
        for card in self.board.get_all_cards(self.current_player):
            for ability_id in card.stats.ability_ids:
                ability = get_ability(ability_id)
                if ability and ability.ability_type == AbilityType.TRIGGERED:
                    if ability.trigger == AbilityTrigger.ON_TURN_START:
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
        """Execute a triggered ability automatically."""
        # Regeneration
        if ability.heal_amount > 0 and card.curr_life < card.life:
            healed = card.heal(ability.heal_amount)
            if healed > 0:
                self.log(f"{card.name}: {ability.name} (+{healed} HP)")
                self.emit_heal(card.position, healed)

        # Front row bonus (+1 to ranged) - first row = closest to middle
        if ability.id == "front_row_bonus":
            if self._is_in_own_row(card, 1):  # First row (front, closest to middle)
                card.temp_ranged_bonus += ability.bonus_attack
                self.log(f"{card.name}: +{ability.bonus_attack} к выстрелам (первый ряд)")

        # Back row direct (third row grants direct) - third row = back line
        if ability.id == "back_row_direct":
            if self._is_in_own_row(card, 3):  # Third row (back line)
                card.has_direct = True
                self.log(f"{card.name}: прямой удар (третий ряд)")

        # Axe counter - gain counter at turn start (only in formation)
        if ability.id == "axe_counter":
            if card.in_formation:
                if card.max_counters == 0 or card.counters < card.max_counters:
                    card.counters += 1
                    self.log(f"{card.name}: +1 фишка в строю ({card.counters})")

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

        # Regular ranged shot using card attack
        if ability.id == "ranged_shot":
            bonus = card.temp_ranged_bonus
            atk = card.stats.attack
            d0, d1, d2 = atk[0] + bonus, atk[1] + bonus, atk[2] + bonus
            return f"Выстрел {d0}-{d1}-{d2}"

        # Heal abilities
        if ability.heal_amount > 0:
            return f"{ability.name} +{ability.heal_amount} HP"

        # Magical strike with damage value
        if ability.id == "magical_strike":
            return f"Магический удар {ability.damage_amount}"

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
                self.selected_counters = 0
                targets = self._get_ability_targets(card, ability)
                if not targets:
                    self.log("Нет доступных целей!")
                    return False
                self.pending_ability = ability
                self.pending_ability_card = card
                self.valid_ability_targets = targets
                self.log(f"Выберите цель для {ability.name} (0 фишек)")
                return True
            # Start counter selection mode
            self.awaiting_counter_selection = True
            self.counter_selection_card = card
            self.counter_selection_ability = ability_id
            self.selected_counters = 0  # Default to 0 counters
            self.log(f"Выберите количество фишек (0-{card.counters})")
            return True

        # Self-targeting abilities execute immediately
        if ability.target_type == TargetType.SELF:
            result = self._execute_ability(card, ability, card)
            if card.tapped:
                self.valid_moves = []
                self.valid_attacks = []
            return result

        # Abilities that need targets
        if ability.target_type in (TargetType.ENEMY, TargetType.ALLY, TargetType.ANY):
            targets = self._get_ability_targets(card, ability)
            if not targets:
                self.log("Нет доступных целей!")
                return False

            # Store pending ability for target selection
            self.pending_ability = ability
            self.pending_ability_card = card
            self.valid_ability_targets = targets
            self.log(f"Выберите цель для {ability.name}")
            return True

        return False

    def _get_ability_targets(self, card: Card, ability: Ability) -> List[int]:
        """Get valid target positions for an ability."""
        targets = []

        if ability.range == 0:
            # Self only
            return [card.position] if card.position is not None else []

        # Get cells in range
        if card.position is None:
            return []

        if ability.range == 1:
            cells = self.board.get_adjacent_cells(card.position, include_diagonals=True)
        else:
            # Range 2+ - all cells within range (respecting min_range)
            # For ranged abilities, min_range uses Chebyshev distance to exclude
            # all 8 adjacent cells (orthogonal + diagonal)
            cells = set()
            for pos in range(30):
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

            # Lunge: check path doesn't go through enemies (only orthogonal)
            if ability.id.startswith("lunge"):
                if not self._is_valid_lunge_path(card.position, pos, card.player):
                    continue

            if ability.target_type == TargetType.ENEMY and target_card.player != card.player:
                targets.append(pos)
            elif ability.target_type == TargetType.ALLY and target_card.player == card.player and target_card != card:
                targets.append(pos)
            elif ability.target_type == TargetType.ANY:
                # ANY includes self, allies, and enemies
                targets.append(pos)

        # Ranged abilities (range >= 2, except lunge and web_throw) can always target flying creatures
        # Web throw cannot target flyers (can't web a flying creature)
        if ability.range >= 2 and not ability.id.startswith("lunge") and ability.id != "web_throw":
            for flying_card in self.board.get_flying_cards():
                if flying_card.position is not None and flying_card.position not in targets:
                    if ability.target_type == TargetType.ENEMY and flying_card.player != card.player:
                        targets.append(flying_card.position)
                    elif ability.target_type == TargetType.ALLY and flying_card.player == card.player and flying_card != card:
                        targets.append(flying_card.position)
                    elif ability.target_type == TargetType.ANY:
                        targets.append(flying_card.position)

        return targets

    def _is_valid_lunge_path(self, from_pos: int, to_pos: int, player: int) -> bool:
        """Check if lunge path is valid (orthogonal, no enemies in between)."""
        from_col, from_row = from_pos % 5, from_pos // 5
        to_col, to_row = to_pos % 5, to_pos // 5

        # Must be orthogonal (same row or same column)
        if from_col != to_col and from_row != to_row:
            return False

        # Check the cell in between
        mid_col = (from_col + to_col) // 2
        mid_row = (from_row + to_row) // 2
        mid_pos = mid_row * 5 + mid_col

        mid_card = self.board.get_card(mid_pos)
        # Can go through empty or friendly, not through enemy
        if mid_card is not None and mid_card.player != player:
            return False

        return True

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
        if not self.pending_ability or not self.pending_ability_card:
            return False

        if pos not in self.valid_ability_targets:
            return False

        target = self.board.get_card(pos)
        if not target:
            return False

        card = self.pending_ability_card
        result = self._execute_ability(card, self.pending_ability, target)
        self.cancel_ability()

        # Clear actions if card is now tapped
        if card.tapped:
            self.valid_moves = []
            self.valid_attacks = []

        return result

    def _execute_ability(self, card: Card, ability: Ability, target: Card) -> bool:
        """Execute an ability on a target."""
        # Heal
        if ability.heal_amount > 0:
            # Emit heal arrow (only if targeting another card)
            if card != target:
                self.emit_arrow(card.position, target.position, 'heal')
            healed = target.heal(ability.heal_amount)
            self.log(f"{card.name} использует {ability.name}: {target.name} +{healed} HP")
            self.emit_heal(target.position, healed)
            self.emit_clear_arrows()

        # Damage (for ranged attacks with ranged_damage)
        if ability.ranged_damage and not ability.id.startswith("lunge"):
            # Use ranged attack with ability's damage values
            return self._ranged_attack(card, target, ability)

        # Lunge attack (fixed damage, no counter)
        if ability.id.startswith("lunge"):
            return self._lunge_attack(card, target, ability)

        # Powerful blow (bonus damage attack)
        if ability.id == "powerful_blow":
            return self._powerful_attack(card, target, ability.damage_amount)

        # Magical strike (fixed damage, ignores reductions)
        if ability.id == "magical_strike":
            return self._magical_strike(card, target, ability.damage_amount)

        # Inspire (buff ally)
        if ability.id == "inspire":
            target.temp_attack_bonus += ability.bonus_attack
            self.log(f"{card.name} воодушевляет {target.name} (+{ability.bonus_attack} к атаке)")
            card.tap()
            card.put_ability_on_cooldown(ability.id, ability.cooldown)
            return True

        # Web throw (apply web status)
        if ability.id == "web_throw":
            self.emit_arrow(card.position, target.position, 'attack')
            target.webbed = True
            self.log(f"{card.name} опутывает {target.name} паутиной!")
            self.emit_clear_arrows()
            card.tap()
            card.put_ability_on_cooldown(ability.id, ability.cooldown)
            return True

        # Gain counter (for discharge)
        if ability.id == "gain_counter":
            if card.max_counters > 0 and card.counters >= card.max_counters:
                self.log(f"{card.name}: максимум фишек ({card.max_counters})")
                return False
            card.counters += 1
            self.log(f"{card.name} получает фишку ({card.counters}/{card.max_counters})")
            card.tap()
            return True

        # Борг: tap to gain counter (max 1)
        if ability.id == "borg_counter":
            if card.counters >= 1:
                self.log(f"{card.name}: уже есть фишка")
                return False
            card.counters += 1
            self.log(f"{card.name} разбегается (фишка: {card.counters})")
            card.tap()
            return True

        # Борг: spend counter for 3 damage + stun
        if ability.id == "borg_strike":
            if card.counters < 1:
                self.log(f"{card.name}: нужна фишка")
                return False
            if not target:
                self.log(f"{card.name}: нет цели")
                return False

            card.counters -= 1
            damage = ability.damage_amount  # Fixed 3 damage
            self.emit_arrow(card.position, target.position, 'attack')

            # If target is tapped, stun it (won't untap next turn)
            if target.tapped:
                target.stunned = True
                self.log(f"{card.name} бьёт рогами {target.name}: {damage} урона + оглушение!")
            else:
                self.log(f"{card.name} бьёт рогами {target.name}: {damage} урона")

            dealt, webbed = self._deal_damage(target, damage)
            self.emit_clear_arrows()
            self._handle_death(target, card)
            card.tap()
            self._check_winner()
            return True

        # Axe tap: tap to gain a counter
        if ability.id == "axe_tap":
            if card.max_counters == 0 or card.counters < card.max_counters:
                card.counters += 1
                self.log(f"{card.name} кует: +1 фишка ({card.counters})")
            else:
                self.log(f"{card.name}: максимум фишек")
            card.tap()
            return True

        # Axe strike: magical strike with counter-based damage (0-1-2 + counters spent)
        if ability.id == "axe_strike":
            counters_spent = self.selected_counters
            if counters_spent < 0 or counters_spent > card.counters:
                self.log(f"{card.name}: недостаточно фишек")
                return False

            # Roll for tier (like regular attack)
            roll = self.roll_dice()
            tier = self._get_attack_tier(roll)
            tier_names = ["слабый", "средний", "сильный"]
            base_damage = [0, 1, 2][tier]  # Base 0-1-2
            total_damage = base_damage + counters_spent

            card.counters -= counters_spent
            self.emit_arrow(card.position, target.position, 'attack')
            self.log(f"{card.name} маг. удар ({tier_names[tier]}, кубик {roll}): {base_damage}+{counters_spent} фишек = {total_damage}")

            # Set last_combat to display dice roll
            self.last_combat = CombatResult(
                attacker_roll=roll,
                defender_roll=0,
                attacker_damage_dealt=total_damage,
                defender_damage_dealt=0,
                attacker_name=card.name,
                defender_name=target.name
            )

            # Check magic immunity
            if target.has_ability("magic_immune"):
                self.log(f"  -> {target.name} защита от магии!")
                self.emit_clear_arrows()
                card.tap()
                return True

            self._deal_damage(target, total_damage, is_magical=True)
            self.emit_clear_arrows()
            self._handle_death(target, card)
            card.tap()

            # Clear counter selection state
            self.counter_selection_card = None
            self.counter_selection_ability = None
            self.selected_counters = 0

            self._check_winner()
            return True

        # Discharge (deal damage based on counters)
        if ability.id == "discharge":
            base_damage = ability.damage_amount
            bonus_damage = card.counters * 3  # +3 per counter
            total_damage = base_damage + bonus_damage
            self.emit_arrow(card.position, target.position, 'attack')

            # Always lose a фишка when discharging
            if card.counters > 0:
                card.counters -= 1

            # Check for discharge immunity
            if target.has_ability("magic_immune") or target.has_ability("discharge_immune"):
                self.log(f"{card.name} разряд на {target.name}: защита от разрядов!")
                self.log(f"  [Осталось фишек: {card.counters}]")
                self.emit_clear_arrows()
                card.tap()
                return True

            dealt, webbed = self._deal_damage(target, total_damage, is_magical=True)
            if not webbed:
                self.log(f"{card.name} разряд на {target.name}: {total_damage} урона ({base_damage}+{bonus_damage})")
                self.log(f"  [Осталось фишек: {card.counters}]")
            self.emit_clear_arrows()
            self._handle_death(target, card)
            card.tap()
            self._check_winner()
            return True

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
                if ability.id == "attack_exp":
                    bonus += ability.bonus_attack
                # OVA+1: always +1 to attack dice
                elif ability.id == "ova_1":
                    bonus += ability.bonus_attack
                # Note: anti_magic gives +1 damage, not dice bonus - handled in _get_attack_bonus
                # Edge column attack: +1 ОвА on flanks (columns 0 or 4)
                elif ability.id == "edge_column_attack" and col in (0, 4):
                    bonus += 1
        return bonus

    def _get_defense_dice_bonus(self, card: Card) -> int:
        """Get dice bonus for defending (passive abilities like ОвЗ)."""
        bonus = 0
        col = self._get_card_column(card)
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.ability_type == AbilityType.PASSIVE:
                if ability.id == "defense_exp":
                    bonus += ability.bonus_attack  # Reusing bonus_attack field
                # OVZ+1: always +1 to defense dice
                elif ability.id == "ovz_1":
                    bonus += ability.bonus_attack
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
                if ability.bonus_attack > 0:
                    return True
                # Check for permanent OVZ (defense dice bonus)
                if ability.id in ("defense_exp", "ovz_1"):
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

    def _process_defender_triggers(self, defender: Card):
        """Process ON_DEFEND triggered abilities when card becomes a defender."""
        for ability_id in defender.stats.ability_ids:
            ability = get_ability(ability_id)
            if not ability or ability.trigger != AbilityTrigger.ON_DEFEND:
                continue

            # defender_buff: +2 attack and +1 dice bonus (lasts until end of owner's next turn)
            if ability.id == "defender_buff":
                defender.defender_buff_attack = ability.bonus_attack  # +2
                defender.defender_buff_dice = 1  # ОвА+1
                defender.defender_buff_turns = 1  # Lasts through 1 owner turn-end
                self.log(f"  -> {defender.name}: +{ability.bonus_attack} к удару, ОвА+1 (до конца след. хода)")

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

        # Enter counter shot targeting mode
        self.pending_counter_shot = attacker
        self.counter_shot_targets = valid_targets
        self.log(f"{attacker.name}: выберите цель для выстрела")

    def select_counter_shot_target(self, pos: int) -> bool:
        """Player selects target for counter shot."""
        if not self.pending_counter_shot or pos not in self.counter_shot_targets:
            return False

        attacker = self.pending_counter_shot
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

        self.pending_counter_shot = None
        self.counter_shot_targets = []
        return True

    @property
    def awaiting_counter_shot(self) -> bool:
        """Check if waiting for counter shot target selection."""
        return self.pending_counter_shot is not None

    @property
    def awaiting_movement_shot(self) -> bool:
        """Check if waiting for movement shot target selection."""
        return self.pending_movement_shot is not None

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

        # Ground targets within Manhattan range 3, but Chebyshev >= 2 (not adjacent)
        for target_card in self.board.get_all_cards(include_flying=False):
            if not target_card.is_alive or target_card.position is None or target_card == card:
                continue
            manhattan = self._get_distance(card.position, target_card.position)
            chebyshev = self._get_chebyshev_distance(card.position, target_card.position)
            if manhattan <= 3 and chebyshev >= 2:
                valid_targets.append(target_card.position)

        # Flying targets (ranged attacks can always target flyers)
        for target_card in self.board.get_flying_cards():
            if target_card.is_alive and target_card.position not in valid_targets:
                valid_targets.append(target_card.position)

        if not valid_targets:
            return

        # Enter movement shot targeting mode (optional)
        self.pending_movement_shot = card
        self.movement_shot_targets = valid_targets
        self.log(f"{card.name}: можно выстрелить (необязательно)")

    def select_movement_shot_target(self, pos: int) -> bool:
        """Player selects target for movement shot."""
        if not self.pending_movement_shot or pos not in self.movement_shot_targets:
            return False

        shooter = self.pending_movement_shot
        target = self.board.get_card(pos)

        if not target:
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

        self.pending_movement_shot = None
        self.movement_shot_targets = []
        return True

    def skip_movement_shot(self):
        """Skip the movement shot opportunity."""
        if self.pending_movement_shot:
            self.log(f"{self.pending_movement_shot.name}: выстрел пропущен")
            self.pending_movement_shot = None
            self.movement_shot_targets = []

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
        # Enter heal confirmation mode
        self.pending_heal_confirm = (attacker, heal_amount)
        self.log(f"{attacker.name}: лечиться на {heal_amount}? (напротив: {front_card.name})")

    def confirm_heal_on_attack(self, accept: bool) -> bool:
        """Player confirms or declines optional heal."""
        if not self.pending_heal_confirm:
            return False
        attacker, heal_amount = self.pending_heal_confirm
        if accept and attacker.is_alive:
            healed = attacker.heal(heal_amount)
            if healed > 0:
                self.emit_heal(attacker.position, healed)
                self.log(f"  -> {attacker.name} +{healed} HP")
        else:
            self.log(f"  -> {attacker.name} отказался от лечения")
        self.pending_heal_confirm = None
        return True

    @property
    def awaiting_heal_confirm(self) -> bool:
        """Check if waiting for heal confirmation."""
        return self.pending_heal_confirm is not None

    def _process_hellish_stench(self, attacker: Card, target: Card, was_target_tapped: bool, damage_dealt: int):
        """Process hellish_stench ability - target must tap or take 2 damage.

        Only triggers if attacker dealt at least some damage (weak attack or better).
        """
        if "hellish_stench" not in attacker.stats.ability_ids:
            return
        # Only triggers when attacking an untapped (open) creature
        if was_target_tapped:
            return
        # Only triggers if damage was actually dealt
        if damage_dealt <= 0:
            return
        if not target.is_alive or target.position is None:
            return
        # If target is already tapped (from combat or other effect), no choice needed
        if target.tapped:
            return

        ability = get_ability("hellish_stench")
        damage = ability.damage_amount if ability else 2

        # Enter stench choice mode - target's controller must choose
        self.pending_stench_choice = (attacker, target, damage)
        self.log(f"{attacker.name}: Адское зловоние! {target.name} закрывается или получает {damage} урона")

    def resolve_stench_choice(self, tap: bool) -> bool:
        """Target's controller chooses: tap or take damage."""
        if not self.pending_stench_choice:
            return False

        attacker, target, damage = self.pending_stench_choice

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

        self.pending_stench_choice = None
        return True

    @property
    def awaiting_stench_choice(self) -> bool:
        """Check if waiting for stench choice."""
        return self.pending_stench_choice is not None

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
            self._apply_lunge_front_buff(attacker)
            self._process_heal_on_attack(attacker, target)

        self._handle_death(target, attacker)
        attacker.tap()
        self.valid_moves = []
        self.valid_attacks = []
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
            front_row = row + 1  # Player 1 moves up
        else:
            front_row = row - 1  # Player 2 moves down

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
        dice_context = {
            'type': 'ranged',
            'attacker': attacker,
            'target': target,
            'ability': ability,
            'ranged_type': ranged_type,
            'atk_roll': atk_roll,
            'atk_modifier': 0,  # Luck can modify this
        }

        # Check if we should enter priority phase
        if self._enter_priority_phase(dice_context):
            # Priority phase started - ranged attack will continue after priority resolves
            return True

        # No priority phase needed - continue immediately
        return self._finish_ranged_attack(dice_context)

    def _finish_ranged_attack(self, dice_context: dict) -> bool:
        """Finish ranged attack after priority phase (or immediately if no priority)."""
        attacker = dice_context['attacker']
        target = dice_context['target']
        ability = dice_context.get('ability')
        ranged_type = dice_context['ranged_type']

        # Apply modifiers from luck
        atk_roll = dice_context['atk_roll'] + dice_context.get('atk_modifier', 0)
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

    def _powerful_attack(self, attacker: Card, target: Card, bonus_damage: int) -> bool:
        """Execute a powerful melee attack with bonus damage."""
        if target.position not in self.board.get_adjacent_cells(attacker.position, True):
            self.log("Цель слишком далеко!")
            return False

        self.log(f"{attacker.name} наносит мощный удар!")

        # If webbed, skip dice rolls entirely
        if target.webbed:
            dealt, _ = self._deal_damage(target, 0)  # Just triggers web removal
            self.last_combat = CombatResult(0, 0, 0, 0, attacker_name=attacker.name, defender_name=target.name)
        else:
            atk_roll = self.roll_dice()
            def_roll = self.roll_dice() if not target.tapped else 0
            roll_diff = atk_roll - def_roll
            dmg_to_def, dmg_to_atk = self.calculate_damage(roll_diff, attacker, target, not target.tapped, atk_roll)
            dmg_to_def += bonus_damage

            dealt, _ = self._deal_damage(target, dmg_to_def)
            attacker.take_damage(dmg_to_atk)
            self.emit_damage(attacker.position, dmg_to_atk)

            self.last_combat = CombatResult(atk_roll, def_roll, dealt, dmg_to_atk, attacker_name=attacker.name, defender_name=target.name)
            self.log(f"  [{atk_roll}] vs [{def_roll}]")
            if dealt > 0:
                self.log(f"  -> {target.name} получил {dealt} урона")
            if dmg_to_atk > 0:
                self.log(f"  -> {attacker.name} получил {dmg_to_atk} урона")

        self._handle_death(target, attacker)
        if self._handle_death(attacker, target):
            self.deselect_card()
        else:
            attacker.tap()
            attacker.put_ability_on_cooldown("powerful_blow", 2)
            self.valid_moves = []
            self.valid_attacks = []
            self.attack_mode = False

        self._check_winner()
        return True

    def _magical_strike(self, attacker: Card, target: Card, damage: int) -> bool:
        """Execute magical strike (fixed damage, ignores reductions and armor)."""
        self.emit_arrow(attacker.position, target.position, 'magic')
        self.log(f"{attacker.name} магический удар!")

        # Check magic immunity
        if "magic_immune" in target.stats.ability_ids:
            self.log(f"  -> {target.name}: защита от магии!")
            self.emit_clear_arrows()
            dealt = 0
        else:
            dealt, webbed = self._deal_damage(target, damage, is_magical=True)
            if not webbed:
                self.emit_clear_arrows()
                self.log(f"  -> {target.name}: -{dealt} HP (магия)")

        self.last_combat = CombatResult(0, 0, dealt, 0, attacker_name=attacker.name, defender_name=target.name)
        self._handle_death(target, attacker)
        attacker.tap()
        self.valid_moves = []
        self.valid_attacks = []
        self.attack_mode = False
        self._check_winner()
        return True

    def cancel_ability(self):
        """Cancel pending ability targeting."""
        self.pending_ability = None
        self.pending_ability_card = None
        self.valid_ability_targets = []
        # Also cancel counter selection if active
        self.awaiting_counter_selection = False
        self.counter_selection_card = None
        self.counter_selection_ability = None
        self.selected_counters = 0

    def set_counter_selection(self, count: int):
        """Set the number of counters to spend."""
        if not self.awaiting_counter_selection or not self.counter_selection_card:
            return
        max_counters = self.counter_selection_card.counters
        self.selected_counters = max(1, min(count, max_counters))

    def confirm_counter_selection(self) -> bool:
        """Confirm counter selection and proceed to target selection."""
        if not self.awaiting_counter_selection or not self.counter_selection_card:
            return False

        card = self.counter_selection_card
        ability_id = self.counter_selection_ability
        ability = get_ability(ability_id)

        if not ability:
            self.cancel_ability()
            return False

        # Clear counter selection state but keep selected_counters for damage calc
        self.awaiting_counter_selection = False

        # Proceed to target selection
        targets = self._get_ability_targets(card, ability)
        if not targets:
            self.log("Нет доступных целей!")
            self.cancel_ability()
            return False

        self.pending_ability = ability
        self.pending_ability_card = card
        self.valid_ability_targets = targets
        self.log(f"Выберите цель для {ability.name} ({self.selected_counters} фишек)")
        return True

    # =========================================================================
    # PRIORITY SYSTEM (Instant Abilities - Внезапные действия)
    # =========================================================================

    def _get_instant_cards(self, player: int) -> List[Tuple[Card, Ability]]:
        """Get all cards with instant abilities for a player (internal, no state check)."""
        # Get card IDs already on the stack (can't use instant twice)
        card_ids_on_stack = {instant['card'].id for instant in self.instant_stack}

        # Get attacker and defender IDs - they can't use instants on their own combat
        combat_card_ids = set()
        if self.pending_dice_roll:
            attacker = self.pending_dice_roll.get('attacker')
            defender = self.pending_dice_roll.get('defender')
            if attacker:
                combat_card_ids.add(attacker.id)
            if defender:
                combat_card_ids.add(defender.id)

        result = []
        for card in self.board.get_all_cards(player):
            if not card.is_alive or card.tapped:
                continue
            # Skip cards already on the stack
            if card.id in card_ids_on_stack:
                continue
            # Skip attacker/defender - can't modify own combat
            if card.id in combat_card_ids:
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

    def _apply_instant_effect(self, instant: dict):
        """Apply the effect of a resolved instant ability."""
        card = instant['card']
        ability = instant['ability']
        option = instant['option']

        if ability.id == "luck":
            # Parse option: atk_plus1, atk_minus1, atk_reroll, def_plus1, def_minus1, def_reroll
            target = 'atk' if option.startswith('atk_') else 'def'
            action = option.split('_')[1]  # plus1, minus1, reroll

            # For ranged attacks, there's only attacker roll (target is 'target', not 'defender')
            is_ranged = self.pending_dice_roll.get('type') == 'ranged'

            # Ranged attacks only have attacker roll, ignore defender modifications
            if is_ranged and target == 'def':
                self.log(f"  -> {card.name}: Нет броска защитника для изменения")
                return

            if target == 'atk':
                target_name = self.pending_dice_roll['attacker'].name
            else:
                # For combat, there's a 'defender' key; for ranged, use 'target'
                target_name = self.pending_dice_roll.get('defender', self.pending_dice_roll.get('target')).name

            modifier_key = f'{target}_modifier'
            roll_key = f'{target}_roll'

            if action == 'plus1':
                self.pending_dice_roll[modifier_key] += 1
                self.log(f"  -> {card.name}: Удача +1 к броску {target_name}")
            elif action == 'minus1':
                self.pending_dice_roll[modifier_key] -= 1
                self.log(f"  -> {card.name}: Удача -1 к броску {target_name}")
            elif action == 'reroll':
                new_roll = random.randint(1, 6)
                old_roll = self.pending_dice_roll[roll_key]
                self.pending_dice_roll[roll_key] = new_roll
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

        # Check if this card already has an instant on the stack (can only use once per stack)
        for instant in self.instant_stack:
            if instant['card'].id == card.id:
                self.log(f"{card.name}: уже использовал способность")
                return False

        # Add to stack
        self.instant_stack.append({
            'card': card,
            'ability': ability,
            'option': option
        })

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

    def move_card(self, to_pos: int) -> bool:
        """Move selected card to position."""
        # Clear previous dice display
        self.last_combat = None

        # Block during priority phase
        if self.priority_phase:
            return False

        # Block movement during forced attack
        if self.has_forced_attack:
            self.log("Сначала атакуйте закрытого врага!")
            return False

        if not self.selected_card or to_pos not in self.valid_moves:
            return False

        card = self.selected_card
        from_pos = card.position

        # Calculate actual distance moved (Manhattan distance for orthogonal movement)
        from_col, from_row = from_pos % 5, from_pos // 5
        to_col, to_row = to_pos % 5, to_pos // 5
        distance = abs(to_col - from_col) + abs(to_row - from_row)

        if self.board.move_card(from_pos, to_pos):
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

            # Keep card selected but refresh valid moves
            self.valid_moves = self.board.get_valid_moves(card) if card.can_act else []
            self.valid_attacks = []
            self.attack_mode = False
            return True
        return False

    def roll_dice(self) -> int:
        """Roll a D6."""
        return random.randint(1, 6)

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
        """Get attack values for display, including all flat bonuses.

        This includes: base attack, temp bonuses, defender buff, formation bonus.
        Does NOT include tier-specific bonuses (like edge column +1 to medium/strong).
        """
        base = card.get_effective_attack()  # Already includes temp_attack_bonus and defender_buff

        # Add formation attack bonus
        formation_bonus = 0
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.is_formation and card.in_formation:
                formation_bonus += ability.formation_attack_bonus

        return (base[0] + formation_bonus, base[1] + formation_bonus, base[2] + formation_bonus)

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

    def attack(self, target_pos: int) -> bool:
        """Initiate attack - may trigger defender choice or friendly fire confirmation."""
        # Clear previous dice display
        self.last_combat = None

        # Block during priority phase
        if self.priority_phase:
            return False

        if not self.selected_card or target_pos not in self.valid_attacks:
            return False

        attacker = self.selected_card
        target = self.board.get_card(target_pos)

        if not target:
            return False

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
            # Enter defender choice mode
            self.awaiting_defender = True
            self.pending_attack = PendingAttack(
                attacker=attacker,
                original_target=target,
                valid_defenders=valid_defenders
            )
            self.log(f"{attacker.name} атакует {target.name}!")
            self.log(f"Игрок {target.player}: выберите защитника")
            return True
        else:
            # No defenders available - resolve immediately
            return self._resolve_combat(attacker, target)

    def choose_defender(self, defender: Card) -> bool:
        """Defender player chooses to intercept with this card."""
        if not self.awaiting_defender or not self.pending_attack:
            return False

        if defender not in self.pending_attack.valid_defenders:
            return False

        attacker = self.pending_attack.attacker
        self.log(f"{defender.name} перехватывает атаку!")

        # Trigger ON_DEFEND abilities before combat
        self._process_defender_triggers(defender)

        # Clear defender state
        self.awaiting_defender = False
        self.pending_attack = None

        # Resolve combat with the intercepting defender
        result = self._resolve_combat(attacker, defender)

        # Intercepting defender taps after combat (if still alive)
        # Unless they have defender_no_tap ability
        if defender.is_alive and "defender_no_tap" not in defender.stats.ability_ids:
            defender.tap()

        return result

    def skip_defender(self) -> bool:
        """Defender player chooses not to intercept."""
        if not self.awaiting_defender or not self.pending_attack:
            return False

        attacker = self.pending_attack.attacker
        target = self.pending_attack.original_target
        self.log("Защита не выставлена.")

        # Clear defender state
        self.awaiting_defender = False
        self.pending_attack = None

        # Resolve combat with original target
        return self._resolve_combat(attacker, target)

    def _resolve_combat(self, attacker: Card, defender: Card) -> bool:
        """Resolve combat between attacker and defender."""
        # If defender is webbed, skip dice rolls entirely
        if defender.webbed:
            dealt, _ = self._deal_damage(defender, 0)  # Just triggers web removal
            self.last_combat = CombatResult(0, 0, 0, 0, attacker_name=attacker.name, defender_name=defender.name)
            attacker.tap()
            self.valid_moves = []
            self.valid_attacks = []
            self._check_winner()
            return True

        # Always roll dice
        atk_roll = self.roll_dice()
        def_roll = 0 if defender.tapped else self.roll_dice()
        atk_bonus = self._get_attack_dice_bonus(attacker, defender)
        def_bonus = 0 if defender.tapped else self._get_defense_dice_bonus(defender)

        # Log the initial rolls
        self.log(f"{attacker.name} [{atk_roll}] vs {defender.name} [{def_roll}]")

        # Check if dice modifications matter (constant damage = all attack values equal)
        atk_values = attacker.get_effective_attack()
        atk_is_constant = atk_values[0] == atk_values[1] == atk_values[2]
        def_values = defender.get_effective_attack()
        def_is_constant = def_values[0] == def_values[1] == def_values[2]
        dice_matter = not (atk_is_constant and (defender.tapped or def_is_constant))

        # Create dice context for priority phase
        dice_context = {
            'type': 'combat',
            'attacker': attacker,
            'defender': defender,
            'atk_roll': atk_roll,
            'atk_bonus': atk_bonus,
            'def_roll': def_roll,
            'def_bonus': def_bonus,
            'atk_modifier': 0,  # Instant abilities can modify attacker's roll
            'def_modifier': 0,  # Instant abilities can modify defender's roll
            'dice_matter': dice_matter,  # Whether dice modifications would affect outcome
            'defender_was_tapped': defender.tapped,  # Store tapped state at roll time
        }

        # Check if we should enter priority phase (only if dice matter)
        if dice_matter and self._enter_priority_phase(dice_context):
            # Priority phase started - combat will continue after priority resolves
            return True

        # No priority phase needed - continue immediately
        return self._finish_combat(dice_context)

    def _finish_combat(self, dice_context: dict, force_reduced: bool = False) -> bool:
        """Finish combat after priority phase (or immediately if no priority).

        Args:
            dice_context: Combat context with rolls, cards, etc.
            force_reduced: If True, use reduced attack tier (exchange choice to avoid counter)
        """
        attacker = dice_context['attacker']
        defender = dice_context['defender']
        atk_roll = dice_context['atk_roll'] + dice_context.get('atk_modifier', 0)
        atk_bonus = dice_context['atk_bonus']
        def_roll = dice_context['def_roll'] + dice_context.get('def_modifier', 0)
        def_bonus = dice_context['def_bonus']

        # Clear pending dice roll
        self.pending_dice_roll = None

        # Use tapped state from when dice were rolled (not current state)
        defender_was_tapped = dice_context.get('defender_was_tapped', defender.tapped)

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
            if is_exchange and not force_reduced and not self.awaiting_exchange_choice and not dice_context.get('exchange_resolved'):
                # Enter exchange choice state
                self.awaiting_exchange_choice = True
                self.exchange_context = dice_context.copy()
                # Store who chooses (player with higher roll)
                self.exchange_context['attacker_advantage'] = roll_diff > 0
                self.exchange_context['roll_diff'] = roll_diff
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
        dealt, _ = self._deal_damage(defender, dmg_to_def)
        attacker.take_damage(dmg_to_atk)
        self.emit_damage(attacker.position, dmg_to_atk)
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

        # Process hellish_stench (only triggers vs untapped targets and if damage was dealt)
        if attacker.is_alive and defender.is_alive:
            self._process_hellish_stench(attacker, defender, defender_was_tapped, dealt)

        # Handle deaths
        self._handle_death(defender, attacker)

        if self._handle_death(attacker, defender):
            self.deselect_card()
        else:
            attacker.tap()
            self.valid_moves = []
            self.valid_attacks = []
            self.attack_mode = False

        # Update forced attackers after combat
        self._update_forced_attackers()

        self._check_winner()
        return True

    def continue_after_priority(self) -> bool:
        """Continue combat/action after priority phase resolves."""
        if not self.pending_dice_roll:
            return False

        dice_context = self.pending_dice_roll
        if dice_context['type'] == 'combat':
            return self._finish_combat(dice_context)
        elif dice_context['type'] == 'ranged':
            return self._finish_ranged_attack(dice_context)
        return False

    def resolve_exchange_choice(self, reduce_damage: bool) -> bool:
        """Handle player's choice during exchange.

        Args:
            reduce_damage: True to reduce attack tier and avoid counter,
                          False to deal full damage but take counter
        """
        if not self.awaiting_exchange_choice or not self.exchange_context:
            return False

        dice_context = self.exchange_context
        dice_context['exchange_resolved'] = True  # Mark that exchange was handled
        self.awaiting_exchange_choice = False
        self.exchange_context = None

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
            self.pending_movement_shot = None
            self.movement_shot_targets = []

        self.deselect_card()

        # Tick defender buff duration for current player's cards (expires at end of their turn)
        for card in self.board.get_all_cards(player=self.current_player):
            card.tick_defender_buff()

        # Switch player
        if self.current_player == 1:
            self.current_player = 2
        else:
            self.current_player = 1
            self.turn_number += 1

        self.start_turn()

    def handle_click(self, pos: int) -> bool:
        """Handle a click on board position. Returns True if action taken."""
        if self.phase == GamePhase.GAME_OVER:
            return False

        if self.phase == GamePhase.SETUP:
            # During setup, clicking selects placement position
            hand = self.get_current_hand()
            if hand:
                # Auto-place first card in hand at clicked position
                return self.place_card_from_hand(hand[0], pos)
            return False

        # Handle counter shot target selection mode
        if self.awaiting_counter_shot:
            if pos in self.counter_shot_targets:
                return self.select_counter_shot_target(pos)
            # Clicking elsewhere does nothing during counter shot selection
            return False

        # Handle movement shot target selection (use skip button to skip)
        if self.awaiting_movement_shot:
            if pos in self.movement_shot_targets:
                return self.select_movement_shot_target(pos)
            # Clicking elsewhere does nothing - must use skip button
            return False

        # Handle Valhalla target selection mode
        if self.awaiting_valhalla:
            if pos in self.valhalla_targets:
                return self.select_valhalla_target(pos)
            # Clicking elsewhere does nothing during Valhalla selection
            return False

        # Handle defender choice mode
        if self.awaiting_defender and self.pending_attack:
            card = self.board.get_card(pos)
            if card and card in self.pending_attack.valid_defenders:
                return self.choose_defender(card)
            # Clicking elsewhere does nothing during defender choice
            return False

        # Handle ability target selection mode
        if self.pending_ability and self.pending_ability_card:
            if pos in self.valid_ability_targets:
                return self.select_ability_target(pos)
            # Clicking elsewhere cancels ability
            self.cancel_ability()
            return False

        # Main phase - normal actions
        if self.selected_card:
            # Check if clicking on a valid move
            if pos in self.valid_moves:
                return self.move_card(pos)
            # Check if clicking on a valid attack target
            if pos in self.valid_attacks:
                return self.attack(pos)

        # Select/deselect card at position
        return self.select_card(pos)
