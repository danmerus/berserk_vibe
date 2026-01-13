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
# Perspective-based colors (used when rendering from a player's viewpoint)
COLOR_SELF = (70, 130, 180)     # Blue for "your" cards
COLOR_OPPONENT = (180, 70, 70)  # Red for opponent's cards
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
    SETTINGS = auto()        # Settings screen
    GAME = auto()            # In-game (local hotseat)
    DECK_BUILDER = auto()    # Deck building screen
    DECK_SELECT = auto()     # Deck selection for local game
    SQUAD_SELECT = auto()    # Squad selection (spending crystals)
    SQUAD_PLACE = auto()     # Squad placement on board
    NETWORK_LOBBY = auto()   # Network game lobby (connect/create/join)
    NETWORK_WAITING = auto() # Waiting for opponent to join
    NETWORK_GAME = auto()    # Network game in progress


# Available resolutions
RESOLUTIONS = [
    (1280, 720),
    (1366, 768),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
]


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

    # Card name display
    CARD_NAME_MAX_LEN = 17     # Max characters before truncation with ellipsis

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
    # CHAT (network games only, left side)
    # -------------------------------------------------------------------------
    CHAT_X = 10
    CHAT_Y = 120
    CHAT_WIDTH = 250
    CHAT_HEIGHT = 500
    CHAT_INPUT_HEIGHT = 32
    CHAT_TITLE_HEIGHT = 24
    CHAT_MESSAGE_PADDING = 4

    # -------------------------------------------------------------------------
    # DRAW BUTTON (network games only, below chat)
    # -------------------------------------------------------------------------
    DRAW_BUTTON_OFFSET_Y = 350      # Gap between chat and draw button
    DRAW_BUTTON_HEIGHT = 50
    # Colors (normal state)
    DRAW_BUTTON_BG = (60, 60, 70)
    DRAW_BUTTON_BORDER = (100, 100, 110)
    DRAW_BUTTON_TEXT = (200, 200, 200)
    # Colors (opponent offered - accept state)
    DRAW_BUTTON_ACCEPT_BG = (70, 130, 70)
    DRAW_BUTTON_ACCEPT_BG_FLASH = (80, 140, 80)
    DRAW_BUTTON_ACCEPT_BG_DARK = (60, 100, 60)
    DRAW_BUTTON_ACCEPT_TEXT = (240, 240, 240)
    # Colors (we offered - waiting state)
    DRAW_BUTTON_WAITING_BG = (80, 80, 60)
    DRAW_BUTTON_WAITING_TEXT = (180, 180, 150)

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
    # POPUPS - General settings
    # -------------------------------------------------------------------------
    POPUP_DEFAULT_Y = 60       # Default Y position for popups
    POPUP_BORDER_WIDTH = 2     # Border thickness for all popups

    # Card preview popup (right-click on card)
    POPUP_CARD_WIDTH = 350
    POPUP_CARD_HEIGHT = 500

    # -------------------------------------------------------------------------
    # INTERACTION POPUPS (defender choice, valhalla, heal confirm, etc.)
    # -------------------------------------------------------------------------
    # Defender choice popup
    POPUP_DEFENDER_WIDTH = 500
    POPUP_DEFENDER_HEIGHT = 100
    POPUP_DEFENDER_BG = (0, 80, 80, 230)
    POPUP_DEFENDER_BORDER = (0, 200, 200)

    # Valhalla target popup
    POPUP_VALHALLA_WIDTH = 450
    POPUP_VALHALLA_HEIGHT = 80
    POPUP_VALHALLA_BG = (80, 60, 0, 230)
    POPUP_VALHALLA_BORDER = (255, 200, 100)

    # Heal confirmation popup
    POPUP_HEAL_WIDTH = 350
    POPUP_HEAL_HEIGHT = 90
    POPUP_HEAL_BG = (20, 80, 40, 230)
    POPUP_HEAL_BORDER = (80, 200, 100)

    # Counter shot / movement shot popup
    POPUP_SHOT_WIDTH = 400
    POPUP_SHOT_HEIGHT = 60
    POPUP_SHOT_BG = (80, 50, 0, 230)
    POPUP_SHOT_BORDER = (255, 140, 50)

    # Stench choice popup
    POPUP_STENCH_WIDTH = 380
    POPUP_STENCH_HEIGHT = 100
    POPUP_STENCH_BG = (60, 40, 20, 230)
    POPUP_STENCH_BORDER = (180, 120, 60)

    # Exchange (damage trade) popup
    POPUP_EXCHANGE_WIDTH = 320
    POPUP_EXCHANGE_HEIGHT = 115  # Taller for two-line buttons
    POPUP_EXCHANGE_BG = (80, 60, 20, 230)
    POPUP_EXCHANGE_BORDER = (255, 180, 80)

    # -------------------------------------------------------------------------
    # GAME OVER POPUP
    # -------------------------------------------------------------------------
    POPUP_GAME_OVER_WIDTH = 400
    POPUP_GAME_OVER_HEIGHT = 200
    POPUP_GAME_OVER_BG = (40, 50, 60)
    POPUP_GAME_OVER_BORDER = (80, 100, 120)
    POPUP_GAME_OVER_OVERLAY = (0, 0, 0, 200)  # Semi-transparent background

    # -------------------------------------------------------------------------
    # DICE POPUP (priority phase)
    # -------------------------------------------------------------------------
    POPUP_DICE_WIDTH = 420
    POPUP_DICE_HEIGHT_MELEE = 170    # Height for melee combat (both rolls)
    POPUP_DICE_HEIGHT_RANGED = 160   # Height for ranged/magic (single roll)
    POPUP_DICE_Y = 100
    POPUP_DICE_BG = (40, 40, 50)
    POPUP_DICE_BORDER = (100, 100, 120)

    # -------------------------------------------------------------------------
    # PAUSE MENU
    # -------------------------------------------------------------------------
    POPUP_PAUSE_WIDTH = 300
    POPUP_PAUSE_BUTTON_WIDTH = 200
    POPUP_PAUSE_BUTTON_HEIGHT = 40
    POPUP_PAUSE_BUTTON_GAP = 15
    POPUP_PAUSE_BG = (30, 30, 40, 240)
    POPUP_PAUSE_BORDER = (80, 80, 100)

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
    # DICE DISPLAY (combat roll indicators)
    # X: offset from board edges (left of board, right of board)
    # Y: anchored to GRAVEYARD_P1_Y
    # -------------------------------------------------------------------------
    DICE_SIZE = 48             # Size of dice icons
    # Board edges in base resolution (for anchoring)
    BOARD_LEFT_X = 340         # Left edge of board (base resolution)
    BOARD_RIGHT_X = 840        # Right edge of board (340 + 5*100)
    # Offsets from board edges
    DICE_X_OFFSET = 10         # X offset from board edge (negative = towards board)
    DICE_Y_OFFSET = 100        # Y offset from GRAVEYARD_P1_Y (negative = above)
    # Animation and styling
    DICE_BONUS_FONT_SIZE = 16  # Font size for bonus text
    DICE_ANIM_DURATION = 0.4   # Animation duration in seconds
    DICE_SPACING = 8           # Space between dice and bonus text

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
