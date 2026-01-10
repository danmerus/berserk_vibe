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
    cmd_select_card, cmd_select_position, cmd_deselect, cmd_move, cmd_attack,
    cmd_toggle_attack_mode, cmd_use_ability, cmd_use_instant,
    cmd_confirm, cmd_cancel, cmd_choose_position, cmd_choose_card,
    cmd_choose_amount, cmd_pass_priority, cmd_skip, cmd_end_turn
)
from src.deck_builder import DeckBuilder
from src.deck_builder_renderer import DeckBuilderRenderer
from src.squad_builder import SquadBuilder
from src.squad_builder_renderer import SquadBuilderRenderer
from src.placement import PlacementState
from src.placement_renderer import PlacementRenderer


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


def main():
    """Main game loop."""
    pygame.init()
    pygame.display.set_caption("Берсерк - Цифровая версия")
    pygame.key.set_repeat(300, 30)

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    fullscreen = False

    app_state = AppState.MENU
    game = None
    renderer = Renderer(screen)

    deck_builder = None
    deck_builder_renderer = None
    local_game_state = create_local_game_state()

    running = True
    while running:
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

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    if fullscreen:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
                    renderer.handle_resize(screen)

                elif app_state == AppState.GAME and game:
                    if event.key == pygame.K_RETURN and game.phase == GamePhase.SETUP:
                        game.finish_placement()
                    elif event.key == pygame.K_r:
                        game = Game()
                        game.setup_game()
                        game.auto_place_for_testing()
                    elif event.key == pygame.K_y and game.awaiting_heal_confirm:
                        game.process_command(cmd_confirm(game.current_player, True))
                    elif event.key == pygame.K_n and game.awaiting_heal_confirm:
                        game.process_command(cmd_confirm(game.current_player, False))

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
                if app_state == AppState.GAME:
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
                elif app_state in (AppState.DECK_BUILDER, AppState.DECK_SELECT) and deck_builder_renderer:
                    if deck_builder_renderer.dragging_scrollbar:
                        deck_builder_renderer.drag_scrollbar(gy)

            elif event.type == pygame.MOUSEWHEEL:
                mx, my = renderer.screen_to_game_coords(*pygame.mouse.get_pos())
                if app_state == AppState.GAME and game:
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
                            game = Game()
                            game.setup_game()
                            game.auto_place_for_testing()
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
                        elif btn == 'exit':
                            running = False

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
                                game = Game()
                                game.setup_game_with_placement(
                                    local_game_state['placed_cards_p1'],
                                    local_game_state['placed_cards_p2']
                                )
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

                    # Game state
                    elif app_state == AppState.GAME and game:
                        if renderer.game_over_popup:
                            if renderer.is_game_over_button_clicked(mx, my):
                                renderer.hide_game_over_popup()
                                game = None
                                app_state = AppState.MENU
                                local_game_state = create_local_game_state()
                        elif renderer.popup_card:
                            renderer.hide_popup()
                        elif renderer.start_popup_drag(mx, my, game):
                            pass
                        elif renderer.start_log_scrollbar_drag(mx, my):
                            pass
                        elif game.awaiting_priority:
                            if renderer.dice_popup_open:
                                opt = renderer.get_clicked_dice_option(mx, my)
                                if opt == 'cancel':
                                    renderer.close_dice_popup()
                                elif opt:
                                    card = renderer.dice_popup_card
                                    if card:
                                        game.process_command(cmd_use_instant(game.priority_player, card.id, "luck", opt))
                                        renderer.close_dice_popup()
                            elif renderer.get_pass_button_rect().collidepoint(mx, my):
                                renderer.close_dice_popup()
                                game.process_command(cmd_pass_priority(game.priority_player))
                            else:
                                # Allow clicking on cards and abilities during priority
                                ability_id = renderer.get_clicked_ability(mx, my)
                                if ability_id and game.selected_card:
                                    if ability_id == "luck":
                                        renderer.open_dice_popup(game.selected_card)
                                else:
                                    # Try to select a card
                                    pos = renderer.screen_to_pos(mx, my)
                                    if pos is not None:
                                        game.select_card(pos)
                        elif game.awaiting_counter_selection:
                            opt = renderer.get_clicked_counter_button(mx, my)
                            if opt == 'confirm':
                                game.confirm_counter_selection()
                            elif opt == 'cancel':
                                game.process_command(cmd_cancel(game.current_player))
                            elif isinstance(opt, int):
                                game.process_command(cmd_choose_amount(game.current_player, opt))
                        elif game.awaiting_heal_confirm:
                            choice = renderer.get_clicked_heal_button(mx, my)
                            if choice == 'yes':
                                game.process_command(cmd_confirm(game.current_player, True))
                            elif choice == 'no':
                                game.process_command(cmd_confirm(game.current_player, False))
                        elif game.awaiting_exchange_choice:
                            choice = renderer.get_clicked_exchange_button(mx, my)
                            if choice == 'full':
                                game.resolve_exchange_choice(reduce_damage=False)
                            elif choice == 'reduce':
                                game.resolve_exchange_choice(reduce_damage=True)
                        elif game.awaiting_stench_choice:
                            choice = renderer.get_clicked_stench_button(mx, my)
                            if choice == 'tap':
                                game.resolve_stench_choice(tap=True)
                            elif choice == 'damage':
                                game.resolve_stench_choice(tap=False)
                        elif renderer.get_skip_button_rect().collidepoint(mx, my):
                            game.process_command(cmd_skip(game.current_player))
                        elif renderer.handle_side_panel_click(mx, my):
                            pass
                        elif renderer.get_end_turn_button_rect().collidepoint(mx, my):
                            game.process_command(cmd_end_turn(game.current_player))
                        elif renderer.get_clicked_attack_button(mx, my):
                            if game.selected_card:
                                game.process_command(cmd_toggle_attack_mode(game.current_player))
                        else:
                            ability_id = renderer.get_clicked_ability(mx, my)
                            if ability_id and game.selected_card:
                                if game.awaiting_priority and ability_id == "luck":
                                    renderer.open_dice_popup(game.selected_card)
                                else:
                                    game.process_command(cmd_use_ability(
                                        game.current_player,
                                        game.selected_card.id,
                                        ability_id
                                    ))
                            else:
                                pos = renderer.screen_to_pos(mx, my)
                                if pos is not None:
                                    game.handle_click(pos)

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

                    elif app_state == AppState.GAME and game:
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
                                    game.process_command(cmd_deselect(game.current_player))

        # Process visual events
        if app_state == AppState.GAME and game:
            for ve in game.visual_events:
                if ve['type'] == 'damage':
                    renderer.add_floating_text(ve['pos'], f"-{ve['amount']}", (255, 80, 80))
                elif ve['type'] == 'heal':
                    renderer.add_floating_text(ve['pos'], f"+{ve['amount']}", (80, 255, 80))
                elif ve['type'] == 'arrow':
                    color = (100, 255, 100) if ve['arrow_type'] == 'heal' else (255, 100, 100)
                    renderer.add_arrow(ve['from_pos'], ve['to_pos'], color)
                elif ve['type'] == 'clear_arrows':
                    renderer.clear_arrows()
                elif ve['type'] == 'clear_arrows_immediate':
                    renderer.clear_arrows_immediate()
            game.visual_events.clear()

        # Render
        dt = clock.tick(FPS) / 1000.0
        if app_state == AppState.MENU:
            renderer.draw_menu()
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
        elif app_state == AppState.GAME and game:
            if game.phase == GamePhase.GAME_OVER and not renderer.game_over_popup:
                winner = game.board.check_winner()
                renderer.show_game_over_popup(winner if winner is not None else 0)
            renderer.draw(game, dt)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
