"""
Berserk Digital Card Game - MVP
Hot-seat mode for two players on the same computer.
"""
import pygame
import sys

from src.constants import WINDOW_WIDTH, WINDOW_HEIGHT, FPS, GamePhase, AppState
from src.game import Game
from src.renderer import Renderer
from src.commands import (
    cmd_select_position,
    cmd_move, cmd_attack, cmd_prepare_flyer_attack,
    cmd_use_ability, cmd_use_instant,
    cmd_confirm, cmd_cancel, cmd_choose_position, cmd_choose_card,
    cmd_choose_amount, cmd_pass_priority, cmd_skip, cmd_end_turn
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


def main():
    """Main game loop."""
    pygame.init()
    pygame.display.set_caption("Берсерк - Цифровая версия")
    pygame.key.set_repeat(300, 30)

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
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

    deck_builder = None
    deck_builder_renderer = None
    local_game_state = create_local_game_state()
    network_ui = None  # Network lobby UI
    network_client = None  # Network client for multiplayer

    running = True
    while running:
        # Switch clients based on whose turn it is (hotseat mode) - must happen before events
        if app_state == AppState.GAME and game and client_p1 and client_p2:
            if game.current_player == 1:
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
                if app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder_renderer:
                    if deck_builder_renderer.text_input_active:
                        deck_builder_renderer.handle_text_input(event)
                elif app_state == AppState.NETWORK_LOBBY and network_ui:
                    network_ui.handle_text_input(event)

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    if fullscreen:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
                    renderer.handle_resize(screen)

                elif app_state == AppState.NETWORK_LOBBY and network_ui:
                    if event.key == pygame.K_ESCAPE:
                        network_ui.disconnect()
                        network_ui = None
                        app_state = AppState.MENU
                    else:
                        network_ui.handle_text_input(event)

                elif app_state == AppState.GAME and game and client and match_client:
                    if event.key == pygame.K_RETURN and game.phase == GamePhase.SETUP:
                        game.finish_placement()
                    elif event.key == pygame.K_y and game.awaiting_heal_confirm:
                        # Use interaction's acting_player for heal confirm
                        player = game.interaction.acting_player if game.interaction else game.current_player
                        send_command(match_client, renderer, cmd_confirm(player, True))
                    elif event.key == pygame.K_n and game.awaiting_heal_confirm:
                        player = game.interaction.acting_player if game.interaction else game.current_player
                        send_command(match_client, renderer, cmd_confirm(player, False))

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

                elif app_state == AppState.SQUAD_SELECT and local_game_state['squad_renderer']:
                    if event.key == pygame.K_ESCAPE and local_game_state['squad_renderer'].popup_card_name:
                        local_game_state['squad_renderer'].hide_card_popup()

                elif app_state == AppState.SQUAD_PLACE and local_game_state['placement_state']:
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
                elif app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder_renderer:
                    deck_builder_renderer.stop_scrollbar_drag()
                elif app_state == AppState.SQUAD_PLACE and local_game_state['placement_state']:
                    ps = local_game_state['placement_state']
                    pr = local_game_state['placement_renderer']
                    if ps.dragging_card:
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
                elif app_state == AppState.NETWORK_LOBBY and network_ui:
                    # Create event with game coords for text input
                    mouse_event = pygame.event.Event(event.type, pos=(gx, gy), rel=event.rel, buttons=event.buttons)
                    network_ui.handle_mouse_event(mouse_event)
                elif app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder_renderer:
                    if deck_builder_renderer.dragging_scrollbar:
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
                elif app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder_renderer:
                    from src.constants import UILayout, scaled
                    if my < scaled(UILayout.DECK_BUILDER_DECK_Y):
                        deck_builder_renderer.scroll_library(event.y)
                    else:
                        deck_builder_renderer.scroll_deck(event.y)
                elif app_state == AppState.SQUAD_SELECT and local_game_state['squad_renderer']:
                    from src.constants import UILayout, scaled
                    if my < scaled(UILayout.DECK_BUILDER_DECK_Y):
                        local_game_state['squad_renderer'].scroll_hand(event.y)
                    else:
                        local_game_state['squad_renderer'].scroll_squad(event.y)

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
                            # Initialize network UI
                            network_ui = NetworkUI(
                                screen=renderer.screen,
                                font_large=renderer.font_large,
                                font_medium=renderer.font_medium,
                                font_small=renderer.font_small,
                            )
                            # Use starter deck for now (TODO: deck selection)
                            network_ui.squad = create_starter_deck()
                            app_state = AppState.NETWORK_LOBBY
                        elif btn == 'exit':
                            running = False

                    # Network lobby
                    elif app_state == AppState.NETWORK_LOBBY and network_ui:
                        # Handle mouse for text input cursor/selection
                        mouse_event = pygame.event.Event(event.type, pos=(mx, my), button=event.button)
                        network_ui.handle_mouse_event(mouse_event)
                        # Handle button clicks
                        action = network_ui.handle_click(mx, my)
                        if action:
                            result = network_ui.process_action(action)
                            if result == 'back':
                                network_ui = None
                                app_state = AppState.MENU

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
                            pass
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
                                        player = local_game_state['current_player']
                                        deck_cards = deck_builder.get_deck_card_list()
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
                    elif app_state == AppState.SQUAD_SELECT and local_game_state['squad_renderer']:
                        sb = local_game_state['squad_builder']
                        sr = local_game_state['squad_renderer']
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
                                    player = local_game_state['current_player']
                                    squad = sb.finalize()
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
                    elif app_state == AppState.SQUAD_PLACE and local_game_state['placement_state']:
                        ps = local_game_state['placement_state']
                        pr = local_game_state['placement_renderer']
                        if pr.is_confirm_clicked(mx, my) and ps.is_complete():
                            player = local_game_state['current_player']
                            cards = ps.finalize()
                            if player == 1:
                                local_game_state['placed_cards_p1'] = cards
                                local_game_state['current_player'] = 2
                                ps = PlacementState(player=2, squad_cards=local_game_state['squad_p2'])
                                s, ci, _, f = renderer.get_deck_builder_resources()
                                pr = PlacementRenderer(s, ci, f)
                                local_game_state['placement_state'] = ps
                                local_game_state['placement_renderer'] = pr
                            else:
                                local_game_state['placed_cards_p2'] = cards
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
                        if renderer.game_over_popup:
                            if renderer.is_game_over_button_clicked(mx, my):
                                renderer.hide_game_over_popup()
                                server = None
                                client_p1 = None
                                client_p2 = None
                                match_client = None
                                game = None
                                client = None
                                app_state = AppState.MENU
                                local_game_state = create_local_game_state()
                        elif renderer.popup_card:
                            renderer.hide_popup()
                        else:
                            handle_game_left_click(match_client, game, client, renderer, mx, my)

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

                    elif app_state == AppState.SQUAD_SELECT and local_game_state['squad_renderer']:
                        sr = local_game_state['squad_renderer']
                        if sr.popup_card_name:
                            sr.hide_card_popup()
                        else:
                            card = sr.get_clicked_hand_card(mx, my)
                            if not card:
                                card = sr.get_clicked_squad_card(mx, my)
                            if card:
                                sr.show_card_popup(card)

                    elif app_state == AppState.SQUAD_PLACE and local_game_state['placement_state']:
                        ps = local_game_state['placement_state']
                        pr = local_game_state['placement_renderer']
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

        # Process any remaining game events (from turn start triggers, etc.)
        if app_state == AppState.GAME and game and client:
            events = game.pop_events()
            if events:
                process_events(game, renderer, events)

        # Render
        dt = clock.tick(FPS) / 1000.0
        if app_state == AppState.MENU:
            renderer.draw_menu()
        elif app_state == AppState.NETWORK_LOBBY and network_ui:
            network_ui.update()  # Poll for network events
            network_ui.draw()
            renderer.finalize_frame()
        elif app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder and deck_builder_renderer:
            deck_builder_renderer.update_notification()
            _, _, cif, _ = renderer.get_deck_builder_resources()
            deck_builder_renderer.draw(deck_builder, cif)
            renderer.finalize_frame()
        elif app_state == AppState.SQUAD_SELECT and local_game_state['squad_builder']:
            sr = local_game_state['squad_renderer']
            sb = local_game_state['squad_builder']
            sr.update_notification()
            _, _, cif, _ = renderer.get_deck_builder_resources()
            sr.draw(sb, cif)
            renderer.finalize_frame()
        elif app_state == AppState.SQUAD_PLACE and local_game_state['placement_state']:
            ps = local_game_state['placement_state']
            pr = local_game_state['placement_renderer']
            mouse_pos = renderer.screen_to_game_coords(*pygame.mouse.get_pos())
            pr.draw(ps, mouse_pos)
            if renderer.popup_card:
                renderer.draw_popup()
            renderer.finalize_frame()
        elif app_state == AppState.GAME and game and client:
            client.update(dt)  # Update UI animations
            if game.phase == GamePhase.GAME_OVER and not renderer.game_over_popup:
                winner = game.board.check_winner()
                renderer.show_game_over_popup(winner if winner is not None else 0)
            renderer.draw(game, dt, client.ui)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
