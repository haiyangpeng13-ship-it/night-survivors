"""Night Survivors: window, drawing and input. Run with `python main.py`."""

import asyncio
import math

import pygame

import rules

COLOURS = {
    "hero": (94, 214, 138),
    "hero_edge": (38, 120, 74),
    "enemy_edge": (18, 20, 30),
    "spark": (255, 224, 102),
    "gem_1": (70, 150, 255),
    "gem_2": (255, 95, 190),
    "ring": (255, 240, 160),
    "hp_back": (60, 24, 30),
    "hp_bar": (226, 68, 68),
    "victory": (255, 214, 94),
    "xp_back": (24, 32, 60),
    "xp_bar": (70, 150, 255),
    "card": (38, 44, 66),
    "card_edge": (120, 132, 176),
    "number": (255, 255, 255),
    "flash": (255, 245, 200),
    "text": (232, 236, 245),
    "overlay": (12, 14, 22),
}


def camera_top_left(state, width, height):
    return (state.hero["x"] - width / 2.0, state.hero["y"] - height / 2.0)


def to_screen(x, y, camera):
    return (round(x - camera[0]), round(y - camera[1]))


def picture_names(data):
    names = [data["floor"].get("picture"), data["hero"].get("picture")]
    names += [stats.get("picture") for stats in data["enemies"].values()]
    names += [weapon.get("picture") for weapon in data["weapons"].values()]
    names += [gem["picture"] for gem in data["art"]["gems"]]
    return [name for name in names if name]


def load_pictures(data):
    """Pictures made by make_assets.py. If they are missing we draw shapes instead."""
    pictures = {}
    for name in picture_names(data):
        path = f"assets/{name}"
        try:
            pictures[name] = pygame.image.load(path).convert_alpha()
        except (pygame.error, FileNotFoundError):
            print(f"no {path} - run `py -3.13 make_assets.py`. Drawing shapes for now.")
    return pictures


def load_sounds(data):
    """Short sounds made by make_sounds.py. No sound device just means silence."""
    cfg = data["sound"]
    try:
        pygame.mixer.init()
    except pygame.error:
        print("no sound device - playing in silence.")
        return {}
    sounds = {}
    for event, name in cfg["files"].items():
        for extension in cfg["extensions"]:
            path = f"{cfg['directory']}/{name}{extension}"
            try:
                sound = pygame.mixer.Sound(path)
            except (pygame.error, FileNotFoundError):
                continue
            sound.set_volume(cfg["volume"])
            sounds[event] = sound
            break
        else:
            missing = f"{cfg['directory']}/{name}.wav"
            print(f"no {missing} - run `py -3.13 make_sounds.py`. Playing in silence.")
    return sounds


def play_events(state, sounds):
    """One sound per kind of event, however many of them happened this frame."""
    heard = set()
    for event in state.events:
        if event in heard:
            continue
        heard.add(event)
        sound = sounds.get(event)
        if sound:
            sound.play()
    state.events.clear()


def gem_picture(data, pictures, xp):
    for gem in data["art"]["gems"]:
        if gem["xp"] == xp and gem["picture"] in pictures:
            return pictures[gem["picture"]]
    return None


def draw_picture(screen, picture, position):
    screen.blit(picture, picture.get_rect(center=position))


def draw_floor(screen, camera, floor, pictures):
    picture = pictures.get(floor["picture"])
    tile = picture.get_width() if picture else floor["tile"]
    width, height = screen.get_size()
    left = math.floor(camera[0] / tile) * tile
    top = math.floor(camera[1] / tile) * tile
    row = 0
    y = top
    while y - camera[1] < height:
        column = row
        x = left
        while x - camera[0] < width:
            origin = to_screen(x, y, camera)
            if picture:
                screen.blit(picture, origin)
            else:
                colour = floor["colour_a"] if column % 2 == 0 else floor["colour_b"]
                pygame.draw.rect(screen, colour, pygame.Rect(origin, (tile, tile)))
            x += tile
            column += 1
        y += tile
        row += 1


