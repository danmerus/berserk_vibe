"""
Unified click handler for both local and network games.
Consolidates duplicate click handling logic from main.py.
"""
from typing import Optional, Callable, Any
from src.game import Game
from src.ui_state import GameClient
from src.renderer import Renderer
from src.commands import (
    cmd_move, cmd_attack, cmd_prepare_flyer_attack,
    cmd_use_ability, cmd_use_instant,
    cmd_confirm, cmd_cancel, cmd_choose_position, cmd_choose_card,
    cmd_choose_amount, cmd_pass_priority, cmd_skip, cmd_end_turn
)


class GameClickHandler:
    """
    Unified click handler for game interactions.
    Works for both local (match_client) and network games.
    """

    def __init__(
        self,
        game: Game,
        client: GameClient,
        renderer: Renderer,
        send_fn: Callable[[Any], bool],
        player: Optional[int] = None
    ):
        """
        Initialize click handler.

        Args:
            game: The game state
            client: UI state manager (selection, valid moves)
            renderer: Renderer for UI queries and visual state
            send_fn: Function to send commands. For local: sends and returns success.
                     For network: just sends, returns True.
            player: Our player number (1 or 2). None for local hotseat.
        """
        self.game = game
        self.client = client
        self.renderer = renderer
        self.send = send_fn
        self.player = player  # None = local hotseat (both players on same machine)

    def _get_acting_player(self) -> int:
        """Get the player who should act right now."""
        if self.game.interaction and self.game.interaction.acting_player:
            return self.game.interaction.acting_player
        return self.game.current_player

    def _can_act(self) -> bool:
        """Check if we can take actions (local always True, network checks player)."""
        if self.player is None:
            return True  # Local hotseat - always can act
        return self._get_acting_player() == self.player

    def _can_act_on_turn(self) -> bool:
        """Check if we can take turn-based actions (not interaction responses)."""
        if self.player is None:
            return True
        return self.game.current_player == self.player

    def _can_act_on_priority(self) -> bool:
        """Check if we have priority to act."""
        if self.player is None:
            return True
        return self.game.priority_player == self.player

    # =========================================================================
    # PRIORITY PHASE HANDLING
    # =========================================================================

    def handle_priority_click(self, mx: int, my: int) -> bool:
        """Handle clicks during priority phase. Returns True if handled."""
        # Dice popup interactions
        if self.renderer.dice_popup_open:
            opt = self.renderer.get_clicked_dice_option(mx, my)
            if opt == 'cancel':
                self.renderer.close_dice_popup()
                return True
            elif opt:
                card = self.renderer.dice_popup_card
                if card and self._can_act_on_priority():
                    player = self.player if self.player else self.game.priority_player
                    self.send(cmd_use_instant(player, card.id, "luck", opt))
                    self.renderer.close_dice_popup()
                    return True

        # Pass priority button
        if self.renderer.get_pass_button_rect().collidepoint(mx, my):
            if self._can_act_on_priority():
                self.renderer.close_dice_popup()
                player = self.player if self.player else self.game.priority_player
                self.send(cmd_pass_priority(player))
            return True

        # Ability clicks during priority (luck ability)
        ability_id = self.renderer.get_clicked_ability(mx, my)
        if ability_id and self.client.selected_card:
            if ability_id == "luck":
                card = self.client.selected_card
                is_combat_participant = False
                if self.game.pending_dice_roll:
                    dice = self.game.pending_dice_roll
                    combat_ids = {dice.attacker_id, dice.defender_id}
                    is_combat_participant = card.id in combat_ids
                if not is_combat_participant:
                    self.renderer.open_dice_popup(self.client.selected_card)
                    return True

        # Card selection during priority (including flying zones)
        pos, card = self._get_clicked_position_and_card(mx, my)
        if pos is not None:
            if card:
                self.client.select_card(card.id)
            else:
                self.client.deselect()
            return True

        return False

    # =========================================================================
    # INTERACTION POPUP HANDLING
    # =========================================================================

    def handle_interaction_click(self, mx: int, my: int) -> bool:
        """Handle clicks during popup/interaction states. Returns True if handled."""
        if not self._can_act():
            return False

        player = self.player if self.player else self._get_acting_player()

        # Counter selection popup
        if self.game.awaiting_counter_selection:
            opt = self.renderer.get_clicked_counter_button(mx, my)
            if opt == 'confirm':
                self.send(cmd_confirm(player, True))
                return True
            elif opt == 'cancel':
                self.send(cmd_cancel(player))
                return True
            elif isinstance(opt, int):
                self.send(cmd_choose_amount(player, opt))
                return True

        # Heal confirmation popup
        if self.game.awaiting_heal_confirm:
            choice = self.renderer.get_clicked_heal_button(mx, my)
            if choice == 'yes':
                self.send(cmd_confirm(player, True))
                return True
            elif choice == 'no':
                self.send(cmd_confirm(player, False))
                return True

        # Exchange (damage trade) popup
        if self.game.awaiting_exchange_choice:
            choice = self.renderer.get_clicked_exchange_button(mx, my)
            if choice == 'full':
                self.send(cmd_confirm(player, True))
                return True
            elif choice == 'reduce':
                self.send(cmd_confirm(player, False))
                return True

        # Stench choice popup
        if self.game.awaiting_stench_choice:
            choice = self.renderer.get_clicked_stench_button(mx, my)
            if choice == 'tap':
                self.send(cmd_confirm(player, True))
                return True
            elif choice == 'damage':
                self.send(cmd_confirm(player, False))
                return True

        return False

    # =========================================================================
    # UI ELEMENT HANDLING
    # =========================================================================

    def handle_ui_click(self, mx: int, my: int) -> bool:
        """Handle clicks on UI elements (buttons, panels). Returns True if handled."""
        player = self.player if self.player else self._get_acting_player()

        # Skip button
        if self.renderer.get_skip_button_rect().collidepoint(mx, my):
            if self._can_act():
                self.send(cmd_skip(player))
            return True

        # Side panel clicks (graveyards, flying zones)
        if self.renderer.handle_side_panel_click(mx, my):
            return True

        # End turn button
        if self.renderer.get_end_turn_button_rect().collidepoint(mx, my):
            if self._can_act_on_turn():
                turn_player = self.player if self.player else self.game.current_player
                # Cancel ability targeting if active
                if self.game.awaiting_ability_target:
                    self.send(cmd_cancel(turn_player))
                self.send(cmd_end_turn(turn_player))
                self.client.deselect()
            return True

        # Attack mode toggle button
        if self.renderer.get_clicked_attack_button(mx, my):
            if self.client.selected_card:
                # Cancel ability targeting if active
                turn_player = self.player if self.player else self.game.current_player
                if self.game.awaiting_ability_target:
                    self.send(cmd_cancel(turn_player))
                self.client.toggle_attack_mode()
                return True

        return False

    # =========================================================================
    # ABILITY BUTTON HANDLING
    # =========================================================================

    def handle_ability_click(self, mx: int, my: int) -> bool:
        """Handle clicks on ability buttons. Returns True if handled."""
        if not self._can_act_on_turn():
            return False

        player = self.player if self.player else self.game.current_player

        # Prepare flyer attack button
        if (self.renderer.prepare_flyer_button_rect and
            self.renderer.prepare_flyer_button_rect.collidepoint(mx, my) and
            self.client.selected_card):
            # Cancel ability targeting if active
            if self.game.awaiting_ability_target:
                self.send(cmd_cancel(player))
            self.send(cmd_prepare_flyer_attack(player, self.client.selected_card.id))
            return True

        ability_id = self.renderer.get_clicked_ability(mx, my)
        if ability_id and self.client.selected_card:
            # Cancel previous ability targeting if clicking a different ability
            if self.game.awaiting_ability_target:
                self.send(cmd_cancel(player))
            if self.game.awaiting_priority and ability_id == "luck":
                self.renderer.open_dice_popup(self.client.selected_card)
            else:
                self.send(cmd_use_ability(player, self.client.selected_card.id, ability_id))
            return True

        return False

    # =========================================================================
    # BOARD CLICK HANDLING
    # =========================================================================

    def _get_clicked_position_and_card(self, mx: int, my: int):
        """Get position and card at mouse coordinates (main board or flying zone)."""
        # Check main board first
        pos = self.renderer.screen_to_pos(mx, my)
        if pos is not None:
            card = self.game.board.get_card(pos)
            return pos, card

        # Check flying zones
        flying_pos = self.renderer.get_flying_slot_at_pos(mx, my, self.game)
        if flying_pos is not None:
            card = self.game.board.get_card(flying_pos)
            return flying_pos, card

        return None, None

    def handle_board_click(self, mx: int, my: int) -> bool:
        """Handle clicks on the game board (including flying zones). Returns True if handled."""
        pos, card_at_pos = self._get_clicked_position_and_card(mx, my)
        if pos is None:
            # Clicking outside board - cancel ability targeting if active
            if self.game.awaiting_ability_target or self.game.awaiting_counter_shot or self.game.awaiting_movement_shot:
                player = self.player if self.player else self._get_acting_player()
                self.send(cmd_cancel(player))
                self.client.deselect()
                return True
            return False

        player = self.player if self.player else self._get_acting_player()

        # If we can't act, only allow selection for viewing
        if not self._can_act():
            if card_at_pos:
                self.client.select_card(card_at_pos.id)
            else:
                self.client.deselect()
            return True

        # Handle ability targeting interactions
        if self.game.awaiting_ability_target or self.game.awaiting_counter_shot or self.game.awaiting_movement_shot:
            if self.game.interaction and self.game.interaction.can_select_position(pos):
                self.send(cmd_choose_position(player, pos))
                return True
            else:
                # Invalid target - cancel ability targeting
                self.send(cmd_cancel(player))
                self.client.deselect()
                return True

        # Handle valhalla target selection
        if self.game.awaiting_valhalla:
            if self.game.interaction and self.game.interaction.can_select_position(pos):
                self.send(cmd_choose_position(player, pos))
                return True
            return True

        # Handle defender selection
        if self.game.awaiting_defender:
            if card_at_pos and self.game.interaction and self.game.interaction.can_select_card_id(card_at_pos.id):
                self.send(cmd_choose_card(player, card_at_pos.id))
                return True
            else:
                # Skip defender selection (network sends skip, local does nothing)
                if self.player is not None:
                    self.send(cmd_skip(player))
                return True

        # Handle move/attack with selected card
        if self.client.selected_card:
            card_player = self.client.selected_card.player
            can_use_card = (self.player is None) or (card_player == self.player)

            if can_use_card:
                if pos in self.client.ui.valid_moves:
                    self.send(cmd_move(player, self.client.selected_card.id, pos))
                    return True
                if pos in self.client.ui.valid_attacks:
                    self.send(cmd_attack(player, self.client.selected_card.id, pos))
                    return True

        # Client-side selection/deselection
        if card_at_pos:
            self.client.select_card(card_at_pos.id)
        else:
            self.client.deselect()
        return True

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    def handle_left_click(self, mx: int, my: int) -> bool:
        """
        Handle left click during game. Returns True if handled.
        Routes to appropriate handler based on game state.
        """
        # Handle popup drag attempts first
        if self.renderer.start_popup_drag(mx, my, self.game):
            return True
        if self.renderer.start_log_scrollbar_drag(mx, my):
            return True

        # Priority phase has special handling
        if self.game.awaiting_priority:
            return self.handle_priority_click(mx, my)

        # Check for interaction popups (counter, heal, exchange, stench)
        if self.handle_interaction_click(mx, my):
            return True

        # Check UI elements (buttons, panels)
        if self.handle_ui_click(mx, my):
            return True

        # Check ability clicks
        if self.handle_ability_click(mx, my):
            return True

        # Finally, handle board clicks
        return self.handle_board_click(mx, my)
