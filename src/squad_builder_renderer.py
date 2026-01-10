"""Squad builder rendering module."""
import pygame
from typing import List, Tuple, Optional, Dict

from .constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT,
    UILayout, scaled
)
from .card_database import CARD_DATABASE, get_card_image
from .squad_builder import SquadBuilder


class SquadBuilderRenderer:
    """Handles squad builder screen rendering."""

    def __init__(self, screen: pygame.Surface, card_images: Dict, fonts: Dict):
        """Initialize with shared resources."""
        self.screen = screen
        self.card_images = card_images
        self.fonts = fonts

        # Click detection storage
        self.hand_card_rects: List[Tuple[str, pygame.Rect]] = []
        self.squad_card_rects: List[Tuple[str, pygame.Rect]] = []
        self.button_rects: List[Tuple[str, pygame.Rect]] = []

        # Scroll state
        self.hand_scroll = 0
        self.squad_scroll = 0

        # Popup for card preview
        self.popup_card_name: Optional[str] = None

        # Notification
        self.notification_message = ""
        self.notification_timer = 0

    def draw(self, squad_builder: SquadBuilder, card_images_full: Dict):
        """Draw the complete squad builder screen."""
        self.screen.fill(COLOR_BG)

        # Clear click detection lists
        self.hand_card_rects.clear()
        self.squad_card_rects.clear()
        self.button_rects.clear()

        # Draw header
        self._draw_header(squad_builder)

        # Draw sections
        self._draw_hand(squad_builder)
        self._draw_squad(squad_builder)
        self._draw_right_panel(squad_builder)

        # Draw notification
        if self.notification_message:
            self._draw_notification()

        # Draw popup on top
        if self.popup_card_name:
            self._draw_card_popup(card_images_full)

    def _draw_header(self, squad_builder: SquadBuilder):
        """Draw the player header."""
        turn_order = "ходит первым" if squad_builder.player == 1 else "ходит вторым"
        header_text = f"Формирование отряда - Игрок {squad_builder.player} ({turn_order})"
        header = self.fonts['large'].render(header_text, True, COLOR_TEXT)
        self.screen.blit(header, (scaled(10), scaled(10)))

    def _draw_hand(self, squad_builder: SquadBuilder):
        """Draw the hand section (top) - cards available to pick."""
        x = scaled(UILayout.DECK_BUILDER_LIBRARY_X)
        y = scaled(UILayout.DECK_BUILDER_LIBRARY_Y)
        width = scaled(UILayout.DECK_BUILDER_LIBRARY_WIDTH)
        height = scaled(UILayout.DECK_BUILDER_LIBRARY_HEIGHT)

        # Section background
        pygame.draw.rect(self.screen, (40, 40, 50), (x, y, width, height))
        pygame.draw.rect(self.screen, (80, 80, 100), (x, y, width, height), 2)

        # Section label
        label = self.fonts['small'].render("РАЗДАЧА (выберите карты в отряд)", True, (150, 150, 170))
        self.screen.blit(label, (x + 5, y - scaled(18)))

        # Card dimensions
        card_w = scaled(UILayout.DECK_BUILDER_CARD_WIDTH)
        card_h = scaled(UILayout.DECK_BUILDER_CARD_HEIGHT)
        gap = scaled(UILayout.DECK_BUILDER_CARD_GAP)
        cards_per_row = UILayout.DECK_BUILDER_CARDS_PER_ROW
        padding = scaled(8)

        hand_cards = squad_builder.get_hand_cards()

        # Create clipping rect
        clip_rect = pygame.Rect(x, y, width, height)
        self.screen.set_clip(clip_rect)

        for i, (card_name, can_add, reason) in enumerate(hand_cards):
            row = i // cards_per_row
            col = i % cards_per_row

            card_x = x + padding + col * (card_w + gap)
            card_y = y + padding + row * (card_h + gap) - self.hand_scroll

            # Skip if outside visible area
            if card_y + card_h < y or card_y > y + height:
                continue

            self._draw_squad_card(card_name, card_x, card_y, card_w, card_h,
                                  can_add=can_add, in_hand=True)
            self.hand_card_rects.append((card_name, pygame.Rect(card_x, card_y, card_w, card_h)))

        self.screen.set_clip(None)

    def _draw_squad(self, squad_builder: SquadBuilder):
        """Draw the squad section (bottom) - selected cards."""
        x = scaled(UILayout.DECK_BUILDER_LIBRARY_X)
        y = scaled(UILayout.DECK_BUILDER_DECK_Y)
        width = scaled(UILayout.DECK_BUILDER_LIBRARY_WIDTH)
        height = scaled(UILayout.DECK_BUILDER_DECK_HEIGHT)

        # Section background
        pygame.draw.rect(self.screen, (45, 40, 45), (x, y, width, height))
        pygame.draw.rect(self.screen, (100, 80, 100), (x, y, width, height), 2)

        # Section label with count
        squad_count = len(squad_builder.squad)
        label = self.fonts['small'].render(f"ОТРЯД ({squad_count} существ)", True, (150, 150, 170))
        self.screen.blit(label, (x + 5, y - scaled(18)))

        # Card dimensions
        card_w = scaled(UILayout.DECK_BUILDER_CARD_WIDTH)
        card_h = scaled(UILayout.DECK_BUILDER_CARD_HEIGHT)
        gap = scaled(UILayout.DECK_BUILDER_CARD_GAP)
        cards_per_row = UILayout.DECK_BUILDER_CARDS_PER_ROW
        padding = scaled(8)

        squad_cards = squad_builder.get_squad_cards()

        # Create clipping rect
        clip_rect = pygame.Rect(x, y, width, height)
        self.screen.set_clip(clip_rect)

        for i, (card_name, gold, silver) in enumerate(squad_cards):
            row = i // cards_per_row
            col = i % cards_per_row

            card_x = x + padding + col * (card_w + gap)
            card_y = y + padding + row * (card_h + gap) - self.squad_scroll

            # Skip if outside visible area
            if card_y + card_h < y or card_y > y + height:
                continue

            self._draw_squad_card(card_name, card_x, card_y, card_w, card_h,
                                  can_add=True, in_hand=False, gold_spent=gold, silver_spent=silver)
            self.squad_card_rects.append((card_name, pygame.Rect(card_x, card_y, card_w, card_h)))

        self.screen.set_clip(None)

    def _draw_squad_card(self, card_name: str, x: int, y: int, width: int, height: int,
                          can_add: bool, in_hand: bool, gold_spent: int = 0, silver_spent: int = 0):
        """Draw a single card in squad builder style."""
        stats = CARD_DATABASE.get(card_name)
        if not stats:
            return

        # Calculate name bar height and art area
        name_bar_height = height // 6
        art_height = height - name_bar_height

        # Get card image
        img_key = get_card_image(card_name)
        if img_key not in self.card_images:
            pygame.draw.rect(self.screen, (60, 60, 70), (x, y, width, art_height))
        else:
            img = self.card_images[img_key]
            img_scaled = pygame.transform.smoothscale(img, (width, art_height))

            # Dim if cannot add
            if not can_add and in_hand:
                img_scaled = img_scaled.copy()
                img_scaled.set_alpha(100)

            self.screen.blit(img_scaled, (x, y))

        # Draw YELLOW name bar below art
        name_bar_y = y + art_height
        pygame.draw.rect(self.screen, (180, 150, 50), (x, name_bar_y, width, name_bar_height))

        # Draw card name
        max_chars = width // 7
        display_name = card_name[:max_chars] + ".." if len(card_name) > max_chars else card_name
        name_font = self.fonts.get('card_name', self.fonts['small'])
        name_surface = name_font.render(display_name, True, (30, 25, 10))
        name_x = x + (width - name_surface.get_width()) // 2
        name_y = name_bar_y + (name_bar_height - name_surface.get_height()) // 2
        self.screen.blit(name_surface, (name_x, name_y))

        # Draw cost indicator (top-left)
        ind_w = scaled(UILayout.DECK_BUILDER_INDICATOR_WIDTH)
        ind_h = scaled(UILayout.DECK_BUILDER_INDICATOR_HEIGHT)
        cost_bg = (200, 170, 50) if stats.is_elite else (180, 180, 180)
        cost_text_color = (30, 20, 10) if stats.is_elite else (30, 30, 30)
        cost_rect = pygame.Rect(x + 2, y + 2, ind_w, ind_h)
        pygame.draw.rect(self.screen, cost_bg, cost_rect)
        pygame.draw.rect(self.screen, (50, 50, 60), cost_rect, 1)

        cost_text = self.fonts['indicator'].render(str(stats.cost), True, cost_text_color)
        cost_x = cost_rect.x + (ind_w - cost_text.get_width()) // 2
        cost_y = cost_rect.y + (ind_h - cost_text.get_height()) // 2
        self.screen.blit(cost_text, (cost_x, cost_y))

        # For squad cards, show spent crystals (top-right)
        if not in_hand and (gold_spent > 0 or silver_spent > 0):
            spent_text = ""
            if gold_spent > 0:
                spent_text += f"{gold_spent}g"
            if silver_spent > 0:
                if spent_text:
                    spent_text += "+"
                spent_text += f"{silver_spent}s"

            spent_surface = self.fonts['indicator'].render(spent_text, True, COLOR_TEXT)
            spent_rect = pygame.Rect(x + width - spent_surface.get_width() - 4, y + 2,
                                     spent_surface.get_width() + 4, ind_h)
            pygame.draw.rect(self.screen, (60, 60, 80), spent_rect)
            self.screen.blit(spent_surface, (spent_rect.x + 2, spent_rect.y + 2))

        # Flying indicator
        if stats.is_flying:
            fly_surface = self.fonts['indicator'].render("FLY", True, (100, 200, 255))
            self.screen.blit(fly_surface, (x + 2, y + ind_h + 4))

    def _draw_right_panel(self, squad_builder: SquadBuilder):
        """Draw the right panel with crystals and buttons."""
        x = scaled(UILayout.DECK_BUILDER_PANEL_X)
        panel_width = scaled(UILayout.DECK_BUILDER_PANEL_WIDTH)

        # Panel background
        pygame.draw.rect(self.screen, (45, 35, 35), (x, 0, panel_width, WINDOW_HEIGHT))
        pygame.draw.rect(self.screen, (80, 50, 50), (x, 0, 2, WINDOW_HEIGHT))

        y = scaled(50)

        # --- Crystal Display ---
        header = self.fonts['medium'].render("КРИСТАЛЛЫ", True, COLOR_TEXT)
        self.screen.blit(header, (x + scaled(15), y))

        y += scaled(35)

        # Gold crystals
        gold_color = (220, 180, 50)
        available_gold = squad_builder.get_available_gold()
        gold_text = self.fonts['medium'].render(f"Золото: {available_gold}", True, gold_color)
        self.screen.blit(gold_text, (x + scaled(15), y))

        y += scaled(28)

        # Silver crystals
        silver_color = (180, 180, 200)
        silver_text = self.fonts['medium'].render(f"Серебро: {squad_builder.silver}", True, silver_color)
        self.screen.blit(silver_text, (x + scaled(15), y))

        y += scaled(35)

        # Element penalty
        penalty = squad_builder.get_element_penalty()
        if penalty > 0:
            penalty_text = self.fonts['small'].render(f"Штраф за стихии: -{penalty} золота", True, (200, 100, 100))
            self.screen.blit(penalty_text, (x + scaled(15), y))
            y += scaled(22)

        # Flying cost
        flying_cost = squad_builder.get_flying_cost()
        fly_color = (100, 200, 255) if flying_cost <= 15 else (255, 100, 100)
        fly_text = self.fonts['small'].render(f"Летающие: {flying_cost}/15", True, fly_color)
        self.screen.blit(fly_text, (x + scaled(15), y))

        y += scaled(35)

        # --- Stats ---
        total_gold, total_silver = squad_builder.get_squad_total_cost()
        spent_text = self.fonts['small'].render(f"Потрачено: {total_gold}g + {total_silver}s", True, (150, 150, 160))
        self.screen.blit(spent_text, (x + scaled(15), y))

        y += scaled(22)

        squad_count = len(squad_builder.squad)
        count_text = self.fonts['small'].render(f"В отряде: {squad_count} существ", True, (150, 150, 160))
        self.screen.blit(count_text, (x + scaled(15), y))

        y += scaled(22)

        # Elements in squad
        elements = squad_builder.get_elements_in_squad()
        if elements:
            elem_names = ", ".join(e.value for e in elements)
            elem_text = self.fonts['small'].render(f"Стихии: {elem_names}", True, (150, 150, 160))
            self.screen.blit(elem_text, (x + scaled(15), y))

        # --- Buttons ---
        y = scaled(350)
        btn_width = panel_width - scaled(30)
        btn_height = scaled(40)
        btn_gap = scaled(12)

        # Mulligan button
        mulligan_rect = pygame.Rect(x + scaled(15), y, btn_width, btn_height)
        mulligan_color = (70, 50, 40) if squad_builder.gold >= 1 else (50, 40, 40)
        pygame.draw.rect(self.screen, mulligan_color, mulligan_rect)
        pygame.draw.rect(self.screen, (110, 80, 60), mulligan_rect, 2)

        mulligan_label = f"Пересдача (-1 золото)"
        mulligan_text = self.fonts['small'].render(mulligan_label, True, COLOR_TEXT)
        self.screen.blit(mulligan_text, (mulligan_rect.x + (btn_width - mulligan_text.get_width()) // 2,
                                         mulligan_rect.y + (btn_height - mulligan_text.get_height()) // 2))
        self.button_rects.append(("mulligan", mulligan_rect))

        y += btn_height + btn_gap

        # Mulligan count
        if squad_builder.mulligan_count > 0:
            mull_count = self.fonts['small'].render(f"Пересдач: {squad_builder.mulligan_count}", True, (120, 120, 140))
            self.screen.blit(mull_count, (x + scaled(15), y))
            y += scaled(25)

        y += scaled(20)

        # Confirm button
        confirm_rect = pygame.Rect(x + scaled(15), y, btn_width, btn_height)
        can_confirm = squad_builder.is_valid()
        confirm_color = (50, 80, 50) if can_confirm else (50, 50, 50)
        pygame.draw.rect(self.screen, confirm_color, confirm_rect)
        pygame.draw.rect(self.screen, (80, 130, 80) if can_confirm else (70, 70, 70), confirm_rect, 2)

        confirm_text = self.fonts['medium'].render("Подтвердить", True, COLOR_TEXT if can_confirm else (100, 100, 100))
        self.screen.blit(confirm_text, (confirm_rect.x + (btn_width - confirm_text.get_width()) // 2,
                                        confirm_rect.y + (btn_height - confirm_text.get_height()) // 2))
        self.button_rects.append(("confirm", confirm_rect))

    def _draw_notification(self):
        """Draw notification message."""
        popup_w = scaled(400)
        popup_h = scaled(50)
        popup_x = (WINDOW_WIDTH - popup_w) // 2
        popup_y = scaled(20)

        pygame.draw.rect(self.screen, (40, 60, 40), (popup_x, popup_y, popup_w, popup_h))
        pygame.draw.rect(self.screen, (80, 140, 80), (popup_x, popup_y, popup_w, popup_h), 2)

        text = self.fonts['medium'].render(self.notification_message, True, (200, 255, 200))
        text_x = popup_x + (popup_w - text.get_width()) // 2
        text_y = popup_y + (popup_h - text.get_height()) // 2
        self.screen.blit(text, (text_x, text_y))

    def _draw_card_popup(self, card_images_full: Dict):
        """Draw full card preview popup."""
        if not self.popup_card_name:
            return

        img_key = get_card_image(self.popup_card_name)
        if img_key not in card_images_full:
            self.popup_card_name = None
            return

        img = card_images_full[img_key]

        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        img_x = (WINDOW_WIDTH - img.get_width()) // 2
        img_y = (WINDOW_HEIGHT - img.get_height()) // 2
        self.screen.blit(img, (img_x, img_y))

    # --- Click detection ---

    def get_clicked_hand_card(self, x: int, y: int) -> Optional[str]:
        """Check if a hand card was clicked."""
        for card_name, rect in self.hand_card_rects:
            if rect.collidepoint(x, y):
                return card_name
        return None

    def get_clicked_squad_card(self, x: int, y: int) -> Optional[str]:
        """Check if a squad card was clicked."""
        for card_name, rect in self.squad_card_rects:
            if rect.collidepoint(x, y):
                return card_name
        return None

    def get_clicked_button(self, x: int, y: int) -> Optional[str]:
        """Check if a button was clicked."""
        for btn_id, rect in self.button_rects:
            if rect.collidepoint(x, y):
                return btn_id
        return None

    # --- Actions ---

    def show_notification(self, message: str):
        """Show a notification message."""
        self.notification_message = message
        self.notification_timer = 120

    def update_notification(self):
        """Update notification timer."""
        if self.notification_timer > 0:
            self.notification_timer -= 1
            if self.notification_timer <= 0:
                self.notification_message = ""

    def show_card_popup(self, card_name: str):
        """Show full card preview."""
        self.popup_card_name = card_name

    def hide_card_popup(self):
        """Hide card preview."""
        self.popup_card_name = None

    def scroll_hand(self, amount: int):
        """Scroll the hand section."""
        self.hand_scroll = max(0, self.hand_scroll - amount * scaled(30))

    def scroll_squad(self, amount: int):
        """Scroll the squad section."""
        self.squad_scroll = max(0, self.squad_scroll - amount * scaled(30))
