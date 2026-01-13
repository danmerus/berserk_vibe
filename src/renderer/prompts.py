"""In-game prompts - defender selection, valhalla, heal confirm, etc."""
import pygame
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, TYPE_CHECKING

from ..constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT,
    COLOR_TEXT, scaled, UILayout
)

if TYPE_CHECKING:
    from ..game import Game
    from .base import PopupConfig


@dataclass
class ChoiceOption:
    """Configuration for a choice button."""
    id: str
    label: str
    color: Tuple[int, int, int]
    hover_color: Tuple[int, int, int]


@dataclass
class ChoicePromptConfig:
    """Configuration for a two-option choice prompt."""
    popup_id: str
    title: str
    question: str
    option1: ChoiceOption
    option2: ChoiceOption
    title_color: Tuple[int, int, int] = (255, 255, 255)
    bg_color: Tuple[int, int, int, int] = (40, 50, 70, 230)
    border_color: Tuple[int, int, int] = (100, 150, 200)
    btn_width: int = 100


class PromptsMixin:
    """Mixin for in-game prompt dialogs."""

    def draw_choice_prompt(self, config: ChoicePromptConfig):
        """Draw a generic two-option choice prompt.

        This is the unified method for yes/no and similar two-button prompts.
        Stores buttons in self.choice_buttons[popup_id] for click detection.
        """
        from .base import PopupConfig

        popup_config = PopupConfig(
            popup_id=config.popup_id,
            width=scaled(UILayout.POPUP_HEAL_WIDTH),
            height=scaled(UILayout.POPUP_HEAL_HEIGHT),
            bg_color=config.bg_color,
            border_color=config.border_color,
            title=config.title,
            title_color=config.title_color,
        )

        x, y, content_y = self.draw_popup_base(popup_config)

        # Question text
        content_y = self.draw_popup_text(x, popup_config.width, content_y,
                                         config.question, (255, 255, 255))

        # Buttons
        btn_width = scaled(config.btn_width)
        btn_height = scaled(30)
        gap = scaled(20)
        btn_y = content_y + 3

        btn1_rect = self.draw_popup_button(
            x + popup_config.width // 2 - btn_width - gap // 2, btn_y,
            btn_width, btn_height, config.option1.label,
            config.option1.color, config.option1.hover_color)

        btn2_rect = self.draw_popup_button(
            x + popup_config.width // 2 + gap // 2, btn_y,
            btn_width, btn_height, config.option2.label,
            config.option2.color, config.option2.hover_color)

        self.choice_buttons[config.popup_id] = [
            (config.option1.id, btn1_rect),
            (config.option2.id, btn2_rect)
        ]

    def get_clicked_choice_button(self, popup_id: str, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if a choice button was clicked. Returns button id or None."""
        buttons = self.choice_buttons.get(popup_id, [])
        for button_id, rect in buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return button_id
        return None

    def clear_choice_buttons(self, popup_id: str):
        """Clear choice buttons for a popup."""
        self.choice_buttons[popup_id] = []

    def draw_heal_confirm_prompt(self, game: 'Game'):
        """Draw the heal confirmation prompt with clickable buttons (draggable)."""
        if not game.awaiting_heal_confirm or not game.interaction:
            self.clear_choice_buttons('heal_confirm')
            return

        attacker = game.get_card_by_id(game.interaction.actor_id)
        heal_amount = game.interaction.context.get('heal_amount', 0)
        if not attacker:
            self.clear_choice_buttons('heal_confirm')
            return

        config = ChoicePromptConfig(
            popup_id='heal_confirm',
            title=f"ЛЕЧЕНИЕ: {attacker.name}",
            question=f"Восстановить {heal_amount} HP?",
            option1=ChoiceOption('yes', "Да", (40, 140, 60), (100, 220, 120)),
            option2=ChoiceOption('no', "Нет", (140, 40, 40), (220, 100, 100)),
            title_color=(180, 255, 200),
            bg_color=UILayout.POPUP_HEAL_BG,
            border_color=UILayout.POPUP_HEAL_BORDER,
        )
        self.draw_choice_prompt(config)

    def draw_untap_confirm_prompt(self, game: 'Game'):
        """Draw the untap confirmation prompt - card may untap at opponent's turn start."""
        if not game.awaiting_untap_confirm or not game.interaction:
            self.clear_choice_buttons('untap_confirm')
            return

        card = game.get_card_by_id(game.interaction.actor_id)
        acting_player = game.interaction.acting_player
        if not card:
            self.clear_choice_buttons('untap_confirm')
            return

        config = ChoicePromptConfig(
            popup_id='untap_confirm',
            title=f"ИГРОК {acting_player}: {card.name}",
            question="Открыться?",
            option1=ChoiceOption('yes', "Да", (40, 100, 140), (100, 180, 220)),
            option2=ChoiceOption('no', "Нет", (80, 80, 80), (140, 140, 140)),
            title_color=(180, 200, 255),
            bg_color=(40, 50, 70, 230),
            border_color=(100, 150, 200),
        )
        self.draw_choice_prompt(config)

    def draw_stench_choice_prompt(self, game: 'Game'):
        """Draw the stench choice prompt - target must tap or take damage (draggable)."""
        if not game.awaiting_stench_choice or not game.interaction:
            self.clear_choice_buttons('stench_choice')
            return

        target = game.get_card_by_id(game.interaction.target_id)
        damage = game.interaction.context.get('damage_amount', 2)
        if not target:
            self.clear_choice_buttons('stench_choice')
            return

        config = ChoicePromptConfig(
            popup_id='stench_choice',
            title=f"ЗЛОВОНИЕ: {target.name}",
            question=f"Закрыться или получить {damage} урона?",
            option1=ChoiceOption('tap', "Закрыться", (80, 60, 40), (160, 120, 80)),
            option2=ChoiceOption('damage', f"Получить {damage}", (140, 40, 40), (220, 100, 100)),
            title_color=(255, 200, 150),
            bg_color=UILayout.POPUP_STENCH_BG,
            border_color=UILayout.POPUP_STENCH_BORDER,
            btn_width=130,
        )
        self.draw_choice_prompt(config)

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

    def draw_generic_selection_prompt(self, game: 'Game'):
        """Draw a generic selection prompt using interaction config."""
        if not game.interaction or not game.interaction.is_board_selection:
            return
        # Skip defender - it has its own special prompt with card images
        if game.awaiting_defender:
            return

        from ..interaction import get_interaction_config, InteractionKind
        from .base import PopupConfig

        acting_player = game.interaction.acting_player
        interaction_config = get_interaction_config(game.interaction.kind)

        if not interaction_config.prompt_title:
            return

        # For Valhalla, add ability description
        extra_text = None
        extra_height = 0
        if game.interaction.kind == InteractionKind.SELECT_VALHALLA_TARGET:
            ability_id = game.interaction.context.get('ability_id')
            if ability_id:
                from ..abilities import get_ability
                ability = get_ability(ability_id)
                if ability and ability.description:
                    extra_text = ability.description
                    extra_height = scaled(20)

        popup_config = PopupConfig(
            popup_id=f'selection_{game.interaction.kind.name.lower()}',
            width=scaled(UILayout.POPUP_SHOT_WIDTH + 50),
            height=scaled(UILayout.POPUP_SHOT_HEIGHT + 20) + extra_height,
            bg_color=(40, 50, 70, 230),
            border_color=(100, 150, 200),
            title=f"ИГРОК {acting_player}: {interaction_config.prompt_title}",
            title_color=(180, 200, 255),
        )

        x, y, content_y = self.draw_popup_base(popup_config)

        # Instructions
        text = interaction_config.prompt_text or "Выберите цель"
        content_y = self.draw_popup_text(x, popup_config.width, content_y,
                            text, (200, 200, 255), self.font_small)

        # Extra description for Valhalla
        if extra_text:
            self.draw_popup_text(x, popup_config.width, content_y + 3,
                                extra_text, (255, 220, 150), self.font_small)

    def draw_waiting_for_opponent_prompt(self, game: 'Game'):
        """Draw a waiting indicator when opponent needs to make a decision."""
        if not game.interaction or not game.interaction.acting_player:
            return

        from ..interaction import get_interaction_config

        acting_player = game.interaction.acting_player
        config = get_interaction_config(game.interaction.kind)

        # Use configured waiting text, or fallback
        if config.waiting_text:
            message = f"Игрок {acting_player} {config.waiting_text}"
        else:
            message = f"Ожидание игрока {acting_player}..."

        from .base import PopupConfig
        popup_config = PopupConfig(
            popup_id='waiting_opponent',
            width=scaled(UILayout.POPUP_HEAL_WIDTH + 50),
            height=scaled(60),
            bg_color=(50, 50, 70, 200),
            border_color=(100, 100, 150),
            title=None,
        )

        x, y, content_y = self.draw_popup_base(popup_config)

        # Draw waiting message
        self.draw_popup_text(x, popup_config.width, y + 20, message, (200, 200, 255))

    # Click handlers for prompts
    def get_clicked_exchange_button(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Check if an exchange choice button was clicked. Returns 'full', 'reduce', or None."""
        for button_id, rect in self.exchange_buttons:
            if rect.collidepoint(mouse_x, mouse_y):
                return button_id
        return None
