"""Game constants and enums."""
from enum import Enum, auto


# Display settings - change these to adjust resolution
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
FPS = 60

# Base resolution for scaling (original design resolution)
BASE_WIDTH = 1280
BASE_HEIGHT = 720

# UI scale factor - all UI elements scale by this
UI_SCALE = WINDOW_WIDTH / BASE_WIDTH

def scaled(value: int) -> int:
    """Scale a value by UI_SCALE."""
    return int(value * UI_SCALE)

# Board dimensions (scaled from base values)
BOARD_COLS = 5
BOARD_ROWS = 6
CELL_SIZE = scaled(100)
BOARD_OFFSET_X = scaled(340)
BOARD_OFFSET_Y = scaled(60)

# Card display (scaled from base values)
CARD_WIDTH = scaled(90)
CARD_HEIGHT = scaled(90)

# Colors
COLOR_BG = (30, 30, 40)
COLOR_BOARD_LIGHT = (60, 60, 70)
COLOR_BOARD_DARK = (50, 50, 60)
COLOR_GRID_LINE = (80, 80, 90)
COLOR_PLAYER1 = (70, 130, 180)  # Steel blue
COLOR_PLAYER2 = (180, 70, 70)   # Indian red
COLOR_SELECTED = (255, 215, 0)  # Gold
COLOR_MOVE_HIGHLIGHT = (100, 200, 100, 128)  # Green transparent
COLOR_ATTACK_HIGHLIGHT = (200, 100, 100, 128)  # Red transparent
COLOR_TEXT = (240, 240, 240)
COLOR_TEXT_DARK = (20, 20, 20)
COLOR_HP_BAR = (50, 180, 50)
COLOR_HP_BAR_BG = (80, 30, 30)


class AppState(Enum):
    """Application states."""
    MENU = auto()            # Main menu
    GAME = auto()            # In-game
    DECK_BUILDER = auto()    # Deck building screen
    DECK_SELECT = auto()     # Deck selection for local game
    SQUAD_SELECT = auto()    # Squad selection (spending crystals)
    SQUAD_PLACE = auto()     # Squad placement on board


class GamePhase(Enum):
    """Game phases."""
    SETUP = auto()           # Initial placement
    REVEAL = auto()          # Cards revealed
    MAIN = auto()            # Main gameplay
    GAME_OVER = auto()       # Game ended


class CardType(Enum):
    """Card types."""
    CREATURE = auto()
    FLYER = auto()
    ARTIFACT = auto()
    LAND = auto()


class Element(Enum):
    """Card elements/colors."""
    NEUTRAL = "Нейтральный"
    MOUNTAINS = "Горы"
    PLAINS = "Степь"
    SWAMPS = "Болота"
    FOREST = "Лес"
    DARKNESS = "Тьма"


class ActionType(Enum):
    """Types of actions."""
    MOVE = auto()
    ATTACK = auto()
    ABILITY = auto()
    DEFEND = auto()
    PASS = auto()


# =============================================================================
# UI LAYOUT CONFIGURATION
# All values are in BASE resolution (1280x720) and get auto-scaled
# To modify UI, change these values - no need to touch renderer.py
# =============================================================================

