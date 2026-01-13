"""Base renderer with core functionality, scaling, and coordinate conversion."""
import pygame
import os
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, TYPE_CHECKING

from ..constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT,
    BOARD_COLS, BOARD_ROWS, CELL_SIZE, BOARD_OFFSET_X, BOARD_OFFSET_Y,
    CARD_WIDTH, CARD_HEIGHT,
    COLOR_BG, COLOR_BOARD_LIGHT, COLOR_BOARD_DARK, COLOR_GRID_LINE,
    COLOR_PLAYER1, COLOR_PLAYER2, COLOR_SELECTED,
    COLOR_MOVE_HIGHLIGHT, COLOR_ATTACK_HIGHLIGHT,
    COLOR_TEXT, COLOR_TEXT_DARK, COLOR_HP_BAR, COLOR_HP_BAR_BG,
    GamePhase, scaled, UI_SCALE, UILayout
)
from ..ui import FontManager, draw_button_simple, BUTTON_STYLES, ButtonStyle

if TYPE_CHECKING:
    from ..game import Game
    from ..card import Card
    from ..ui_state import UIState


@dataclass
class UIView:
    """UI state snapshot for rendering (decoupled from Game/UIState)."""
    selected_card: Optional['Card'] = None
    valid_moves: List[int] = field(default_factory=list)
    valid_attacks: List[int] = field(default_factory=list)
    attack_mode: bool = False


@dataclass
class PopupConfig:
    """Configuration for a popup banner."""
    popup_id: str
    width: int
    height: int
    bg_color: Tuple[int, int, int, int]  # RGBA
    border_color: Tuple[int, int, int]   # RGB
    title: str = ""
    title_color: Tuple[int, int, int] = (255, 255, 255)
    default_x: Optional[int] = None  # None = center horizontally
    default_y: int = 60


