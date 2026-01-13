"""
Renderer package - Pygame rendering for the Berserk card game.

The renderer is split into multiple mixins for maintainability:
- base.py: Core initialization, scaling, coordinate conversion
- board.py: Board grid and card rendering
- effects.py: Floating text, arrows, card animations
- popups.py: Popup dialogs (card preview, game over, dice, counters)
- prompts.py: In-game prompts (defender, valhalla, heal confirm)
- ui.py: Game UI elements (card info, messages, buttons)
- panels.py: Side panels (flying zones, graveyards)
- menus.py: Menu screens (main menu, settings, pause)

The Renderer class inherits from all mixins and RendererBase.
"""
import pygame
import os
import sys
from typing import Optional, Dict, List, TYPE_CHECKING

from ..constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT,
    CELL_SIZE, CARD_WIDTH, CARD_HEIGHT,
    COLOR_BG, COLOR_TEXT, COLOR_PLAYER1, COLOR_PLAYER2,
    COLOR_MOVE_HIGHLIGHT, COLOR_ATTACK_HIGHLIGHT,
    GamePhase, scaled, UI_SCALE, UILayout
)
from ..ui import FontManager

# Import base and mixins
from .base import RendererBase, UIView, PopupConfig
from .board import BoardMixin
from .effects import EffectsMixin
from .popups import PopupsMixin
from .prompts import PromptsMixin
from .ui import UIMixin
from .panels import PanelsMixin
from .menus import MenusMixin

if TYPE_CHECKING:
    from ..game import Game
    from ..card import Card
    from ..ui_state import UIState


# Re-export for backward compatibility
__all__ = ['Renderer', 'UIView', 'PopupConfig']


