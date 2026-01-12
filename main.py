"""
Berserk Digital Card Game - MVP
Hot-seat mode for two players on the same computer.
"""
import pygame
import sys

from src.constants import WINDOW_WIDTH, WINDOW_HEIGHT, FPS, GamePhase, AppState
from src.settings import get_resolution, set_resolution
from src.game import Game
from src.renderer import Renderer
from src.commands import (
    cmd_select_position,
    cmd_move, cmd_attack, cmd_prepare_flyer_attack,
    cmd_use_ability, cmd_use_instant,
    cmd_confirm, cmd_cancel, cmd_choose_position, cmd_choose_card,
    cmd_choose_amount, cmd_pass_priority, cmd_skip, cmd_end_turn, cmd_concede
)
from src.deck_builder import DeckBuilder
from src.deck_builder_renderer import DeckBuilderRenderer
from src.squad_builder import SquadBuilder
from src.squad_builder_renderer import SquadBuilderRenderer
from src.placement import PlacementState
from src.placement_renderer import PlacementRenderer
from src.commands import EventType
from src.ui_state import GameClient
from src.match import MatchServer, LocalMatchClient
from src.network_ui import NetworkUI, LobbyState
from src.card_database import create_starter_deck
from src.chat import ChatUI


def create_local_game_state():
    """Create fresh local game state."""
    return {
        'current_player': 1,
        'deck_p1': None,
        'deck_p2': None,
        'squad_builder': None,
        'squad_renderer': None,
        'squad_p1': None,
        'squad_p2': None,
        'placement_state': None,
        'placement_renderer': None,
        'placed_cards_p1': None,
        'placed_cards_p2': None,
    }


def create_network_prep_state():
    """Create fresh network game preparation state."""
    return {
        'deck': None,           # Selected deck cards
        'squad': None,          # Built squad (card names)
        'placed_cards': None,   # Placed cards with positions
        'squad_builder': None,
        'squad_renderer': None,
        'placement_state': None,
        'placement_renderer': None,
        'waiting_for_opponent': False,  # True after placement sent, waiting for game start
    }


# =============================================================================
# CLICK HANDLING HELPERS - Factor out the big if/elif ladder
# =============================================================================

def process_events(game, renderer, events):
    """Process game events and build visuals."""
    for event in events:
        if event.type == EventType.CARD_DAMAGED:
            card = game.get_card_by_id(event.card_id)
            if card and card.position is not None and event.amount:
                renderer.add_floating_text(card.position, f"-{event.amount}", (255, 80, 80))
        elif event.type == EventType.CARD_HEALED:
            card = game.get_card_by_id(event.card_id)
            if card and card.position is not None and event.amount:
                renderer.add_floating_text(card.position, f"+{event.amount}", (80, 255, 80))
        elif event.type == EventType.ARROW_ADDED:
            color = (100, 255, 100) if event.arrow_type == 'heal' else (255, 100, 100)
            renderer.add_arrow(event.from_position, event.to_position, color)
        elif event.type == EventType.ARROWS_CLEARED:
            renderer.clear_arrows()


def send_command(match_client: LocalMatchClient, renderer: Renderer, cmd) -> bool:
    """Send command via match client and process results.

    Args:
        match_client: LocalMatchClient to send command through
        renderer: Renderer for visual effects
        cmd: Command to send

    Returns:
        True if command was accepted
    """
    result = match_client.send_command(cmd)
    if result.events:
        process_events(match_client.game, renderer, result.events)
    return result.accepted


def send_network_command(network_client, cmd):
    """Send command via network client.

    Args:
        network_client: NetworkClient to send command through
        cmd: Command to send
    """
    if network_client:
        network_client.send_command(cmd)


def handle_priority_click(match_client, game, client, renderer, mx: int, my: int) -> bool:
    """Handle clicks during priority phase. Returns True if handled."""
    # During priority, use priority_player (who has priority to act)
    priority_player = game.priority_player

    if renderer.dice_popup_open:
        opt = renderer.get_clicked_dice_option(mx, my)
        if opt == 'cancel':
            renderer.close_dice_popup()
            return True
        elif opt:
            card = renderer.dice_popup_card
            if card:
                send_command(match_client, renderer, cmd_use_instant(priority_player, card.id, "luck", opt))
                renderer.close_dice_popup()
                return True

    if renderer.get_pass_button_rect().collidepoint(mx, my):
        renderer.close_dice_popup()
        send_command(match_client, renderer, cmd_pass_priority(priority_player))
        return True

    # Allow clicking on cards and abilities during priority
    ability_id = renderer.get_clicked_ability(mx, my)
    if ability_id and client.selected_card:
        if ability_id == "luck":
            # Check if card is a combat participant (can't use luck on own combat)
            card = client.selected_card
            is_combat_participant = False
            if game.pending_dice_roll:
                dice = game.pending_dice_roll
                combat_ids = {dice.attacker_id, dice.defender_id}
                is_combat_participant = card.id in combat_ids
            if not is_combat_participant:
                renderer.open_dice_popup(client.selected_card)
                return True

    # Try to select a card (client-side selection during priority)
    pos = renderer.screen_to_pos(mx, my)
    if pos is not None:
        card = game.board.get_card(pos)
        if card:
            client.select_card(card.id)
        else:
            client.deselect()
        return True

    return False


def handle_interaction_click(match_client, game, client, renderer, mx: int, my: int) -> bool:
    """Handle clicks during popup/interaction states. Returns True if handled."""
    # For interactions, use the interaction's acting_player (who should respond)
    # This may differ from current_player (e.g., stench target chooses, not attacker)
    acting_player = game.interaction.acting_player if game.interaction else game.current_player

    if game.awaiting_counter_selection:
        opt = renderer.get_clicked_counter_button(mx, my)
        if opt == 'confirm':
            send_command(match_client, renderer, cmd_confirm(acting_player, True))
            return True
        elif opt == 'cancel':
            send_command(match_client, renderer, cmd_cancel(acting_player))
            return True
        elif isinstance(opt, int):
            send_command(match_client, renderer, cmd_choose_amount(acting_player, opt))
            return True

    if game.awaiting_heal_confirm:
        choice = renderer.get_clicked_heal_button(mx, my)
        if choice == 'yes':
            send_command(match_client, renderer, cmd_confirm(acting_player, True))
            return True
        elif choice == 'no':
            send_command(match_client, renderer, cmd_confirm(acting_player, False))
            return True

    if game.awaiting_exchange_choice:
        choice = renderer.get_clicked_exchange_button(mx, my)
        if choice == 'full':
            send_command(match_client, renderer, cmd_confirm(acting_player, True))
            return True
        elif choice == 'reduce':
            send_command(match_client, renderer, cmd_confirm(acting_player, False))
            return True

    if game.awaiting_stench_choice:
        choice = renderer.get_clicked_stench_button(mx, my)
        if choice == 'tap':
            send_command(match_client, renderer, cmd_confirm(acting_player, True))
            return True
        elif choice == 'damage':
            send_command(match_client, renderer, cmd_confirm(acting_player, False))
            return True

    return False


def handle_ui_click(match_client, game, client, renderer, mx: int, my: int) -> bool:
    """Handle clicks on UI elements (buttons, panels). Returns True if handled."""
    if renderer.get_skip_button_rect().collidepoint(mx, my):
        # Skip uses acting_player during interactions (e.g., skip defender selection)
        if game.interaction and game.interaction.acting_player:
            player = game.interaction.acting_player
        else:
            player = game.current_player
        send_command(match_client, renderer, cmd_skip(player))
        return True

    if renderer.handle_side_panel_click(mx, my):
        return True

    if renderer.get_end_turn_button_rect().collidepoint(mx, my):
        send_command(match_client, renderer, cmd_end_turn(game.current_player))
        client.deselect()  # Clear selection on turn end
        return True

    if renderer.get_clicked_attack_button(mx, my):
        if client.selected_card:
            # Client-side toggle attack mode
            client.toggle_attack_mode()
            return True

    return False


