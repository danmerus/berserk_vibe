"""
Berserk Digital Card Game - Refactored Main
Uses state handlers for clean separation of concerns.
"""
import pygame
import sys

from src.constants import WINDOW_WIDTH, WINDOW_HEIGHT, FPS, AppState
from src.settings import get_resolution
from src.renderer import Renderer
from src.app_context import AppContext, create_local_game_state
from src.state_handlers import (
    MenuHandler,
    SettingsHandler,
    DeckBuilderHandler,
    SquadSelectHandler,
    SquadPlaceHandler,
    GameHandler,
    NetworkLobbyHandler,
    NetworkGameHandler,
)


def handle_global_event(event: pygame.event.Event, ctx: AppContext) -> bool:
    """Handle global events that apply to all states.

    Returns True if event was handled and shouldn't be passed to state handler.
    """
    if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
        # Toggle fullscreen
        ctx.fullscreen = not ctx.fullscreen
        if ctx.fullscreen:
            ctx.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            ctx.screen = pygame.display.set_mode(ctx.current_resolution, pygame.RESIZABLE)
        ctx.renderer.handle_resize(ctx.screen)
        return True

    return False


def main():
    """Main game loop using state handlers."""
    pygame.init()
    pygame.key.set_repeat(300, 30)

    # Initialize window
    saved_res = get_resolution()
    if saved_res:
        initial_resolution = saved_res
    else:
        initial_resolution = (WINDOW_WIDTH, WINDOW_HEIGHT)

    screen = pygame.display.set_mode(initial_resolution, pygame.RESIZABLE)
    pygame.display.set_caption("Berserk")

    clock = pygame.time.Clock()
    renderer = Renderer(screen)

    # Create application context
    ctx = AppContext(
        screen=screen,
        clock=clock,
        renderer=renderer,
        current_resolution=initial_resolution,
        local_game_state=create_local_game_state(),
    )

    # Create state handlers
    handlers = {
        AppState.MENU: MenuHandler(ctx),
        AppState.SETTINGS: SettingsHandler(ctx),
        AppState.DECK_BUILDER: DeckBuilderHandler(ctx, is_selection_mode=False),
        AppState.DECK_SELECT: DeckBuilderHandler(ctx, is_selection_mode=True),
        AppState.SQUAD_SELECT: SquadSelectHandler(ctx),
        AppState.SQUAD_PLACE: SquadPlaceHandler(ctx),
        AppState.GAME: GameHandler(ctx),
        AppState.NETWORK_LOBBY: NetworkLobbyHandler(ctx),
        AppState.NETWORK_GAME: NetworkGameHandler(ctx),
    }

    # Initial state
    app_state = AppState.MENU
    current_handler = handlers[app_state]
    current_handler.on_enter()

    running = True

    while running:
        dt = clock.tick(FPS) / 1000.0

        # Process events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue

            if event.type == pygame.VIDEORESIZE:
                if not ctx.fullscreen:
                    ctx.current_resolution = (event.w, event.h)
                    ctx.screen = pygame.display.set_mode(ctx.current_resolution, pygame.RESIZABLE)
                    ctx.renderer.handle_resize(ctx.screen)
                continue

            # Handle global events (F11 fullscreen)
            if handle_global_event(event, ctx):
                continue

            # Let current handler process event
            new_state = current_handler.handle_event(event)

            # Check for exit request from menu
            if app_state == AppState.MENU and hasattr(current_handler, 'should_exit') and current_handler.should_exit:
                running = False
                continue

            # Handle state transition from event
            if new_state is not None and new_state != app_state:
                current_handler.on_exit()
                app_state = new_state
                current_handler = handlers[app_state]
                current_handler.on_enter()

        # Update current handler
        new_state = current_handler.update(dt)

        # Handle state transition from update
        if new_state is not None and new_state != app_state:
            current_handler.on_exit()
            app_state = new_state
            current_handler = handlers[app_state]
            current_handler.on_enter()

        # Render
        current_handler.render()

        # Flip display
        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    main()
