"""State handlers for application states.

Each app state has its own handler class that manages events, updates, and rendering
for that state. This provides clean separation of concerns and makes the code
more maintainable.
"""

from .base import StateHandler
from .menu import MenuHandler
from .settings import SettingsHandler
from .deck_builder import DeckBuilderHandler
from .squad_select import SquadSelectHandler
from .squad_place import SquadPlaceHandler
from .game_handler import GameHandler
from .network_lobby import NetworkLobbyHandler
from .network_game import NetworkGameHandler

__all__ = [
    'StateHandler',
    'MenuHandler',
    'SettingsHandler',
    'DeckBuilderHandler',
    'SquadSelectHandler',
    'SquadPlaceHandler',
    'GameHandler',
    'NetworkLobbyHandler',
    'NetworkGameHandler',
]
