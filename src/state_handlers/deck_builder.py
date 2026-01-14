"""Deck builder and deck select state handler."""

import pygame
from typing import Optional, TYPE_CHECKING

from .base import StateHandler
from .helpers import handle_prep_pause_menu_event, render_prep_pause_menu

if TYPE_CHECKING:
    from ..app_context import AppContext
    from ..constants import AppState


class DeckBuilderHandler(StateHandler):
    """Handler for deck builder and deck selection states.

    Both DECK_BUILDER and DECK_SELECT use similar logic but with different
    purposes:
    - DECK_BUILDER: Create/edit/save decks
    - DECK_SELECT: Select a deck for playing (local or network game)

    Handles:
    - Card library browsing and scrolling
    - Adding/removing cards from deck
    - Saving/loading decks
    - Deck validation
    """

    def __init__(self, ctx: 'AppContext', is_selection_mode: bool = False):
        super().__init__(ctx)
        self.is_selection_mode = is_selection_mode

    def handle_event(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle deck builder events."""
        from ..constants import AppState, UILayout

        dbr = self.ctx.deck_builder_renderer
        if not dbr:
            return None

        # Handle pause menu first (only in selection mode)
        if self.is_selection_mode:
            result = handle_prep_pause_menu_event(self.ctx, event)
            if result is not False:  # False means not in pause menu
                return result

        if event.type == pygame.KEYDOWN:
            return self._handle_keydown(event)

        elif event.type == pygame.TEXTINPUT:
            if dbr.text_input_active:
                dbr.handle_text_input(event)
            return None

        elif event.type == pygame.MOUSEWHEEL:
            mx, my = self.ctx.renderer.screen_to_game_coords(*pygame.mouse.get_pos())
            if my < UILayout.DECK_BUILDER_DECK_Y:
                dbr.scroll_library(event.y)
            else:
                dbr.scroll_deck(event.y)
            return None

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_click(mx, my, event)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            return self._handle_right_click(mx, my)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            dbr.stop_scrollbar_drag()
            # Handle mouse up for text input drag selection
            if dbr.text_input_active:
                mouse_event = pygame.event.Event(event.type, pos=(mx, my), button=event.button)
                dbr.handle_text_mouse_event(mouse_event)
            return None

        elif event.type == pygame.MOUSEMOTION:
            mx, my = self.ctx.renderer.screen_to_game_coords(*event.pos)
            # Handle text input drag selection
            if dbr.text_input_active:
                mouse_event = pygame.event.Event(event.type, pos=(mx, my), rel=event.rel, buttons=event.buttons)
                dbr.handle_text_mouse_event(mouse_event)
            elif dbr.dragging_scrollbar:
                dbr.drag_scrollbar(my)
            return None

        return None

    def _handle_keydown(self, event: pygame.event.Event) -> Optional['AppState']:
        """Handle key press in deck builder."""
        from ..constants import AppState

        dbr = self.ctx.deck_builder_renderer
        db = self.ctx.deck_builder

        if dbr.text_input_active:
            was_active = dbr.text_input_active
            result = dbr.handle_text_input(event)
            if result is not None:
                # Text input submitted - process the pending action
                dbr.handle_text_input_result(result, db)
            elif was_active and not dbr.text_input_active:
                # Text input was cancelled (ESC pressed) - clear pending action
                dbr.handle_text_input_result(None, db)
            return None

        if event.key == pygame.K_ESCAPE:
            if dbr.popup_card_name:
                dbr.hide_card_popup()
            elif dbr.show_load_popup:
                dbr.hide_load_popup()
            elif dbr.show_confirm_popup:
                dbr.hide_confirmation()
            elif self.is_selection_mode:
                # Show pause menu in selection mode
                self.ctx.show_pause_menu = True
            else:
                return self._go_back()

        return None

    def _handle_click(self, mx: int, my: int, event: pygame.event.Event) -> Optional['AppState']:
        """Handle left click in deck builder."""
        from ..constants import AppState

        dbr = self.ctx.deck_builder_renderer
        db = self.ctx.deck_builder

        # Handle popup states first
        if dbr.popup_card_name:
            dbr.hide_card_popup()
            return None

        if dbr.show_load_popup:
            deck_path = dbr.get_clicked_load_deck(mx, my)
            if deck_path:
                db.load(deck_path)
                dbr.hide_load_popup()
            return None

        if dbr.text_input_active:
            mouse_event = pygame.event.Event(event.type, pos=(mx, my), button=event.button)
            dbr.handle_text_mouse_event(mouse_event)
            return None

        if dbr.show_confirm_popup:
            choice = dbr.get_clicked_confirm_button(mx, my)
            if choice:
                dbr.handle_confirm_action(choice, db)
            return None

        if dbr.start_scrollbar_drag(mx, my):
            return None

        # Check button clicks
        btn = dbr.get_clicked_button(mx, my)
        if btn:
            return self._handle_button(btn)

        # Card/deck list clicks
        deck_path = dbr.get_clicked_deck_list_item(mx, my)
        if deck_path:
            if self.is_selection_mode:
                db.load(deck_path)
            else:
                dbr.handle_deck_list_click(deck_path, db)
            return None

        # Library card clicks
        card = dbr.get_clicked_library_card(mx, my)
        if card:
            db.add_card(card)
            return None

        # Deck card clicks
        card = dbr.get_clicked_deck_card(mx, my)
        if card:
            db.remove_card(card)
            return None

        return None

    def _handle_right_click(self, mx: int, my: int) -> Optional['AppState']:
        """Handle right click (show card popup)."""
        dbr = self.ctx.deck_builder_renderer

        # Check library
        card = dbr.get_clicked_library_card(mx, my)
        if card:
            dbr.show_card_popup(card)
            return None

        # Check deck
        card = dbr.get_clicked_deck_card(mx, my)
        if card:
            dbr.show_card_popup(card)
            return None

        return None

    def _handle_button(self, btn: str) -> Optional['AppState']:
        """Handle button clicks."""
        from ..constants import AppState
        from ..squad_builder import SquadBuilder
        from ..squad_builder_renderer import SquadBuilderRenderer
        from ..deck_builder import DeckBuilder
        from ..deck_builder_renderer import DeckBuilderRenderer
        from ..app_context import create_local_game_state

        dbr = self.ctx.deck_builder_renderer
        db = self.ctx.deck_builder

        if self.is_selection_mode and btn == 'confirm_selection':
            return self._confirm_deck_selection()

        if btn == 'back':
            return self._go_back()

        # All other buttons handled by renderer
        result = dbr.handle_button_action(btn, db)
        if result == 'back':
            return AppState.MENU

        return None

    def _confirm_deck_selection(self) -> Optional['AppState']:
        """Confirm deck selection and proceed to squad building."""
        from ..constants import AppState
        from ..squad_builder import SquadBuilder
        from ..squad_builder_renderer import SquadBuilderRenderer
        from ..deck_builder import DeckBuilder
        from ..deck_builder_renderer import DeckBuilderRenderer

        db = self.ctx.deck_builder
        dbr = self.ctx.deck_builder_renderer

        if not db.is_valid():
            dbr.show_notification("Колода должна содержать 30-50 карт")
            return None

        deck_cards = db.get_deck_card_list()

        # Check if preparing for network game
        if self.ctx.network_prep_state is not None:
            self.ctx.network_prep_state['deck'] = deck_cards
            # Use actual player number from network UI
            my_player = self.ctx.network_ui.my_player_number if self.ctx.network_ui else 1
            sb = SquadBuilder(player=my_player, deck_cards=deck_cards)
            s, ci, _, f = self.ctx.renderer.get_deck_builder_resources()
            sr = SquadBuilderRenderer(s, ci, f)
            sr.custom_header = "Набор отряда - Сетевая игра"
            self.ctx.network_prep_state['squad_builder'] = sb
            self.ctx.network_prep_state['squad_renderer'] = sr
            return AppState.SQUAD_SELECT

        # Local game flow
        player = self.ctx.local_game_state['current_player']
        if player == 1:
            self.ctx.local_game_state['deck_p1'] = deck_cards
            self.ctx.local_game_state['current_player'] = 2
            # Reset for player 2
            self.ctx.deck_builder = DeckBuilder()
            s, ci, _, f = self.ctx.renderer.get_deck_builder_resources()
            self.ctx.deck_builder_renderer = DeckBuilderRenderer(s, ci, f)
            self.ctx.deck_builder_renderer.selection_mode = True
            self.ctx.deck_builder_renderer.custom_header = "Выбор колоды - Игрок 2"
            return None  # Stay in DECK_SELECT
        else:
            self.ctx.local_game_state['deck_p2'] = deck_cards
            self.ctx.local_game_state['current_player'] = 1
            # Move to squad selection for player 1
            sb = SquadBuilder(player=1, deck_cards=self.ctx.local_game_state['deck_p1'])
            s, ci, _, f = self.ctx.renderer.get_deck_builder_resources()
            sr = SquadBuilderRenderer(s, ci, f)
            self.ctx.local_game_state['squad_builder'] = sb
            self.ctx.local_game_state['squad_renderer'] = sr
            return AppState.SQUAD_SELECT

    def _go_back(self) -> 'AppState':
        """Go back to menu (for non-selection mode only)."""
        from ..constants import AppState
        return AppState.MENU

    def update(self, dt: float) -> Optional['AppState']:
        """Update deck builder state."""
        dbr = self.ctx.deck_builder_renderer
        if dbr:
            dbr.update_notification()
        return None

    def render(self) -> None:
        """Render the deck builder."""
        dbr = self.ctx.deck_builder_renderer
        db = self.ctx.deck_builder
        if dbr and db:
            _, _, card_images_full, _ = self.ctx.renderer.get_deck_builder_resources()
            dbr.draw(db, card_images_full)

            # Draw pause menu overlay (selection mode only)
            if self.is_selection_mode and render_prep_pause_menu(self.ctx):
                return
            self.ctx.renderer.finalize_frame()

    def on_enter(self) -> None:
        """Called when entering deck builder/selection state."""
        self.ctx.show_pause_menu = False