class RendererBase:
    """Base renderer class with core functionality."""

    # Side panel constants - flying zones now in unified side panel
    FLYING_CELL_SIZE = scaled(UILayout.SIDE_PANEL_CARD_SIZE)

    # Base resolution (game renders at this size, then scales)
    BASE_WIDTH = WINDOW_WIDTH
    BASE_HEIGHT = WINDOW_HEIGHT

    def __init__(self, window: pygame.Surface):
        self.window = window  # Actual window surface
        # Render surface at fixed resolution - all drawing goes here
        self.screen = pygame.Surface((self.BASE_WIDTH, self.BASE_HEIGHT))
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self._update_scale()

        # Which player's perspective to render from (1 = P1 at bottom, 2 = P2 at bottom)
        self.viewing_player = 1

        # Initialize FontManager with UI scale
        FontManager.init(scale=UI_SCALE)

        # Get fonts from FontManager (cached)
        self.font_large = FontManager.get('large')
        self.font_medium = FontManager.get('medium')
        self.font_small = FontManager.get('small')
        self.font_card_name = FontManager.get('card_name')
        self.font_popup = FontManager.get('popup')
        self.font_indicator = FontManager.get('indicator')

        # Initialize UI view
        self._ui = UIView()

        # Surfaces for highlighting (with transparency)
        self.move_highlight = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
        self.move_highlight.fill(COLOR_MOVE_HIGHLIGHT)

        self.attack_highlight = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
        self.attack_highlight.fill(COLOR_ATTACK_HIGHLIGHT)

        # Defender highlight (cyan/teal)
        self.defender_highlight = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
        self.defender_highlight.fill((0, 200, 200, 150))

        # Ability target highlight (purple)
        self.ability_highlight = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
        self.ability_highlight.fill((180, 100, 220, 150))

        # Valhalla target highlight (gold)
        self.valhalla_highlight = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
        self.valhalla_highlight.fill((255, 200, 100, 150))

        # Counter shot target highlight (orange)
        self.counter_shot_highlight = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
        self.counter_shot_highlight.fill((255, 140, 50, 150))

        # Highlights for flying zones in side panels (same size as panel cards)
        fly_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
        self.move_highlight_fly = pygame.Surface((fly_size, fly_size), pygame.SRCALPHA)
        self.move_highlight_fly.fill(COLOR_MOVE_HIGHLIGHT)
        self.attack_highlight_fly = pygame.Surface((fly_size, fly_size), pygame.SRCALPHA)
        self.attack_highlight_fly.fill(COLOR_ATTACK_HIGHLIGHT)
        self.defender_highlight_fly = pygame.Surface((fly_size, fly_size), pygame.SRCALPHA)
        self.defender_highlight_fly.fill((0, 200, 200, 150))
        self.ability_highlight_fly = pygame.Surface((fly_size, fly_size), pygame.SRCALPHA)
        self.ability_highlight_fly.fill((180, 100, 220, 150))
        self.valhalla_highlight_fly = pygame.Surface((fly_size, fly_size), pygame.SRCALPHA)
        self.valhalla_highlight_fly.fill((255, 200, 100, 150))
        self.counter_shot_highlight_fly = pygame.Surface((fly_size, fly_size), pygame.SRCALPHA)
        self.counter_shot_highlight_fly.fill((255, 140, 50, 150))

    def _update_scale(self):
        """Update scale factor based on current window size."""
        win_w, win_h = self.window.get_size()
        scale_x = win_w / self.BASE_WIDTH
        scale_y = win_h / self.BASE_HEIGHT
        self.scale = min(scale_x, scale_y)  # Maintain aspect ratio

        # Calculate offset for centering
        scaled_w = int(self.BASE_WIDTH * self.scale)
        scaled_h = int(self.BASE_HEIGHT * self.scale)
        self.offset_x = (win_w - scaled_w) // 2
        self.offset_y = (win_h - scaled_h) // 2

    def handle_resize(self, new_window: pygame.Surface):
        """Handle window resize event."""
        self.window = new_window
        self._update_scale()

    def screen_to_game_coords(self, screen_x: int, screen_y: int) -> Tuple[int, int]:
        """Convert screen coordinates to game coordinates."""
        game_x = int((screen_x - self.offset_x) / self.scale)
        game_y = int((screen_y - self.offset_y) / self.scale)
        return game_x, game_y

    def game_to_window_coords(self, game_x: int, game_y: int) -> Tuple[int, int]:
        """Convert game coordinates to window coordinates for native UI rendering."""
        window_x = int(game_x * self.scale) + self.offset_x
        window_y = int(game_y * self.scale) + self.offset_y
        return window_x, window_y

    def game_to_window_rect(self, rect: pygame.Rect) -> pygame.Rect:
        """Convert a game-space rect to window-space rect."""
        x, y = self.game_to_window_coords(rect.x, rect.y)
        w = int(rect.width * self.scale)
        h = int(rect.height * self.scale)
        return pygame.Rect(x, y, w, h)

    def get_native_font(self, name: str, base_size: Optional[int] = None) -> pygame.font.Font:
        """Get font sized for native window resolution (not pre-scaled).

        This returns a font that renders at the correct size for the current window,
        accounting for the window-to-base-resolution scale factor.
        """
        if base_size is None:
            spec = FontManager.FONT_SPECS.get(name)
            base_size = spec.base_size if spec else 14
        # Scale by window scale (not UI_SCALE, which is for base resolution)
        native_size = int(base_size * self.scale * UI_SCALE)
        return FontManager.get(name, native_size // UI_SCALE if UI_SCALE != 1 else native_size)

    def get_flying_screen_pos(self, pos: int, visual_index: int = -1, centered: bool = False) -> Tuple[int, int]:
        """Get screen coordinates for a flying card position.

        This is the single source of truth for flying card positioning.
        Used by: pos_to_screen, death animations, floating text, panel drawing.

        Args:
            pos: Board position (30-34 for P1, 35-39 for P2)
            visual_index: If >= 0, use this index instead of calculating from board state.
                         Use this during death animations or when slot index is known.
            centered: If True, return center of card. If False, return top-left corner.

        Returns:
            (x, y) screen coordinates
        """
        from ..board import Board

        tab_height = scaled(UILayout.SIDE_PANEL_TAB_HEIGHT)
        spacing = scaled(UILayout.SIDE_PANEL_SPACING)
        card_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
        card_spacing = scaled(UILayout.SIDE_PANEL_CARD_SPACING)
        panel_width = scaled(UILayout.SIDE_PANEL_WIDTH)

        if pos < Board.FLYING_P2_START:
            # P1 flying (positions 30-34)
            slot_idx = pos - Board.FLYING_P1_START
            if self.viewing_player == 2:
                panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
                base_y = scaled(UILayout.SIDE_PANEL_P2_Y)
            else:
                panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
                base_y = scaled(UILayout.SIDE_PANEL_P1_Y)
        else:
            # P2 flying (positions 35-39)
            slot_idx = pos - Board.FLYING_P2_START
            if self.viewing_player == 2:
                panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
                base_y = scaled(UILayout.SIDE_PANEL_P1_Y)
            else:
                panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
                base_y = scaled(UILayout.SIDE_PANEL_P2_Y)

        # Use provided visual_index or slot_idx as fallback
        idx = visual_index if visual_index >= 0 else slot_idx

        content_y = base_y + tab_height + spacing + 5
        x = panel_x + (panel_width - card_size) // 2
        y = content_y + idx * (card_size + card_spacing)

        if centered:
            x += card_size // 2
            y += card_size // 2

        return (x, y)

    def pos_to_screen(self, pos: int, game: 'Game' = None) -> Tuple[int, int]:
        """Convert board position to screen coordinates.

        The board is rendered from the viewing player's perspective:
        - Player 1 view: P1 at bottom (positions 0-14), P2 at top (15-29)
        - Player 2 view: Board is flipped - P2 at bottom, P1 at top

        Flying positions (30-39) are also handled with viewing player perspective.

        Args:
            pos: Board position (0-29 for main board, 30-39 for flying zones)
            game: Optional game state for accurate flying zone visual positioning
        """
        from ..board import Board

        # Handle flying positions (30-39)
        if pos >= Board.FLYING_P1_START:
            # Calculate visual index from current board state
            if pos < Board.FLYING_P2_START:
                slot_idx = pos - Board.FLYING_P1_START
                flying_zone = game.board.flying_p1 if game else None
            else:
                slot_idx = pos - Board.FLYING_P2_START
                flying_zone = game.board.flying_p2 if game else None

            if flying_zone:
                visual_idx = sum(1 for i in range(slot_idx) if flying_zone[i] is not None)
            else:
                visual_idx = slot_idx

            return self.get_flying_screen_pos(pos, visual_index=visual_idx)

        if pos < 0:
            return (0, 0)

        # Get logical row/col from position
        row = pos // BOARD_COLS
        col = pos % BOARD_COLS

        # Flip row for Player 1 (so P1 cards are at bottom)
        # Default rendering: row 0 at top, row 5 at bottom
        # P1 view: P1 (rows 0-2) at bottom -> need to flip rows
        # P2 view: P2 (rows 3-5) at bottom -> no flip needed
        # Note: Only flip rows, not columns - this is a vertical flip, not 180° rotation
        if self.viewing_player == 1:
            row = (BOARD_ROWS - 1) - row

        x = BOARD_OFFSET_X + col * CELL_SIZE
        y = BOARD_OFFSET_Y + row * CELL_SIZE
        return (x, y)

    def screen_to_pos(self, screen_x: int, screen_y: int) -> Optional[int]:
        """Convert screen coordinates to board position, accounting for viewing player.

        Returns None if coordinates are outside the board.
        Flying zone clicks are handled separately.
        """
        # Check if within board bounds
        if screen_x < BOARD_OFFSET_X or screen_x >= BOARD_OFFSET_X + BOARD_COLS * CELL_SIZE:
            return None
        if screen_y < BOARD_OFFSET_Y or screen_y >= BOARD_OFFSET_Y + BOARD_ROWS * CELL_SIZE:
            return None

        # Calculate visual row/col
        col = (screen_x - BOARD_OFFSET_X) // CELL_SIZE
        row = (screen_y - BOARD_OFFSET_Y) // CELL_SIZE

        # Flip row for Player 1 (matches pos_to_screen)
        if self.viewing_player == 1:
            row = (BOARD_ROWS - 1) - row

        return row * BOARD_COLS + col

    def _is_flying_pos(self, pos: int) -> bool:
        """Check if position is a flying zone."""
        return pos >= 30

    def _get_highlight(self, highlight_normal: pygame.Surface, highlight_fly: pygame.Surface, pos: int) -> pygame.Surface:
        """Get appropriate highlight surface based on position type."""
        return highlight_fly if self._is_flying_pos(pos) else highlight_normal

    def finalize_frame(self, native_ui_callback: Optional[callable] = None, skip_flip: bool = False):
        """Scale and display the current frame with optional native resolution UI.

        Args:
            native_ui_callback: Optional function(window, game_to_window_coords) to draw
                               UI elements at native window resolution after the scaled
                               game board is drawn. This allows crisp text rendering.
            skip_flip: If True, don't call pygame.display.flip() - caller will handle it.

        Call this after deck builder or other screens draw to self.screen.
        """
        self.window.fill((0, 0, 0))
        if self.scale != 1.0:
            scaled_w = int(self.BASE_WIDTH * self.scale)
            scaled_h = int(self.BASE_HEIGHT * self.scale)
            scaled_surface = pygame.transform.smoothscale(self.screen, (scaled_w, scaled_h))
            self.window.blit(scaled_surface, (self.offset_x, self.offset_y))
        else:
            self.window.blit(self.screen, (self.offset_x, self.offset_y))

        # Draw native resolution UI if callback provided
        if native_ui_callback:
            native_ui_callback(self.window, self.game_to_window_coords)

        if not skip_flip:
            pygame.display.flip()
