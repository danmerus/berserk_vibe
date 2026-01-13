"""In-game prompts - defender selection, valhalla, heal confirm, etc."""
import pygame
from typing import Optional, List, Tuple, TYPE_CHECKING

from ..constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT,
    COLOR_TEXT, scaled, UILayout
)

if TYPE_CHECKING:
    from ..game import Game
    from .base import PopupConfig


class PromptsMixin:
    """Mixin for in-game prompt dialogs."""

    def draw_counter_shot_prompt(self, game: 'Game'):
        """Draw the counter shot target selection prompt (draggable)."""
        if not game.awaiting_counter_shot or not game.interaction:
            return

        attacker = game.get_card_by_id(game.interaction.actor_id)
        if not attacker:
            return

        from .base import PopupConfig
        config = PopupConfig(
            popup_id='counter_shot',
            width=scaled(UILayout.POPUP_SHOT_WIDTH),
            height=scaled(UILayout.POPUP_SHOT_HEIGHT),
            bg_color=UILayout.POPUP_SHOT_BG,
            border_color=UILayout.POPUP_SHOT_BORDER,
            title=f"ВЫСТРЕЛ: {attacker.name}",
            title_color=(255, 200, 150),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Instructions
        self.draw_popup_text(x, config.width, content_y,
                            "Выберите цель (ОРАНЖЕВЫЕ клетки)",
                            (255, 220, 180), self.font_small)

    def draw_movement_shot_prompt(self, game: 'Game'):
        """Draw the movement shot target selection prompt (draggable)."""
        if not game.awaiting_movement_shot or not game.interaction:
            return

        shooter = game.get_card_by_id(game.interaction.actor_id)
        if not shooter:
            return

        from .base import PopupConfig
        config = PopupConfig(
            popup_id='movement_shot',
            width=scaled(UILayout.POPUP_SHOT_WIDTH + 50),  # Slightly wider for longer text
            height=scaled(UILayout.POPUP_SHOT_HEIGHT + 35),
            bg_color=UILayout.POPUP_SHOT_BG,
            border_color=UILayout.POPUP_SHOT_BORDER,
            title=f"ВЫСТРЕЛ: {shooter.name}",
            title_color=(255, 200, 150),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Instructions
        self.draw_popup_text(x, config.width, content_y,
                            "Рядом с союзником 7+ кристаллов!",
                            (255, 220, 180), self.font_small)
        self.draw_popup_text(x, config.width, content_y + 18,
                            "Выберите цель (или пропустите)",
                            (200, 200, 200), self.font_small)

    def draw_heal_confirm_prompt(self, game: 'Game'):
        """Draw the heal confirmation prompt with clickable buttons (draggable)."""
        if not game.awaiting_heal_confirm or not game.interaction:
            self.heal_confirm_buttons = []
            return

        attacker = game.get_card_by_id(game.interaction.actor_id)
        heal_amount = game.interaction.context.get('heal_amount', 0)
        if not attacker:
            self.heal_confirm_buttons = []
            return

        from .base import PopupConfig
        config = PopupConfig(
            popup_id='heal_confirm',
            width=scaled(UILayout.POPUP_HEAL_WIDTH),
            height=scaled(UILayout.POPUP_HEAL_HEIGHT),
            bg_color=UILayout.POPUP_HEAL_BG,
            border_color=UILayout.POPUP_HEAL_BORDER,
            title=f"ЛЕЧЕНИЕ: {attacker.name}",
            title_color=(180, 255, 200),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Heal amount
        content_y = self.draw_popup_text(x, config.width, content_y,
                                         f"Восстановить {heal_amount} HP?", (255, 255, 255))

        # Buttons
        btn_width, btn_height, gap = scaled(100), scaled(30), scaled(20)
        btn_y = content_y + 3

        yes_rect = self.draw_popup_button(
            x + config.width // 2 - btn_width - gap // 2, btn_y,
            btn_width, btn_height, "Да", (40, 140, 60), (100, 220, 120))

        no_rect = self.draw_popup_button(
            x + config.width // 2 + gap // 2, btn_y,
            btn_width, btn_height, "Нет", (140, 40, 40), (220, 100, 100))

        self.heal_confirm_buttons = [('yes', yes_rect), ('no', no_rect)]

    def draw_stench_choice_prompt(self, game: 'Game'):
        """Draw the stench choice prompt - target must tap or take damage (draggable)."""
        if not game.awaiting_stench_choice or not game.interaction:
            self.stench_choice_buttons = []
            return

        target = game.get_card_by_id(game.interaction.target_id)
        damage = game.interaction.context.get('damage_amount', 2)
        if not target:
            self.stench_choice_buttons = []
            return

        from .base import PopupConfig
        config = PopupConfig(
            popup_id='stench_choice',
            width=scaled(UILayout.POPUP_STENCH_WIDTH),
            height=scaled(UILayout.POPUP_STENCH_HEIGHT),
            bg_color=UILayout.POPUP_STENCH_BG,
            border_color=UILayout.POPUP_STENCH_BORDER,
            title=f"ЗЛОВОНИЕ: {target.name}",
            title_color=(255, 200, 150),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Description
        content_y = self.draw_popup_text(x, config.width, content_y,
                                         f"Закрыться или получить {damage} урона?", (255, 255, 255))

        # Buttons
        btn_width, btn_height, gap = scaled(130), scaled(30), scaled(20)
        btn_y = content_y + 3

        tap_rect = self.draw_popup_button(
            x + config.width // 2 - btn_width - gap // 2, btn_y,
            btn_width, btn_height, "Закрыться", (80, 60, 40), (160, 120, 80))

        damage_rect = self.draw_popup_button(
            x + config.width // 2 + gap // 2, btn_y,
            btn_width, btn_height, f"Получить {damage}", (140, 40, 40), (220, 100, 100))

        self.stench_choice_buttons = [('tap', tap_rect), ('damage', damage_rect)]

    def draw_exchange_prompt(self, game: 'Game'):
        """Draw the exchange choice prompt with clickable buttons (draggable)."""
        if not game.awaiting_exchange_choice or not game.interaction:
            self.exchange_buttons = []
            return

        attacker = game.get_card_by_id(game.interaction.actor_id)
        defender = game.get_card_by_id(game.interaction.target_id)
        if not attacker or not defender:
            self.exchange_buttons = []
            return
        ctx = game.interaction.context
        attacker_advantage = ctx.get('attacker_advantage', True)
        roll_diff = ctx.get('roll_diff', 0)

        # Tier names for display
        tier_names = {0: "слабый", 1: "средний", 2: "сильный"}

        if attacker_advantage:
            # Attacker chooses - roll_diff is 2 or 4
            if roll_diff == 4:
                atk_current_tier = 2  # Strong
                atk_reduced_tier = 1  # Medium
            else:  # roll_diff == 2
                atk_current_tier = 1  # Medium
                atk_reduced_tier = 0  # Weak

            # Full option: deal current tier, receive weak counter
            full_deal = tier_names[atk_current_tier]
            full_receive = tier_names[0]  # Weak counter
            # Reduced option: deal reduced tier, receive nothing
            reduced_deal = tier_names[atk_reduced_tier]
            reduced_receive = "промах"

            title = "ОБМЕН УДАРАМИ"
            full_line1 = f"Нанести {full_deal}"
            full_line2 = f"Получить {full_receive}"
            reduced_line1 = f"Нанести {reduced_deal}"
            reduced_line2 = f"Получить {reduced_receive}"
        else:
            # Defender chooses - roll_diff is -4
            def_current_tier = 1  # Medium counter
            def_reduced_tier = 0  # Weak counter

            # Full option: receive weak attack, counter with current tier
            full_receive = tier_names[0]  # Weak attack
            full_counter = tier_names[def_current_tier]
            # Reduced option: receive nothing, counter with reduced tier
            reduced_receive = "промах"
            reduced_counter = tier_names[def_reduced_tier]

            title = "ОБМЕН УДАРАМИ"
            full_line1 = f"Получить {full_receive}"
            full_line2 = f"Контратака {full_counter}"
            reduced_line1 = f"Получить {reduced_receive}"
            reduced_line2 = f"Контратака {reduced_counter}"

        from .base import PopupConfig
        config = PopupConfig(
            popup_id='exchange',
            width=scaled(UILayout.POPUP_EXCHANGE_WIDTH),
            height=scaled(UILayout.POPUP_EXCHANGE_HEIGHT),
            bg_color=UILayout.POPUP_EXCHANGE_BG,
            border_color=UILayout.POPUP_EXCHANGE_BORDER,
            title=title,
            title_color=(255, 220, 150),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Two-line buttons with damage descriptions
        btn_width, btn_height = scaled(145), scaled(50)
        margin = scaled(10)
        btn_y = content_y + scaled(5)

        # Full button on left (brown = attack with counter)
        full_x = x + margin
        full_rect = pygame.Rect(full_x, btn_y, btn_width, btn_height)
        pygame.draw.rect(self.screen, (140, 80, 40), full_rect)
        pygame.draw.rect(self.screen, (220, 140, 80), full_rect, 2)
        # Two lines of text
        line1_surf = self.font_small.render(full_line1, True, (255, 255, 255))
        line2_surf = self.font_small.render(full_line2, True, (255, 200, 200))
        self.screen.blit(line1_surf, (full_x + (btn_width - line1_surf.get_width()) // 2, btn_y + scaled(8)))
        self.screen.blit(line2_surf, (full_x + (btn_width - line2_surf.get_width()) // 2, btn_y + scaled(28)))

        # Reduce button on right (green = safe attack)
        reduce_x = x + config.width - margin - btn_width
        reduce_rect = pygame.Rect(reduce_x, btn_y, btn_width, btn_height)
        pygame.draw.rect(self.screen, (40, 100, 60), reduce_rect)
        pygame.draw.rect(self.screen, (80, 180, 100), reduce_rect, 2)
        # Two lines of text
        line1_surf = self.font_small.render(reduced_line1, True, (255, 255, 255))
        line2_surf = self.font_small.render(reduced_line2, True, (200, 255, 200))
        self.screen.blit(line1_surf, (reduce_x + (btn_width - line1_surf.get_width()) // 2, btn_y + scaled(8)))
        self.screen.blit(line2_surf, (reduce_x + (btn_width - line2_surf.get_width()) // 2, btn_y + scaled(28)))

        self.exchange_buttons = [('full', full_rect), ('reduce', reduce_rect)]

    def draw_valhalla_prompt(self, game: 'Game'):
        """Draw the Valhalla target selection prompt (draggable)."""
        if not game.interaction:
            return

        from ..abilities import get_ability
        dead_card = game.get_card_by_id(game.interaction.actor_id)
        ability_id = game.interaction.context.get('ability_id')
        ability = get_ability(ability_id) if ability_id else None
        if not dead_card or not ability:
            return

        from .base import PopupConfig
        config = PopupConfig(
            popup_id='valhalla',
            width=scaled(UILayout.POPUP_VALHALLA_WIDTH),
            height=scaled(UILayout.POPUP_VALHALLA_HEIGHT),
            bg_color=UILayout.POPUP_VALHALLA_BG,
            border_color=UILayout.POPUP_VALHALLA_BORDER,
            title=f"ВАЛЬХАЛЛА: {dead_card.name}",
            title_color=(255, 220, 150),
        )

        x, y, content_y = self.draw_popup_base(config)

        # Effect description
        content_y = self.draw_popup_text(x, config.width, content_y, ability.description, (255, 255, 255))

        # Instructions
        self.draw_popup_text(x, config.width, content_y,
                            "Выберите существо (ЗОЛОТЫЕ клетки)",
                            (255, 230, 180), self.font_small)

    def draw_defender_prompt(self, game: 'Game'):
        """Draw the defender choice prompt banner (draggable)."""
        interaction = game.interaction
        if not interaction:
            return
        attacker = game.get_card_by_id(interaction.actor_id)
        target = game.get_card_by_id(interaction.target_id)
        if not attacker or not target:
            return
        defending_player = target.player

        from .base import PopupConfig
        config = PopupConfig(
            popup_id='defender',
            width=scaled(UILayout.POPUP_DEFENDER_WIDTH),
            height=scaled(UILayout.POPUP_DEFENDER_HEIGHT),
            bg_color=UILayout.POPUP_DEFENDER_BG,
            border_color=UILayout.POPUP_DEFENDER_BORDER,
            title=f"ИГРОК {defending_player}: ВЫБОР ЗАЩИТНИКА",
        )

        x, y, content_y = self.draw_popup_base(config)

        # Attack info
        info = f"{attacker.name} атакует {target.name}"
        content_y = self.draw_popup_text(x, config.width, content_y, info, (255, 255, 255))

        # Instructions
        self.draw_popup_text(x, config.width, content_y + 5,
                            "Выберите защитника (или пропустите)",
                            (200, 255, 255), self.font_small)

    # Click handlers for prompts
    def get_clicked_heal_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if a heal confirmation button was clicked. Returns 'yes', 'no', or None."""
        for button_id, rect in self.heal_confirm_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return button_id
        return None

    def get_clicked_exchange_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if an exchange choice button was clicked. Returns 'full', 'reduce', or None."""
        for button_id, rect in self.exchange_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return button_id
        return None

    def get_clicked_stench_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if a stench choice button was clicked. Returns 'tap', 'damage', or None."""
        for button_id, rect in self.stench_choice_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return button_id
        return None
