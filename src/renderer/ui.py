"""Game UI elements - card info, messages, buttons, indicators."""
import pygame
from typing import Optional, Tuple, List, TYPE_CHECKING

from ..constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT,
    COLOR_PLAYER1, COLOR_PLAYER2, COLOR_TEXT,
    GamePhase, scaled, UILayout
)
from ..ui import draw_button_simple
from ..abilities import get_ability, AbilityType

if TYPE_CHECKING:
    from ..game import Game
    from ..card import Card


class UIMixin:
    """Mixin for game UI elements."""

    def draw_ui(self, game: 'Game'):
        """Draw UI elements (backgrounds only - text drawn in draw_ui_native)."""
        # End turn button background - use the same rect as click detection
        # Color based on viewing player (my color), not current player
        my_color = COLOR_PLAYER1 if self.viewing_player == 1 else COLOR_PLAYER2
        button_rect = self.get_end_turn_button_rect()
        pygame.draw.rect(self.screen, my_color, button_rect)
        pygame.draw.rect(self.screen, COLOR_TEXT, button_rect, 2)

        # Store game state for native rendering
        self._ui_game_state = {
            'current_player': game.current_player,
            'turn_number': game.turn_number,
            'phase': game.phase,
            'end_turn_rect': button_rect,
        }

        # Check if we're the acting player for interaction popups
        is_acting = (game.interaction and game.interaction.acting_player == self.viewing_player)

        # Counter shot selection prompt (only for acting player)
        if game.awaiting_counter_shot and is_acting:
            self.draw_counter_shot_prompt(game)

        # Movement shot selection prompt (only for acting player)
        if game.awaiting_movement_shot and is_acting:
            self.draw_movement_shot_prompt(game)

        # Heal confirmation prompt (only for acting player)
        if game.awaiting_heal_confirm and is_acting:
            self.draw_heal_confirm_prompt(game)

        # Stench choice prompt (only for acting player)
        if game.awaiting_stench_choice and is_acting:
            self.draw_stench_choice_prompt(game)

        # Exchange choice prompt (only for acting player)
        if game.awaiting_exchange_choice and is_acting:
            self.draw_exchange_prompt(game)

        # Valhalla selection prompt (only for acting player)
        if game.awaiting_valhalla and is_acting:
            self.draw_valhalla_prompt(game)

        # Defender choice prompt (only for acting player)
        if game.awaiting_defender and game.interaction and is_acting:
            self.draw_defender_prompt(game)

        # Selected card info
        if self._ui.selected_card and not game.awaiting_defender:
            self.draw_card_info(self._ui.selected_card, game)

        # Message log
        self.draw_messages(game)

        # Skip button (only show when something can be skipped and we're acting)
        if (game.awaiting_defender or game.awaiting_movement_shot) and is_acting:
            self.draw_skip_button(game)

        # Dice panel (shows pending or last combat dice)
        if (game.awaiting_priority and game.pending_dice_roll) or (game.last_combat and not game.awaiting_defender):
            self.draw_dice_panel(game)

    def draw_ui_native(self, game: 'Game'):
        """Draw UI text elements at native window resolution."""
        # Main UI text (player, turn, phase)
        if hasattr(self, '_ui_game_state'):
            state = self._ui_game_state
            large_font = self.get_native_font('large')
            medium_font = self.get_native_font('medium')

            # Current player indicator
            player_color = COLOR_PLAYER1 if state['current_player'] == 1 else COLOR_PLAYER2
            player_text = f"Ход: Игрок {state['current_player']}"
            text_surface = large_font.render(player_text, True, player_color)
            x, y = self.game_to_window_coords(20, 20)
            self.window.blit(text_surface, (x, y))

            # Turn number
            turn_text = f"Раунд: {state['turn_number']}"
            turn_surface = medium_font.render(turn_text, True, COLOR_TEXT)
            x, y = self.game_to_window_coords(20, 55)
            self.window.blit(turn_surface, (x, y))

            # Phase
            phase_names = {
                GamePhase.SETUP: "Расстановка",
                GamePhase.REVEAL: "Открытие",
                GamePhase.MAIN: "Главная фаза",
                GamePhase.GAME_OVER: "Игра окончена"
            }
            phase_text = phase_names.get(state['phase'], "")
            phase_surface = medium_font.render(phase_text, True, COLOR_TEXT)
            x, y = self.game_to_window_coords(20, 80)
            self.window.blit(phase_surface, (x, y))

            # End turn button text
            button_rect = state['end_turn_rect']
            win_rect = self.game_to_window_rect(button_rect)
            button_text = "Конец хода"
            button_surface = medium_font.render(button_text, True, COLOR_TEXT)
            text_x = win_rect.x + (win_rect.width - button_surface.get_width()) // 2
            text_y = win_rect.y + (win_rect.height - button_surface.get_height()) // 2
            self.window.blit(button_surface, (text_x, text_y))

        # Turn indicator text
        if hasattr(self, '_turn_indicator_state') and self._turn_indicator_state.get('visible'):
            state = self._turn_indicator_state
            medium_font = self.get_native_font('medium')
            text = "Ваш ход" if state['is_my_turn'] else "Ход противника"
            text_surface = medium_font.render(text, True, COLOR_TEXT)
            win_rect = self.game_to_window_rect(state['rect'])
            text_x = win_rect.x + (win_rect.width - text_surface.get_width()) // 2
            text_y = win_rect.y + int(4 * self.scale)
            self.window.blit(text_surface, (text_x, text_y))

    def draw_card_info(self, card: 'Card', game: 'Game'):
        """Draw detailed info about selected card with scrolling."""
        # Check if card is hidden enemy
        is_hidden = card.face_down and card.player != self.viewing_player

        # Reset scroll when card changes
        if card.id != self.card_info_last_card_id:
            self.card_info_scroll = 0
            self.card_info_last_card_id = card.id

        panel_x = UILayout.get_card_info_x()
        panel_y = scaled(UILayout.CARD_INFO_Y)
        panel_width = scaled(UILayout.CARD_INFO_WIDTH)
        panel_height = scaled(UILayout.CARD_INFO_HEIGHT)

        # Panel background
        pygame.draw.rect(self.screen, (40, 40, 50),
                         (panel_x, panel_y, panel_width, panel_height))
        pygame.draw.rect(self.screen, COLOR_TEXT,
                         (panel_x, panel_y, panel_width, panel_height), 1)

        # For hidden enemy cards, show only "???"
        if is_hidden:
            padding = scaled(UILayout.CARD_INFO_PADDING)
            hidden_text = self.font_large.render("???", True, COLOR_TEXT)
            self.screen.blit(hidden_text, (panel_x + padding, panel_y + padding))

            info_text = self.font_small.render("Скрытая карта", True, (150, 150, 150))
            self.screen.blit(info_text, (panel_x + padding, panel_y + padding + 30))
            return

        # Set clipping rect for scrollable content
        clip_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)
        self.screen.set_clip(clip_rect)

        # Apply scroll offset
        scroll_y = -self.card_info_scroll

        # Card name
        padding = scaled(UILayout.CARD_INFO_PADDING)
        name_surface = self.font_large.render(card.name, True, COLOR_TEXT)
        self.screen.blit(name_surface, (panel_x + padding, panel_y + padding + scroll_y))

        # Stats
        y_offset = 75 + scroll_y
        line_spacing = scaled(UILayout.CARD_INFO_LINE_SPACING)
        status_spacing = scaled(UILayout.CARD_INFO_STATUS_SPACING)
        effective_atk = card.get_effective_attack()

        # Build attack string with positional modifiers
        atk_parts = []
        for tier in range(3):
            base = effective_atk[tier]
            pos_mod = game._get_positional_damage_modifier(card, tier)
            if pos_mod > 0:
                atk_parts.append(f"{base}(+{pos_mod})")
            elif pos_mod < 0:
                atk_parts.append(f"{base}({pos_mod})")
            else:
                atk_parts.append(str(base))
        atk_str = "-".join(atk_parts)

        # Show dice bonuses
        atk_dice = game._get_attack_dice_bonus(card)
        def_dice = game._get_defense_dice_bonus(card)
        dice_parts = []
        if atk_dice > 0:
            dice_parts.append(f"+{atk_dice}ОвА")
        if def_dice > 0:
            dice_parts.append(f"+{def_dice}ОвЗ")
        if dice_parts:
            atk_str += " " + " ".join(dice_parts)

        # Only show HP - attack and movement are shown on card indicators
        hp_surface = self.font_small.render(f"HP: {card.curr_life}/{card.life}", True, COLOR_TEXT)
        self.screen.blit(hp_surface, (panel_x + padding, panel_y + y_offset))
        y_offset += line_spacing

        if card.tapped:
            tapped = self.font_small.render("(Закрыт)", True, (180, 100, 100))
            self.screen.blit(tapped, (panel_x + padding, panel_y + y_offset))
            y_offset += line_spacing

        # Active statuses (temporary buffs)
        statuses = []
        if card.temp_ranged_bonus > 0:
            statuses.append(f"+{card.temp_ranged_bonus} выстрел")
        if card.has_direct:
            statuses.append("прямой удар")
        if card.temp_attack_bonus > 0:
            statuses.append(f"+{card.temp_attack_bonus} атака")

        # Calculate total dice bonuses
        total_ova = card.temp_dice_bonus
        total_ovz = 0
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability:
                total_ova += ability.dice_bonus_attack
                total_ovz += ability.dice_bonus_defense

        # Show unified dice bonuses
        if total_ova > 0:
            statuses.append(f"ОвА +{total_ova}")
        if total_ovz > 0:
            statuses.append(f"ОвЗ +{total_ovz}")

        # Defender buff
        if card.defender_buff_attack > 0:
            statuses.append(f"+{card.defender_buff_attack} защ.бафф")
        if card.defender_buff_dice > 0:
            statuses.append(f"+{card.defender_buff_dice} защ.бросок")
        # Positional damage reduction
        col = game._get_card_column(card)
        if card.has_ability("center_column_defense") and col == 2:
            statuses.append("-1 от слабых")
        # Counter/token display
        if card.counters > 0:
            statuses.append(f"фишек: {card.counters}")

        # Armor display
        if card.armor > 0:
            statuses.append(f"броня: {card.armor_remaining}/{card.armor}")

        # Formation status and bonuses
        if card.in_formation:
            formation_def = 0
            for ability_id in card.stats.ability_ids:
                ability = get_ability(ability_id)
                if ability and ability.is_formation and ability.formation_dice_bonus > 0:
                    if ability.requires_elite_ally and game._has_elite_ally_in_formation(card):
                        formation_def += ability.formation_dice_bonus
                    elif ability.requires_common_ally and game._has_common_ally_in_formation(card):
                        formation_def += ability.formation_dice_bonus
                    elif not ability.requires_elite_ally and not ability.requires_common_ally:
                        formation_def += ability.formation_dice_bonus

            stroy_parts = ["В СТРОЮ"]
            if card.formation_armor_remaining > 0:
                stroy_parts.append(f"броня: {card.formation_armor_remaining}")
            if formation_def > 0:
                stroy_parts.append(f"ОвЗ +{formation_def}")
            statuses.append(" ".join(stroy_parts))

        # Prepared flyer attack
        if card.can_attack_flyer:
            statuses.append("ГОТОВ К АТАКЕ ЛЕТАЮЩИХ")

        # Pull status_text from abilities
        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if ability and ability.status_text:
                if ability.dice_bonus_attack > 0 or ability.dice_bonus_defense > 0:
                    has_other_effects = (
                        ability.damage_reduction > 0 or
                        ability.heal_amount > 0 or
                        ability.damage_amount > 0 or
                        ability.is_formation or
                        ability.trigger is not None
                    )
                    if not has_other_effects:
                        continue
                statuses.append(ability.status_text)

        if statuses:
            max_width = panel_width - padding * 2
            current_line = []
            lines = []
            for status in statuses:
                test_line = ", ".join(current_line + [status])
                test_surface = self.font_small.render(f"[{test_line}]", True, (100, 200, 100))
                if test_surface.get_width() > max_width and current_line:
                    lines.append(current_line)
                    current_line = [status]
                else:
                    current_line.append(status)
            if current_line:
                lines.append(current_line)

            for line in lines:
                line_text = ", ".join(line)
                status_surface = self.font_small.render(f"[{line_text}]", True, (100, 200, 100))
                self.screen.blit(status_surface, (panel_x + padding, panel_y + y_offset))
                y_offset += status_spacing

        # Attack button
        y_offset += 8
        self.attack_button_rect = None

        btn_height = scaled(UILayout.CARD_INFO_BUTTON_HEIGHT)
        btn_spacing = scaled(UILayout.CARD_INFO_BUTTON_SPACING)

        btn_rect = pygame.Rect(panel_x + padding, panel_y + y_offset, panel_width - padding * 2, btn_height)

        is_own_card = card.player == game.current_player
        can_use = is_own_card and card.can_act
        # Compare by ID since network games create new Card objects on sync
        is_selected = self._ui.selected_card and self._ui.selected_card.id == card.id
        has_attacks = len(self._ui.valid_attacks) > 0 if is_selected else False
        in_attack_mode = self._ui.attack_mode and is_selected

        if in_attack_mode:
            btn_color = (150, 60, 60)
            text_color = COLOR_TEXT
        elif can_use and (has_attacks or not card.tapped):
            btn_color = (120, 50, 50)
            text_color = COLOR_TEXT
        else:
            btn_color = (50, 50, 55)
            text_color = (120, 120, 120)

        pygame.draw.rect(self.screen, btn_color, btn_rect)
        pygame.draw.rect(self.screen, (160, 80, 80), btn_rect, 1)

        atk = game.get_display_attack(card)
        btn_text = f"Атака {atk[0]}-{atk[1]}-{atk[2]}"
        btn_surface = self.font_small.render(btn_text, True, text_color)
        text_x = btn_rect.x + (btn_rect.width - btn_surface.get_width()) // 2
        text_y = btn_rect.y + (btn_rect.height - btn_surface.get_height()) // 2
        self.screen.blit(btn_surface, (text_x, text_y))

        if can_use and not card.tapped:
            self.attack_button_rect = btn_rect

        y_offset += btn_spacing

        # Ability buttons
        self.ability_button_rects = []
        usable_abilities = game.get_usable_abilities(card)

        for ability_id in card.stats.ability_ids:
            ability = get_ability(ability_id)
            if not ability or ability.ability_type != AbilityType.ACTIVE:
                continue

            btn_rect = pygame.Rect(panel_x + padding, panel_y + y_offset, panel_width - padding * 2, btn_height)

            is_usable = ability in usable_abilities
            on_cooldown = ability_id in card.ability_cooldowns

            if is_usable:
                btn_color = (80, 60, 120)
                text_color = COLOR_TEXT
            elif on_cooldown:
                btn_color = (50, 50, 55)
                text_color = (120, 120, 120)
            else:
                btn_color = (50, 50, 55)
                text_color = (120, 120, 120)

            pygame.draw.rect(self.screen, btn_color, btn_rect)
            pygame.draw.rect(self.screen, (100, 80, 140), btn_rect, 1)

            btn_text = game.get_ability_display_text(card, ability)
            if on_cooldown:
                cd = card.ability_cooldowns[ability_id]
                btn_text += f" ({cd})"

            btn_surface = self.font_small.render(btn_text, True, text_color)
            text_x = btn_rect.x + (btn_rect.width - btn_surface.get_width()) // 2
            text_y = btn_rect.y + (btn_rect.height - btn_surface.get_height()) // 2
            self.screen.blit(btn_surface, (text_x, text_y))

            if is_usable:
                self.ability_button_rects.append((btn_rect, ability_id))

            y_offset += btn_spacing

        # Prepare Flyer Attack button
        self.prepare_flyer_button_rect = None
        if game.can_prepare_flyer_attack(card):
            btn_rect = pygame.Rect(panel_x + padding, panel_y + y_offset, panel_width - padding * 2, btn_height)
            btn_color = (120, 80, 40)
            pygame.draw.rect(self.screen, btn_color, btn_rect)
            pygame.draw.rect(self.screen, (180, 120, 60), btn_rect, 1)

            btn_text = "Подготовить атаку летающих"
            btn_surface = self.font_small.render(btn_text, True, COLOR_TEXT)
            text_x = btn_rect.x + (btn_rect.width - btn_surface.get_width()) // 2
            text_y = btn_rect.y + (btn_rect.height - btn_surface.get_height()) // 2
            self.screen.blit(btn_surface, (text_x, text_y))

            self.prepare_flyer_button_rect = btn_rect
            y_offset += btn_spacing

        # Card description
        if card.stats.description:
            y_offset += padding
            desc_lines = self._wrap_text(card.stats.description, panel_width - padding * 2)
            for line in desc_lines:
                desc_surface = self.font_small.render(line, True, (180, 180, 200))
                self.screen.blit(desc_surface, (panel_x + padding, panel_y + y_offset))
                y_offset += status_spacing - 4

        self.card_info_content_height = y_offset - scroll_y
        self.screen.set_clip(None)

        # Draw scroll indicators
        if self.card_info_content_height > panel_height:
            if self.card_info_scroll < self.card_info_content_height - panel_height:
                hint = self.font_small.render("▼ прокрутка ▼", True, (150, 150, 150))
                hint_x = panel_x + (panel_width - hint.get_width()) // 2
                self.screen.blit(hint, (hint_x, panel_y + panel_height - 18))
            if self.card_info_scroll > 0:
                hint_up = self.font_small.render("▲ прокрутка ▲", True, (150, 150, 150))
                hint_x = panel_x + (panel_width - hint_up.get_width()) // 2
                self.screen.blit(hint_up, (hint_x, panel_y + 2))

    def scroll_card_info(self, direction: int):
        """Scroll the card info panel. direction: -1 = up, 1 = down."""
        self.card_info_scroll += direction * 20
        panel_height = scaled(UILayout.CARD_INFO_HEIGHT)
        max_scroll = max(0, self.card_info_content_height - panel_height)
        self.card_info_scroll = max(0, min(self.card_info_scroll, max_scroll))

    def _wrap_text(self, text: str, max_width: int) -> list:
        """Wrap text to fit within max_width pixels."""
        words = text.split(' ')
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            test_surface = self.font_small.render(test_line, True, (255, 255, 255))
            if test_surface.get_width() <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        return lines if lines else [text]

    def draw_messages(self, game: 'Game'):
        """Draw scrollable message log on the right side."""
        panel_x = UILayout.get_combat_log_x()
        panel_y = scaled(UILayout.COMBAT_LOG_Y)
        panel_width = scaled(UILayout.COMBAT_LOG_WIDTH)
        panel_height = scaled(UILayout.COMBAT_LOG_HEIGHT)
        line_height = scaled(UILayout.COMBAT_LOG_LINE_HEIGHT)
        max_text_width = panel_width - scaled(25)

        # Panel background
        pygame.draw.rect(self.screen, (25, 25, 30),
                         (panel_x, panel_y, panel_width, panel_height))
        pygame.draw.rect(self.screen, (60, 60, 70),
                         (panel_x, panel_y, panel_width, panel_height), 1)

        # Title
        title = "Журнал боя"
        title_surface = self.font_small.render(title, True, (150, 150, 160))
        self.screen.blit(title_surface, (panel_x + 5, panel_y + 3))

        # Wrap all messages
        display_lines = []
        for i, msg in enumerate(game.messages):
            wrapped = self._wrap_text(msg, max_text_width)
            for line in wrapped:
                display_lines.append((line, i))

        # Calculate visible lines
        visible_lines = (panel_height - 50) // line_height
        total_lines = len(display_lines)
        max_scroll = max(0, total_lines - visible_lines)
        self.log_scroll_offset = max(0, min(self.log_scroll_offset, max_scroll))

        start_idx = max(0, total_lines - visible_lines - self.log_scroll_offset)
        end_idx = total_lines - self.log_scroll_offset

        # Clipping rect
        title_gap = 28
        clip_rect = pygame.Rect(panel_x + 2, panel_y + title_gap, panel_width - 4, panel_height - title_gap - 22)
        self.screen.set_clip(clip_rect)

        y_offset = title_gap
        for i in range(start_idx, end_idx):
            if i < 0 or i >= total_lines:
                continue
            line_text, msg_idx = display_lines[i]
            color = (220, 220, 220)
            msg_surface = self.font_small.render(line_text, True, color)
            self.screen.blit(msg_surface, (panel_x + 5, panel_y + y_offset))
            y_offset += line_height

        self.screen.set_clip(None)

        # Scrollbar
        if total_lines > visible_lines:
            scrollbar_x = panel_x + panel_width - 12
            scrollbar_y = panel_y + 22
            scrollbar_height = panel_height - 44
            scrollbar_width = 8

            self.log_scrollbar_rect = pygame.Rect(scrollbar_x, scrollbar_y, scrollbar_width, scrollbar_height)
            self.log_max_scroll = max_scroll

            pygame.draw.rect(self.screen, (40, 40, 50),
                           (scrollbar_x, scrollbar_y, scrollbar_width, scrollbar_height))

            thumb_ratio = visible_lines / total_lines
            thumb_height = max(20, int(scrollbar_height * thumb_ratio))
            scroll_ratio = self.log_scroll_offset / max_scroll if max_scroll > 0 else 0
            thumb_y = scrollbar_y + int((scrollbar_height - thumb_height) * (1 - scroll_ratio))

            thumb_color = (130, 130, 150) if self.log_scrollbar_dragging else (100, 100, 120)
            pygame.draw.rect(self.screen, thumb_color,
                           (scrollbar_x, thumb_y, scrollbar_width, thumb_height))
            pygame.draw.rect(self.screen, (140, 140, 160),
                           (scrollbar_x, thumb_y, scrollbar_width, thumb_height), 1)
        else:
            self.log_scrollbar_rect = None
            self.log_max_scroll = 0

    def scroll_log(self, direction: int, game: 'Game'):
        """Scroll the message log. direction: -1=up (older), 1=down (newer)."""
        panel_width = UILayout.COMBAT_LOG_WIDTH
        max_text_width = panel_width - 15
        total_lines = 0
        for msg in game.messages:
            total_lines += len(self._wrap_text(msg, max_text_width))

        panel_height = UILayout.COMBAT_LOG_HEIGHT
        line_height = UILayout.COMBAT_LOG_LINE_HEIGHT
        visible_lines = (panel_height - 44) // line_height
        max_scroll = max(0, total_lines - visible_lines)

        self.log_scroll_offset -= direction
        self.log_scroll_offset = max(0, min(self.log_scroll_offset, max_scroll))

    def start_log_scrollbar_drag(self, mouse_x: int, mouse_y: int) -> bool:
        """Start dragging the log scrollbar. Returns True if drag started."""
        if self.log_scrollbar_rect and self.log_scrollbar_rect.collidepoint(mouse_x, mouse_y):
            self.log_scrollbar_dragging = True
            self._update_log_scroll_from_mouse(mouse_y)
            return True
        return False

    def drag_log_scrollbar(self, mouse_y: int):
        """Update log scroll position while dragging."""
        if self.log_scrollbar_dragging:
            self._update_log_scroll_from_mouse(mouse_y)

    def stop_log_scrollbar_drag(self):
        """Stop dragging the log scrollbar."""
        self.log_scrollbar_dragging = False

    def _update_log_scroll_from_mouse(self, mouse_y: int):
        """Update log scroll offset based on mouse Y position."""
        if not self.log_scrollbar_rect or self.log_max_scroll <= 0:
            return
        rel_y = mouse_y - self.log_scrollbar_rect.y
        ratio = rel_y / self.log_scrollbar_rect.height
        ratio = max(0, min(1, ratio))
        self.log_scroll_offset = int((1 - ratio) * self.log_max_scroll)
        self.log_scroll_offset = max(0, min(self.log_scroll_offset, self.log_max_scroll))

    def draw_dice_panel(self, game: 'Game'):
        """Draw dice panel - shows pending or last combat dice in one row."""
        panel_x = WINDOW_WIDTH // 2 - scaled(200)
        panel_y = scaled(10)
        panel_width = scaled(400)
        panel_height = scaled(35)

        if game.awaiting_priority and game.pending_dice_roll:
            bg_color = (50, 40, 60)
            border_color = (100, 80, 140)
        else:
            bg_color = (50, 30, 30)
            border_color = COLOR_TEXT

        pygame.draw.rect(self.screen, bg_color,
                         (panel_x, panel_y, panel_width, panel_height))
        pygame.draw.rect(self.screen, border_color,
                         (panel_x, panel_y, panel_width, panel_height), 2)

        # Get dice context - use pending_dice_roll during priority, last_combat otherwise
        dice = None
        if game.awaiting_priority and game.pending_dice_roll:
            dice = game.pending_dice_roll
        elif game.last_combat:
            # Create pseudo-dice context from last combat result
            dice = game.last_combat

        if dice is None:
            return

        # Draw title
        title = self.font_small.render("Кубики:", True, COLOR_TEXT)
        self.screen.blit(title, (panel_x + 10, panel_y + 8))

        x_offset = panel_x + 80

        # Handle DiceContext (during priority phase)
        if hasattr(dice, 'atk_roll'):
            # Attacker info
            attacker = game.board.get_card_by_id(dice.attacker_id) if dice.attacker_id else None
            atk_name = attacker.name[:8] if attacker else "Атк"
            atk_has_mods = dice.atk_modifier != 0 or dice.atk_bonus != 0
            atk_total = dice.atk_roll + dice.atk_modifier + dice.atk_bonus
            atk_text = f"{atk_name}: [{dice.atk_roll}]"
            if dice.atk_modifier != 0:
                atk_text += f"{'+' if dice.atk_modifier > 0 else ''}{dice.atk_modifier}"
            if dice.atk_bonus != 0:
                atk_text += f" +{dice.atk_bonus}"
            if atk_has_mods:
                atk_text += f" = {atk_total}"

            atk_surface = self.font_small.render(atk_text, True, COLOR_PLAYER1)
            self.screen.blit(atk_surface, (x_offset, panel_y + 8))
            x_offset += atk_surface.get_width() + 20

            # Defender info (if combat, not ranged)
            if dice.def_roll > 0:
                defender = game.board.get_card_by_id(dice.defender_id) if dice.defender_id else None
                def_name = defender.name[:8] if defender else "Защ"
                def_has_mods = dice.def_modifier != 0 or dice.def_bonus != 0
                def_total = dice.def_roll + dice.def_modifier + dice.def_bonus
                def_text = f"{def_name}: [{dice.def_roll}]"
                if dice.def_modifier != 0:
                    def_text += f"{'+' if dice.def_modifier > 0 else ''}{dice.def_modifier}"
                if dice.def_bonus != 0:
                    def_text += f" +{dice.def_bonus}"
                if def_has_mods:
                    def_text += f" = {def_total}"

                def_surface = self.font_small.render(def_text, True, COLOR_PLAYER2)
                self.screen.blit(def_surface, (x_offset, panel_y + 8))

        # Handle CombatResult (after combat resolved)
        elif hasattr(dice, 'attacker_roll'):
            atk_total = dice.attacker_roll + dice.attacker_bonus
            def_total = dice.defender_roll + dice.defender_bonus

            atk_text = f"{dice.attacker_name[:8]}: [{dice.attacker_roll}]"
            if dice.attacker_bonus != 0:
                atk_text += f" +{dice.attacker_bonus} = {atk_total}"

            atk_surface = self.font_small.render(atk_text, True, COLOR_PLAYER1)
            self.screen.blit(atk_surface, (x_offset, panel_y + 8))
            x_offset += atk_surface.get_width() + 20

            if dice.defender_roll > 0:
                def_text = f"{dice.defender_name[:8]}: [{dice.defender_roll}]"
                if dice.defender_bonus != 0:
                    def_text += f" +{dice.defender_bonus} = {def_total}"

                def_surface = self.font_small.render(def_text, True, COLOR_PLAYER2)
                self.screen.blit(def_surface, (x_offset, panel_y + 8))

    def draw_turn_indicator(self, game: 'Game'):
        """Draw turn indicator background (text drawn in native pass)."""
        if game.awaiting_priority:
            self._turn_indicator_state = {'visible': False}
            return

        info_x = WINDOW_WIDTH - scaled(UILayout.PRIORITY_BAR_X_OFFSET)
        info_y = scaled(UILayout.PRIORITY_BAR_Y)
        info_width = scaled(UILayout.PRIORITY_BAR_WIDTH)
        info_height = scaled(UILayout.PRIORITY_BAR_HEIGHT)

        is_my_turn = game.current_player == self.viewing_player

        if is_my_turn:
            bg_color = (40, 60, 40)
            border_color = (80, 140, 80)
        else:
            bg_color = (60, 40, 40)
            border_color = (140, 80, 80)

        pygame.draw.rect(self.screen, bg_color, (info_x, info_y, info_width, info_height))
        pygame.draw.rect(self.screen, border_color, (info_x, info_y, info_width, info_height), 2)

        self._turn_indicator_state = {
            'is_my_turn': is_my_turn,
            'rect': pygame.Rect(info_x, info_y, info_width, info_height),
            'visible': True
        }

    def draw_priority_info(self, game: 'Game'):
        """Draw priority phase info under buttons."""
        if not game.awaiting_priority:
            return

        # Hide turn indicator when showing priority (they share the same position)
        self._turn_indicator_state = {'visible': False}

        info_x = WINDOW_WIDTH - scaled(UILayout.PRIORITY_BAR_X_OFFSET)
        info_y = scaled(UILayout.PRIORITY_BAR_Y)
        info_width = scaled(UILayout.PRIORITY_BAR_WIDTH)
        info_height = scaled(UILayout.PRIORITY_BAR_HEIGHT)

        pygame.draw.rect(self.screen, (50, 40, 70), (info_x, info_y, info_width, info_height))
        pygame.draw.rect(self.screen, (100, 80, 140), (info_x, info_y, info_width, info_height), 2)

        is_my_priority = game.priority_player == self.viewing_player
        if is_my_priority:
            priority_text = "Ваш приоритет"
            priority_color = (100, 200, 100)
        else:
            priority_text = "Приоритет противника"
            priority_color = (200, 100, 100)
        text_surface = self.font_medium.render(priority_text, True, priority_color)
        text_x = info_x + (info_width - text_surface.get_width()) // 2
        self.screen.blit(text_surface, (text_x, info_y + 4))

    def draw_side_control_indicator(self, controlled_player: Optional[int]):
        """Draw indicator showing which side is being controlled (test game mode)."""
        x = scaled(10)
        y = scaled(10)

        if controlled_player is None:
            text = "TAB: Авто (ход)"
            bg_color = (40, 40, 40)
            border_color = (80, 80, 80)
        elif controlled_player == 1:
            text = "TAB: Игрок 1"
            bg_color = (35, 65, 90)
            border_color = COLOR_PLAYER1
        else:
            text = "TAB: Игрок 2"
            bg_color = (90, 35, 35)
            border_color = COLOR_PLAYER2

        text_surface = self.font_small.render(text, True, COLOR_TEXT)
        padding = scaled(6)
        width = text_surface.get_width() + padding * 2
        height = text_surface.get_height() + padding * 2

        pygame.draw.rect(self.screen, bg_color, (x, y, width, height))
        pygame.draw.rect(self.screen, border_color, (x, y, width, height), 2)
        self.screen.blit(text_surface, (x + padding, y + padding))

    # Button methods
    def get_end_turn_button_rect(self) -> pygame.Rect:
        """Get the end turn button rectangle for click detection."""
        return pygame.Rect(
            scaled(UILayout.END_TURN_X),
            scaled(UILayout.END_TURN_Y),
            scaled(UILayout.END_TURN_WIDTH),
            scaled(UILayout.END_TURN_HEIGHT)
        )

    def get_skip_button_rect(self) -> pygame.Rect:
        """Get the skip button rectangle for click detection."""
        return pygame.Rect(
            scaled(UILayout.SKIP_X),
            scaled(UILayout.SKIP_Y),
            scaled(UILayout.SKIP_WIDTH),
            scaled(UILayout.SKIP_HEIGHT)
        )

    def get_pass_button_rect(self) -> pygame.Rect:
        """Get the pass priority button rectangle."""
        return pygame.Rect(
            scaled(UILayout.SKIP_X),
            scaled(UILayout.SKIP_Y),
            scaled(UILayout.SKIP_WIDTH),
            scaled(UILayout.SKIP_HEIGHT)
        )

    def draw_skip_button(self, game: 'Game'):
        """Draw skip button under the combat log."""
        button_rect = self.get_skip_button_rect()
        draw_button_simple(self.screen, button_rect, "Пропустить",
                          self.font_medium, style='skip')

    def draw_pass_button(self, game: 'Game'):
        """Draw pass priority button (same style as skip)."""
        button_rect = self.get_pass_button_rect()
        draw_button_simple(self.screen, button_rect, "Пасс",
                          self.font_medium, style='pass')

    # Click handlers
    def get_clicked_ability(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if an ability button was clicked. Returns ability_id or None."""
        for rect, ability_id in self.ability_button_rects:
            if rect.collidepoint(mouse_x, mouse_y):
                return ability_id
        return None

    def get_clicked_attack_button(self, mouse_x: int, mouse_y: int) -> bool:
        """Check if the attack button was clicked."""
        if self.attack_button_rect and self.attack_button_rect.collidepoint(mouse_x, mouse_y):
            return True
        return False

    # =========================================================================
    # DICE DISPLAY
    # =========================================================================

    def update_dice_display(self, game: 'Game', dt: float):
        """Update dice display state based on game state."""
        # Check if there's a dice roll to display
        dice_context = None
        if game.pending_dice_roll:
            dice_context = game.pending_dice_roll
        elif game.last_combat and not game.awaiting_defender:
            dice_context = game.last_combat

        if dice_context is None:
            # Clear dice display with fade out
            if self.dice_display_state and not self.dice_display_state.get('fading'):
                self.dice_display_state['fading'] = True
            if self.dice_display_state and self.dice_display_state.get('fading'):
                self.dice_display_state['anim_timer'] -= dt * 3  # Fade out
                if self.dice_display_state['anim_timer'] <= 0:
                    self.dice_display_state = None
            return

        # Get roll values based on context type
        if hasattr(dice_context, 'atk_roll'):
            # DiceContext from pending_dice_roll
            atk_roll = dice_context.atk_roll
            def_roll = dice_context.def_roll
            atk_mod = dice_context.atk_modifier
            def_mod = dice_context.def_modifier
            atk_bonus = dice_context.atk_bonus
            def_bonus = dice_context.def_bonus
            atk_id = dice_context.attacker_id
            def_id = dice_context.defender_id or dice_context.target_id
            atk_player = None
            def_player = None
        else:
            # CombatResult from last_combat - use stored player info
            atk_roll = dice_context.attacker_roll
            def_roll = dice_context.defender_roll
            atk_mod = 0
            def_mod = 0
            atk_bonus = dice_context.attacker_bonus
            def_bonus = dice_context.defender_bonus
            atk_id = None
            def_id = None
            atk_player = dice_context.attacker_player
            def_player = dice_context.defender_player

        # Determine which player each die belongs to (from cards if available)
        if atk_player is None:
            atk_player = 1
            if atk_id:
                atk_card = game.get_card_by_id(atk_id)
                if atk_card:
                    atk_player = atk_card.player
        if def_player is None:
            def_player = 2
            if def_id:
                def_card = game.get_card_by_id(def_id)
                if def_card:
                    def_player = def_card.player

        # Check if this is a new roll or same roll
        is_new_roll = (not self.dice_display_state or
                       self.dice_display_state['atk_roll'] != atk_roll or
                       self.dice_display_state['def_roll'] != def_roll)

        if is_new_roll:
            # New roll - start animation from 0
            self.dice_display_state = {
                'atk_roll': atk_roll,
                'def_roll': def_roll,
                'atk_total_bonus': atk_mod + atk_bonus,
                'def_total_bonus': def_mod + def_bonus,
                'atk_player': atk_player,
                'def_player': def_player,
                'anim_timer': 0,  # Start from 0 for entrance animation
                'fading': False,
            }
        else:
            # Same roll - update bonuses and progress animation
            self.dice_display_state['atk_total_bonus'] = atk_mod + atk_bonus
            self.dice_display_state['def_total_bonus'] = def_mod + def_bonus
            self.dice_display_state['fading'] = False
            # Animate entrance
            if self.dice_display_state['anim_timer'] < UILayout.DICE_ANIM_DURATION:
                self.dice_display_state['anim_timer'] = min(
                    UILayout.DICE_ANIM_DURATION,
                    self.dice_display_state['anim_timer'] + dt * 2
                )

    def clear_dice_display(self):
        """Clear dice display state. Call when starting a new game."""
        self.dice_display_state = None

    def draw_dice_display(self, game: 'Game'):
        """Draw dice icons below graveyards."""
        if not self.dice_display_state or not self.dice_images:
            return

        state = self.dice_display_state
        anim_progress = min(1.0, state['anim_timer'] / UILayout.DICE_ANIM_DURATION)

        # Easing function for smooth animation
        ease = 1 - (1 - anim_progress) ** 3  # Ease out cubic

        dice_size = scaled(UILayout.DICE_SIZE)
        spacing = scaled(UILayout.DICE_SPACING)

        # Determine positions based on viewing player
        # Left side = opponent, Right side = us
        if self.viewing_player == 1:
            left_player = 2
            right_player = 1
        else:
            left_player = 1
            right_player = 2

        # Calculate positions anchored to board edges
        left_x = scaled(UILayout.BOARD_LEFT_X - UILayout.DICE_X_OFFSET - UILayout.DICE_SIZE)
        left_y = scaled(UILayout.GRAVEYARD_P1_Y + UILayout.DICE_Y_OFFSET)
        right_x = scaled(UILayout.BOARD_RIGHT_X + UILayout.DICE_X_OFFSET)
        right_y = scaled(UILayout.GRAVEYARD_P1_Y + UILayout.DICE_Y_OFFSET)

        # Draw attacker's die
        if state['atk_roll'] > 0 and state['atk_roll'] in self.dice_images:
            if state['atk_player'] == left_player:
                x, y = left_x, left_y
                x_offset = int((1 - ease) * -dice_size)
            else:
                x, y = right_x, right_y
                x_offset = int((1 - ease) * dice_size)

            self._draw_single_die(x + x_offset, y, state['atk_roll'],
                                 state['atk_total_bonus'], ease)

        # Draw defender's die
        if state['def_roll'] > 0 and state['def_roll'] in self.dice_images:
            if state['def_player'] == left_player:
                x, y = left_x, left_y
                x_offset = int((1 - ease) * -dice_size)
            else:
                x, y = right_x, right_y
                x_offset = int((1 - ease) * dice_size)

            self._draw_single_die(x + x_offset, y, state['def_roll'],
                                 state['def_total_bonus'], ease)

    def _draw_single_die(self, x: int, y: int, roll: int, bonus: int, alpha: float):
        """Draw a single die with bonus text."""
        if roll not in self.dice_images:
            return

        dice_size = scaled(UILayout.DICE_SIZE)
        spacing = scaled(UILayout.DICE_SPACING)

        # Draw die image with alpha
        die_img = self.dice_images[roll]
        if alpha < 1.0:
            die_img = die_img.copy()
            die_img.set_alpha(int(255 * alpha))

        self.screen.blit(die_img, (x, y))

        # Draw bonus text below die
        if bonus != 0:
            bonus_text = f"+{bonus}" if bonus > 0 else str(bonus)
            if bonus > 0:
                color = (100, 200, 100)  # Green for positive
            else:
                color = (200, 100, 100)  # Red for negative

            text_surface = self.font_small.render(bonus_text, True, color)
            text_x = x + (dice_size - text_surface.get_width()) // 2
            text_y = y + dice_size + spacing

            if alpha < 1.0:
                text_surface.set_alpha(int(255 * alpha))

            self.screen.blit(text_surface, (text_x, text_y))
