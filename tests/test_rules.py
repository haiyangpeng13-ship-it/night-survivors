"""Tests for rules.py only (no drawing, no pygame)."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rules  # noqa: E402

DATA = rules.load_data()


def new_state(seed=1, spawn=True, wand=False):
    """A fresh game. Switch spawning and the wand off to look at one rule at a time."""
    state = rules.State(DATA, rng=random.Random(seed))
    state.weapon_wait["spark_wand"] = (
        DATA["weapons"]["spark_wand"]["levels"][0]["interval"] if wand else 1000.0
    )
    if not spawn:
        state.spawn_wait = 1000.0
    return state


def run(state, steps, target=None):
    for _ in range(steps):
        rules.step(state, target)


def tough_enemy(state, x, y, hp=1000.0):
    """An enemy that survives the test so we can count the hits."""
    state.add_enemy("bat", x, y)
    state.enemies[-1]["hp"] = hp
    return state.enemies[-1]


class Spawning(unittest.TestCase):
    def test_new_bats_appear_on_the_circle_around_the_hero(self):
        state = new_state()
        state.spawn_wait = 0.0
        rules.spawn_enemies(state)
        for enemy in state.enemies:
            gap = rules.distance(state.hero["x"], state.hero["y"], enemy["x"], enemy["y"])
            self.assertAlmostEqual(gap, DATA["spawn"]["radius"], places=6)

    def test_spawning_stops_at_the_per_second_cap_then_fills_the_minimum(self):
        state = new_state()
        state.spawn_wait = 0.0
        rules.spawn_enemies(state)
        self.assertEqual(len(state.enemies), DATA["spawn"]["max_per_second"])
        state.spawn_wait = 0.0
        rules.spawn_enemies(state)
        self.assertEqual(len(state.enemies), rules.current_wave(state)["min_alive"])

    def test_never_more_than_the_max_alive(self):
        state = new_state()
        state.data = {**DATA, "waves": [{"from": 0, "types": ["bat"], "min_alive": 500}]}
        for _ in range(200):
            state.spawn_wait = 0.0
            rules.spawn_enemies(state)
        self.assertEqual(len(state.enemies), DATA["spawn"]["max_alive"])

    def test_the_wave_table_is_read_from_the_data_file(self):
        state = new_state()
        state.t = 20.0
        self.assertEqual(rules.current_wave(state)["min_alive"], 20)

    def test_far_bats_are_removed(self):
        state = new_state()
        state.add_enemy("bat", DATA["spawn"]["despawn_radius"] + 100.0, 0.0)
        run(state, 1)
        self.assertEqual(state.enemies, [])


class Damage(unittest.TestCase):
    def test_hero_walks_toward_the_pointer(self):
        state = new_state()
        run(state, 60, target=(200.0, 0.0))
        self.assertAlmostEqual(state.hero["x"], DATA["hero"]["speed"], places=1)

    def test_hero_stops_inside_the_dead_zone(self):
        state = new_state()
        run(state, 60, target=(state.hero["x"] + DATA["hero"]["dead_zone"] - 1, 0.0))
        self.assertEqual(state.hero["x"], 0.0)

    def test_a_bat_hurts_once_every_half_second(self):
        state = new_state()
        state.add_enemy("bat", state.hero["x"], state.hero["y"])
        run(state, 27)
        self.assertEqual(state.hero["hp"], 100 - DATA["enemies"]["bat"]["damage"])
        run(state, 33)
        self.assertEqual(state.hero["hp"], 100 - 2 * DATA["enemies"]["bat"]["damage"])

    def test_spark_wand_kills_a_bat(self):
        state = new_state(spawn=False, wand=True)
        state.add_enemy("bat", 120.0, 0.0)
        run(state, 90)
        self.assertEqual(state.kills, 1)
        self.assertEqual(state.enemies, [])

    def test_wand_stays_quiet_without_an_enemy(self):
        state = new_state(spawn=False, wand=True)
        run(state, 120)
        self.assertEqual(state.sparks, [])

    def test_spin_blades_hit_a_bat_on_the_orbit(self):
        state = new_state(spawn=False)
        state.weapons = {"spin_blades": 1}
        enemy = tough_enemy(state, 65.0, 0.0)
        run(state, 30)
        self.assertEqual(enemy["hp"], 1000 - DATA["weapons"]["spin_blades"]["levels"][0]["damage"])

    def test_holy_ring_hurts_everything_inside_and_waits_half_a_second(self):
        state = new_state(spawn=False)
        state.weapons = {"holy_ring": 1}
        ring = DATA["weapons"]["holy_ring"]
        inside = tough_enemy(state, 40.0, 0.0)
        outside = tough_enemy(state, 200.0, 0.0)
        run(state, 29)
        self.assertEqual(inside["hp"], 1000 - ring["levels"][0]["damage"])
        self.assertEqual(outside["hp"], 1000)
        run(state, 5)
        self.assertEqual(inside["hp"], 1000 - 2 * ring["levels"][0]["damage"])


class Growth(unittest.TestCase):
    def test_a_dead_bat_leaves_a_gem_worth_its_xp(self):
        state = new_state(spawn=False)
        tough_enemy(state, 300.0, 0.0, hp=0.0)
        rules.remove_dead_enemies(state)
        self.assertEqual(state.kills, 1)
        self.assertEqual([gem["xp"] for gem in state.gems], [DATA["enemies"]["bat"]["xp"]])

    def test_a_gem_inside_the_magnet_radius_flies_to_the_hero(self):
        state = new_state(spawn=False)
        magnet = DATA["hero"]["magnet_radius"]
        state.gems.append({"xp": 2, "x": magnet - 10.0, "y": 0.0})
        run(state, 5)
        self.assertLess(state.gems[0]["x"], magnet - 10.0)
        run(state, 60)
        self.assertEqual(state.gems, [])
        self.assertEqual(state.xp, 2)

    def test_a_gem_outside_the_magnet_radius_waits_there(self):
        state = new_state(spawn=False)
        state.gems.append({"xp": 1, "x": DATA["hero"]["magnet_radius"] + 50.0, "y": 0.0})
        run(state, 30)
        self.assertEqual(state.gems[0]["x"], DATA["hero"]["magnet_radius"] + 50.0)
        self.assertEqual(state.xp, 0)

    def test_enough_xp_levels_up_and_shows_three_cards(self):
        state = new_state(spawn=False)
        state.xp = rules.xp_needed(state)
        run(state, 1)
        self.assertEqual(state.level, 2)
        self.assertEqual(state.xp, 0)
        self.assertTrue(state.awaiting_choice)
        self.assertEqual(len(state.cards), DATA["level_up"]["cards"])

    def test_the_world_stops_while_a_card_is_chosen(self):
        state = new_state(spawn=False)
        state.awaiting_choice = True
        state.cards = [rules.new_card(state, "magnet", "passive", 1)] * 3
        before = state.t
        run(state, 60, target=(300.0, 0.0))
        self.assertEqual(state.t, before)
        self.assertEqual(state.hero["x"], 0.0)

    def test_the_xp_curve_is_five_then_three_more_each_level(self):
        state = new_state(spawn=False)
        needed = [rules.xp_needed(state)]
        for _ in range(3):
            state.level += 1
            needed.append(rules.xp_needed(state))
        self.assertEqual(needed, [5, 8, 11, 14])

    def test_a_weapon_card_adds_or_levels_up_a_weapon(self):
        state = new_state(spawn=False)
        rules.apply_card(state, rules.new_card(state, "spin_blades", "weapon", 1))
        self.assertEqual(state.weapons["spin_blades"], 1)
        rules.apply_card(state, rules.new_card(state, "spin_blades", "weapon", 2))
        self.assertEqual(state.weapons["spin_blades"], 2)

    def test_passive_cards_change_the_hero(self):
        state = new_state(spawn=False)
        rules.apply_card(state, rules.new_card(state, "big_heart", "passive", 1))
        self.assertEqual(state.hero["max_hp"], 120)
        self.assertEqual(state.hero["hp"], 120)
        rules.apply_card(state, rules.new_card(state, "swift_boots", "passive", 1))
        self.assertAlmostEqual(rules.hero_speed(state), 132.0, places=6)
        rules.apply_card(state, rules.new_card(state, "magnet", "passive", 1))
        self.assertEqual(rules.magnet_radius(state), 90)

    def test_heal_card_gives_back_hp_but_never_more_than_the_maximum(self):
        state = new_state(spawn=False)
        state.hero["hp"] = 10
        rules.apply_card(state, rules.new_card(state, "heal", "heal", None))
        self.assertEqual(state.hero["hp"], 40)
        state.hero["hp"] = 95
        rules.apply_card(state, rules.new_card(state, "heal", "heal", None))
        self.assertEqual(state.hero["hp"], 100)


class Cards(unittest.TestCase):
    def test_kinds_in_the_pool(self):
        state = new_state(spawn=False)
        kinds = {(card["kind"], card["type"]) for card in rules.card_pool(state)}
        self.assertIn(("spark_wand", "weapon"), kinds)
        self.assertIn(("holy_ring", "weapon"), kinds)
        self.assertIn(("magnet", "passive"), kinds)

    def test_no_new_weapon_once_the_hero_has_three(self):
        state = new_state(spawn=False)
        state.weapons = {"spark_wand": 1, "spin_blades": 1, "holy_ring": 1}
        new_weapons = [
            card
            for card in rules.card_pool(state)
            if card["type"] == "weapon" and card["kind"] not in state.weapons
        ]
        self.assertEqual(new_weapons, [])

    def test_nothing_maxed_is_ever_offered(self):
        state = new_state(spawn=False)
        state.weapons = {kind: DATA["levels_max"] for kind in DATA["weapons"]}
        state.passives = {kind: DATA["levels_max"] for kind in DATA["passives"]}
        self.assertEqual(rules.card_pool(state), [])

    def test_only_heal_is_left_when_nothing_can_be_offered(self):
        state = new_state(spawn=False)
        state.weapons = {kind: DATA["levels_max"] for kind in DATA["weapons"]}
        state.passives = {kind: DATA["levels_max"] for kind in DATA["passives"]}
        cards = rules.make_cards(state)
        self.assertEqual(len(cards), DATA["level_up"]["cards"])
        self.assertEqual({card["type"] for card in cards}, {"heal"})

    def test_a_choice_is_applied_and_the_game_goes_on(self):
        state = new_state(spawn=False)
        state.cards = rules.make_cards(state)
        state.awaiting_choice = True
        rules.choose(state, 0)
        self.assertFalse(state.awaiting_choice)
        self.assertEqual(state.cards, [])
        run(state, 5)
        self.assertGreater(state.t, 0.0)


class Waves(unittest.TestCase):
    def wave_at(self, seconds):
        state = new_state(spawn=False)
        state.t = seconds
        return rules.current_wave(state)

    def test_the_wave_table_comes_from_the_data_file(self):
        self.assertEqual(self.wave_at(35.0)["types"], ["bat", "slime"])
        self.assertEqual(self.wave_at(50.0)["types"], ["slime", "ghost"])
        self.assertEqual(self.wave_at(65.0)["types"], ["bat", "ghost"])
        self.assertEqual(self.wave_at(110.0), {"from": 105, "types": ["bat"], "min_alive": 75})

    def test_the_boss_wave_names_the_boss(self):
        self.assertEqual(self.wave_at(90.0).get("boss"), "demon")
        self.assertIsNone(self.wave_at(89.0).get("boss"))

    def test_each_enemy_follows_its_own_speed(self):
        for kind, steps in (("slime", 60), ("ghost", 60)):
            state = new_state(spawn=False)
            state.add_enemy(kind, 200.0, 0.0)
            run(state, steps)
            travelled = DATA["enemies"][kind]["speed"] * steps * state.dt
            self.assertAlmostEqual(state.enemies[0]["x"], 200.0 - travelled, places=1)

    def test_the_ghost_is_faster_than_the_hero(self):
        self.assertGreater(DATA["enemies"]["ghost"]["speed"], DATA["hero"]["speed"])

    def test_a_slime_hurts_the_hero_for_its_own_damage(self):
        state = new_state(spawn=False)
        state.add_enemy("slime", state.hero["x"], state.hero["y"])
        run(state, 1)
        self.assertEqual(state.hero["hp"], 100 - DATA["enemies"]["slime"]["damage"])

    def test_the_boss_appears_once(self):
        state = new_state(spawn=False)
        state.t = 90.0
        run(state, 1)
        run(state, 120)
        bosses = [e for e in state.enemies if e["kind"] == "demon"]
        self.assertEqual(len(bosses), 1)
        self.assertTrue(state.boss_spawned)

    def test_the_boss_is_never_removed_but_is_pulled_back_close(self):
        state = new_state(spawn=False)
        state.boss_spawned = True
        state.add_enemy("demon", DATA["spawn"]["despawn_radius"] + 200.0, 0.0)
        run(state, 1)
        self.assertEqual(len(state.enemies), 1)
        gap = rules.distance(0.0, 0.0, state.enemies[0]["x"], state.enemies[0]["y"])
        self.assertAlmostEqual(gap, DATA["spawn"]["radius"], places=6)

    def test_the_boss_drops_no_gem(self):
        state = new_state(spawn=False)
        state.add_enemy("demon", 100.0, 0.0)
        state.enemies[0]["hp"] = 0.0
        rules.remove_dead_enemies(state)
        self.assertEqual(state.kills, 1)
        self.assertEqual(state.gems, [])

    def test_surviving_to_the_goal_is_a_victory(self):
        state = new_state(spawn=False)
        state.boss_spawned = True
        state.t = DATA["victory_at"] - 5.0
        run(state, 320)
        self.assertTrue(state.won)
        self.assertTrue(state.game_over)
        self.assertEqual(state.hero["hp"], 100)

    def test_a_won_game_does_not_change(self):
        state = new_state()
        state.won = True
        state.game_over = True
        run(state, 60, target=(500.0, 500.0))
        self.assertEqual(state.t, 0.0)


class Feel(unittest.TestCase):
    """The little pieces main.py needs for sound and game feel."""

    def test_a_hit_leaves_a_damage_number_and_a_hit_event(self):
        state = new_state(spawn=False)
        enemy = tough_enemy(state, 100.0, 0.0)
        damage = DATA["weapons"]["spark_wand"]["levels"][0]["damage"]
        rules.damage_enemy(state, enemy, damage)
        self.assertEqual(enemy["hp"], 1000 - damage)
        self.assertEqual([number["text"] for number in state.numbers], [str(damage)])
        self.assertEqual(state.events, ["hit"])

    def test_the_numbers_float_up_and_then_go_away(self):
        state = new_state(spawn=False)
        enemy = tough_enemy(state, 100.0, 0.0)
        rules.damage_enemy(state, enemy, 5)
        start = state.numbers[0]["y"]
        run(state, 10)
        self.assertLess(state.numbers[0]["y"], start)
        run(state, int(DATA["feel"]["number_life"] / state.dt) + 1)
        self.assertEqual(state.numbers, [])

    def test_the_number_list_never_grows_for_ever(self):
        state = new_state(spawn=False)
        enemy = tough_enemy(state, 100.0, 0.0)
        for _ in range(DATA["feel"]["max_numbers"] + 10):
            rules.damage_enemy(state, enemy, 1)
        self.assertEqual(len(state.numbers), DATA["feel"]["max_numbers"])

    def test_a_dead_enemy_flashes_once_and_the_flash_fades(self):
        state = new_state(spawn=False)
        tough_enemy(state, 300.0, 0.0, hp=0.0)
        rules.remove_dead_enemies(state)
        self.assertEqual(len(state.flashes), 1)
        run(state, int(DATA["feel"]["flash_life"] / state.dt) + 1)
        self.assertEqual(state.flashes, [])

    def test_the_hero_shakes_when_an_enemy_hurts_him(self):
        state = new_state(spawn=False)
        state.add_enemy("bat", state.hero["x"], state.hero["y"])
        run(state, 1)
        self.assertAlmostEqual(state.shake, DATA["feel"]["shake"] - state.dt)
        self.assertEqual(state.events, ["hurt"])
        run(state, int(DATA["feel"]["shake"] / state.dt) + 1)
        self.assertEqual(state.shake, 0.0)

    def test_a_gem_picked_up_makes_a_gem_event(self):
        state = new_state(spawn=False)
        state.gems.append({"xp": 1, "x": 4.0, "y": 0.0})
        run(state, 5)
        self.assertEqual(state.events, ["gem"])
        self.assertEqual(state.xp, 1)

    def test_a_level_up_makes_an_event(self):
        state = new_state(spawn=False)
        state.xp = rules.xp_needed(state)
        run(state, 1)
        self.assertIn("level_up", state.events)

    def test_the_end_is_announced_once(self):
        state = new_state(spawn=False)
        state.hero["hp"] = 1.0
        state.add_enemy("bat", state.hero["x"], state.hero["y"])
        run(state, 1)
        self.assertEqual(state.events.count("end"), 1)
        run(state, 60)
        self.assertEqual(state.events.count("end"), 1)


class Losing(unittest.TestCase):
    def test_hp_reaching_zero_ends_the_game(self):
        state = new_state()
        state.hero["hp"] = DATA["enemies"]["bat"]["damage"]
        state.add_enemy("bat", state.hero["x"], state.hero["y"])
        run(state, 5)
        self.assertTrue(state.game_over)
        self.assertEqual(state.hero["hp"], 0)

    def test_a_dead_game_does_not_change(self):
        state = new_state()
        state.game_over = True
        run(state, 60, target=(500.0, 500.0))
        self.assertEqual(state.t, 0.0)
        self.assertEqual(state.enemies, [])


if __name__ == "__main__":
    unittest.main()
