"""Avatar 2D vectorial: cara grande con seguimiento de mirada + animaciones idle.

Todo se dibuja por primitivas de pygame (sin imagenes), asi que escala a
cualquier resolucion. La cara ocupa un porcentaje de la altura de la pantalla
y se recentra automaticamente.

Dos conceptos gobiernan el estado:

* Mirada: mezcla de (a) donde esta la persona en el encuadre y (b) hacia
  donde mira de verdad, mas la velocidad de su movimiento para "perseguirlo".
* Reacciones e idle: los gestos del usuario mandan sobre la cara; cuando no
  hay nadie, un director de idle hace que el emoji tenga vida propia.
"""

import math
import random
import time
from typing import Callable, Optional, Tuple

try:
    import pygame
except ImportError:
    pygame = None


# --------------------------------------------------------------------------
# Expresiones. Cada una define la geometria de ojos, cejas y boca.
#   lid     : 1.0 = ojo abierto, 0.0 = cerrado (pestania)
#   brow    : >0 enfadado / ceja baja, <0 ceja alta (sorpresa)
#   mouth   : tipo de boca (ver _draw_mouth)
#   glow    : intensidad del halo de fondo
#   squint  : 0..1 aprieta los ojos (sonrisa fuerte)
# --------------------------------------------------------------------------
EXPRESSIONS = {
    "neutral":   dict(lid=1.00, brow=0.00,  mouth="smile", pupil=1.00, glow=0.00, squint=0.0),
    "happy":     dict(lid=0.78, brow=-0.18, mouth="grin",  pupil=1.05, glow=0.35, squint=0.45),
    "excited":   dict(lid=0.70, brow=-0.30, mouth="grin",  pupil=1.08, glow=0.50, squint=0.55),
    "surprise":  dict(lid=1.40, brow=-0.60, mouth="open",  pupil=0.75, glow=0.25, squint=0.0),
    "shock":     dict(lid=1.65, brow=-0.80, mouth="shout", pupil=0.50, glow=0.60, squint=0.0),
    "alert":     dict(lid=1.15, brow=-0.45, mouth="small", pupil=1.15, glow=0.20, squint=0.0),
    "wink":      dict(lid=1.00, brow=-0.12, mouth="smirk", pupil=1.00, glow=0.25, squint=0.2),
    "curious":   dict(lid=1.18, brow=-0.32, mouth="small", pupil=1.25, glow=0.18, squint=0.0),
    "grumpy":    dict(lid=0.92, brow=0.62,  mouth="frown",  pupil=0.90, glow=0.00, squint=0.25),
    "affirm":    dict(lid=0.82, brow=-0.08, mouth="smile", pupil=1.00, glow=0.22, squint=0.35),
    "deny":      dict(lid=0.98, brow=0.22,  mouth="wave",   pupil=1.00, glow=0.10, squint=0.0),
    "confused":  dict(lid=1.05, brow=0.40,  mouth="wobble", pupil=1.00, glow=0.12, squint=0.0),
    "silly":     dict(lid=1.05, brow=-0.22, mouth="tongue", pupil=1.05, glow=0.28, squint=0.2),
    "stop":      dict(lid=1.22, brow=0.45,  mouth="o",      pupil=1.00, glow=0.30, squint=0.0),
    "powered":   dict(lid=0.88, brow=0.70,  mouth="grit",   pupil=1.15, glow=0.65, squint=0.3),
    "celebrate": dict(lid=0.62, brow=-0.45, mouth="grin",   pupil=1.00, glow=0.75, squint=0.6),
    # --- expresiones de idle
    "bored":     dict(lid=0.55, brow=0.15,  mouth="flat",   pupil=0.95, glow=0.00, squint=0.0),
    "sleepy":    dict(lid=0.22, brow=0.10,  mouth="small",  pupil=0.90, glow=0.00, squint=0.0),
    "dizzy":     dict(lid=0.95, brow=0.05,  mouth="wobble", pupil=1.00, glow=0.20, squint=0.0),
    "talk":      dict(lid=0.95, brow=-0.10, mouth="talk",   pupil=1.02, glow=0.10, squint=0.0),
    "ponder":    dict(lid=0.90, brow=-0.25, mouth="small",  pupil=1.10, glow=0.12, squint=0.0),
}