def handle_ability_click(match_client, game, client, renderer, mx: int, my: int) -> bool:
    """Handle clicks on ability buttons. Returns True if handled."""
    # Check for prepare flyer attack button first
    if (renderer.prepare_flyer_button_rect and
        renderer.prepare_flyer_button_rect.collidepoint(mx, my) and
        client.selected_card):
        send_command(match_client, renderer, cmd_prepare_flyer_attack(
            game.current_player,
            client.selected_card.id
        ))
        return True

    ability_id = renderer.get_clicked_ability(mx, my)
    if ability_id and client.selected_card:
        if game.awaiting_priority and ability_id == "luck":
            renderer.open_dice_popup(client.selected_card)
        else:
            send_command(match_client, renderer, cmd_use_ability(
                game.current_player,
                client.selected_card.id,
                ability_id
            ))
        return True
    return False


def handle_board_click(match_client, game, client, renderer, mx: int, my: int) -> bool:
    """Handle clicks on the game board. Returns True if handled."""
    pos = renderer.screen_to_pos(mx, my)
    if pos is not None:
        # During interactions (defender choice, valhalla, etc.), use acting_player
        if game.interaction and game.interaction.acting_player:
            player = game.interaction.acting_player
        else:
            player = game.current_player

        # Handle interaction states - these need server commands
        if game.awaiting_ability_target or game.awaiting_counter_shot or game.awaiting_movement_shot:
            if game.interaction and game.interaction.can_select_position(pos):
                send_command(match_client, renderer, cmd_choose_position(player, pos))
                return True
            # Invalid target - do nothing (or could cancel)
            return True

        if game.awaiting_valhalla:
            if game.interaction and game.interaction.can_select_position(pos):
                send_command(match_client, renderer, cmd_choose_position(player, pos))
                return True
            return True

        if game.awaiting_defender:
            card = game.board.get_card(pos)
            if card and game.interaction and game.interaction.can_select_card_id(card.id):
                send_command(match_client, renderer, cmd_choose_card(player, card.id))
                return True
            return True

        # If a card is selected and clicking on a valid move/attack position,
        # send explicit command with card_id (network-ready)
        if client.selected_card and client.selected_card.player == player:
            if pos in client.ui.valid_moves:
                send_command(match_client, renderer, cmd_move(player, client.selected_card.id, pos))
                return True
            if pos in client.ui.valid_attacks:
                send_command(match_client, renderer, cmd_attack(player, client.selected_card.id, pos))
                return True

        # Client-side selection/deselection (no server command needed)
        card = game.board.get_card(pos)
        if card:
            client.select_card(card.id)
        else:
            client.deselect()
        return True
    return False


def handle_game_left_click(match_client, game, client, renderer, mx: int, my: int) -> bool:
    """
    Handle left click during game. Returns True if handled.
    Routes to appropriate handler based on game state.
    """
    # Handle popup drag attempts first
    if renderer.start_popup_drag(mx, my, game):
        return True
    if renderer.start_log_scrollbar_drag(mx, my):
        return True

    # Priority phase has special handling
    if game.awaiting_priority:
        return handle_priority_click(match_client, game, client, renderer, mx, my)

    # Check for interaction popups (counter, heal, exchange, stench)
    if handle_interaction_click(match_client, game, client, renderer, mx, my):
        return True

    # Check UI elements (buttons, panels)
    if handle_ui_click(match_client, game, client, renderer, mx, my):
        return True

    # Check ability clicks
    if handle_ability_click(match_client, game, client, renderer, mx, my):
        return True

    # Finally, handle board clicks
    return handle_board_click(match_client, game, client, renderer, mx, my)


# =============================================================================
# NETWORK GAME CLICK HANDLERS
# =============================================================================

def handle_network_board_click(network_client, game, client, renderer, mx: int, my: int, player: int) -> bool:
    """Handle clicks on the game board for network play. Returns True if handled."""
    pos = renderer.screen_to_pos(mx, my)
    if pos is not None:
        # During interactions, use acting_player
        if game.interaction and game.interaction.acting_player:
            acting_player = game.interaction.acting_player
        else:
            acting_player = game.current_player

        # Only allow actions if we're the acting player
        if acting_player != player:
            # Allow card selection for viewing, but no actions
            card = game.board.get_card(pos)
            if card:
                client.select_card(card.id)
            else:
                client.deselect()
            return True

        # Handle interaction states
        if game.awaiting_ability_target or game.awaiting_counter_shot or game.awaiting_movement_shot:
            if game.interaction and game.interaction.can_select_position(pos):
                send_network_command(network_client, cmd_choose_position(player, pos))
                return True
            else:
                # Clicking on invalid position - cancel the ability targeting
                send_network_command(network_client, cmd_cancel(player))
                client.deselect()
                return True

        if game.awaiting_valhalla:
            if game.interaction and game.interaction.can_select_position(pos):
                send_network_command(network_client, cmd_choose_position(player, pos))
                return True
            else:
                # Clicking outside valhalla targets - just deselect visually
                # (valhalla usually has limited skip options)
                return True

        if game.awaiting_defender:
            card = game.board.get_card(pos)
            if card and game.interaction and game.interaction.can_select_card_id(card.id):
                send_network_command(network_client, cmd_choose_card(player, card.id))
                return True
            else:
                # Clicking outside valid defenders - skip defender selection
                send_network_command(network_client, cmd_skip(player))
                return True

        # If a card is selected and clicking on a valid move/attack position
        if client.selected_card and client.selected_card.player == player:
            if pos in client.ui.valid_moves:
                send_network_command(network_client, cmd_move(player, client.selected_card.id, pos))
                return True
            if pos in client.ui.valid_attacks:
                send_network_command(network_client, cmd_attack(player, client.selected_card.id, pos))
                return True

        # Client-side selection/deselection
        card = game.board.get_card(pos)
        if card:
            client.select_card(card.id)
        else:
            client.deselect()
        return True
    return False


def handle_network_ui_click(network_client, game, client, renderer, mx: int, my: int, player: int) -> bool:
    """Handle clicks on UI elements for network play. Returns True if handled."""
    # Skip button - check if we're the acting player
    if renderer.get_skip_button_rect().collidepoint(mx, my):
        if game.interaction and game.interaction.acting_player:
            acting_player = game.interaction.acting_player
        else:
            acting_player = game.current_player

        if acting_player == player:
            send_network_command(network_client, cmd_skip(player))
        return True

    if renderer.handle_side_panel_click(mx, my):
        return True

    # End turn button - only current player can end turn
    if renderer.get_end_turn_button_rect().collidepoint(mx, my):
        if game.current_player == player:
            # Cancel ability targeting if active
            if game.awaiting_ability_target:
                send_network_command(network_client, cmd_cancel(player))
            send_network_command(network_client, cmd_end_turn(player))
            client.deselect()
        return True

    if renderer.get_clicked_attack_button(mx, my):
        if client.selected_card:
            # Cancel ability targeting if active
            if game.awaiting_ability_target:
                send_network_command(network_client, cmd_cancel(player))
            client.toggle_attack_mode()
            return True

    return False


def handle_network_ability_click(network_client, game, client, renderer, mx: int, my: int, player: int) -> bool:
    """Handle clicks on ability buttons for network play. Returns True if handled."""
    # Only allow ability use if it's our turn
    if game.current_player != player:
        return False

    # Prepare flyer attack button
    if (renderer.prepare_flyer_button_rect and
        renderer.prepare_flyer_button_rect.collidepoint(mx, my) and
        client.selected_card):
        # Cancel ability targeting if active
        if game.awaiting_ability_target:
            send_network_command(network_client, cmd_cancel(player))
        send_network_command(network_client, cmd_prepare_flyer_attack(player, client.selected_card.id))
        return True

    ability_id = renderer.get_clicked_ability(mx, my)
    if ability_id and client.selected_card:
        # Cancel ability targeting if clicking a different ability
        if game.awaiting_ability_target:
            send_network_command(network_client, cmd_cancel(player))
        if game.awaiting_priority and ability_id == "luck":
            renderer.open_dice_popup(client.selected_card)
        else:
            send_network_command(network_client, cmd_use_ability(player, client.selected_card.id, ability_id))
        return True
    return False


