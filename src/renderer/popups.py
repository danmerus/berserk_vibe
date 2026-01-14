"""Popup windows and dialogs - card preview, game over, dice, counters."""
import pygame
from typing import Optional, Tuple, List, TYPE_CHECKING

from ..constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT,
    COLOR_SELF, COLOR_OPPONENT, COLOR_TEXT,
    scaled, UILayout
)
from ..card_database import get_card_image

if TYPE_CHECKING:
    from ..game import Game
    from ..card import Card


class PopupsMixin:
    """Mixin for popup windows and dialogs."""

    def _get_popup_pos(self, popup_id: str, default_x: int, default_y: int) -> Tuple[int, int]:
        """Get popup position, using stored position or default."""
        if popup_id not in self.popup_positions:
            self.popup_positions[popup_id] = (default_x, default_y)
        return self.popup_positions[popup_id]

    def _get_popup_rect(self, popup_id: str, width: int, height: int,
                        default_x: int, default_y: int) -> pygame.Rect:
        """Get popup rectangle with stored or default position."""
        x, y = self._get_popup_pos(popup_id, default_x, default_y)
        return pygame.Rect(x, y, width, height)

    def draw_popup_base(self, config: 'PopupConfig') -> Tuple[int, int, int]:
        """Draw popup background, border, drag handle, and title.

        Returns (x, y, content_y) where content_y is where content should start.
        """
        # Calculate default x if not specified (center)
        default_x = config.default_x if config.default_x is not None else (WINDOW_WIDTH - config.width) // 2

        # Get position (may be dragged)
        x, y = self._get_popup_pos(config.popup_id, default_x, config.default_y)

        # Draw semi-transparent background
        bg_surface = pygame.Surface((config.width, config.height), pygame.SRCALPHA)
        bg_surface.fill(config.bg_color)
        self.screen.blit(bg_surface, (x, y))

        # Draw border
        pygame.draw.rect(self.screen, config.border_color, (x, y, config.width, config.height), 3)

        # Draw drag handle (two lines at top center)
        handle_color = tuple(min(c + 50, 255) for c in config.border_color)
        handle_x1 = x + config.width // 2 - 50
        handle_x2 = x + config.width // 2 + 50
        pygame.draw.line(self.screen, handle_color, (handle_x1, y + 5), (handle_x2, y + 5), 2)
        pygame.draw.line(self.screen, handle_color, (handle_x1, y + 8), (handle_x2, y + 8), 2)

        # Draw title if provided
        content_y = y + 12
        if config.title:
            title_surface = self.font_large.render(config.title, True, config.title_color)
            title_x = x + (config.width - title_surface.get_width()) // 2
            self.screen.blit(title_surface, (title_x, content_y))
            content_y += title_surface.get_height() + 5

        return x, y, content_y

    def draw_popup_text(self, x: int, width: int, y: int, text: str,
                        color: Tuple[int, int, int], font: pygame.font.Font = None,
                        center: bool = True) -> int:
        """Draw centered text in popup. Returns new y position."""
        if font is None:
            font = self.font_popup  # Use smaller popup font
        surface = font.render(text, True, color)
        if center:
            text_x = x + (width - surface.get_width()) // 2
        else:
            text_x = x + 10
        self.screen.blit(surface, (text_x, y))
        return y + surface.get_height() + 3

    def draw_popup_button(self, x: int, y: int, width: int, height: int,
                          text: str, bg_color: Tuple[int, int, int],
                          border_color: Tuple[int, int, int]) -> pygame.Rect:
        """Draw a button in popup. Returns the button rect for click detection."""
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, bg_color, rect)
        pygame.draw.rect(self.screen, border_color, rect, 2)
        text_surface = self.font_popup.render(text, True, (255, 255, 255))
        self.screen.blit(text_surface, (rect.centerx - text_surface.get_width() // 2,
                                        rect.centery - text_surface.get_height() // 2))
        return rect

    def start_popup_drag(self, mouse_x: int, mouse_y: int, game: 'Game') -> bool:
        """Try to start dragging a popup. Returns True if drag started."""
        # Only check popups that are currently visible
        active_popups = []
        if game.awaiting_defender:
            active_popups.append(('defender', 500, 100))
        if game.awaiting_valhalla:
            active_popups.append(('valhalla', 450, 80))
        if game.awaiting_counter_shot:
            active_popups.append(('counter_shot', 400, 60))
        if game.awaiting_movement_shot:
            active_popups.append(('movement_shot', 450, 95))
        if game.awaiting_heal_confirm:
            active_popups.append(('heal_confirm', 350, 90))
        if game.awaiting_untap_confirm:
            active_popups.append(('untap_confirm', 350, 90))
        if game.awaiting_select_untap:
            active_popups.append(('select_untap', 450, 80))
        if game.awaiting_stench_choice:
            active_popups.append(('stench_choice', 380, 90))
        if game.awaiting_exchange_choice:
            active_popups.append(('exchange', 320, 100))

        # Waiting indicator (when opponent is deciding)
        if game.interaction and game.interaction.acting_player != self.viewing_player:
            active_popups.append(('waiting_opponent', 400, 60))

        for popup_id, width, height in active_popups:
            rect = self._get_popup_rect(popup_id, width, height, (WINDOW_WIDTH - width) // 2, 60)
            # Check if clicking on title bar (top 30 pixels)
            title_rect = pygame.Rect(rect.x, rect.y, rect.width, 30)
            if title_rect.collidepoint(mouse_x, mouse_y):
                self.dragging_popup = popup_id
                self.drag_offset = (mouse_x - rect.x, mouse_y - rect.y)
                return True
        return False

    def drag_popup(self, mouse_x: int, mouse_y: int):
        """Update dragged popup position."""
        if self.dragging_popup:
            new_x = mouse_x - self.drag_offset[0]
            new_y = mouse_y - self.drag_offset[1]
            # Clamp to screen
            new_x = max(0, min(new_x, WINDOW_WIDTH - 100))
            new_y = max(0, min(new_y, WINDOW_HEIGHT - 50))
            self.popup_positions[self.dragging_popup] = (new_x, new_y)

    def stop_popup_drag(self):
        """Stop dragging popup."""
        self.dragging_popup = None

    # Card popup methods
    def show_popup(self, card: 'Card'):
        """Show popup for a card."""
        self.popup_card = card

    def hide_popup(self):
        """Hide the popup."""
        self.popup_card = None

    def draw_popup(self):
        """Draw full card popup if active."""
        if not self.popup_card:
            return

        card = self.popup_card

        # Get card image
        img_filename = get_card_image(card.name)
        if not img_filename or img_filename not in self.card_images_full:
            return

        img = self.card_images_full[img_filename]
        img_w, img_h = img.get_size()

        # Center image on screen
        img_x = (WINDOW_WIDTH - img_w) // 2
        img_y = (WINDOW_HEIGHT - img_h) // 2

        # Semi-transparent overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        # Draw card image (no border for cleaner look)
        self.screen.blit(img, (img_x, img_y))

    # Game over popup methods
    def show_game_over_popup(self, winner: int, player1_name: str = None, player2_name: str = None):
        """Show game over popup with winner info."""
        self.game_over_popup = True
        self.game_over_winner = winner
        self.game_over_player1_name = player1_name
        self.game_over_player2_name = player2_name

    def hide_game_over_popup(self):
        """Hide game over popup."""
        self.game_over_popup = False
        self.game_over_button_rect = None

    def draw_game_over_popup(self):
        """Draw game over popup background/overlay to self.screen."""
        if not self.game_over_popup:
            return

        # Semi-transparent overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill(UILayout.POPUP_GAME_OVER_OVERLAY)
        self.screen.blit(overlay, (0, 0))

        # Popup box
        popup_w = scaled(UILayout.POPUP_GAME_OVER_WIDTH)
        popup_h = scaled(UILayout.POPUP_GAME_OVER_HEIGHT)
        popup_x = (WINDOW_WIDTH - popup_w) // 2
        popup_y = (WINDOW_HEIGHT - popup_h) // 2

        # Background
        pygame.draw.rect(self.screen, UILayout.POPUP_GAME_OVER_BG, (popup_x, popup_y, popup_w, popup_h))
        pygame.draw.rect(self.screen, UILayout.POPUP_GAME_OVER_BORDER, (popup_x, popup_y, popup_w, popup_h), 3)

    def draw_game_over_popup_native(self):
        """Draw game over popup text and button at native resolution."""
        if not self.game_over_popup:
            return

        # Popup box dimensions in game coords
        popup_w = scaled(UILayout.POPUP_GAME_OVER_WIDTH)
        popup_h = scaled(UILayout.POPUP_GAME_OVER_HEIGHT)
        popup_x = (WINDOW_WIDTH - popup_w) // 2
        popup_y = (WINDOW_HEIGHT - popup_h) // 2
        popup_win_rect = self.game_to_window_rect(pygame.Rect(popup_x, popup_y, popup_w, popup_h))

        # Winner text (blue if you won, red if opponent won)
        if self.game_over_winner == 0:
            title_text = "Ничья!"
            title_color = (200, 200, 200)
            winner_name = None
        else:
            # Color based on viewer perspective: blue = you won, red = opponent won
            if self.game_over_winner == self.viewing_player:
                title_color = COLOR_SELF  # You won - blue
            else:
                title_color = COLOR_OPPONENT  # Opponent won - red

            if self.game_over_winner == 1:
                winner_name = getattr(self, 'game_over_player1_name', None)
            else:
                winner_name = getattr(self, 'game_over_player2_name', None)

            if winner_name:
                title_text = f"Победил игрок {self.game_over_winner}!"
            else:
                title_text = f"Победа игрока {self.game_over_winner}!"

        large_font = self.get_native_font('large')
        title_surface = large_font.render(title_text, True, title_color)
        title_x = popup_win_rect.x + (popup_win_rect.width - title_surface.get_width()) // 2
        _, title_y = self.game_to_window_coords(0, popup_y + scaled(35))
        self.window.blit(title_surface, (title_x, title_y))

        medium_font = self.get_native_font('medium')
        congrats_y_game = popup_y + scaled(80)

        # Winner name (if available)
        if self.game_over_winner != 0 and winner_name:
            name_text = winner_name
            name_surface = medium_font.render(name_text, True, title_color)
            name_x = popup_win_rect.x + (popup_win_rect.width - name_surface.get_width()) // 2
            _, name_y = self.game_to_window_coords(0, popup_y + scaled(75))
            self.window.blit(name_surface, (name_x, name_y))
            congrats_y_game = popup_y + scaled(110)

        # Congratulations text (skip for draws)
        if self.game_over_winner != 0:
            congrats_text = "Поздравляем!"
            congrats_surface = medium_font.render(congrats_text, True, COLOR_TEXT)
            congrats_x = popup_win_rect.x + (popup_win_rect.width - congrats_surface.get_width()) // 2
            _, congrats_y = self.game_to_window_coords(0, congrats_y_game)
            self.window.blit(congrats_surface, (congrats_x, congrats_y))

        # OK button at native resolution
        btn_w = scaled(150)
        btn_h = scaled(40)
        btn_x = popup_x + (popup_w - btn_w) // 2
        btn_y = popup_y + popup_h - btn_h - scaled(20)

        self.game_over_button_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        btn_win_rect = self.game_to_window_rect(self.game_over_button_rect)

        # Draw button at native resolution
        border_width = max(1, int(2 * self.scale))
        pygame.draw.rect(self.window, (50, 100, 50), btn_win_rect)
        pygame.draw.rect(self.window, (80, 150, 80), btn_win_rect, border_width)

        btn_text = medium_font.render("В меню", True, COLOR_TEXT)
        text_x = btn_win_rect.x + (btn_win_rect.width - btn_text.get_width()) // 2
        text_y = btn_win_rect.y + (btn_win_rect.height - btn_text.get_height()) // 2
        self.window.blit(btn_text, (text_x, text_y))

    def is_game_over_button_clicked(self, x: int, y: int) -> bool:
        """Check if game over button was clicked."""
        return self.game_over_button_rect and self.game_over_button_rect.collidepoint(x, y)

    # Dice popup methods
    def open_dice_popup(self, card: 'Card'):
        """Open the dice modification popup for an instant ability card."""
        self.dice_popup_open = True
        self.dice_popup_card = card

    def close_dice_popup(self):
        """Close the dice modification popup."""
        self.dice_popup_open = False
        self.dice_popup_card = None
        self.dice_option_buttons = []

    def _draw_dice_row(self, popup_x: int, y_offset: int, card: 'Card', roll: int,
                       modifier: int, bonus: int, btn_prefix: str):
        """Draw a single dice row with name, dice value, and modification buttons."""
        color = self.get_player_color(card.player)  # Blue for you, red for opponent
        total = roll + modifier + bonus

        # Draw card name (position from UILayout.POPUP_DICE_NAME_X)
        name_surface = self.font_medium.render(f"{card.name}:", True, color)
        self.screen.blit(name_surface, (popup_x + scaled(UILayout.POPUP_DICE_NAME_X), y_offset))

        # Draw dice value (position from UILayout.POPUP_DICE_VALUE_X)
        dice_x = popup_x + scaled(UILayout.POPUP_DICE_VALUE_X)
        bonus_str = f"+{bonus}" if bonus > 0 else ""

        if modifier != 0:
            # Show: [roll+bonus] -> [total] with color indicating modification
            orig_text = f"[{roll}{bonus_str}]"
            orig_surface = self.font_medium.render(orig_text, True, (150, 150, 150))
            self.screen.blit(orig_surface, (dice_x, y_offset))

            arrow_surface = self.font_medium.render(" → ", True, COLOR_TEXT)
            self.screen.blit(arrow_surface, (dice_x + orig_surface.get_width(), y_offset))

            mod_color = (100, 255, 100) if modifier > 0 else (255, 100, 100)
            mod_text = f"[{total}]"
            mod_surface = self.font_medium.render(mod_text, True, mod_color)
            self.screen.blit(mod_surface, (dice_x + orig_surface.get_width() + arrow_surface.get_width(), y_offset))
        else:
            # Show roll with bonus or just roll
            if bonus > 0:
                dice_text = f"[{roll}+{bonus}={roll + bonus}]"
            else:
                dice_text = f"[{roll}]"
            dice_surface = self.font_medium.render(dice_text, True, COLOR_TEXT)
            self.screen.blit(dice_surface, (dice_x, y_offset))

        # Draw modification buttons (position from UILayout.POPUP_DICE_BUTTONS_X/Y_OFFSET)
        btn_x = popup_x + scaled(UILayout.POPUP_DICE_BUTTONS_X)
        btn_y = y_offset - 3 + scaled(UILayout.POPUP_DICE_BUTTONS_Y_OFFSET)
        for suffix, label, color in [('_plus1', '+1', (80, 140, 80)),
                                     ('_minus1', '-1', (140, 80, 80)),
                                     ('_reroll', 'reroll', (80, 80, 140))]:
            btn_rect = pygame.Rect(btn_x, btn_y, 48, 26)
            pygame.draw.rect(self.screen, color, btn_rect)
            pygame.draw.rect(self.screen, COLOR_TEXT, btn_rect, 1)
            btn_text = self.font_small.render(label, True, COLOR_TEXT)
            self.screen.blit(btn_text, (btn_rect.x + (48 - btn_text.get_width()) // 2,
                                        btn_rect.y + (26 - btn_text.get_height()) // 2))
            self.dice_option_buttons.append((f'{btn_prefix}{suffix}', btn_rect))
            btn_x += 52

    def draw_dice_popup(self, game: 'Game'):
        """Draw dice modification popup when an instant card is selected during priority."""
        if not self.dice_popup_open or not game.pending_dice_roll:
            return

        dice = game.pending_dice_roll
        attacker = game.board.get_card_by_id(dice.attacker_id)
        if not attacker:
            return

        is_single_roll = dice.type in ('ranged', 'magic')
        defender = game.board.get_card_by_id(dice.defender_id) if dice.defender_id and not is_single_roll else None
        target = game.board.get_card_by_id(dice.target_id) if dice.target_id and is_single_roll else None

        # Popup dimensions and position
        popup_width = scaled(UILayout.POPUP_DICE_WIDTH)
        popup_height = scaled(UILayout.POPUP_DICE_HEIGHT_RANGED if is_single_roll else UILayout.POPUP_DICE_HEIGHT_MELEE)
        popup_x = (WINDOW_WIDTH - popup_width) // 2
        popup_y = scaled(UILayout.POPUP_DICE_Y)

        # Draw popup background
        bg_surface = pygame.Surface((popup_width, popup_height), pygame.SRCALPHA)
        bg_surface.fill(UILayout.POPUP_DICE_BG + (240,))
        self.screen.blit(bg_surface, (popup_x, popup_y))
        pygame.draw.rect(self.screen, UILayout.POPUP_DICE_BORDER, (popup_x, popup_y, popup_width, popup_height), 3)

        # Title
        if dice.type == 'magic':
            title_text = "Удача - изменить бросок (магия)"
        elif dice.type == 'ranged':
            ranged_type = dice.ranged_type or 'shot'
            title_text = "Удача - изменить бросок (метание)" if ranged_type == "throw" else "Удача - изменить бросок (выстрел)"
        else:
            title_text = "Удача - изменить бросок"
        title = self.font_medium.render(title_text, True, (255, 220, 100))
        self.screen.blit(title, (popup_x + (popup_width - title.get_width()) // 2, popup_y + 10))

        self.dice_option_buttons = []
        y_offset = popup_y + 50

        # Attacker dice row
        self._draw_dice_row(popup_x, y_offset, attacker,
                           dice.atk_roll, dice.atk_modifier, dice.atk_bonus, 'atk')
        y_offset += 55

        # Defender dice row (only for melee combat with active defender)
        if not is_single_roll and defender and dice.def_roll > 0:
            self._draw_dice_row(popup_x, y_offset, defender,
                               dice.def_roll, dice.def_modifier, dice.def_bonus, 'def')
            y_offset += 55
        elif is_single_roll and target:
            # Show target info for ranged/magic attacks (read-only)
            target_color = self.get_player_color(target.player)  # Blue for you, red for opponent
            target_name_surface = self.font_medium.render(f"Цель: {target.name}", True, target_color)
            self.screen.blit(target_name_surface, (popup_x + 15, y_offset))
            y_offset += 35

        # Cancel button
        cancel_rect = pygame.Rect(popup_x + popup_width // 2 - 50, y_offset, 100, 30)
        pygame.draw.rect(self.screen, (80, 60, 60), cancel_rect)
        pygame.draw.rect(self.screen, COLOR_TEXT, cancel_rect, 1)
        cancel_text = self.font_small.render("Отмена", True, COLOR_TEXT)
        self.screen.blit(cancel_text, (cancel_rect.x + (100 - cancel_text.get_width()) // 2,
                                       cancel_rect.y + (30 - cancel_text.get_height()) // 2))
        self.dice_option_buttons.append(('cancel', cancel_rect))

    def get_clicked_dice_option(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if a dice modification button was clicked. Returns option_id or None."""
        if not hasattr(self, 'dice_option_buttons'):
            return None
        for opt_id, btn_rect in self.dice_option_buttons:
            if btn_rect.collidepoint(mouse_x, mouse_y):
                return opt_id
        return None

    # Counter selection popup methods
    def draw_counter_popup(self, game: 'Game'):
        """Draw counter selection popup for abilities like axe_strike."""
        if not game.awaiting_counter_selection or not game.counter_selection_card:
            return

        card = game.counter_selection_card
        max_counters = card.counters
        selected = game.interaction.selected_amount if game.interaction else 0

        # Popup dimensions (scaled for resolution)
        popup_width = scaled(350)
        popup_height = scaled(150)
        popup_x = (WINDOW_WIDTH - popup_width) // 2
        popup_y = scaled(150)

        # Draw popup background
        bg_surface = pygame.Surface((popup_width, popup_height), pygame.SRCALPHA)
        bg_surface.fill((40, 35, 60, 240))
        self.screen.blit(bg_surface, (popup_x, popup_y))
        pygame.draw.rect(self.screen, (100, 80, 140), (popup_x, popup_y, popup_width, popup_height), 3)

        # Title
        title = self.font_medium.render("Выберите количество фишек", True, (255, 220, 100))
        self.screen.blit(title, (popup_x + (popup_width - title.get_width()) // 2, popup_y + 10))

        # Counter display
        counter_text = f"Фишки: {selected} / {max_counters}"
        counter_surface = self.font_medium.render(counter_text, True, COLOR_TEXT)
        self.screen.blit(counter_surface, (popup_x + (popup_width - counter_surface.get_width()) // 2, popup_y + 45))

        # Clear button list
        self.counter_popup_buttons = []

        # Counter selection buttons (row of numbers 0 to max)
        y_offset = popup_y + 75
        btn_width = 35
        btn_height = 30
        num_buttons = min(max_counters + 1, 11)  # 0 to max, up to 11 buttons
        total_btn_width = num_buttons * (btn_width + 5) - 5
        start_x = popup_x + (popup_width - total_btn_width) // 2

        for i in range(0, min(max_counters + 1, 11)):  # Show 0 to max (up to 10)
            btn_x = start_x + i * (btn_width + 5)
            btn_rect = pygame.Rect(btn_x, y_offset, btn_width, btn_height)

            # Highlight selected
            if i == selected:
                btn_color = (100, 150, 100)  # Green for selected
            else:
                btn_color = (60, 50, 80)

            pygame.draw.rect(self.screen, btn_color, btn_rect)
            pygame.draw.rect(self.screen, COLOR_TEXT, btn_rect, 1)

            num_surface = self.font_small.render(str(i), True, COLOR_TEXT)
            self.screen.blit(num_surface, (btn_rect.x + (btn_width - num_surface.get_width()) // 2,
                                           btn_rect.y + (btn_height - num_surface.get_height()) // 2))
            self.counter_popup_buttons.append((i, btn_rect))

        # Confirm and Cancel buttons
        y_offset += 40
        confirm_rect = pygame.Rect(popup_x + popup_width // 2 - 110, y_offset, 100, 28)
        cancel_rect = pygame.Rect(popup_x + popup_width // 2 + 10, y_offset, 100, 28)

        # Confirm
        pygame.draw.rect(self.screen, (60, 100, 60), confirm_rect)
        pygame.draw.rect(self.screen, COLOR_TEXT, confirm_rect, 1)
        confirm_text = self.font_small.render("OK", True, COLOR_TEXT)
        self.screen.blit(confirm_text, (confirm_rect.x + (100 - confirm_text.get_width()) // 2,
                                        confirm_rect.y + (28 - confirm_text.get_height()) // 2))
        self.counter_confirm_button = confirm_rect

        # Cancel
        pygame.draw.rect(self.screen, (100, 60, 60), cancel_rect)
        pygame.draw.rect(self.screen, COLOR_TEXT, cancel_rect, 1)
        cancel_text = self.font_small.render("Отмена", True, COLOR_TEXT)
        self.screen.blit(cancel_text, (cancel_rect.x + (100 - cancel_text.get_width()) // 2,
                                       cancel_rect.y + (28 - cancel_text.get_height()) // 2))
        self.counter_cancel_button = cancel_rect

    def get_clicked_counter_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check counter popup button clicks. Returns 'confirm', 'cancel', or count as int, or None."""
        if hasattr(self, 'counter_confirm_button') and self.counter_confirm_button:
            if self.counter_confirm_button.collidepoint(mouse_x, mouse_y):
                return 'confirm'
        if hasattr(self, 'counter_cancel_button') and self.counter_cancel_button:
            if self.counter_cancel_button.collidepoint(mouse_x, mouse_y):
                return 'cancel'
        if hasattr(self, 'counter_popup_buttons'):
            for count, btn_rect in self.counter_popup_buttons:
                if btn_rect.collidepoint(mouse_x, mouse_y):
                    return count
        return None