class UILayout:
    """Centralized UI layout configuration. All values in base resolution."""

    # -------------------------------------------------------------------------
    # FONTS (sizes in base resolution)
    # -------------------------------------------------------------------------
    FONT_LARGE = 24
    FONT_MEDIUM = 20
    FONT_SMALL = 14
    FONT_CARD_NAME = 11
    FONT_POPUP = 14
    FONT_INDICATOR = 10        # Font size for HP/Move indicators
    FONT_INDICATOR_NAME = 'tahoma'  # Try: consolas, tahoma, segoe ui, arial narrow

    # -------------------------------------------------------------------------
    # CARD INFO PANEL (right side)
    # -------------------------------------------------------------------------
    CARD_INFO_X = 980          # Distance from left edge (will be WINDOW_WIDTH - offset)
    CARD_INFO_Y = 420           # Distance from top
    CARD_INFO_WIDTH = 250
    CARD_INFO_HEIGHT = 280
    CARD_INFO_PADDING = 10     # Internal padding
    CARD_INFO_LINE_SPACING = 28      # Space between text lines
    CARD_INFO_STATUS_SPACING = 26    # Space between status lines
    CARD_INFO_BUTTON_HEIGHT = 28     # Height of attack/ability buttons
    CARD_INFO_BUTTON_SPACING = 32    # Space after buttons

    # -------------------------------------------------------------------------
    # GRAVEYARDS (left side panels)
    # -------------------------------------------------------------------------
    GRAVEYARD_X = 10           # Distance from left edge
    GRAVEYARD_P2_Y = 60        # Player 2 graveyard Y position
    GRAVEYARD_P1_Y = 380       # Player 1 graveyard Y position
    GRAVEYARD_WIDTH = 150
    GRAVEYARD_HEIGHT = 280
    GRAVEYARD_COLLAPSED_HEIGHT = 40
    GRAVEYARD_LINE_HEIGHT = 22       # Space between card names
    GRAVEYARD_HEADER_HEIGHT = 45     # Height of title + count area

    # -------------------------------------------------------------------------
    # SIDE PANELS (P1 on right, P2 on left)
    # -------------------------------------------------------------------------
    SIDE_PANEL_WIDTH = 110    # Width of expanded panel (fits 100px cards + padding)
    SIDE_PANEL_TAB_HEIGHT = 28 # Height of collapsed tab header
    SIDE_PANEL_SPACING = 2     # Gap between tabs
    SIDE_PANEL_EXPANDED_HEIGHT = 320  # Height when expanded (fits ~3 cards with scroll)

    # P1 zone (RIGHT side of board, before card info panel)
    SIDE_PANEL_P1_X = 845      # X position for P1 panels
    SIDE_PANEL_P1_Y = 60       # Y position for P1 tabs

    # P2 zone (LEFT side of board)
    SIDE_PANEL_P2_X = 225       # X position for P2 panels
    SIDE_PANEL_P2_Y = 60       # Y position for P2 tabs

    # Flying and graveyard content
    SIDE_PANEL_CARD_SIZE = 100 # Size of card thumbnails in side panels
    SIDE_PANEL_CARD_SPACING = 4  # Space between cards in panels

    # -------------------------------------------------------------------------
    # BUTTONS
    # -------------------------------------------------------------------------
    # End Turn button (right side)
    END_TURN_X = 1130          # X position (BASE_WIDTH - 110)
    END_TURN_Y = 333           # Y position
    END_TURN_WIDTH = 120
    END_TURN_HEIGHT = 24

    # Skip button (left of End Turn)
    SKIP_X = 1000              # X position
    SKIP_Y = 333               # Same Y as End Turn
    SKIP_WIDTH = 120
    SKIP_HEIGHT = 24

    # Priority bar (shown during priority phase)
    PRIORITY_BAR_X_OFFSET = 280  # Distance from right edge
    PRIORITY_BAR_Y = 360
    PRIORITY_BAR_WIDTH = 250
    PRIORITY_BAR_HEIGHT = 27

    # -------------------------------------------------------------------------
    # COMBAT LOG (right side, below card info)
    # -------------------------------------------------------------------------
    COMBAT_LOG_X_OFFSET = 300  # Distance from right edge
    COMBAT_LOG_Y = 40
    COMBAT_LOG_WIDTH = 300
    COMBAT_LOG_HEIGHT = 250
    COMBAT_LOG_LINE_HEIGHT = 18

    # -------------------------------------------------------------------------
    # CARD INDICATORS (on card surface)
    # -------------------------------------------------------------------------
    INDICATOR_HP_WIDTH = 30    # Was 38, reduced 15%
    INDICATOR_HP_HEIGHT = 13   # Was 16, reduced 15%
    INDICATOR_MARGIN = 4       # Was 5, reduced 15%
    INDICATOR_GAP = 3          # Gap between indicator and name bar

    COUNTER_SIZE = 17          # Was 20, reduced 15%
    FORMATION_SIZE = 14        # Was 16, reduced 15%
    ARMOR_SIZE = 15            # Was 18, reduced 15%

    NAME_BAR_HEIGHT = 16       # Card name bar height

    # -------------------------------------------------------------------------
    # POPUPS
    # -------------------------------------------------------------------------
    POPUP_DEFAULT_Y = 60       # Default Y position for popups
    POPUP_CARD_WIDTH = 350     # Full card popup width
    POPUP_CARD_HEIGHT = 500    # Full card popup height

    # -------------------------------------------------------------------------
    # DECK BUILDER
    # -------------------------------------------------------------------------
    DECK_BUILDER_LIBRARY_X = 10
    DECK_BUILDER_LIBRARY_Y = 50
    DECK_BUILDER_LIBRARY_WIDTH = 900
    DECK_BUILDER_LIBRARY_HEIGHT = 280
    DECK_BUILDER_DECK_Y = 350
    DECK_BUILDER_DECK_HEIGHT = 320
    DECK_BUILDER_PANEL_X = 920
    DECK_BUILDER_PANEL_WIDTH = 340
    # Card dimensions - larger cards, square for less cropping
    DECK_BUILDER_CARD_WIDTH = 85
    DECK_BUILDER_CARD_HEIGHT = 85
    DECK_BUILDER_CARD_GAP = 6
    DECK_BUILDER_CARDS_PER_ROW = 9
    DECK_BUILDER_INDICATOR_WIDTH = 22
    DECK_BUILDER_INDICATOR_HEIGHT = 14
    # Scrollbar
    DECK_BUILDER_SCROLLBAR_WIDTH = 12

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    @classmethod
    def get_flying_p1_x(cls):
        """Flying zone P1 X position (right of board)."""
        return BOARD_OFFSET_X + BOARD_COLS * CELL_SIZE + scaled(cls.FLYING_MARGIN)

    @classmethod
    def get_flying_p2_x(cls):
        """Flying zone P2 X position (left of board)."""
        return BOARD_OFFSET_X - scaled(cls.FLYING_ZONE_WIDTH) - scaled(cls.FLYING_MARGIN)

    @classmethod
    def get_card_info_x(cls):
        """Card info panel X position."""
        return scaled(cls.CARD_INFO_X)

    @classmethod
    def get_combat_log_x(cls):
        """Combat log X position (right side of screen)."""
        return WINDOW_WIDTH - scaled(cls.COMBAT_LOG_X_OFFSET)


# Shortcut for accessing layout values with scaling
def ui(value: int) -> int:
    """Scale a UI layout value. Shortcut for scaled()."""
    return scaled(value)