def handle_network_interaction_click(network_client, game, client, renderer, mx: int, my: int, player: int) -> bool:
    """Handle clicks during popup/interaction states for network play. Returns True if handled."""
    # Check if we're the acting player for this interaction
    if game.interaction and game.interaction.acting_player:
        acting_player = game.interaction.acting_player
    else:
        acting_player = game.current_player

    if acting_player != player:
        return False

    if game.awaiting_counter_selection:
        opt = renderer.get_clicked_counter_button(mx, my)
        if opt == 'confirm':
            send_network_command(network_client, cmd_confirm(player, True))
            return True
        elif opt == 'cancel':
            send_network_command(network_client, cmd_cancel(player))
            return True
        elif isinstance(opt, int):
            send_network_command(network_client, cmd_choose_amount(player, opt))
            return True

    if game.awaiting_heal_confirm:
        choice = renderer.get_clicked_heal_button(mx, my)
        if choice == 'yes':
            send_network_command(network_client, cmd_confirm(player, True))
            return True
        elif choice == 'no':
            send_network_command(network_client, cmd_confirm(player, False))
            return True

    if game.awaiting_exchange_choice:
        choice = renderer.get_clicked_exchange_button(mx, my)
        if choice == 'full':
            send_network_command(network_client, cmd_confirm(player, True))
            return True
        elif choice == 'reduce':
            send_network_command(network_client, cmd_confirm(player, False))
            return True

    if game.awaiting_stench_choice:
        choice = renderer.get_clicked_stench_button(mx, my)
        if choice == 'tap':
            send_network_command(network_client, cmd_confirm(player, True))
            return True
        elif choice == 'damage':
            send_network_command(network_client, cmd_confirm(player, False))
            return True

    return False


def handle_network_priority_click(network_client, game, client, renderer, mx: int, my: int, player: int) -> bool:
    """Handle clicks during priority phase for network play. Returns True if handled."""
    priority_player = game.priority_player

    if renderer.dice_popup_open:
        opt = renderer.get_clicked_dice_option(mx, my)
        if opt == 'cancel':
            renderer.close_dice_popup()
            return True
        elif opt:
            card = renderer.dice_popup_card
            if card and priority_player == player:
                send_network_command(network_client, cmd_use_instant(player, card.id, "luck", opt))
                renderer.close_dice_popup()
                return True

    # Pass priority button
    if renderer.get_pass_button_rect().collidepoint(mx, my):
        if priority_player == player:
            renderer.close_dice_popup()
            send_network_command(network_client, cmd_pass_priority(player))
        return True

    # Allow clicking on cards and abilities during priority
    ability_id = renderer.get_clicked_ability(mx, my)
    if ability_id and client.selected_card:
        if ability_id == "luck":
            card = client.selected_card
            is_combat_participant = False
            if game.pending_dice_roll:
                dice = game.pending_dice_roll
                combat_ids = {dice.attacker_id, dice.defender_id}
                is_combat_participant = card.id in combat_ids
            if not is_combat_participant:
                renderer.open_dice_popup(client.selected_card)
                return True

    # Card selection during priority
    pos = renderer.screen_to_pos(mx, my)
    if pos is not None:
        card = game.board.get_card(pos)
        if card:
            client.select_card(card.id)
        else:
            client.deselect()
        return True

    return False


def handle_network_game_click(network_client, game, client, renderer, mx: int, my: int, player: int) -> bool:
    """
    Handle left click during network game. Returns True if handled.
    Routes to appropriate handler based on game state.
    """
    # Handle popup drag attempts first
    if renderer.start_popup_drag(mx, my, game):
        return True
    if renderer.start_log_scrollbar_drag(mx, my):
        return True

    # Priority phase has special handling
    if game.awaiting_priority:
        return handle_network_priority_click(network_client, game, client, renderer, mx, my, player)

    # Check for interaction popups (counter, heal, exchange, stench)
    if handle_network_interaction_click(network_client, game, client, renderer, mx, my, player):
        return True

    # Check UI elements (buttons, panels)
    if handle_network_ui_click(network_client, game, client, renderer, mx, my, player):
        return True

    # Check ability clicks
    if handle_network_ability_click(network_client, game, client, renderer, mx, my, player):
        return True

    # Finally, handle board clicks
    return handle_network_board_click(network_client, game, client, renderer, mx, my, player)


