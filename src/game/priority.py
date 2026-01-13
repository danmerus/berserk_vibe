"""Priority system - instant abilities (Внезапные действия)."""
from typing import List, Tuple, TYPE_CHECKING

from .base import StackItem, DiceContext
from ..abilities import get_ability, AbilityTrigger

if TYPE_CHECKING:
    from ..card import Card
    from ..abilities import Ability


class PriorityMixin:
    """Mixin for priority system and instant abilities."""

    def _get_instant_cards(self, player: int, debug: bool = False) -> List[Tuple['Card', 'Ability']]:
        """Get all cards with instant abilities for a player."""
        card_ids_on_stack = {instant.card_id for instant in self.instant_stack}

        combat_card_ids = set()
        if self.pending_dice_roll:
            dice = self.pending_dice_roll
            if dice.attacker_id:
                combat_card_ids.add(dice.attacker_id)
            if dice.defender_id:
                combat_card_ids.add(dice.defender_id)

        result = []
        for card in self.board.get_all_cards(player):
            if "luck" not in card.stats.ability_ids:
                continue
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

    def get_legal_instants(self, player: int) -> List[Tuple['Card', 'Ability']]:
        """Get all cards with legal instant abilities for a player during priority."""
        if not self.priority_phase or not self.pending_dice_roll:
            return []
        return self._get_instant_cards(player)

    def _enter_priority_phase(self, dice_context: DiceContext):
        """Enter priority phase after a dice roll."""
        self.pending_dice_roll = dice_context

        p1_instants = self._get_instant_cards(1)
        p2_instants = self._get_instant_cards(2)

        if not p1_instants and not p2_instants:
            found_any = False
            for card in self.board.get_all_cards():
                if card.has_ability("luck"):
                    found_any = True
                    break
            if found_any:
                self._get_instant_cards(1, debug=True)
                self._get_instant_cards(2, debug=True)
            self.pending_dice_roll = None
            return False

        self.priority_phase = True
        self.priority_passed = []
        self.instant_stack = []

        current_has_instants = p1_instants if self.current_player == 1 else p2_instants
        opponent = 2 if self.current_player == 1 else 1
        opponent_has_instants = p2_instants if self.current_player == 1 else p1_instants

        if current_has_instants:
            self.priority_player = self.current_player
        elif opponent_has_instants:
            self.priority_passed.append(self.current_player)
            self.priority_player = opponent

        self.log(f"Приоритет: Игрок {self.priority_player}")
        return True

    def pass_priority(self) -> bool:
        """Current priority player passes."""
        if not self.priority_phase:
            return False

        if self.priority_player not in self.priority_passed:
            self.priority_passed.append(self.priority_player)

        other_player = 2 if self.priority_player == 1 else 1

        if other_player not in self.priority_passed:
            other_instants = self.get_legal_instants(other_player)
            if other_instants:
                self.priority_player = other_player
                self.log(f"Приоритет: Игрок {self.priority_player}")
                return False
            else:
                self.priority_passed.append(other_player)

        self._resolve_priority_stack()
        return True

    def _resolve_priority_stack(self):
        """Resolve all instant abilities on the stack."""
        while self.instant_stack:
            instant = self.instant_stack.pop()
            self._apply_instant_effect(instant)

        self.priority_phase = False
        self.priority_player = 0
        self.priority_passed = []

    def _apply_instant_effect(self, instant: StackItem):
        """Apply the effect of a resolved instant ability."""
        card = self.board.get_card_by_id(instant.card_id)
        if not card:
            return

        if instant.ability_id == "luck":
            target = 'atk' if instant.option.startswith('atk_') else 'def'
            action = instant.option.split('_')[1]

            dice = self.pending_dice_roll
            if not dice:
                return

            is_single_roll = dice.type in ('ranged', 'magic')

            if is_single_roll and target == 'def':
                self.log(f"  -> {card.name}: Нет броска защитника для изменения")
                return

            if target == 'def' and dice.def_roll == 0:
                self.log(f"  -> {card.name}: Защитник закрыт - нет броска для изменения")
                return

            if target == 'atk':
                atk_card = self.board.get_card_by_id(dice.attacker_id)
                target_name = atk_card.name if atk_card else "атакующий"
            else:
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

            card.tap()

    def use_instant_ability(self, card: 'Card', ability_id: str, option: str) -> bool:
        """Use an instant ability during priority phase."""
        if not self.priority_phase:
            return False

        if card.player != self.priority_player:
            return False

        ability = get_ability(ability_id)
        if not ability or not ability.is_instant:
            return False

        if not card.can_use_ability(ability_id):
            return False

        if self.pending_dice_roll:
            dice = self.pending_dice_roll
            combat_card_ids = set()
            if dice.attacker_id:
                combat_card_ids.add(dice.attacker_id)
            if dice.defender_id:
                combat_card_ids.add(dice.defender_id)
            if card.id in combat_card_ids:
                self.log(f"{card.name}: участвует в бою")
                return False

        for instant in self.instant_stack:
            if instant.card_id == card.id:
                self.log(f"{card.name}: уже использовал способность")
                return False

        # Reveal face-down card when it acts
        if card.face_down:
            self.reveal_card(card)

        self.instant_stack.append(StackItem(
            card_id=card.id,
            ability_id=ability.id,
            option=option
        ))

        self.log(f"{card.name}: Удача ({option})")

        opponent = 2 if card.player == 1 else 1
        opponent_instants = self.get_legal_instants(opponent)

        if opponent_instants:
            self.priority_passed = []
            self.priority_player = opponent
            self.log(f"Приоритет: Игрок {self.priority_player}")
        else:
            self._resolve_priority_stack()
            self.continue_after_priority()

        return True
