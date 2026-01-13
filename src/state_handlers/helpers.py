"""Shared helper functions for state handlers.

These functions consolidate duplicate logic that was spread across
different app states in main.py.
"""

from typing import Optional, Callable, Any, TYPE_CHECKING

from ..constants import scaled

if TYPE_CHECKING:
    from ..game import Game
    from ..ui_state import GameClient
    from ..renderer import Renderer
    from ..constants import AppState
    from ..app_context import AppContext


def handle_game_scroll(
    game: 'Game',
    game_client: 'GameClient',
    renderer: 'Renderer',
    mx: int,
    my: int,
    scroll_y: int,
) -> bool:
    """Handle scroll wheel events in game view.

    Handles scrolling for:
    - Side panels (graveyards, flyers)
    - Combat log
    - Card info panel

    Args:
        game: The game state
        game_client: The game client (for viewing_player)
        renderer: The renderer
        mx: Mouse X in game coordinates
        my: Mouse Y in game coordinates
        scroll_y: Scroll amount (positive = up, negative = down)

    Returns:
        True if the scroll was handled
    """
    from ..constants import UILayout

    # Calculate scaled panel boundaries
    left_panel_start = scaled(UILayout.SIDE_PANEL_P2_X) - 5
    left_panel_end = scaled(UILayout.SIDE_PANEL_P2_X + UILayout.SIDE_PANEL_WIDTH) + 5
    right_panel_start = scaled(UILayout.SIDE_PANEL_P1_X) - 5
    right_panel_end = scaled(UILayout.SIDE_PANEL_P1_X + UILayout.SIDE_PANEL_WIDTH) + 5
    ui_panel_start = scaled(UILayout.CARD_INFO_X)
    card_info_y = scaled(UILayout.CARD_INFO_Y)

    viewing = game_client.ui.viewing_player

    if left_panel_start <= mx <= left_panel_end:
        # Left panel - shows P2 content when viewing P1, P1 content when viewing P2
        owner = 'p2' if viewing == 1 else 'p1'
        panel_type = renderer.expanded_panel_p2 if viewing == 1 else renderer.expanded_panel_p1
        # Default to flyers if panel has flyers but type not set
        if not panel_type:
            flyers = game.board.flying_p2 if viewing == 1 else game.board.flying_p1
            if any(c is not None for c in flyers):
                panel_type = 'flyers'
        if panel_type:
            renderer.scroll_side_panel(-scroll_y, f'{owner}_{panel_type}')
        return True

    elif right_panel_start <= mx <= right_panel_end:
        # Right panel - shows P1 content when viewing P1, P2 content when viewing P2
        owner = 'p1' if viewing == 1 else 'p2'
        panel_type = renderer.expanded_panel_p1 if viewing == 1 else renderer.expanded_panel_p2
        # Default to flyers if panel has flyers but type not set
        if not panel_type:
            flyers = game.board.flying_p1 if viewing == 1 else game.board.flying_p2
            if any(c is not None for c in flyers):
                panel_type = 'flyers'
        if panel_type:
            renderer.scroll_side_panel(-scroll_y, f'{owner}_{panel_type}')
        return True

    elif mx > ui_panel_start:
        # Log is at top, card info is below
        if my < card_info_y:
            renderer.scroll_log(-scroll_y, game)
        else:
            renderer.scroll_card_info(-scroll_y)
        return True

    else:
        renderer.scroll_log(-scroll_y, game)
        return True


def handle_game_esc(
    game: 'Game',
    game_client: 'GameClient',
    renderer: 'Renderer',
    cancel_fn: Callable[[], None],
    show_pause_menu: bool,
) -> tuple[bool, bool]:
    """Handle ESC key press hierarchy in game.

    ESC priority order:
    1. Close pause menu if open
    2. Close card popup if open
    3. Close dice popup if open
    4. Cancel ability targeting if active
    5. Deselect selected card if any
    6. Open pause menu

    Args:
        game: The game state
        game_client: The game client
        renderer: The renderer
        cancel_fn: Function to call to cancel ability targeting
        show_pause_menu: Current pause menu state

    Returns:
        Tuple of (handled, new_show_pause_menu)
    """
    if show_pause_menu:
        return True, False

    if renderer.popup_card:
        renderer.hide_popup()
        return True, show_pause_menu

    if renderer.dice_popup_open:
        renderer.close_dice_popup()
        return True, show_pause_menu

    if game.awaiting_ability_target:
        cancel_fn()
        game_client.deselect()
        return True, show_pause_menu

    if game_client.selected_card:
        game_client.deselect()
        return True, show_pause_menu

    # Nothing else to close - open pause menu
    return True, True


