"""Movement and flyer attack preparation."""
from typing import List, TYPE_CHECKING

from ..commands import evt_card_moved

if TYPE_CHECKING:
    from ..card import Card


class MovementMixin:
    """Mixin for movement and flyer attack handling."""

    def can_prepare_flyer_attack(self, card: 'Card') -> bool:
        """Check if a ground card can tap to prepare for flyer attack."""
        if self.current_player != card.player:
            return False
        if card.stats.is_flying:
            return False
        if card.tapped:
            return False
        if card.can_attack_flyer:
            return False
        return self.opponent_has_only_flyers(card.player)

    def prepare_flyer_attack(self, card: 'Card') -> bool:
        """Tap a ground card to prepare it to attack flyers."""
        if not self.can_prepare_flyer_attack(card):
            return False

        card.tap()
        card.can_attack_flyer = True
        card.can_attack_flyer_until_turn = self.turn_number + 1

        self.log(f"{card.name} готовится атаковать летающих!")
        return True

    def get_attack_targets(self, card: 'Card', include_allies: bool = True) -> List[int]:
        """Get valid attack targets for a card."""
        targets = self.board.get_attack_targets(card, include_allies)

        # If card has prepared flyer attack, add enemy flyers
        if card.can_attack_flyer and not card.stats.is_flying:
            enemy_player = 2 if card.player == 1 else 1
            for flying_card in self.board.get_flying_cards(enemy_player):
                if flying_card.is_alive and flying_card.position is not None:
                    if flying_card.position not in targets:
                        targets.append(flying_card.position)

        return targets

    def move_card(self, card: 'Card', to_pos: int) -> bool:
        """Move card to position."""
        self.last_combat = None

        if self.has_blocking_interaction:
            return False

        if self.has_forced_attack:
            self.log("Сначала атакуйте закрытого врага!")
            return False

        if not card or not card.can_act:
            return False

        # Reveal face-down card when it acts
        if card.face_down:
            self.reveal_card(card)

        from_pos = card.position

        from_col, from_row = from_pos % 5, from_pos // 5
        to_col, to_row = to_pos % 5, to_pos // 5
        distance = abs(to_col - from_col) + abs(to_row - from_row)

        if self.board.move_card(from_pos, to_pos):
            self.emit_event(evt_card_moved(card.id, from_pos, to_pos))

            if card.has_ability("jump"):
                card.curr_move = 0
                self.log(f"{card.name} прыгнул.")
            else:
                card.curr_move -= distance
                self.log(f"{card.name} переместился.")

            self.recalculate_formations()
            self._process_movement_shot(card)
            self._update_forced_attackers()
            forced_targets = self.get_forced_attacker_card(card)
            if forced_targets:
                self.log(f"{card.name} должен атаковать закрытого врага!")

            return True
        return False
