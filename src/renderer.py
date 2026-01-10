"""Pygame rendering for the game."""
import pygame
import os
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict

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

        # Card image cache
        self.card_images: Dict[str, pygame.Surface] = {}
        self.card_images_full: Dict[str, pygame.Surface] = {}
        self._load_card_images()

        # Popup state
        self.popup_card: Optional[Card] = None

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

        # Priority phase animation
        self.priority_glow_timer: float = 0.0  # Cycles 0-2π for sine wave

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
                    art_top = int(img_h * 0.14)       # ~98px on 700h - skip card name
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
        # Flip Y so player 1 is at bottom
        screen_row = BOARD_ROWS - 1 - row
        x = BOARD_OFFSET_X + col * CELL_SIZE
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
        col = (screen_x - BOARD_OFFSET_X) // CELL_SIZE
        screen_row = (screen_y - BOARD_OFFSET_Y) // CELL_SIZE

        if not (0 <= col < BOARD_COLS and 0 <= screen_row < BOARD_ROWS):
            return None

        # Flip Y back
        row = BOARD_ROWS - 1 - screen_row
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
        # Counter shot target mode - highlight valid targets (board only)
        if game.awaiting_counter_shot and game.interaction:
            for pos in game.interaction.valid_positions:
                if self._is_flying_pos(pos):
                    continue  # Skip flying - handled in side panels
                x, y = self.pos_to_screen(pos)
                self.screen.blit(self.counter_shot_highlight, (x, y))
            return

        # Movement shot target mode - highlight valid targets (board only)
        if game.awaiting_movement_shot and game.interaction:
            for pos in game.interaction.valid_positions:
                if self._is_flying_pos(pos):
                    continue
                x, y = self.pos_to_screen(pos)
                self.screen.blit(self.counter_shot_highlight, (x, y))
            return

        # Valhalla target mode - highlight valid targets (board only)
        if game.awaiting_valhalla and game.interaction:
            for pos in game.interaction.valid_positions:
                if self._is_flying_pos(pos):
                    continue
                x, y = self.pos_to_screen(pos)
                self.screen.blit(self.valhalla_highlight, (x, y))
            return

        # Defender choice mode - highlight valid defenders (board only)
        if game.awaiting_defender and game.interaction:
            # Highlight original target in red
            target = game.interaction.target
            if target and target.position is not None and not self._is_flying_pos(target.position):
                x, y = self.pos_to_screen(target.position)
                self.screen.blit(self.attack_highlight, (x, y))

            # Highlight valid defenders in cyan
            for defender in game.interaction.valid_cards:
                if defender.position is not None and not self._is_flying_pos(defender.position):
                    x, y = self.pos_to_screen(defender.position)
                    self.screen.blit(self.defender_highlight, (x, y))
            return

        # Ability targeting mode - highlight valid targets (board only)
        if game.awaiting_ability_target and game.interaction:
            for pos in game.interaction.valid_positions:
                if self._is_flying_pos(pos):
                    continue
                x, y = self.pos_to_screen(pos)
                self.screen.blit(self.ability_highlight, (x, y))
            return

        # Movement highlights (board only)
        for pos in game.valid_moves:
            if self._is_flying_pos(pos):
                continue
            x, y = self.pos_to_screen(pos)
            self.screen.blit(self.move_highlight, (x, y))

        # Attack highlights (board only)
        for pos in game.valid_attacks:
            if self._is_flying_pos(pos):
                continue
            x, y = self.pos_to_screen(pos)
            self.screen.blit(self.attack_highlight, (x, y))

    def draw_card(self, card: Card, x: int, y: int, selected: bool = False, glow_intensity: float = 0.0, game: 'Game' = None):
        """Draw a single card with image.

        Args:
            card: Card to draw
            x, y: Position
            selected: Whether card is selected
            glow_intensity: 0-1 for pulsing glow effect (instant abilities)
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
            glow_color = (255, 220, 100)  # Golden glow
            glow_alpha = int(100 * glow_intensity)
            glow_size = int(6 + 4 * glow_intensity)  # Pulsing size

            # Draw multiple glow layers for soft effect
            for i in range(glow_size, 0, -2):
                glow_rect = card_rect.inflate(i * 2, i * 2)
                glow_surface = pygame.Surface((glow_rect.width, glow_rect.height), pygame.SRCALPHA)
                layer_alpha = int(glow_alpha * (glow_size - i + 1) / glow_size)
                pygame.draw.rect(glow_surface, (*glow_color, layer_alpha), glow_surface.get_rect(), border_radius=3)
                self.screen.blit(glow_surface, glow_rect.topleft)

        # Player border color
        if card.player == 1:
            border_color = COLOR_PLAYER1
        else:
            border_color = COLOR_PLAYER2

        # Draw card background/border
        pygame.draw.rect(self.screen, border_color, card_rect)

        # Name bar dimensions
        name_bar_height = scaled(UILayout.NAME_BAR_HEIGHT)
        name_bar_y = card_rect.y + CARD_HEIGHT - name_bar_height

        # Determine name bar colors based on current player
        current_player = game.current_player if game else 1
        if card.player == current_player:
            name_bar_color = (180, 160, 60)  # Yellow/gold for allied
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

        # Player border color
        if card.player == 1:
            border_color = COLOR_PLAYER1
        else:
            border_color = COLOR_PLAYER2

        # Draw card background/border
        pygame.draw.rect(self.screen, border_color, card_rect)

        # Name bar dimensions (proportionally smaller)
        name_bar_height = max(12, size // 7)

        # Current player detection for name bar color
        current_player = game.current_player if game else 1
        if card.player == current_player:
            name_bar_color = (180, 160, 60)  # Yellow/gold for allied
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
        glowing_card_ids = set()
        if game.awaiting_priority:
            glow_intensity = 0.5 + 0.5 * math.sin(self.priority_glow_timer)
            # Get cards with legal instants for current priority player
            for card, ability in game.get_legal_instants(game.priority_player):
                glowing_card_ids.add(card.id)
        elif game.has_forced_attack:
            glow_intensity = 0.5 + 0.5 * math.sin(self.priority_glow_timer)
            # Highlight cards that must attack
            for card_id, (card, targets) in game.forced_attackers.items():
                glowing_card_ids.add(card_id)

        # Draw ground cards
        for pos, card in enumerate(game.board.cells):
            if card is not None:
                x, y = self.pos_to_screen(pos)
                selected = (game.selected_card == card)
                card_glow = glow_intensity if card.id in glowing_card_ids else 0.0
                self.draw_card(card, x, y, selected, card_glow, game)

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
        button_rect = self.get_end_turn_button_rect()
        pygame.draw.rect(self.screen, player_color, button_rect)
        pygame.draw.rect(self.screen, COLOR_TEXT, button_rect, 2)

        button_text = "Конец хода"
        button_surface = self.font_medium.render(button_text, True, COLOR_TEXT)
        text_x = button_rect.x + (button_rect.width - button_surface.get_width()) // 2
        text_y = button_rect.y + (button_rect.height - button_surface.get_height()) // 2
        self.screen.blit(button_surface, (text_x, text_y))

        # Counter shot selection prompt
        if game.awaiting_counter_shot:
            self.draw_counter_shot_prompt(game)

        # Movement shot selection prompt
        if game.awaiting_movement_shot:
            self.draw_movement_shot_prompt(game)

        # Heal confirmation prompt
        if game.awaiting_heal_confirm:
            self.draw_heal_confirm_prompt(game)

        # Stench choice prompt
        if game.awaiting_stench_choice:
            self.draw_stench_choice_prompt(game)

        # Exchange choice prompt
        if game.awaiting_exchange_choice:
            self.draw_exchange_prompt(game)

        # Valhalla selection prompt
        if game.awaiting_valhalla:
            self.draw_valhalla_prompt(game)

        # Defender choice prompt
        if game.awaiting_defender and game.interaction:
            self.draw_defender_prompt(game)

        # Selected card info
        if game.selected_card and not game.awaiting_defender:
            self.draw_card_info(game.selected_card, game)

        # Message log
        self.draw_messages(game)

        # Skip button (only show when something can be skipped)
        if game.awaiting_defender or game.awaiting_movement_shot:
            self.draw_skip_button(game)

        # Dice panel (shows pending or last combat dice)
        if (game.awaiting_priority and game.pending_dice_roll) or (game.last_combat and not game.awaiting_defender):
            self.draw_dice_panel(game)

    def draw_counter_shot_prompt(self, game: Game):
        """Draw the counter shot target selection prompt (draggable)."""
        if not game.awaiting_counter_shot or not game.interaction:
            return

        attacker = game.interaction.actor

        config = PopupConfig(
            popup_id='counter_shot',
            width=scaled(400),
            height=scaled(60),
            bg_color=(80, 50, 0, 230),
            border_color=(255, 140, 50),
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

        shooter = game.interaction.actor

        config = PopupConfig(
            popup_id='movement_shot',
            width=scaled(450),
            height=scaled(95),
            bg_color=(80, 50, 0, 230),
            border_color=(255, 140, 50),
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

        attacker = game.interaction.actor
        heal_amount = game.interaction.amount

        config = PopupConfig(
            popup_id='heal_confirm',
            width=scaled(350),
            height=scaled(90),
            bg_color=(20, 80, 40, 230),
            border_color=(80, 200, 100),
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

        target = game.interaction.target
        damage = game.interaction.amount

        config = PopupConfig(
            popup_id='stench_choice',
            width=scaled(380),
            height=scaled(100),
            bg_color=(60, 40, 20, 230),
            border_color=(180, 120, 60),
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

        attacker = game.interaction.actor
        defender = game.interaction.target
        ctx = game.interaction.context
        attacker_advantage = ctx.get('attacker_advantage', True)
        roll_diff = ctx.get('roll_diff', 0)

        # Calculate damage values
        atk = attacker.get_effective_attack()
        def_atk = defender.get_effective_attack()

        if attacker_advantage:
            # Attacker chooses - roll_diff is 2 or 4
            if roll_diff == 4:
                atk_current_tier = 2  # Strong
                atk_reduced_tier = 1  # Medium
            else:  # roll_diff == 2
                atk_current_tier = 1  # Medium
                atk_reduced_tier = 0  # Weak

            current_atk_dmg = atk[atk_current_tier] + game._get_positional_damage_modifier(attacker, atk_current_tier)
            reduced_atk_dmg = atk[atk_reduced_tier] + game._get_positional_damage_modifier(attacker, atk_reduced_tier)
            counter_dmg = def_atk[0]  # Weak counter

            title = "ОБМЕН УДАРАМИ"
            full_btn_text = f"{current_atk_dmg} / -{counter_dmg}"
            reduce_btn_text = f"{reduced_atk_dmg} / 0"
        else:
            # Defender chooses - roll_diff is -4
            atk_dmg = atk[0]  # Weak attack
            def_current_tier = 1  # Medium counter
            def_reduced_tier = 0  # Weak counter

            current_def_dmg = def_atk[def_current_tier] + game._get_positional_damage_modifier(defender, def_current_tier)
            reduced_def_dmg = def_atk[def_reduced_tier] + game._get_positional_damage_modifier(defender, def_reduced_tier)

            title = "ОБМЕН УДАРАМИ"
            full_btn_text = f"-{atk_dmg} / {current_def_dmg}"
            reduce_btn_text = f"0 / {reduced_def_dmg}"

        config = PopupConfig(
            popup_id='exchange',
            width=scaled(300),
            height=scaled(90),
            bg_color=(80, 60, 20, 230),
            border_color=(255, 180, 80),
            title=title,
            title_color=(255, 220, 150),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Buttons with damage values
        btn_width, btn_height, gap = scaled(120), scaled(32), scaled(20)
        btn_y = content_y + scaled(8)

        full_rect = self.draw_popup_button(
            x + config.width // 2 - btn_width - gap // 2, btn_y,
            btn_width, btn_height, full_btn_text, (140, 80, 40), (220, 140, 80))

        reduce_rect = self.draw_popup_button(
            x + config.width // 2 + gap // 2, btn_y,
            btn_width, btn_height, reduce_btn_text, (40, 100, 60), (80, 180, 100))

        self.exchange_buttons = [('full', full_rect), ('reduce', reduce_rect)]

    def draw_valhalla_prompt(self, game: Game):
        """Draw the Valhalla target selection prompt (draggable)."""
        if not game.interaction:
            return

        dead_card = game.interaction.actor
        ability = game.interaction.context.get('ability')
        if not ability:
            return

        config = PopupConfig(
            popup_id='valhalla',
            width=scaled(450),
            height=scaled(80),
            bg_color=(80, 60, 0, 230),
            border_color=(255, 200, 100),
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
        defending_player = interaction.target.player

        config = PopupConfig(
            popup_id='defender',
            width=scaled(500),
            height=scaled(100),
            bg_color=(0, 80, 80, 230),
            border_color=(0, 200, 200),
            title=f"ИГРОК {defending_player}: ВЫБОР ЗАЩИТНИКА",
        )

        x, y, content_y = self.draw_popup_base(config)

        # Attack info
        info = f"{interaction.actor.name} атакует {interaction.target.name}"
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
        if card.temp_dice_bonus > 0:
            statuses.append(f"ОвА +{card.temp_dice_bonus}")
        # Defender buff (lasts until end of owner's next turn)
        if card.defender_buff_attack > 0:
            statuses.append(f"+{card.defender_buff_attack} защ.бафф")
        if card.defender_buff_dice > 0:
            statuses.append(f"ОвА +{card.defender_buff_dice} защ.")
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

        # Pull status_text from abilities (passive/triggered only)
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.status_text:
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
        has_attacks = len(game.valid_attacks) > 0 if game.selected_card == card else False
        in_attack_mode = game.attack_mode and game.selected_card == card

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
            attacker = dice['attacker']
            is_ranged = dice.get('type') == 'ranged'
            defender = dice.get('defender') if not is_ranged else None
            target = dice.get('target') if is_ranged else None

            # Get base rolls, bonuses (ОвА/ОвЗ), and instant modifiers
            atk_roll = dice['atk_roll']
            atk_bonus = dice.get('atk_bonus', 0)
            atk_mod = dice.get('atk_modifier', 0)

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

            if is_ranged and target:
                # For ranged attacks, show " -> Target" instead of "vs defender[roll]"
                arrow_surface = self.font_small.render(" → ", True, COLOR_TEXT)
                self.screen.blit(arrow_surface, (x, panel_y + 8))
                x += arrow_surface.get_width()

                target_name = target.name[:8]
                target_color = COLOR_PLAYER1 if target.player == 1 else COLOR_PLAYER2
                target_surface = self.font_small.render(target_name, True, target_color)
                self.screen.blit(target_surface, (x, panel_y + 8))
            elif defender:
                # For combat, show "vs defender[roll]"
                def_roll = dice['def_roll']
                def_bonus = dice.get('def_bonus', 0)
                def_mod = dice.get('def_modifier', 0)
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

        # Auto-expand flying zones if they have flyers (and nothing else expanded for that player)
        has_p1_flyers = any(c is not None for c in game.board.flying_p1)
        has_p2_flyers = any(c is not None for c in game.board.flying_p2)
        if has_p1_flyers and self.expanded_panel_p1 is None:
            self.expanded_panel_p1 = 'flyers'
        if has_p2_flyers and self.expanded_panel_p2 is None:
            self.expanded_panel_p2 = 'flyers'

        panel_width = scaled(UILayout.SIDE_PANEL_WIDTH)
        tab_height = scaled(UILayout.SIDE_PANEL_TAB_HEIGHT)
        spacing = scaled(UILayout.SIDE_PANEL_SPACING)
        expanded_height = scaled(UILayout.SIDE_PANEL_EXPANDED_HEIGHT)
        card_size = scaled(UILayout.SIDE_PANEL_CARD_SIZE)
        card_spacing = scaled(UILayout.SIDE_PANEL_CARD_SPACING)

        self.side_panel_tab_rects = {}

        # ========== P2 ZONES (LEFT side) ==========
        p2_panel_x = scaled(UILayout.SIDE_PANEL_P2_X)
        p2_y = scaled(UILayout.SIDE_PANEL_P2_Y)

        # P2 Flyers tab
        p2_flyers_expanded = self.is_panel_expanded('p2_flyers')
        p2_flyers_rect = pygame.Rect(p2_panel_x, p2_y, panel_width, tab_height)
        self.side_panel_tab_rects['p2_flyers'] = p2_flyers_rect

        tab_color = (80, 50, 50) if p2_flyers_expanded else (50, 35, 35)
        pygame.draw.rect(self.screen, tab_color, p2_flyers_rect)
        pygame.draw.rect(self.screen, COLOR_PLAYER2, p2_flyers_rect, 2)

        flyer_count = sum(1 for c in game.board.flying_p2 if c is not None)
        label = self.font_small.render(f"Летающие П2 ({flyer_count})", True, COLOR_PLAYER2)
        self.screen.blit(label, (p2_panel_x + 5, p2_y + 5))

        # Expanded content for P2 flyers
        if p2_flyers_expanded:
            content_y = p2_y + tab_height + spacing
            content_rect = pygame.Rect(p2_panel_x, content_y, panel_width, expanded_height)
            pygame.draw.rect(self.screen, (50, 35, 35), content_rect)
            pygame.draw.rect(self.screen, COLOR_PLAYER2, content_rect, 1)

            # Get flying cards
            flyers = [c for c in game.board.flying_p2 if c is not None]
            scroll = self.side_panel_scroll.get('p2_flyers', 0)
            self._draw_panel_cards(flyers, p2_panel_x, content_y, panel_width, expanded_height,
                                   card_size, card_spacing, scroll, game, 'p2_flyers')

        # P2 Graveyard tab
        p2_grave_y = p2_y + tab_height + spacing
        if p2_flyers_expanded:
            p2_grave_y += expanded_height + spacing
        p2_grave_expanded = self.is_panel_expanded('p2_grave')
        p2_grave_rect = pygame.Rect(p2_panel_x, p2_grave_y, panel_width, tab_height)
        self.side_panel_tab_rects['p2_grave'] = p2_grave_rect

        tab_color = (80, 50, 50) if p2_grave_expanded else (50, 35, 35)
        pygame.draw.rect(self.screen, tab_color, p2_grave_rect)
        pygame.draw.rect(self.screen, COLOR_PLAYER2, p2_grave_rect, 2)

        grave_count = len(game.board.graveyard_p2)
        label = self.font_small.render(f"Кладбище П2 ({grave_count})", True, COLOR_PLAYER2)
        self.screen.blit(label, (p2_panel_x + 5, p2_grave_y + 5))

        # Expanded content for P2 graveyard
        if p2_grave_expanded:
            content_y = p2_grave_y + tab_height + spacing
            content_rect = pygame.Rect(p2_panel_x, content_y, panel_width, expanded_height)
            pygame.draw.rect(self.screen, (50, 35, 35), content_rect)
            pygame.draw.rect(self.screen, COLOR_PLAYER2, content_rect, 1)

            # Get graveyard cards (most recent first)
            grave_cards = list(reversed(game.board.graveyard_p2))
            scroll = self.side_panel_scroll.get('p2_grave', 0)
            self._draw_panel_cards(grave_cards, p2_panel_x, content_y, panel_width, expanded_height,
                                   card_size, card_spacing, scroll, game, 'p2_grave')

        # ========== P1 ZONES (RIGHT side) ==========
        p1_panel_x = scaled(UILayout.SIDE_PANEL_P1_X)
        p1_y = scaled(UILayout.SIDE_PANEL_P1_Y)

        # P1 Flyers tab
        p1_flyers_expanded = self.is_panel_expanded('p1_flyers')
        p1_flyers_rect = pygame.Rect(p1_panel_x, p1_y, panel_width, tab_height)
        self.side_panel_tab_rects['p1_flyers'] = p1_flyers_rect

        tab_color = (50, 60, 80) if p1_flyers_expanded else (30, 40, 50)
        pygame.draw.rect(self.screen, tab_color, p1_flyers_rect)
        pygame.draw.rect(self.screen, COLOR_PLAYER1, p1_flyers_rect, 2)

        flyer_count = sum(1 for c in game.board.flying_p1 if c is not None)
        label = self.font_small.render(f"Летающие П1 ({flyer_count})", True, COLOR_PLAYER1)
        self.screen.blit(label, (p1_panel_x + 5, p1_y + 5))

        # Expanded content for P1 flyers
        if p1_flyers_expanded:
            content_y = p1_y + tab_height + spacing
            content_rect = pygame.Rect(p1_panel_x, content_y, panel_width, expanded_height)
            pygame.draw.rect(self.screen, (30, 40, 50), content_rect)
            pygame.draw.rect(self.screen, COLOR_PLAYER1, content_rect, 1)

            flyers = [c for c in game.board.flying_p1 if c is not None]
            scroll = self.side_panel_scroll.get('p1_flyers', 0)
            self._draw_panel_cards(flyers, p1_panel_x, content_y, panel_width, expanded_height,
                                   card_size, card_spacing, scroll, game, 'p1_flyers')

        # P1 Graveyard tab
        p1_grave_y = p1_y + tab_height + spacing
        if p1_flyers_expanded:
            p1_grave_y += expanded_height + spacing
        p1_grave_expanded = self.is_panel_expanded('p1_grave')
        p1_grave_rect = pygame.Rect(p1_panel_x, p1_grave_y, panel_width, tab_height)
        self.side_panel_tab_rects['p1_grave'] = p1_grave_rect

        tab_color = (50, 60, 80) if p1_grave_expanded else (30, 40, 50)
        pygame.draw.rect(self.screen, tab_color, p1_grave_rect)
        pygame.draw.rect(self.screen, COLOR_PLAYER1, p1_grave_rect, 2)

        grave_count = len(game.board.graveyard_p1)
        label = self.font_small.render(f"Кладбище П1 ({grave_count})", True, COLOR_PLAYER1)
        self.screen.blit(label, (p1_panel_x + 5, p1_grave_y + 5))

        # Expanded content for P1 graveyard
        if p1_grave_expanded:
            content_y = p1_grave_y + tab_height + spacing
            content_rect = pygame.Rect(p1_panel_x, content_y, panel_width, expanded_height)
            pygame.draw.rect(self.screen, (30, 40, 50), content_rect)
            pygame.draw.rect(self.screen, COLOR_PLAYER1, content_rect, 1)

            grave_cards = list(reversed(game.board.graveyard_p1))
            scroll = self.side_panel_scroll.get('p1_grave', 0)
            self._draw_panel_cards(grave_cards, p1_panel_x, content_y, panel_width, expanded_height,
                                   card_size, card_spacing, scroll, game, 'p1_grave')

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
        highlight_type = None  # 'attack', 'move', 'ability', etc.
        if is_flyers and game:
            # Check various highlight modes
            if game.awaiting_counter_shot and game.interaction:
                highlighted_positions = set(game.interaction.valid_positions)
                highlight_type = 'counter_shot'
            elif game.awaiting_movement_shot and game.interaction:
                highlighted_positions = set(game.interaction.valid_positions)
                highlight_type = 'counter_shot'
            elif game.awaiting_ability_target and game.interaction:
                highlighted_positions = set(game.interaction.valid_positions)
                highlight_type = 'ability'
            elif game.awaiting_valhalla and game.interaction:
                highlighted_positions = set(game.interaction.valid_positions)
                highlight_type = 'valhalla'
            else:
                # Normal mode - check valid_attacks
                highlighted_positions = set(game.valid_attacks)
                highlight_type = 'attack'

        for i, card in enumerate(cards):
            card_y = content_y + 5 + i * (card_size + card_spacing) - scroll
            # Only draw if visible
            if card_y + card_size > content_y and card_y < content_y + panel_height:
                self.draw_card_thumbnail(card, card_x, card_y, card_size, game, is_graveyard)

                # Draw highlight as colored border around card (not covering art)
                if is_flyers and card.position in highlighted_positions:
                    border_width = 4
                    if highlight_type == 'attack':
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

        # Check P1 flyers
        if self.is_panel_expanded('p1_flyers'):
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

        # Check P2 flyers
        if self.is_panel_expanded('p2_flyers'):
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

    def draw(self, game: Game, dt: float = 0.016):
        """Main draw function."""
        import math

        # Update priority glow animation timer (also used for forced attack highlight)
        if game.awaiting_priority or game.has_forced_attack:
            self.priority_glow_timer += dt * 4  # Speed of pulsing
            if self.priority_glow_timer > 2 * math.pi:
                self.priority_glow_timer -= 2 * math.pi
        else:
            self.priority_glow_timer = 0.0

        # Clear render surface
        self.screen.fill(COLOR_BG)

        # Draw everything to render surface
        self.draw_board(game)
        self.draw_side_panels(game)
        self.draw_highlights(game)  # Board highlights only (flying handled in side panels)
        self.draw_cards(game)
        self.draw_ui(game)
        self.draw_hand(game)

        # Draw priority phase UI (info box, pass button, dice popup)
        if game.awaiting_priority:
            self.draw_priority_info(game)
            self.draw_pass_button(game)
            # Draw dice popup if open
            if self.dice_popup_open:
                self.draw_dice_popup(game)
        else:
            # Close dice popup if priority ended
            if self.dice_popup_open:
                self.close_dice_popup()

        # Draw counter selection popup
        if game.awaiting_counter_selection:
            self.draw_counter_popup(game)

        # Update and draw floating texts
        self.update_floating_texts(dt)
        self.draw_floating_texts()

        # Update and draw interaction arrows
        self.update_arrows(dt)
        self.draw_arrows()

        self.draw_popup()

        # Scale and blit to window
        self.window.fill((0, 0, 0))  # Black letterbox
        if self.scale != 1.0:
            scaled_w = int(self.BASE_WIDTH * self.scale)
            scaled_h = int(self.BASE_HEIGHT * self.scale)
            scaled_surface = pygame.transform.smoothscale(self.screen, (scaled_w, scaled_h))
            self.window.blit(scaled_surface, (self.offset_x, self.offset_y))
        else:
            self.window.blit(self.screen, (self.offset_x, self.offset_y))

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

    def draw_dice_popup(self, game: Game):
        """Draw dice modification popup when an instant card is selected during priority."""
        if not self.dice_popup_open or not game.pending_dice_roll:
            return

        dice = game.pending_dice_roll
        attacker = dice['attacker']
        # For ranged attacks, there's no defender - use 'target' key instead
        is_ranged = dice.get('type') == 'ranged'
        defender = dice.get('defender') if not is_ranged else None
        target = dice.get('target') if is_ranged else None

        # Popup dimensions
        popup_width = 420
        popup_height = 160 if is_ranged else 220  # Smaller popup for ranged (no defender row)
        popup_x = (WINDOW_WIDTH - popup_width) // 2
        popup_y = 100

        # Draw popup background
        bg_surface = pygame.Surface((popup_width, popup_height), pygame.SRCALPHA)
        bg_surface.fill((40, 35, 60, 240))
        self.screen.blit(bg_surface, (popup_x, popup_y))
        pygame.draw.rect(self.screen, (100, 80, 140), (popup_x, popup_y, popup_width, popup_height), 3)

        # Title - different text for ranged attacks
        if is_ranged:
            ranged_type = dice.get('ranged_type', 'shot')
            title_text = "Удача - изменить бросок (метание)" if ranged_type == "throw" else "Удача - изменить бросок (выстрел)"
        else:
            title_text = "Удача - изменить бросок"
        title = self.font_medium.render(title_text, True, (255, 220, 100))
        self.screen.blit(title, (popup_x + (popup_width - title.get_width()) // 2, popup_y + 10))

        # Clear dice option buttons
        self.dice_option_buttons = []

        y_offset = popup_y + 50

        # Attacker dice row
        atk_color = COLOR_PLAYER1 if attacker.player == 1 else COLOR_PLAYER2
        atk_mod = dice.get('atk_modifier', 0)  # Luck modifier
        atk_bonus = dice.get('atk_bonus', 0)   # Ability bonus (OvA)
        atk_roll = dice['atk_roll']
        atk_total = atk_roll + atk_mod + atk_bonus

        # Show name and original roll
        atk_name_surface = self.font_medium.render(f"{attacker.name}:", True, atk_color)
        self.screen.blit(atk_name_surface, (popup_x + 15, y_offset))

        # Show dice value with bonus and luck modification
        dice_x = popup_x + 140
        # Format: [roll+bonus] or [roll+bonus] -> [modified] if luck used
        bonus_str = f"+{atk_bonus}" if atk_bonus > 0 else ""

        if atk_mod != 0:
            # Show: [roll+bonus] -> [total] with color
            orig_text = f"[{atk_roll}{bonus_str}]"
            orig_surface = self.font_medium.render(orig_text, True, (150, 150, 150))
            self.screen.blit(orig_surface, (dice_x, y_offset))

            arrow_surface = self.font_medium.render(" → ", True, COLOR_TEXT)
            self.screen.blit(arrow_surface, (dice_x + orig_surface.get_width(), y_offset))

            mod_color = (100, 255, 100) if atk_mod > 0 else (255, 100, 100)
            mod_text = f"[{atk_total}]"
            mod_surface = self.font_medium.render(mod_text, True, mod_color)
            self.screen.blit(mod_surface, (dice_x + orig_surface.get_width() + arrow_surface.get_width(), y_offset))
        else:
            # Show roll with bonus: [roll+bonus=total] or just [roll] if no bonus
            if atk_bonus > 0:
                dice_text = f"[{atk_roll}+{atk_bonus}={atk_roll + atk_bonus}]"
            else:
                dice_text = f"[{atk_roll}]"
            dice_surface = self.font_medium.render(dice_text, True, COLOR_TEXT)
            self.screen.blit(dice_surface, (dice_x, y_offset))

        # Attacker dice buttons
        btn_x = popup_x + 260
        for opt_id, label, color in [('atk_plus1', '+1', (80, 140, 80)),
                                      ('atk_minus1', '-1', (140, 80, 80)),
                                      ('atk_reroll', 'Re', (80, 80, 140))]:
            btn_rect = pygame.Rect(btn_x, y_offset - 3, 48, 26)
            pygame.draw.rect(self.screen, color, btn_rect)
            pygame.draw.rect(self.screen, COLOR_TEXT, btn_rect, 1)
            btn_text = self.font_small.render(label, True, COLOR_TEXT)
            self.screen.blit(btn_text, (btn_rect.x + (48 - btn_text.get_width()) // 2,
                                        btn_rect.y + (26 - btn_text.get_height()) // 2))
            self.dice_option_buttons.append((opt_id, btn_rect))
            btn_x += 52

        y_offset += 55

        # Defender dice row (only for combat, not ranged attacks, and only if defender rolled)
        # def_roll is 0 when attacking a tapped creature (no counter-attack)
        if not is_ranged and defender and dice.get('def_roll', 0) > 0:
            def_color = COLOR_PLAYER1 if defender.player == 1 else COLOR_PLAYER2
            def_mod = dice.get('def_modifier', 0)  # Luck modifier
            def_bonus = dice.get('def_bonus', 0)   # Ability bonus (OvZ)
            def_roll = dice['def_roll']
            def_total = def_roll + def_mod + def_bonus

            # Show name and original roll
            def_name_surface = self.font_medium.render(f"{defender.name}:", True, def_color)
            self.screen.blit(def_name_surface, (popup_x + 15, y_offset))

            # Show dice value with bonus and luck modification
            dice_x = popup_x + 140
            bonus_str = f"+{def_bonus}" if def_bonus > 0 else ""

            if def_mod != 0:
                # Show: [roll+bonus] -> [total] with color
                orig_text = f"[{def_roll}{bonus_str}]"
                orig_surface = self.font_medium.render(orig_text, True, (150, 150, 150))
                self.screen.blit(orig_surface, (dice_x, y_offset))

                arrow_surface = self.font_medium.render(" → ", True, COLOR_TEXT)
                self.screen.blit(arrow_surface, (dice_x + orig_surface.get_width(), y_offset))

                mod_color = (100, 255, 100) if def_mod > 0 else (255, 100, 100)
                mod_text = f"[{def_total}]"
                mod_surface = self.font_medium.render(mod_text, True, mod_color)
                self.screen.blit(mod_surface, (dice_x + orig_surface.get_width() + arrow_surface.get_width(), y_offset))
            else:
                # Show roll with bonus: [roll+bonus=total] or just [roll] if no bonus
                if def_bonus > 0:
                    dice_text = f"[{def_roll}+{def_bonus}={def_roll + def_bonus}]"
                else:
                    dice_text = f"[{def_roll}]"
                dice_surface = self.font_medium.render(dice_text, True, COLOR_TEXT)
                self.screen.blit(dice_surface, (dice_x, y_offset))

            # Defender dice buttons
            btn_x = popup_x + 260
            for opt_id, label, color in [('def_plus1', '+1', (80, 140, 80)),
                                          ('def_minus1', '-1', (140, 80, 80)),
                                          ('def_reroll', 'Re', (80, 80, 140))]:
                btn_rect = pygame.Rect(btn_x, y_offset - 3, 48, 26)
                pygame.draw.rect(self.screen, color, btn_rect)
                pygame.draw.rect(self.screen, COLOR_TEXT, btn_rect, 1)
                btn_text = self.font_small.render(label, True, COLOR_TEXT)
                self.screen.blit(btn_text, (btn_rect.x + (48 - btn_text.get_width()) // 2,
                                            btn_rect.y + (26 - btn_text.get_height()) // 2))
                self.dice_option_buttons.append((opt_id, btn_rect))
                btn_x += 52

            y_offset += 55
        elif is_ranged and target:
            # Show target info for ranged attacks (read-only, no dice to modify)
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
        selected = game.selected_counters

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

        # Priority player text only
        priority_color = COLOR_PLAYER1 if game.priority_player == 1 else COLOR_PLAYER2
        priority_text = f"Приоритет: Игрок {game.priority_player}"
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
            active_popups.append(('exchange', 300, 90))

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