def draw_hero(screen, state, camera, pictures):
    centre = to_screen(state.hero["x"], state.hero["y"], camera)
    picture = pictures.get(state.data["hero"].get("picture"))
    if picture:
        draw_picture(screen, picture, centre)
        return
    radius = state.data["hero"]["hit_radius"]
    pygame.draw.circle(screen, COLOURS["hero_edge"], centre, radius + 2)
    pygame.draw.circle(screen, COLOURS["hero"], centre, radius)


def draw_enemy(screen, enemy, data, camera, pictures):
    stats = data["enemies"][enemy["kind"]]
    centre = to_screen(enemy["x"], enemy["y"], camera)
    scale = stats.get("scale", 1)
    picture = pictures.get(stats.get("picture"))
    if picture:
        if scale != 1:
            size = (picture.get_width() * scale, picture.get_height() * scale)
            picture = pygame.transform.scale(picture, size)
        draw_picture(screen, picture, centre)
        return
    radius = round(stats["radius"] * scale)
    pygame.draw.circle(screen, COLOURS["enemy_edge"], centre, radius + 2)
    pygame.draw.circle(screen, stats["colour"], centre, radius)


def draw_gems(screen, state, camera, pictures):
    for gem in state.gems:
        position = to_screen(gem["x"], gem["y"], camera)
        picture = gem_picture(state.data, pictures, gem["xp"])
        if picture:
            draw_picture(screen, picture, position)
        else:
            colour = COLOURS.get(f"gem_{gem['xp']}", COLOURS["gem_1"])
            pygame.draw.circle(screen, colour, position, 6)


def draw_sparks(screen, state, camera):
    radius = state.data["weapons"]["spark_wand"]["projectile_radius"]
    for spark in state.sparks:
        pygame.draw.circle(
            screen, COLOURS["spark"], to_screen(spark["x"], spark["y"], camera), radius
        )


def draw_blades(screen, state, camera, pictures):
    if "spin_blades" not in state.weapons:
        return
    cfg = state.data["weapons"]["spin_blades"]
    picture = pictures.get(cfg.get("picture"))
    for position in rules.blade_positions(state):
        centre = to_screen(*position, camera)
        if picture:
            out = math.degrees(
                math.atan2(position[1] - state.hero["y"], position[0] - state.hero["x"])
            )
            draw_picture(screen, pygame.transform.rotate(picture, -out - 90), centre)
        else:
            pygame.draw.circle(screen, COLOURS["text"], centre, cfg["blade_radius"])


def draw_ring(screen, state, camera):
    if "holy_ring" not in state.weapons or state.ring_flash <= 0:
        return
    cfg = state.data["weapons"]["holy_ring"]
    radius = rules.weapon_level(state, "holy_ring")["radius"]
    fade = state.ring_flash / cfg["flash"]
    centre = to_screen(state.hero["x"], state.hero["y"], camera)
    pygame.draw.circle(screen, COLOURS["ring"], centre, round(radius * (1.2 - 0.2 * fade)), 3)


def shake_offset(state, data):
    """The whole view jumps a little while the hero is hurting."""
    if state.shake <= 0:
        return (0.0, 0.0)
    feel = data["feel"]
    left = state.shake / feel["shake"]
    angle = state.t * 60.0
    pixels = feel["shake_pixels"] * left
    return (math.cos(angle) * pixels, math.sin(angle) * pixels)


def draw_flashes(screen, state, camera):
    life = state.data["feel"]["flash_life"]
    widest = state.data["feel"]["flash_radius"]
    for flash in state.flashes:
        at = 1.0 - flash["life"] / life
        centre = to_screen(flash["x"], flash["y"], camera)
        pygame.draw.circle(screen, COLOURS["flash"], centre, round(4 + widest * at), 2)


