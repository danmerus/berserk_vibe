"""Game constants and enums."""
from enum import Enum, auto


# Display settings
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS = 60

# Board dimensions
BOARD_COLS = 5
BOARD_ROWS = 6
CELL_SIZE = 100
BOARD_OFFSET_X = 340
BOARD_OFFSET_Y = 60

# Card display
CARD_WIDTH = 90
CARD_HEIGHT = 90

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