def main():
    """Main game loop."""
    pygame.init()
    pygame.display.set_caption("Берсерк - Цифровая версия")
    pygame.key.set_repeat(300, 30)

    # Load saved resolution or use default
    saved_resolution = get_resolution()
    current_resolution = saved_resolution
    screen = pygame.display.set_mode(current_resolution, pygame.RESIZABLE)
    clock = pygame.time.Clock()
    fullscreen = False

    app_state = AppState.MENU
    server = None  # MatchServer for game state
    client_p1 = None  # LocalMatchClient for player 1
    client_p2 = None  # LocalMatchClient for player 2
    match_client = None  # Current active LocalMatchClient (switches based on turn)
    game = None  # Shared game reference
    client = None  # Current active GameClient (switches based on turn)
    renderer = Renderer(screen)
    renderer.handle_resize(screen)  # Apply saved resolution scaling

    deck_builder = None
    deck_builder_renderer = None
    local_game_state = create_local_game_state()
    network_prep_state = None  # Network game preparation state
    network_ui = None  # Network lobby UI
    network_client = None  # Network client for multiplayer

    # Network game state
    network_game = None  # Game instance for network play
    network_player = 0  # Which player we are (1 or 2)
    network_game_client = None  # GameClient for network play
    network_chat = None  # ChatUI for network game

    # Draw offer state for network games
    draw_offered_by_us = False  # We offered a draw
    draw_offered_by_opponent = False  # Opponent offered a draw
    draw_button_rect = None  # For click detection
    draw_button_flash_timer = 0  # For flashing effect when opponent offers

    # Pause menu state
    show_pause_menu = False

    # Test game mode flag and side control (None = auto-switch based on turn, 1 or 2 = manual control)
    is_test_game = False
    test_game_controlled_player = None

    running = True
    while running:
        # Switch clients based on who needs to act
        if app_state == AppState.GAME and game and client_p1 and client_p2:
            # Determine the active player (who needs to make a decision)
            if is_test_game:
                # Test game: auto-switch to whoever needs to act
                if game.awaiting_priority:
                    active_player = game.priority_player
                elif game.interaction and game.interaction.acting_player:
                    active_player = game.interaction.acting_player
                else:
                    active_player = game.current_player
            else:
                # Normal hotseat: switch based on turn
                active_player = game.current_player

            if active_player == 1:
                match_client = client_p1
            else:
                match_client = client_p2
            client = match_client.game_client

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE:
                if not fullscreen:
                    screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    renderer.handle_resize(screen)

            elif event.type == pygame.TEXTINPUT:
                if app_state == AppState.SETTINGS:
                    if renderer.settings_nickname_input.active:
                        renderer.settings_nickname_input.handle_event(event)
                elif app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder_renderer:
                    if deck_builder_renderer.text_input_active:
                        deck_builder_renderer.handle_text_input(event)
                elif app_state == AppState.NETWORK_LOBBY and network_ui:
                    network_ui.handle_text_input(event)
                elif app_state == AppState.NETWORK_GAME and network_chat:
                    network_chat.handle_event(event)

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    if fullscreen:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
                    renderer.handle_resize(screen)

                elif app_state == AppState.SETTINGS:
                    if renderer.settings_nickname_input.active:
                        result = renderer.settings_nickname_input.handle_event(event)
                        if result == 'submit' or result == 'cancel':
                            renderer.settings_nickname_input.deactivate()
                            from src.settings import set_nickname
                            set_nickname(renderer.settings_nickname_input.value)
                    elif event.key == pygame.K_ESCAPE:
                        # Save and go back to menu
                        from src.settings import set_nickname
                        set_nickname(renderer.settings_nickname_input.value)
                        app_state = AppState.MENU

                elif app_state == AppState.NETWORK_LOBBY and network_ui:
                    if event.key == pygame.K_ESCAPE:
                        network_ui.disconnect()
                        network_ui = None
                        app_state = AppState.MENU
                    else:
                        network_ui.handle_text_input(event)

                elif app_state == AppState.GAME and game and client and match_client:
                    if event.key == pygame.K_ESCAPE:
                        if show_pause_menu:
                            show_pause_menu = False
                        elif renderer.popup_card:
                            renderer.hide_popup()
                        elif renderer.dice_popup_open:
                            renderer.close_dice_popup()
                        elif game.awaiting_ability_target:
                            # Cancel ability targeting
                            player = game.current_player
                            send_command(match_client, renderer, cmd_cancel(player))
                            client.deselect()
                        elif client.selected_card:
                            client.deselect()
                        else:
                            show_pause_menu = True
                    elif event.key == pygame.K_RETURN and game.phase == GamePhase.SETUP:
                        game.finish_placement()
                    elif event.key == pygame.K_y and game.awaiting_heal_confirm:
                        # Use interaction's acting_player for heal confirm
                        player = game.interaction.acting_player if game.interaction else game.current_player
                        send_command(match_client, renderer, cmd_confirm(player, True))
                    elif event.key == pygame.K_n and game.awaiting_heal_confirm:
                        player = game.interaction.acting_player if game.interaction else game.current_player
                        send_command(match_client, renderer, cmd_confirm(player, False))

                elif app_state == AppState.NETWORK_GAME and network_game and network_game_client:
                    # Let chat handle event first if focused
                    if network_chat and network_chat.is_input_focused():
                        if network_chat.handle_event(event):
                            continue
                    if event.key == pygame.K_ESCAPE:
                        if show_pause_menu:
                            show_pause_menu = False
                        elif network_chat and network_chat.is_input_focused():
                            network_chat.text_input.deactivate()
                        elif renderer.popup_card:
                            renderer.hide_popup()
                        elif renderer.dice_popup_open:
                            renderer.close_dice_popup()
                        elif network_game.awaiting_ability_target:
                            # Cancel ability targeting
                            send_network_command(network_client, cmd_cancel(network_player))
                            network_game_client.deselect()
                        elif network_game_client.selected_card:
                            # Deselect current card
                            network_game_client.deselect()
                        else:
                            # Nothing selected - open pause menu
                            show_pause_menu = True
                    elif event.key == pygame.K_y and network_game.awaiting_heal_confirm:
                        acting_player = network_game.interaction.acting_player if network_game.interaction else network_game.current_player
                        if acting_player == network_player:
                            send_network_command(network_client, cmd_confirm(network_player, True))
                    elif event.key == pygame.K_n and network_game.awaiting_heal_confirm:
                        acting_player = network_game.interaction.acting_player if network_game.interaction else network_game.current_player
                        if acting_player == network_player:
                            send_network_command(network_client, cmd_confirm(network_player, False))

                elif app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder_renderer:
                    if deck_builder_renderer.text_input_active:
                        result = deck_builder_renderer.handle_text_input(event)
                        if result is not None:
                            deck_builder_renderer.handle_text_input_result(result, deck_builder)
                        elif event.key == pygame.K_ESCAPE:
                            deck_builder_renderer.handle_text_input_result(None, deck_builder)
                    elif event.key == pygame.K_ESCAPE:
                        if deck_builder_renderer.popup_card_name:
                            deck_builder_renderer.hide_card_popup()
                        elif deck_builder_renderer.show_load_popup:
                            deck_builder_renderer.hide_load_popup()
                        elif deck_builder_renderer.show_confirm_popup:
                            deck_builder_renderer.hide_confirmation()
                        else:
                            if app_state == AppState.DECK_SELECT:
                                local_game_state = create_local_game_state()
                            app_state = AppState.MENU

                elif app_state == AppState.SQUAD_SELECT:
                    sr = (network_prep_state and network_prep_state.get('squad_renderer')) or local_game_state.get('squad_renderer')
                    if sr and event.key == pygame.K_ESCAPE and sr.popup_card_name:
                        sr.hide_card_popup()

                elif app_state == AppState.SQUAD_PLACE:
                    if event.key == pygame.K_ESCAPE and renderer.popup_card:
                        renderer.hide_popup()

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if app_state == AppState.NETWORK_LOBBY and network_ui:
                    gx, gy = renderer.screen_to_game_coords(*event.pos)
                    mouse_event = pygame.event.Event(event.type, pos=(gx, gy), button=event.button)
                    network_ui.handle_mouse_event(mouse_event)
                elif app_state == AppState.GAME:
                    renderer.stop_popup_drag()
                    renderer.stop_log_scrollbar_drag()
                elif app_state == AppState.NETWORK_GAME:
                    renderer.stop_popup_drag()
                    renderer.stop_log_scrollbar_drag()
                    # Handle chat mouse up for drag selection
                    if network_chat:
                        gx, gy = renderer.screen_to_game_coords(*event.pos)
                        chat_event = pygame.event.Event(event.type, pos=(gx, gy), button=event.button)
                        network_chat.handle_event(chat_event)
                elif app_state == AppState.SETTINGS:
                    # Handle mouse up for nickname input drag selection
                    if renderer.settings_nickname_input.active and renderer.settings_nickname_rect:
                        gx, gy = renderer.screen_to_game_coords(*event.pos)
                        renderer.settings_nickname_input.handle_mouse_event(
                            pygame.event.Event(event.type, pos=(gx, gy), button=event.button),
                            renderer.settings_nickname_rect, renderer.font_medium
                        )
                elif app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder_renderer:
                    deck_builder_renderer.stop_scrollbar_drag()
                    # Handle mouse up for text input drag selection
                    if deck_builder_renderer.text_input_active:
                        gx, gy = renderer.screen_to_game_coords(*event.pos)
                        mouse_event = pygame.event.Event(event.type, pos=(gx, gy), button=event.button)
                        deck_builder_renderer.handle_text_mouse_event(mouse_event)
                elif app_state == AppState.SQUAD_PLACE:
                    # Get from network prep or local state
                    if network_prep_state and network_prep_state.get('placement_state'):
                        ps = network_prep_state['placement_state']
                        pr = network_prep_state['placement_renderer']
                    else:
                        ps = local_game_state.get('placement_state')
                        pr = local_game_state.get('placement_renderer')
                    if ps and pr and ps.dragging_card:
                        mx, my = renderer.screen_to_game_coords(*event.pos)
                        drop_pos = pr.get_drop_position(mx, my, ps)
                        if drop_pos is not None:
                            ps.place_card(ps.dragging_card, drop_pos)
                        ps.stop_drag()

            elif event.type == pygame.MOUSEMOTION:
                gx, gy = renderer.screen_to_game_coords(*event.pos)
                if app_state == AppState.GAME:
                    if renderer.dragging_popup:
                        renderer.drag_popup(gx, gy)
                    elif renderer.log_scrollbar_dragging:
                        renderer.drag_log_scrollbar(gy)
                elif app_state == AppState.NETWORK_GAME:
                    if renderer.dragging_popup:
                        renderer.drag_popup(gx, gy)
                    elif renderer.log_scrollbar_dragging:
                        renderer.drag_log_scrollbar(gy)
                    if network_chat:
                        # Always pass motion to chat for drag selection
                        network_chat.handle_event(pygame.event.Event(event.type, pos=(gx, gy), rel=event.rel, buttons=event.buttons))
                elif app_state == AppState.NETWORK_LOBBY and network_ui:
                    # Create event with game coords for text input
                    mouse_event = pygame.event.Event(event.type, pos=(gx, gy), rel=event.rel, buttons=event.buttons)
                    network_ui.handle_mouse_event(mouse_event)
                elif app_state == AppState.SETTINGS:
                    # Handle drag selection for nickname input
                    if renderer.settings_nickname_input.active and renderer.settings_nickname_rect:
                        renderer.settings_nickname_input.handle_mouse_event(
                            pygame.event.Event(event.type, pos=(gx, gy), rel=event.rel, buttons=event.buttons),
                            renderer.settings_nickname_rect, renderer.font_medium
                        )
                elif app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder_renderer:
                    if deck_builder_renderer.text_input_active:
                        # Handle drag selection for text input
                        mouse_event = pygame.event.Event(event.type, pos=(gx, gy), rel=event.rel, buttons=event.buttons)
                        deck_builder_renderer.handle_text_mouse_event(mouse_event)
                    elif deck_builder_renderer.dragging_scrollbar:
                        deck_builder_renderer.drag_scrollbar(gy)

            elif event.type == pygame.MOUSEWHEEL:
                mx, my = renderer.screen_to_game_coords(*pygame.mouse.get_pos())
                if app_state == AppState.GAME and game and client:
                    # Side panel scroll
                    if mx < 200 and renderer.expanded_panel_p2:
                        renderer.scroll_side_panel(event.y, f'p2_{renderer.expanded_panel_p2}')
                    elif 800 < mx < 990 and renderer.expanded_panel_p1:
                        renderer.scroll_side_panel(event.y, f'p1_{renderer.expanded_panel_p1}')
                    elif mx > 960:
                        if my < 240:
                            renderer.scroll_card_info(-event.y)
                        else:
                            renderer.scroll_log(-event.y, game)
                    else:
                        renderer.scroll_log(-event.y, game)
                elif app_state == AppState.NETWORK_GAME and network_game and network_game_client:
                    # Check if chat wants the scroll event
                    if network_chat and network_chat.handle_event(event):
                        pass  # Chat consumed it
                    # Side panel scroll
                    elif mx < 200 and renderer.expanded_panel_p2:
                        renderer.scroll_side_panel(event.y, f'p2_{renderer.expanded_panel_p2}')
                    elif 800 < mx < 990 and renderer.expanded_panel_p1:
                        renderer.scroll_side_panel(event.y, f'p1_{renderer.expanded_panel_p1}')
                    elif mx > 960:
                        if my < 240:
                            renderer.scroll_card_info(-event.y)
                        else:
                            renderer.scroll_log(-event.y, network_game)
                    else:
                        renderer.scroll_log(-event.y, network_game)
                elif app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder_renderer:
                    from src.constants import UILayout, scaled
                    if my < scaled(UILayout.DECK_BUILDER_DECK_Y):
                        deck_builder_renderer.scroll_library(event.y)
                    else:
                        deck_builder_renderer.scroll_deck(event.y)
                elif app_state == AppState.SQUAD_SELECT:
                    sr = (network_prep_state and network_prep_state.get('squad_renderer')) or local_game_state.get('squad_renderer')
                    if sr:
                        from src.constants import UILayout, scaled
                        if my < scaled(UILayout.DECK_BUILDER_DECK_Y):
                            sr.scroll_hand(event.y)
                        else:
                            sr.scroll_squad(event.y)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = renderer.screen_to_game_coords(*event.pos)

                if event.button == 1:
                    # Menu
                    if app_state == AppState.MENU:
                        btn = renderer.get_clicked_menu_button(mx, my)
                        if btn == 'test_game':
                            server = MatchServer()
                            server.setup_game()
                            server.game.auto_place_for_testing()
                            client_p1 = LocalMatchClient(server, player=1)
                            client_p2 = LocalMatchClient(server, player=2)
                            game = server.game
                            match_client = client_p1  # P1 starts
                            client = match_client.game_client
                            is_test_game = True
                            app_state = AppState.GAME
                        elif btn == 'local_game':
                            local_game_state = create_local_game_state()
                            deck_builder = DeckBuilder()
                            s, ci, _, f = renderer.get_deck_builder_resources()
                            deck_builder_renderer = DeckBuilderRenderer(s, ci, f)
                            deck_builder_renderer.selection_mode = True
                            deck_builder_renderer.custom_header = "Выбор колоды - Игрок 1"
                            app_state = AppState.DECK_SELECT
                        elif btn == 'deck_builder':
                            deck_builder = DeckBuilder()
                            s, ci, _, f = renderer.get_deck_builder_resources()
                            deck_builder_renderer = DeckBuilderRenderer(s, ci, f)
                            app_state = AppState.DECK_BUILDER
                        elif btn == 'network_game':
                            # Go to network lobby first, deck/squad/placement after ready
                            network_ui = NetworkUI(
                                screen=renderer.screen,
                                font_large=renderer.font_large,
                                font_medium=renderer.font_medium,
                                font_small=renderer.font_small,
                            )

                            # Callback when both players ready - start deck selection
                            def on_both_ready():
                                nonlocal app_state, network_prep_state, deck_builder, deck_builder_renderer
                                network_prep_state = create_network_prep_state()
                                deck_builder = DeckBuilder()
                                s, ci, _, f = renderer.get_deck_builder_resources()
                                deck_builder_renderer = DeckBuilderRenderer(s, ci, f)
                                deck_builder_renderer.selection_mode = True
                                deck_builder_renderer.custom_header = "Выбор колоды - Сетевая игра"
                                app_state = AppState.DECK_SELECT

                            # Callback when game actually starts (server has both placements)
                            def on_network_game_start(player: int, snapshot: dict):
                                nonlocal app_state, network_game, network_player, network_game_client, network_client, network_prep_state, network_chat
                                nonlocal draw_offered_by_us, draw_offered_by_opponent, draw_button_flash_timer
                                network_player = player
                                network_game = Game.from_dict(snapshot)
                                network_game_client = GameClient(network_game, player)
                                # Set network_client now that game is starting
                                network_client = network_ui.client
                                network_prep_state = None
                                # Create chat UI with position from constants
                                from src.constants import scaled, UILayout
                                network_chat = ChatUI()
                                network_chat.x = scaled(UILayout.CHAT_X)
                                network_chat.y = scaled(UILayout.CHAT_Y)
                                network_chat.width = scaled(UILayout.CHAT_WIDTH)
                                network_chat.height = scaled(UILayout.CHAT_HEIGHT)
                                network_chat.input_height = scaled(UILayout.CHAT_INPUT_HEIGHT)
                                network_chat.set_fonts(renderer.font_medium, renderer.font_small)
                                network_chat.my_player_number = network_player
                                network_chat.on_send = lambda text: network_client.send_chat(text) if network_client else None
                                # Set up chat and draw callbacks
                                if network_client:
                                    network_client.on_chat = lambda name, text, pnum: network_chat.add_message(name, text, pnum)

                                    def on_draw_offered(pnum):
                                        nonlocal draw_offered_by_opponent, draw_button_flash_timer
                                        print(f"[DEBUG] Draw offered by player {pnum}")
                                        draw_offered_by_opponent = True
                                        draw_button_flash_timer = 120  # Flash for 2 seconds at 60fps
                                    network_client.on_draw_offered = on_draw_offered

                                # Reset draw state
                                draw_offered_by_us = False
                                draw_offered_by_opponent = False
                                draw_button_flash_timer = 0
                                app_state = AppState.NETWORK_GAME

                            # Set up update callback for visual effects
                            def on_network_update(result):
                                nonlocal network_game, network_game_client
                                # Update game reference from client's authoritative state
                                if network_ui.client and network_ui.client.game:
                                    network_game = network_ui.client.game
                                    # IMPORTANT: Also update GameClient's game reference
                                    if network_game_client:
                                        network_game_client.game = network_game
                                        # Refresh UI state after game state change
                                        network_game_client.refresh_selection()
                                if result.events and network_game:
                                    process_events(network_game, renderer, result.events)

                            # Callback to set up on_update when client connects
                            def on_client_connected():
                                if network_ui.client:
                                    network_ui.client.on_update = on_network_update

                            network_ui.on_connected = on_client_connected
                            network_ui.on_both_ready = on_both_ready
                            network_ui.on_game_start = on_network_game_start
                            app_state = AppState.NETWORK_LOBBY
                        elif btn == 'settings':
                            app_state = AppState.SETTINGS
                        elif btn == 'exit':
                            running = False

                    # Settings screen
                    elif app_state == AppState.SETTINGS:
                        # Check if clicking on nickname input
                        if (renderer.settings_nickname_rect and
                            renderer.settings_nickname_rect.collidepoint(mx, my)):
                            if not renderer.settings_nickname_input.active:
                                renderer.settings_nickname_input.activate(renderer.settings_nickname_input.value)
                            renderer.settings_nickname_input.handle_mouse_event(
                                pygame.event.Event(event.type, pos=(mx, my), button=event.button),
                                renderer.settings_nickname_rect, renderer.font_medium
                            )
                        else:
                            # Clicked outside input - deactivate and save
                            if renderer.settings_nickname_input.active:
                                renderer.settings_nickname_input.deactivate()
                                from src.settings import set_nickname
                                set_nickname(renderer.settings_nickname_input.value)

                        btn = renderer.get_clicked_settings_button(mx, my)
                        if btn == 'back':
                            # Save nickname when leaving settings
                            if renderer.settings_nickname_input.active:
                                renderer.settings_nickname_input.deactivate()
                            from src.settings import set_nickname
                            set_nickname(renderer.settings_nickname_input.value)
                            app_state = AppState.MENU
                        elif btn and btn.startswith('res_'):
                            # Parse resolution from button id (res_WIDTH_HEIGHT)
                            parts = btn.split('_')
                            new_width = int(parts[1])
                            new_height = int(parts[2])
                            current_size = renderer.window.get_size()
                            if (new_width, new_height) != current_size:
                                # Update resolution
                                current_resolution = (new_width, new_height)
                                screen = pygame.display.set_mode(current_resolution, pygame.RESIZABLE)
                                renderer = Renderer(screen)
                                fullscreen = False
                                set_resolution(new_width, new_height)  # Save for next launch

                    # Network lobby
                    elif app_state == AppState.NETWORK_LOBBY and network_ui:
                        # Handle button clicks first (activates input fields)
                        action = network_ui.handle_click(mx, my)
                        # Process action first to activate input field
                        if action:
                            result = network_ui.process_action(action)
                            if result == 'back':
                                network_ui = None
                                app_state = AppState.MENU
                                continue
                        # Then handle mouse for text input cursor/selection
                        mouse_event = pygame.event.Event(event.type, pos=(mx, my), button=event.button)
                        network_ui.handle_mouse_event(mouse_event)

                    # Deck builder / Deck select (shared logic)
                    elif app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder_renderer:
                        if deck_builder_renderer.popup_card_name:
                            deck_builder_renderer.hide_card_popup()
                        elif deck_builder_renderer.show_load_popup:
                            deck_path = deck_builder_renderer.get_clicked_load_deck(mx, my)
                            if deck_path:
                                deck_builder.load(deck_path)
                                deck_builder_renderer.hide_load_popup()
                        elif deck_builder_renderer.text_input_active:
                            # Handle mouse events for text input
                            mouse_event = pygame.event.Event(event.type, pos=(mx, my), button=event.button)
                            deck_builder_renderer.handle_text_mouse_event(mouse_event)
                        elif deck_builder_renderer.show_confirm_popup:
                            choice = deck_builder_renderer.get_clicked_confirm_button(mx, my)
                            if choice:
                                deck_builder_renderer.handle_confirm_action(choice, deck_builder)
                        elif deck_builder_renderer.start_scrollbar_drag(mx, my):
                            pass
                        else:
                            btn = deck_builder_renderer.get_clicked_button(mx, my)
                            if btn:
                                if app_state == AppState.DECK_SELECT and btn == 'confirm_selection':
                                    if deck_builder.is_valid():
                                        deck_cards = deck_builder.get_deck_card_list()
                                        # Check if preparing for network game
                                        if network_prep_state is not None:
                                            network_prep_state['deck'] = deck_cards
                                            # Use actual player number from network UI
                                            my_player = network_ui.my_player_number if network_ui else 1
                                            sb = SquadBuilder(player=my_player, deck_cards=deck_cards)
                                            s, ci, _, f = renderer.get_deck_builder_resources()
                                            sr = SquadBuilderRenderer(s, ci, f)
                                            sr.custom_header = "Набор отряда - Сетевая игра"
                                            network_prep_state['squad_builder'] = sb
                                            network_prep_state['squad_renderer'] = sr
                                            app_state = AppState.SQUAD_SELECT
                                        else:
                                            # Local game flow
                                            player = local_game_state['current_player']
                                            if player == 1:
                                                local_game_state['deck_p1'] = deck_cards
                                                local_game_state['current_player'] = 2
                                                deck_builder = DeckBuilder()
                                                s, ci, _, f = renderer.get_deck_builder_resources()
                                                deck_builder_renderer = DeckBuilderRenderer(s, ci, f)
                                                deck_builder_renderer.selection_mode = True
                                                deck_builder_renderer.custom_header = "Выбор колоды - Игрок 2"
                                            else:
                                                local_game_state['deck_p2'] = deck_cards
                                                local_game_state['current_player'] = 1
                                                sb = SquadBuilder(player=1, deck_cards=local_game_state['deck_p1'])
                                                s, ci, _, f = renderer.get_deck_builder_resources()
                                                sr = SquadBuilderRenderer(s, ci, f)
                                                local_game_state['squad_builder'] = sb
                                                local_game_state['squad_renderer'] = sr
                                                app_state = AppState.SQUAD_SELECT
                                    else:
                                        deck_builder_renderer.show_notification("Колода должна содержать 30-50 карт")
                                elif btn == 'back':
                                    if app_state == AppState.DECK_SELECT:
                                        if network_prep_state is not None:
                                            network_prep_state = None
                                        else:
                                            local_game_state = create_local_game_state()
                                    app_state = AppState.MENU
                                else:
                                    result = deck_builder_renderer.handle_button_action(btn, deck_builder)
                                    if result == 'back':
                                        app_state = AppState.MENU
                            else:
                                # Card/deck list clicks
                                deck_path = deck_builder_renderer.get_clicked_deck_list_item(mx, my)
                                if deck_path:
                                    if app_state == AppState.DECK_BUILDER:
                                        deck_builder_renderer.handle_deck_list_click(deck_path, deck_builder)
                                    else:
                                        deck_builder.load(deck_path)
                                else:
                                    card = deck_builder_renderer.get_clicked_library_card(mx, my)
                                    if card:
                                        deck_builder.add_card(card)
                                    else:
                                        card = deck_builder_renderer.get_clicked_deck_card(mx, my)
                                        if card:
                                            deck_builder.remove_card(card)

                    # Squad selection
                    elif app_state == AppState.SQUAD_SELECT:
                        # Get squad builder/renderer from appropriate state
                        if network_prep_state and network_prep_state['squad_renderer']:
                            sb = network_prep_state['squad_builder']
                            sr = network_prep_state['squad_renderer']
                        elif local_game_state['squad_renderer']:
                            sb = local_game_state['squad_builder']
                            sr = local_game_state['squad_renderer']
                        else:
                            sb = sr = None

                        if sb and sr:
                            if sr.popup_card_name:
                                sr.hide_card_popup()
                            else:
                                btn = sr.get_clicked_button(mx, my)
                                if btn == 'mulligan':
                                    if sb.mulligan():
                                        sr.show_notification("Карты пересданы")
                                    else:
                                        sr.show_notification("Недостаточно золота")
                                elif btn == 'confirm':
                                    if sb.is_valid():
                                        squad = sb.finalize()
                                        # Check if preparing for network game
                                        if network_prep_state is not None:
                                            network_prep_state['squad'] = squad
                                            # Use actual player number from network UI
                                            my_player = network_ui.my_player_number if network_ui else 1
                                            ps = PlacementState(player=my_player, squad_cards=squad)
                                            s, ci, _, f = renderer.get_deck_builder_resources()
                                            pr = PlacementRenderer(s, ci, f)
                                            pr.custom_header = "Расстановка - Сетевая игра"
                                            network_prep_state['placement_state'] = ps
                                            network_prep_state['placement_renderer'] = pr
                                            app_state = AppState.SQUAD_PLACE
                                        else:
                                            # Local game flow
                                            player = local_game_state['current_player']
                                            if player == 1:
                                                local_game_state['squad_p1'] = squad
                                                local_game_state['current_player'] = 2
                                                sb = SquadBuilder(player=2, deck_cards=local_game_state['deck_p2'])
                                                s, ci, _, f = renderer.get_deck_builder_resources()
                                                sr = SquadBuilderRenderer(s, ci, f)
                                                local_game_state['squad_builder'] = sb
                                                local_game_state['squad_renderer'] = sr
                                            else:
                                                local_game_state['squad_p2'] = squad
                                                local_game_state['current_player'] = 1
                                                ps = PlacementState(player=1, squad_cards=local_game_state['squad_p1'])
                                                s, ci, _, f = renderer.get_deck_builder_resources()
                                                pr = PlacementRenderer(s, ci, f)
                                                local_game_state['placement_state'] = ps
                                                local_game_state['placement_renderer'] = pr
                                                app_state = AppState.SQUAD_PLACE
                                elif not btn:
                                    card = sr.get_clicked_hand_card(mx, my)
                                    if card:
                                        if not sb.add_card(card):
                                            _, reason = sb.can_add_card(card)
                                            sr.show_notification(reason)
                                    else:
                                        card = sr.get_clicked_squad_card(mx, my)
                                        if card:
                                            sb.remove_card(card)

                    # Placement phase
                    elif app_state == AppState.SQUAD_PLACE:
                        # Get placement state from appropriate source
                        if network_prep_state and network_prep_state['placement_state']:
                            ps = network_prep_state['placement_state']
                            pr = network_prep_state['placement_renderer']
                        elif local_game_state['placement_state']:
                            ps = local_game_state['placement_state']
                            pr = local_game_state['placement_renderer']
                        else:
                            ps = pr = None

                        if ps and pr:
                            if pr.is_confirm_clicked(mx, my) and ps.is_complete():
                                # Don't allow confirm if already waiting
                                if network_prep_state and network_prep_state.get('waiting_for_opponent'):
                                    pass  # Already sent, just waiting
                                else:
                                    placed_cards = ps.finalize()
                                    # Check if preparing for network game
                                    if network_prep_state is not None:
                                        network_prep_state['placed_cards'] = placed_cards
                                        # Send placement to server and wait (convert cards to dicts for serialization)
                                        if network_ui and network_ui.client:
                                            placed_cards_data = [card.to_dict() for card in placed_cards]
                                            network_ui.client.send_placement_done(placed_cards_data)
                                            network_prep_state['waiting_for_opponent'] = True
                                    else:
                                        # Local game flow
                                        player = local_game_state['current_player']
                                        if player == 1:
                                            local_game_state['placed_cards_p1'] = placed_cards
                                            local_game_state['current_player'] = 2
                                            ps = PlacementState(player=2, squad_cards=local_game_state['squad_p2'])
                                            s, ci, _, f = renderer.get_deck_builder_resources()
                                            pr = PlacementRenderer(s, ci, f)
                                            local_game_state['placement_state'] = ps
                                            local_game_state['placement_renderer'] = pr
                                        else:
                                            local_game_state['placed_cards_p2'] = placed_cards
                                            server = MatchServer()
                                            server.setup_with_placement(
                                                local_game_state['placed_cards_p1'],
                                                local_game_state['placed_cards_p2']
                                            )
                                            client_p1 = LocalMatchClient(server, player=1)
                                            client_p2 = LocalMatchClient(server, player=2)
                                            game = server.game
                                            match_client = client_p1  # P1 starts
                                            client = match_client.game_client
                                            app_state = AppState.GAME
                            else:
                                card = pr.get_unplaced_card_at(mx, my)
                                if card:
                                    ox, oy = pr.get_card_center_offset()
                                    ps.start_drag(card, ox, oy)
                                else:
                                    pos = pr.get_placed_position_at(mx, my)
                                    if pos is not None:
                                        card = ps.unplace_card(pos)
                                        if card:
                                            ox, oy = pr.get_card_center_offset()
                                            ps.start_drag(card, ox, oy)

                    # Game state - use refactored click handler
                    elif app_state == AppState.GAME and client_p1 and game and client:
                        if show_pause_menu:
                            btn = renderer.get_clicked_pause_button(mx, my)
                            if btn == "resume":
                                show_pause_menu = False
                            elif btn == "concede":
                                # In local game, just end the game
                                game.winner = 2 if game.current_player == 1 else 1
                                game.phase = GamePhase.GAME_OVER
                                show_pause_menu = False
                            elif btn == "exit":
                                # Exit to menu
                                show_pause_menu = False
                                server = None
                                client_p1 = None
                                client_p2 = None
                                match_client = None
                                game = None
                                client = None
                                is_test_game = False
                                test_game_controlled_player = None
                                app_state = AppState.MENU
                                local_game_state = create_local_game_state()
                            elif btn and btn.startswith("res_"):
                                parts = btn.split("_")
                                if len(parts) == 3:
                                    new_w, new_h = int(parts[1]), int(parts[2])
                                    current_resolution = (new_w, new_h)
                                    screen = pygame.display.set_mode(current_resolution, pygame.RESIZABLE)
                                    renderer.handle_resize(screen)
                                    set_resolution(new_w, new_h)
                        elif renderer.game_over_popup:
                            if renderer.is_game_over_button_clicked(mx, my):
                                renderer.hide_game_over_popup()
                                server = None
                                client_p1 = None
                                client_p2 = None
                                match_client = None
                                game = None
                                client = None
                                is_test_game = False
                                test_game_controlled_player = None
                                app_state = AppState.MENU
                                local_game_state = create_local_game_state()
                        elif renderer.popup_card:
                            renderer.hide_popup()
                        else:
                            handle_game_left_click(match_client, game, client, renderer, mx, my)

                    # Network game state
                    elif app_state == AppState.NETWORK_GAME and network_game and network_game_client:
                        # Check chat click first (convert to game coords)
                        if network_chat:
                            chat_event = pygame.event.Event(event.type, pos=(mx, my), button=event.button)
                            if network_chat.handle_event(chat_event):
                                pass  # Chat consumed the event
                                continue

                        # Check draw button click
                        if draw_button_rect and draw_button_rect.collidepoint(mx, my):
                            if draw_offered_by_opponent:
                                # Accept the draw
                                if network_client:
                                    print(f"[DEBUG] Accepting draw, client state: {network_client.state}")
                                    network_client.send_draw_accept()
                            elif not draw_offered_by_us:
                                # Offer a draw
                                if network_client:
                                    print(f"[DEBUG] Offering draw, client state: {network_client.state}")
                                    network_client.send_draw_offer()
                                    draw_offered_by_us = True
                                else:
                                    print("[DEBUG] No network_client!")
                            continue

                        if show_pause_menu:
                            # Handle pause menu clicks
                            btn = renderer.get_clicked_pause_button(mx, my)
                            if btn == "resume":
                                show_pause_menu = False
                            elif btn == "concede":
                                send_network_command(network_client, cmd_concede(network_player))
                                show_pause_menu = False
                            elif btn and btn.startswith("res_"):
                                # Resolution change
                                parts = btn.split("_")
                                if len(parts) == 3:
                                    new_w, new_h = int(parts[1]), int(parts[2])
                                    current_resolution = (new_w, new_h)
                                    screen = pygame.display.set_mode(current_resolution, pygame.RESIZABLE)
                                    renderer.handle_resize(screen)
                                    set_resolution(new_w, new_h)  # Save for next launch
                        elif renderer.game_over_popup:
                            if renderer.is_game_over_button_clicked(mx, my):
                                renderer.hide_game_over_popup()
                                network_game = None
                                network_game_client = None
                                network_client = None
                                network_player = 0
                                network_ui = None
                                network_chat = None
                                # Reset draw state
                                draw_offered_by_us = False
                                draw_offered_by_opponent = False
                                draw_button_flash_timer = 0
                                draw_button_rect = None
                                app_state = AppState.MENU
                        elif renderer.popup_card:
                            renderer.hide_popup()
                        else:
                            # Handle network game clicks
                            handle_network_game_click(
                                network_client, network_game, network_game_client,
                                renderer, mx, my, network_player
                            )

                elif event.button == 3:  # Right click
                    if app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder_renderer:
                        if deck_builder_renderer.popup_card_name:
                            deck_builder_renderer.hide_card_popup()
                        else:
                            card = deck_builder_renderer.get_clicked_library_card(mx, my)
                            if not card:
                                card = deck_builder_renderer.get_clicked_deck_card(mx, my)
                            if card:
                                deck_builder_renderer.show_card_popup(card)

                    elif app_state == AppState.SQUAD_SELECT:
                        sr = (network_prep_state and network_prep_state.get('squad_renderer')) or local_game_state.get('squad_renderer')
                        if sr:
                            if sr.popup_card_name:
                                sr.hide_card_popup()
                            else:
                                card = sr.get_clicked_hand_card(mx, my)
                                if not card:
                                    card = sr.get_clicked_squad_card(mx, my)
                                if card:
                                    sr.show_card_popup(card)

                    elif app_state == AppState.SQUAD_PLACE:
                        if network_prep_state and network_prep_state.get('placement_state'):
                            ps = network_prep_state['placement_state']
                            pr = network_prep_state['placement_renderer']
                        else:
                            ps = local_game_state.get('placement_state')
                            pr = local_game_state.get('placement_renderer')
                        if ps and pr:
                            if renderer.popup_card:
                                renderer.hide_popup()
                            else:
                                card = pr.get_card_at(mx, my, ps)
                                if card:
                                    renderer.show_popup(card)

                    elif app_state == AppState.GAME and game and client:
                        if renderer.popup_card:
                            renderer.hide_popup()
                        else:
                            card = renderer.get_card_at_screen_pos(game, mx, my)
                            if card:
                                renderer.show_popup(card)
                            else:
                                card = renderer.get_graveyard_card_at_pos(game, mx, my)
                                if card:
                                    renderer.show_popup(card)
                                else:
                                    # Client-side deselection
                                    client.deselect()

                    elif app_state == AppState.NETWORK_GAME and network_game and network_game_client:
                        if renderer.popup_card:
                            renderer.hide_popup()
                        else:
                            card = renderer.get_card_at_screen_pos(network_game, mx, my)
                            if card:
                                renderer.show_popup(card)
                            else:
                                card = renderer.get_graveyard_card_at_pos(network_game, mx, my)
                                if card:
                                    renderer.show_popup(card)
                                else:
                                    network_game_client.deselect()

        # Process any remaining game events (from turn start triggers, etc.)
        if app_state == AppState.GAME and game and client:
            events = game.pop_events()
            if events:
                process_events(game, renderer, events)

        # Render
        dt = clock.tick(FPS) / 1000.0
        if app_state == AppState.MENU:
            renderer.draw_menu()
        elif app_state == AppState.SETTINGS:
            # Get current window size for highlighting
            current_res = (renderer.window.get_width(), renderer.window.get_height())
            renderer.draw_settings(current_res)
        elif app_state == AppState.NETWORK_LOBBY and network_ui:
            network_ui.update()  # Poll for network events
            network_ui.draw()
            renderer.finalize_frame()
        elif app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder and deck_builder_renderer:
            deck_builder_renderer.update_notification()
            _, _, cif, _ = renderer.get_deck_builder_resources()
            deck_builder_renderer.draw(deck_builder, cif)
            renderer.finalize_frame()
        elif app_state == AppState.SQUAD_SELECT:
            # Get from network prep or local state
            if network_prep_state and network_prep_state.get('squad_builder'):
                sr = network_prep_state['squad_renderer']
                sb = network_prep_state['squad_builder']
            else:
                sr = local_game_state.get('squad_renderer')
                sb = local_game_state.get('squad_builder')
            if sr and sb:
                sr.update_notification()
                _, _, cif, _ = renderer.get_deck_builder_resources()
                sr.draw(sb, cif)
                renderer.finalize_frame()
        elif app_state == AppState.SQUAD_PLACE:
            # Get from network prep or local state
            if network_prep_state and network_prep_state.get('placement_state'):
                ps = network_prep_state['placement_state']
                pr = network_prep_state['placement_renderer']
                # Poll network client for game start
                if network_ui and network_ui.client:
                    network_ui.client.poll()
            else:
                ps = local_game_state.get('placement_state')
                pr = local_game_state.get('placement_renderer')
            if ps and pr:
                mouse_pos = renderer.screen_to_game_coords(*pygame.mouse.get_pos())
                pr.draw(ps, mouse_pos)
                # Show waiting message if waiting for opponent
                if network_prep_state and network_prep_state.get('waiting_for_opponent'):
                    # Draw slim banner at bottom
                    banner_height = 50
                    banner_y = 720 - banner_height - 20
                    banner = pygame.Surface((400, banner_height), pygame.SRCALPHA)
                    banner.fill((0, 0, 0, 200))
                    renderer.screen.blit(banner, (440, banner_y))
                    text = renderer.font_medium.render("Ожидание противника...", True, (255, 255, 255))
                    text_rect = text.get_rect(center=(640, banner_y + banner_height // 2))
                    renderer.screen.blit(text, text_rect)
                if renderer.popup_card:
                    renderer.draw_popup()
                renderer.finalize_frame()
        elif app_state == AppState.GAME and game and client:
            client.update(dt)  # Update UI animations
            if game.phase == GamePhase.GAME_OVER and not renderer.game_over_popup:
                winner = game.board.check_winner()
                renderer.show_game_over_popup(winner if winner is not None else 0)
            renderer.draw(game, dt, client.ui, skip_flip=show_pause_menu)
            # Draw pause menu overlay if active
            if show_pause_menu:
                renderer.draw_pause_menu(current_resolution, is_network_game=False)
                renderer.finalize_frame()
        elif app_state == AppState.NETWORK_GAME and network_game and network_game_client:
            # Poll for network updates
            if network_client:
                network_client.poll()
                # Update game from network client's game state
                if network_client.game:
                    network_game = network_client.game
                    # IMPORTANT: Also update GameClient's game reference
                    network_game_client.game = network_game

            network_game_client.update(dt)
            if network_game.phase == GamePhase.GAME_OVER and not renderer.game_over_popup:
                # Use game.winner if set (from concede), otherwise check board
                winner = network_game.winner if network_game.winner is not None else network_game.board.check_winner()
                # Get player names from network UI
                p1_name, p2_name = None, None
                if network_ui:
                    if network_ui.my_player_number == 1:
                        p1_name = network_ui.player_name
                        p2_name = network_ui.opponent_name
                    else:
                        p1_name = network_ui.opponent_name
                        p2_name = network_ui.player_name
                renderer.show_game_over_popup(winner if winner is not None else 0, p1_name, p2_name)
            # Draw game, skip flip if pause menu or chat needs to be drawn
            has_chat = network_chat is not None
            renderer.draw(network_game, dt, network_game_client.ui, skip_flip=show_pause_menu or has_chat)
            # Draw chat on the left side
            if network_chat:
                from src.constants import scaled, UILayout
                network_chat.x = scaled(UILayout.CHAT_X)
                network_chat.y = scaled(UILayout.CHAT_Y)
                network_chat.width = scaled(UILayout.CHAT_WIDTH)
                network_chat.height = scaled(UILayout.CHAT_HEIGHT)
                network_chat.input_height = scaled(UILayout.CHAT_INPUT_HEIGHT)
                network_chat.draw(renderer.screen)

                # Draw the draw offer button below chat
                btn_x = scaled(UILayout.CHAT_X)
                btn_y = scaled(UILayout.CHAT_Y) + scaled(UILayout.CHAT_HEIGHT) + scaled(UILayout.DRAW_BUTTON_OFFSET_Y)
                btn_w = scaled(UILayout.CHAT_WIDTH)
                btn_h = scaled(UILayout.DRAW_BUTTON_HEIGHT)
                draw_button_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

                # Determine button state and colors
                if draw_offered_by_opponent:
                    # Opponent offered - show accept button with flash effect
                    if draw_button_flash_timer > 0:
                        draw_button_flash_timer -= 1
                        # Flash between two colors
                        if (draw_button_flash_timer // 10) % 2 == 0:
                            btn_color = UILayout.DRAW_BUTTON_ACCEPT_BG_FLASH
                        else:
                            btn_color = UILayout.DRAW_BUTTON_ACCEPT_BG_DARK
                    else:
                        btn_color = UILayout.DRAW_BUTTON_ACCEPT_BG
                    btn_text = "Принять ничью"
                    text_color = UILayout.DRAW_BUTTON_ACCEPT_TEXT
                elif draw_offered_by_us:
                    # We offered - show waiting state
                    btn_color = UILayout.DRAW_BUTTON_WAITING_BG
                    btn_text = "Ожидание..."
                    text_color = UILayout.DRAW_BUTTON_WAITING_TEXT
                else:
                    # Default state
                    btn_color = UILayout.DRAW_BUTTON_BG
                    btn_text = "Предложить ничью"
                    text_color = UILayout.DRAW_BUTTON_TEXT

                pygame.draw.rect(renderer.screen, btn_color, draw_button_rect)
                pygame.draw.rect(renderer.screen, UILayout.DRAW_BUTTON_BORDER, draw_button_rect, 1)

                # Render button text
                text_surface = renderer.font_small.render(btn_text, True, text_color)
                text_x = btn_x + (btn_w - text_surface.get_width()) // 2
                text_y = btn_y + (btn_h - text_surface.get_height()) // 2
                renderer.screen.blit(text_surface, (text_x, text_y))

                if not show_pause_menu:
                    renderer.finalize_frame()
            # Draw pause menu overlay if active
            if show_pause_menu:
                renderer.draw_pause_menu(current_resolution, is_network_game=True)
                renderer.finalize_frame()  # Scale screen to window and flip

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
