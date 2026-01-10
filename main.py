"""
Berserk Digital Card Game - MVP
Hot-seat mode for two players on the same computer.
"""
import pygame
import sys

from src.constants import WINDOW_WIDTH, WINDOW_HEIGHT, FPS, GamePhase
from src.game import Game
from src.renderer import Renderer


def main():
    """Main game loop."""
    pygame.init()
    pygame.display.set_caption("Берсерк - Цифровая версия")

    # Create resizable window
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    fullscreen = False

    game = Game()
    renderer = Renderer(screen)

    # Setup game
    game.setup_game()

    # For quick testing, auto-place cards (comment out for manual placement)
    game.auto_place_for_testing()

    running = True
    while running:
        # Event handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE:
                if not fullscreen:
                    screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    renderer.handle_resize(screen)

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                # F11 - toggle fullscreen
                elif event.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    if fullscreen:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
                    renderer.handle_resize(screen)

                # Space key disabled - use buttons instead

                # Enter to finish placement
                elif event.key == pygame.K_RETURN:
                    if game.phase == GamePhase.SETUP:
                        game.finish_placement()

                # R to restart
                elif event.key == pygame.K_r:
                    game = Game()
                    game.setup_game()
                    game.auto_place_for_testing()

                # Y/N for heal confirmation
                elif event.key == pygame.K_y:
                    if game.awaiting_heal_confirm:
                        game.confirm_heal_on_attack(True)

                elif event.key == pygame.K_n:
                    if game.awaiting_heal_confirm:
                        game.confirm_heal_on_attack(False)

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    renderer.stop_popup_drag()
                    renderer.stop_log_scrollbar_drag()

            elif event.type == pygame.MOUSEMOTION:
                game_x, game_y = renderer.screen_to_game_coords(*event.pos)
                if renderer.dragging_popup:
                    renderer.drag_popup(game_x, game_y)
                elif renderer.log_scrollbar_dragging:
                    renderer.drag_log_scrollbar(game_y)

            elif event.type == pygame.MOUSEWHEEL:
                # Modern scroll wheel handling
                mouse_x, mouse_y = renderer.screen_to_game_coords(*pygame.mouse.get_pos())

                # Check if over expanded side panel first (priority for scroll)
                side_panel_scrolled = False
                # P2 panels (left side): x < 200
                if mouse_x < 200 and renderer.expanded_panel_p2:
                    panel_id = f'p2_{renderer.expanded_panel_p2}'
                    renderer.scroll_side_panel(event.y, panel_id)
                    side_panel_scrolled = True
                # P1 panels (right side): x > 800 and x < 990
                elif 800 < mouse_x < 990 and renderer.expanded_panel_p1:
                    panel_id = f'p1_{renderer.expanded_panel_p1}'
                    renderer.scroll_side_panel(event.y, panel_id)
                    side_panel_scrolled = True

                if not side_panel_scrolled:
                    # Card info panel: x=960-1260, y=20-420
                    # Log panel: x=960-1260, y=240-490
                    if mouse_x > 960 and mouse_y >= 20 and mouse_y < 240:
                        renderer.scroll_card_info(-event.y)
                    elif mouse_x > 960 and mouse_y >= 240 and mouse_y < 490:
                        renderer.scroll_log(-event.y, game)
                    else:
                        renderer.scroll_log(-event.y, game)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                # Convert screen coords to game coords for all click handling
                mouse_x, mouse_y = renderer.screen_to_game_coords(*event.pos)

                if event.button == 1:  # Left click

                    # Close popup if open
                    if renderer.popup_card:
                        renderer.hide_popup()
                        continue

                    # Try to start dragging a popup
                    if renderer.start_popup_drag(mouse_x, mouse_y, game):
                        continue

                    # Try to start dragging log scrollbar
                    if renderer.start_log_scrollbar_drag(mouse_x, mouse_y):
                        continue

                    # Check priority phase interactions
                    if game.awaiting_priority:
                        # Check dice popup first if open
                        if renderer.dice_popup_open:
                            dice_opt = renderer.get_clicked_dice_option(mouse_x, mouse_y)
                            if dice_opt:
                                if dice_opt == 'cancel':
                                    renderer.close_dice_popup()
                                else:
                                    # Use instant ability with this dice option
                                    card = renderer.dice_popup_card
                                    if card:
                                        game.use_instant_ability(card, "luck", dice_opt)
                                        renderer.close_dice_popup()
                                continue

                        # Check pass button
                        if renderer.get_pass_button_rect().collidepoint(mouse_x, mouse_y):
                            renderer.close_dice_popup()
                            if game.pass_priority():
                                # Priority resolved - continue with action
                                game.continue_after_priority()
                            continue

                    # Check counter selection popup
                    if game.awaiting_counter_selection:
                        counter_opt = renderer.get_clicked_counter_button(mouse_x, mouse_y)
                        if counter_opt is not None:
                            if counter_opt == 'confirm':
                                game.confirm_counter_selection()
                            elif counter_opt == 'cancel':
                                game.cancel_ability()
                            elif isinstance(counter_opt, int):
                                game.set_counter_selection(counter_opt)
                            continue

                    # Check heal confirmation buttons
                    if game.awaiting_heal_confirm:
                        heal_choice = renderer.get_clicked_heal_button(mouse_x, mouse_y)
                        if heal_choice == 'yes':
                            game.confirm_heal_on_attack(True)
                            continue
                        elif heal_choice == 'no':
                            game.confirm_heal_on_attack(False)
                            continue

                    # Check exchange choice buttons
                    if game.awaiting_exchange_choice:
                        exchange_choice = renderer.get_clicked_exchange_button(mouse_x, mouse_y)
                        if exchange_choice == 'full':
                            game.resolve_exchange_choice(reduce_damage=False)
                            continue
                        elif exchange_choice == 'reduce':
                            game.resolve_exchange_choice(reduce_damage=True)
                            continue

                    # Check stench choice buttons
                    if game.awaiting_stench_choice:
                        stench_choice = renderer.get_clicked_stench_button(mouse_x, mouse_y)
                        if stench_choice == 'tap':
                            game.resolve_stench_choice(tap=True)
                            continue
                        elif stench_choice == 'damage':
                            game.resolve_stench_choice(tap=False)
                            continue

                    # Check skip button
                    if renderer.get_skip_button_rect().collidepoint(mouse_x, mouse_y):
                        if game.awaiting_defender:
                            game.skip_defender()
                        elif game.awaiting_movement_shot:
                            game.skip_movement_shot()
                        continue

                    # Check side panel tab click (expand/collapse flyers/graveyards)
                    if renderer.handle_side_panel_click(mouse_x, mouse_y):
                        continue

                    # Check end turn button

                    if renderer.get_end_turn_button_rect().collidepoint(mouse_x, mouse_y):
                        if game.phase == GamePhase.MAIN and not game.awaiting_defender:
                            game.end_turn()
                        continue

                    # Check attack button click
                    if renderer.get_clicked_attack_button(mouse_x, mouse_y):
                        if game.selected_card:
                            game.toggle_attack_mode()
                        continue

                    # Check ability button click
                    ability_id = renderer.get_clicked_ability(mouse_x, mouse_y)
                    if ability_id and game.selected_card:
                        # Check if this is an instant ability during priority phase
                        if game.awaiting_priority and ability_id == "luck":
                            # Open dice popup instead of using ability directly
                            renderer.open_dice_popup(game.selected_card)
                        else:
                            game.use_ability(game.selected_card, ability_id)
                        continue

                    # Check board click
                    pos = renderer.screen_to_pos(mouse_x, mouse_y)
                    if pos is not None:
                        game.handle_click(pos)

                elif event.button == 3:  # Right click for popup or deselect
                    if renderer.popup_card:
                        # Close popup if open
                        renderer.hide_popup()
                    else:
                        # Check if clicking on a card on board
                        card = renderer.get_card_at_screen_pos(game, mouse_x, mouse_y)
                        if card:
                            renderer.show_popup(card)
                        else:
                            # Check if clicking on a graveyard card
                            grave_card = renderer.get_graveyard_card_at_pos(game, mouse_x, mouse_y)
                            if grave_card:
                                renderer.show_popup(grave_card)
                            else:
                                game.deselect_card()

                elif event.button == 4:  # Scroll up
                    # Check if over card info panel (right side)
                    if mouse_x > 960 and mouse_y < 420:
                        renderer.scroll_card_info(-1)
                    else:
                        renderer.scroll_log(-1, game)

                elif event.button == 5:  # Scroll down
                    # Check if over card info panel (right side)
                    if mouse_x > 960 and mouse_y < 420:
                        renderer.scroll_card_info(1)
                    else:
                        renderer.scroll_log(1, game)

        # Process visual events from game
        for event in game.visual_events:
            if event['type'] == 'damage':
                renderer.add_floating_text(event['pos'], f"-{event['amount']}", (255, 80, 80))
            elif event['type'] == 'heal':
                renderer.add_floating_text(event['pos'], f"+{event['amount']}", (80, 255, 80))
            elif event['type'] == 'arrow':
                # Red for damage, green for heal
                if event['arrow_type'] == 'heal':
                    color = (100, 255, 100)  # Green
                else:
                    color = (255, 100, 100)  # Red for all attacks
                renderer.add_arrow(event['from_pos'], event['to_pos'], color)
            elif event['type'] == 'clear_arrows':
                renderer.clear_arrows()
            elif event['type'] == 'clear_arrows_immediate':
                renderer.clear_arrows_immediate()
        game.visual_events.clear()

        # Render
        dt = clock.tick(FPS) / 1000.0  # Delta time in seconds
        renderer.draw(game, dt)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