def get_phase_state(
    network_prep_state: Optional[dict],
    local_game_state: dict,
    key: str
) -> Any:
    """Get state from network or local flow based on which is active.

    Args:
        network_prep_state: Network prep state dict (or None)
        local_game_state: Local game state dict
        key: Key to look up in the state dict

    Returns:
        Value from network_prep_state if available, otherwise from local_game_state
    """
    if network_prep_state and network_prep_state.get(key):
        return network_prep_state[key]
    return local_game_state.get(key)


def handle_pause_menu_click(
    ctx: 'AppContext',
    mx: int,
    my: int,
    is_network: bool = False,
) -> Optional['AppState']:
    """Handle click on pause menu buttons.

    Args:
        ctx: Application context
        mx: Mouse X in game coordinates
        my: Mouse Y in game coordinates
        is_network: Whether this is a network game

    Returns:
        New AppState if transitioning, None otherwise
    """
    from ..constants import AppState

    btn = ctx.renderer.get_clicked_pause_button(mx, my)
    if not btn:
        return None

    if btn == 'resume':
        ctx.show_pause_menu = False
        return None

    elif btn == 'concede':
        # Concede the game
        if is_network:
            # For network, we need to handle this differently
            # Just close the pause menu for now - actual concede logic
            # should be handled by the network game handler
            pass
        else:
            # Local game - end with opponent winning
            if ctx.game:
                from ..constants import GamePhase
                ctx.game.phase = GamePhase.GAME_OVER
                # Current player loses
                ctx.game.winner = 3 - ctx.game.current_player
        ctx.show_pause_menu = False
        return None

    elif btn == 'exit':
        ctx.show_pause_menu = False
        if is_network:
            ctx.reset_network_game()
        else:
            ctx.reset_local_game()
        return AppState.MENU

    return None


def process_game_events(game: 'Game', renderer: 'Renderer', events: list) -> None:
    """Process game events and update UI.

    Args:
        game: The game state
        renderer: The renderer
        events: List of Event objects to process
    """
    from ..commands import EventType

    for event in events:
        if event.type == EventType.CARD_DAMAGED:
            # Use position from event (card may be in graveyard by now)
            pos = event.position if event.position is not None and event.position >= 0 else None
            if pos is None:
                # Fallback to card's current position
                card = game.get_card_by_id(event.card_id)
                pos = card.position if card else None
            if pos is not None and event.amount:
                renderer.add_floating_text(pos, f"-{event.amount}", (255, 80, 80))
                renderer.play_damage_sound(event.amount)
        elif event.type == EventType.CARD_HEALED:
            # Use position from event for consistency
            pos = event.position if event.position is not None and event.position >= 0 else None
            if pos is None:
                # Fallback to card's current position
                card = game.get_card_by_id(event.card_id)
                pos = card.position if card else None
            if pos is not None and event.amount:
                renderer.add_floating_text(pos, f"+{event.amount}", (80, 255, 80))
        elif event.type == EventType.ARROW_ADDED:
            color = (100, 255, 100) if event.arrow_type == 'heal' else (255, 100, 100)
            renderer.add_arrow(event.from_position, event.to_position, color)
        elif event.type == EventType.ARROWS_CLEARED:
            renderer.clear_arrows()
        elif event.type == EventType.VALHALLA_APPLIED:
            # Gold glow effect on the buffed card
            pos = event.position if event.position is not None and event.position >= 0 else None
            if pos is not None:
                renderer.add_valhalla_glow(pos)
        elif event.type == EventType.CARD_DIED:
            # Get card from graveyard (it was just moved there)
            card = None
            pos = event.position if hasattr(event, 'position') else -1
            visual_index = event.context.get('visual_index', -1) if event.context else -1
            for grave_card in game.board.graveyard_p1 + game.board.graveyard_p2:
                if grave_card.id == event.card_id:
                    card = grave_card
                    break
            if card and pos >= 0:
                renderer.start_death_animation(card, pos, visual_index)
        elif event.type == EventType.CARD_REVEALED:
            # Update local card with revealed data (for network sync)
            # In local games, the card already has correct state - just reveal it
            # In network games, we may need to sync state from server
            card = game.get_card_by_id(event.card_id)
            if card:
                card.face_down = False
                # Note: Don't copy position from event data. The event is emitted
                # BEFORE _move_to_flying_zone(), so it contains the old board position.
                # Local state is authoritative - the card is already in correct position.
