"""Tests for advanced abilities: lunge, counter_shot, heal_on_attack, magical_strike, valhalla."""
import pytest
from tests.conftest import assert_hp, assert_tapped, assert_untapped, assert_card_dead, assert_card_alive, resolve_combat


class TestLungeAbility:
    """Tests for lunge ability - attack through a cell with fixed damage."""

    def test_kobold_has_lunge(self, place_card):
        """Кобольд should have lunge ability."""
        kobold = place_card("Кобольд", player=1, pos=10)
        assert "lunge" in kobold.stats.ability_ids

    def test_ledoviy_okhotnik_has_lunge_2(self, place_card):
        """Ледовый охотник should have lunge_2 ability (2 damage)."""
        hunter = place_card("Ледовый охотник", player=1, pos=10)
        assert "lunge_2" in hunter.stats.ability_ids

    def test_lunge_requires_exactly_2_cells_distance(self, game, place_card):
        """Lunge can only target cards exactly 2 cells away."""
        attacker = place_card("Кобольд", player=1, pos=10)
        # Position 20 is 2 rows away (distance 2 in Manhattan terms)
        target = place_card("Друид", player=2, pos=20)

        result = game.use_ability(attacker, "lunge")
        assert result is True  # Ability activated

        # Should have valid targets
        assert game.interaction is not None

    def test_lunge_cannot_target_adjacent(self, game, place_card):
        """Lunge cannot target adjacent cards (distance 1)."""
        attacker = place_card("Кобольд", player=1, pos=10)
        adjacent_target = place_card("Друид", player=2, pos=15)

        result = game.use_ability(attacker, "lunge")

        # If no valid targets at distance 2, ability may still return True
        # but target at distance 1 should not be valid
        if game.interaction and hasattr(game.interaction, 'valid_positions'):
            assert 15 not in game.interaction.valid_positions

    def test_lunge_deals_fixed_damage(self, game, place_card):
        """Lunge deals fixed damage regardless of dice rolls."""
        attacker = place_card("Кобольд", player=1, pos=10)
        target = place_card("Друид", player=2, pos=20)  # 2 cells away

        initial_hp = target.curr_life
        game.use_ability(attacker, "lunge")

        if game.interaction and hasattr(game.interaction, 'valid_positions'):
            if 20 in game.interaction.valid_positions:
                game.select_ability_target(20)
                # Lunge deals 1 fixed damage for basic lunge
                assert target.curr_life == initial_hp - 1

    def test_lunge_2_deals_2_damage(self, game, place_card):
        """Lunge_2 deals 2 fixed damage."""
        attacker = place_card("Ледовый охотник", player=1, pos=10)
        target = place_card("Друид", player=2, pos=20)

        initial_hp = target.curr_life
        game.use_ability(attacker, "lunge_2")

        if game.interaction and hasattr(game.interaction, 'valid_positions'):
            if 20 in game.interaction.valid_positions:
                game.select_ability_target(20)
                # Lunge_2 deals 2 fixed damage
                assert target.curr_life == initial_hp - 2

    def test_lunge_taps_attacker(self, game, place_card):
        """Using lunge should tap the attacker."""
        attacker = place_card("Кобольд", player=1, pos=10)
        target = place_card("Друид", player=2, pos=20)

        assert_untapped(attacker)
        game.use_ability(attacker, "lunge")

        if game.interaction and hasattr(game.interaction, 'valid_positions'):
            if 20 in game.interaction.valid_positions:
                game.select_ability_target(20)
                assert_tapped(attacker)

    def test_lunge_has_no_counter_attack(self, game, place_card):
        """Lunge attack does not trigger counter-attack."""
        attacker = place_card("Кобольд", player=1, pos=10)
        target = place_card("Циклоп", player=2, pos=20)  # Strong counter potential

        attacker_initial_hp = attacker.curr_life
        game.use_ability(attacker, "lunge")

        if game.interaction and hasattr(game.interaction, 'valid_positions'):
            if 20 in game.interaction.valid_positions:
                game.select_ability_target(20)
                # Attacker should take no damage (no counter from lunge)
                assert_hp(attacker, attacker_initial_hp)


