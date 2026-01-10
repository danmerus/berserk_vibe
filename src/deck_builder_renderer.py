"""Deck builder rendering module."""
import pygame
from typing import List, Tuple, Optional, Dict

from .constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT,
    UILayout, scaled
)
from .card_database import CARD_DATABASE, get_card_image
from .deck_builder import DeckBuilder


class DeckBuilderRenderer:
    """Handles all deck builder screen rendering."""

    def __init__(self, screen: pygame.Surface, card_images: Dict, fonts: Dict):
        """Initialize with shared resources from main renderer."""
        self.screen = screen
        self.card_images = card_images
        self.fonts = fonts

        # Click detection storage
        self.library_card_rects: List[Tuple[str, pygame.Rect]] = []
        self.deck_card_rects: List[Tuple[str, pygame.Rect]] = []
        self.button_rects: List[Tuple[str, pygame.Rect]] = []
        self.deck_list_rects: List[Tuple[str, pygame.Rect]] = []

        # Scroll state
        self.library_scroll = 0
        self.deck_scroll = 0
        self.library_max_scroll = 0

        # Scrollbar dragging
        self.dragging_scrollbar = False
        self.scrollbar_rect: Optional[pygame.Rect] = None

        # Input state for text entry
        self.text_input_active = False
        self.text_input_value = ""
        self.text_cursor_pos = 0
        self.cursor_blink_timer = 0

        # Popup for card preview
        self.popup_card_name: Optional[str] = None

        # Load list popup
        self.show_load_popup = False
        self.load_popup_decks: List[str] = []
        self.load_deck_rects: List[Tuple[str, pygame.Rect]] = []

        # Confirmation popup
        self.show_confirm_popup = False
        self.confirm_message = ""
        self.confirm_yes_rect: Optional[pygame.Rect] = None
        self.confirm_no_rect: Optional[pygame.Rect] = None

        # Notification popup (auto-dismiss)
        self.notification_message = ""
        self.notification_timer = 0

        # Pending action after text input
        self.pending_action: Optional[str] = None  # 'save', 'new', 'import', 'rename'
        self.pending_import_code: Optional[str] = None  # Store clipboard content for import

        # Double-click detection
        self.last_click_time = 0
        self.last_click_item: Optional[str] = None
        self.double_click_threshold = 400  # milliseconds

        # Custom header for deck selection mode
        self.custom_header: Optional[str] = None

        # Selection mode (hides save/load buttons, shows only confirm)
        self.selection_mode = False

    def draw(self, deck_builder: DeckBuilder, card_images_full: Dict):
        """Draw the complete deck builder screen."""
        self.screen.fill(COLOR_BG)

        # Draw custom header if set
        if self.custom_header:
            header = self.fonts['large'].render(self.custom_header, True, COLOR_TEXT)
            self.screen.blit(header, (scaled(10), scaled(10)))

        # Clear click detection lists
        self.library_card_rects.clear()
        self.deck_card_rects.clear()
        self.button_rects.clear()
        self.deck_list_rects.clear()

        # Draw sections
        self._draw_library(deck_builder)
        self._draw_deck(deck_builder)
        self._draw_right_panel(deck_builder)

        # Draw popups on top
        if self.show_load_popup:
            self._draw_load_popup()
        if self.text_input_active:
            self._draw_text_input()
        if self.show_confirm_popup:
            self._draw_confirm_popup()
        if self.popup_card_name:
            self._draw_card_popup(card_images_full)
        if self.notification_message:
            self._draw_notification()

    def _draw_library(self, deck_builder: DeckBuilder):
        """Draw the library section (top) with scrollbar."""
        x = scaled(UILayout.DECK_BUILDER_LIBRARY_X)
        y = scaled(UILayout.DECK_BUILDER_LIBRARY_Y)
        width = scaled(UILayout.DECK_BUILDER_LIBRARY_WIDTH)
        height = scaled(UILayout.DECK_BUILDER_LIBRARY_HEIGHT)
        scrollbar_w = scaled(UILayout.DECK_BUILDER_SCROLLBAR_WIDTH)

        # Section background
        pygame.draw.rect(self.screen, (40, 40, 50), (x, y, width, height))
        pygame.draw.rect(self.screen, (80, 80, 100), (x, y, width, height), 2)

        # Section label
        label = self.fonts['small'].render("БИБЛИОТЕКА", True, (150, 150, 170))
        self.screen.blit(label, (x + 5, y - scaled(18)))

        # Card dimensions
        card_w = scaled(UILayout.DECK_BUILDER_CARD_WIDTH)
        card_h = scaled(UILayout.DECK_BUILDER_CARD_HEIGHT)
        gap = scaled(UILayout.DECK_BUILDER_CARD_GAP)
        cards_per_row = UILayout.DECK_BUILDER_CARDS_PER_ROW
        padding = scaled(8)

        # Content area (excluding scrollbar)
        content_width = width - scrollbar_w - padding

        library_cards = deck_builder.get_library_cards()
        total_rows = (len(library_cards) + cards_per_row - 1) // cards_per_row
        total_content_height = total_rows * (card_h + gap)
        self.library_max_scroll = max(0, total_content_height - height + padding * 2)

        # Clamp scroll
        self.library_scroll = max(0, min(self.library_scroll, self.library_max_scroll))

        # Create clipping rect for cards
        clip_rect = pygame.Rect(x, y, width - scrollbar_w, height)
        self.screen.set_clip(clip_rect)

        for i, (card_name, remaining) in enumerate(library_cards):
            row = i // cards_per_row
            col = i % cards_per_row

            card_x = x + padding + col * (card_w + gap)
            card_y = y + padding + row * (card_h + gap) - self.library_scroll

            # Skip if outside visible area
            if card_y + card_h < y or card_y > y + height:
                continue

            self._draw_builder_card(card_name, card_x, card_y, card_w, card_h, remaining, is_library=True)
            self.library_card_rects.append((card_name, pygame.Rect(card_x, card_y, card_w, card_h)))

        self.screen.set_clip(None)

        # Draw scrollbar
        if self.library_max_scroll > 0:
            self._draw_scrollbar(x + width - scrollbar_w, y, scrollbar_w, height)

    def _draw_scrollbar(self, x: int, y: int, width: int, height: int):
        """Draw a scrollbar for the library."""
        # Track background
        pygame.draw.rect(self.screen, (50, 50, 60), (x, y, width, height))

        # Calculate thumb size and position
        if self.library_max_scroll > 0:
            visible_ratio = height / (height + self.library_max_scroll)
            thumb_height = max(scaled(30), int(height * visible_ratio))
            scroll_ratio = self.library_scroll / self.library_max_scroll
            thumb_y = y + int((height - thumb_height) * scroll_ratio)

            # Thumb
            thumb_rect = pygame.Rect(x + 2, thumb_y, width - 4, thumb_height)
            color = (100, 100, 120) if not self.dragging_scrollbar else (120, 120, 140)
            pygame.draw.rect(self.screen, color, thumb_rect, border_radius=3)

            self.scrollbar_rect = pygame.Rect(x, y, width, height)

    def _draw_deck(self, deck_builder: DeckBuilder):
        """Draw the deck section (bottom)."""
        x = scaled(UILayout.DECK_BUILDER_LIBRARY_X)
        y = scaled(UILayout.DECK_BUILDER_DECK_Y)
        width = scaled(UILayout.DECK_BUILDER_LIBRARY_WIDTH)
        height = scaled(UILayout.DECK_BUILDER_DECK_HEIGHT)

        # Section background
        pygame.draw.rect(self.screen, (45, 40, 45), (x, y, width, height))
        pygame.draw.rect(self.screen, (100, 80, 100), (x, y, width, height), 2)

        # Section label with count
        total = deck_builder.get_total_count()
        valid_color = (100, 200, 100) if deck_builder.is_valid() else (200, 100, 100)
        label = self.fonts['small'].render(f"КОЛОДА ({total}/30-50)", True, valid_color)
        self.screen.blit(label, (x + 5, y - scaled(18)))

        # Card dimensions
        card_w = scaled(UILayout.DECK_BUILDER_CARD_WIDTH)
        card_h = scaled(UILayout.DECK_BUILDER_CARD_HEIGHT)
        gap = scaled(UILayout.DECK_BUILDER_CARD_GAP)
        cards_per_row = UILayout.DECK_BUILDER_CARDS_PER_ROW
        padding = scaled(8)

        deck_cards = deck_builder.get_deck_cards()

        # Create clipping rect
        clip_rect = pygame.Rect(x, y, width, height)
        self.screen.set_clip(clip_rect)

        for i, (card_name, count) in enumerate(deck_cards):
            row = i // cards_per_row
            col = i % cards_per_row

            card_x = x + padding + col * (card_w + gap)
            card_y = y + padding + row * (card_h + gap) - self.deck_scroll

            # Skip if outside visible area
            if card_y + card_h < y or card_y > y + height:
                continue

            self._draw_builder_card(card_name, card_x, card_y, card_w, card_h, count, is_library=False)
            self.deck_card_rects.append((card_name, pygame.Rect(card_x, card_y, card_w, card_h)))

        self.screen.set_clip(None)

    def _draw_builder_card(self, card_name: str, x: int, y: int, width: int, height: int,
                           count: int, is_library: bool):
        """Draw a single card in deck builder style with name bar below art."""
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

            # Scale image to fit the art area (above name bar)
            img_scaled = pygame.transform.smoothscale(img, (width, art_height))

            # Draw with reduced opacity if count is 0
            if count <= 0:
                img_scaled = img_scaled.copy()
                img_scaled.set_alpha(80)
            self.screen.blit(img_scaled, (x, y))

        # Draw YELLOW name bar below art
        name_bar_y = y + art_height
        pygame.draw.rect(self.screen, (180, 150, 50), (x, name_bar_y, width, name_bar_height))

        # Draw card name (truncated if needed) - dark text on yellow
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
        cost_bg = (200, 170, 50) if stats.is_elite else (220, 220, 220)
        cost_text_color = (30, 20, 10) if stats.is_elite else (30, 30, 30)
        cost_rect = pygame.Rect(x + 2, y + 2, ind_w, ind_h)
        pygame.draw.rect(self.screen, cost_bg, cost_rect)
        pygame.draw.rect(self.screen, (50, 50, 60), cost_rect, 1)

        cost_text = self.fonts['indicator'].render(str(stats.cost), True, cost_text_color)
        cost_x = cost_rect.x + (ind_w - cost_text.get_width()) // 2
        cost_y = cost_rect.y + (ind_h - cost_text.get_height()) // 2
        self.screen.blit(cost_text, (cost_x, cost_y))

        # Draw count indicator (top-right)
        count_bg = (70, 130, 200) if is_library else (130, 70, 130)
        count_rect = pygame.Rect(x + width - ind_w - 2, y + 2, ind_w, ind_h)
        pygame.draw.rect(self.screen, count_bg, count_rect)
        pygame.draw.rect(self.screen, (50, 50, 60), count_rect, 1)

        count_text = self.fonts['indicator'].render(str(count), True, COLOR_TEXT)
        count_x = count_rect.x + (ind_w - count_text.get_width()) // 2
        count_y = count_rect.y + (ind_h - count_text.get_height()) // 2
        self.screen.blit(count_text, (count_x, count_y))

    def _draw_right_panel(self, deck_builder: DeckBuilder):
        """Draw the right panel with deck name, deck list, and buttons."""
        x = scaled(UILayout.DECK_BUILDER_PANEL_X)
        panel_width = scaled(UILayout.DECK_BUILDER_PANEL_WIDTH)

        # Panel background
        pygame.draw.rect(self.screen, (45, 35, 35), (x, 0, panel_width, WINDOW_HEIGHT))
        pygame.draw.rect(self.screen, (80, 50, 50), (x, 0, 2, WINDOW_HEIGHT))

        # --- Deck Name Section ---
        y = scaled(20)
        header = self.fonts['medium'].render("Название деки", True, COLOR_TEXT)
        self.screen.blit(header, (x + scaled(15), y))

        y += scaled(28)
        name_text = self.fonts['medium'].render(deck_builder.name, True, (180, 180, 150))
        self.screen.blit(name_text, (x + scaled(15), y))

        # --- Saved Decks List ---
        y += scaled(50)
        list_header = self.fonts['small'].render("Сохранённые колоды:", True, (150, 150, 160))
        self.screen.blit(list_header, (x + scaled(15), y))

        y += scaled(25)
        list_height = scaled(200)
        list_rect = pygame.Rect(x + scaled(10), y, panel_width - scaled(20), list_height)
        pygame.draw.rect(self.screen, (55, 45, 45), list_rect)
        pygame.draw.rect(self.screen, (90, 60, 60), list_rect, 1)

        # Draw saved decks
        saved_decks = DeckBuilder.list_saved_decks()
        item_height = scaled(28)
        item_y = y + scaled(5)

        for deck_path in saved_decks[:6]:  # Show up to 6 decks
            if item_y + item_height > y + list_height - scaled(5):
                break

            deck_name = DeckBuilder.get_deck_name_from_file(deck_path)
            item_rect = pygame.Rect(x + scaled(15), item_y, panel_width - scaled(30), item_height - 3)

            # Highlight if this is current deck
            if deck_builder.file_path == deck_path:
                pygame.draw.rect(self.screen, (80, 60, 60), item_rect)
            else:
                pygame.draw.rect(self.screen, (60, 50, 50), item_rect)

            pygame.draw.rect(self.screen, (100, 70, 70), item_rect, 1)

            # Truncate name to fit in item rect
            max_width = item_rect.width - 16
            display_name = deck_name
            name_surface = self.fonts['small'].render(display_name, True, COLOR_TEXT)
            while name_surface.get_width() > max_width and len(display_name) > 3:
                display_name = display_name[:-1]
                name_surface = self.fonts['small'].render(display_name + "..", True, COLOR_TEXT)
            self.screen.blit(name_surface, (item_rect.x + 8, item_rect.y + 4))

            self.deck_list_rects.append((deck_path, item_rect))
            item_y += item_height

        # --- Buttons ---
        y = y + list_height + scaled(20)
        btn_height = scaled(32)
        btn_gap = scaled(8)

        if self.selection_mode:
            # Selection mode: only confirm and back buttons
            full_btn_width = panel_width - scaled(30)

            # Confirm selection button
            confirm_rect = pygame.Rect(x + scaled(15), y, full_btn_width, scaled(40))
            can_confirm = deck_builder.is_valid()
            bg_color = (50, 80, 50) if can_confirm else (50, 50, 50)
            border_color = (80, 130, 80) if can_confirm else (70, 70, 70)
            pygame.draw.rect(self.screen, bg_color, confirm_rect)
            pygame.draw.rect(self.screen, border_color, confirm_rect, 2)

            confirm_text = self.fonts['medium'].render("Подтвердить выбор", True,
                                                        COLOR_TEXT if can_confirm else (100, 100, 100))
            self.screen.blit(confirm_text, (confirm_rect.x + (full_btn_width - confirm_text.get_width()) // 2,
                                            confirm_rect.y + (scaled(40) - confirm_text.get_height()) // 2))
            self.button_rects.append(("confirm_selection", confirm_rect))

            y += scaled(40) + btn_gap

            # Back button
            back_rect = pygame.Rect(x + scaled(15), y, full_btn_width, btn_height)
            pygame.draw.rect(self.screen, (60, 50, 60), back_rect)
            pygame.draw.rect(self.screen, (100, 80, 100), back_rect, 2)

            back_text = self.fonts['small'].render("Назад", True, COLOR_TEXT)
            self.screen.blit(back_text, (back_rect.x + (full_btn_width - back_text.get_width()) // 2,
                                         back_rect.y + (btn_height - back_text.get_height()) // 2))
            self.button_rects.append(("back", back_rect))
        else:
            # Normal mode: all buttons
            btn_width = (panel_width - scaled(40)) // 2

            # Button pairs: (id1, text1), (id2, text2)
            button_rows = [
                (("load", "Загрузить"), ("save", "Сохранить")),
                (("import", "Импорт"), ("export", "Экспорт")),
                (("delete", "Удалить"), ("new", "Новая")),
            ]

            for row_btns in button_rows:
                for col, (btn_id, btn_text) in enumerate(row_btns):
                    btn_x = x + scaled(15) + col * (btn_width + btn_gap)
                    btn_rect = pygame.Rect(btn_x, y, btn_width, btn_height)

                    # Button color - all dark red style
                    bg_color = (70, 40, 40)
                    border_color = (110, 60, 60)

                    pygame.draw.rect(self.screen, bg_color, btn_rect)
                    pygame.draw.rect(self.screen, border_color, btn_rect, 2)

                    text_surface = self.fonts['small'].render(btn_text, True, COLOR_TEXT)
                    text_x = btn_rect.x + (btn_width - text_surface.get_width()) // 2
                    text_y = btn_rect.y + (btn_height - text_surface.get_height()) // 2
                    self.screen.blit(text_surface, (text_x, text_y))

                    self.button_rects.append((btn_id, btn_rect))

                y += btn_height + btn_gap

            # Back button (full width)
            y += scaled(10)
            back_rect = pygame.Rect(x + scaled(15), y, panel_width - scaled(30), btn_height)
            pygame.draw.rect(self.screen, (60, 50, 60), back_rect)
            pygame.draw.rect(self.screen, (100, 80, 100), back_rect, 2)

            back_text = self.fonts['small'].render("Назад в меню", True, COLOR_TEXT)
            self.screen.blit(back_text, (back_rect.x + (back_rect.width - back_text.get_width()) // 2,
                                         back_rect.y + (btn_height - back_text.get_height()) // 2))
            self.button_rects.append(("back", back_rect))

        # --- Statistics ---
        y += btn_height + scaled(25)
        self._draw_stats_section(x, y, panel_width, deck_builder)

    def _draw_stats_section(self, x: int, y: int, panel_width: int, deck_builder: DeckBuilder):
        """Draw deck statistics."""
        stats_header = self.fonts['small'].render("СТАТИСТИКА", True, (150, 150, 160))
        self.screen.blit(stats_header, (x + scaled(15), y))

        y += scaled(22)
        line_height = scaled(18)

        # Calculate stats
        deck_cards = deck_builder.get_deck_cards()
        total_cards = deck_builder.get_total_count()

        element_counts = {}
        elite_count = 0
        total_cost = 0

        for card_name, count in deck_cards:
            stats = CARD_DATABASE[card_name]
            element_name = stats.element.value
            element_counts[element_name] = element_counts.get(element_name, 0) + count
            if stats.is_elite:
                elite_count += count
            total_cost += stats.cost * count

        # Total cards
        color = (100, 200, 100) if deck_builder.is_valid() else (200, 150, 100)
        self._draw_stat_line(x + scaled(15), y, f"Карт: {total_cards}/30-50", color)
        y += line_height

        # Elements
        for element, count in sorted(element_counts.items()):
            self._draw_stat_line(x + scaled(15), y, f"{element}: {count}")
            y += line_height

        # Elite and average cost
        if total_cards > 0:
            y += scaled(5)
            self._draw_stat_line(x + scaled(15), y, f"Элитных: {elite_count}")
            y += line_height
            avg_cost = total_cost / total_cards
            self._draw_stat_line(x + scaled(15), y, f"Ср. цена: {avg_cost:.1f}")

    def _draw_stat_line(self, x: int, y: int, text: str, color: Tuple[int, int, int] = None):
        """Draw a statistics line."""
        if color is None:
            color = (160, 160, 170)
        surface = self.fonts['small'].render(text, True, color)
        self.screen.blit(surface, (x, y))

    def _draw_text_input(self):
        """Draw text input popup for deck name."""
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        popup_w = scaled(400)
        popup_h = scaled(150)
        popup_x = (WINDOW_WIDTH - popup_w) // 2
        popup_y = (WINDOW_HEIGHT - popup_h) // 2

        pygame.draw.rect(self.screen, (50, 50, 60), (popup_x, popup_y, popup_w, popup_h))
        pygame.draw.rect(self.screen, (120, 120, 140), (popup_x, popup_y, popup_w, popup_h), 3)

        title = self.fonts['medium'].render("Название колоды:", True, COLOR_TEXT)
        self.screen.blit(title, (popup_x + 20, popup_y + 20))

        input_rect = pygame.Rect(popup_x + 20, popup_y + 55, popup_w - 40, scaled(35))
        pygame.draw.rect(self.screen, (30, 30, 40), input_rect)
        pygame.draw.rect(self.screen, (100, 100, 120), input_rect, 2)

        # Draw text with cursor
        text_before_cursor = self.text_input_value[:self.text_cursor_pos]
        text_after_cursor = self.text_input_value[self.text_cursor_pos:]

        # Render text before cursor to get cursor x position
        before_surface = self.fonts['medium'].render(text_before_cursor, True, COLOR_TEXT)
        full_surface = self.fonts['medium'].render(self.text_input_value, True, COLOR_TEXT)

        text_x = input_rect.x + 10
        text_y = input_rect.y + (input_rect.height - full_surface.get_height()) // 2
        self.screen.blit(full_surface, (text_x, text_y))

        # Draw blinking cursor
        self.cursor_blink_timer = (self.cursor_blink_timer + 1) % 60
        if self.cursor_blink_timer < 30:
            cursor_x = text_x + before_surface.get_width()
            cursor_y = text_y
            cursor_h = full_surface.get_height()
            pygame.draw.line(self.screen, COLOR_TEXT, (cursor_x, cursor_y), (cursor_x, cursor_y + cursor_h), 2)

        hint = self.fonts['small'].render("Enter - подтвердить, Esc - отмена, Ctrl+V - вставить", True, (120, 120, 140))
        self.screen.blit(hint, (popup_x + 20, popup_y + 110))

    def _draw_load_popup(self):
        """Draw deck selection popup for loading."""
        self.load_deck_rects.clear()

        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        popup_w = scaled(500)
        popup_h = scaled(400)
        popup_x = (WINDOW_WIDTH - popup_w) // 2
        popup_y = (WINDOW_HEIGHT - popup_h) // 2

        pygame.draw.rect(self.screen, (50, 50, 60), (popup_x, popup_y, popup_w, popup_h))
        pygame.draw.rect(self.screen, (120, 120, 140), (popup_x, popup_y, popup_w, popup_h), 3)

        title = self.fonts['large'].render("Загрузить колоду", True, COLOR_TEXT)
        self.screen.blit(title, (popup_x + 20, popup_y + 15))

        list_y = popup_y + scaled(60)
        item_height = scaled(40)

        for i, deck_path in enumerate(self.load_popup_decks):
            item_y = list_y + i * item_height
            if item_y > popup_y + popup_h - scaled(60):
                break

            deck_name = DeckBuilder.get_deck_name_from_file(deck_path)
            item_rect = pygame.Rect(popup_x + 20, item_y, popup_w - 40, item_height - 5)

            pygame.draw.rect(self.screen, (60, 60, 70), item_rect)
            pygame.draw.rect(self.screen, (90, 90, 110), item_rect, 1)

            name_text = self.fonts['medium'].render(deck_name, True, COLOR_TEXT)
            self.screen.blit(name_text, (item_rect.x + 15, item_rect.y + 8))

            self.load_deck_rects.append((deck_path, item_rect))

        hint = self.fonts['small'].render("Esc - закрыть", True, (120, 120, 140))
        self.screen.blit(hint, (popup_x + 20, popup_y + popup_h - scaled(30)))

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

    # Click detection methods

    def get_clicked_library_card(self, x: int, y: int) -> Optional[str]:
        """Check if a library card was clicked."""
        for card_name, rect in self.library_card_rects:
            if rect.collidepoint(x, y):
                return card_name
        return None

    def get_clicked_deck_card(self, x: int, y: int) -> Optional[str]:
        """Check if a deck card was clicked."""
        for card_name, rect in self.deck_card_rects:
            if rect.collidepoint(x, y):
                return card_name
        return None

    def get_clicked_button(self, x: int, y: int) -> Optional[str]:
        """Check if a button was clicked."""
        for btn_id, rect in self.button_rects:
            if rect.collidepoint(x, y):
                return btn_id
        return None

    def get_clicked_deck_list_item(self, x: int, y: int) -> Optional[str]:
        """Check if a deck in the list was clicked."""
        for deck_path, rect in self.deck_list_rects:
            if rect.collidepoint(x, y):
                return deck_path
        return None

    def handle_deck_list_click(self, deck_path: str, deck_builder: DeckBuilder) -> bool:
        """Handle click on deck list item. Returns True if handled (double-click rename)."""
        current_time = pygame.time.get_ticks()

        # Check for double-click on same item
        if (self.last_click_item == deck_path and
            current_time - self.last_click_time < self.double_click_threshold):
            # Double-click detected - try to rename
            # First load the deck to check if it's protected
            deck_builder.load(deck_path)
            if deck_builder.is_protected():
                self.show_notification("Защищённую колоду нельзя переименовать")
            else:
                self.pending_action = 'rename'
                self.start_text_input(deck_builder.name)
            # Reset double-click tracking
            self.last_click_time = 0
            self.last_click_item = None
            return True
        else:
            # Single click - just load the deck
            self.last_click_time = current_time
            self.last_click_item = deck_path
            deck_builder.load(deck_path)
            return False

    def get_clicked_load_deck(self, x: int, y: int) -> Optional[str]:
        """Check if a deck in load popup was clicked."""
        for deck_path, rect in self.load_deck_rects:
            if rect.collidepoint(x, y):
                return deck_path
        return None

    def show_card_popup(self, card_name: str):
        """Show full card preview."""
        self.popup_card_name = card_name

    def hide_card_popup(self):
        """Hide card preview."""
        self.popup_card_name = None

    def start_text_input(self, initial_value: str = ""):
        """Start text input mode."""
        self.text_input_active = True
        self.text_input_value = initial_value
        self.text_cursor_pos = len(initial_value)
        pygame.key.start_text_input()

    def stop_text_input(self):
        """Stop text input mode."""
        self.text_input_active = False
        self.text_input_value = ""
        self.text_cursor_pos = 0
        pygame.key.stop_text_input()

    def handle_text_input(self, event: pygame.event.Event) -> Optional[str]:
        """Handle text input events. Returns value on Enter, None otherwise."""
        if not self.text_input_active:
            return None

        # Handle TEXTINPUT events (actual character input)
        if event.type == pygame.TEXTINPUT:
            # Insert text at cursor position
            self.text_input_value = (self.text_input_value[:self.text_cursor_pos] +
                                     event.text +
                                     self.text_input_value[self.text_cursor_pos:])
            self.text_cursor_pos += len(event.text)
            return None

        # Handle KEYDOWN for control keys
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                value = self.text_input_value
                self.stop_text_input()
                return value
            elif event.key == pygame.K_ESCAPE:
                self.stop_text_input()
                return None
            elif event.key == pygame.K_BACKSPACE:
                if self.text_cursor_pos > 0:
                    self.text_input_value = (self.text_input_value[:self.text_cursor_pos-1] +
                                             self.text_input_value[self.text_cursor_pos:])
                    self.text_cursor_pos -= 1
            elif event.key == pygame.K_DELETE:
                if self.text_cursor_pos < len(self.text_input_value):
                    self.text_input_value = (self.text_input_value[:self.text_cursor_pos] +
                                             self.text_input_value[self.text_cursor_pos+1:])
            elif event.key == pygame.K_LEFT:
                self.text_cursor_pos = max(0, self.text_cursor_pos - 1)
            elif event.key == pygame.K_RIGHT:
                self.text_cursor_pos = min(len(self.text_input_value), self.text_cursor_pos + 1)
            elif event.key == pygame.K_HOME:
                self.text_cursor_pos = 0
            elif event.key == pygame.K_END:
                self.text_cursor_pos = len(self.text_input_value)
            elif event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
                # Ctrl+V - Paste
                try:
                    pygame.scrap.init()
                    clipboard = pygame.scrap.get(pygame.SCRAP_TEXT)
                    if clipboard:
                        paste_text = clipboard.decode('utf-8').rstrip('\x00')
                        self.text_input_value = (self.text_input_value[:self.text_cursor_pos] +
                                                 paste_text +
                                                 self.text_input_value[self.text_cursor_pos:])
                        self.text_cursor_pos += len(paste_text)
                except Exception:
                    pass
            elif event.key == pygame.K_a and (event.mod & pygame.KMOD_CTRL):
                # Ctrl+A - Select all (just move cursor to end for now)
                self.text_cursor_pos = len(self.text_input_value)

        return None

    def hide_load_popup(self):
        """Hide the load deck popup."""
        self.show_load_popup = False

    def scroll_library(self, amount: int):
        """Scroll the library section."""
        self.library_scroll = max(0, min(self.library_scroll - amount * scaled(30), self.library_max_scroll))

    def scroll_deck(self, amount: int):
        """Scroll the deck section."""
        self.deck_scroll = max(0, self.deck_scroll - amount * scaled(30))

    def start_scrollbar_drag(self, x: int, y: int) -> bool:
        """Start dragging the scrollbar if clicked."""
        if self.scrollbar_rect and self.scrollbar_rect.collidepoint(x, y):
            self.dragging_scrollbar = True
            return True
        return False

    def drag_scrollbar(self, y: int):
        """Update scroll position while dragging."""
        if not self.dragging_scrollbar or not self.scrollbar_rect:
            return

        # Calculate scroll position from mouse y
        track_y = self.scrollbar_rect.y
        track_h = self.scrollbar_rect.height
        relative_y = y - track_y
        scroll_ratio = max(0, min(1, relative_y / track_h))
        self.library_scroll = int(scroll_ratio * self.library_max_scroll)

    def stop_scrollbar_drag(self):
        """Stop dragging the scrollbar."""
        self.dragging_scrollbar = False

    def _draw_notification(self):
        """Draw notification message at top of screen."""
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

    def _draw_confirm_popup(self):
        """Draw confirmation popup for delete action."""
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        popup_w = scaled(400)
        popup_h = scaled(150)
        popup_x = (WINDOW_WIDTH - popup_w) // 2
        popup_y = (WINDOW_HEIGHT - popup_h) // 2

        pygame.draw.rect(self.screen, (60, 40, 40), (popup_x, popup_y, popup_w, popup_h))
        pygame.draw.rect(self.screen, (140, 80, 80), (popup_x, popup_y, popup_w, popup_h), 3)

        # Message
        message = self.fonts['medium'].render(self.confirm_message, True, COLOR_TEXT)
        msg_x = popup_x + (popup_w - message.get_width()) // 2
        self.screen.blit(message, (msg_x, popup_y + scaled(30)))

        # Buttons
        btn_width = scaled(100)
        btn_height = scaled(35)
        btn_y = popup_y + popup_h - scaled(55)
        gap = scaled(30)

        # Yes button
        yes_x = popup_x + popup_w // 2 - btn_width - gap // 2
        self.confirm_yes_rect = pygame.Rect(yes_x, btn_y, btn_width, btn_height)
        pygame.draw.rect(self.screen, (80, 50, 50), self.confirm_yes_rect)
        pygame.draw.rect(self.screen, (120, 70, 70), self.confirm_yes_rect, 2)
        yes_text = self.fonts['medium'].render("Да", True, COLOR_TEXT)
        self.screen.blit(yes_text, (yes_x + (btn_width - yes_text.get_width()) // 2,
                                    btn_y + (btn_height - yes_text.get_height()) // 2))

        # No button
        no_x = popup_x + popup_w // 2 + gap // 2
        self.confirm_no_rect = pygame.Rect(no_x, btn_y, btn_width, btn_height)
        pygame.draw.rect(self.screen, (50, 50, 70), self.confirm_no_rect)
        pygame.draw.rect(self.screen, (70, 70, 100), self.confirm_no_rect, 2)
        no_text = self.fonts['medium'].render("Нет", True, COLOR_TEXT)
        self.screen.blit(no_text, (no_x + (btn_width - no_text.get_width()) // 2,
                                   btn_y + (btn_height - no_text.get_height()) // 2))

    def show_confirmation(self, message: str):
        """Show confirmation popup."""
        self.show_confirm_popup = True
        self.confirm_message = message

    def hide_confirmation(self):
        """Hide confirmation popup."""
        self.show_confirm_popup = False
        self.confirm_message = ""

    def get_clicked_confirm_button(self, x: int, y: int) -> Optional[str]:
        """Check if a confirmation button was clicked."""
        if self.confirm_yes_rect and self.confirm_yes_rect.collidepoint(x, y):
            return 'yes'
        if self.confirm_no_rect and self.confirm_no_rect.collidepoint(x, y):
            return 'no'
        return None

    def handle_button_action(self, btn_id: str, deck_builder: DeckBuilder) -> Optional[str]:
        """Handle button click action. Returns 'back' if should return to menu, else None."""
        if btn_id == 'back':
            return 'back'
        elif btn_id == 'new':
            self.pending_action = 'new'
            self.start_text_input("Новая колода")
        elif btn_id == 'save':
            # If deck already has a file, just save. Otherwise prompt for name.
            if deck_builder.file_path and not deck_builder.is_protected():
                if deck_builder.save():
                    self.show_notification("Колода сохранена")
                else:
                    self.show_notification("Не удалось сохранить")
            elif deck_builder.is_protected():
                # Protected deck - must save as new
                self.pending_action = 'save'
                self.start_text_input(deck_builder.name + " (копия)")
            else:
                # New deck - prompt for name
                self.pending_action = 'save'
                self.start_text_input(deck_builder.name)
        elif btn_id == 'load':
            self.load_popup_decks = DeckBuilder.list_saved_decks()
            self.show_load_popup = True
        elif btn_id == 'export':
            code = deck_builder.export_code()
            if code:
                try:
                    pygame.scrap.init()
                    pygame.scrap.put(pygame.SCRAP_TEXT, code.encode('utf-8'))
                    self.show_notification("Код скопирован в буфер обмена")
                except Exception as e:
                    # Fallback: print to console
                    print(f"Deck code: {code}")
                    self.show_notification("Код выведен в консоль")
        elif btn_id == 'import':
            # First check if clipboard has valid data
            try:
                pygame.scrap.init()
                clipboard_data = pygame.scrap.get(pygame.SCRAP_TEXT)
                if clipboard_data:
                    code = clipboard_data.decode('utf-8').rstrip('\x00')
                    if code.strip():
                        # Store the code and prompt for deck name
                        self.pending_import_code = code.strip()
                        self.pending_action = 'import'
                        self.start_text_input("Импортированная колода")
                    else:
                        self.show_notification("Буфер обмена пуст")
                else:
                    self.show_notification("Буфер обмена пуст")
            except Exception as e:
                self.show_notification("Ошибка чтения буфера")
        elif btn_id == 'delete':
            if deck_builder.is_protected():
                self.show_notification("Защищённую колоду нельзя удалить")
            elif deck_builder.file_path:
                self.show_confirmation("Удалить эту колоду?")
            else:
                self.show_notification("Колода не сохранена")
        return None

    def show_notification(self, message: str):
        """Show a notification message."""
        self.notification_message = message
        self.notification_timer = 120  # frames (2 seconds at 60fps)

    def update_notification(self):
        """Update notification timer. Call each frame."""
        if self.notification_timer > 0:
            self.notification_timer -= 1
            if self.notification_timer <= 0:
                self.notification_message = ""

    def handle_confirm_action(self, choice: str, deck_builder: DeckBuilder):
        """Handle confirmation popup choice."""
        if choice == 'yes':
            # Double-check protection before deleting
            if deck_builder.is_protected():
                self.show_notification("Защищённую колоду нельзя удалить")
            else:
                if deck_builder.delete():
                    self.show_notification("Колода удалена")
                else:
                    self.show_notification("Не удалось удалить колоду")
        self.hide_confirmation()

    def handle_text_input_result(self, result: Optional[str], deck_builder: DeckBuilder):
        """Handle text input completion based on pending action."""
        if result is None:
            # Cancelled
            self.pending_action = None
            self.pending_import_code = None
            return

        if self.pending_action == 'save':
            # Save with new name
            if result.strip():
                if deck_builder.save(new_name=result.strip()):
                    self.show_notification("Колода сохранена")
                else:
                    self.show_notification("Не удалось сохранить")
        elif self.pending_action == 'new':
            # Create new empty deck and save it
            deck_name = result.strip() if result.strip() else "Новая колода"
            deck_builder.new_deck(deck_name)
            if deck_builder.save():
                self.show_notification("Новая колода создана")
            else:
                self.show_notification("Не удалось создать колоду")
        elif self.pending_action == 'import':
            # Import using stored clipboard code
            if self.pending_import_code:
                if deck_builder.import_code(self.pending_import_code):
                    # Set the name and save to file
                    deck_name = result.strip() if result.strip() else "Импортированная колода"
                    deck_builder.name = deck_name
                    if deck_builder.save():
                        self.show_notification("Колода импортирована и сохранена")
                    else:
                        self.show_notification("Импорт успешен, но не удалось сохранить")
                else:
                    self.show_notification("Ошибка импорта: неверный код")
            else:
                self.show_notification("Нет данных для импорта")
            self.pending_import_code = None
        elif self.pending_action == 'rename':
            # Rename the deck (save with new name)
            if result.strip():
                if deck_builder.save(new_name=result.strip()):
                    self.show_notification("Колода переименована")
                else:
                    self.show_notification("Не удалось переименовать")

        self.pending_action = None
