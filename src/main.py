"""Avatar Interactivo - punto de entrada.

Ejecuta el avatar en la pantalla secundaria, captura la camara USB, detecta
gestos faciales y de manos, reproduce sonidos y sigue la mirada del usuario.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import cv2
except ImportError:
    print("[fatal] falta opencv. Ejecuta: pip install -r requirements.txt")
    raise SystemExit(1)

try:
    import pygame
except ImportError:
    print("[fatal] falta pygame. Ejecuta: pip install -r requirements.txt")
    raise SystemExit(1)

from audio import SoundEngine
from avatar import Avatar
from camera import list_camera_names, open_camera
from config import load_config, load_gestures
from gestures import Detector, GestureEngine


def open_display(cfg: dict, log=print):
    """Crea la ventana del avatar en la pantalla secundaria."""
    disp = cfg.get("display", {})
    screen_index = int(disp.get("screen_index", 1))
    fullscreen = bool(disp.get("fullscreen", True))

    try:
        from screeninfo import get_monitors
        monitors = get_monitors()
        if not monitors:
            monitors = [None]
        idx = min(screen_index, len(monitors) - 1)
        mon = monitors[idx]
        size = (mon.width, mon.height) if mon else (1920, 1080)
        x, y = (mon.x, mon.y) if mon else (0, 0)
    except Exception as exc:
        log(f"[display] screeninfo fallo ({exc}); usando pantalla 0 1920x1080")
        size, x, y = (1920, 1080), 0, 0

    flags = pygame.FULLSCREEN | pygame.SCALED if fullscreen else pygame.RESIZABLE
    try:
        screen = pygame.display.set_mode(size, flags)
    except Exception:
        log("[display] no se pudo abrir en la pantalla secundaria, usando primaria")
        screen = pygame.display.set_mode(size or (1920, 1080))
    pygame.display.set_caption("Avatar Interactivo")
    log(f"[display] ventana {size[0]}x{size[1]} en ({x},{y}) fullscreen={fullscreen}")
    return screen


def main():
    cfg = load_config()
    debug = cfg.get("debug", {})

    pygame.init()
    pygame.font.init()
    screen = open_display(cfg)
    font = pygame.font.SysFont("consolas", 22)
    small_font = pygame.font.SysFont("consolas", 16)
    clock = pygame.time.Clock()

    cap = open_camera(cfg)
    if cap is None:
        print("[fatal] sin camara disponible")
        # Sin esto el usuario solo ve "sin camara disponible" y no sabe si
        # el problema es que no hay camara, que otro programa la tiene
        # ocupada, o que config.yaml apunta a la equivocada. En el AIO esto
        # es justo el fallo que mas veces toca diagnosticar.
        nombres = list_camera_names()
        if nombres:
            print(f"[fatal] este equipo ve {len(nombres)} camara(s):")
            for i, n in enumerate(nombres):
                print(f"[fatal]   [{i}] {n}")
        else:
            print("[fatal] DirectShow no lista ninguna camara. Se puede "
                  "comprobar si alguna abre aun sin nombre con: "
                  "scripts\\select_camera.py --list")
        print("[fatal] si la correcta esta en la lista pero no se abre, "
              "probablemente otro programa la tenga ocupada.")
        print("[fatal] para elegir camara:  scripts\\select_camera.py")
        # Codigo propio: run.bat lo usa para ofrecer el selector solo
        # cuando el fallo es de camara, no por cualquier otro motivo.
        return 3

    gcfg = cfg.get("gaze", {})
    detector = Detector(
        gaze_gain_x=float(gcfg.get("gain_x", 9.0)),
        gaze_gain_y=float(gcfg.get("gain_y", 7.0)),
    )
    detector._gaze_base_k = float(gcfg.get("base_k", 0.03))
    detector._gaze_deadzone = float(gcfg.get("deadzone", 0.02))
    gestures = load_gestures()
    engine = GestureEngine(gestures, cfg.get("gestures", {}))
    sound = SoundEngine(cfg)
    avatar = Avatar(cfg)

    running = True
    fps_avg = 0.0
    frame_count = 0
    log = print

    while running:
        frame_count += 1
        dt = clock.tick(60) / 1000.0
        fps_avg = fps_avg * 0.92 + (1 / max(dt, 1e-6)) * 0.08

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif ev.key == pygame.K_d:
                    debug["show_camera_preview"] = not debug["show_camera_preview"]
                elif ev.key == pygame.K_s:
                    debug["show_landmarks"] = not debug["show_landmarks"]

        ok, frame = cap.read()
        if not ok or frame is None:
            log("[camara] frame perdido, reintentando")
            time.sleep(0.05)
            continue
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        metrics = detector.process(rgb, ts_ms=int(time.time() * 1000))
        fired = engine.update(metrics)

        # --- avatar: seguir a la persona (posicion + gaze + velocidad)
        if metrics["face"]:
            avatar.set_face_target(metrics["pos"], metrics["vel"], metrics["look"])
            avatar.set_mouth_open(metrics["mouth_open"])
            avatar.mark_activity()
        else:
            avatar.set_face_target((0.0, 0.0), (0.0, 0.0), (0.0, 0.0))
            avatar.set_mouth_open(0.0)

        # --- reacciones
        for g in fired:
            react = g.get("reaction", {}) or {}
            expr = react.get("expression", "neutral")
            # Si una expresion de mayor prioridad ya esta en curso, el gesto no
            # cambia la cara; entonces tampoco suena, para que lo que se ve y
            # lo que se oyen sean siempre lo mismo.
            shown = avatar.set_expression(expr,
                                          int(react.get("duration_ms", 1200)),
                                          int(react.get("priority", 0)))
            if not shown:
                continue
            sound.play(g.get("sound"), g.get("fallback"))
            log(f"[gesto] {g.get('id')} -> {expr}")

        # --- overlay de landmarks (solo si la vista previa esta activa)
        overlay = None
        if debug.get("show_landmarks"):
            overlay = frame.copy()
            h, w = frame.shape[:2]
            for (lx, ly) in metrics.get("face_lms") or []:
                cv2.circle(overlay, (int(lx * w), int(ly * h)), 1, (0, 255, 0), -1)

        # --- render del avatar
        screen.fill((6, 8, 16))
        center = (screen.get_width() // 2, screen.get_height() // 2)
        avatar.draw(screen, center, font=font)

        if debug.get("show_fps"):
            txt = small_font.render(f"FPS {fps_avg:5.1f}  frame {frame_count}", True, (120, 200, 150))
            screen.blit(txt, (12, 10))
        if not metrics["face"]:
            txt = small_font.render("Esperando rostro...", True, (150, 150, 170))
            screen.blit(txt, (center[0] - txt.get_width() // 2, center[1] + 180))
        if debug.get("show_landmarks"):
            info = f"gaze {metrics['look'][0]:+.2f},{metrics['look'][1]:+.2f}  " \
                   f"pos {metrics['pos'][0]:+.2f},{metrics['pos'][1]:+.2f}  " \
                   f"vel {metrics['vel'][0]:+.3f}  " \
                   f"boca {metrics['mouth_open']:.2f}  tilt {metrics['tilt']:+.1f}  " \
                   f"sonrisa {metrics['smile']:.2f}  manos {len(metrics['hands'])}"
            txt = small_font.render(info, True, (140, 170, 210))
            screen.blit(txt, (12, 34))
            txt2 = small_font.render(
                f"expresion {avatar.expression}  idle={avatar.idle_enabled}  S={avatar.size}",
                True, (140, 170, 210))
            screen.blit(txt2, (12, 54))

        if debug.get("show_camera_preview"):
            if overlay is None:
                overlay = frame
            preview = cv2.resize(overlay, (320, 240))
            preview = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
            surf = pygame.surfarray.make_surface(preview.swapaxes(0, 1))
            screen.blit(pygame.transform.flip(surf, True, False), (10, screen.get_height() - 250))

        pygame.display.flip()

    cap.release()
    detector.close()
    pygame.quit()
    log("[app] cerrado correctamente")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