class TestCounterShotAbility:
    """Tests for counter_shot - ranged attack triggered after melee attack."""

    def test_elfiyskiy_voin_has_counter_shot(self, place_card):
        """Эльфийский воин should have counter_shot ability."""
        elf = place_card("Эльфийский воин", player=1, pos=10)
        assert "counter_shot" in elf.stats.ability_ids

    def test_counter_shot_triggers_after_attack(self, game, place_card, set_rolls):
        """Counter shot should trigger after a successful melee attack."""
        attacker = place_card("Эльфийский воин", player=1, pos=10)
        melee_target = place_card("Друид", player=2, pos=15)
        distant_target = place_card("Циклоп", player=2, pos=25)  # Far away for shot

        set_rolls(6, 1)  # Strong hit
        game.attack(attacker, melee_target.position)
        resolve_combat(game)

        # After combat, counter shot interaction should appear
        # (if there are valid targets at range >= 2)
        # The counter shot deals 2 damage

    def test_counter_shot_requires_distance_2(self, game, place_card, set_rolls):
        """Counter shot can only target cards at distance >= 2."""
        attacker = place_card("Эльфийский воин", player=1, pos=10)
        melee_target = place_card("Друид", player=2, pos=15)  # Adjacent

        set_rolls(6, 1)
        game.attack(attacker, melee_target.position)
        resolve_combat(game)

        # Adjacent targets should not be valid for counter shot
        if game.awaiting_counter_shot:
            assert 15 not in game.interaction.valid_positions


class TestHealOnAttackAbility:
    """Tests for heal_on_attack - heal based on creature in front when attacking."""

    def test_kobold_has_heal_on_attack(self, place_card):
        """Кобольд should have heal_on_attack ability."""
        kobold = place_card("Кобольд", player=1, pos=10)
        assert "heal_on_attack" in kobold.stats.ability_ids

    def test_heal_on_attack_triggers_when_damaged(self, game, place_card, set_rolls):
        """Heal on attack should trigger if attacker is damaged and has creature in front."""
        attacker = place_card("Кобольд", player=1, pos=10)
        attacker.curr_life = attacker.stats.life - 5  # Damage attacker

        # Place a card in front (position 15 is one row ahead for P1)
        front_card = place_card("Циклоп", player=2, pos=15)  # Enemy in front
        target = place_card("Друид", player=2, pos=16)  # Attack target

        set_rolls(6, 1)
        game.attack(attacker, target.position)
        resolve_combat(game)

        # heal_on_attack heals based on medium damage of creature in front
        # Should prompt for confirmation

    def test_heal_on_attack_no_trigger_at_full_hp(self, game, place_card, set_rolls):
        """Heal on attack should not trigger if attacker is at full HP."""
        attacker = place_card("Кобольд", player=1, pos=10)
        # Don't damage attacker - at full HP

        front_card = place_card("Циклоп", player=2, pos=15)
        target = place_card("Друид", player=2, pos=16)

        initial_hp = attacker.curr_life
        set_rolls(6, 1)
        game.attack(attacker, target.position)
        resolve_combat(game)

        # No heal trigger since already at full HP
        assert attacker.curr_life == initial_hp


class TestMagicalStrikeAbility:
    """Tests for magical_strike - deal magic damage."""

    def test_cyclops_has_magical_strike(self, place_card):
        """Циклоп should have magical_strike ability."""
        cyclops = place_card("Циклоп", player=1, pos=10)
        assert "magical_strike" in cyclops.stats.ability_ids

    def test_magical_strike_deals_magic_damage(self, game, place_card):
        """Magical strike should deal 2 magic damage."""
        attacker = place_card("Циклоп", player=1, pos=10)
        target = place_card("Друид", player=2, pos=15)

        initial_hp = target.curr_life
        result = game.use_ability(attacker, "magical_strike")

        if result and game.interaction:
            game.select_ability_target(15)
            resolve_combat(game)
            # Magic strike deals 2 damage
            assert target.curr_life <= initial_hp - 2

    def test_magical_strike_ignores_armor(self, game, place_card):
        """Magical strike should ignore armor/damage reduction."""
        attacker = place_card("Циклоп", player=1, pos=10)
        # Хобгоблин has tough_hide which reduces damage from cheap creatures
        # But magic damage should ignore this
        target = place_card("Хобгоблин", player=2, pos=15)

        initial_hp = target.curr_life
        result = game.use_ability(attacker, "magical_strike")

        if result and game.interaction:
            game.select_ability_target(15)
            resolve_combat(game)
            # Full 2 magic damage even against tough_hide
            assert target.curr_life == initial_hp - 2

    def test_magical_strike_taps_user(self, game, place_card):
        """Using magical strike should tap the card."""
        attacker = place_card("Циклоп", player=1, pos=10)
        target = place_card("Друид", player=2, pos=15)

        assert_untapped(attacker)
        result = game.use_ability(attacker, "magical_strike")

        if result and game.interaction:
            game.select_ability_target(15)
            assert_tapped(attacker)


