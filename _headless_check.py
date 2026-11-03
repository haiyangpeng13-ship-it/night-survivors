"""Temporary headless check of main.py: drives input events without a window."""

import asyncio
import math
import os
import random

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame

import main
import rules

DATA = rules.load_data()
SIZE = (DATA["screen"]["width"], DATA["screen"]["height"])


def finger(event_type, x, y):
    return pygame.event.Event(
        event_type,
        dict(x=x, y=y, dx=0.0, dy=0.0, pressure=1.0, touch_id=0, finger_id=0),
    )


def fresh_state(seed=7):
    state = rules.State(DATA, rng=random.Random(seed))
    state.spawn_wait = 0.02
    state.weapon_wait["spark_wand"] = 0.02
    return state


def report(label, state, extra=""):
    print(
        f"{label}: t={state.t:.2f}s hp={round(state.hero['hp'])} "
        f"hero=({state.hero['x']:.0f},{state.hero['y']:.0f}) "
        f"enemies={len(state.enemies)} sparks={len(state.sparks)} kills={state.kills} "
        f"over={state.game_over} won={state.won} {extra}"
    )


async def run_case(label, frames, state=None, prepare=None, extra="", screenshot=None):
    saved = {"n": 0}
    if screenshot:
        original_flip = pygame.display.flip
        moment = max(1, frames - 10)

        def flip_and_save():
            saved["n"] += 1
            if saved["n"] == moment:
                pygame.image.save(pygame.display.get_surface(), screenshot)
                print("saved", screenshot)
            original_flip()

        pygame.display.flip = flip_and_save
    pygame.init()
    pygame.display.set_mode(SIZE)
    pygame.event.clear()
    if prepare is not None:
        prepare()
    state = await main.main(max_frames=frames, state=state, data=DATA)
    if screenshot:
        pygame.display.flip = original_flip
    report(label, state, extra)
    return state