# --------------------------------------------------------------------------
# Animaciones de idle: lo que hace el emoji cuando no hay nadie.
# Cada accion define duracion, expresion, y un effect(p, t) que devuelve
# (dx, dy, escala, rotacion_grados, override_mirada|None).
#   p = progreso 0..1 de la animacion, t = tiempo en segundos.
# --------------------------------------------------------------------------
def _swipe(freq: float, phase: float = 0.0):
    def f(p, t):
        return math.sin(t * freq + phase)
    return f


IDLE_ACTIONS = [
    dict(name="look_around", dur=4.0, expr="curious", idle_gap=6.0,
         look_fn=lambda p, t: (math.sin(t * 1.5) * 0.95, math.sin(t * 0.9) * 0.35)),
    dict(name="think", dur=3.2, expr="ponder", idle_gap=9.0,
         look_fn=lambda p, t: (0.55, -0.75)),
    dict(name="sway", dur=4.5, expr="neutral", idle_gap=7.0,
         effect=lambda p, t: (math.sin(t * 0.8) * 0.030, 0, 1.0, math.sin(t * 0.8) * 2.6)),
    dict(name="dance", dur=3.6, expr="celebrate", idle_gap=14.0,
         effect=lambda p, t: (math.sin(t * 4.0) * 0.035, abs(math.sin(t * 4.0)) * 0.045 - 0.02,
                              1.0 + math.sin(t * 8.0) * 0.02, math.sin(t * 2.0) * 5.0),
         look_fn=lambda p, t: (math.sin(t * 2.0) * 0.5, 0)),
    dict(name="sleepy", dur=5.5, expr="sleepy", idle_gap=18.0,
         effect=lambda p, t: (0, 0.022, 1.0, 0)),
    dict(name="dizzy", dur=2.6, expr="dizzy", idle_gap=22.0,
         look_fn=lambda p, t: (math.cos(t * 6.0) * 0.95, math.sin(t * 6.0) * 0.6)),
    dict(name="bored", dur=4.5, expr="bored", idle_gap=16.0,
         effect=lambda p, t: (math.sin(t * 0.5) * 0.018, 0.012, 0.99, math.sin(t * 0.5) * 1.4),
         look_fn=lambda p, t: (0.75, 0.45)),
    dict(name="zoom_peek", dur=2.4, expr="alert", idle_gap=20.0,
         effect=lambda p, t: (0, 0, 1.0 + 0.10 * math.sin(p * math.pi), 0),
         look_fn=lambda p, t: (0.0, 0.0)),
    dict(name="spooked", dur=1.3, expr="surprise", idle_gap=26.0,
         effect=lambda p, t: (0, 0.06 * math.sin(p * math.pi), 1.0 - 0.07 * math.sin(p * math.pi), 0)),
    dict(name="chat", dur=3.8, expr="talk", idle_gap=11.0,
         look_fn=lambda p, t: (math.sin(t * 1.2) * 0.4, math.sin(t * 2.4) * 0.2)),
    dict(name="stretch", dur=3.2, expr="happy", idle_gap=15.0,
         effect=lambda p, t: (0, -0.030 * math.sin(p * math.pi),
                              1.0 + 0.06 * math.sin(p * math.pi), 0)),
    dict(name="head_nod_alone", dur=2.6, expr="affirm", idle_gap=13.0,
         effect=lambda p, t: (0, math.sin(t * 3.4) * 0.016, 1.0, 0)),
    dict(name="look_down_up", dur=3.4, expr="curious", idle_gap=12.0,
         look_fn=lambda p, t: (0.2, 0.9 if math.sin(p * math.pi) < 0.5 else -0.4)),
    dict(name="bounce", dur=2.2, expr="excited", idle_gap=17.0,
         effect=lambda p, t: (0, -0.040 * abs(math.sin(t * 5.0)), 1.0, 0)),
]


