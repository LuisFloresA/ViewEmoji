"""Test de humo del pipeline: renderiza el avatar en PNG sin camara ni pantalla.

Valida que el render 2D, el motor de gestos, el audio con fallback y la
carga de configuracion funcionan, sin depender de hardware.

Uso:  python scripts/smoke_test.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "out"


def test_config():
    from config import load_config, load_gestures
    cfg = load_config()
    g = load_gestures()
    assert cfg["camera"]["fps"] == 30, "config.camera.fps no leido"
    assert len(g) == 16, f"esperaba 16 gestos, hay {len(g)}"
    ids = [d["id"] for d in g]
    assert len(ids) == len(set(ids)), "hay ids de gesto duplicados"
    for d in g:
        assert "reaction" in d and "expression" in d["reaction"], f"{d['id']} sin reaction"
        assert d.get("fallback"), f"{d['id']} sin fallback de audio"
    print(f"[OK] config + {len(g)} gestos validos")
    return cfg, g


def test_audio(gdefs):
    from audio import SoundEngine
    snd = SoundEngine({"audio": {"enabled": True, "volume": 0.5}}, log=lambda *a: None)
    if not snd.enabled:
        print("[AVISO] audio no disponible en este equipo (sin dispositivo de audio)")
        return
    ok = sum(1 for d in gdefs if snd.play(d.get("sound"), d.get("fallback")))
    print(f"[OK] audio: {ok}/{len(gdefs)} sonidos resueltos y reproducidos")
    time.sleep(0.4)


def test_render():
    import pygame
    from avatar import Avatar, EXPRESSIONS as ALL

    pygame.init()
    W, H = 1280, 720
    surf = pygame.Surface((W, H))
    cfg = {"avatar": {"size_ratio": 0.70, "smooth_factor": 1.0,
                      "blink_interval_min": 9999, "blink_interval_max": 9999,
                      "idle_enabled": False}}
    avatar = Avatar(cfg)
    font = pygame.font.SysFont("consolas", 20)
    OUT.mkdir(exist_ok=True)

    failures = []
    for expr in ALL:
        avatar._expr_priority = -1
        if not avatar.set_expression(expr, 60_000, priority=0):
            failures.append(f"{expr}: set_expression rechazado")
            continue
        avatar.set_look(0.7, -0.3)
        avatar.set_mouth_open(0.5)
        surf.fill((6, 8, 16))
        avatar.draw(surf, (W // 2, H // 2), font=font)
        arr = pygame.surfarray.array3d(surf)
        if arr.max() <= 40:
            failures.append(f"{expr}: render casi vacio")
            continue
        pygame.image.save(surf, str(OUT / f"expr_{expr}.png"))

    if failures:
        for f in failures:
            print(f"[FALLO] {f}")
        pygame.quit()
        return False
    print(f"[OK] render: {len(ALL)} expresiones a 1280x720 en out/")
    pygame.quit()
    return True


def test_face_size():
    """La cara debe ocupar el size_ratio de la altura de pantalla."""
    import pygame
    from avatar import Avatar
    import numpy as np

    pygame.init()
    ok = True
    for h, ratio in ((720, 0.70), (1080, 0.70), (1080, 0.85)):
        surf = pygame.Surface((1920, h))
        a = Avatar({"avatar": {"size_ratio": ratio, "idle_enabled": False}})
        surf.fill((0, 0, 0))
        a.draw(surf, (960, h // 2))
        arr = pygame.surfarray.array3d(surf)
        lit = arr.max(axis=2) > 150
        rows = np.nonzero(lit.any(axis=1))[0]
        if len(rows) == 0:
            print(f"[FALLO] {h}p ratio {ratio}: nada dibujado")
            ok = False
            continue
        height_px = rows.max() - rows.min()
        expect = int(h * ratio)
        # la cara dibuja cejas..boca, algo menor que el diametro completo
        if not (0.45 * expect <= height_px <= 1.15 * expect):
            print(f"[FALLO] {h}p ratio {ratio}: alto real {height_px}px, "
                  f"esperado ~{expect}px")
            ok = False
        else:
            print(f"[OK] {h}p ratio {ratio}: {width_px_note(lit)} alto {height_px}px")
    pygame.quit()
    return ok


def width_px_note(lit) -> str:
    import numpy as np
    cols = np.nonzero(lit.any(axis=0))[0]
    return f"ancho {cols.max() - cols.min()}px" if len(cols) else "?"


def test_idle():
    """Sin actividad, el avatar debe ejecutar acciones idle variadas."""
    import pygame
    from avatar import Avatar, IDLE_ACTIONS

    pygame.init()
    surf = pygame.Surface((800, 600))
    a = Avatar({"avatar": {"size_ratio": 0.6, "idle_enabled": True,
                           "idle_min_gap": 0.05, "idle_max_gap": 0.1}})
    seen, exprs = set(), set()
    a._next_idle_at = 0.0
    a._busy_until = 0.0
    for i in range(12000):
        surf.fill((0, 0, 0))
        a.draw(surf, (400, 300))
        if a._idle_idx >= 0:
            seen.add(IDLE_ACTIONS[a._idle_idx]["name"])
            exprs.add(a.expression)
    pygame.quit()
    if len(seen) < 5:
        print(f"[FALLO] solo {len(seen)} acciones idle distintas: {sorted(seen)}")
        return False
    print(f"[OK] idle: {len(seen)} acciones distintas en 12000 frames")
    print(f"     {sorted(seen)}")
    return True


def test_priority():
    """Con varios gestos en el mismo frame debe ganar el mas especifico."""
    from gestures import GestureEngine
    from config import load_gestures

    gdefs = load_gestures()
    base = dict(face=True, look=(0, 0), pos=(0, 0), vel=(0, 0), mouth_open=0.0,
                tilt=0.0, smile=0.0, brow_up=False, brow_down=False,
                hands=[], face_lms=None, face_x=0.5, face_y=0.5)

    # boca muy abierta + cejas arriba: gana shock (90) sobre alert (30)
    eng = GestureEngine(gdefs, {"cooldown_ms": 0, "min_hold_frames": 1},
                        log=lambda *a: None)
    fired = [f["id"] for f in eng.update({**base, "mouth_open": 0.95,
                                          "brow_up": True})]
    if fired != ["shock"]:
        print(f"[FALLO] se esperaba ['shock'], obtuve {fired}")
        return False
    print("[OK] prioridad: shock gana sobre eyebrows_up")

    # cejas arriba + sonrisa: gana big_smile (45) sobre alert (30)
    eng = GestureEngine(gdefs, {"cooldown_ms": 0, "min_hold_frames": 1},
                        log=lambda *a: None)
    fired = [f["id"] for f in eng.update({**base, "brow_up": True, "smile": 0.9})]
    if fired != ["big_smile"]:
        print(f"[FALLO] se esperaba ['big_smile'], obtuve {fired}")
        return False
    print("[OK] prioridad: big_smile gana sobre eyebrows_up")

    # las bandas de boca no se pisan: 0.62 -> mouth_open, 0.78 -> tongue_out
    for mo, expected in ((0.62, "mouth_open"), (0.78, "tongue_out"), (0.95, "shock")):
        eng = GestureEngine(gdefs, {"cooldown_ms": 0, "min_hold_frames": 1},
                            log=lambda *a: None)
        got = [f["id"] for f in eng.update({**base, "mouth_open": mo, "smile": 0.1})]
        if got != [expected]:
            print(f"[FALLO] boca {mo}: esperaba ['{expected}'], obtuve {got}")
            return False
    print("[OK] bandas de boca excluyentes: 0.62/0.78/0.95 -> mouth/tongue/shock")

    # solo cejas arriba -> alert
    eng = GestureEngine(gdefs, {"cooldown_ms": 0, "min_hold_frames": 1},
                        log=lambda *a: None)
    fired = [f["id"] for f in eng.update({**base, "brow_up": True})]
    if fired != ["eyebrows_up"]:
        print(f"[FALLO] se esperaba ['eyebrows_up'], obtuve {fired}")
        return False
    print("[OK] cejas arriba aisladas -> alert")

    # Un gesto cuya expresion se ignora por prioridad NO debe sonar: si la
    # cara no cambia, el sonido tampoco puede corresponderse con ella.
    import pygame
    from avatar import Avatar
    pygame.init()
    a = Avatar({"avatar": {"idle_enabled": False}})
    if not a.set_expression("shock", 4000, priority=90):
        print("[FALLO] no se pudo aplicar la expresion de alta prioridad")
        return False
    if a.set_expression("happy", 1500, priority=30):
        print("[FALLO] una expresion de menor prioridad piso a shock (90)")
        return False
    if a.expression != "shock":
        print(f"[FALLO] la cara cambio a '{a.expression}' pese a menor prioridad")
        return False
    print("[OK] expresion de menor prioridad se rechaza (y no suena)")
    pygame.quit()

    # todos los gestos deben tener expresion valida y prioridad
    from avatar import EXPRESSIONS
    for g in gdefs:
        r = g.get("reaction", {})
        if r.get("expression") not in EXPRESSIONS:
            print(f"[FALLO] {g['id']}: expresion {r.get('expression')!r} no existe")
            return False
    print(f"[OK] los {len(gdefs)} gestos usan expresiones existentes")
    return True


def test_gaze_tracking():
    """La mirada debe moverse cuando la persona se mueve de sitio."""
    import pygame
    from avatar import Avatar

    pygame.init()
    a = Avatar({"avatar": {"smooth_factor": 1.0, "idle_enabled": False,
                           "gaze_w_pos": 0.62, "gaze_w_vel": 2.4,
                           "look_limit": 1.0}})
    a.set_face_target((-0.8, 0.0), (0.0, 0.0), (0.0, 0.0))
    a._update(1 / 60.0)
    left = a.look[0]
    a.set_face_target((0.8, 0.0), (0.0, 0.0), (0.0, 0.0))
    a._update(1 / 60.0)
    right = a.look[0]
    pygame.quit()

    if not (left < -0.4 and right > 0.4):
        print(f"[FALLO] seguimiento: izquierda {left:+.2f}, derecha {right:+.2f} "
              f"(se esperaba <-0.4 y >0.4)")
        return False
    print(f"[OK] seguimiento de cara: izq {left:+.2f} / der {right:+.2f}")

    # la velocidad debe empujar la mirada mas alla de la posicion
    a2 = Avatar({"avatar": {"smooth_factor": 1.0, "idle_enabled": False}})
    a2.set_face_target((0.0, 0.0), (0.0, 0.0), (0.0, 0.0))
    a2._update(1 / 60.0)
    still = a2.look[0]
    a2.set_face_target((0.0, 0.0), (0.2, 0.0), (0.0, 0.0))
    a2._update(1 / 60.0)
    moving = a2.look[0]
    if abs(moving) <= abs(still):
        print(f"[FALLO] la velocidad no aporta: quieto {still:+.3f} vs {moving:+.3f}")
        return False
    print(f"[OK] la velocidad aporta/anticipa: {still:+.3f} -> {moving:+.3f}")
    return True


def test_gesture_engine():
    from gestures import GestureEngine
    from config import load_gestures

    gdefs = load_gestures()

    base = dict(face=True, look=(0, 0), pos=(0, 0), vel=(0, 0), mouth_open=0.0,
                tilt=0.0, smile=0.0, brow_up=False, brow_down=False, wink=False,
                hands=[], face_lms=None, face_x=0.5, face_y=0.5)

    cases = [
        ("mouth_open", {**base, "mouth_open": 0.62}),
        ("shock", {**base, "mouth_open": 0.95}),
        ("tongue_out", {**base, "mouth_open": 0.78, "smile": 0.1}),
        ("big_smile", {**base, "smile": 0.9}),
        ("eyebrows_up", {**base, "brow_up": True}),
        ("frown", {**base, "brow_down": True}),
        ("wink", {**base, "wink": True}),
        ("head_tilt", {**base, "tilt": 22.0}),
        ("thumbs_up", {**base, "hands": [{"thumb_up": True, "open_palm": False,
                                          "victory": False, "fist": False,
                                          "n_extended": 0, "x": .5, "y": .5}]}),
        ("open_palm", {**base, "hands": [{"thumb_up": False, "open_palm": True,
                                          "victory": False, "fist": False,
                                          "n_extended": 5, "x": .5, "y": .5}]}),
        ("victory", {**base, "hands": [{"thumb_up": False, "open_palm": False,
                                        "victory": True, "fist": False,
                                        "n_extended": 2, "x": .5, "y": .5}]}),
        ("fist", {**base, "hands": [{"thumb_up": False, "open_palm": False,
                                     "victory": False, "fist": True,
                                     "n_extended": 0, "x": .5, "y": .5}]}),
        ("hands_up", {**base, "hands": [{"thumb_up": False, "open_palm": False,
                                         "victory": False, "fist": False,
                                         "n_extended": 0, "x": .5, "y": .5}] * 2}),
    ]

    failed = []
    detected = set()
    for expected, metrics in cases:
        # Motor nuevo por caso: el disparo es por flanco y un motor ya usado
        # tendria el gesto desarmado por un caso anterior.
        eng = GestureEngine(gdefs, {"cooldown_ms": 0, "min_hold_frames": 1,
                                    "head_tilt_threshold_deg": 15},
                            log=lambda *a: None)
        fired = [f["id"] for f in eng.update(metrics)]
        detected |= set(fired)
        if expected not in fired:
            failed.append(f"{expected} (disparados: {fired})")
    if failed:
        print("[FALLO] gestos no detectados:")
        for f in failed:
            print(f"   - {f}")
        return False
    print(f"[OK] motor de gestos: {len(cases)}/{len(cases)} disparados")

    # Gestos de movimiento: necesitan una SECUENCIA de frames, no un frame.
    seqs = [
        # (nombre, [metricas por frame...])
        ("nod", [{**base, "face_y": y} for y in
                 (0.50, 0.60, 0.50, 0.60, 0.50, 0.60, 0.50)]),
        ("shake", [{**base, "face_x": x} for x in
                   (0.50, 0.65, 0.40, 0.65, 0.40, 0.65, 0.40)]),
        ("head_shake_fast", [{**base, "tilt": t} for t in
                             (25.0, -25.0, 25.0, -25.0, 25.0, -25.0)]),
    ]
    for expected, seq in seqs:
        eng = GestureEngine(gdefs, {"cooldown_ms": 0, "min_hold_frames": 1,
                                    "head_tilt_threshold_deg": 15,
                                    "head_shake_min_interval_s": 0.0},
                            log=lambda *a: None)
        got = []
        for metrics in seq:
            got += [f["id"] for f in eng.update(metrics)]
        detected |= set(got)
        if expected not in got:
            failed.append(f"{expected} (secuencia, disparados: {got})")
    if failed:
        print("[FALLO] gestos de movimiento no detectados:")
        for f in failed:
            print(f"   - {f}")
        return False
    print(f"[OK] gestos de movimiento: "
          f"{', '.join(e for e, _ in seqs)}")

    # Cobertura: TODO gesto de gestures.yaml debe tener deteccion. Sin esto,
    # un gesto nuevo en la tabla se quedaria sin funcionar en silencio.
    declared = {d["id"] for d in gdefs}
    missing = declared - detected
    if missing:
        print(f"[FALLO] gestos declarados sin ninguna deteccion: {sorted(missing)}")
        return False
    print(f"[OK] cobertura completa: los {len(declared)} gestos de la tabla "
          f"tienen deteccion")

    # rostro ausente no debe disparar nada
    eng = GestureEngine(gdefs, {"cooldown_ms": 0, "min_hold_frames": 1},
                        log=lambda *a: None)
    none = eng.update({**base, "face": False})
    assert not none, f"sin rostro disparo gestos: {none}"
    print("[OK] sin rostro no hay falsos positivos")
    return True


def test_no_repeat():
    """Un gesto mantenido debe sonar UNA vez, no en bucle."""
    from gestures import GestureEngine
    from config import load_gestures

    gdefs = load_gestures()
    eng = GestureEngine(gdefs, {"cooldown_ms": 0, "min_hold_frames": 3,
                                "rearm_frames": 6}, log=lambda *a: None)
    base = dict(face=True, look=(0, 0), pos=(0, 0), vel=(0, 0), mouth_open=0.0,
                tilt=0.0, smile=0.0, brow_up=False, brow_down=False,
                hands=[], face_lms=None, face_x=0.5, face_y=0.5)
    open_mouth = {**base, "mouth_open": 0.62}

    # 60 frames con la boca abierta = debe sonar 1 sola vez
    fired = [f["id"] for _ in range(60) for f in eng.update(open_mouth)]
    n_open = fired.count("mouth_open")
    if n_open != 1:
        print(f"[FALLO] boca abierta mantuvo: {n_open} disparos (se esperaba 1)")
        return False
    print("[OK] gesto mantenido dispara 1 sola vez (60 frames, mouth_open)")

    # lo mismo con la banda de shock
    eng2 = GestureEngine(gdefs, {"cooldown_ms": 0, "min_hold_frames": 3,
                                 "rearm_frames": 6}, log=lambda *a: None)
    wide = {**base, "mouth_open": 0.95}
    fired2 = [f["id"] for _ in range(60) for f in eng2.update(wide)]
    n_shock = fired2.count("shock")
    if n_shock != 1:
        print(f"[FALLO] shock mantuvo: {n_shock} disparos (se esperaba 1)")
        return False
    print("[OK] gesto mantenido dispara 1 sola vez (60 frames, shock)")

    # tras soltarla y volver a ponerla, debe volver a sonar
    for _ in range(10):
        eng.update(base)
    again = [f["id"] for _ in range(10) for f in eng.update(open_mouth)]
    if again.count("mouth_open") != 1:
        print(f"[FALLO] tras rearmar: {again.count('mouth_open')} disparos (se esperaba 1)")
        return False
    print("[OK] gesto rearma tras soltarlo y vuelve a sonar 1 vez")
    return True


def test_fallback_files(gdefs):
    fb = ROOT / "assets" / "sounds_fallback"
    missing = []
    for d in gdefs:
        name = d.get("fallback")
        if not any((fb / f"{name}{ext}").exists() for ext in (".wav", ".ogg")):
            missing.append(name)
    if missing:
        print(f"[FALLO] faltan sonidos fallback: {missing}")
        return False
    print(f"[OK] {len(gdefs)} sonidos fallback presentes")
    return True


def main():
    print("=" * 50)
    print("  SMOKE TEST - Avatar Interactivo")
    print("=" * 50)
    cfg, gdefs = test_config()
    ok = True
    ok &= test_fallback_files(gdefs)
    ok &= test_gesture_engine()
    ok &= test_no_repeat()
    ok &= test_priority()
    ok &= test_gaze_tracking()
    ok &= test_face_size()
    ok &= test_idle()
    ok &= test_render()
    test_audio(gdefs)
    print("=" * 50)
    print("RESULTADO:", "TODO OK" if ok else "HAY FALLOS")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