async def check():
    pygame.init()
    pygame.display.set_mode(SIZE)

    # 1. mouse: the hero walks toward the pointer and keeps walking
    def move_mouse():
        pygame.mouse.set_pos(340, 640)
        pygame.event.post(
            pygame.event.Event(pygame.MOUSEMOTION, dict(pos=(340, 640), rel=(1, 1), buttons=(0, 0, 0)))
        )

    await run_case("mouse walk", 90, prepare=move_mouse, screenshot="_gameplay.png")

    # 1b. a phone that has not been touched yet: get_pos() is (0,0), the hero must stand still
    await run_case(
        "phone, no touch yet", 60, extra="(hero must stay 0,0)", screenshot="_waiting.png"
    )

    # 2a. finger held down: the hero walks toward the finger
    def touch_down():
        pygame.event.post(finger(pygame.FINGERDOWN, 0.2, 0.2))
        pygame.event.post(finger(pygame.FINGERMOTION, 0.15, 0.25))

    await run_case("finger held", 90, prepare=touch_down)

    # 2b. finger down then lifted in the same frame: the hero must stop
    def touch_down_and_up():
        pygame.event.post(finger(pygame.FINGERDOWN, 0.2, 0.2))
        pygame.event.post(finger(pygame.FINGERUP, 0.2, 0.2))

    lifted = await run_case("finger lifted", 90, prepare=touch_down_and_up)
    print(f"hero after lift: {round(lifted.hero['x'], 1)}, {round(lifted.hero['y'], 1)} (expect 0, 0)")

    # 3. P pauses
    def press_p():
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, dict(key=pygame.K_p, mod=0)))

    paused_state = await run_case("P pressed", 60, prepare=press_p, extra="(t stays 0)")

    # 4. click the end screen to play again
    def click():
        pygame.mouse.set_pos(100, 100)
        pygame.event.post(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, dict(button=1, pos=(100, 100), rel=(0, 0), num_touches=0)
            )
        )

    dead = fresh_state()
    dead.game_over = True
    dead.kills = 5
    restarted = await run_case("click on end screen", 5, state=dead, prepare=click)
    print(f"restart after click: over={restarted.game_over} kills={restarted.kills}")

    # 5. tap the end screen to play again, and a real death in play
    dead2 = fresh_state()
    dead2.game_over = True

    def tap():
        pygame.event.post(finger(pygame.FINGERDOWN, 0.5, 0.5))

    tapped = await run_case("tap on end screen", 5, state=dead2, prepare=tap)
    print(f"restart after tap: over={tapped.game_over} kills={tapped.kills}")

    doomed = rules.State(DATA, rng=random.Random(3))
    doomed.hero["hp"] = DATA["enemies"]["bat"]["damage"]
    doomed.add_enemy("bat", doomed.hero["x"] + 3, doomed.hero["y"] + 3)

    def no_input():
        pygame.mouse.set_pos(SIZE[0] // 2, SIZE[1] // 2)

    await run_case(
        "hero dies",
        30,
        state=doomed,
        prepare=no_input,
        extra="(expect over=True)",
        screenshot="_end.png",
    )

    # 6. level-up: three cards are shown, the world waits, a click picks one
    def quiet(state):
        state.spawn_wait = 1000.0
        state.weapon_wait["spark_wand"] = 1000.0
        return state

    card_state = quiet(rules.State(DATA, rng=random.Random(4)))
    card_state.gems.append({"xp": 2, "x": 30.0, "y": 0.0})
    card_state.xp = rules.xp_needed(card_state) - 2
    shown = await run_case(
        "level up screen", 40, state=card_state, prepare=no_input, screenshot="_levelup.png"
    )
    print(f"cards shown: {[c['name'] for c in shown.cards]} waiting={shown.awaiting_choice}")

    def click_middle_card():
        pygame.mouse.set_pos(195, 350)
        pygame.event.post(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, dict(button=1, pos=(195, 350), rel=(0, 0), num_touches=0)
            )
        )

    picked = await run_case("click a card", 20, state=shown, prepare=click_middle_card)
    print(
        f"after click: waiting={picked.awaiting_choice} level={picked.level} "
        f"weapons={picked.weapons} passives={picked.passives}"
    )

    # 7. blades and holy ring
    armed = quiet(rules.State(DATA, rng=random.Random(6)))
    armed.weapons = {"spin_blades": 2, "holy_ring": 1}
    for angle in range(0, 360, 45):
        armed.add_enemy(
            "bat",
            armed.hero["x"] + math.cos(math.radians(angle)) * 45,
            armed.hero["y"] + math.sin(math.radians(angle)) * 45,
        )
    armed.hero["hp"] = 1000.0
    armed.hero["max_hp"] = 1000.0
    await run_case(
        "blades + ring", 20, state=armed, prepare=no_input, screenshot="_weapons.png"
    )

    # 8. the three normal enemies walk side by side
    crowd = quiet(rules.State(DATA, rng=random.Random(9)))
    crowd.hero["hp"] = crowd.hero["max_hp"] = 1000.0
    crowd.t = 50.0
    for kind, spot in (("bat", (-70, -40)), ("slime", (70, 30)), ("ghost", (0, 90))):
        crowd.add_enemy(kind, *spot)
    kinds = await run_case(
        "three kinds", 30, state=crowd, prepare=no_input, screenshot="_waves.png"
    )
    print("kinds alive:", sorted(e["kind"] for e in kinds.enemies))

    # 9. the boss: one demon, drawn twice as big, never removed
    boss = quiet(rules.State(DATA, rng=random.Random(11)))
    boss.hero["hp"] = boss.hero["max_hp"] = 1000.0
    boss.t = 90.0
    boss = await run_case("boss wave", 40, state=boss, prepare=no_input)
    gap = round(rules.distance(0.0, 0.0, boss.enemies[0]["x"], boss.enemies[0]["y"]))
    print(f"boss alive hp={round(boss.enemies[0]['hp'])} distance={gap}")
    boss.enemies[0]["x"] = boss.enemies[0]["y"] = 5000.0
    boss = await run_case("boss far away", 5, state=boss, prepare=no_input)
    gap = round(rules.distance(0.0, 0.0, boss.enemies[0]["x"], boss.enemies[0]["y"]))
    print(f"boss after running away: alive={len(boss.enemies)} distance={gap} (expect 380)")

    # ... and it is drawn twice as big as the hero
    def put_boss_next_to_the_hero():
        boss.enemies[0]["x"], boss.enemies[0]["y"] = 90.0, 0.0

    await run_case(
        "boss on screen", 6, state=boss, prepare=put_boss_next_to_the_hero, screenshot="_boss.png"
    )

    # 10. reaching 2:00 shows VICTORY
    winner = quiet(rules.State(DATA, rng=random.Random(13)))
    winner.boss_spawned = True
    winner.t = DATA["victory_at"] - 1.0
    won = await run_case(
        "at the goal", 90, state=winner, prepare=no_input, screenshot="_victory.png"
    )
    print(f"victory screen: won={won.won} over={won.game_over} t={won.t:.2f}")

    # 11. sound and feel: damage numbers, death flashes, a shake when the hero is hurt
    print("sounds loaded:", sorted(main.load_sounds(DATA)))
    messy = rules.State(DATA, rng=random.Random(21))
    messy.hero["hp"] = messy.hero["max_hp"] = 1000.0
    messy.spawn_wait = 1000.0
    messy.weapon_wait["spark_wand"] = 0.02
    for angle in range(0, 360, 60):
        messy.add_enemy(
            "bat",
            messy.hero["x"] + math.cos(math.radians(angle)) * 90,
            messy.hero["y"] + math.sin(math.radians(angle)) * 90,
        )
    messy.add_enemy("bat", messy.hero["x"], messy.hero["y"])
    messy = await run_case(
        "combat feel", 45, state=messy, prepare=no_input, screenshot="_combat.png"
    )
    print(
        f"numbers={len(messy.numbers)} flashes={len(messy.flashes)} "
        f"shake={messy.shake:.3f} events_left={messy.events} kills={messy.kills}"
    )

    # 12. one of each effect, caught a few frames later so the picture shows them
    effects = quiet(rules.State(DATA, rng=random.Random(23)))
    feel = DATA["feel"]
    effects.numbers.append({"x": -70.0, "y": -40.0, "text": "22", "life": feel["number_life"]})
    effects.flashes.append({"x": 60.0, "y": 50.0, "life": feel["flash_life"]})
    effects.shake = feel["shake"]
    effects = await run_case(
        "effects", 12, state=effects, prepare=no_input, screenshot="_feel.png"
    )
    print(
        f"after 12 frames: numbers={len(effects.numbers)} flashes={len(effects.flashes)} "
        f"shake={effects.shake:.3f}"
    )


asyncio.run(check())
print("headless check finished")
