"""Game setup, placement, and turn management."""
from typing import List, TYPE_CHECKING

from ..card import Card, create_card
from ..card_database import create_starter_deck, create_starter_deck_p2
from ..constants import GamePhase
from ..abilities import get_ability, AbilityType, AbilityTrigger
from ..ability_handlers import get_trigger_handler
from ..interaction import InteractionKind, interaction_valhalla
from ..commands import evt_turn_started, evt_turn_ended

if TYPE_CHECKING:
    from ..abilities import Ability


class SetupMixin:
    """Mixin for game setup, placement, and turn management."""

    def setup_game(self, p1_squad: list = None, p2_squad: list = None):
        """Initialize a new game."""
        deck_p1 = p1_squad if p1_squad else create_starter_deck()
        deck_p2 = p2_squad if p2_squad else create_starter_deck_p2()

        for name in deck_p1:
            card = create_card(name, player=1, card_id=self._next_card_id)
            self._next_card_id += 1
            self.hand_p1.append(card)

        for name in deck_p2:
            card = create_card(name, player=2, card_id=self._next_card_id)
            self._next_card_id += 1
            self.hand_p2.append(card)

        self.hand_p1.sort(key=lambda c: c.stats.cost, reverse=True)
        self.hand_p2.sort(key=lambda c: c.stats.cost, reverse=True)

        self.phase = GamePhase.SETUP
        self.current_player = 1
        self.log("Игра началась! Расставьте существ.")

    def setup_game_with_placement(self, p1_cards: List[Card], p2_cards: List[Card]):
        """Initialize game with pre-placed cards from placement phase."""
        # Place all cards at their assigned positions from placement phase
        for card in p1_cards:
            self.board.place_card(card, card.position)

        for card in p2_cards:
            self.board.place_card(card, card.position)

        # Reveal cards - P1 reveals all (flyers move to flying zone), P2 keeps back row hidden
        self._reveal_cards_at_game_start()

        self.phase = GamePhase.MAIN
        self.turn_number = 1
        self.current_player = 1

        self.recalculate_formations()
        self.log("Карты расставлены!")
        self.start_turn()

    def auto_place_for_testing(self):
        """Auto-place some cards for quick testing."""
        positions_p1 = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
        positions_p2 = [29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15]

        def select_cards(hand, count):
            flying = [c for c in hand if c.stats.is_flying]
            ground = [c for c in hand if not c.stats.is_flying]

            priority_names = ("Оури", "Паук-пересмешник", "Матросы Аделаиды", "Эльфийский воин",
                            "Ловец удачи", "Горный великан", "Ледовый охотник", "Костедробитель",
                            "Борг", "Гном-басаарг", "Мастер топора", "Повелитель молний",
                            "Смотритель горнила", "Хранитель гор", "Мразень", "Овражный гном")
            giants = [c for c in ground if c.name == "Горный великан"]
            hunters = [c for c in ground if c.name == "Ледовый охотник"]
            crushers = [c for c in ground if c.name == "Костедробитель"]
            borgs = [c for c in ground if c.name == "Борг"]
            dwarves = [c for c in ground if c.name == "Гном-басаарг"]
            axe_masters = [c for c in ground if c.name == "Мастер топора"]
            lightning = [c for c in ground if c.name == "Повелитель молний"]
            furnace = [c for c in ground if c.name == "Смотритель горнила"]
            keepers = [c for c in ground if c.name == "Хранитель гор"]
            frost = [c for c in ground if c.name == "Мразень"]
            ravine = [c for c in ground if c.name == "Овражный гном"]
            ouri = [c for c in ground if c.name == "Оури"]
            spider = [c for c in ground if c.name == "Паук-пересмешник"]
            sailors = [c for c in ground if c.name == "Матросы Аделаиды"]
            elf = [c for c in ground if c.name == "Эльфийский воин"]
            luck = [c for c in ground if c.name == "Ловец удачи"]
            expensive = [c for c in ground if c.stats.cost >= 7 and c.name not in priority_names]
            with_abilities = [c for c in ground if c.stats.ability_ids and c.name not in priority_names and c.stats.cost < 7]
            without_abilities = [c for c in ground if not c.stats.ability_ids and c.stats.cost < 7]
            without_abilities.sort(key=lambda c: c.stats.cost, reverse=True)

            selected_ground = (giants + lightning + axe_masters + dwarves + borgs + furnace +
                             keepers + frost + ravine + luck + hunters[:1] + crushers[:1] +
                             ouri[:1] + expensive[:1] + spider + sailors + elf + hunters[1:] +
                             crushers[1:] + ouri[1:] + expensive[1:] + with_abilities + without_abilities)[:count]
            return selected_ground, flying

        ground_p1, flying_p1 = select_cards(self.hand_p1, len(positions_p1))
        ground_p2, flying_p2 = select_cards(self.hand_p2, len(positions_p2))

        for card, pos in zip(ground_p1, positions_p1):
            self.board.place_card(card, pos)

        for card, pos in zip(ground_p2, positions_p2):
            self.board.place_card(card, pos)

        # P1's flyers go directly to flying zone (revealed at game start)
        for i, card in enumerate(flying_p1[:self.board.FLYING_SLOTS]):
            self.board.place_card(card, self.board.FLYING_P1_START + i)

        # P2's flyers go to back row (hidden) if there's room, otherwise flying zone (revealed)
        p2_back_row = [29, 28, 27, 26, 25]
        used_positions = set(positions_p2[:len(ground_p2)])
        available_back_row = [pos for pos in p2_back_row if pos not in used_positions]

        flying_zone_idx = 0
        for card in flying_p2[:self.board.FLYING_SLOTS]:
            if available_back_row:
                pos = available_back_row.pop(0)
                card.position = pos
                self.board.place_card(card, pos)
            else:
                flying_pos = self.board.FLYING_P2_START + flying_zone_idx
                card.position = flying_pos
                self.board.place_card(card, flying_pos)
                flying_zone_idx += 1

        self.hand_p1.clear()
        self.hand_p2.clear()

        # Reveal cards - P1 reveals all, P2 keeps back row hidden
        self._reveal_cards_at_game_start()

        self.phase = GamePhase.MAIN
        self.turn_number = 1
        self.current_player = 1

        self.recalculate_formations()
        self.log("Карты расставлены!")
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

            # Reveal phase: P1 reveals all, P2 keeps back row hidden
            self._reveal_cards_at_game_start()

            self.phase = GamePhase.MAIN
            self.turn_number = 1
            self.current_player = 1
            self.start_turn()

        return True

    def _reveal_cards_at_game_start(self):
        """Reveal cards at game start. P1 reveals all, P2 keeps back row hidden."""
        # P1 reveals all cards - flyers move to flying zone
        for card in list(self.board.get_all_cards(player=1, include_flying=True)):
            card.face_down = False
            if card.stats.is_flying and card.position is not None and card.position < 30:
                self._move_to_flying_zone(card)

        # P2: reveal front/middle rows only, back row stays hidden
        for card in list(self.board.get_all_cards(player=2, include_flying=True)):
            is_back_row = card.position is not None and 25 <= card.position <= 29

            if is_back_row:
                # Back row stays hidden (including flyers) - they move to flying zone when revealed later
                card.face_down = True
            else:
                # Front/middle rows are revealed - flyers move to flying zone
                card.face_down = False
                if card.stats.is_flying and card.position is not None and card.position < 30:
                    self._move_to_flying_zone(card)

        self.log("Карты вскрыты!")

    def _move_to_flying_zone(self, card: 'Card'):
        """Move a flying creature from ground to flying zone."""
        if card.position is None or card.position >= 30:
            return  # Already in flying zone or not on board

        old_pos = card.position
        flying_start = self.board.FLYING_P1_START if card.player == 1 else self.board.FLYING_P2_START

        # Find free slot in flying zone
        for i in range(self.board.FLYING_SLOTS):
            flying_pos = flying_start + i
            if self.board.get_card(flying_pos) is None:
                self.board.remove_card(old_pos)
                card.position = flying_pos
                self.board.place_card(card, flying_pos)
                self.log(f"{card.name} перемещён в зону полёта")
                return

        self.log(f"Нет места в зоне полёта для {card.name}!")

    def reveal_card(self, card: 'Card') -> bool:
        """Reveal a face-down card. Moves flying creatures to flying zone."""
        from ..commands import evt_card_revealed

        if not card.face_down:
            return False

        card.face_down = False
        self.log(f"{card.name} вскрыт!")

        # Emit reveal event with full card data for network sync
        self.emit_event(evt_card_revealed(card.id, card.to_dict()))

        # Move flying creatures to flying zone
        if card.stats.is_flying and card.position is not None and card.position < 30:
            self._move_to_flying_zone(card)

        return True

    def _reveal_remaining_hidden_cards(self):
        """Reveal all remaining hidden cards for current player at turn start."""
        # Collect hidden cards first to avoid iteration issues during reveal
        hidden_cards = [
            card for card in self.board.get_all_cards(player=self.current_player, include_flying=True)
            if card.face_down
        ]
        for card in hidden_cards:
            self.reveal_card(card)  # This logs and handles flying movement properly

    def start_turn(self):
        """Start a new turn for current player."""
        # At start of P2's turn, reveal all remaining hidden cards
        if self.current_player == 2:
            self._reveal_remaining_hidden_cards()

        # Reset armor for all cards
        for card in self.board.get_all_cards():
            card.reset_armor()
            if card.in_formation:
                bonus = self._get_formation_armor_bonus(card)
                card.formation_armor_remaining = bonus
                card.formation_armor_max = bonus
            else:
                card.formation_armor_remaining = 0
                card.formation_armor_max = 0

        # Reset cards for current player
        for card in self.board.get_all_cards(self.current_player):
            card.reset_for_turn()

        self.last_combat = None
        self.cancel_ability()

        self.log(f"Ход {self.turn_number}: Игрок {self.current_player}")
        self.emit_event(evt_turn_started(self.current_player, self.turn_number))

        # Process Valhalla abilities
        self._process_valhalla_triggers()

        # Process turn start triggers
        self._process_turn_start_triggers()

        # Check for forced attacks
        self._update_forced_attackers()
        if self.has_forced_attack:
            for card_id in self.forced_attackers:
                card = self.get_card_by_id(card_id)
                if card:
                    self.log(f"{card.name} должен атаковать закрытого врага!")

    def end_turn(self):
        """End current player's turn."""
        if self.phase != GamePhase.MAIN:
            return

        if (self.awaiting_defender or self.awaiting_valhalla or
            self.awaiting_counter_shot or self.awaiting_heal_confirm or
            self.awaiting_exchange_choice or self.awaiting_stench_choice):
            return

        if self.has_forced_attack:
            self.log("Сначала атакуйте закрытого врага!")
            return

        if self.awaiting_movement_shot:
            self.interaction = None

        # Tick defender buff duration
        for card in self.board.get_all_cards(player=self.current_player):
            card.tick_defender_buff()

        # Expire flyer attack ability
        for card in self.board.get_all_cards(player=self.current_player):
            if card.can_attack_flyer and card.can_attack_flyer_until_turn <= self.turn_number:
                card.can_attack_flyer = False
                card.can_attack_flyer_until_turn = 0

        # Remove web status
        for card in self.board.get_all_cards(player=self.current_player):
            if card.webbed:
                card.webbed = False
                self.log(f"{card.name} освобождается от паутины")

        self.emit_event(evt_turn_ended(self.current_player))

        # Switch player
        if self.current_player == 1:
            self.current_player = 2
        else:
            self.current_player = 1
            self.turn_number += 1

        self.start_turn()

    # =========================================================================
    # VALHALLA PROCESSING
    # =========================================================================

    def _process_valhalla_triggers(self):
        """Process Valhalla abilities from graveyard."""
        graveyard = self.board.graveyard_p1 if self.current_player == 1 else self.board.graveyard_p2

        self.pending_valhalla = []
        for card in graveyard:
            if not card.killed_by_enemy:
                continue

            for ability_id in card.stats.ability_ids:
                ability = get_ability(ability_id)
                if ability and ability.trigger == AbilityTrigger.VALHALLA:
                    self.pending_valhalla.append((card.id, ability_id))

        self._process_next_valhalla()

    def _process_next_valhalla(self):
        """Process the next Valhalla trigger in queue."""
        if not self.pending_valhalla:
            if self.interaction and self.interaction.kind == InteractionKind.SELECT_VALHALLA_TARGET:
                self.interaction = None
            return

        dead_card_id, ability_id = self.pending_valhalla.pop(0)
        dead_card = self.get_card_by_id(dead_card_id)
        ability = get_ability(ability_id)

        if not dead_card or not ability:
            self._process_next_valhalla()
            return

        allies = self.board.get_all_cards(dead_card.player)
        allies = [c for c in allies if c.is_alive and c.position is not None]

        if not allies:
            self.log(f"Вальхалла {dead_card.name}: нет союзников!")
            self._process_next_valhalla()
            return

        self.interaction = interaction_valhalla(
            source_id=dead_card.id,
            valid_positions=tuple(c.position for c in allies),
            valid_card_ids=tuple(c.id for c in allies),
            acting_player=dead_card.player,
        )
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

        if ability.id == "valhalla_ova":
            target.temp_dice_bonus += ability.dice_bonus_attack
            self.log(f"  -> {target.name} получил ОвА+{ability.dice_bonus_attack}")
        elif ability.id == "valhalla_strike":
            target.temp_attack_bonus += ability.damage_bonus
            self.log(f"  -> {target.name} получил +{ability.damage_bonus} к удару")

        self.interaction = None
        self._process_next_valhalla()

        return True

    @property
    def awaiting_valhalla(self) -> bool:
        """Check if waiting for Valhalla target selection."""
        return self.interaction is not None and self.interaction.kind == InteractionKind.SELECT_VALHALLA_TARGET

    # =========================================================================
    # TURN START TRIGGERS
    # =========================================================================

    def _process_turn_start_triggers(self):
        """Process all ON_TURN_START triggered abilities."""
        ctx = {}
        for card in self.board.get_all_cards(self.current_player):
            for ability_id in card.stats.ability_ids:
                ability = get_ability(ability_id)
                if ability and ability.ability_type == AbilityType.TRIGGERED:
                    if ability.trigger == AbilityTrigger.ON_TURN_START:
                        handler = get_trigger_handler(ability_id)
                        if handler:
                            handler(self, card, ability, ctx)
                        else:
                            self._execute_triggered_ability(card, ability)

    def _execute_triggered_ability(self, card: Card, ability: 'Ability'):
        """Execute a triggered ability automatically (fallback for unregistered triggers)."""
        if ability.heal_amount > 0 and card.curr_life < card.life:
            healed = card.heal(ability.heal_amount)
            if healed > 0:
                self.log(f"{card.name}: {ability.name} (+{healed} HP)")
                self.emit_heal(card.position, healed, card_id=card.id, source_id=card.id)