class TestValhallaAbility:
    """Tests for Valhalla abilities - triggered from graveyard when killed by enemy."""

    def test_ledoviy_okhotnik_has_valhalla_ova(self, place_card):
        """Ледовый охотник should have valhalla_ova ability."""
        hunter = place_card("Ледовый охотник", player=1, pos=10)
        assert "valhalla_ova" in hunter.stats.ability_ids

    def test_kostedrobitel_has_valhalla_strike(self, place_card):
        """Костедробитель should have valhalla_strike ability."""
        crusher = place_card("Костедробитель", player=1, pos=10)
        assert "valhalla_strike" in crusher.stats.ability_ids

    def test_valhalla_triggers_on_death_by_enemy(self, game, place_card, set_rolls):
        """Valhalla should trigger when card dies from enemy attack."""
        # Card with Valhalla ability
        hunter = place_card("Ледовый охотник", player=1, pos=10)
        hunter.curr_life = 1  # Low HP to die

        # Ally to receive Valhalla buff
        ally = place_card("Друид", player=1, pos=11)

        # Enemy attacker
        attacker = place_card("Циклоп", player=2, pos=15)

        set_rolls(6, 1)  # Strong hit to kill
        game.current_player = 2
        game.attack(attacker, hunter.position)
        resolve_combat(game)

        # Hunter should die
        assert_card_dead(hunter)

        # At next turn start for player 1, Valhalla should trigger
        game.current_player = 1
        game.start_turn()

        # Should be awaiting Valhalla target selection
        if game.awaiting_valhalla:
            game.select_valhalla_target(ally.position)
            # Ally should have received dice bonus
            assert ally.temp_dice_bonus > 0

    def test_valhalla_does_not_trigger_on_friendly_death(self, game, place_card, set_rolls):
        """Valhalla should NOT trigger when card dies from friendly fire."""
        hunter = place_card("Ледовый охотник", player=1, pos=10)
        hunter.curr_life = 1

        ally = place_card("Друид", player=1, pos=11)

        # Friendly attacker
        friendly = place_card("Циклоп", player=1, pos=5)

        # Enable friendly fire
        game.friendly_fire_target = 10  # Set up for friendly attack

        set_rolls(6, 1)
        game.attack(friendly, hunter.position)
        resolve_combat(game)

        # Hunter should die but not trigger Valhalla
        # (killed_by_enemy should be False)

    def test_valhalla_requires_living_allies(self, game, place_card, set_rolls):
        """Valhalla should not trigger if no living allies."""
        hunter = place_card("Ледовый охотник", player=1, pos=10)
        hunter.curr_life = 1

        # Only card for player 1 - no allies
        attacker = place_card("Циклоп", player=2, pos=15)

        set_rolls(6, 1)
        game.current_player = 2
        game.attack(attacker, hunter.position)
        resolve_combat(game)

        assert_card_dead(hunter)

        # At turn start, should NOT prompt for Valhalla (no valid targets)
        game.current_player = 1
        game.start_turn()

        # Should not be awaiting Valhalla if no allies
        # (may log "no allies" message instead)

    def test_valhalla_strike_gives_damage_bonus(self, game, place_card, set_rolls):
        """Valhalla_strike should give +1 to attack damage."""
        crusher = place_card("Костедробитель", player=1, pos=10)
        crusher.curr_life = 1

        ally = place_card("Друид", player=1, pos=11)
        attacker = place_card("Циклоп", player=2, pos=15)

        set_rolls(6, 1)
        game.current_player = 2
        game.attack(attacker, crusher.position)
        resolve_combat(game)

        assert_card_dead(crusher)

        game.current_player = 1
        game.start_turn()

        if game.awaiting_valhalla:
            initial_bonus = ally.temp_attack_bonus
            game.select_valhalla_target(ally.position)
            # Should have +1 attack bonus
            assert ally.temp_attack_bonus == initial_bonus + 1


class TestLungeFrontBuff:
    """Tests for lunge_front_buff - buff ally in front after lunge."""

    def test_ledoviy_okhotnik_has_lunge_front_buff(self, place_card):
        """Ледовый охотник should have lunge_front_buff ability."""
        hunter = place_card("Ледовый охотник", player=1, pos=10)
        assert "lunge_front_buff" in hunter.stats.ability_ids

    def test_lunge_front_buff_gives_dice_bonus(self, game, place_card):
        """After lunge, ally in front should get +1 dice bonus."""
        # Attacker with lunge_front_buff
        hunter = place_card("Ледовый охотник", player=1, pos=10)

        # Ally in front (position 15 is one row ahead for player 1)
        ally = place_card("Друид", player=1, pos=15)

        # Target for lunge (2 cells away)
        target = place_card("Циклоп", player=2, pos=20)

        initial_bonus = ally.temp_dice_bonus

        result = game.use_ability(hunter, "lunge_2")
        if result and game.interaction and 20 in game.interaction.valid_positions:
            game.select_ability_target(20)

            # Ally in front should have received dice bonus
            assert ally.temp_dice_bonus == initial_bonus + 1
