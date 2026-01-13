"""Placement phase rendering."""
import pygame
from typing import Dict, List, Optional, Tuple

from .constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT,
    BOARD_COLS, BOARD_ROWS, CELL_SIZE, BOARD_OFFSET_X, BOARD_OFFSET_Y,
    COLOR_GRID_LINE, COLOR_BOARD_LIGHT, COLOR_BOARD_DARK,
    COLOR_PLAYER1, COLOR_PLAYER2,
    scaled, UILayout
)
from .card import Card
from .card_database import get_card_image
from .placement import PlacementState


class PlacementRenderer:
    """Renders the placement phase screen."""

    def __init__(self, screen: pygame.Surface, card_images: Dict, fonts: Dict):
        """Initialize with shared resources."""
        self.screen = screen
        self.card_images = card_images
        self.fonts = fonts

        # Click detection
        self.unplaced_card_rects: List[Tuple[Card, pygame.Rect]] = []
        self.placed_card_rects: List[Tuple[int, pygame.Rect]] = []  # position -> rect
        self.legal_position_rects: List[Tuple[int, pygame.Rect]] = []

        # Confirm button
        self.confirm_rect: Optional[pygame.Rect] = None

        # Current player (for board flipping)
        self._current_player: int = 1

    def draw(self, state: PlacementState, mouse_pos: Tuple[int, int]):
        """Draw the placement screen."""
        self.screen.fill(COLOR_BG)
        self._current_player = state.player

        # Clear detection lists
        self.unplaced_card_rects.clear()
        self.placed_card_rects.clear()
        self.legal_position_rects.clear()

        # Draw header
        self._draw_header(state)

        # Draw board
        self._draw_board(state)

        # Draw unplaced cards on opponent's side
        self._draw_unplaced_cards(state)

        # Draw legal position markers (red dots)
        self._draw_legal_positions(state)

        # Draw placed cards with art
        self._draw_placed_cards(state)

        # Draw confirm button
        self._draw_confirm_button(state)

        # Draw dragging card on top
        if state.dragging_card:
            self._draw_dragging_card(state, mouse_pos)

    def _draw_header(self, state: PlacementState):
        """Draw the header."""
        turn_info = "ходит первым" if state.player == 1 else "ходит вторым"
        remaining = len(state.unplaced_cards)
        header_text = f"Расстановка - Игрок {state.player} ({turn_info}) - Осталось: {remaining}"
        header = self.fonts['large'].render(header_text, True, COLOR_TEXT)
        self.screen.blit(header, (scaled(10), scaled(10)))

    def _draw_board(self, state: PlacementState):
        """Draw the game board."""
        for row in range(BOARD_ROWS):
            for col in range(BOARD_COLS):
                x = BOARD_OFFSET_X + col * CELL_SIZE
                y = BOARD_OFFSET_Y + row * CELL_SIZE

                # Checkerboard pattern
                if (row + col) % 2 == 0:
                    color = COLOR_BOARD_LIGHT
                else:
                    color = COLOR_BOARD_DARK

                pygame.draw.rect(self.screen, color, (x, y, CELL_SIZE, CELL_SIZE))
                pygame.draw.rect(self.screen, COLOR_GRID_LINE, (x, y, CELL_SIZE, CELL_SIZE), 1)

        # Draw center line
        center_y = BOARD_OFFSET_Y + 3 * CELL_SIZE
        pygame.draw.line(
            self.screen,
            (150, 150, 150),
            (BOARD_OFFSET_X, center_y),
            (BOARD_OFFSET_X + BOARD_COLS * CELL_SIZE, center_y),
            3
        )

    def _pos_to_screen(self, pos: int) -> Tuple[int, int]:
        """Convert board position to screen coordinates.

        For Player 2, the board is flipped so their positions appear at the bottom.
        Columns are NOT flipped - must match main game renderer.
        """
        row = pos // BOARD_COLS
        col = pos % BOARD_COLS

        if self._current_player == 2:
            # P2: row 5 at bottom, row 0 at top (no row flip needed)
            # Columns stay the same as game coordinates
            display_row = row
            display_col = col
        else:
            # P1: row 0 at bottom (rows flipped), columns stay same
            display_row = BOARD_ROWS - 1 - row
            display_col = col

        x = BOARD_OFFSET_X + display_col * CELL_SIZE
        y = BOARD_OFFSET_Y + display_row * CELL_SIZE
        return x, y

    def _screen_to_pos(self, screen_x: int, screen_y: int) -> Optional[int]:
        """Convert screen coordinates to board position."""
        if screen_x < BOARD_OFFSET_X or screen_x >= BOARD_OFFSET_X + BOARD_COLS * CELL_SIZE:
            return None
        if screen_y < BOARD_OFFSET_Y or screen_y >= BOARD_OFFSET_Y + BOARD_ROWS * CELL_SIZE:
            return None

        display_col = (screen_x - BOARD_OFFSET_X) // CELL_SIZE
        display_row = (screen_y - BOARD_OFFSET_Y) // CELL_SIZE

        if self._current_player == 2:
            # P2: no flip needed - display coords match game coords
            row = display_row
            col = display_col
        else:
            # P1: flip row back, columns stay same
            row = BOARD_ROWS - 1 - display_row
            col = display_col

        return row * BOARD_COLS + col

    def _draw_unplaced_cards(self, state: PlacementState):
        """Draw unplaced cards on opponent's side of the board."""
        if state.dragging_card:
            cards_to_draw = [c for c in state.unplaced_cards if c != state.dragging_card]
        else:
            cards_to_draw = state.unplaced_cards

        # Get opponent positions to place unplaced cards visually
        opponent_positions = sorted(state.get_opponent_positions())

        for i, card in enumerate(cards_to_draw):
            if i >= len(opponent_positions):
                break

            pos = opponent_positions[i]
            x, y = self._pos_to_screen(pos)

            # Draw card with art
            self._draw_card_with_art(x, y, CELL_SIZE, CELL_SIZE, card)

            rect = pygame.Rect(x, y, CELL_SIZE, CELL_SIZE)
            self.unplaced_card_rects.append((card, rect))

    def _draw_card_with_art(self, x: int, y: int, width: int, height: int, card: Card):
        """Draw a card with its art image."""
        # Card border based on player
        if card.player == 1:
            border_color = COLOR_PLAYER1
        else:
            border_color = COLOR_PLAYER2

        card_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, border_color, card_rect)

        # Name bar dimensions
        name_bar_height = max(12, height // 7)

        # Name bar color (yellow/gold for current player's cards)
        name_bar_color = (180, 160, 60)
        name_text_color = (40, 30, 0)

        # Try to draw card image
        img_filename = get_card_image(card.name)
        if img_filename and img_filename in self.card_images:
            img = self.card_images[img_filename]

            # Calculate image area (above name bar)
            img_area_height = height - name_bar_height - 4
            img_area_width = width - 4

            # Scale image to fit
            img_scaled = pygame.transform.smoothscale(img, (img_area_width, img_area_height))
            self.screen.blit(img_scaled, (x + 2, y + 2))

            # Draw name bar
            name_bar_rect = pygame.Rect(x + 2, y + height - name_bar_height - 2, img_area_width, name_bar_height)
            pygame.draw.rect(self.screen, name_bar_color, name_bar_rect)

            # Card name (shortened)
            max_len = width // 10
            display_name = card.name[:max_len] + '..' if len(card.name) > max_len else card.name
            name_surface = self.fonts['small'].render(display_name, True, name_text_color)
            name_x = name_bar_rect.x + (name_bar_rect.width - name_surface.get_width()) // 2
            name_y = name_bar_rect.y + (name_bar_rect.height - name_surface.get_height()) // 2
            self.screen.blit(name_surface, (name_x, name_y))
        else:
            # Fallback: colored rectangle with name
            pygame.draw.rect(self.screen, (40, 40, 50), card_rect.inflate(-4, -4))
            name_bar_rect = pygame.Rect(x + 2, y + height - name_bar_height - 2, width - 4, name_bar_height)
            pygame.draw.rect(self.screen, name_bar_color, name_bar_rect)
            display_name = card.name[:8] + '..' if len(card.name) > 8 else card.name
            name_surface = self.fonts['small'].render(display_name, True, name_text_color)
            self.screen.blit(name_surface, (x + 4, y + height - name_bar_height))

        # Cost indicator (top-left)
        cost_bg = (200, 170, 50) if card.stats.is_elite else (180, 180, 180)
        cost_rect = pygame.Rect(x + 4, y + 4, scaled(22), scaled(16))
        pygame.draw.rect(self.screen, cost_bg, cost_rect)
        pygame.draw.rect(self.screen, (50, 50, 60), cost_rect, 1)
        cost_text = self.fonts['indicator'].render(str(card.stats.cost), True, (30, 30, 30))
        self.screen.blit(cost_text, (cost_rect.x + 4, cost_rect.y + 1))

        # Flying indicator
        if card.stats.is_flying:
            fly_text = self.fonts['indicator'].render("FLY", True, (100, 200, 255))
            self.screen.blit(fly_text, (x + 4, y + scaled(22)))

        # Unique indicator (crown)
        if card.stats.is_unique:
            unique_text = self.fonts['indicator'].render("U", True, (255, 215, 0))
            self.screen.blit(unique_text, (x + width - scaled(16), y + 4))

    def _draw_legal_positions(self, state: PlacementState):
        """Draw red dots on legal placement positions."""
        legal_positions = state.get_legal_positions()

        for pos in legal_positions:
            if pos in state.placed_cards:
                continue

            x, y = self._pos_to_screen(pos)
            center_x = x + CELL_SIZE // 2
            center_y = y + CELL_SIZE // 2

            # Red dot
            pygame.draw.circle(self.screen, (200, 50, 50), (center_x, center_y), scaled(12))
            pygame.draw.circle(self.screen, (255, 100, 100), (center_x, center_y), scaled(8))

            rect = pygame.Rect(x, y, CELL_SIZE, CELL_SIZE)
            self.legal_position_rects.append((pos, rect))

    def _draw_placed_cards(self, state: PlacementState):
        """Draw placed cards with art on player's side."""
        for pos, card in state.placed_cards.items():
            x, y = self._pos_to_screen(pos)
            self._draw_card_with_art(x, y, CELL_SIZE, CELL_SIZE, card)

            rect = pygame.Rect(x, y, CELL_SIZE, CELL_SIZE)
            self.placed_card_rects.append((pos, rect))

    def _draw_confirm_button(self, state: PlacementState):
        """Draw the confirm button."""
        btn_width = scaled(200)
        btn_height = scaled(50)
        btn_x = WINDOW_WIDTH - btn_width - scaled(20)
        btn_y = WINDOW_HEIGHT - btn_height - scaled(20)

        can_confirm = state.is_complete()
        bg_color = (50, 100, 50) if can_confirm else (60, 60, 60)
        border_color = (80, 150, 80) if can_confirm else (80, 80, 80)

        self.confirm_rect = pygame.Rect(btn_x, btn_y, btn_width, btn_height)
        pygame.draw.rect(self.screen, bg_color, self.confirm_rect)
        pygame.draw.rect(self.screen, border_color, self.confirm_rect, 2)

        text = "Подтвердить" if can_confirm else f"Разместите все ({len(state.unplaced_cards)})"
        text_color = COLOR_TEXT if can_confirm else (120, 120, 120)
        text_surface = self.fonts['medium'].render(text, True, text_color)
        text_x = btn_x + (btn_width - text_surface.get_width()) // 2
        text_y = btn_y + (btn_height - text_surface.get_height()) // 2
        self.screen.blit(text_surface, (text_x, text_y))

    def _draw_dragging_card(self, state: PlacementState, mouse_pos: Tuple[int, int]):
        """Draw the card being dragged."""
        card = state.dragging_card
        if not card:
            return

        x = mouse_pos[0] - state.drag_offset_x
        y = mouse_pos[1] - state.drag_offset_y

        # Draw card with art
        self._draw_card_with_art(x, y, CELL_SIZE, CELL_SIZE, card)

        # Draw highlight border
        pygame.draw.rect(self.screen, (255, 200, 50), (x, y, CELL_SIZE, CELL_SIZE), 3)

    # --- Click/drag detection ---

    def get_unplaced_card_at(self, x: int, y: int) -> Optional[Card]:
        """Get unplaced card at screen position."""
        for card, rect in self.unplaced_card_rects:
            if rect.collidepoint(x, y):
                return card
        return None

    def get_placed_position_at(self, x: int, y: int) -> Optional[int]:
        """Get placed card position at screen position."""
        for pos, rect in self.placed_card_rects:
            if rect.collidepoint(x, y):
                return pos
        return None

    def get_legal_position_at(self, x: int, y: int) -> Optional[int]:
        """Get legal position at screen position."""
        for pos, rect in self.legal_position_rects:
            if rect.collidepoint(x, y):
                return pos
        return None

    def get_drop_position(self, x: int, y: int, state: PlacementState) -> Optional[int]:
        """Get the position where a card would be dropped."""
        pos = self._screen_to_pos(x, y)
        if pos is not None and pos in state.get_legal_positions():
            return pos
        return None

    def is_confirm_clicked(self, x: int, y: int) -> bool:
        """Check if confirm button was clicked."""
        return self.confirm_rect and self.confirm_rect.collidepoint(x, y)

    def get_card_center_offset(self) -> Tuple[int, int]:
        """Get offset to center of card for dragging."""
        return CELL_SIZE // 2, CELL_SIZE // 2

    def get_card_at(self, x: int, y: int, state: PlacementState) -> Optional[Card]:
        """Get any card at screen position (for popup display)."""
        # Check unplaced cards
        card = self.get_unplaced_card_at(x, y)
        if card:
            return card

        # Check placed cards
        pos = self.get_placed_position_at(x, y)
        if pos is not None and pos in state.placed_cards:
            return state.placed_cards[pos]

        return None