class Renderer(
    RendererBase,
    BoardMixin,
    EffectsMixin,
    PopupsMixin,
    PromptsMixin,
    UIMixin,
    PanelsMixin,
    MenusMixin
):
    """Main renderer class - combines all rendering functionality via mixins."""

    def __init__(self, window: pygame.Surface):
        # Initialize base class first (sets up core state)
        super().__init__(window)

        # Additional initialization not in base

        # Message log scroll offset (0 = bottom/newest)
        self.log_scroll_offset = 0
        self.log_scrollbar_rect: Optional[pygame.Rect] = None
        self.log_scrollbar_dragging = False
        self.log_max_scroll = 0

        # Card info panel scroll offset
        self.card_info_scroll = 0
        self.card_info_content_height = 0
        self.card_info_last_card_id = None

        # Ability button rects (for click detection)
        self.ability_button_rects = []
        self.attack_button_rect = None
        self.prepare_flyer_button_rect = None

        # Card image cache
        self.card_images: Dict[str, pygame.Surface] = {}
        self.card_images_full: Dict[str, pygame.Surface] = {}
        self._load_card_images()

        # Sound effects
        self.damage_sounds: Dict[str, pygame.mixer.Sound] = {}
        self._load_sounds()

        # Popup state
        self.popup_card: Optional['Card'] = None

        # Game over popup state
        self.game_over_popup: bool = False
        self.game_over_winner: int = 0
        self.game_over_button_rect: Optional[pygame.Rect] = None

        # Floating numbers (damage/heal effects)
        self.floating_texts: List[dict] = []

        # Heal confirmation buttons
        self.heal_confirm_buttons: List[tuple] = []

        # Exchange choice buttons
        self.exchange_buttons: List[tuple] = []

        # Stench choice buttons
        self.stench_choice_buttons: List[tuple] = []

        # Draggable popup state
        self.popup_positions: Dict[str, tuple] = {}
        self.dragging_popup: Optional[str] = None
        self.drag_offset: tuple = (0, 0)

        # Interaction arrows
        self.arrows: List[dict] = []

        # Priority phase animation
        self.priority_glow_timer: float = 0.0

        # Card movement animation
        self.card_animations: Dict[int, dict] = {}
        self.card_last_positions: Dict[int, int] = {}
        self.CARD_MOVE_DURATION = 0.25

        # Card death animation
        self.death_animations: Dict[int, dict] = {}  # card_id -> {timer, duration, pos, card_surface}
        self.DEATH_ANIM_DURATION = 0.4  # Total duration
        self.DEATH_POP_DURATION = 0.1   # Duration of initial "pop" expansion

        # Dice popup state
        self.dice_popup_open: bool = False
        self.dice_popup_card: Optional['Card'] = None
        self.dice_option_buttons: List[tuple] = []

        # Counter selection popup state
        self.counter_popup_buttons: List[tuple] = []
        self.counter_confirm_button: Optional[pygame.Rect] = None
        self.counter_cancel_button: Optional[pygame.Rect] = None

        # Side panel state
        self.expanded_panel_p1: Optional[str] = None
        self.expanded_panel_p2: Optional[str] = None
        self.side_panel_tab_rects: Dict[str, pygame.Rect] = {}
        self.side_panel_scroll: Dict[str, int] = {
            'p1_flyers': 0, 'p1_grave': 0, 'p2_flyers': 0, 'p2_grave': 0
        }

        # Menu button rects
        self.menu_buttons: List[tuple] = []

        # Settings state
        from ..text_input import TextInput
        from ..settings import get_nickname
        self.settings_nickname_input = TextInput(max_length=20)
        self.settings_nickname_input.value = get_nickname()
        self.settings_nickname_rect: Optional[pygame.Rect] = None

    def _load_card_images(self):
        """Load and cache all card images."""
        # Find data directory
        base_paths = [
            os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'cards'),
            os.path.join(os.path.dirname(__file__), '..', 'data', 'cards'),
            'data/cards',
        ]
        if hasattr(sys, '_MEIPASS'):
            base_paths.insert(0, os.path.join(sys._MEIPASS, 'data', 'cards'))

        cards_dir = None
        for path in base_paths:
            if os.path.exists(path):
                cards_dir = path
                break

        if not cards_dir:
            print("Warning: Card images directory not found")
            return

        for filename in os.listdir(cards_dir):
            if filename.endswith('.jpg') or filename.endswith('.png'):
                filepath = os.path.join(cards_dir, filename)
                try:
                    img = pygame.image.load(filepath)
                    img_w, img_h = img.get_size()

                    # Crop art area
                    art_margin_x = int(img_w * 0.06)
                    art_top = int(img_h * 0.135)
                    art_bottom = int(img_h * 0.55)
                    art_width = img_w - 2 * art_margin_x
                    art_height = art_bottom - art_top

                    art_crop = img.subsurface((art_margin_x, art_top, art_width, art_height))

                    # Scale for board display
                    name_bar_height = scaled(UILayout.NAME_BAR_HEIGHT)
                    board_size = (CARD_WIDTH * 2, (CARD_HEIGHT - name_bar_height) * 2)
                    board_img = pygame.transform.smoothscale(art_crop, board_size)
                    self.card_images[filename] = board_img

                    # Full card for popup
                    popup_w = min(img_w, 500)
                    popup_h = int(popup_w * img_h / img_w)
                    full_img = pygame.transform.smoothscale(img, (popup_w, popup_h))

                    # Make white corners transparent
                    full_img = full_img.convert_alpha()
                    arr = pygame.surfarray.pixels3d(full_img)
                    alpha = pygame.surfarray.pixels_alpha(full_img)

                    corner_size = int(popup_w * 0.08)
                    h = popup_h
                    w = popup_w
                    white_thresh = 240

                    for region in [(0, corner_size, 0, corner_size),
                                   (w - corner_size, w, 0, corner_size),
                                   (0, corner_size, h - corner_size, h),
                                   (w - corner_size, w, h - corner_size, h)]:
                        x1, x2, y1, y2 = region
                        region_rgb = arr[x1:x2, y1:y2]
                        region_alpha = alpha[x1:x2, y1:y2]
                        white_mask = ((region_rgb[:, :, 0] > white_thresh) &
                                      (region_rgb[:, :, 1] > white_thresh) &
                                      (region_rgb[:, :, 2] > white_thresh))
                        region_alpha[white_mask] = 0

                    del arr, alpha
                    self.card_images_full[filename] = full_img
                except Exception as e:
                    print(f"Error loading {filename}: {e}")

        # Load cardback image for face-down cards
        self.cardback_image: Optional[pygame.Surface] = None
        misc_paths = [
            os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'misc'),
            os.path.join(os.path.dirname(__file__), '..', 'data', 'misc'),
            'data/misc',
        ]
        if hasattr(sys, '_MEIPASS'):
            misc_paths.insert(0, os.path.join(sys._MEIPASS, 'data', 'misc'))

        for path in misc_paths:
            cardback_path = os.path.join(path, 'cardback.jpg')
            if os.path.exists(cardback_path):
                try:
                    img = pygame.image.load(cardback_path)
                    # Scale for board display
                    name_bar_height = scaled(UILayout.NAME_BAR_HEIGHT)
                    board_size = (CARD_WIDTH * 2, (CARD_HEIGHT - name_bar_height) * 2)
                    self.cardback_image = pygame.transform.smoothscale(img, board_size)
                except Exception as e:
                    print(f"Error loading cardback.jpg: {e}")
                break

        # Load dice images
        self.dice_images: Dict[int, pygame.Surface] = {}
        dice_paths = [
            os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'die'),
            os.path.join(os.path.dirname(__file__), '..', 'data', 'die'),
            'data/die',
        ]
        if hasattr(sys, '_MEIPASS'):
            dice_paths.insert(0, os.path.join(sys._MEIPASS, 'data', 'die'))

        dice_size = scaled(UILayout.DICE_SIZE)
        for path in dice_paths:
            if os.path.isdir(path):
                for i in range(1, 7):
                    dice_file = os.path.join(path, f'Alea_{i}.png')
                    if os.path.exists(dice_file):
                        try:
                            img = pygame.image.load(dice_file).convert_alpha()
                            self.dice_images[i] = pygame.transform.smoothscale(img, (dice_size, dice_size))
                        except Exception as e:
                            print(f"Error loading dice {i}: {e}")
                if self.dice_images:
                    break

        # Dice display state
        self.dice_display_state: Optional[dict] = None  # {atk_roll, def_roll, atk_bonus, def_bonus, atk_player, def_player, anim_timer}

    def _load_sounds(self):
        """Load damage sound effects."""
        sound_paths = [
            os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'sounds'),
            os.path.join(os.path.dirname(__file__), '..', 'data', 'sounds'),
            'data/sounds',
        ]
        if hasattr(sys, '_MEIPASS'):
            sound_paths.insert(0, os.path.join(sys._MEIPASS, 'data', 'sounds'))

        sounds_dir = None
        for path in sound_paths:
            if os.path.exists(path):
                sounds_dir = path
                break

        if not sounds_dir:
            print("Warning: Sounds directory not found")
            return

        # Load damage sounds
        sound_files = {
            'weak': 'weak_punch.wav',
            'med': 'med_punch.wav',
            'hard': 'hard_punch.wav',
        }

        for key, filename in sound_files.items():
            filepath = os.path.join(sounds_dir, filename)
            if os.path.exists(filepath):
                try:
                    self.damage_sounds[key] = pygame.mixer.Sound(filepath)
                except Exception as e:
                    print(f"Error loading {filename}: {e}")

    def play_damage_sound(self, amount: int):
        """Play damage sound based on damage amount.

        Args:
            amount: Damage dealt (1-2: weak, 3-4: med, 5+: hard)
        """
        from ..settings import get_sound_enabled

        if amount <= 0:
            return

        if not get_sound_enabled():
            return

        if amount <= 2:
            sound_key = 'weak'
        elif amount <= 4:
            sound_key = 'med'
        else:
            sound_key = 'hard'

        sound = self.damage_sounds.get(sound_key)
        if sound:
            sound.play()

    def draw(self, game: 'Game', dt: float = 0.016, ui_state: 'UIState' = None,
             skip_flip: bool = False, test_controlled_player: any = "not_test_game"):
        """Main draw function.

        Args:
            game: Game state to render
            dt: Delta time for animations
            ui_state: UIState for client-side selection/highlighting
            skip_flip: If True, skip pygame.display.flip()
            test_controlled_player: For test game mode - None (auto) or 1/2 (manual)
        """
        import math

        # Populate _ui from UIState
        if ui_state is not None:
            self._ui.selected_card = game.get_card_by_id(ui_state.selected_card_id) if ui_state.selected_card_id else None
            self._ui.valid_moves = list(ui_state.valid_moves)
            self._ui.valid_attacks = list(ui_state.valid_attacks)
            self._ui.attack_mode = ui_state.attack_mode
            self.viewing_player = ui_state.viewing_player
        else:
            self._ui.selected_card = None
            self._ui.valid_moves = []
            self._ui.valid_attacks = []
            self._ui.attack_mode = False
            self.viewing_player = 1

        # Update priority glow animation timer
        if game.awaiting_priority or game.has_forced_attack or game.awaiting_defender:
            self.priority_glow_timer += dt * 4
            if self.priority_glow_timer > 2 * math.pi:
                self.priority_glow_timer -= 2 * math.pi
        else:
            self.priority_glow_timer = 0.0

        # Clear render surface
        self.screen.fill(COLOR_BG)

        # Update card movement animations
        self.update_card_animations(game, dt)

        # Update death animations
        self.update_death_animations(dt)

        # Update dice display animation
        self.update_dice_display(game, dt)

        # Draw everything to render surface
        self.draw_board(game)
        self.draw_side_panels(game)
        self.draw_highlights(game)
        self.draw_cards(game)
        self.draw_death_animations()
        self.draw_ui(game)
        self.draw_hand(game)

        # Side control indicator for test game mode
        if test_controlled_player != "not_test_game":
            self.draw_side_control_indicator(test_controlled_player)

        # Priority phase UI or turn indicator
        if game.awaiting_priority:
            self.draw_priority_info(game)
            if game.priority_player == self.viewing_player:
                self.draw_pass_button(game)
            if self.dice_popup_open:
                self.draw_dice_popup(game)
        else:
            if self.dice_popup_open:
                self.close_dice_popup()
            self.draw_turn_indicator(game)

        # Draw dice icons below graveyards
        self.draw_dice_display(game)

        # Counter selection popup
        if game.awaiting_counter_selection:
            if game.interaction and game.interaction.acting_player == self.viewing_player:
                self.draw_counter_popup(game)

        # Update and draw effects
        self.update_floating_texts(dt)
        self.draw_floating_texts(game)
        self.update_arrows(dt)
        self.draw_arrows(game)

        self.draw_popup()

        # Game over popup background
        if self.game_over_popup:
            self.draw_game_over_popup()

        # Scale and blit to window
        self.window.fill((0, 0, 0))
        if self.scale != 1.0:
            scaled_w = int(self.BASE_WIDTH * self.scale)
            scaled_h = int(self.BASE_HEIGHT * self.scale)
            scaled_surface = pygame.transform.smoothscale(self.screen, (scaled_w, scaled_h))
            self.window.blit(scaled_surface, (self.offset_x, self.offset_y))
        else:
            self.window.blit(self.screen, (self.offset_x, self.offset_y))

        # Draw native resolution UI
        self.draw_ui_native(game)

        if self.game_over_popup:
            self.draw_game_over_popup_native()

        if not skip_flip:
            pygame.display.flip()

    def draw_hand(self, game: 'Game'):
        """Draw player hand (placeholder for future deck/hand system)."""
        pass  # Hand system not yet implemented

    def get_card_at_screen_pos(self, game: 'Game', mouse_x: int, mouse_y: int) -> Optional['Card']:
        """Get card at screen position (main board or flying zones)."""
        # Check main board first
        pos = self.screen_to_pos(mouse_x, mouse_y)
        if pos is not None:
            return game.board.get_card(pos)

        # Check flying zones
        flying_pos = self.get_flying_slot_at_pos(mouse_x, mouse_y, game)
        if flying_pos is not None:
            return game.board.get_card(flying_pos)

        return None
