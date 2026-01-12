"""Pygame rendering for the game."""
import pygame
import os
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, TYPE_CHECKING

from .constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT,
    BOARD_COLS, BOARD_ROWS, CELL_SIZE, BOARD_OFFSET_X, BOARD_OFFSET_Y,
    CARD_WIDTH, CARD_HEIGHT,
    COLOR_BG, COLOR_BOARD_LIGHT, COLOR_BOARD_DARK, COLOR_GRID_LINE,
    COLOR_PLAYER1, COLOR_PLAYER2, COLOR_SELECTED,
    COLOR_MOVE_HIGHLIGHT, COLOR_ATTACK_HIGHLIGHT,
    COLOR_TEXT, COLOR_TEXT_DARK, COLOR_HP_BAR, COLOR_HP_BAR_BG,
    GamePhase, scaled, UI_SCALE, UILayout
)
from .game import Game
from .card import Card
from .card_database import get_card_image
from .abilities import get_ability, AbilityType

if TYPE_CHECKING:
    from .ui_state import UIState


@dataclass
class UIView:
    """UI state snapshot for rendering (decoupled from Game/UIState)."""
    selected_card: Optional[Card] = None
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


class Renderer:
    """Handles all Pygame rendering."""

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

        self.font_large = pygame.font.Font(None, scaled(UILayout.FONT_LARGE + 8))
        self.font_medium = pygame.font.Font(None, scaled(UILayout.FONT_MEDIUM + 6))
        self.font_small = pygame.font.Font(None, scaled(UILayout.FONT_SMALL + 6))

        # Try to load a font that supports Cyrillic
        try:
            self.font_large = pygame.font.SysFont('arial', scaled(UILayout.FONT_LARGE))
            self.font_medium = pygame.font.SysFont('arial', scaled(UILayout.FONT_MEDIUM))
            self.font_small = pygame.font.SysFont('arial', scaled(UILayout.FONT_SMALL))
            self.font_card_name = pygame.font.SysFont('arial', scaled(UILayout.FONT_CARD_NAME))
            self.font_popup = pygame.font.SysFont('arial', scaled(UILayout.FONT_POPUP))
            # Dedicated font for HP/Move indicators
            self.font_indicator = pygame.font.SysFont(UILayout.FONT_INDICATOR_NAME, scaled(UILayout.FONT_INDICATOR))
        except:
            self.font_card_name = pygame.font.Font(None, scaled(UILayout.FONT_CARD_NAME + 3))
            self.font_popup = pygame.font.Font(None, scaled(UILayout.FONT_POPUP + 2))
            self.font_indicator = pygame.font.Font(None, scaled(UILayout.FONT_INDICATOR + 2))

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

        # Message log scroll offset (0 = bottom/newest)
        self.log_scroll_offset = 0
        self.log_scrollbar_rect: Optional[pygame.Rect] = None  # Track area for click detection
        self.log_scrollbar_dragging = False
        self.log_max_scroll = 0  # Cached max scroll value

        # Card info panel scroll offset
        self.card_info_scroll = 0
        self.card_info_content_height = 0  # Total content height
        self.card_info_last_card_id = None  # Track which card is displayed

        # Ability button rects (for click detection)
        self.ability_button_rects = []
        self.attack_button_rect = None
        self.prepare_flyer_button_rect = None

        # Card image cache
        self.card_images: Dict[str, pygame.Surface] = {}
        self.card_images_full: Dict[str, pygame.Surface] = {}
        self._load_card_images()

        # Popup state
        self.popup_card: Optional[Card] = None

        # Game over popup state
        self.game_over_popup: bool = False
        self.game_over_winner: int = 0  # 0 = draw, 1 or 2 = winner
        self.game_over_button_rect: Optional[pygame.Rect] = None

        # Floating numbers (damage/heal effects)
        # Each entry: {'x': int, 'y': int, 'text': str, 'color': tuple, 'life': float, 'max_life': float}
        self.floating_texts: List[dict] = []

        # Heal confirmation buttons (for click detection)
        self.heal_confirm_buttons: List[Tuple[str, pygame.Rect]] = []

        # Exchange choice buttons (for click detection)
        self.exchange_buttons: List[Tuple[str, pygame.Rect]] = []

        # Stench choice buttons (for click detection)
        self.stench_choice_buttons: List[Tuple[str, pygame.Rect]] = []

        # Draggable popup state
        self.popup_positions: Dict[str, Tuple[int, int]] = {}  # popup_id -> (x, y)
        self.dragging_popup: Optional[str] = None
        self.drag_offset: Tuple[int, int] = (0, 0)

        # Interaction arrows (attack/heal/ability visualizations)
        # Each entry: {'from_pos': int, 'to_pos': int, 'color': tuple, 'life': float, 'max_life': float}
        self.arrows: List[dict] = []

        # UI view state for rendering (decoupled from Game)
        self._ui: UIView = UIView()

        # Priority phase animation
        self.priority_glow_timer: float = 0.0  # Cycles 0-2π for sine wave

        # Card movement animation
        # Maps card_id -> {'from_x': int, 'from_y': int, 'to_x': int, 'to_y': int, 'progress': float}
        self.card_animations: Dict[int, dict] = {}
        self.card_last_positions: Dict[int, int] = {}  # card_id -> last known board position
        self.CARD_MOVE_DURATION = 0.25  # Animation duration in seconds

        # Dice popup state
        self.dice_popup_open: bool = False
        self.dice_popup_card: Optional[Card] = None  # Card using the instant ability
        self.dice_option_buttons: List[Tuple[str, pygame.Rect]] = []

        # Counter selection popup state
        self.counter_popup_buttons: List[Tuple[int, pygame.Rect]] = []  # (count, rect) pairs
        self.counter_confirm_button: Optional[pygame.Rect] = None

        # Side panel state - separate for each player (can have both open)
        # Each player can have one panel expanded: 'flyers' or 'grave' or None
        self.expanded_panel_p1: Optional[str] = None  # 'flyers', 'grave', or None
        self.expanded_panel_p2: Optional[str] = None  # 'flyers', 'grave', or None
        self.side_panel_tab_rects: Dict[str, pygame.Rect] = {}  # For click detection
        self.side_panel_scroll: Dict[str, int] = {  # Scroll offset for each panel
            'p1_flyers': 0, 'p1_grave': 0, 'p2_flyers': 0, 'p2_grave': 0
        }
        self.counter_cancel_button: Optional[pygame.Rect] = None

        # Main menu button rects: (button_id, rect)
        self.menu_buttons: List[Tuple[str, pygame.Rect]] = []

        # Settings nickname input
        from .text_input import TextInput
        from .settings import get_nickname
        self.settings_nickname_input = TextInput(max_length=20)
        self.settings_nickname_input.value = get_nickname()
        self.settings_nickname_rect: Optional[pygame.Rect] = None

    def is_panel_expanded(self, panel_id: str) -> bool:
        """Check if a specific panel is expanded."""
        if panel_id == 'p1_flyers':
            return self.expanded_panel_p1 == 'flyers'
        elif panel_id == 'p1_grave':
            return self.expanded_panel_p1 == 'grave'
        elif panel_id == 'p2_flyers':
            return self.expanded_panel_p2 == 'flyers'
        elif panel_id == 'p2_grave':
            return self.expanded_panel_p2 == 'grave'
        return False

    def toggle_panel(self, panel_id: str):
        """Toggle a panel. Only one panel per player can be expanded."""
        if panel_id.startswith('p1'):
            panel_type = panel_id.replace('p1_', '')
            if self.expanded_panel_p1 == panel_type:
                self.expanded_panel_p1 = None
            else:
                self.expanded_panel_p1 = panel_type
        else:  # p2
            panel_type = panel_id.replace('p2_', '')
            if self.expanded_panel_p2 == panel_type:
                self.expanded_panel_p2 = None
            else:
                self.expanded_panel_p2 = panel_type

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

    def _load_card_images(self):
        """Load and cache all card images."""
        import sys
        # Find data directory (handle both dev and packaged paths)
        base_paths = [
            os.path.join(os.path.dirname(__file__), '..', 'data', 'cards'),
            os.path.join(os.path.dirname(__file__), 'data', 'cards'),
            'data/cards',
        ]
        # Add PyInstaller bundled path
        if hasattr(sys, '_MEIPASS'):
            base_paths.insert(0, os.path.join(sys._MEIPASS, 'data', 'cards'))

        cards_dir = None
        for path in base_paths:
            if os.path.exists(path):
                cards_dir = path
                break

        if not cards_dir:
            print("Warning: Card images directory not found")
            return

        for filename in os.listdir(cards_dir):
            if filename.endswith('.jpg') or filename.endswith('.png'):
                filepath = os.path.join(cards_dir, filename)
                try:
                    img = pygame.image.load(filepath)
                    img_w, img_h = img.get_size()

                    # Crop art area (top portion of card, excluding frame/name/text)
                    # Berserk cards: skip name at top, get art only
                    art_margin_x = int(img_w * 0.06)  # ~30px on 496w
                    art_top = int(img_h * 0.135)       # ~98px on 700h - skip card name
                    art_bottom = int(img_h * 0.55)    # ~385px on 700h
                    art_width = img_w - 2 * art_margin_x
                    art_height = art_bottom - art_top

                    # Crop the art portion
                    art_crop = img.subsurface((art_margin_x, art_top, art_width, art_height))

                    # Scale cropped art for board display at 2x size for quality
                    # Will be scaled down when drawing, but higher source = better quality
                    name_bar_height = scaled(UILayout.NAME_BAR_HEIGHT)
                    board_size = (CARD_WIDTH * 2, (CARD_HEIGHT - name_bar_height) * 2)
                    board_img = pygame.transform.smoothscale(art_crop, board_size)
                    self.card_images[filename] = board_img

                    # Keep full card at higher resolution for popup
                    # Store at original size or slightly reduced for memory efficiency
                    popup_w = min(img_w, 500)  # Cap at 500px wide
                    popup_h = int(popup_w * img_h / img_w)
                    full_img = pygame.transform.smoothscale(img, (popup_w, popup_h))

                    # Make white corners transparent (only in corner regions)
                    full_img = full_img.convert_alpha()
                    arr = pygame.surfarray.pixels3d(full_img)
                    alpha = pygame.surfarray.pixels_alpha(full_img)

                    # Only check corner regions (about 8% from edges)
                    corner_size = int(popup_w * 0.08)
                    h = popup_h
                    w = popup_w

                    # Create corner masks
                    import numpy as np
                    white_thresh = 240

                    for region in [(0, corner_size, 0, corner_size),           # top-left
                                   (w - corner_size, w, 0, corner_size),       # top-right
                                   (0, corner_size, h - corner_size, h),       # bottom-left
                                   (w - corner_size, w, h - corner_size, h)]:  # bottom-right
                        x1, x2, y1, y2 = region
                        region_rgb = arr[x1:x2, y1:y2]
                        region_alpha = alpha[x1:x2, y1:y2]
                        white_mask = ((region_rgb[:, :, 0] > white_thresh) &
                                      (region_rgb[:, :, 1] > white_thresh) &
                                      (region_rgb[:, :, 2] > white_thresh))
                        region_alpha[white_mask] = 0

                    del arr, alpha

                    self.card_images_full[filename] = full_img
                except Exception as e:
                    print(f"Error loading {filename}: {e}")

    def pos_to_screen(self, pos: int) -> Tuple[int, int]:
        """Convert board position to screen coordinates."""
        from .board import Board

        # Flying positions - use side panel locations
        tab_height = scaled(UILayout.SIDE_PANEL_TAB_HEIGHT)
        spacing = scaled(UILayout.SIDE_PANEL_SPACING)
        card_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
        card_spacing = scaled(UILayout.SIDE_PANEL_CARD_SPACING)
        panel_width = scaled(UILayout.SIDE_PANEL_WIDTH)

        if Board.FLYING_P1_START <= pos < Board.FLYING_P1_START + Board.FLYING_SLOTS:
            idx = pos - Board.FLYING_P1_START
            if self.is_panel_expanded('p1_flyers'):
                # For player 2's view, P1's flyers appear on left side (P2's panel position)
                if self.viewing_player == 2:
                    panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
                    content_y = scaled(UILayout.SIDE_PANEL_P2_Y) + tab_height + spacing
                else:
                    panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
                    content_y = scaled(UILayout.SIDE_PANEL_P1_Y) + tab_height + spacing
                scroll = self.side_panel_scroll.get('p1_flyers', 0)
                x = panel_x + (panel_width - card_size) // 2
                y = content_y + 5 + idx * (card_size + card_spacing) - scroll
                return x, y
            else:
                # Return off-screen position when panel is collapsed
                return -1000, -1000

        elif Board.FLYING_P2_START <= pos < Board.FLYING_P2_START + Board.FLYING_SLOTS:
            idx = pos - Board.FLYING_P2_START
            if self.is_panel_expanded('p2_flyers'):
                # For player 2's view, P2's flyers appear on right side (P1's panel position)
                if self.viewing_player == 2:
                    panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
                    content_y = scaled(UILayout.SIDE_PANEL_P1_Y) + tab_height + spacing
                else:
                    panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
                    content_y = scaled(UILayout.SIDE_PANEL_P2_Y) + tab_height + spacing
                scroll = self.side_panel_scroll.get('p2_flyers', 0)
                x = panel_x + (panel_width - card_size) // 2
                y = content_y + 5 + idx * (card_size + card_spacing) - scroll
                return x, y
            else:
                # Return off-screen position when panel is collapsed
                return -1000, -1000

        col = pos % BOARD_COLS
        row = pos // BOARD_COLS

        # Flip board for perspective (rotate 180 degrees for player 2)
        if self.viewing_player == 2:
            # Player 2: their back row (row 5) at bottom, flip columns too
            screen_row = row
            screen_col = BOARD_COLS - 1 - col
        else:
            # Player 1 (default): their back row (row 0) at bottom
            screen_row = BOARD_ROWS - 1 - row
            screen_col = col

        x = BOARD_OFFSET_X + screen_col * CELL_SIZE
        y = BOARD_OFFSET_Y + screen_row * CELL_SIZE
        return x, y

    def screen_to_pos(self, screen_x: int, screen_y: int) -> Optional[int]:
        """Convert screen coordinates to board position (including flying zones)."""
        from .board import Board

        # Check flying zones in side panels (only when expanded)
        flying_pos = self.get_flying_slot_at_pos(screen_x, screen_y)
        if flying_pos is not None:
            return flying_pos

        # Standard board
        screen_col = (screen_x - BOARD_OFFSET_X) // CELL_SIZE
        screen_row = (screen_y - BOARD_OFFSET_Y) // CELL_SIZE

        if not (0 <= screen_col < BOARD_COLS and 0 <= screen_row < BOARD_ROWS):
            return None

        # Convert screen coordinates back to board position based on perspective
        if self.viewing_player == 2:
            # Player 2: screen row = board row, flip columns back
            row = screen_row
            col = BOARD_COLS - 1 - screen_col
        else:
            # Player 1 (default): flip Y back
            row = BOARD_ROWS - 1 - screen_row
            col = screen_col

        return row * BOARD_COLS + col

    def draw_board(self, game: Game):
        """Draw the game board grid."""
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

    def _is_flying_pos(self, pos: int) -> bool:
        """Check if position is in flying zone."""
        from .board import Board
        return Board.FLYING_P1_START <= pos < Board.FLYING_P1_START + Board.FLYING_SLOTS * 2

    def _get_highlight(self, highlight_normal: pygame.Surface, highlight_fly: pygame.Surface, pos: int) -> pygame.Surface:
        """Get appropriate highlight surface for position."""
        return highlight_fly if self._is_flying_pos(pos) else highlight_normal

    def draw_highlights(self, game: Game):
        """Draw movement, attack, and defender highlights for board only.
        Flying position highlights are drawn in draw_side_panels."""
        # Only show interaction highlights to the acting player
        is_acting = (game.interaction and game.interaction.acting_player == self.viewing_player)

        # Counter shot target mode - highlight valid targets (board only)
        if game.awaiting_counter_shot and game.interaction and is_acting:
            for pos in game.interaction.valid_positions:
                if self._is_flying_pos(pos):
                    continue  # Skip flying - handled in side panels
                x, y = self.pos_to_screen(pos)
                self.screen.blit(self.counter_shot_highlight, (x, y))
            return

        # Movement shot target mode - highlight valid targets (board only)
        if game.awaiting_movement_shot and game.interaction and is_acting:
            for pos in game.interaction.valid_positions:
                if self._is_flying_pos(pos):
                    continue
                x, y = self.pos_to_screen(pos)
                self.screen.blit(self.counter_shot_highlight, (x, y))
            return

        # Valhalla target mode - highlight valid targets (board only)
        if game.awaiting_valhalla and game.interaction and is_acting:
            for pos in game.interaction.valid_positions:
                if self._is_flying_pos(pos):
                    continue
                x, y = self.pos_to_screen(pos)
                self.screen.blit(self.valhalla_highlight, (x, y))
            return

        # Defender choice mode - highlight valid defenders (board only)
        if game.awaiting_defender and game.interaction and is_acting:
            # Highlight original target in red
            target = game.get_card_by_id(game.interaction.target_id)
            if target and target.position is not None and not self._is_flying_pos(target.position):
                x, y = self.pos_to_screen(target.position)
                self.screen.blit(self.attack_highlight, (x, y))

            # Highlight valid defenders in cyan (use valid_positions since positions match card positions)
            for pos in game.interaction.valid_positions:
                if not self._is_flying_pos(pos):
                    x, y = self.pos_to_screen(pos)
                    self.screen.blit(self.defender_highlight, (x, y))
            return

        # Ability targeting mode - highlight valid targets (board only)
        if game.awaiting_ability_target and game.interaction and is_acting:
            for pos in game.interaction.valid_positions:
                if self._is_flying_pos(pos):
                    continue
                x, y = self.pos_to_screen(pos)
                self.screen.blit(self.ability_highlight, (x, y))
            return

        # Movement highlights (board only) - only show if it's our turn
        if game.current_player == self.viewing_player:
            for pos in self._ui.valid_moves:
                if self._is_flying_pos(pos):
                    continue
                x, y = self.pos_to_screen(pos)
                self.screen.blit(self.move_highlight, (x, y))

            # Attack highlights (board only)
            for pos in self._ui.valid_attacks:
                if self._is_flying_pos(pos):
                    continue
                x, y = self.pos_to_screen(pos)
                self.screen.blit(self.attack_highlight, (x, y))

    def draw_card(self, card: Card, x: int, y: int, selected: bool = False, glow_intensity: float = 0.0, game: 'Game' = None, glow_color: tuple = None):
        """Draw a single card with image.

        Args:
            card: Card to draw
            x, y: Position
            selected: Whether card is selected
            glow_intensity: 0-1 for pulsing glow effect (instant abilities, defenders)
            glow_color: RGB tuple for glow color, defaults to golden (255, 220, 100)
        """
        # Card rectangle (slightly smaller than cell)
        card_rect = pygame.Rect(
            x + (CELL_SIZE - CARD_WIDTH) // 2,
            y + (CELL_SIZE - CARD_HEIGHT) // 2,
            CARD_WIDTH,
            CARD_HEIGHT
        )

        # Draw pulsing glow effect if intensity > 0
        if glow_intensity > 0:
            if glow_color is None:
                glow_color = (255, 220, 100)  # Golden glow (default)
            glow_alpha = int(180 * glow_intensity)  # Stronger glow (was 100)
            glow_size = int(10 + 8 * glow_intensity)  # Larger pulsing size (was 6+4)

            # Draw multiple glow layers for soft effect
            for i in range(glow_size, 0, -2):
                glow_rect = card_rect.inflate(i * 2, i * 2)
                glow_surface = pygame.Surface((glow_rect.width, glow_rect.height), pygame.SRCALPHA)
                layer_alpha = int(glow_alpha * (glow_size - i + 1) / glow_size)
                pygame.draw.rect(glow_surface, (*glow_color, layer_alpha), glow_surface.get_rect(), border_radius=3)
                self.screen.blit(glow_surface, glow_rect.topleft)

        # Player border color - based on viewing player perspective
        # Own cards = yellow/gold, enemy cards = blue
        if card.player == self.viewing_player:
            border_color = (180, 150, 50)  # Gold for own cards
        else:
            border_color = (70, 100, 160)  # Blue for enemy cards

        # Draw card background/border
        pygame.draw.rect(self.screen, border_color, card_rect)

        # Name bar dimensions
        name_bar_height = scaled(UILayout.NAME_BAR_HEIGHT)
        name_bar_y = card_rect.y + CARD_HEIGHT - name_bar_height

        # Determine name bar colors based on viewing player (own vs enemy)
        if card.player == self.viewing_player:
            name_bar_color = (180, 160, 60)  # Yellow/gold for own cards
            name_text_color = (40, 30, 0)    # Dark text
        else:
            name_bar_color = (60, 80, 140)   # Blue for enemy
            name_text_color = (220, 230, 255)  # Light text

        # Card name text
        max_name_len = 12
        display_name = card.name[:max_name_len] + '..' if len(card.name) > max_name_len else card.name
        name_surface = self.font_card_name.render(display_name, True, name_text_color)

        # Try to draw card image with name bar
        img_filename = get_card_image(card.name)
        if img_filename and img_filename in self.card_images:
            img_raw = self.card_images[img_filename]
            # Scale to target size (stored at 2x for quality)
            target_h = CARD_HEIGHT - name_bar_height
            img = pygame.transform.smoothscale(img_raw, (CARD_WIDTH, target_h))

            if card.tapped:
                # For tapped cards: greyscale art only, keep name bar and indicators in color
                composite_width = CARD_WIDTH
                composite_height = img.get_height() + name_bar_height
                composite = pygame.Surface((composite_width, composite_height))

                # Convert image to grayscale FIRST (only the art)
                grey_img = img.copy()
                arr = pygame.surfarray.pixels3d(grey_img)
                gray = (arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114).astype('uint8')
                arr[:, :, 0] = gray
                arr[:, :, 1] = gray
                arr[:, :, 2] = gray
                del arr  # Release the surface lock

                # Draw greyscaled image at top
                img_x_offset = (composite_width - grey_img.get_width()) // 2
                composite.blit(grey_img, (img_x_offset, 0))

                # Draw name bar at bottom IN COLOR
                pygame.draw.rect(composite, name_bar_color,
                                 (0, img.get_height(), composite_width, name_bar_height))
                name_x_offset = (composite_width - name_surface.get_width()) // 2
                name_y_offset = img.get_height() + (name_bar_height - name_surface.get_height()) // 2
                composite.blit(name_surface, (name_x_offset, name_y_offset))

                # Stat dimensions for later use
                stat_width = scaled(UILayout.INDICATOR_HP_WIDTH)
                stat_height = scaled(UILayout.INDICATOR_HP_HEIGHT)
                stat_y = img.get_height() - stat_height - scaled(UILayout.INDICATOR_GAP)
                move_x = composite_width - stat_width - scaled(UILayout.INDICATOR_MARGIN)

                # Add indicators IN COLOR (name bar and indicators stay colored)
                # They will rotate with the card but stay colored

                # HP indicator (left side, above name bar)
                hp_bg_color = (25, 85, 25)
                hp_border_color = (50, 130, 50)
                ind_margin = scaled(UILayout.INDICATOR_MARGIN)
                pygame.draw.rect(composite, hp_bg_color, (ind_margin, stat_y, stat_width, stat_height))
                pygame.draw.rect(composite, hp_border_color, (ind_margin, stat_y, stat_width, stat_height), 1)
                hp_text = f"{card.curr_life}/{card.life}"
                hp_surface = self.font_indicator.render(hp_text, True, COLOR_TEXT)
                composite.blit(hp_surface, (ind_margin + (stat_width - hp_surface.get_width()) // 2,
                                           stat_y + (stat_height - hp_surface.get_height()) // 2))

                # Move indicator (right side, above name bar)
                move_bg_color = (120, 40, 40)
                move_border_color = (180, 80, 80)
                pygame.draw.rect(composite, move_bg_color, (move_x, stat_y, stat_width, stat_height))
                pygame.draw.rect(composite, move_border_color, (move_x, stat_y, stat_width, stat_height), 1)
                move_text = f"{card.curr_move}/{card.move}"
                move_surface = self.font_indicator.render(move_text, True, COLOR_TEXT)
                composite.blit(move_surface, (move_x + (stat_width - move_surface.get_width()) // 2,
                                             stat_y + (stat_height - move_surface.get_height()) // 2))

                # Counter/token indicator (fishka) - top-right
                if card.counters > 0:
                    counter_size = scaled(UILayout.COUNTER_SIZE)
                    counter_x = composite_width - counter_size - scaled(UILayout.INDICATOR_GAP)
                    counter_y = scaled(UILayout.INDICATOR_GAP)
                    pygame.draw.circle(composite, (50, 100, 200),
                                       (counter_x + counter_size // 2, counter_y + counter_size // 2),
                                       counter_size // 2)
                    pygame.draw.circle(composite, (100, 150, 255),
                                       (counter_x + counter_size // 2, counter_y + counter_size // 2),
                                       counter_size // 2, 2)
                    counter_text = self.font_small.render(str(card.counters), True, (255, 255, 255))
                    composite.blit(counter_text, (counter_x + (counter_size - counter_text.get_width()) // 2,
                                                  counter_y + (counter_size - counter_text.get_height()) // 2))

                # Formation indicator (stroy) - top-left
                if card.in_formation:
                    badge_size = scaled(UILayout.FORMATION_SIZE)
                    badge_x = scaled(UILayout.INDICATOR_GAP)
                    badge_y = scaled(UILayout.INDICATOR_GAP)
                    pygame.draw.rect(composite, (180, 150, 50), (badge_x, badge_y, badge_size, badge_size))
                    pygame.draw.rect(composite, (255, 220, 100), (badge_x, badge_y, badge_size, badge_size), 1)
                    formation_text = self.font_small.render("С", True, (255, 255, 255))
                    composite.blit(formation_text, (badge_x + (badge_size - formation_text.get_width()) // 2,
                                                    badge_y + (badge_size - formation_text.get_height()) // 2))

                # Armor indicator - bottom-left (above stats)
                total_armor = card.armor_remaining + card.formation_armor_remaining
                if card.armor > 0 or card.formation_armor_remaining > 0:
                    armor_size = scaled(UILayout.ARMOR_SIZE)
                    armor_x = scaled(UILayout.INDICATOR_GAP)
                    armor_y = stat_y - armor_size - scaled(UILayout.INDICATOR_GAP)
                    armor_color = (100, 100, 120) if total_armor > 0 else (60, 60, 70)
                    pygame.draw.rect(composite, armor_color, (armor_x, armor_y, armor_size, armor_size))
                    pygame.draw.rect(composite, (180, 180, 200), (armor_x, armor_y, armor_size, armor_size), 1)
                    armor_text = self.font_small.render(str(total_armor), True, (255, 255, 255))
                    composite.blit(armor_text, (armor_x + (armor_size - armor_text.get_width()) // 2,
                                                armor_y + (armor_size - armor_text.get_height()) // 2))

                # Rotate 90 degrees clockwise
                rotated = pygame.transform.rotate(composite, -90)

                # Center rotated image in card rect
                rot_x = card_rect.x + (card_rect.width - rotated.get_width()) // 2
                rot_y = card_rect.y + (card_rect.height - rotated.get_height()) // 2
                self.screen.blit(rotated, (rot_x, rot_y))
            else:
                # Non-tapped: draw image and name bar normally
                # Set clipping to card area (excluding name bar)
                img_clip = pygame.Rect(card_rect.x, card_rect.y, card_rect.width, card_rect.height - name_bar_height)
                self.screen.set_clip(img_clip)

                # Position image at top of card (no gap)
                img_x = card_rect.x + (card_rect.width - img.get_width()) // 2
                img_y = card_rect.y
                self.screen.blit(img, (img_x, img_y))

                # Remove clipping
                self.screen.set_clip(None)

                # Draw name bar at bottom
                name_bar_rect = pygame.Rect(card_rect.x, name_bar_y, CARD_WIDTH, name_bar_height)
                pygame.draw.rect(self.screen, name_bar_color, name_bar_rect)

                # Draw card name
                name_x = card_rect.x + (CARD_WIDTH - name_surface.get_width()) // 2
                name_y = name_bar_y + (name_bar_height - name_surface.get_height()) // 2
                self.screen.blit(name_surface, (name_x, name_y))

        # Selection border
        if selected:
            pygame.draw.rect(self.screen, COLOR_SELECTED, card_rect, 3)
        else:
            pygame.draw.rect(self.screen, COLOR_TEXT, card_rect, 1)

        # Stats over art - HP (green) and Move (red)
        # Only draw for non-tapped cards (tapped cards have stats in rotated composite)
        if not card.tapped:
            stat_width = scaled(UILayout.INDICATOR_HP_WIDTH)
            stat_height = scaled(UILayout.INDICATOR_HP_HEIGHT)
            ind_margin = scaled(UILayout.INDICATOR_MARGIN)
            ind_gap = scaled(UILayout.INDICATOR_GAP)
            stat_y = name_bar_y - stat_height - ind_gap

            # HP on green background (left)
            hp_bg_rect = pygame.Rect(card_rect.x + ind_margin, stat_y, stat_width, stat_height)
            pygame.draw.rect(self.screen, (25, 85, 25), hp_bg_rect)
            pygame.draw.rect(self.screen, (50, 130, 50), hp_bg_rect, 1)
            hp_text = f"{card.curr_life}/{card.life}"
            hp_surface = self.font_indicator.render(hp_text, True, COLOR_TEXT)
            hp_text_x = hp_bg_rect.x + (stat_width - hp_surface.get_width()) // 2
            hp_text_y = hp_bg_rect.y + (stat_height - hp_surface.get_height()) // 2
            self.screen.blit(hp_surface, (hp_text_x, hp_text_y))

            # Move on red background (right)
            move_bg_rect = pygame.Rect(card_rect.x + CARD_WIDTH - stat_width - ind_margin, stat_y, stat_width, stat_height)
            pygame.draw.rect(self.screen, (120, 40, 40), move_bg_rect)
            pygame.draw.rect(self.screen, (180, 80, 80), move_bg_rect, 1)
            move_text = f"{card.curr_move}/{card.move}"
            move_surface = self.font_indicator.render(move_text, True, COLOR_TEXT)
            move_text_x = move_bg_rect.x + (stat_width - move_surface.get_width()) // 2
            move_text_y = move_bg_rect.y + (stat_height - move_surface.get_height()) // 2
            self.screen.blit(move_surface, (move_text_x, move_text_y))

        # Webbed indicator - draw web pattern overlay
        if card.webbed:
            # Semi-transparent white overlay with "web" pattern
            web_surface = pygame.Surface((card_rect.width, card_rect.height), pygame.SRCALPHA)
            web_surface.fill((255, 255, 255, 80))  # Light white overlay

            # Draw diagonal lines for web effect
            for i in range(-card_rect.height, card_rect.width, 12):
                pygame.draw.line(web_surface, (200, 200, 200, 150),
                                 (i, 0), (i + card_rect.height, card_rect.height), 2)
                pygame.draw.line(web_surface, (200, 200, 200, 150),
                                 (i + card_rect.height, 0), (i, card_rect.height), 2)

            self.screen.blit(web_surface, card_rect.topleft)

            # "WEB" text at top
            web_text = self.font_small.render("ПАУТИНА", True, (255, 255, 255))
            web_bg = pygame.Rect(card_rect.centerx - web_text.get_width() // 2 - 2,
                                 card_rect.y + 5, web_text.get_width() + 4, 14)
            pygame.draw.rect(self.screen, (100, 100, 100, 200), web_bg)
            self.screen.blit(web_text, (web_bg.x + 2, web_bg.y))

        # Counter/token indicator (show when > 0) - only for non-tapped (tapped has it in rotated composite)
        if not card.tapped and card.counters > 0:
            # Draw counter badge in top-right corner
            counter_size = scaled(UILayout.COUNTER_SIZE)
            ind_gap = scaled(UILayout.INDICATOR_GAP)
            counter_x = card_rect.x + CARD_WIDTH - counter_size - ind_gap
            counter_y = card_rect.y + ind_gap
            # Blue circle for counters (фишки)
            pygame.draw.circle(self.screen, (50, 100, 200),
                               (counter_x + counter_size // 2, counter_y + counter_size // 2),
                               counter_size // 2)
            pygame.draw.circle(self.screen, (100, 150, 255),
                               (counter_x + counter_size // 2, counter_y + counter_size // 2),
                               counter_size // 2, 2)
            # Counter number (white text for contrast)
            counter_text = self.font_small.render(str(card.counters), True, (255, 255, 255))
            text_x = counter_x + (counter_size - counter_text.get_width()) // 2
            text_y = counter_y + (counter_size - counter_text.get_height()) // 2
            self.screen.blit(counter_text, (text_x, text_y))

        # Formation indicator (Строй) - only for non-tapped (tapped has it in rotated composite)
        if not card.tapped and card.in_formation:
            # Draw formation badge in top-left corner
            badge_size = scaled(UILayout.FORMATION_SIZE)
            ind_gap = scaled(UILayout.INDICATOR_GAP)
            badge_x = card_rect.x + ind_gap
            badge_y = card_rect.y + ind_gap
            # Yellow/gold shield shape for formation
            pygame.draw.rect(self.screen, (180, 150, 50),
                             (badge_x, badge_y, badge_size, badge_size))
            pygame.draw.rect(self.screen, (255, 220, 100),
                             (badge_x, badge_y, badge_size, badge_size), 1)
            # "С" for Строй
            formation_text = self.font_small.render("С", True, (255, 255, 255))
            text_x = badge_x + (badge_size - formation_text.get_width()) // 2
            text_y = badge_y + (badge_size - formation_text.get_height()) // 2
            self.screen.blit(formation_text, (text_x, text_y))

        # Armor indicator (Броня) - only for non-tapped (tapped has it in rotated composite)
        if not card.tapped:
            total_armor = card.armor_remaining + card.formation_armor_remaining
            if card.armor > 0 or card.formation_armor_remaining > 0:
                # Draw armor badge in bottom-left corner (above HP bar and name bar)
                armor_size = scaled(UILayout.ARMOR_SIZE)
                ind_gap = scaled(UILayout.INDICATOR_GAP)
                stat_height = scaled(UILayout.INDICATOR_HP_HEIGHT)
                armor_x = card_rect.x + ind_gap
                armor_y = card_rect.y + CARD_HEIGHT - name_bar_height - stat_height - armor_size - ind_gap * 2
                # Gray color for armor indicator
                armor_color = (100, 100, 120) if total_armor > 0 else (60, 60, 70)
                border_color = (180, 180, 200)
                pygame.draw.rect(self.screen, armor_color,
                                 (armor_x, armor_y, armor_size, armor_size))
                pygame.draw.rect(self.screen, border_color,
                                 (armor_x, armor_y, armor_size, armor_size), 1)
                # Show total effective armor
                armor_text = self.font_small.render(str(total_armor), True, (255, 255, 255))
                text_x = armor_x + (armor_size - armor_text.get_width()) // 2
                text_y = armor_y + (armor_size - armor_text.get_height()) // 2
                self.screen.blit(armor_text, (text_x, text_y))

    def draw_card_thumbnail(self, card: Card, x: int, y: int, size: int, game: 'Game' = None, is_graveyard: bool = False):
        """Draw a small card thumbnail for side panels (flyers/graveyard).

        Args:
            card: Card to draw
            x, y: Position (top-left corner)
            size: Size of the thumbnail (square)
            game: Game reference for current player detection
            is_graveyard: If True, skip HP bar (dead cards)
        """
        from .card_database import get_card_image

        # Card rectangle
        card_rect = pygame.Rect(x, y, size, size)

        # Player border color - based on viewing player perspective
        # Own cards = yellow/gold, enemy cards = blue
        if card.player == self.viewing_player:
            border_color = (180, 150, 50)  # Gold for own cards
        else:
            border_color = (70, 100, 160)  # Blue for enemy cards

        # Draw card background/border
        pygame.draw.rect(self.screen, border_color, card_rect)

        # Name bar dimensions (proportionally smaller)
        name_bar_height = max(12, size // 7)

        # Name bar color - based on viewing player
        if card.player == self.viewing_player:
            name_bar_color = (180, 160, 60)  # Yellow/gold for own cards
            name_text_color = (40, 30, 0)
        else:
            name_bar_color = (60, 80, 140)  # Blue for enemy
            name_text_color = (220, 230, 255)

        # Try to draw card image
        img_filename = get_card_image(card.name)
        if img_filename and img_filename in self.card_images:
            img = self.card_images[img_filename]

            # Calculate image area (above name bar)
            img_area_height = size - name_bar_height - 4  # 2px border on each side
            img_area_width = size - 4

            # Scale image to fit
            img_scaled = pygame.transform.smoothscale(img, (img_area_width, img_area_height))

            if card.tapped:
                # Convert to grayscale for tapped cards
                arr = pygame.surfarray.pixels3d(img_scaled)
                gray = (arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114).astype('uint8')
                arr[:, :, 0] = gray
                arr[:, :, 1] = gray
                arr[:, :, 2] = gray
                del arr

                # Create composite surface for rotation
                composite = pygame.Surface((img_area_width, img_area_height + name_bar_height), pygame.SRCALPHA)
                composite.blit(img_scaled, (0, 0))

                # Draw HP indicator on composite (for flying cards, include in rotation)
                if not is_graveyard:
                    ind_width = scaled(UILayout.INDICATOR_HP_WIDTH)
                    ind_height = scaled(UILayout.INDICATOR_HP_HEIGHT)
                    ind_margin = scaled(UILayout.INDICATOR_MARGIN)
                    ind_gap = scaled(UILayout.INDICATOR_GAP)
                    hp_y = img_area_height - ind_height - ind_gap
                    hp_bg_rect = pygame.Rect(ind_margin, hp_y, ind_width, ind_height)
                    pygame.draw.rect(composite, (25, 85, 25), hp_bg_rect)
                    pygame.draw.rect(composite, (50, 130, 50), hp_bg_rect, 1)
                    hp_text = f"{card.curr_life}/{card.life}"
                    hp_surface = self.font_indicator.render(hp_text, True, COLOR_TEXT)
                    hp_text_x = hp_bg_rect.x + (ind_width - hp_surface.get_width()) // 2
                    hp_text_y = hp_bg_rect.y + (ind_height - hp_surface.get_height()) // 2
                    composite.blit(hp_surface, (hp_text_x, hp_text_y))

                # Draw name bar on composite
                name_bar_rect_local = pygame.Rect(0, img_area_height, img_area_width, name_bar_height)
                pygame.draw.rect(composite, name_bar_color, name_bar_rect_local)
                max_len = size // 10
                display_name = card.name[:max_len] + '..' if len(card.name) > max_len else card.name
                name_surface = self.font_small.render(display_name, True, name_text_color)
                name_x = (img_area_width - name_surface.get_width()) // 2
                name_y = img_area_height + (name_bar_height - name_surface.get_height()) // 2
                composite.blit(name_surface, (name_x, name_y))

                # Rotate 90 degrees clockwise
                rotated = pygame.transform.rotate(composite, -90)

                # Center rotated image in card rect (inside border)
                rot_x = x + 2 + (img_area_width - rotated.get_width()) // 2
                rot_y = y + 2 + (img_area_height + name_bar_height - rotated.get_height()) // 2
                self.screen.blit(rotated, (rot_x, rot_y))
            else:
                # Non-tapped: draw normally
                self.screen.blit(img_scaled, (x + 2, y + 2))

                # Draw name bar
                name_bar_rect = pygame.Rect(x + 2, y + size - name_bar_height - 2, img_area_width, name_bar_height)
                pygame.draw.rect(self.screen, name_bar_color, name_bar_rect)

                # Card name (shortened)
                max_len = size // 10
                display_name = card.name[:max_len] + '..' if len(card.name) > max_len else card.name
                name_surface = self.font_small.render(display_name, True, name_text_color)
                name_x = name_bar_rect.x + (name_bar_rect.width - name_surface.get_width()) // 2
                name_y = name_bar_rect.y + (name_bar_rect.height - name_surface.get_height()) // 2
                self.screen.blit(name_surface, (name_x, name_y))
        else:
            # Fallback: colored rectangle with name
            pygame.draw.rect(self.screen, (40, 40, 50), card_rect.inflate(-4, -4))
            name_bar_rect = pygame.Rect(x + 2, y + size - name_bar_height - 2, size - 4, name_bar_height)
            pygame.draw.rect(self.screen, name_bar_color, name_bar_rect)
            display_name = card.name[:8] + '..' if len(card.name) > 8 else card.name
            name_surface = self.font_small.render(display_name, True, name_text_color)
            self.screen.blit(name_surface, (x + 4, y + size - name_bar_height))

        # Draw HP indicator (only for non-tapped, non-graveyard - tapped has HP in rotated composite)
        # Flying cards don't need move indicator
        if not is_graveyard and not card.tapped:
            # Use same indicator sizes as board cards
            ind_width = scaled(UILayout.INDICATOR_HP_WIDTH)
            ind_height = scaled(UILayout.INDICATOR_HP_HEIGHT)
            ind_margin = scaled(UILayout.INDICATOR_MARGIN)
            ind_gap = scaled(UILayout.INDICATOR_GAP)
            stat_y = y + size - name_bar_height - ind_height - ind_gap - 2

            # HP on green background (left)
            hp_bg_rect = pygame.Rect(x + ind_margin, stat_y, ind_width, ind_height)
            pygame.draw.rect(self.screen, (25, 85, 25), hp_bg_rect)
            pygame.draw.rect(self.screen, (50, 130, 50), hp_bg_rect, 1)
            hp_text = f"{card.curr_life}/{card.life}"
            hp_surface = self.font_indicator.render(hp_text, True, COLOR_TEXT)
            hp_text_x = hp_bg_rect.x + (ind_width - hp_surface.get_width()) // 2
            hp_text_y = hp_bg_rect.y + (ind_height - hp_surface.get_height()) // 2
            self.screen.blit(hp_surface, (hp_text_x, hp_text_y))


    def draw_flying_zones(self, game: Game):
        """Draw the flying zones for both players."""
        from .board import Board

        # Player 1 flying zone (right side) - blue border
        pygame.draw.rect(self.screen, (30, 40, 50),
                         (self.FLYING_P1_X, self.FLYING_ZONE_Y,
                          self.FLYING_ZONE_WIDTH, self.FLYING_ZONE_HEIGHT))
        pygame.draw.rect(self.screen, COLOR_PLAYER1,
                         (self.FLYING_P1_X, self.FLYING_ZONE_Y,
                          self.FLYING_ZONE_WIDTH, self.FLYING_ZONE_HEIGHT), 2)

        # Label
        label = self.font_small.render("Летающие П1", True, COLOR_PLAYER1)
        self.screen.blit(label, (self.FLYING_P1_X + 5, self.FLYING_ZONE_Y - 18))

        # Draw slots
        for i in range(Board.FLYING_SLOTS):
            slot_y = self.FLYING_ZONE_Y + i * self.FLYING_CELL_SIZE + 5
            pygame.draw.rect(self.screen, (50, 60, 70),
                             (self.FLYING_P1_X + 5, slot_y,
                              self.FLYING_CELL_SIZE, self.FLYING_CELL_SIZE))
            pygame.draw.rect(self.screen, (70, 100, 130),
                             (self.FLYING_P1_X + 5, slot_y,
                              self.FLYING_CELL_SIZE, self.FLYING_CELL_SIZE), 1)

        # Player 2 flying zone (left side) - red border
        pygame.draw.rect(self.screen, (50, 35, 35),
                         (self.FLYING_P2_X, self.FLYING_ZONE_Y,
                          self.FLYING_ZONE_WIDTH, self.FLYING_ZONE_HEIGHT))
        pygame.draw.rect(self.screen, COLOR_PLAYER2,
                         (self.FLYING_P2_X, self.FLYING_ZONE_Y,
                          self.FLYING_ZONE_WIDTH, self.FLYING_ZONE_HEIGHT), 2)

        # Label
        label = self.font_small.render("Летающие П2", True, COLOR_PLAYER2)
        self.screen.blit(label, (self.FLYING_P2_X + 5, self.FLYING_ZONE_Y - 18))

        # Draw slots
        for i in range(Board.FLYING_SLOTS):
            slot_y = self.FLYING_ZONE_Y + i * self.FLYING_CELL_SIZE + 5
            pygame.draw.rect(self.screen, (60, 50, 50),
                             (self.FLYING_P2_X + 5, slot_y,
                              self.FLYING_CELL_SIZE, self.FLYING_CELL_SIZE))
            pygame.draw.rect(self.screen, (130, 80, 80),
                             (self.FLYING_P2_X + 5, slot_y,
                              self.FLYING_CELL_SIZE, self.FLYING_CELL_SIZE), 1)

    def draw_cards(self, game: Game):
        """Draw all cards on the board (including flying zones)."""
        import math
        from .board import Board

        # Calculate glow intensity for priority phase or forced attack (sine wave pulsing)
        glow_intensity = 0.0
        glowing_card_ids = set()  # Golden glow (instant abilities, forced attack)
        defender_card_ids = set()  # Red glow (valid defenders)

        if game.awaiting_priority and game.priority_player == self.viewing_player:
            # Only show priority glow for the player who has priority
            # Higher base intensity (0.6-1.0) for better visibility
            glow_intensity = 0.6 + 0.4 * math.sin(self.priority_glow_timer)
            # Get cards with legal instants for current priority player
            for card, ability in game.get_legal_instants(game.priority_player):
                glowing_card_ids.add(card.id)
        elif game.has_forced_attack and game.current_player == self.viewing_player:
            # Only show forced attack glow for the player whose turn it is
            glow_intensity = 0.6 + 0.4 * math.sin(self.priority_glow_timer)
            # Highlight cards that must attack
            for card_id in game.forced_attackers:
                glowing_card_ids.add(card_id)
        elif game.awaiting_defender and game.interaction:
            # Only show defender glow for the acting player
            if game.interaction.acting_player == self.viewing_player:
                glow_intensity = 0.5 + 0.5 * math.sin(self.priority_glow_timer)
                for card_id in game.interaction.valid_card_ids:
                    defender_card_ids.add(card_id)

        # Draw ground cards
        for pos, card in enumerate(game.board.cells):
            if card is not None:
                base_x, base_y = self.pos_to_screen(pos)
                # Apply movement animation if active
                x, y = self.get_card_draw_position(card.id, base_x, base_y)
                selected = (self._ui.selected_card == card)
                # Determine glow color based on whether it's a defender or instant ability
                if card.id in defender_card_ids:
                    self.draw_card(card, x, y, selected, glow_intensity, game, glow_color=(255, 100, 100))  # Red
                elif card.id in glowing_card_ids:
                    self.draw_card(card, x, y, selected, glow_intensity, game)  # Golden (default)
                else:
                    self.draw_card(card, x, y, selected, 0.0, game)

        # Flying cards are now drawn in draw_side_panels()

    def draw_ui(self, game: Game):
        """Draw UI elements."""
        # Current player indicator
        player_color = COLOR_PLAYER1 if game.current_player == 1 else COLOR_PLAYER2
        player_text = f"Ход: Игрок {game.current_player}"
        text_surface = self.font_large.render(player_text, True, player_color)
        self.screen.blit(text_surface, (20, 20))

        # Turn number
        turn_text = f"Раунд: {game.turn_number}"
        turn_surface = self.font_medium.render(turn_text, True, COLOR_TEXT)
        self.screen.blit(turn_surface, (20, 55))

        # Phase
        phase_names = {
            GamePhase.SETUP: "Расстановка",
            GamePhase.REVEAL: "Открытие",
            GamePhase.MAIN: "Главная фаза",
            GamePhase.GAME_OVER: "Игра окончена"
        }
        phase_text = phase_names.get(game.phase, "")
        phase_surface = self.font_medium.render(phase_text, True, COLOR_TEXT)
        self.screen.blit(phase_surface, (20, 80))

        # End turn button - use the same rect as click detection
        # Color based on viewing player (my color), not current player
        my_color = COLOR_PLAYER1 if self.viewing_player == 1 else COLOR_PLAYER2
        button_rect = self.get_end_turn_button_rect()
        pygame.draw.rect(self.screen, my_color, button_rect)
        pygame.draw.rect(self.screen, COLOR_TEXT, button_rect, 2)

        button_text = "Конец хода"
        button_surface = self.font_medium.render(button_text, True, COLOR_TEXT)
        text_x = button_rect.x + (button_rect.width - button_surface.get_width()) // 2
        text_y = button_rect.y + (button_rect.height - button_surface.get_height()) // 2
        self.screen.blit(button_surface, (text_x, text_y))

        # Check if we're the acting player for interaction popups
        is_acting = (game.interaction and game.interaction.acting_player == self.viewing_player)

        # Counter shot selection prompt (only for acting player)
        if game.awaiting_counter_shot and is_acting:
            self.draw_counter_shot_prompt(game)

        # Movement shot selection prompt (only for acting player)
        if game.awaiting_movement_shot and is_acting:
            self.draw_movement_shot_prompt(game)

        # Heal confirmation prompt (only for acting player)
        if game.awaiting_heal_confirm and is_acting:
            self.draw_heal_confirm_prompt(game)

        # Stench choice prompt (only for acting player)
        if game.awaiting_stench_choice and is_acting:
            self.draw_stench_choice_prompt(game)

        # Exchange choice prompt (only for acting player)
        if game.awaiting_exchange_choice and is_acting:
            self.draw_exchange_prompt(game)

        # Valhalla selection prompt (only for acting player)
        if game.awaiting_valhalla and is_acting:
            self.draw_valhalla_prompt(game)

        # Defender choice prompt (only for acting player)
        if game.awaiting_defender and game.interaction and is_acting:
            self.draw_defender_prompt(game)

        # Selected card info
        if self._ui.selected_card and not game.awaiting_defender:
            self.draw_card_info(self._ui.selected_card, game)

        # Message log
        self.draw_messages(game)

        # Skip button (only show when something can be skipped and we're acting)
        if (game.awaiting_defender or game.awaiting_movement_shot) and is_acting:
            self.draw_skip_button(game)

        # Dice panel (shows pending or last combat dice)
        if (game.awaiting_priority and game.pending_dice_roll) or (game.last_combat and not game.awaiting_defender):
            self.draw_dice_panel(game)

    def draw_counter_shot_prompt(self, game: Game):
        """Draw the counter shot target selection prompt (draggable)."""
        if not game.awaiting_counter_shot or not game.interaction:
            return

        attacker = game.get_card_by_id(game.interaction.actor_id)
        if not attacker:
            return

        config = PopupConfig(
            popup_id='counter_shot',
            width=scaled(UILayout.POPUP_SHOT_WIDTH),
            height=scaled(UILayout.POPUP_SHOT_HEIGHT),
            bg_color=UILayout.POPUP_SHOT_BG,
            border_color=UILayout.POPUP_SHOT_BORDER,
            title=f"ВЫСТРЕЛ: {attacker.name}",
            title_color=(255, 200, 150),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Instructions
        self.draw_popup_text(x, config.width, content_y,
                            "Выберите цель (ОРАНЖЕВЫЕ клетки)",
                            (255, 220, 180), self.font_small)

    def draw_movement_shot_prompt(self, game: Game):
        """Draw the movement shot target selection prompt (draggable)."""
        if not game.awaiting_movement_shot or not game.interaction:
            return

        shooter = game.get_card_by_id(game.interaction.actor_id)
        if not shooter:
            return

        config = PopupConfig(
            popup_id='movement_shot',
            width=scaled(UILayout.POPUP_SHOT_WIDTH + 50),  # Slightly wider for longer text
            height=scaled(UILayout.POPUP_SHOT_HEIGHT + 35),
            bg_color=UILayout.POPUP_SHOT_BG,
            border_color=UILayout.POPUP_SHOT_BORDER,
            title=f"ВЫСТРЕЛ: {shooter.name}",
            title_color=(255, 200, 150),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Instructions
        self.draw_popup_text(x, config.width, content_y,
                            "Рядом с союзником 7+ кристаллов!",
                            (255, 220, 180), self.font_small)
        self.draw_popup_text(x, config.width, content_y + 18,
                            "Выберите цель (или пропустите)",
                            (200, 200, 200), self.font_small)

    def draw_heal_confirm_prompt(self, game: Game):
        """Draw the heal confirmation prompt with clickable buttons (draggable)."""
        if not game.awaiting_heal_confirm or not game.interaction:
            self.heal_confirm_buttons = []
            return

        attacker = game.get_card_by_id(game.interaction.actor_id)
        heal_amount = game.interaction.context.get('heal_amount', 0)
        if not attacker:
            self.heal_confirm_buttons = []
            return

        config = PopupConfig(
            popup_id='heal_confirm',
            width=scaled(UILayout.POPUP_HEAL_WIDTH),
            height=scaled(UILayout.POPUP_HEAL_HEIGHT),
            bg_color=UILayout.POPUP_HEAL_BG,
            border_color=UILayout.POPUP_HEAL_BORDER,
            title=f"ЛЕЧЕНИЕ: {attacker.name}",
            title_color=(180, 255, 200),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Heal amount
        content_y = self.draw_popup_text(x, config.width, content_y,
                                         f"Восстановить {heal_amount} HP?", (255, 255, 255))

        # Buttons
        btn_width, btn_height, gap = scaled(100), scaled(30), scaled(20)
        btn_y = content_y + 3

        yes_rect = self.draw_popup_button(
            x + config.width // 2 - btn_width - gap // 2, btn_y,
            btn_width, btn_height, "Да", (40, 140, 60), (100, 220, 120))

        no_rect = self.draw_popup_button(
            x + config.width // 2 + gap // 2, btn_y,
            btn_width, btn_height, "Нет", (140, 40, 40), (220, 100, 100))

        self.heal_confirm_buttons = [('yes', yes_rect), ('no', no_rect)]

    def draw_stench_choice_prompt(self, game: Game):
        """Draw the stench choice prompt - target must tap or take damage (draggable)."""
        if not game.awaiting_stench_choice or not game.interaction:
            self.stench_choice_buttons = []
            return

        target = game.get_card_by_id(game.interaction.target_id)
        damage = game.interaction.context.get('damage_amount', 2)
        if not target:
            self.stench_choice_buttons = []
            return

        config = PopupConfig(
            popup_id='stench_choice',
            width=scaled(UILayout.POPUP_STENCH_WIDTH),
            height=scaled(UILayout.POPUP_STENCH_HEIGHT),
            bg_color=UILayout.POPUP_STENCH_BG,
            border_color=UILayout.POPUP_STENCH_BORDER,
            title=f"ЗЛОВОНИЕ: {target.name}",
            title_color=(255, 200, 150),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Description
        content_y = self.draw_popup_text(x, config.width, content_y,
                                         f"Закрыться или получить {damage} урона?", (255, 255, 255))

        # Buttons
        btn_width, btn_height, gap = scaled(130), scaled(30), scaled(20)
        btn_y = content_y + 3

        tap_rect = self.draw_popup_button(
            x + config.width // 2 - btn_width - gap // 2, btn_y,
            btn_width, btn_height, "Закрыться", (80, 60, 40), (160, 120, 80))

        damage_rect = self.draw_popup_button(
            x + config.width // 2 + gap // 2, btn_y,
            btn_width, btn_height, f"Получить {damage}", (140, 40, 40), (220, 100, 100))

        self.stench_choice_buttons = [('tap', tap_rect), ('damage', damage_rect)]

    def draw_exchange_prompt(self, game: Game):
        """Draw the exchange choice prompt with clickable buttons (draggable)."""
        if not game.awaiting_exchange_choice or not game.interaction:
            self.exchange_buttons = []
            return

        attacker = game.get_card_by_id(game.interaction.actor_id)
        defender = game.get_card_by_id(game.interaction.target_id)
        if not attacker or not defender:
            self.exchange_buttons = []
            return
        ctx = game.interaction.context
        attacker_advantage = ctx.get('attacker_advantage', True)
        roll_diff = ctx.get('roll_diff', 0)

        # Tier names for display
        tier_names = {0: "слабый", 1: "средний", 2: "сильный"}

        if attacker_advantage:
            # Attacker chooses - roll_diff is 2 or 4
            if roll_diff == 4:
                atk_current_tier = 2  # Strong
                atk_reduced_tier = 1  # Medium
            else:  # roll_diff == 2
                atk_current_tier = 1  # Medium
                atk_reduced_tier = 0  # Weak

            # Full option: deal current tier, receive weak counter
            full_deal = tier_names[atk_current_tier]
            full_receive = tier_names[0]  # Weak counter
            # Reduced option: deal reduced tier, receive nothing
            reduced_deal = tier_names[atk_reduced_tier]
            reduced_receive = "промах"

            title = "ОБМЕН УДАРАМИ"
            full_line1 = f"Нанести {full_deal}"
            full_line2 = f"Получить {full_receive}"
            reduced_line1 = f"Нанести {reduced_deal}"
            reduced_line2 = f"Получить {reduced_receive}"
        else:
            # Defender chooses - roll_diff is -4
            def_current_tier = 1  # Medium counter
            def_reduced_tier = 0  # Weak counter

            # Full option: receive weak attack, counter with current tier
            full_receive = tier_names[0]  # Weak attack
            full_counter = tier_names[def_current_tier]
            # Reduced option: receive nothing, counter with reduced tier
            reduced_receive = "промах"
            reduced_counter = tier_names[def_reduced_tier]

            title = "ОБМЕН УДАРАМИ"
            full_line1 = f"Получить {full_receive}"
            full_line2 = f"Контратака {full_counter}"
            reduced_line1 = f"Получить {reduced_receive}"
            reduced_line2 = f"Контратака {reduced_counter}"

        config = PopupConfig(
            popup_id='exchange',
            width=scaled(UILayout.POPUP_EXCHANGE_WIDTH),
            height=scaled(UILayout.POPUP_EXCHANGE_HEIGHT),
            bg_color=UILayout.POPUP_EXCHANGE_BG,
            border_color=UILayout.POPUP_EXCHANGE_BORDER,
            title=title,
            title_color=(255, 220, 150),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Two-line buttons with damage descriptions
        btn_width, btn_height = scaled(145), scaled(50)
        margin = scaled(10)
        btn_y = content_y + scaled(5)

        # Full button on left (brown = attack with counter)
        full_x = x + margin
        full_rect = pygame.Rect(full_x, btn_y, btn_width, btn_height)
        pygame.draw.rect(self.screen, (140, 80, 40), full_rect)
        pygame.draw.rect(self.screen, (220, 140, 80), full_rect, 2)
        # Two lines of text
        line1_surf = self.font_small.render(full_line1, True, (255, 255, 255))
        line2_surf = self.font_small.render(full_line2, True, (255, 200, 200))
        self.screen.blit(line1_surf, (full_x + (btn_width - line1_surf.get_width()) // 2, btn_y + scaled(8)))
        self.screen.blit(line2_surf, (full_x + (btn_width - line2_surf.get_width()) // 2, btn_y + scaled(28)))

        # Reduce button on right (green = safe attack)
        reduce_x = x + config.width - margin - btn_width
        reduce_rect = pygame.Rect(reduce_x, btn_y, btn_width, btn_height)
        pygame.draw.rect(self.screen, (40, 100, 60), reduce_rect)
        pygame.draw.rect(self.screen, (80, 180, 100), reduce_rect, 2)
        # Two lines of text
        line1_surf = self.font_small.render(reduced_line1, True, (255, 255, 255))
        line2_surf = self.font_small.render(reduced_line2, True, (200, 255, 200))
        self.screen.blit(line1_surf, (reduce_x + (btn_width - line1_surf.get_width()) // 2, btn_y + scaled(8)))
        self.screen.blit(line2_surf, (reduce_x + (btn_width - line2_surf.get_width()) // 2, btn_y + scaled(28)))

        self.exchange_buttons = [('full', full_rect), ('reduce', reduce_rect)]

    def draw_valhalla_prompt(self, game: Game):
        """Draw the Valhalla target selection prompt (draggable)."""
        if not game.interaction:
            return

        from .abilities import get_ability
        dead_card = game.get_card_by_id(game.interaction.actor_id)
        ability_id = game.interaction.context.get('ability_id')
        ability = get_ability(ability_id) if ability_id else None
        if not dead_card or not ability:
            return

        config = PopupConfig(
            popup_id='valhalla',
            width=scaled(UILayout.POPUP_VALHALLA_WIDTH),
            height=scaled(UILayout.POPUP_VALHALLA_HEIGHT),
            bg_color=UILayout.POPUP_VALHALLA_BG,
            border_color=UILayout.POPUP_VALHALLA_BORDER,
            title=f"ВАЛЬХАЛЛА: {dead_card.name}",
            title_color=(255, 220, 150),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Effect description
        content_y = self.draw_popup_text(x, config.width, content_y, ability.description, (255, 255, 255))

        # Instructions
        self.draw_popup_text(x, config.width, content_y,
                            "Выберите существо (ЗОЛОТЫЕ клетки)",
                            (255, 230, 180), self.font_small)

    def draw_defender_prompt(self, game: Game):
        """Draw the defender choice prompt banner (draggable)."""
        interaction = game.interaction
        if not interaction:
            return
        attacker = game.get_card_by_id(interaction.actor_id)
        target = game.get_card_by_id(interaction.target_id)
        if not attacker or not target:
            return
        defending_player = target.player

        config = PopupConfig(
            popup_id='defender',
            width=scaled(UILayout.POPUP_DEFENDER_WIDTH),
            height=scaled(UILayout.POPUP_DEFENDER_HEIGHT),
            bg_color=UILayout.POPUP_DEFENDER_BG,
            border_color=UILayout.POPUP_DEFENDER_BORDER,
            title=f"ИГРОК {defending_player}: ВЫБОР ЗАЩИТНИКА",
        )

        x, y, content_y = self.draw_popup_base(config)

        # Attack info
        info = f"{attacker.name} атакует {target.name}"
        content_y = self.draw_popup_text(x, config.width, content_y, info, (255, 255, 255))

        # Instructions
        self.draw_popup_text(x, config.width, content_y + 5,
                            "Выберите защитника (или пропустите)",
                            (200, 255, 255), self.font_small)

    def draw_card_info(self, card: Card, game: Game):
        """Draw detailed info about selected card with scrolling."""
        # Reset scroll when card changes
        if card.id != self.card_info_last_card_id:
            self.card_info_scroll = 0
            self.card_info_last_card_id = card.id

        panel_x = UILayout.get_card_info_x()
        panel_y = scaled(UILayout.CARD_INFO_Y)
        panel_width = scaled(UILayout.CARD_INFO_WIDTH)
        panel_height = scaled(UILayout.CARD_INFO_HEIGHT)

        # Panel background
        pygame.draw.rect(self.screen, (40, 40, 50),
                         (panel_x, panel_y, panel_width, panel_height))
        pygame.draw.rect(self.screen, COLOR_TEXT,
                         (panel_x, panel_y, panel_width, panel_height), 1)

        # Set clipping rect for scrollable content
        clip_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)
        self.screen.set_clip(clip_rect)

        # Apply scroll offset
        scroll_y = -self.card_info_scroll

        # Card name
        padding = scaled(UILayout.CARD_INFO_PADDING)
        name_surface = self.font_large.render(card.name, True, COLOR_TEXT)
        self.screen.blit(name_surface, (panel_x + padding, panel_y + padding + scroll_y))

        # Stats
        y_offset = 75 + scroll_y
        line_spacing = scaled(UILayout.CARD_INFO_LINE_SPACING)
        status_spacing = scaled(UILayout.CARD_INFO_STATUS_SPACING)
        effective_atk = card.get_effective_attack()

        # Build attack string with positional modifiers
        atk_parts = []
        for tier in range(3):
            base = effective_atk[tier]
            pos_mod = game._get_positional_damage_modifier(card, tier)
            if pos_mod > 0:
                atk_parts.append(f"{base}(+{pos_mod})")
            elif pos_mod < 0:
                atk_parts.append(f"{base}({pos_mod})")
            else:
                atk_parts.append(str(base))
        atk_str = "-".join(atk_parts)

        # Show dice bonuses (ОвА/ОвЗ)
        atk_dice = game._get_attack_dice_bonus(card)
        def_dice = game._get_defense_dice_bonus(card)
        dice_parts = []
        if atk_dice > 0:
            dice_parts.append(f"+{atk_dice}ОвА")
        if def_dice > 0:
            dice_parts.append(f"+{def_dice}ОвЗ")
        if dice_parts:
            atk_str += " " + " ".join(dice_parts)

        # Only show HP - attack and movement are shown on card indicators
        hp_surface = self.font_small.render(f"HP: {card.curr_life}/{card.life}", True, COLOR_TEXT)
        self.screen.blit(hp_surface, (panel_x + padding, panel_y + y_offset))
        y_offset += line_spacing

        if card.tapped:
            tapped = self.font_small.render("(Закрыт)", True, (180, 100, 100))
            self.screen.blit(tapped, (panel_x + padding, panel_y + y_offset))
            y_offset += line_spacing

        # Active statuses (temporary buffs)
        statuses = []
        if card.temp_ranged_bonus > 0:
            statuses.append(f"+{card.temp_ranged_bonus} выстрел")
        if card.has_direct:
            statuses.append("прямой удар")
        if card.temp_attack_bonus > 0:
            statuses.append(f"+{card.temp_attack_bonus} атака")

        # Calculate total dice bonuses (from abilities + temp)
        total_ova = card.temp_dice_bonus
        total_ovz = 0
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability:
                total_ova += ability.dice_bonus_attack
                total_ovz += ability.dice_bonus_defense

        # Show unified dice bonuses
        if total_ova > 0:
            statuses.append(f"ОвА +{total_ova}")
        if total_ovz > 0:
            statuses.append(f"ОвЗ +{total_ovz}")

        # Defender buff (lasts until end of owner's next turn)
        if card.defender_buff_attack > 0:
            statuses.append(f"+{card.defender_buff_attack} защ.бафф")
        if card.defender_buff_dice > 0:
            statuses.append(f"+{card.defender_buff_dice} защ.бросок")
        # Positional damage reduction (center column - weak attacks only)
        col = game._get_card_column(card)
        if card.has_ability("center_column_defense") and col == 2:
            statuses.append("-1 от слабых")
        # Counter/token display
        if card.counters > 0:
            statuses.append(f"фишек: {card.counters}")

        # Armor display
        if card.armor > 0:
            statuses.append(f"броня: {card.armor_remaining}/{card.armor}")

        # Formation status and bonuses
        if card.in_formation:
            formation_def = 0
            # Calculate formation defense bonus
            for ability_id in card.stats.ability_ids:
                ability = get_ability(ability_id)
                if ability and ability.is_formation and ability.formation_dice_bonus > 0:
                    if ability.requires_elite_ally and game._has_elite_ally_in_formation(card):
                        formation_def += ability.formation_dice_bonus
                    elif ability.requires_common_ally and game._has_common_ally_in_formation(card):
                        formation_def += ability.formation_dice_bonus
                    elif not ability.requires_elite_ally and not ability.requires_common_ally:
                        formation_def += ability.formation_dice_bonus

            stroy_parts = ["В СТРОЮ"]
            if card.formation_armor_remaining > 0:
                stroy_parts.append(f"броня: {card.formation_armor_remaining}")
            if formation_def > 0:
                stroy_parts.append(f"ОвЗ +{formation_def}")
            statuses.append(" ".join(stroy_parts))

        # Prepared flyer attack
        if card.can_attack_flyer:
            statuses.append("ГОТОВ К АТАКЕ ЛЕТАЮЩИХ")

        # Pull status_text from abilities (passive/triggered only)
        # Skip abilities that only provide dice bonuses (already shown unified above)
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.status_text:
                # Skip if ability only provides dice bonus (already displayed)
                if ability.dice_bonus_attack > 0 or ability.dice_bonus_defense > 0:
                    # Check if ability has other effects beyond dice bonus
                    has_other_effects = (
                        ability.damage_reduction > 0 or
                        ability.heal_amount > 0 or
                        ability.damage_amount > 0 or
                        ability.is_formation or
                        ability.trigger is not None
                    )
                    if not has_other_effects:
                        continue  # Skip - dice bonus already shown
                statuses.append(ability.status_text)

        if statuses:
            # Wrap status text to fit panel width
            max_width = panel_width - padding * 2
            current_line = []
            lines = []
            for status in statuses:
                test_line = ", ".join(current_line + [status])
                test_surface = self.font_small.render(f"[{test_line}]", True, (100, 200, 100))
                if test_surface.get_width() > max_width and current_line:
                    lines.append(current_line)
                    current_line = [status]
                else:
                    current_line.append(status)
            if current_line:
                lines.append(current_line)

            for line in lines:
                line_text = ", ".join(line)
                status_surface = self.font_small.render(f"[{line_text}]", True, (100, 200, 100))
                self.screen.blit(status_surface, (panel_x + padding, panel_y + y_offset))
                y_offset += status_spacing

        # Attack button (before abilities) - always shown to display attack power
        y_offset += 8
        self.attack_button_rect = None

        btn_height = scaled(UILayout.CARD_INFO_BUTTON_HEIGHT)
        btn_spacing = scaled(UILayout.CARD_INFO_BUTTON_SPACING)

        btn_rect = pygame.Rect(panel_x + padding, panel_y + y_offset, panel_width - padding * 2, btn_height)

        # Check if this is current player's usable card
        is_own_card = card.player == game.current_player
        can_use = is_own_card and card.can_act

        # Check if in attack mode or has valid attacks
        has_attacks = len(self._ui.valid_attacks) > 0 if self._ui.selected_card == card else False
        in_attack_mode = self._ui.attack_mode and self._ui.selected_card == card

        if in_attack_mode:
            btn_color = (150, 60, 60)  # Red - attack mode active
            text_color = COLOR_TEXT
        elif can_use and (has_attacks or not card.tapped):
            btn_color = (120, 50, 50)  # Dark red - clickable
            text_color = COLOR_TEXT
        else:
            btn_color = (50, 50, 55)  # Dark - can't attack (enemy or tapped)
            text_color = (120, 120, 120)

        pygame.draw.rect(self.screen, btn_color, btn_rect)
        pygame.draw.rect(self.screen, (160, 80, 80), btn_rect, 1)

        # Attack text with damage values (including all bonuses) - centered
        atk = game.get_display_attack(card)
        btn_text = f"Атака {atk[0]}-{atk[1]}-{atk[2]}"
        btn_surface = self.font_small.render(btn_text, True, text_color)
        text_x = btn_rect.x + (btn_rect.width - btn_surface.get_width()) // 2
        text_y = btn_rect.y + (btn_rect.height - btn_surface.get_height()) // 2
        self.screen.blit(btn_surface, (text_x, text_y))

        # Only make clickable for own untapped cards
        if can_use and not card.tapped:
            self.attack_button_rect = btn_rect

        y_offset += btn_spacing

        # Ability buttons
        self.ability_button_rects = []
        usable_abilities = game.get_usable_abilities(card)

        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if not ability or ability.ability_type != AbilityType.ACTIVE:
                continue

            btn_rect = pygame.Rect(panel_x + padding, panel_y + y_offset, panel_width - padding * 2, btn_height)

            # Check if usable
            is_usable = ability in usable_abilities
            on_cooldown = ability_id in card.ability_cooldowns

            if is_usable:
                btn_color = (80, 60, 120)  # Purple - clickable
                text_color = COLOR_TEXT
            elif on_cooldown:
                btn_color = (50, 50, 55)  # Dark - on cooldown
                text_color = (120, 120, 120)
            else:
                btn_color = (50, 50, 55)  # Dark - can't use
                text_color = (120, 120, 120)

            pygame.draw.rect(self.screen, btn_color, btn_rect)
            pygame.draw.rect(self.screen, (100, 80, 140), btn_rect, 1)

            # Ability text - dynamic with current values
            btn_text = game.get_ability_display_text(card, ability)
            if on_cooldown:
                cd = card.ability_cooldowns[ability_id]
                btn_text += f" ({cd})"

            btn_surface = self.font_small.render(btn_text, True, text_color)
            text_x = btn_rect.x + (btn_rect.width - btn_surface.get_width()) // 2
            text_y = btn_rect.y + (btn_rect.height - btn_surface.get_height()) // 2
            self.screen.blit(btn_surface, (text_x, text_y))

            if is_usable:
                self.ability_button_rects.append((btn_rect, ability_id))

            y_offset += btn_spacing

        # Prepare Flyer Attack button (when opponent has only flyers)
        self.prepare_flyer_button_rect = None
        if game.can_prepare_flyer_attack(card):
            btn_rect = pygame.Rect(panel_x + padding, panel_y + y_offset, panel_width - padding * 2, btn_height)
            btn_color = (120, 80, 40)  # Orange-brown - special action
            pygame.draw.rect(self.screen, btn_color, btn_rect)
            pygame.draw.rect(self.screen, (180, 120, 60), btn_rect, 1)

            btn_text = "Подготовить атаку летающих"
            btn_surface = self.font_small.render(btn_text, True, COLOR_TEXT)
            text_x = btn_rect.x + (btn_rect.width - btn_surface.get_width()) // 2
            text_y = btn_rect.y + (btn_rect.height - btn_surface.get_height()) // 2
            self.screen.blit(btn_surface, (text_x, text_y))

            self.prepare_flyer_button_rect = btn_rect
            y_offset += btn_spacing

        # Card description (at the end)
        if card.stats.description:
            y_offset += padding
            desc_lines = self._wrap_text(card.stats.description, panel_width - padding * 2)
            for line in desc_lines:
                desc_surface = self.font_small.render(line, True, (180, 180, 200))
                self.screen.blit(desc_surface, (panel_x + padding, panel_y + y_offset))
                y_offset += status_spacing - 4

        # Store total content height for scrolling (without scroll offset)
        self.card_info_content_height = y_offset - scroll_y

        # Reset clip
        self.screen.set_clip(None)

        # Draw scroll indicators if content overflows
        if self.card_info_content_height > panel_height:
            # Draw scroll hint at bottom
            if self.card_info_scroll < self.card_info_content_height - panel_height:
                hint = self.font_small.render("▼ прокрутка ▼", True, (150, 150, 150))
                hint_x = panel_x + (panel_width - hint.get_width()) // 2
                self.screen.blit(hint, (hint_x, panel_y + panel_height - 18))
            if self.card_info_scroll > 0:
                hint_up = self.font_small.render("▲ прокрутка ▲", True, (150, 150, 150))
                hint_x = panel_x + (panel_width - hint_up.get_width()) // 2
                self.screen.blit(hint_up, (hint_x, panel_y + 2))

    def scroll_card_info(self, direction: int):
        """Scroll the card info panel. direction: -1 = up, 1 = down."""
        self.card_info_scroll += direction * 20
        panel_height = scaled(UILayout.CARD_INFO_HEIGHT)
        max_scroll = max(0, self.card_info_content_height - panel_height)
        self.card_info_scroll = max(0, min(self.card_info_scroll, max_scroll))

    def _wrap_text(self, text: str, max_width: int) -> list:
        """Wrap text to fit within max_width pixels."""
        words = text.split(' ')
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            test_surface = self.font_small.render(test_line, True, (255, 255, 255))
            if test_surface.get_width() <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        return lines if lines else [text]

    def draw_messages(self, game: Game):
        """Draw scrollable message log on the right side."""
        # Position: right side, below card info
        panel_x = UILayout.get_combat_log_x()
        panel_y = scaled(UILayout.COMBAT_LOG_Y)
        panel_width = scaled(UILayout.COMBAT_LOG_WIDTH)
        panel_height = scaled(UILayout.COMBAT_LOG_HEIGHT)
        line_height = scaled(UILayout.COMBAT_LOG_LINE_HEIGHT)
        max_text_width = panel_width - scaled(25)  # Room for scrollbar

        # Panel background
        pygame.draw.rect(self.screen, (25, 25, 30),
                         (panel_x, panel_y, panel_width, panel_height))
        pygame.draw.rect(self.screen, (60, 60, 70),
                         (panel_x, panel_y, panel_width, panel_height), 1)

        # Title
        title = "Журнал боя"
        title_surface = self.font_small.render(title, True, (150, 150, 160))
        self.screen.blit(title_surface, (panel_x + 5, panel_y + 3))

        # Wrap all messages into display lines
        display_lines = []  # (text, message_index)
        for i, msg in enumerate(game.messages):
            wrapped = self._wrap_text(msg, max_text_width)
            for line in wrapped:
                display_lines.append((line, i))

        # Calculate visible lines (accounting for title gap + bottom margin)
        visible_lines = (panel_height - 50) // line_height
        total_lines = len(display_lines)
        max_scroll = max(0, total_lines - visible_lines)
        self.log_scroll_offset = max(0, min(self.log_scroll_offset, max_scroll))

        # Get lines to display (with scroll)
        start_idx = max(0, total_lines - visible_lines - self.log_scroll_offset)
        end_idx = total_lines - self.log_scroll_offset

        # Create clipping rect for messages (with extra space after title)
        title_gap = 28  # Space between title and messages
        clip_rect = pygame.Rect(panel_x + 2, panel_y + title_gap, panel_width - 4, panel_height - title_gap - 22)
        self.screen.set_clip(clip_rect)

        y_offset = title_gap
        for i in range(start_idx, end_idx):
            if i < 0 or i >= total_lines:
                continue
            line_text, msg_idx = display_lines[i]

            # Consistent color for all messages (no fading)
            color = (220, 220, 220)

            msg_surface = self.font_small.render(line_text, True, color)
            self.screen.blit(msg_surface, (panel_x + 5, panel_y + y_offset))
            y_offset += line_height

        # Remove clipping
        self.screen.set_clip(None)

        # Draw vertical scrollbar if there are more lines
        if total_lines > visible_lines:
            scrollbar_x = panel_x + panel_width - 12
            scrollbar_y = panel_y + 22
            scrollbar_height = panel_height - 44
            scrollbar_width = 8

            # Store scrollbar info for mouse interaction
            self.log_scrollbar_rect = pygame.Rect(scrollbar_x, scrollbar_y, scrollbar_width, scrollbar_height)
            self.log_max_scroll = max_scroll

            # Scrollbar track (background)
            pygame.draw.rect(self.screen, (40, 40, 50),
                           (scrollbar_x, scrollbar_y, scrollbar_width, scrollbar_height))

            # Calculate thumb size and position
            thumb_ratio = visible_lines / total_lines
            thumb_height = max(20, int(scrollbar_height * thumb_ratio))

            # Thumb position (inverted because scroll_offset 0 = bottom)
            scroll_ratio = self.log_scroll_offset / max_scroll if max_scroll > 0 else 0
            thumb_y = scrollbar_y + int((scrollbar_height - thumb_height) * (1 - scroll_ratio))

            # Scrollbar thumb (highlight if dragging)
            thumb_color = (130, 130, 150) if self.log_scrollbar_dragging else (100, 100, 120)
            pygame.draw.rect(self.screen, thumb_color,
                           (scrollbar_x, thumb_y, scrollbar_width, thumb_height))
            pygame.draw.rect(self.screen, (140, 140, 160),
                           (scrollbar_x, thumb_y, scrollbar_width, thumb_height), 1)
        else:
            self.log_scrollbar_rect = None
            self.log_max_scroll = 0

    def scroll_log(self, direction: int, game: Game):
        """Scroll the message log. direction: -1=up (older), 1=down (newer)."""
        # Count total wrapped lines
        panel_width = UILayout.COMBAT_LOG_WIDTH
        max_text_width = panel_width - 15
        total_lines = 0
        for msg in game.messages:
            total_lines += len(self._wrap_text(msg, max_text_width))

        panel_height = UILayout.COMBAT_LOG_HEIGHT
        line_height = UILayout.COMBAT_LOG_LINE_HEIGHT
        visible_lines = (panel_height - 44) // line_height
        max_scroll = max(0, total_lines - visible_lines)

        self.log_scroll_offset -= direction
        self.log_scroll_offset = max(0, min(self.log_scroll_offset, max_scroll))

    def start_log_scrollbar_drag(self, mouse_x: int, mouse_y: int) -> bool:
        """Start dragging the log scrollbar. Returns True if drag started."""
        if self.log_scrollbar_rect and self.log_scrollbar_rect.collidepoint(mouse_x, mouse_y):
            self.log_scrollbar_dragging = True
            self._update_log_scroll_from_mouse(mouse_y)
            return True
        return False

    def drag_log_scrollbar(self, mouse_y: int):
        """Update log scroll position while dragging."""
        if self.log_scrollbar_dragging:
            self._update_log_scroll_from_mouse(mouse_y)

    def stop_log_scrollbar_drag(self):
        """Stop dragging the log scrollbar."""
        self.log_scrollbar_dragging = False

    def _update_log_scroll_from_mouse(self, mouse_y: int):
        """Update log scroll offset based on mouse Y position."""
        if not self.log_scrollbar_rect or self.log_max_scroll <= 0:
            return

        # Calculate relative position within scrollbar track
        rel_y = mouse_y - self.log_scrollbar_rect.y
        ratio = rel_y / self.log_scrollbar_rect.height
        ratio = max(0, min(1, ratio))

        # Invert ratio (top = max scroll, bottom = 0)
        self.log_scroll_offset = int((1 - ratio) * self.log_max_scroll)
        self.log_scroll_offset = max(0, min(self.log_scroll_offset, self.log_max_scroll))

    def draw_dice_panel(self, game: Game):
        """Draw dice panel - shows pending or last combat dice in one row."""
        panel_x = WINDOW_WIDTH // 2 - scaled(200)
        panel_y = scaled(10)
        panel_width = scaled(400)
        panel_height = scaled(35)

        # Different color during priority phase
        if game.awaiting_priority and game.pending_dice_roll:
            bg_color = (50, 40, 60)  # Purple tint during priority
            border_color = (100, 80, 140)
        else:
            bg_color = (50, 30, 30)
            border_color = COLOR_TEXT

        pygame.draw.rect(self.screen, bg_color,
                         (panel_x, panel_y, panel_width, panel_height))
        pygame.draw.rect(self.screen, border_color,
                         (panel_x, panel_y, panel_width, panel_height), 2)

        # Show pending dice during priority phase (with real-time modifications)
        if game.awaiting_priority and game.pending_dice_roll:
            dice = game.pending_dice_roll
            attacker = game.board.get_card_by_id(dice.attacker_id)
            if not attacker:
                return
            is_single_roll = dice.type in ('ranged', 'magic')
            defender = game.board.get_card_by_id(dice.defender_id) if dice.defender_id and not is_single_roll else None
            target = game.board.get_card_by_id(dice.target_id) if dice.target_id and is_single_roll else None

            # Get base rolls, bonuses (ОвА/ОвЗ), and instant modifiers
            atk_roll = dice.atk_roll
            atk_bonus = dice.atk_bonus
            atk_mod = dice.atk_modifier

            # Calculate totals: base + bonus + modifier
            atk_base_total = atk_roll + atk_bonus  # Before instant modifier
            atk_final = atk_base_total + atk_mod   # After instant modifier

            atk_name = attacker.name[:8]

            # Format: "Name[roll+bonus=total]" or "Name[roll+bonus→new]" if modified
            if atk_bonus > 0:
                if atk_mod != 0:
                    atk_dice = f"[{atk_roll}+{atk_bonus}→{atk_final}]"
                else:
                    atk_dice = f"[{atk_roll}+{atk_bonus}={atk_base_total}]"
            else:
                if atk_mod != 0:
                    atk_dice = f"[{atk_roll}→{atk_final}]"
                else:
                    atk_dice = f"[{atk_roll}]"

            # Draw label
            label = self.font_small.render("Кубики: ", True, (200, 180, 220))
            x = panel_x + 10
            self.screen.blit(label, (x, panel_y + 8))
            x += label.get_width()

            # Attacker part
            atk_color = COLOR_PLAYER1 if attacker.player == 1 else COLOR_PLAYER2
            if atk_mod != 0:
                atk_color = (100, 255, 100) if atk_mod > 0 else (255, 100, 100)
            atk_surface = self.font_small.render(f"{atk_name}{atk_dice}", True, atk_color)
            self.screen.blit(atk_surface, (x, panel_y + 8))
            x += atk_surface.get_width()

            if is_single_roll and target:
                # For ranged/magic attacks, show " -> Target" instead of "vs defender[roll]"
                arrow_surface = self.font_small.render(" → ", True, COLOR_TEXT)
                self.screen.blit(arrow_surface, (x, panel_y + 8))
                x += arrow_surface.get_width()

                target_name = target.name[:8]
                target_color = COLOR_PLAYER1 if target.player == 1 else COLOR_PLAYER2
                target_surface = self.font_small.render(target_name, True, target_color)
                self.screen.blit(target_surface, (x, panel_y + 8))
            elif defender:
                # For combat, show "vs defender[roll]"
                def_roll = dice.def_roll
                def_bonus = dice.def_bonus
                def_mod = dice.def_modifier
                def_base_total = def_roll + def_bonus
                def_final = def_base_total + def_mod
                def_name = defender.name[:8]

                if def_bonus > 0:
                    if def_mod != 0:
                        def_dice = f"[{def_roll}+{def_bonus}→{def_final}]"
                    else:
                        def_dice = f"[{def_roll}+{def_bonus}={def_base_total}]"
                else:
                    if def_mod != 0:
                        def_dice = f"[{def_roll}→{def_final}]"
                    else:
                        def_dice = f"[{def_roll}]"

                # "vs"
                vs_surface = self.font_small.render(" vs ", True, COLOR_TEXT)
                self.screen.blit(vs_surface, (x, panel_y + 8))
                x += vs_surface.get_width()

                # Defender part
                def_color = COLOR_PLAYER1 if defender.player == 1 else COLOR_PLAYER2
                if def_mod != 0:
                    def_color = (100, 255, 100) if def_mod > 0 else (255, 100, 100)
                def_surface = self.font_small.render(f"{def_name}{def_dice}", True, def_color)
                self.screen.blit(def_surface, (x, panel_y + 8))

        elif game.last_combat:
            combat = game.last_combat

            # Format attacker roll with bonus if present
            atk_str = str(combat.attacker_roll)
            if hasattr(combat, 'attacker_bonus') and combat.attacker_bonus > 0:
                atk_str = f"{combat.attacker_roll}+{combat.attacker_bonus}"

            # Format defender roll with bonus if present
            def_str = str(combat.defender_roll)
            if hasattr(combat, 'defender_bonus') and combat.defender_bonus > 0:
                def_str = f"{combat.defender_roll}+{combat.defender_bonus}"

            # Get card names if available
            atk_name = getattr(combat, 'attacker_name', 'Атк')[:10]
            def_name = getattr(combat, 'defender_name', 'Защ')[:10]

            # One line: "Кубики: Name[roll] vs Name[roll]"
            text = f"Кубики: {atk_name}[{atk_str}] vs {def_name}[{def_str}]"
            text_surface = self.font_small.render(text, True, COLOR_TEXT)
            text_x = panel_x + (panel_width - text_surface.get_width()) // 2
            self.screen.blit(text_surface, (text_x, panel_y + 8))

    def draw_hand(self, game: Game):
        """Draw cards in hand during setup phase."""
        if game.phase != GamePhase.SETUP:
            return

        hand = game.get_current_hand()
        if not hand:
            return

        # Draw first few cards in hand
        panel_x = scaled(20)
        panel_y = scaled(120)
        panel_width = scaled(300)
        panel_height = scaled(350)

        pygame.draw.rect(self.screen, (35, 35, 45),
                         (panel_x, panel_y, panel_width, panel_height))
        pygame.draw.rect(self.screen, COLOR_TEXT,
                         (panel_x, panel_y, panel_width, panel_height), 1)

        title = f"Рука ({len(hand)} карт)"
        title_surface = self.font_medium.render(title, True, COLOR_TEXT)
        self.screen.blit(title_surface, (panel_x + 10, panel_y + 5))

        # Show first 8 cards
        y_offset = 35
        for i, card in enumerate(hand[:8]):
            text = f"{card.name} ({card.stats.cost})"
            if i == 0:
                color = COLOR_SELECTED  # Highlight first card (next to place)
            else:
                color = COLOR_TEXT
            card_surface = self.font_small.render(text, True, color)
            self.screen.blit(card_surface, (panel_x + 10, panel_y + y_offset))
            y_offset += 22

        if len(hand) > 8:
            more_text = f"...и ещё {len(hand) - 8}"
            more_surface = self.font_small.render(more_text, True, (150, 150, 150))
            self.screen.blit(more_surface, (panel_x + 10, panel_y + y_offset))

        # Instructions
        inst_y = panel_y + panel_height + 10
        inst = "Кликните на поле для размещения"
        inst_surface = self.font_small.render(inst, True, COLOR_TEXT)
        self.screen.blit(inst_surface, (panel_x, inst_y))

    def draw_graveyards(self, game: Game):
        """Draw graveyard panels for both players."""
        panel_width = scaled(UILayout.GRAVEYARD_WIDTH)
        panel_height = scaled(UILayout.GRAVEYARD_HEIGHT)
        collapsed_height = scaled(UILayout.GRAVEYARD_COLLAPSED_HEIGHT)

        # Player 2 graveyard (top-left)
        self._draw_graveyard_panel(
            game.board.graveyard_p2,
            player=2,
            x=scaled(UILayout.GRAVEYARD_X),
            y=scaled(UILayout.GRAVEYARD_P2_Y),
            width=panel_width,
            height=collapsed_height if self.graveyard_p2_collapsed else panel_height,
            collapsed=self.graveyard_p2_collapsed
        )

        # Player 1 graveyard (bottom-left)
        self._draw_graveyard_panel(
            game.board.graveyard_p1,
            player=1,
            x=scaled(UILayout.GRAVEYARD_X),
            y=scaled(UILayout.GRAVEYARD_P1_Y),
            width=panel_width,
            height=collapsed_height if self.graveyard_p1_collapsed else panel_height,
            collapsed=self.graveyard_p1_collapsed
        )

    def _draw_graveyard_panel(self, graveyard: list, player: int, x: int, y: int,
                               width: int, height: int, collapsed: bool = False):
        """Draw a single graveyard panel."""
        # Panel background
        bg_color = (35, 25, 25) if player == 1 else (25, 25, 35)
        pygame.draw.rect(self.screen, bg_color, (x, y, width, height))

        border_color = COLOR_PLAYER1 if player == 1 else COLOR_PLAYER2
        pygame.draw.rect(self.screen, border_color, (x, y, width, height), 2)

        # Title with collapse indicator (use simple ASCII for compatibility)
        collapse_indicator = "[+]" if collapsed else "[-]"
        title = f"{collapse_indicator} Кладб.П{player}"
        title_surface = self.font_small.render(title, True, border_color)
        self.screen.blit(title_surface, (x + 5, y + 5))

        # Card count (always shown)
        count_text = f"({len(graveyard)} карт)"
        count_surface = self.font_small.render(count_text, True, (150, 150, 150))
        self.screen.blit(count_surface, (x + 5, y + 22))

        # If collapsed, don't draw card list
        if collapsed:
            return

        # List of dead cards
        header_height = scaled(UILayout.GRAVEYARD_HEADER_HEIGHT)
        line_height = scaled(UILayout.GRAVEYARD_LINE_HEIGHT)
        y_offset = header_height
        max_visible = 12

        # Show most recent deaths first (reverse order)
        visible_cards = list(reversed(graveyard))[:max_visible]

        for i, card in enumerate(visible_cards):
            # Truncate long names
            name = card.name[:12] + '..' if len(card.name) > 12 else card.name

            # Add Valhalla indicator if card has it and died from enemy
            has_valhalla = any(aid.startswith("valhalla") for aid in card.stats.ability_ids)
            if has_valhalla and card.killed_by_enemy:
                name = "[V] " + name  # Valhalla active (triggers each turn)
                color = (255, 200, 100)  # Gold for Valhalla
            else:
                # Fade older cards
                brightness = max(100, 200 - i * 10)
                color = (brightness, brightness - 20, brightness - 20)

            card_surface = self.font_small.render(name, True, color)
            self.screen.blit(card_surface, (x + 8, y + y_offset))
            y_offset += line_height

        # Show "..." if more cards
        if len(graveyard) > max_visible:
            more_text = f"...ещё {len(graveyard) - max_visible}"
            more_surface = self.font_small.render(more_text, True, (100, 100, 100))
            self.screen.blit(more_surface, (x + 8, y + y_offset))

    def handle_graveyard_click(self, mouse_x: int, mouse_y: int) -> bool:
        """Check if click is on graveyard header and toggle collapse. Returns True if handled."""
        header_height = scaled(UILayout.GRAVEYARD_COLLAPSED_HEIGHT)

        # Player 2 graveyard header
        p2_x = scaled(UILayout.GRAVEYARD_X)
        p2_y = scaled(UILayout.GRAVEYARD_P2_Y)
        p2_width = scaled(UILayout.GRAVEYARD_WIDTH)

        if p2_x <= mouse_x <= p2_x + p2_width and p2_y <= mouse_y <= p2_y + header_height:
            self.graveyard_p2_collapsed = not self.graveyard_p2_collapsed
            return True

        # Player 1 graveyard header
        p1_x = scaled(UILayout.GRAVEYARD_X)
        p1_y = scaled(UILayout.GRAVEYARD_P1_Y)
        p1_width = scaled(UILayout.GRAVEYARD_WIDTH)

        if p1_x <= mouse_x <= p1_x + p1_width and p1_y <= mouse_y <= p1_y + header_height:
            self.graveyard_p1_collapsed = not self.graveyard_p1_collapsed
            return True

        return False

    def get_graveyard_card_at_pos(self, game: Game, mouse_x: int, mouse_y: int) -> Optional[Card]:
        """Check if mouse is over a graveyard card in expanded side panel."""
        panel_width = scaled(UILayout.SIDE_PANEL_WIDTH)
        tab_height = scaled(UILayout.SIDE_PANEL_TAB_HEIGHT)
        spacing = scaled(UILayout.SIDE_PANEL_SPACING)
        expanded_height = scaled(UILayout.SIDE_PANEL_EXPANDED_HEIGHT)
        card_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
        card_spacing = scaled(UILayout.SIDE_PANEL_CARD_SPACING)

        # Check P2 graveyard
        if self.is_panel_expanded('p2_grave'):
            panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
            base_y = scaled(UILayout.SIDE_PANEL_P2_Y) + tab_height + spacing
            content_y = base_y + tab_height + spacing
            graveyard = list(reversed(game.board.graveyard_p2))
            scroll = self.side_panel_scroll.get('p2_grave', 0)
            result = self._check_graveyard_click(mouse_x, mouse_y, panel_x, content_y, panel_width, expanded_height, card_size, card_spacing, graveyard, scroll)
            if result:
                return result

        # Check P1 graveyard
        if self.is_panel_expanded('p1_grave'):
            panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
            base_y = scaled(UILayout.SIDE_PANEL_P1_Y) + tab_height + spacing
            content_y = base_y + tab_height + spacing
            graveyard = list(reversed(game.board.graveyard_p1))
            scroll = self.side_panel_scroll.get('p1_grave', 0)
            result = self._check_graveyard_click(mouse_x, mouse_y, panel_x, content_y, panel_width, expanded_height, card_size, card_spacing, graveyard, scroll)
            if result:
                return result

        return None

    def _check_graveyard_click(self, mouse_x, mouse_y, panel_x, content_y, panel_width, expanded_height, card_size, card_spacing, graveyard, scroll):

        card_x = panel_x + (panel_width - card_size) // 2

        # Check if click is within any card
        for i, card in enumerate(graveyard):
            card_y = content_y + 5 + i * (card_size + card_spacing) - scroll
            card_rect = pygame.Rect(card_x, card_y, card_size, card_size)
            if card_rect.collidepoint(mouse_x, mouse_y):
                # Also check if within visible area
                if card_y + card_size > content_y and card_y < content_y + expanded_height:
                    return card

        return None

    def draw_side_panels(self, game: Game):
        """Draw unified side panels for flyers and graveyards with card thumbnails."""
        from .board import Board

        # Panel positions are fixed (physical screen locations)
        # SIDE_PANEL_P2_X is on the LEFT, SIDE_PANEL_P1_X is on the RIGHT
        left_panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
        left_panel_y = scaled(UILayout.SIDE_PANEL_P2_Y)
        right_panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
        right_panel_y = scaled(UILayout.SIDE_PANEL_P1_Y)

        # Determine which content goes where based on viewing player
        # For player 2's view, swap content so their cards are on the right
        if self.viewing_player == 2:
            left_flyers = game.board.flying_p1  # Opponent flyers on left
            right_flyers = game.board.flying_p2  # Own flyers on right
            left_graveyard = game.board.graveyard_p1
            right_graveyard = game.board.graveyard_p2
            left_label_flyers = "Летающие П1"
            right_label_flyers = "Летающие П2"
            left_label_grave = "Кладбище П1"
            right_label_grave = "Кладбище П2"
            left_color = COLOR_PLAYER1
            right_color = COLOR_PLAYER2
            left_flyer_panel = 'p1_flyers'
            right_flyer_panel = 'p2_flyers'
            left_grave_panel = 'p1_grave'
            right_grave_panel = 'p2_grave'
        else:
            left_flyers = game.board.flying_p2  # Opponent flyers on left
            right_flyers = game.board.flying_p1  # Own flyers on right
            left_graveyard = game.board.graveyard_p2
            right_graveyard = game.board.graveyard_p1
            left_label_flyers = "Летающие П2"
            right_label_flyers = "Летающие П1"
            left_label_grave = "Кладбище П2"
            right_label_grave = "Кладбище П1"
            left_color = COLOR_PLAYER2
            right_color = COLOR_PLAYER1
            left_flyer_panel = 'p2_flyers'
            right_flyer_panel = 'p1_flyers'
            left_grave_panel = 'p2_grave'
            right_grave_panel = 'p1_grave'

        # Auto-expand flying zones if they have flyers (and nothing else expanded for that player)
        has_p1_flyers = any(c is not None for c in game.board.flying_p1)
        has_p2_flyers = any(c is not None for c in game.board.flying_p2)
        if has_p1_flyers and self.expanded_panel_p1 is None:
            self.expanded_panel_p1 = 'flyers'
        if has_p2_flyers and self.expanded_panel_p2 is None:
            self.expanded_panel_p2 = 'flyers'

        # Force-expand flying panel when there are flying targets to select
        # This ensures clicking on flying cards works for defender selection,
        # counter shot, movement shot, ability targeting, etc.
        needs_flying_selection = (
            game.awaiting_defender or
            game.awaiting_counter_shot or
            game.awaiting_movement_shot or
            game.awaiting_ability_target
        )
        if needs_flying_selection and game.interaction:
            valid_positions = game.interaction.valid_positions
            # Check if any valid target is in P1 flying zone
            p1_flying_range = range(Board.FLYING_P1_START, Board.FLYING_P1_START + Board.FLYING_SLOTS)
            if any(pos in valid_positions for pos in p1_flying_range):
                self.expanded_panel_p1 = 'flyers'
            # Check if any valid target is in P2 flying zone
            p2_flying_range = range(Board.FLYING_P2_START, Board.FLYING_P2_START + Board.FLYING_SLOTS)
            if any(pos in valid_positions for pos in p2_flying_range):
                self.expanded_panel_p2 = 'flyers'

        # Also expand when attack mode shows flying targets
        if self._ui.attack_mode and self._ui.valid_attacks:
            p1_flying_range = range(Board.FLYING_P1_START, Board.FLYING_P1_START + Board.FLYING_SLOTS)
            if any(pos in self._ui.valid_attacks for pos in p1_flying_range):
                self.expanded_panel_p1 = 'flyers'
            p2_flying_range = range(Board.FLYING_P2_START, Board.FLYING_P2_START + Board.FLYING_SLOTS)
            if any(pos in self._ui.valid_attacks for pos in p2_flying_range):
                self.expanded_panel_p2 = 'flyers'

        panel_width = scaled(UILayout.SIDE_PANEL_WIDTH)
        tab_height = scaled(UILayout.SIDE_PANEL_TAB_HEIGHT)
        spacing = scaled(UILayout.SIDE_PANEL_SPACING)
        expanded_height = scaled(UILayout.SIDE_PANEL_EXPANDED_HEIGHT)
        card_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
        card_spacing = scaled(UILayout.SIDE_PANEL_CARD_SPACING)

        self.side_panel_tab_rects = {}

        # ========== LEFT SIDE PANEL ==========
        # Left flyers tab
        left_flyers_expanded = self.is_panel_expanded(left_flyer_panel)
        left_flyers_rect = pygame.Rect(left_panel_x, left_panel_y, panel_width, tab_height)
        self.side_panel_tab_rects[left_flyer_panel] = left_flyers_rect

        left_bg = (80, 50, 50) if left_color == COLOR_PLAYER2 else (50, 60, 80)
        left_bg_dark = (50, 35, 35) if left_color == COLOR_PLAYER2 else (30, 40, 50)
        tab_color = left_bg if left_flyers_expanded else left_bg_dark
        pygame.draw.rect(self.screen, tab_color, left_flyers_rect)
        pygame.draw.rect(self.screen, left_color, left_flyers_rect, 2)

        flyer_count = sum(1 for c in left_flyers if c is not None)
        label = self.font_small.render(f"{left_label_flyers} ({flyer_count})", True, left_color)
        self.screen.blit(label, (left_panel_x + 5, left_panel_y + 5))

        # Expanded content for left flyers
        if left_flyers_expanded:
            content_y = left_panel_y + tab_height + spacing
            content_rect = pygame.Rect(left_panel_x, content_y, panel_width, expanded_height)
            pygame.draw.rect(self.screen, left_bg_dark, content_rect)
            pygame.draw.rect(self.screen, left_color, content_rect, 1)

            flyers = [c for c in left_flyers if c is not None]
            scroll = self.side_panel_scroll.get(left_flyer_panel, 0)
            self._draw_panel_cards(flyers, left_panel_x, content_y, panel_width, expanded_height,
                                   card_size, card_spacing, scroll, game, left_flyer_panel)

        # Left graveyard tab
        left_grave_y = left_panel_y + tab_height + spacing
        if left_flyers_expanded:
            left_grave_y += expanded_height + spacing
        left_grave_expanded = self.is_panel_expanded(left_grave_panel)
        left_grave_rect = pygame.Rect(left_panel_x, left_grave_y, panel_width, tab_height)
        self.side_panel_tab_rects[left_grave_panel] = left_grave_rect

        tab_color = left_bg if left_grave_expanded else left_bg_dark
        pygame.draw.rect(self.screen, tab_color, left_grave_rect)
        pygame.draw.rect(self.screen, left_color, left_grave_rect, 2)

        grave_count = len(left_graveyard)
        label = self.font_small.render(f"{left_label_grave} ({grave_count})", True, left_color)
        self.screen.blit(label, (left_panel_x + 5, left_grave_y + 5))

        # Expanded content for left graveyard
        if left_grave_expanded:
            content_y = left_grave_y + tab_height + spacing
            content_rect = pygame.Rect(left_panel_x, content_y, panel_width, expanded_height)
            pygame.draw.rect(self.screen, left_bg_dark, content_rect)
            pygame.draw.rect(self.screen, left_color, content_rect, 1)

            grave_cards = list(reversed(left_graveyard))
            scroll = self.side_panel_scroll.get(left_grave_panel, 0)
            self._draw_panel_cards(grave_cards, left_panel_x, content_y, panel_width, expanded_height,
                                   card_size, card_spacing, scroll, game, left_grave_panel)

        # ========== RIGHT SIDE PANEL ==========
        # Right flyers tab
        right_flyers_expanded = self.is_panel_expanded(right_flyer_panel)
        right_flyers_rect = pygame.Rect(right_panel_x, right_panel_y, panel_width, tab_height)
        self.side_panel_tab_rects[right_flyer_panel] = right_flyers_rect

        right_bg = (80, 50, 50) if right_color == COLOR_PLAYER2 else (50, 60, 80)
        right_bg_dark = (50, 35, 35) if right_color == COLOR_PLAYER2 else (30, 40, 50)
        tab_color = right_bg if right_flyers_expanded else right_bg_dark
        pygame.draw.rect(self.screen, tab_color, right_flyers_rect)
        pygame.draw.rect(self.screen, right_color, right_flyers_rect, 2)

        flyer_count = sum(1 for c in right_flyers if c is not None)
        label = self.font_small.render(f"{right_label_flyers} ({flyer_count})", True, right_color)
        self.screen.blit(label, (right_panel_x + 5, right_panel_y + 5))

        # Expanded content for right flyers
        if right_flyers_expanded:
            content_y = right_panel_y + tab_height + spacing
            content_rect = pygame.Rect(right_panel_x, content_y, panel_width, expanded_height)
            pygame.draw.rect(self.screen, right_bg_dark, content_rect)
            pygame.draw.rect(self.screen, right_color, content_rect, 1)

            flyers = [c for c in right_flyers if c is not None]
            scroll = self.side_panel_scroll.get(right_flyer_panel, 0)
            self._draw_panel_cards(flyers, right_panel_x, content_y, panel_width, expanded_height,
                                   card_size, card_spacing, scroll, game, right_flyer_panel)

        # Right graveyard tab
        right_grave_y = right_panel_y + tab_height + spacing
        if right_flyers_expanded:
            right_grave_y += expanded_height + spacing
        right_grave_expanded = self.is_panel_expanded(right_grave_panel)
        right_grave_rect = pygame.Rect(right_panel_x, right_grave_y, panel_width, tab_height)
        self.side_panel_tab_rects[right_grave_panel] = right_grave_rect

        tab_color = right_bg if right_grave_expanded else right_bg_dark
        pygame.draw.rect(self.screen, tab_color, right_grave_rect)
        pygame.draw.rect(self.screen, right_color, right_grave_rect, 2)

        grave_count = len(right_graveyard)
        label = self.font_small.render(f"{right_label_grave} ({grave_count})", True, right_color)
        self.screen.blit(label, (right_panel_x + 5, right_grave_y + 5))

        # Expanded content for right graveyard
        if right_grave_expanded:
            content_y = right_grave_y + tab_height + spacing
            content_rect = pygame.Rect(right_panel_x, content_y, panel_width, expanded_height)
            pygame.draw.rect(self.screen, right_bg_dark, content_rect)
            pygame.draw.rect(self.screen, right_color, content_rect, 1)

            grave_cards = list(reversed(right_graveyard))
            scroll = self.side_panel_scroll.get(right_grave_panel, 0)
            self._draw_panel_cards(grave_cards, right_panel_x, content_y, panel_width, expanded_height,
                                   card_size, card_spacing, scroll, game, right_grave_panel)

    def _draw_panel_cards(self, cards: List[Card], panel_x: int, content_y: int,
                          panel_width: int, panel_height: int, card_size: int,
                          card_spacing: int, scroll: int, game: Game, panel_id: str):
        """Draw cards in a side panel with scrolling support."""
        if not cards:
            # Show empty message
            empty_text = self.font_small.render("Пусто", True, (100, 100, 100))
            self.screen.blit(empty_text, (panel_x + 10, content_y + 10))
            return

        # Calculate total content height
        total_height = len(cards) * (card_size + card_spacing) - card_spacing
        visible_height = panel_height - 10  # Padding

        # Clamp scroll
        max_scroll = max(0, total_height - visible_height)
        scroll = max(0, min(scroll, max_scroll))
        self.side_panel_scroll[panel_id] = scroll

        # Create clipping rect
        clip_rect = pygame.Rect(panel_x + 2, content_y + 2, panel_width - 4, panel_height - 4)
        old_clip = self.screen.get_clip()
        self.screen.set_clip(clip_rect)

        # Draw cards
        card_x = panel_x + (panel_width - card_size) // 2
        is_graveyard = 'grave' in panel_id
        is_flyers = 'flyers' in panel_id

        # Collect highlighted positions for flying cards
        highlighted_positions = set()
        highlighted_card_ids = set()  # For defender highlighting (uses card IDs)
        highlight_type = None  # 'attack', 'move', 'ability', 'defender', etc.
        if is_flyers and game:
            # Only show interaction highlights to the acting player
            is_acting = (game.interaction and game.interaction.acting_player == self.viewing_player)

            # Check various highlight modes (only for acting player)
            if game.awaiting_defender and game.interaction and is_acting:
                highlighted_card_ids = set(game.interaction.valid_card_ids)
                highlight_type = 'defender'
            elif game.awaiting_counter_shot and game.interaction and is_acting:
                highlighted_positions = set(game.interaction.valid_positions)
                highlight_type = 'counter_shot'
            elif game.awaiting_movement_shot and game.interaction and is_acting:
                highlighted_positions = set(game.interaction.valid_positions)
                highlight_type = 'counter_shot'
            elif game.awaiting_ability_target and game.interaction and is_acting:
                highlighted_positions = set(game.interaction.valid_positions)
                highlight_type = 'ability'
            elif game.awaiting_valhalla and game.interaction and is_acting:
                highlighted_positions = set(game.interaction.valid_positions)
                highlight_type = 'valhalla'
            elif game.current_player == self.viewing_player:
                # Normal mode - check valid_attacks (only for current player's turn)
                highlighted_positions = set(self._ui.valid_attacks)
                highlight_type = 'attack'

        for i, card in enumerate(cards):
            card_y = content_y + 5 + i * (card_size + card_spacing) - scroll
            # Only draw if visible
            if card_y + card_size > content_y and card_y < content_y + panel_height:
                self.draw_card_thumbnail(card, card_x, card_y, card_size, game, is_graveyard)

                # Draw selection border for selected flying card (gold)
                if is_flyers and game and self._ui.selected_card == card:
                    select_rect = pygame.Rect(card_x, card_y, card_size, card_size)
                    pygame.draw.rect(self.screen, (255, 215, 0), select_rect, 3)  # Gold border

                # Draw highlight as colored border around card (not covering art)
                # Check both position-based and card-id-based highlights
                is_highlighted = (
                    (is_flyers and card.position in highlighted_positions) or
                    (is_flyers and card.id in highlighted_card_ids)
                )
                if is_highlighted:
                    border_width = 4
                    if highlight_type == 'defender':
                        # Pulsing red glow for defenders
                        import math
                        glow_intensity = 0.5 + 0.5 * math.sin(self.priority_glow_timer)
                        border_color = (255, int(100 * glow_intensity), int(100 * glow_intensity))
                    elif highlight_type == 'attack':
                        border_color = (255, 100, 100)  # Red
                    elif highlight_type == 'ability':
                        border_color = (180, 100, 220)  # Purple
                    elif highlight_type == 'valhalla':
                        border_color = (255, 200, 100)  # Gold
                    elif highlight_type == 'counter_shot':
                        border_color = (255, 150, 50)  # Orange
                    else:
                        border_color = (200, 200, 200)  # Default gray
                    highlight_rect = pygame.Rect(card_x, card_y, card_size, card_size)
                    pygame.draw.rect(self.screen, border_color, highlight_rect, border_width)

                # Valhalla indicator for graveyard cards
                if is_graveyard:
                    has_valhalla = any(aid.startswith("valhalla") for aid in card.stats.ability_ids)
                    if has_valhalla and card.killed_by_enemy:
                        valhalla_text = self.font_small.render("[V]", True, (255, 200, 100))
                        self.screen.blit(valhalla_text, (card_x + 4, card_y + card_size - 30))

        # Restore clip
        self.screen.set_clip(old_clip)

        # Draw scroll indicators if needed
        if max_scroll > 0:
            if scroll > 0:
                # Up arrow
                pygame.draw.polygon(self.screen, (180, 180, 180),
                                    [(panel_x + panel_width - 15, content_y + 8),
                                     (panel_x + panel_width - 10, content_y + 3),
                                     (panel_x + panel_width - 5, content_y + 8)])
            if scroll < max_scroll:
                # Down arrow
                pygame.draw.polygon(self.screen, (180, 180, 180),
                                    [(panel_x + panel_width - 15, content_y + panel_height - 8),
                                     (panel_x + panel_width - 10, content_y + panel_height - 3),
                                     (panel_x + panel_width - 5, content_y + panel_height - 8)])

    def scroll_side_panel(self, direction: int, panel_id: str = None):
        """Scroll a side panel. If panel_id not specified, scrolls the expanded panel for each player."""
        card_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
        scroll_amount = card_size // 2  # Scroll by half a card

        if panel_id:
            self.side_panel_scroll[panel_id] = max(
                0, self.side_panel_scroll.get(panel_id, 0) + direction * scroll_amount
            )
        else:
            # Scroll whichever panel is expanded for each player
            if self.expanded_panel_p1:
                p1_panel = f'p1_{self.expanded_panel_p1}'
                self.side_panel_scroll[p1_panel] = max(
                    0, self.side_panel_scroll.get(p1_panel, 0) + direction * scroll_amount
                )
            if self.expanded_panel_p2:
                p2_panel = f'p2_{self.expanded_panel_p2}'
                self.side_panel_scroll[p2_panel] = max(
                    0, self.side_panel_scroll.get(p2_panel, 0) + direction * scroll_amount
                )

    def handle_side_panel_click(self, mouse_x: int, mouse_y: int) -> bool:
        """Handle click on side panel tabs. Returns True if handled."""
        for panel_id, rect in self.side_panel_tab_rects.items():
            if rect.collidepoint(mouse_x, mouse_y):
                self.toggle_panel(panel_id)
                return True
        return False

    def get_flying_slot_at_pos(self, mouse_x: int, mouse_y: int) -> Optional[int]:
        """Check if mouse is over a flying slot and return the position (30-35)."""
        from .board import Board

        tab_height = scaled(UILayout.SIDE_PANEL_TAB_HEIGHT)
        spacing = scaled(UILayout.SIDE_PANEL_SPACING)
        card_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
        card_spacing = scaled(UILayout.SIDE_PANEL_CARD_SPACING)
        panel_width = scaled(UILayout.SIDE_PANEL_WIDTH)

        # Check P1 flyers - for player 2's view, P1's flyers are on left (P2's panel position)
        if self.is_panel_expanded('p1_flyers'):
            if self.viewing_player == 2:
                panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
                base_y = scaled(UILayout.SIDE_PANEL_P2_Y) + tab_height + spacing
            else:
                panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
                base_y = scaled(UILayout.SIDE_PANEL_P1_Y) + tab_height + spacing
            scroll = self.side_panel_scroll.get('p1_flyers', 0)
            card_x = panel_x + (panel_width - card_size) // 2
            content_y = base_y + 5
            for i in range(Board.FLYING_SLOTS):
                slot_y = content_y + i * (card_size + card_spacing) - scroll
                slot_rect = pygame.Rect(card_x, slot_y, card_size, card_size)
                if slot_rect.collidepoint(mouse_x, mouse_y):
                    return Board.FLYING_P1_START + i

        # Check P2 flyers - for player 2's view, P2's flyers are on right (P1's panel position)
        if self.is_panel_expanded('p2_flyers'):
            if self.viewing_player == 2:
                panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
                base_y = scaled(UILayout.SIDE_PANEL_P1_Y) + tab_height + spacing
            else:
                panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
                base_y = scaled(UILayout.SIDE_PANEL_P2_Y) + tab_height + spacing
            scroll = self.side_panel_scroll.get('p2_flyers', 0)
            card_x = panel_x + (panel_width - card_size) // 2
            content_y = base_y + 5
            for i in range(Board.FLYING_SLOTS):
                slot_y = content_y + i * (card_size + card_spacing) - scroll
                slot_rect = pygame.Rect(card_x, slot_y, card_size, card_size)
                if slot_rect.collidepoint(mouse_x, mouse_y):
                    return Board.FLYING_P2_START + i

        return None

    def draw(self, game: Game, dt: float = 0.016, ui_state: 'UIState' = None, skip_flip: bool = False, test_controlled_player: any = "not_test_game"):
        """Main draw function.

        Args:
            game: Game state to render
            dt: Delta time for animations
            ui_state: UIState for client-side selection/highlighting (required).
            skip_flip: If True, skip pygame.display.flip() - caller will handle it.
            test_controlled_player: For test game mode - pass None (auto) or 1/2 (manual control).
                                   Pass "not_test_game" (default) to hide the indicator.
        """
        import math

        # Populate _ui from UIState
        if ui_state is not None:
            self._ui.selected_card = game.get_card_by_id(ui_state.selected_card_id) if ui_state.selected_card_id else None
            self._ui.valid_moves = list(ui_state.valid_moves)
            self._ui.valid_attacks = list(ui_state.valid_attacks)
            self._ui.attack_mode = ui_state.attack_mode
            # Set viewing_player for board perspective (P2 sees board flipped)
            self.viewing_player = ui_state.viewing_player
        else:
            # No ui_state provided - clear all selection state
            self._ui.selected_card = None
            self._ui.valid_moves = []
            self._ui.valid_attacks = []
            self._ui.attack_mode = False
            self.viewing_player = 1

        # Update priority glow animation timer (also used for forced attack and defender highlight)
        if game.awaiting_priority or game.has_forced_attack or game.awaiting_defender:
            self.priority_glow_timer += dt * 4  # Speed of pulsing
            if self.priority_glow_timer > 2 * math.pi:
                self.priority_glow_timer -= 2 * math.pi
        else:
            self.priority_glow_timer = 0.0

        # Clear render surface
        self.screen.fill(COLOR_BG)

        # Update card movement animations BEFORE drawing cards
        self.update_card_animations(game, dt)

        # Draw everything to render surface
        self.draw_board(game)
        self.draw_side_panels(game)
        self.draw_highlights(game)  # Board highlights only (flying handled in side panels)
        self.draw_cards(game)
        self.draw_ui(game)
        self.draw_hand(game)

        # Draw side control indicator for test game mode
        if test_controlled_player != "not_test_game":
            self.draw_side_control_indicator(test_controlled_player)

        # Draw priority phase UI (info box, pass button, dice popup) or turn indicator
        if game.awaiting_priority:
            self.draw_priority_info(game)
            # Only show pass button to priority player
            if game.priority_player == self.viewing_player:
                self.draw_pass_button(game)
            # Draw dice popup if open
            if self.dice_popup_open:
                self.draw_dice_popup(game)
        else:
            # Close dice popup if priority ended
            if self.dice_popup_open:
                self.close_dice_popup()
            # Show turn indicator when not in priority phase
            self.draw_turn_indicator(game)

        # Draw counter selection popup (only for acting player)
        if game.awaiting_counter_selection:
            if game.interaction and game.interaction.acting_player == self.viewing_player:
                self.draw_counter_popup(game)

        # Update and draw floating texts
        self.update_floating_texts(dt)
        self.draw_floating_texts()

        # Update and draw interaction arrows
        self.update_arrows(dt)
        self.draw_arrows()

        self.draw_popup()

        # Draw game over popup if active
        if self.game_over_popup:
            self.draw_game_over_popup()

        # Scale and blit to window
        self.window.fill((0, 0, 0))  # Black letterbox
        if self.scale != 1.0:
            scaled_w = int(self.BASE_WIDTH * self.scale)
            scaled_h = int(self.BASE_HEIGHT * self.scale)
            scaled_surface = pygame.transform.smoothscale(self.screen, (scaled_w, scaled_h))
            self.window.blit(scaled_surface, (self.offset_x, self.offset_y))
        else:
            self.window.blit(self.screen, (self.offset_x, self.offset_y))

        if not skip_flip:
            pygame.display.flip()


    def open_dice_popup(self, card: Card):
        """Open the dice modification popup for an instant ability card."""
        self.dice_popup_open = True
        self.dice_popup_card = card

    def close_dice_popup(self):
        """Close the dice modification popup."""
        self.dice_popup_open = False
        self.dice_popup_card = None
        self.dice_option_buttons = []

    def _draw_dice_row(self, popup_x: int, y_offset: int, card: Card, roll: int,
                        modifier: int, bonus: int, btn_prefix: str):
        """Draw a single dice row with name, dice value, and modification buttons.

        Args:
            popup_x: X position of popup
            y_offset: Y position for this row
            card: The card (attacker or defender)
            roll: Base dice roll value
            modifier: Luck modifier applied
            bonus: Ability bonus (OvA/OvZ)
            btn_prefix: Prefix for button IDs ('atk' or 'def')
        """
        color = COLOR_PLAYER1 if card.player == 1 else COLOR_PLAYER2
        total = roll + modifier + bonus

        # Draw card name
        name_surface = self.font_medium.render(f"{card.name}:", True, color)
        self.screen.blit(name_surface, (popup_x + 15, y_offset))

        # Draw dice value
        dice_x = popup_x + 170
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

        # Draw modification buttons
        btn_x = popup_x + 290
        for suffix, label, color in [('_plus1', '+1', (80, 140, 80)),
                                     ('_minus1', '-1', (140, 80, 80)),
                                     ('_reroll', 'Re', (80, 80, 140))]:
            btn_rect = pygame.Rect(btn_x, y_offset - 3, 48, 26)
            pygame.draw.rect(self.screen, color, btn_rect)
            pygame.draw.rect(self.screen, COLOR_TEXT, btn_rect, 1)
            btn_text = self.font_small.render(label, True, COLOR_TEXT)
            self.screen.blit(btn_text, (btn_rect.x + (48 - btn_text.get_width()) // 2,
                                        btn_rect.y + (26 - btn_text.get_height()) // 2))
            self.dice_option_buttons.append((f'{btn_prefix}{suffix}', btn_rect))
            btn_x += 52

    def draw_dice_popup(self, game: Game):
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
            target_color = COLOR_PLAYER1 if target.player == 1 else COLOR_PLAYER2
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

    def draw_counter_popup(self, game: Game):
        """Draw counter selection popup for abilities like axe_strike."""
        if not game.awaiting_counter_selection or not game.counter_selection_card:
            return

        card = game.counter_selection_card
        max_counters = card.counters
        selected = game.interaction.selected_amount if game.interaction else 0

        # Popup dimensions
        popup_width = 350
        popup_height = 150
        popup_x = (WINDOW_WIDTH - popup_width) // 2
        popup_y = 150

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
        btn_spacing = 20
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
        if self.counter_confirm_button and self.counter_confirm_button.collidepoint(mouse_x, mouse_y):
            return 'confirm'
        if self.counter_cancel_button and self.counter_cancel_button.collidepoint(mouse_x, mouse_y):
            return 'cancel'
        for count, btn_rect in self.counter_popup_buttons:
            if btn_rect.collidepoint(mouse_x, mouse_y):
                return count
        return None

    def get_end_turn_button_rect(self) -> pygame.Rect:
        """Get the end turn button rectangle for click detection."""
        return pygame.Rect(
            scaled(UILayout.END_TURN_X),
            scaled(UILayout.END_TURN_Y),
            scaled(UILayout.END_TURN_WIDTH),
            scaled(UILayout.END_TURN_HEIGHT)
        )

    def get_skip_button_rect(self) -> pygame.Rect:
        """Get the skip button rectangle for click detection."""
        return pygame.Rect(
            scaled(UILayout.SKIP_X),
            scaled(UILayout.SKIP_Y),
            scaled(UILayout.SKIP_WIDTH),
            scaled(UILayout.SKIP_HEIGHT)
        )

    def get_pass_button_rect(self) -> pygame.Rect:
        """Get the pass priority button rectangle."""
        # Same position as skip button (replaces it during priority)
        return pygame.Rect(
            scaled(UILayout.SKIP_X),
            scaled(UILayout.SKIP_Y),
            scaled(UILayout.SKIP_WIDTH),
            scaled(UILayout.SKIP_HEIGHT)
        )

    def draw_skip_button(self, game: Game):
        """Draw skip button under the combat log."""
        button_rect = self.get_skip_button_rect()
        pygame.draw.rect(self.screen, (80, 60, 60), button_rect)
        pygame.draw.rect(self.screen, (140, 120, 120), button_rect, 2)

        button_text = "Пропустить"
        button_surface = self.font_medium.render(button_text, True, COLOR_TEXT)
        text_x = button_rect.x + (button_rect.width - button_surface.get_width()) // 2
        text_y = button_rect.y + (button_rect.height - button_surface.get_height()) // 2
        self.screen.blit(button_surface, (text_x, text_y))

    def draw_pass_button(self, game: Game):
        """Draw pass priority button (same style as skip)."""
        button_rect = self.get_pass_button_rect()
        pygame.draw.rect(self.screen, (60, 50, 80), button_rect)  # Purple tint
        pygame.draw.rect(self.screen, (100, 80, 140), button_rect, 2)

        button_text = "Пасс"
        button_surface = self.font_medium.render(button_text, True, COLOR_TEXT)
        text_x = button_rect.x + (button_rect.width - button_surface.get_width()) // 2
        text_y = button_rect.y + (button_rect.height - button_surface.get_height()) // 2
        self.screen.blit(button_surface, (text_x, text_y))

    def draw_turn_indicator(self, game: Game):
        """Draw turn indicator showing whose turn it is from viewing player's perspective."""
        # Don't show during priority phase (priority info is shown instead)
        if game.awaiting_priority:
            return

        # Draw turn indicator box (same position as priority bar)
        info_x = WINDOW_WIDTH - scaled(UILayout.PRIORITY_BAR_X_OFFSET)
        info_y = scaled(UILayout.PRIORITY_BAR_Y)
        info_width = scaled(UILayout.PRIORITY_BAR_WIDTH)
        info_height = scaled(UILayout.PRIORITY_BAR_HEIGHT)

        is_my_turn = game.current_player == self.viewing_player

        # Background color based on whose turn
        if is_my_turn:
            bg_color = (40, 60, 40)  # Green tint for your turn
            border_color = (80, 140, 80)
            text = "Ваш ход"
        else:
            bg_color = (60, 40, 40)  # Red tint for opponent's turn
            border_color = (140, 80, 80)
            text = "Ход противника"

        pygame.draw.rect(self.screen, bg_color, (info_x, info_y, info_width, info_height))
        pygame.draw.rect(self.screen, border_color, (info_x, info_y, info_width, info_height), 2)

        # Text
        text_surface = self.font_medium.render(text, True, COLOR_TEXT)
        text_x = info_x + (info_width - text_surface.get_width()) // 2
        self.screen.blit(text_surface, (text_x, info_y + 4))

    def draw_side_control_indicator(self, controlled_player: Optional[int]):
        """Draw indicator showing which side is being controlled (test game mode).

        Args:
            controlled_player: None for auto, 1 or 2 for manual control
        """
        # Draw at top-left corner
        x = scaled(10)
        y = scaled(10)

        if controlled_player is None:
            text = "TAB: Авто (ход)"
            bg_color = (40, 40, 40)
            border_color = (80, 80, 80)
        elif controlled_player == 1:
            text = "TAB: Игрок 1"
            bg_color = (35, 65, 90)  # Dark blue
            border_color = COLOR_PLAYER1
        else:
            text = "TAB: Игрок 2"
            bg_color = (90, 35, 35)  # Dark red
            border_color = COLOR_PLAYER2

        text_surface = self.font_small.render(text, True, COLOR_TEXT)
        padding = scaled(6)
        width = text_surface.get_width() + padding * 2
        height = text_surface.get_height() + padding * 2

        pygame.draw.rect(self.screen, bg_color, (x, y, width, height))
        pygame.draw.rect(self.screen, border_color, (x, y, width, height), 2)
        self.screen.blit(text_surface, (x + padding, y + padding))

    def draw_priority_info(self, game: Game):
        """Draw priority phase info under buttons."""
        if not game.awaiting_priority:
            return

        # Draw priority info box
        info_x = WINDOW_WIDTH - scaled(UILayout.PRIORITY_BAR_X_OFFSET)
        info_y = scaled(UILayout.PRIORITY_BAR_Y)
        info_width = scaled(UILayout.PRIORITY_BAR_WIDTH)
        info_height = scaled(UILayout.PRIORITY_BAR_HEIGHT)

        # Background
        pygame.draw.rect(self.screen, (50, 40, 70), (info_x, info_y, info_width, info_height))
        pygame.draw.rect(self.screen, (100, 80, 140), (info_x, info_y, info_width, info_height), 2)

        # Priority player text - show from viewing player's perspective
        is_my_priority = game.priority_player == self.viewing_player
        if is_my_priority:
            priority_text = "Ваш приоритет"
            priority_color = (100, 200, 100)  # Green
        else:
            priority_text = "Приоритет противника"
            priority_color = (200, 100, 100)  # Red
        text_surface = self.font_medium.render(priority_text, True, priority_color)
        text_x = info_x + (info_width - text_surface.get_width()) // 2
        self.screen.blit(text_surface, (text_x, info_y + 4))

    def _get_popup_pos(self, popup_id: str, default_x: int, default_y: int) -> Tuple[int, int]:
        """Get popup position, using stored position or default."""
        if popup_id not in self.popup_positions:
            self.popup_positions[popup_id] = (default_x, default_y)
        return self.popup_positions[popup_id]

    def _get_popup_rect(self, popup_id: str, width: int, height: int, default_x: int, default_y: int) -> pygame.Rect:
        """Get popup rectangle with stored or default position."""
        x, y = self._get_popup_pos(popup_id, default_x, default_y)
        return pygame.Rect(x, y, width, height)

    def draw_popup_base(self, config: PopupConfig) -> Tuple[int, int, int]:
        """
        Draw popup background, border, drag handle, and title.
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

    def start_popup_drag(self, mouse_x: int, mouse_y: int, game: Game) -> bool:
        """Try to start dragging a popup. Returns True if drag started."""
        # Only check popups that are currently visible
        active_popups = []
        if game.awaiting_defender:
            active_popups.append(('defender', 500, 100))
        if game.awaiting_valhalla:
            active_popups.append(('valhalla', 450, 80))
        if game.awaiting_counter_shot:
            active_popups.append(('counter_shot', 400, 60))
        if game.awaiting_heal_confirm:
            active_popups.append(('heal_confirm', 350, 90))
        if game.awaiting_exchange_choice:
            active_popups.append(('exchange', 320, 100))

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

    def get_clicked_ability(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if an ability button was clicked. Returns ability_id or None."""
        for rect, ability_id in self.ability_button_rects:
            if rect.collidepoint(mouse_x, mouse_y):
                return ability_id
        return None

    def get_clicked_attack_button(self, mouse_x: int, mouse_y: int) -> bool:
        """Check if the attack button was clicked."""
        if self.attack_button_rect and self.attack_button_rect.collidepoint(mouse_x, mouse_y):
            return True
        return False

    def get_clicked_heal_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if a heal confirmation button was clicked. Returns 'yes', 'no', or None."""
        for button_id, rect in self.heal_confirm_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return button_id
        return None

    def get_clicked_exchange_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if an exchange choice button was clicked. Returns 'full', 'reduce', or None."""
        for button_id, rect in self.exchange_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return button_id
        return None

    def get_clicked_stench_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if a stench choice button was clicked. Returns 'tap', 'damage', or None."""
        for button_id, rect in self.stench_choice_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return button_id
        return None

    def add_floating_text(self, board_pos: int, text: str, color: Tuple[int, int, int]):
        """Add a floating text effect at a board position."""
        x, y = self.pos_to_screen(board_pos)
        # Center on cell
        x += CELL_SIZE // 2
        y += CELL_SIZE // 2
        self.floating_texts.append({
            'x': x,
            'y': y,
            'text': text,
            'color': color,
            'life': 1.0,  # Lifetime in seconds
            'max_life': 1.0
        })

    def update_card_animations(self, game: 'Game', dt: float):
        """Update card movement animations and detect new movements."""
        # Update existing animations
        finished = []
        for card_id, anim in self.card_animations.items():
            anim['progress'] += dt / self.CARD_MOVE_DURATION
            if anim['progress'] >= 1.0:
                finished.append(card_id)
        for card_id in finished:
            del self.card_animations[card_id]

        # Detect new card movements by comparing positions
        current_positions = {}
        for pos in range(36):  # All board positions including flying
            card = game.board.get_card(pos)
            if card:
                current_positions[card.id] = pos

        # Check for position changes
        for card_id, new_pos in current_positions.items():
            old_pos = self.card_last_positions.get(card_id)
            if old_pos is not None and old_pos != new_pos:
                # Card moved - start animation
                from_x, from_y = self.pos_to_screen(old_pos)
                to_x, to_y = self.pos_to_screen(new_pos)
                self.card_animations[card_id] = {
                    'from_x': from_x,
                    'from_y': from_y,
                    'to_x': to_x,
                    'to_y': to_y,
                    'progress': 0.0
                }

        # Update last known positions
        self.card_last_positions = current_positions

    def get_card_draw_position(self, card_id: int, base_x: int, base_y: int) -> Tuple[int, int]:
        """Get the position to draw a card, accounting for movement animation."""
        if card_id in self.card_animations:
            anim = self.card_animations[card_id]
            # Smooth easing function (ease-out)
            t = anim['progress']
            t = 1 - (1 - t) ** 2  # Quadratic ease-out
            x = int(anim['from_x'] + (anim['to_x'] - anim['from_x']) * t)
            y = int(anim['from_y'] + (anim['to_y'] - anim['from_y']) * t)
            return x, y
        return base_x, base_y

    def update_floating_texts(self, dt: float):
        """Update floating text positions and lifetimes."""
        for ft in self.floating_texts:
            ft['life'] -= dt
            ft['y'] -= 40 * dt  # Float upward
        # Remove dead texts
        self.floating_texts = [ft for ft in self.floating_texts if ft['life'] > 0]

    def draw_floating_texts(self):
        """Draw all floating text effects."""
        for ft in self.floating_texts:
            alpha = int(255 * (ft['life'] / ft['max_life']))
            # Create text surface
            text_surface = self.font_large.render(ft['text'], True, ft['color'])
            # Apply alpha by creating a copy with per-pixel alpha
            text_surface.set_alpha(alpha)
            # Center text
            text_x = ft['x'] - text_surface.get_width() // 2
            text_y = int(ft['y']) - text_surface.get_height() // 2
            self.screen.blit(text_surface, (text_x, text_y))

    def add_arrow(self, from_pos: int, to_pos: int, color: Tuple[int, int, int]):
        """Add an interaction arrow between two board positions."""
        self.arrows.append({
            'from_pos': from_pos,
            'to_pos': to_pos,
            'color': color,
            'min_display': 1.0,  # Minimum display time in seconds
        })

    def clear_arrows(self):
        """Mark all arrows to clear after minimum display time."""
        for arrow in self.arrows:
            # Mark for clearing - will be removed after min_display reaches 0
            arrow['clearing'] = True

    def clear_arrows_immediate(self):
        """Clear all arrows immediately (for cancellation)."""
        self.arrows.clear()

    def update_arrows(self, dt: float):
        """Update arrow timers."""
        for arrow in self.arrows:
            arrow['min_display'] -= dt
        # Remove arrows that are marked for clearing AND have shown for minimum time
        self.arrows = [a for a in self.arrows
                       if not (a.get('clearing') and a['min_display'] <= 0)]

    def draw_arrows(self):
        """Draw all interaction arrows."""
        import math
        for arrow in self.arrows:
            alpha = 255  # Full opacity until cleared

            # Get screen positions (center of cells)
            from_x, from_y = self.pos_to_screen(arrow['from_pos'])
            to_x, to_y = self.pos_to_screen(arrow['to_pos'])
            from_x += CELL_SIZE // 2
            from_y += CELL_SIZE // 2
            to_x += CELL_SIZE // 2
            to_y += CELL_SIZE // 2

            # Calculate arrow direction
            dx = to_x - from_x
            dy = to_y - from_y
            length = math.sqrt(dx * dx + dy * dy)
            if length < 1:
                continue

            # Normalize direction
            dx /= length
            dy /= length

            # Shorten arrow to not overlap cards
            margin = 45
            start_x = from_x + dx * margin
            start_y = from_y + dy * margin
            end_x = to_x - dx * margin
            end_y = to_y - dy * margin

            # Create surface for arrow with alpha
            arrow_surface = pygame.Surface((self.BASE_WIDTH, self.BASE_HEIGHT), pygame.SRCALPHA)

            # Draw arrow line (thick)
            color_with_alpha = (*arrow['color'], alpha)
            pygame.draw.line(arrow_surface, color_with_alpha,
                           (int(start_x), int(start_y)),
                           (int(end_x), int(end_y)), 4)

            # Draw arrowhead
            head_length = 15
            head_angle = math.pi / 6  # 30 degrees

            # Calculate arrowhead points
            angle = math.atan2(dy, dx)
            head_x1 = end_x - head_length * math.cos(angle - head_angle)
            head_y1 = end_y - head_length * math.sin(angle - head_angle)
            head_x2 = end_x - head_length * math.cos(angle + head_angle)
            head_y2 = end_y - head_length * math.sin(angle + head_angle)

            pygame.draw.polygon(arrow_surface, color_with_alpha, [
                (int(end_x), int(end_y)),
                (int(head_x1), int(head_y1)),
                (int(head_x2), int(head_y2))
            ])

            self.screen.blit(arrow_surface, (0, 0))

    def get_card_at_screen_pos(self, game: Game, mouse_x: int, mouse_y: int) -> Optional[Card]:
        """Get card at screen position, if any."""
        pos = self.screen_to_pos(mouse_x, mouse_y)
        if pos is not None:
            return game.board.get_card(pos)
        return None

    def show_popup(self, card: Card):
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

    def show_game_over_popup(self, winner: int, player1_name: str = None, player2_name: str = None):
        """Show game over popup with winner info.

        Args:
            winner: 1 or 2 for winner, 0 for draw
            player1_name: Name of player 1 (optional)
            player2_name: Name of player 2 (optional)
        """
        self.game_over_popup = True
        self.game_over_winner = winner
        self.game_over_player1_name = player1_name
        self.game_over_player2_name = player2_name

    def hide_game_over_popup(self):
        """Hide game over popup."""
        self.game_over_popup = False
        self.game_over_button_rect = None

    def draw_game_over_popup(self):
        """Draw game over popup if active."""
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

        # Winner text
        if self.game_over_winner == 0:
            title_text = "Ничья!"
            title_color = (200, 200, 200)
            winner_name = None
        else:
            if self.game_over_winner == 1:
                title_color = COLOR_PLAYER1
                winner_name = getattr(self, 'game_over_player1_name', None)
            else:
                title_color = COLOR_PLAYER2
                winner_name = getattr(self, 'game_over_player2_name', None)

            if winner_name:
                title_text = f"Победил игрок {self.game_over_winner}!"
            else:
                title_text = f"Победа игрока {self.game_over_winner}!"

        title_surface = self.font_large.render(title_text, True, title_color)
        title_x = popup_x + (popup_w - title_surface.get_width()) // 2
        title_y = popup_y + scaled(35)
        self.screen.blit(title_surface, (title_x, title_y))

        # Winner name (if available)
        if self.game_over_winner != 0 and winner_name:
            name_text = winner_name
            name_surface = self.font_medium.render(name_text, True, title_color)
            name_x = popup_x + (popup_w - name_surface.get_width()) // 2
            name_y = popup_y + scaled(75)
            self.screen.blit(name_surface, (name_x, name_y))
            congrats_y = popup_y + scaled(110)
        else:
            congrats_y = popup_y + scaled(80)

        # Congratulations text (skip for draws)
        if self.game_over_winner != 0:
            congrats_text = "Поздравляем!"
            congrats_surface = self.font_medium.render(congrats_text, True, COLOR_TEXT)
            congrats_x = popup_x + (popup_w - congrats_surface.get_width()) // 2
            self.screen.blit(congrats_surface, (congrats_x, congrats_y))

        # OK button
        btn_w = scaled(150)
        btn_h = scaled(40)
        btn_x = popup_x + (popup_w - btn_w) // 2
        btn_y = popup_y + popup_h - btn_h - scaled(20)

        self.game_over_button_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        pygame.draw.rect(self.screen, (60, 100, 60), self.game_over_button_rect)
        pygame.draw.rect(self.screen, (80, 140, 80), self.game_over_button_rect, 2)

        btn_text = self.font_medium.render("В меню", True, COLOR_TEXT)
        btn_text_x = btn_x + (btn_w - btn_text.get_width()) // 2
        btn_text_y = btn_y + (btn_h - btn_text.get_height()) // 2
        self.screen.blit(btn_text, (btn_text_x, btn_text_y))

    def is_game_over_button_clicked(self, x: int, y: int) -> bool:
        """Check if game over button was clicked."""
        return self.game_over_button_rect and self.game_over_button_rect.collidepoint(x, y)

    def get_deck_builder_resources(self) -> tuple:
        """Get resources needed for deck builder renderer.

        Returns (screen, card_images, card_images_full, fonts_dict)
        """
        fonts = {
            'large': self.font_large,
            'medium': self.font_medium,
            'small': self.font_small,
            'card_name': self.font_card_name,
            'indicator': self.font_indicator,
        }
        return self.screen, self.card_images, self.card_images_full, fonts

    def draw_menu(self):
        """Draw the main menu screen."""
        self.menu_buttons = []

        # Clear screen with background
        self.screen.fill(COLOR_BG)

        # Title
        title_font = pygame.font.SysFont('arial', scaled(48))
        title = title_font.render("БЕРСЕРК", True, (200, 180, 100))
        title_x = (WINDOW_WIDTH - title.get_width()) // 2
        self.screen.blit(title, (title_x, scaled(80)))

        # Subtitle
        subtitle = self.font_medium.render("Цифровая карточная игра", True, (150, 150, 160))
        subtitle_x = (WINDOW_WIDTH - subtitle.get_width()) // 2
        self.screen.blit(subtitle, (subtitle_x, scaled(140)))

        # Menu buttons
        buttons = [
            ("test_game", "Тестовая игра", True),
            ("local_game", "Hotseat", True),
            ("network_game", "Игра по сети", True),
            ("bot_game", "Игра с ботом", False),
            ("deck_builder", "Создание колоды", True),
            ("settings", "Настройки", True),
            ("exit", "Выход", True),
        ]

        btn_width = scaled(280)
        btn_height = scaled(45)
        btn_spacing = scaled(15)
        start_y = scaled(220)

        for i, (btn_id, btn_text, is_active) in enumerate(buttons):
            btn_x = (WINDOW_WIDTH - btn_width) // 2
            btn_y = start_y + i * (btn_height + btn_spacing)
            btn_rect = pygame.Rect(btn_x, btn_y, btn_width, btn_height)

            # Button colors based on active state
            if is_active:
                bg_color = (60, 50, 70)
                border_color = (120, 100, 140)
                text_color = COLOR_TEXT
            else:
                bg_color = (40, 40, 45)
                border_color = (70, 70, 80)
                text_color = (100, 100, 110)

            # Draw button
            pygame.draw.rect(self.screen, bg_color, btn_rect)
            pygame.draw.rect(self.screen, border_color, btn_rect, 2)

            # Draw text centered
            text_surface = self.font_medium.render(btn_text, True, text_color)
            text_x = btn_rect.x + (btn_width - text_surface.get_width()) // 2
            text_y = btn_rect.y + (btn_height - text_surface.get_height()) // 2
            self.screen.blit(text_surface, (text_x, text_y))

            # Store button rect for click detection (only if active)
            if is_active:
                self.menu_buttons.append((btn_id, btn_rect))

        # Version/credits at bottom
        version_text = self.font_small.render("v0.1 - MVP", True, (80, 80, 90))
        self.screen.blit(version_text, (scaled(20), WINDOW_HEIGHT - scaled(30)))

        # Scale and blit to window
        self.window.fill((0, 0, 0))
        if self.scale != 1.0:
            scaled_w = int(self.BASE_WIDTH * self.scale)
            scaled_h = int(self.BASE_HEIGHT * self.scale)
            scaled_surface = pygame.transform.smoothscale(self.screen, (scaled_w, scaled_h))
            self.window.blit(scaled_surface, (self.offset_x, self.offset_y))
        else:
            self.window.blit(self.screen, (self.offset_x, self.offset_y))

        pygame.display.flip()

    def get_clicked_menu_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if a menu button was clicked. Returns button_id or None."""
        for btn_id, rect in self.menu_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return btn_id
        return None

    def draw_settings(self, current_resolution: tuple):
        """Draw the settings screen."""
        from .constants import RESOLUTIONS

        self.settings_buttons = []

        # Clear screen with background
        self.screen.fill(COLOR_BG)

        # Title
        title_font = pygame.font.SysFont('arial', scaled(36))
        title = title_font.render("НАСТРОЙКИ", True, (200, 180, 100))
        title_x = (WINDOW_WIDTH - title.get_width()) // 2
        self.screen.blit(title, (title_x, scaled(60)))

        # Resolution section
        section_title = self.font_medium.render("Разрешение экрана:", True, COLOR_TEXT)
        self.screen.blit(section_title, (scaled(100), scaled(140)))

        # Resolution buttons
        btn_width = scaled(200)
        btn_height = scaled(40)
        btn_spacing = scaled(10)
        start_x = scaled(100)
        start_y = scaled(190)

        for i, (w, h) in enumerate(RESOLUTIONS):
            col = i % 3
            row = i // 3
            btn_x = start_x + col * (btn_width + btn_spacing)
            btn_y = start_y + row * (btn_height + btn_spacing)
            btn_rect = pygame.Rect(btn_x, btn_y, btn_width, btn_height)

            # Highlight current resolution
            is_current = (w, h) == current_resolution
            if is_current:
                bg_color = (80, 100, 60)
                border_color = (150, 180, 100)
            else:
                bg_color = (60, 50, 70)
                border_color = (120, 100, 140)

            pygame.draw.rect(self.screen, bg_color, btn_rect)
            pygame.draw.rect(self.screen, border_color, btn_rect, 2)

            # Resolution text
            res_text = f"{w} x {h}"
            text_surface = self.font_medium.render(res_text, True, COLOR_TEXT)
            text_x = btn_rect.x + (btn_width - text_surface.get_width()) // 2
            text_y = btn_rect.y + (btn_height - text_surface.get_height()) // 2
            self.screen.blit(text_surface, (text_x, text_y))

            self.settings_buttons.append((f"res_{w}_{h}", btn_rect))

        # Fullscreen toggle info
        fullscreen_text = self.font_small.render("F11 - переключить полноэкранный режим", True, (150, 150, 160))
        self.screen.blit(fullscreen_text, (scaled(100), scaled(340)))

        # Nickname section
        from .text_input import draw_text_input_field
        nickname_label = self.font_medium.render("Никнейм (для сетевой игры):", True, COLOR_TEXT)
        self.screen.blit(nickname_label, (scaled(100), scaled(400)))

        # Nickname input field
        input_width = scaled(300)
        input_height = scaled(36)
        self.settings_nickname_rect = draw_text_input_field(
            self.screen, self.font_medium, self.settings_nickname_input,
            scaled(100), scaled(440), input_width, input_height,
            bg_color=(50, 50, 60),
            bg_active_color=(60, 60, 70),
            border_color=(100, 100, 110),
            border_active_color=(140, 120, 160),
        )

        # Back button
        back_btn_width = scaled(180)
        back_btn_height = scaled(45)
        back_btn_x = (WINDOW_WIDTH - back_btn_width) // 2
        back_btn_y = WINDOW_HEIGHT - scaled(100)
        back_btn_rect = pygame.Rect(back_btn_x, back_btn_y, back_btn_width, back_btn_height)

        pygame.draw.rect(self.screen, (60, 50, 70), back_btn_rect)
        pygame.draw.rect(self.screen, (120, 100, 140), back_btn_rect, 2)

        back_text = self.font_medium.render("Назад", True, COLOR_TEXT)
        text_x = back_btn_rect.x + (back_btn_width - back_text.get_width()) // 2
        text_y = back_btn_rect.y + (back_btn_height - back_text.get_height()) // 2
        self.screen.blit(back_text, (text_x, text_y))

        self.settings_buttons.append(("back", back_btn_rect))

        # Scale and blit to window
        self.window.fill((0, 0, 0))
        if self.scale != 1.0:
            scaled_w = int(self.BASE_WIDTH * self.scale)
            scaled_h = int(self.BASE_HEIGHT * self.scale)
            scaled_surface = pygame.transform.smoothscale(self.screen, (scaled_w, scaled_h))
            self.window.blit(scaled_surface, (self.offset_x, self.offset_y))
        else:
            self.window.blit(self.screen, (self.offset_x, self.offset_y))

        pygame.display.flip()

    def get_clicked_settings_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if a settings button was clicked. Returns button_id or None."""
        if not hasattr(self, 'settings_buttons'):
            return None
        for btn_id, rect in self.settings_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return btn_id
        return None

    def draw_pause_menu(self, current_resolution: tuple, is_network_game: bool = False):
        """Draw in-game pause menu overlay."""
        from .constants import RESOLUTIONS

        self.pause_buttons = []

        # Semi-transparent overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill(UILayout.POPUP_PAUSE_BG)
        self.screen.blit(overlay, (0, 0))

        # Menu panel
        panel_width = scaled(400)
        panel_height = scaled(400)
        panel_x = (WINDOW_WIDTH - panel_width) // 2
        panel_y = (WINDOW_HEIGHT - panel_height) // 2
        panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)

        pygame.draw.rect(self.screen, (40, 35, 50), panel_rect)
        pygame.draw.rect(self.screen, UILayout.POPUP_PAUSE_BORDER, panel_rect, 3)

        # Title
        title_font = pygame.font.SysFont('arial', scaled(28))
        title = title_font.render("ПАУЗА", True, (200, 180, 100))
        title_x = panel_x + (panel_width - title.get_width()) // 2
        self.screen.blit(title, (title_x, panel_y + scaled(20)))

        # Resolution section
        section_y = panel_y + scaled(65)
        section_title = self.font_small.render("Разрешение:", True, COLOR_TEXT)
        self.screen.blit(section_title, (panel_x + scaled(20), section_y))

        # Resolution buttons (2 per row)
        btn_width = scaled(110)
        btn_height = scaled(32)
        btn_spacing = scaled(8)
        start_x = panel_x + scaled(20)
        start_y = section_y + scaled(25)

        for i, (w, h) in enumerate(RESOLUTIONS):
            col = i % 3
            row = i // 3
            btn_x = start_x + col * (btn_width + btn_spacing)
            btn_y = start_y + row * (btn_height + btn_spacing)
            btn_rect = pygame.Rect(btn_x, btn_y, btn_width, btn_height)

            is_current = (w, h) == current_resolution
            if is_current:
                bg_color = (80, 100, 60)
                border_color = (150, 180, 100)
            else:
                bg_color = (60, 50, 70)
                border_color = (100, 80, 120)

            pygame.draw.rect(self.screen, bg_color, btn_rect)
            pygame.draw.rect(self.screen, border_color, btn_rect, 2)

            res_text = f"{w}x{h}"
            text_surface = self.font_small.render(res_text, True, COLOR_TEXT)
            text_x = btn_rect.x + (btn_width - text_surface.get_width()) // 2
            text_y = btn_rect.y + (btn_height - text_surface.get_height()) // 2
            self.screen.blit(text_surface, (text_x, text_y))

            self.pause_buttons.append((f"res_{w}_{h}", btn_rect))

        # Action buttons
        action_btn_width = scaled(180)
        action_btn_height = scaled(40)
        action_y = panel_y + panel_height - scaled(160)

        # Concede button (only in network games)
        if is_network_game:
            concede_rect = pygame.Rect(
                panel_x + (panel_width - action_btn_width) // 2,
                action_y,
                action_btn_width,
                action_btn_height
            )
            pygame.draw.rect(self.screen, (120, 50, 50), concede_rect)
            pygame.draw.rect(self.screen, (180, 80, 80), concede_rect, 2)

            concede_text = self.font_medium.render("Сдаться", True, COLOR_TEXT)
            text_x = concede_rect.x + (action_btn_width - concede_text.get_width()) // 2
            text_y = concede_rect.y + (action_btn_height - concede_text.get_height()) // 2
            self.screen.blit(concede_text, (text_x, text_y))

            self.pause_buttons.append(("concede", concede_rect))
            action_y += action_btn_height + scaled(10)
        else:
            # Exit to menu button (for local games)
            exit_rect = pygame.Rect(
                panel_x + (panel_width - action_btn_width) // 2,
                action_y,
                action_btn_width,
                action_btn_height
            )
            pygame.draw.rect(self.screen, (120, 50, 50), exit_rect)
            pygame.draw.rect(self.screen, (180, 80, 80), exit_rect, 2)

            exit_text = self.font_medium.render("Выход в меню", True, COLOR_TEXT)
            text_x = exit_rect.x + (action_btn_width - exit_text.get_width()) // 2
            text_y = exit_rect.y + (action_btn_height - exit_text.get_height()) // 2
            self.screen.blit(exit_text, (text_x, text_y))

            self.pause_buttons.append(("exit", exit_rect))
            action_y += action_btn_height + scaled(10)

        # Resume button
        resume_rect = pygame.Rect(
            panel_x + (panel_width - action_btn_width) // 2,
            action_y,
            action_btn_width,
            action_btn_height
        )
        pygame.draw.rect(self.screen, (60, 80, 60), resume_rect)
        pygame.draw.rect(self.screen, (100, 150, 100), resume_rect, 2)

        resume_text = self.font_medium.render("Продолжить", True, COLOR_TEXT)
        text_x = resume_rect.x + (action_btn_width - resume_text.get_width()) // 2
        text_y = resume_rect.y + (action_btn_height - resume_text.get_height()) // 2
        self.screen.blit(resume_text, (text_x, text_y))

        self.pause_buttons.append(("resume", resume_rect))

        # ESC hint at bottom
        hint_text = self.font_small.render("ESC - продолжить игру", True, (120, 120, 130))
        hint_x = panel_x + (panel_width - hint_text.get_width()) // 2
        self.screen.blit(hint_text, (hint_x, panel_y + panel_height - scaled(30)))

    def get_clicked_pause_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if a pause menu button was clicked. Returns button_id or None."""
        if not hasattr(self, 'pause_buttons'):
            return None
        for btn_id, rect in self.pause_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return btn_id
        return None

    def finalize_frame(self):
        """Scale and display the current frame.

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

        pygame.display.flip()