class Avatar:
    def __init__(self, cfg: dict):
        acfg = cfg.get("avatar", {}) or {}
        # Proporcion de la altura de pantalla que ocupa la cara.
        self.size_ratio = float(acfg.get("size_ratio", 0.70))
        # Tamano absoluto si se quiere fijar; tiene prioridad sobre el ratio.
        self.size_abs = acfg.get("size")
        self.smooth = float(acfg.get("smooth_factor", 0.22))
        self.look_limit = float(acfg.get("look_limit", 1.0))
        # Cuanto pesa la posicion de la persona frente a su direccion de gaze.
        self.gaze_w_pos = float(acfg.get("gaze_w_pos", 0.62))
        # Ganancia sobre la velocidad: el avatar "persigue" el movimiento.
        self.gaze_w_vel = float(acfg.get("gaze_w_vel", 2.4))

        blink_min = float(acfg.get("blink_interval_min", 1.8))
        blink_max = float(acfg.get("blink_interval_max", 4.2))
        self._blink_min, self._blink_max = blink_min, blink_max

        # idle
        self.idle_enabled = bool(acfg.get("idle_enabled", True))
        self.idle_min_gap = float(acfg.get("idle_min_gap", 5.0))
        self.idle_max_gap = float(acfg.get("idle_max_gap", 12.0))

        # --- estado de la cara
        self.expression = "neutral"
        self.expr_until = 0.0
        self._expr_priority = 0
        self._expr_from_idle = False

        self.look = [0.0, 0.0]        # [-1..1] suavizado
        self._look_target = [0.0, 0.0]
        self.blink = 0.0
        self._next_blink = time.time() + random.uniform(blink_min, blink_max)
        self.mouth_live = 0.0         # apertura de boca real de la persona
        self._t = 0.0
        self._last_dt = 1 / 60.0

        # --- transform de animacion (dx, dy, escala, rot)
        self._fx = (0.0, 0.0, 1.0, 0.0)
        # --- override de mirada por animacion idle
        self._idle_look: Optional[Callable] = None

        # --- director de idle
        self._idle_idx = -1
        self._idle_t = 0.0
        self._idle_dur = 0.0
        self._next_idle_at = time.time() + random.uniform(self.idle_min_gap,
                                                          self.idle_max_gap)
        self._busy_until = 0.0
        self._recent: list[str] = []

    # ------------------------------------------------------------ estado
    def set_expression(self, name: str, duration_ms: int = 1200,
                       priority: int = 0) -> bool:
        """Aplica una expresion respetando prioridades.

        Devuelve False si la peticion se ignora porque ya hay una expresion de
        mayor o igual prioridad en curso. Asi un gesto menor no pisa a uno
        mayor que acaba de dispararse.
        """
        if name not in EXPRESSIONS:
            return False
        now = time.time()
        if self._expr_priority >= priority and self.expr_until > now:
            return False
        self.expression = name
        self.expr_until = now + max(0.15, duration_ms / 1000.0)
        self._expr_priority = priority
        self._expr_from_idle = False
        self._busy_until = self.expr_until
        return True

    def start_idle(self, expr: str, dur: float, priority: int = 0):
        self.expression = expr
        self.expr_until = time.time() + dur
        self._expr_priority = priority
        self._expr_from_idle = True

    def set_look(self, x: float, y: float):
        lim = self.look_limit
        self._look_target[0] = max(-lim, min(lim, x))
        self._look_target[1] = max(-lim, min(lim, y))

    def set_face_target(self, pos: Tuple[float, float], vel: Tuple[float, float],
                        gaze: Tuple[float, float]):
        """Combina donde esta la persona, hacia donde mira y su velocidad.

        pos  : posicion de la cara en el encuadre, -1..1
        vel  : desplazamiento del ultimo frame, para anticipar el movimiento
        gaze : direccion de la mirada real de la persona, -1..1
        """
        w_pos = self.gaze_w_pos
        w_vel = self.gaze_w_vel
        tx = (pos[0] * w_pos + gaze[0] * (1.0 - w_pos)
              + max(-0.6, min(0.6, vel[0] * w_vel)))
        ty = (pos[1] * w_pos + gaze[1] * (1.0 - w_pos)
              + max(-0.6, min(0.6, vel[1] * w_vel)))
        self.set_look(tx, ty)

    def set_mouth_open(self, amount: float):
        self.mouth_live = max(0.0, min(1.0, amount))

    def mark_activity(self):
        """Reinicia el reloj de idle porque ha habido actividad humana."""
        self._busy_until = time.time() + 1.5
        if self._expr_from_idle:
            # La actividad real gana a la animacion de idle.
            self.expression = "neutral"
            self.expr_until = 0.0
            self._expr_from_idle = False
            self._expr_priority = -1

    def suppress_mouth_mirror(self, on: bool):
        """Si esta activo, la boca real del usuario no pisa la de la expresion."""
        self._expr_priority = max(self._expr_priority, 1) if on else self._expr_priority

    @property
    def mouth_mirror(self) -> float:
        """1.0 si la boca real del usuario debe reflejarse en el avatar.

        Durante una reaccion de gesto manda la forma de la expresion (si no,
        una boca abierta real deformaria la 'feliz' o el 'enfadado'). En idle o
        en reposo la boca real si se refleja.
        """
        return 0.0 if self._expr_priority > 0 else 1.0

    # ------------------------------------------------------------- update
    @property
    def style(self) -> dict:
        return EXPRESSIONS.get(self.expression, EXPRESSIONS["neutral"])

    @property
    def size(self) -> int:
        """Tamano en px segun la ultima superficie dibujada."""
        if self.size_abs:
            return int(self.size_abs)
        if getattr(self, "_last_screen_h", 0):
            return int(self._last_screen_h * self.size_ratio)
        return int(640 * self.size_ratio)

    def _update(self, dt: float):
        now = time.time()
        self._t += dt
        self._last_dt = dt

        if self.expr_until and now > self.expr_until:
            self.expression = "neutral"
            self.expr_until = 0.0
            self._expr_priority = 0
            self._expr_from_idle = False

        # --- animacion idle en curso
        if self._idle_idx >= 0:
            self._idle_t += dt
            if self._idle_t >= self._idle_dur:
                self._idle_idx = -1
                self._fx = (0.0, 0.0, 1.0, 0.0)
                self._idle_look = None
        if self._idle_idx >= 0:
            act = IDLE_ACTIONS[self._idle_idx]
            p = min(1.0, self._idle_t / max(0.01, self._idle_dur))
            fx = act.get("effect")
            if fx:
                dx, dy, sc, rot = fx(p, self._idle_t)
                self._fx = (dx, dy, sc, rot)
            lk = act.get("look_fn")
            self._idle_look = lk

        # --- seamless: entra en idle si lleva demasiado tiempo sin humanos
        if self.idle_enabled and self._idle_idx < 0 and now >= self._next_idle_at \
                and now >= self._busy_until:
            self._pick_idle(now)

        # --- parpadeo
        if now > self._next_blink:
            self.blink = 1.0
            self._next_blink = now + random.uniform(self._blink_min, self._blink_max)
        if self.blink > 0:
            self.blink = max(0.0, self.blink - dt * 7.0)

        # --- mirada: la animacion idle tiene prioridad sobre el seguimiento
        if self._idle_look is not None:
            p = min(1.0, self._idle_t / max(0.01, self._idle_dur))
            target = self._idle_look(p, self._t)
        else:
            target = self._look_target
        k = 1.0 - (1.0 - self.smooth) ** max(0.1, dt * 60.0)
        for i in (0, 1):
            self.look[i] += (target[i] - self.look[i]) * k

        # --- boca: la real se refleja salvo que mande una expresion de gesto
        if self.expression == "talk":
            pass  # la boca "talk" se anima sola en _draw_mouth

    def _pick_idle(self, now: float):
        # Evita repetir la misma accion dos veces seguidas.
        pool = [i for i, a in enumerate(IDLE_ACTIONS)
                if a["name"] not in self._recent[-3:]]
        idx = random.choice(pool)
        act = IDLE_ACTIONS[idx]
        self._idle_idx = idx
        self._idle_t = 0.0
        self._idle_dur = act["dur"]
        self._recent.append(act["name"])
        self.start_idle(act["expr"], act["dur"], priority=0)
        gap = random.uniform(self.idle_min_gap, self.idle_max_gap)
        self._next_idle_at = now + act["dur"] + gap

    # ------------------------------------------------------------- dibujo
    def draw(self, surface, center: Tuple[int, int], font=None):
        if pygame is None or surface is None:
            return
        self._update(self._last_dt)
        w, h = surface.get_size()
        self._last_screen_h = h
        S = self.size
        st = self.style
        cx, cy = center
        t = self._t

        # transform aplicado por las animaciones
        dx, dy, scale, rot_deg = self._fx
        rot = math.radians(rot_deg)
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        eff = S * scale

        def P(fx, fy):
            """Punto del espacio-cara (unidades de S) a pantalla."""
            x = fx * eff
            y = fy * eff
            rx = x * cos_r - y * sin_r
            ry = x * sin_r + y * cos_r
            return (int(cx + rx + dx * eff), int(cy + ry + dy * eff))

        def L(v):
            return v * eff

        self._draw_background(surface, cx, cy, eff, st["glow"])
        self._draw_face(surface, P, L, st, rot)

        eye_dx, eye_y = 0.235, -0.105
        eye_w, eye_h = 0.205, 0.145
        self._draw_brows(surface, P, L, st, eye_dx, eye_y, eye_w, eye_h)
        self._draw_eyes(surface, P, L, st, eye_dx, eye_y, eye_w, eye_h, rot, t)
        self._draw_mouth(surface, P, L, st, t)

        if font is not None:
            label = self.expression.upper()
            if self._expr_from_idle:
                label = label + "  (idle)"
            txt = font.render(label, True, (140, 160, 200))
            surface.blit(txt, (cx - txt.get_width() // 2, cy + int(L(0.47))))

    def _draw_background(self, surface, cx, cy, S, glow):
        w, h = surface.get_size()
        bg = pygame.Surface((w, h))
        for i in range(30, 0, -1):
            shade = int(6 + (30 - i) * 1.0)
            pygame.draw.circle(bg, (shade, shade + 2, shade + 9), (cx, cy), int(S * 0.06 * i))
        surface.blit(bg, (0, 0))
        if glow > 0:
            halo = pygame.Surface((w, h), pygame.SRCALPHA)
            for i in range(7, 0, -1):
                a = int(30 * glow * (i / 7))
                pygame.draw.circle(halo, (110, 190, 255, a), (cx, cy), int(S * 0.78 * i / 7))
            surface.blit(halo, (0, 0))

    def _draw_face(self, surface, P, L, st, rot):
        r = int(L(0.44))
        face = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(face, (28, 32, 56, 205), (r, r), r)
        pygame.draw.circle(face, (78, 98, 152, 235), (r, r), r, max(2, int(L(0.012))))
        fx, fy = P(0.0, 0.0)
        blob = pygame.transform.rotate(face, -math.degrees(rot)) if rot else face
        surface.blit(blob, (fx - r, fy - r))

    def _draw_brows(self, surface, P, L, st, eye_dx, eye_y, eye_w, eye_h):
        brow = st["brow"]
        if abs(brow) < 0.03:
            return
        thick = max(3, int(L(0.030)))
        for sign in (-1, 1):
            ex, ey = P(sign * eye_dx, eye_y - 0.145)
            half = int(L(eye_w * 0.60))
            tilt = int(brow * L(0.075))
            pygame.draw.line(surface, (245, 247, 255), (ex - half, ey + tilt),
                             (ex + half, ey - tilt), thick)

    def _draw_eyes(self, surface, P, L, st, eye_dx, eye_y, eye_w, eye_h,
                   rot, t):
        lid = st["lid"]
        squint = st["squint"]
        base_h = eye_h * max(0.12, lid) * (1.0 - squint * 0.35)
        w_px = L(eye_w)
        h_px = L(base_h)

        for sign in (-1, 1):
            ex, ey = P(sign * eye_dx, eye_y)
            is_wink = self.expression == "wink" and sign == -1
            # bajo parpadeo se cierra progresivamente
            close_amt = 1.0 if is_wink else (min(1.0, self.blink / 0.45) if self.blink > 0 else 0.0)
            hh = h_px * (1.0 - close_amt * 0.92)
            if hh < L(0.018):
                pygame.draw.line(surface, (245, 247, 255),
                                 (ex - w_px // 2, ey), (ex + w_px // 2, ey),
                                 max(3, int(L(0.030))))
                continue

            white = pygame.Surface((max(2, int(w_px)), max(2, int(h_px))), pygame.SRCALPHA)
            pygame.draw.ellipse(white, (245, 247, 255, 255),
                                (0, 0, white.get_width() - 1, white.get_height() - 1))
            if rot:
                white = pygame.transform.rotate(white, -math.degrees(rot))
            surface.blit(white, (ex - white.get_width() // 2, ey - white.get_height() // 2))

            # pupila: recorre buena parte del ojo para que se vea el seguimiento
            if close_amt < 0.7:
                pr = int(min(w_px, h_px) * 0.40)
                px = ex + self.look[0] * w_px * 0.30
                py = ey + self.look[1] * h_px * 0.34
                pygame.draw.circle(surface, (16, 18, 32), (int(px), int(py)), pr)
                pygame.draw.circle(surface, (120, 205, 255),
                                   (int(px - pr * 0.32), int(py - pr * 0.34)),
                                   max(2, int(pr * 0.34)))

    def _draw_mouth(self, surface, P, L, st, t):
        kind = st["mouth"]
        cx, my = P(0.0, 0.205)
        mw = L(0.30)
        live = self.mouth_live * self.mouth_mirror
        thick = max(4, int(L(0.032)))
        white = (245, 247, 255)
        dark = (16, 18, 32)

        if kind in ("open", "shout", "o", "talk"):
            if kind == "talk":
                amp = 0.5 + 0.5 * math.sin(t * 9.0)
                h = L(0.055 + 0.075 * amp)
            else:
                cap = 0.20 if kind != "shout" else 0.28
                h = L(cap * max(0.22, live))
                if kind == "o":
                    h = max(h, L(0.12))
            w = mw * (0.62 if kind != "o" else 0.72)
            rect = pygame.Rect(int(cx - w / 2), int(my - h / 2), max(2, int(w)), max(2, int(h)))
            pygame.draw.ellipse(surface, dark, rect)
            pygame.draw.ellipse(surface, white, rect, max(2, int(L(0.014))))
        elif kind in ("grin", "smile", "smirk"):
            depth = L(0.115 if kind == "grin" else 0.075)
            depth = max(depth, depth * (0.5 + live))
            box = pygame.Rect(int(cx - mw / 2), int(my - depth), int(mw), int(depth * 2))
            pygame.draw.arc(surface, white, box, 0.18, math.pi - 0.18, thick)
            if kind == "grin":
                pygame.draw.arc(surface, white, box, 0.30, math.pi - 0.30, thick)
        elif kind == "frown":
            box = pygame.Rect(int(cx - mw / 2), int(my - L(0.05)), int(mw), int(L(0.17)))
            pygame.draw.arc(surface, white, box, math.pi + 0.22, 2 * math.pi - 0.22, thick)
        elif kind == "flat":
            pygame.draw.line(surface, white, (cx - mw // 2, my), (cx + mw // 2, my), thick)
        elif kind == "tongue":
            box = pygame.Rect(int(cx - mw / 2), int(my - L(0.07)), int(mw), int(L(0.14)))
            pygame.draw.arc(surface, white, box, 0.18, math.pi - 0.18, thick)
            pygame.draw.ellipse(surface, (238, 118, 148),
                                (int(cx - mw * 0.16), int(my - L(0.01)),
                                 int(mw * 0.32), int(L(0.085))))
        elif kind == "grit":
            box = pygame.Rect(int(cx - mw / 2), int(my - L(0.035)), int(mw), int(L(0.075)))
            pygame.draw.rect(surface, white, box, max(2, int(L(0.022))))
            for i in range(1, 5):
                x = box.left + box.width * i // 5
                pygame.draw.line(surface, dark, (x, box.top), (x, box.bottom), 2)
        elif kind == "wobble":
            amp = L(0.022)
            pts = [(cx - mw / 2 + mw * i / 20,
                    my + math.sin(t * 8 + i * 0.55) * amp) for i in range(21)]
            pygame.draw.lines(surface, white, False, [(int(a), int(b)) for a, b in pts], thick)
        elif kind == "wave":
            pts = [(cx - mw / 2 + mw * i / 20,
                    my + math.sin(i * 0.85 + t * 2.6) * L(0.024)) for i in range(21)]
            pygame.draw.lines(surface, white, False, [(int(a), int(b)) for a, b in pts], thick)
        else:  # small
            box = pygame.Rect(int(cx - mw * 0.22), int(my - L(0.045)), int(mw * 0.44), int(L(0.09)))
            pygame.draw.ellipse(surface, white, box, max(2, int(L(0.014))))