def draw_numbers(screen, state, camera, font):
    life = state.data["feel"]["number_life"]
    for number in state.numbers:
        label = font.render(number["text"], True, COLOURS["number"])
        label.set_alpha(max(0, min(255, round(255 * number["life"] / life))))
        centre = to_screen(number["x"], number["y"], camera)
        screen.blit(label, (centre[0] - label.get_width() // 2, centre[1]))


def draw_centred(screen, font, text, y, colour=None):
    label = font.render(text, True, colour or COLOURS["text"])
    screen.blit(label, ((screen.get_width() - label.get_width()) // 2, y))


def clock_text(seconds):
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def inventory_text(state):
    parts = []
    for kind in state.data["weapons"]:
        if kind in state.weapons:
            parts.append(f"{state.data['weapons'][kind]['name']} {state.weapons[kind]}")
    for kind in state.data["passives"]:
        if kind in state.passives:
            parts.append(f"{state.data['passives'][kind]['name']} {state.passives[kind]}")
    return "  ".join(parts)


def draw_hud(screen, state, font):
    hero = state.hero
    bar = pygame.Rect(12, 12, 150, 14)
    pygame.draw.rect(screen, COLOURS["hp_back"], bar)
    pygame.draw.rect(
        screen,
        COLOURS["hp_bar"],
        (bar.x, bar.y, round(bar.width * max(0.0, hero["hp"] / hero["max_hp"])), bar.height),
    )
    pygame.draw.rect(screen, COLOURS["text"], bar, 1)
    xp_bar = pygame.Rect(12, bar.bottom + 4, 150, 8)
    pygame.draw.rect(screen, COLOURS["xp_back"], xp_bar)
    pygame.draw.rect(
        screen,
        COLOURS["xp_bar"],
        (
            xp_bar.x,
            xp_bar.y,
            round(xp_bar.width * min(1.0, state.xp / rules.xp_needed(state))),
            xp_bar.height,
        ),
    )
    screen.blit(
        font.render(f"Lv {state.level}", True, COLOURS["text"]),
        (xp_bar.right + 8, xp_bar.y - 6),
    )
    screen.blit(font.render(f"HP {round(hero['hp'])}", True, COLOURS["text"]), (12, xp_bar.bottom + 4))
    goal = clock_text(state.data["victory_at"])
    right = screen.get_width() - 12
    lines = (f"{clock_text(state.t)} / {goal}", f"kills {state.kills}")
    for row, line in enumerate(lines):
        label = font.render(line, True, COLOURS["text"])
        screen.blit(label, (right - label.get_width(), 12 + 22 * row))
    screen.blit(
        font.render(inventory_text(state), True, COLOURS["text"]),
        (12, screen.get_height() - 28),
    )


def card_rects(screen, count):
    margin = 30
    gap = 18
    width = screen.get_width() - margin * 2
    height = 140
    top = (screen.get_height() - (height * count + gap * (count - 1))) // 2 + 20
    return [pygame.Rect(margin, top + index * (height + gap), width, height) for index in range(count)]


def draw_level_up(screen, state, fonts, rects):
    font, big_font, small_font = fonts
    cover = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    cover.fill((*COLOURS["overlay"], 210))
    screen.blit(cover, (0, 0))
    draw_centred(screen, big_font, f"LEVEL {state.level}", 60)
    draw_centred(screen, font, "choose one", 106)
    for rect, card in zip(rects, state.cards):
        pygame.draw.rect(screen, COLOURS["card"], rect, border_radius=12)
        pygame.draw.rect(screen, COLOURS["card_edge"], rect, 2, border_radius=12)
        title = f"{card['name']}  Lv {card['level']}" if card["level"] else card["name"]
        screen.blit(font.render(title, True, COLOURS["text"]), (rect.x + 18, rect.y + 26))
        screen.blit(small_font.render(card["text"], True, COLOURS["card_edge"]), (rect.x + 18, rect.y + 62))


def draw_end(screen, state, font, big_font):
    cover = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    cover.fill((*COLOURS["overlay"], 200))
    screen.blit(cover, (0, 0))
    middle = screen.get_height() // 2
    if state.won:
        draw_centred(screen, big_font, "VICTORY", middle - 60, COLOURS["victory"])
    else:
        draw_centred(screen, big_font, "GAME OVER", middle - 60, COLOURS["hp_bar"])
    draw_centred(
        screen,
        font,
        f"{clock_text(state.t)} / {clock_text(state.data['victory_at'])}",
        middle - 10,
    )
    draw_centred(screen, font, f"kills {state.kills}   level {state.level}", middle + 16)
    draw_centred(screen, font, "click or tap to play again", middle + 52)


def world_target(pointer, camera):
    return (pointer[0] + camera[0], pointer[1] + camera[1])


def choose_card(state, rects, pointer):
    if not state.awaiting_choice:
        return
    for index, rect in enumerate(rects):
        if rect.collidepoint(pointer):
            rules.choose(state, index)
            return


async def main(max_frames=None, state=None, data=None):
    pygame.init()
    data = data if data is not None else rules.load_data()
    state = state if state is not None else rules.State(data)
    size = (data["screen"]["width"], data["screen"]["height"])
    screen = pygame.display.set_mode(size)
    pygame.display.set_caption("Night Survivors")
    pictures = load_pictures(data)
    sounds = load_sounds(data)
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 24)
    big_font = pygame.font.Font(None, 52)
    small_font = pygame.font.Font(None, 20)
    fonts = (font, big_font, small_font)
    running = True
    paused = False
    finger = None
    uses_touch = False
    seen_pointer = False
    accumulator = 0.0
    frames = 0

    while running:
        accumulator = min(accumulator + clock.tick(60) / 1000.0, 0.25)
        rects = card_rects(screen, len(state.cards)) if state.awaiting_choice else []
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                paused = not paused
            elif event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION):
                uses_touch = True
                finger = (event.x * size[0], event.y * size[1])
                if state.game_over:
                    state = rules.State(data)
                else:
                    choose_card(state, rects, finger)
            elif event.type == pygame.FINGERUP:
                finger = None
                if state.game_over:
                    state = rules.State(data)
            elif event.type == pygame.MOUSEMOTION:
                seen_pointer = True
            elif event.type == pygame.MOUSEBUTTONDOWN:
                seen_pointer = True
                if state.game_over:
                    state = rules.State(data)
                else:
                    choose_card(state, rects, event.pos)

        camera = camera_top_left(state, *size)
        if uses_touch:
            pointer = finger
        elif seen_pointer:
            pointer = pygame.mouse.get_pos()
        else:
            # a phone says the mouse is at (0,0) before the first touch: wait for real input
            pointer = None
        started = seen_pointer or uses_touch

        if not paused and not state.game_over and not state.awaiting_choice and pointer is not None:
            target = world_target(pointer, camera)
            while accumulator >= state.dt:
                rules.step(state, target)
                accumulator -= state.dt
        else:
            accumulator = 0.0

        play_events(state, sounds)
        jump = shake_offset(state, data)
        view = (camera[0] + jump[0], camera[1] + jump[1])

        draw_floor(screen, view, data["floor"], pictures)
        draw_gems(screen, state, view, pictures)
        for enemy in state.enemies:
            draw_enemy(screen, enemy, data, view, pictures)
        draw_flashes(screen, state, view)
        draw_ring(screen, state, view)
        draw_hero(screen, state, view, pictures)
        draw_blades(screen, state, view, pictures)
        draw_sparks(screen, state, view)
        draw_numbers(screen, state, view, font)
        draw_hud(screen, state, font)
        if paused:
            draw_centred(screen, font, "PAUSED  -  press P", screen.get_height() // 2)
        if not started:
            draw_centred(screen, font, "touch the screen", int(screen.get_height() * 0.68))
            draw_centred(screen, font, "or move the mouse", int(screen.get_height() * 0.68) + 26)
        if state.awaiting_choice:
            draw_level_up(screen, state, fonts, rects)
        if state.game_over:
            draw_end(screen, state, font, big_font)
        pygame.display.flip()

        frames += 1
        if max_frames is not None and frames >= max_frames:
            running = False
        await asyncio.sleep(0)

    pygame.quit()
    return state


if __name__ == "__main__":
    asyncio.run(main())
