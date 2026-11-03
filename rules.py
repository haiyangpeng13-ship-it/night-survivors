"""The rules of Night Survivors. Pure Python: no pygame in this file."""

import json
import math
import pathlib
import random


def load_data(path=None):
    if path is None:
        path = pathlib.Path(__file__).resolve().parent / "data" / "game.json"
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def distance(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def _move(x, y, tx, ty, step):
    """Move from (x, y) toward (tx, ty) by at most `step` pixels."""
    d = distance(x, y, tx, ty)
    if d == 0:
        return x, y
    step = min(step, d)
    return x + (tx - x) / d * step, y + (ty - y) / d * step


def weapon_level(state, kind):
    """The numbers of the level the hero has for this weapon."""
    levels = state.data["weapons"][kind]["levels"]
    return levels[min(state.weapons.get(kind, 1), state.data["levels_max"]) - 1]


def hero_speed(state):
    boots = state.passives.get("swift_boots", 0)
    bonus = state.data["passives"]["swift_boots"]["speed"]
    return state.data["hero"]["speed"] * (1 + bonus * boots)


def magnet_radius(state):
    levels = state.passives.get("magnet", 0)
    bonus = state.data["passives"]["magnet"]["magnet_radius"]
    return state.data["hero"]["magnet_radius"] + bonus * levels


def xp_needed(state):
    curve = state.data["xp"]
    return curve["first"] + curve["each_more"] * (state.level - 1)


def is_boss(state, enemy):
    return bool(state.data["enemies"][enemy["kind"]].get("boss"))


def on_the_circle(state, angle):
    """A point on the spawn circle, `radius` pixels away from the hero."""
    radius = state.data["spawn"]["radius"]
    return (
        state.hero["x"] + math.cos(angle) * radius,
        state.hero["y"] + math.sin(angle) * radius,
    )


def note(state, event):
    """Tell main.py what happened so it can play a sound."""
    state.events.append(event)


def damage_enemy(state, enemy, amount):
    """Every weapon hits through here: it leaves a number and a hit sound."""
    enemy["hp"] -= amount
    feel = state.data["feel"]
    state.numbers.append(
        {"x": enemy["x"], "y": enemy["y"], "text": str(int(amount)), "life": feel["number_life"]}
    )
    del state.numbers[: max(0, len(state.numbers) - feel["max_numbers"])]
    note(state, "hit")


class State:
    def __init__(self, data, rng=None):
        self.data = data
        self.rng = rng if rng is not None else random.Random()
        self.dt = data["time_step"]
        hero = data["hero"]
        self.t = 0.0
        self.hero = {
            "x": 0.0,
            "y": 0.0,
            "hp": float(hero["hp"]),
            "max_hp": float(hero["hp"]),
        }
        self.enemies = []
        self.sparks = []
        self.gems = []
        self.weapons = {"spark_wand": 1}
        self.passives = {}
        self.weapon_wait = {"spark_wand": weapon_level(self, "spark_wand")["interval"]}
        self.blade_angle = 0.0
        self.blade_hits = []
        self.ring_flash = 0.0
        self.level = 1
        self.xp = 0
        self.cards = []
        self.awaiting_choice = False
        self.next_uid = 1
        self.spawn_wait = data["spawn"]["every"]
        self.boss_spawned = False
        self.kills = 0
        self.won = False
        self.game_over = False
        self.events = []
        self.numbers = []
        self.flashes = []
        self.shake = 0.0

    def add_enemy(self, kind, x, y):
        stats = self.data["enemies"][kind]
        self.enemies.append(
            {
                "uid": self.next_uid,
                "kind": kind,
                "x": x,
                "y": y,
                "hp": float(stats["hp"]),
                "touch_wait": 0.0,
            }
        )
        self.next_uid += 1


def current_wave(state):
    """The wave entry that applies at state.t (the last one that has started)."""
    chosen = None
    for entry in state.data["waves"]:
        if entry["from"] <= state.t:
            chosen = entry
    if chosen is None:
        chosen = state.data["waves"][0]
    return chosen


def move_hero(state, target):
    if target is None:
        return
    hero = state.hero
    gap = distance(hero["x"], hero["y"], target[0], target[1])
    if gap <= state.data["hero"]["dead_zone"]:
        return
    hero["x"], hero["y"] = _move(
        hero["x"], hero["y"], target[0], target[1], hero_speed(state) * state.dt
    )


def spawn_enemies(state):
    state.spawn_wait -= state.dt
    if state.spawn_wait > 0:
        return
    spawn = state.data["spawn"]
    state.spawn_wait = spawn["every"]
    wave = current_wave(state)
    wanted = wave["min_alive"] - len(state.enemies)
    wanted = min(wanted, spawn["max_per_second"], spawn["max_alive"] - len(state.enemies))
    kinds = [kind for kind in wave["types"] if kind in state.data["enemies"]]
    if not kinds:
        return
    for _ in range(max(0, wanted)):
        angle = state.rng.uniform(0.0, 2.0 * math.pi)
        state.add_enemy(state.rng.choice(kinds), *on_the_circle(state, angle))


def spawn_boss(state):
    """The boss of a wave appears once, when that wave starts."""
    if state.boss_spawned:
        return
    for wave in state.data["waves"]:
        kind = wave.get("boss")
        if kind and wave["from"] <= state.t and kind in state.data["enemies"]:
            state.boss_spawned = True
            angle = state.rng.uniform(0.0, 2.0 * math.pi)
            state.add_enemy(kind, *on_the_circle(state, angle))
            return


def move_enemies(state):
    hero = state.hero
    for enemy in state.enemies:
        stats = state.data["enemies"][enemy["kind"]]
        enemy["x"], enemy["y"] = _move(
            enemy["x"], enemy["y"], hero["x"], hero["y"], stats["speed"] * state.dt
        )


def apply_contact_damage(state):
    hero = state.hero
    hero_radius = state.data["hero"]["hit_radius"]
    for enemy in state.enemies:
        enemy["touch_wait"] -= state.dt
        stats = state.data["enemies"][enemy["kind"]]
        touching = (
            distance(hero["x"], hero["y"], enemy["x"], enemy["y"])
            <= hero_radius + stats["radius"]
        )
        if touching and enemy["touch_wait"] <= 0:
            hero["hp"] -= stats["damage"]
            enemy["touch_wait"] = stats["touch_cooldown"]
            state.shake = state.data["feel"]["shake"]
            note(state, "hurt")


def remove_dead_enemies(state):
    """A dead enemy leaves a gem worth its XP and flashes once."""
    alive = []
    for enemy in state.enemies:
        if enemy["hp"] > 0:
            alive.append(enemy)
            continue
        state.kills += 1
        state.flashes.append(
            {"x": enemy["x"], "y": enemy["y"], "life": state.data["feel"]["flash_life"]}
        )
        xp = state.data["enemies"][enemy["kind"]]["xp"]
        if xp > 0:
            state.gems.append({"xp": xp, "x": enemy["x"], "y": enemy["y"]})
    state.enemies = alive


def fire_spark_wand(state):
    weapon = state.data["weapons"]["spark_wand"]
    wait = state.weapon_wait.get("spark_wand", 0.0) - state.dt
    if wait > 0 or not state.enemies:
        state.weapon_wait["spark_wand"] = wait
        return
    entry = weapon_level(state, "spark_wand")
    state.weapon_wait["spark_wand"] = entry["interval"]
    hero = state.hero
    left = list(state.enemies)
    for _ in range(entry["count"]):
        if not left:
            break
        target = min(left, key=lambda e: distance(hero["x"], hero["y"], e["x"], e["y"]))
        left.remove(target)
        gap = distance(hero["x"], hero["y"], target["x"], target["y"]) or 1.0
        state.sparks.append(
            {
                "x": hero["x"],
                "y": hero["y"],
                "vx": (target["x"] - hero["x"]) / gap * weapon["projectile_speed"],
                "vy": (target["y"] - hero["y"]) / gap * weapon["projectile_speed"],
                "distance": 0.0,
            }
        )


def move_sparks(state):
    if not state.sparks:
        return
    weapon = state.data["weapons"]["spark_wand"]
    damage = weapon_level(state, "spark_wand")["damage"]
    keep = []
    for spark in state.sparks:
        before = (spark["x"], spark["y"])
        spark["x"] += spark["vx"] * state.dt
        spark["y"] += spark["vy"] * state.dt
        spark["distance"] += distance(before[0], before[1], spark["x"], spark["y"])
        spent = spark["distance"] > weapon["range"]
        for enemy in state.enemies:
            reach = weapon["projectile_radius"] + state.data["enemies"][enemy["kind"]]["radius"]
            if distance(spark["x"], spark["y"], enemy["x"], enemy["y"]) <= reach:
                damage_enemy(state, enemy, damage)
                spent = True
                break
        if not spent:
            keep.append(spark)
    state.sparks = keep


def blade_positions(state):
    """Where the spinning blades are, evenly spread around the hero."""
    count = len(state.blade_hits)
    if count == 0:
        return []
    cfg = state.data["weapons"]["spin_blades"]
    spread = 2 * math.pi / count
    return [
        (
            state.hero["x"] + math.cos(state.blade_angle + i * spread) * cfg["orbit_radius"],
            state.hero["y"] + math.sin(state.blade_angle + i * spread) * cfg["orbit_radius"],
        )
        for i in range(count)
    ]


def fire_spin_blades(state):
    cfg = state.data["weapons"]["spin_blades"]
    entry = weapon_level(state, "spin_blades")
    state.blade_angle += 2 * math.pi / cfg["turn_seconds"] * state.dt
    if len(state.blade_hits) != entry["count"]:
        state.blade_hits = [{} for _ in range(entry["count"])]
    for hits, (bx, by) in zip(state.blade_hits, blade_positions(state)):
        for uid in list(hits):
            hits[uid] -= state.dt
            if hits[uid] <= 0:
                del hits[uid]
        for enemy in state.enemies:
            reach = cfg["blade_radius"] + state.data["enemies"][enemy["kind"]]["radius"]
            if enemy["uid"] not in hits and distance(bx, by, enemy["x"], enemy["y"]) <= reach:
                damage_enemy(state, enemy, entry["damage"])
                hits[enemy["uid"]] = cfg["hit_cooldown"]


def fire_holy_ring(state):
    cfg = state.data["weapons"]["holy_ring"]
    wait = state.weapon_wait.get("holy_ring", 0.0) - state.dt
    if wait > 0:
        state.weapon_wait["holy_ring"] = wait
        return
    entry = weapon_level(state, "holy_ring")
    state.weapon_wait["holy_ring"] = cfg["every"]
    state.ring_flash = cfg["flash"]
    for enemy in state.enemies:
        if distance(state.hero["x"], state.hero["y"], enemy["x"], enemy["y"]) <= entry["radius"]:
            damage_enemy(state, enemy, entry["damage"])


WEAPONS = {
    "spark_wand": fire_spark_wand,
    "spin_blades": fire_spin_blades,
    "holy_ring": fire_holy_ring,
}


def run_weapons(state):
    state.ring_flash = max(0.0, state.ring_flash - state.dt)
    for kind in list(state.weapons):
        WEAPONS[kind](state)
    remove_dead_enemies(state)


def move_gems(state):
    hero = state.hero
    reach = magnet_radius(state)
    left = []
    for gem in state.gems:
        gap = distance(hero["x"], hero["y"], gem["x"], gem["y"])
        if gap <= reach:
            gem["x"], gem["y"] = _move(
                gem["x"],
                gem["y"],
                hero["x"],
                hero["y"],
                state.data["gems"]["speed"] * state.dt,
            )
            gap = distance(hero["x"], hero["y"], gem["x"], gem["y"])
        if gap <= state.data["gems"]["pick_radius"]:
            state.xp += gem["xp"]
            note(state, "gem")
        else:
            left.append(gem)
    state.gems = left


def update_effects(state):
    """The damage numbers float up, the death flashes fade, the shake dies away."""
    feel = state.data["feel"]
    rising = feel["number_rise"] * state.dt
    keep = []
    for number in state.numbers:
        number["life"] -= state.dt
        number["y"] -= rising
        if number["life"] > 0:
            keep.append(number)
    state.numbers = keep
    for flash in state.flashes:
        flash["life"] -= state.dt
    state.flashes = [flash for flash in state.flashes if flash["life"] > 0]
    state.shake = max(0.0, state.shake - state.dt)


def remove_far_enemies(state):
    """Normal enemies that fall too far behind go away. The boss never does."""
    hero = state.hero
    spawn = state.data["spawn"]
    keep = []
    for enemy in state.enemies:
        gap = distance(hero["x"], hero["y"], enemy["x"], enemy["y"])
        if is_boss(state, enemy):
            if gap > spawn["boss_return_radius"]:
                angle = state.rng.uniform(0.0, 2.0 * math.pi)
                enemy["x"], enemy["y"] = on_the_circle(state, angle)
            keep.append(enemy)
        elif gap <= spawn["despawn_radius"]:
            keep.append(enemy)
    state.enemies = keep


def new_card(state, kind, card_type, level):
    if card_type == "heal":
        return {
            "kind": "heal",
            "type": "heal",
            "level": None,
            "name": "Heal",
            "text": f"heal {state.data['level_up']['heal']} HP",
        }
    meta = state.data["weapons" if card_type == "weapon" else "passives"][kind]
    return {
        "kind": kind,
        "type": card_type,
        "level": level,
        "name": meta["name"],
        "text": meta["text"],
    }


def card_pool(state):
    """Everything the hero could be offered: a new weapon, one more level, a passive item."""
    cards = []
    for kind in state.data["weapons"]:
        level = state.weapons.get(kind)
        if level is None:
            if len(state.weapons) < state.data["weapons_max"]:
                cards.append(new_card(state, kind, "weapon", 1))
        elif level < state.data["levels_max"]:
            cards.append(new_card(state, kind, "weapon", level + 1))
    for kind in state.data["passives"]:
        level = state.passives.get(kind, 0)
        if level < state.data["levels_max"]:
            cards.append(new_card(state, kind, "passive", level + 1))
    return cards


def make_cards(state):
    pool = card_pool(state)
    state.rng.shuffle(pool)
    count = state.data["level_up"]["cards"]
    cards = pool[:count]
    while len(cards) < count:
        cards.append(new_card(state, "heal", "heal", None))
    return cards


def apply_card(state, card):
    if card["type"] == "heal":
        heal = state.data["level_up"]["heal"]
        state.hero["hp"] = min(state.hero["max_hp"], state.hero["hp"] + heal)
    elif card["type"] == "weapon":
        kind = card["kind"]
        state.weapons[kind] = card["level"]
        state.weapon_wait.setdefault(kind, 0.0)
    else:
        meta = state.data["passives"][card["kind"]]
        state.passives[card["kind"]] = card["level"]
        if "max_hp" in meta:
            state.hero["max_hp"] += meta["max_hp"]
            state.hero["hp"] = min(state.hero["max_hp"], state.hero["hp"] + meta["heal"])


def choose(state, index):
    """The hero picks one card, so the game can go on."""
    if not state.awaiting_choice:
        return
    apply_card(state, state.cards[index])
    state.cards = []
    state.awaiting_choice = False


def check_level_up(state):
    if state.xp >= xp_needed(state):
        state.xp -= xp_needed(state)
        state.level += 1
        state.cards = make_cards(state)
        state.awaiting_choice = True
        note(state, "level_up")


def step(state, target=None):
    """Advance the world by one fixed time step."""
    if state.game_over or state.awaiting_choice:
        return
    state.t += state.dt
    move_hero(state, target)
    spawn_enemies(state)
    spawn_boss(state)
    move_enemies(state)
    apply_contact_damage(state)
    run_weapons(state)
    move_sparks(state)
    move_gems(state)
    remove_far_enemies(state)
    update_effects(state)
    check_level_up(state)
    if state.t >= state.data["victory_at"]:
        state.won = True
        state.game_over = True
        note(state, "end")
    elif state.hero["hp"] <= 0:
        state.hero["hp"] = 0.0
        state.game_over = True
        note(state, "end")
