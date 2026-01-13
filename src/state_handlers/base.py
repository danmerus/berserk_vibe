"""Base class for state handlers."""

import pygame
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app_context import AppContext
    from ..constants import AppState


class StateHandler(ABC):
    """Abstract base class for app state handlers.

    Each app state (MENU, SETTINGS, GAME, etc.) has its own handler that
    manages events, updates, and rendering for that state.

    Handlers receive an AppContext with all shared state, eliminating
    the need for global variables.
    """

    def __init__(self, ctx: 'AppContext'):
        """Initialize handler with app context.

        Args:
            ctx: Application context containing all shared state
        """
        self.ctx = ctx

    @abstractmethod
    def handle_event(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle a pygame event.

        Args:
            event: The pygame event to handle

        Returns:
            New AppState to transition to, or None to stay in current state
        """
        pass

    @abstractmethod
    def update(self, dt: float) -> Optional['AppState']:
        """Update state logic.

        Called every frame to update animations, timers, etc.

        Args:
            dt: Delta time in seconds since last frame

        Returns:
            New AppState to transition to, or None to stay in current state
        """
        pass

    @abstractmethod
    def render(self) -> None:
        """Render the state to the screen.

        Should draw using ctx.renderer, which handles scaling to the window.
        """
        pass

    def on_enter(self) -> None:
        """Called when entering this state.

        Override to perform setup when transitioning to this state.
        """
        pass

    def on_exit(self) -> None:
        """Called when leaving this state.

        Override to perform cleanup when transitioning away from this state.
        """
        pass
