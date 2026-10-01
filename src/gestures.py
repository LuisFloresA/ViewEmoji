"""Deteccion de rostro y manos con MediaPipe Tasks API + logica de gestos.

Nota de version: MediaPipe 1.x elimino la API legacy `mp.solutions`, por lo que
usamos `mediapipe.tasks.python.vision` (FaceLandmarker + HandLandmarker), que
ademas es mas rapida. Requiere los ficheros .task en models/.

Si MediaPipe no esta disponible, la app continua con el avatar inactivo.
"""

import math
import time
from typing import Optional

import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    MP_AVAILABLE = True
except Exception:  # pragma: no cover
    mp = None
    MP_AVAILABLE = False

from config import ROOT

FACE_MODEL = ROOT / "models" / "face_landmarker.task"
HAND_MODEL = ROOT / "models" / "hand_landmarker.task"

# Indices de landmarks de FaceMesh (cara con refine/478 puntos)
L_MOUTH_UP, L_MOUTH_DOWN = 13, 14
L_MOUTH_L, L_MOUTH_R = 61, 291
L_EYE_L_OUT, L_EYE_L_IN = 33, 133
L_EYE_R_OUT, L_EYE_R_IN = 263, 362
# Párpados superior/inferior de cada ojo, para medir la apertura (EAR).
L_EYE_L_UP, L_EYE_L_DOWN = 159, 145
L_EYE_R_UP, L_EYE_R_DOWN = 386, 374
L_BROW_L, L_BROW_R = 105, 334
L_CHEEK_L, L_CHEEK_R = 50, 280
L_CHIN = 152
NOSE_TIP = 1
IRIS_L, IRIS_R = 468, 473


def _to_mp_image(frame_rgb: np.ndarray):
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame_rgb))


class Detector:
    def __init__(self, log=print, gaze_w_pos: float = 0.75,
                 gaze_gain_x: float = 9.0, gaze_gain_y: float = 7.0):
        self.log = log
        self.face = None
        self.hands = None
        self._last_ts = 0
        self._prev_face: Optional[tuple] = None
        # Calibracion adaptativa del "mirar al frente" (ver _gaze).
        self.gaze_w_pos = gaze_w_pos
        self.gaze_gain_x = gaze_gain_x
        self.gaze_gain_y = gaze_gain_y
        self._gaze_base: Optional[tuple] = None
        self._gaze_base_k = 0.03
        self._gaze_deadzone = 0.06

        if not MP_AVAILABLE:
            self.log("[mp] mediapipe no disponible: solo avatar inactivo")
            return

        try:
            if not FACE_MODEL.exists():
                self.log(f"[mp] falta {FACE_MODEL.name}; ejecuta scripts/download_models.py")
            else:
                opts = vision.FaceLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=str(FACE_MODEL)),
                    running_mode=vision.RunningMode.VIDEO,
                    num_faces=1,
                    min_face_detection_confidence=0.5,
                    min_face_presence_confidence=0.5,
                    min_tracking_confidence=0.5,
                    output_face_blendshapes=False,
                    output_facial_transformation_matrixes=False,
                )
                self.face = vision.FaceLandmarker.create_from_options(opts)
        except Exception as exc:
            self.log(f"[mp] FaceLandmarker fallo: {exc}")
            self.face = None

        try:
            if not HAND_MODEL.exists():
                self.log(f"[mp] falta {HAND_MODEL.name}; ejecuta scripts/download_models.py")
            else:
                opts = vision.HandLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=str(HAND_MODEL)),
                    running_mode=vision.RunningMode.VIDEO,
                    num_hands=2,
                    min_hand_detection_confidence=0.5,
                    min_hand_presence_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                self.hands = vision.HandLandmarker.create_from_options(opts)
        except Exception as exc:
            self.log(f"[mp] HandLandmarker fallo: {exc}")
            self.hands = None

        if self.face or self.hands:
            self.log(f"[mp] modelos cargados (face={bool(self.face)} hand={bool(self.hands)})")
        else:
            self.log("[mp] sin modelos: el avatar no detectara gestos")

    def close(self):
        for obj in (self.face, self.hands):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _dist(a, b) -> float:
        return math.hypot(a.x - b.x, a.y - b.y)

    def process(self, frame_rgb: np.ndarray, ts_ms: Optional[int] = None) -> dict:
        out = dict(
            face=False, look=(0.0, 0.0), pos=(0.0, 0.0), vel=(0.0, 0.0),
            mouth_open=0.0, tilt=0.0,
            smile=0.0, brow_up=False, brow_down=False, wink=False,
            hands=[], face_lms=None, face_x=0.5, face_y=0.5,
        )
        if ts_ms is None:
            ts_ms = int(time.time() * 1000)
        if ts_ms <= self._last_ts:
            ts_ms = self._last_ts + 1
        self._last_ts = ts_ms

        img = None
        if self.face is not None or self.hands is not None:
            try:
                img = _to_mp_image(frame_rgb)
            except Exception as exc:
                self.log(f"[mp] error creando imagen: {exc}")
                return out

        if self.face is not None and img is not None:
            try:
                res = self.face.detect_for_video(img, ts_ms)
                lms = getattr(res, "face_landmarks", None)
                if lms:
                    lm = lms[0]
                    out["face"] = True
                    out["face_lms"] = [(p.x, p.y) for p in lm]
                    out.update(self._face_metrics(lm))
            except Exception as exc:
                self.log(f"[mp] face error: {exc}")

        if self.hands is not None and img is not None:
            try:
                hres = self.hands.detect_for_video(img, ts_ms)
                hands_lms = getattr(hres, "hand_landmarks", None)
                if hands_lms:
                    out["hands"] = self._hand_metrics(hands_lms)
            except Exception as exc:
                self.log(f"[mp] hand error: {exc}")

        if not out["face"]:
            # Sin rostro no hay referencia: se olvidan los deltas y la
            # postura neutra, para que al volver no salte la mirada.
            self._prev_face = None
            self._reset_gaze_base()

        return out

    # ------------------------------------------------------------- gaze
    def _gaze(self, raw_x: float, raw_y: float) -> tuple:
        """Convierte desplazamientos crudos del iris en gaze -1..1.

        MediaPipe no nos da un "mirar al frente" absoluto: depende de la
        persona, la camara y el encuadre. Por eso se aprende la linea base
        conadaptacion lenta y SOLO dentro de una zona muerta, de forma que
        una desviacion sostenida (mirar fijamente a un lado) no se aprende
        como si fuera la postura neutra.
        """
        if self._gaze_base is None:
            self._gaze_base = (raw_x, raw_y)
            return 0.0, 0.0
        bx, by = self._gaze_base
        dx, dy = raw_x - bx, raw_y - by
        k = self._gaze_base_k
        if abs(dx) < self._gaze_deadzone:
            bx += dx * k
        if abs(dy) < self._gaze_deadzone:
            by += dy * k
        self._gaze_base = (bx, by)
        return (max(-1.0, min(1.0, dx * self.gaze_gain_x)),
                max(-1.0, min(1.0, dy * self.gaze_gain_y)))

    def _reset_gaze_base(self):
        self._gaze_base = None

    # ------------------------------------------------------------- face
    def _face_metrics(self, lm) -> dict:
        face_h = self._dist(lm[NOSE_TIP], lm[L_CHIN]) or 1e-6

        # --- DIRECCION DE LA MIRADA (gaze): donde mira la propia persona.
        # Se mide el desplazamiento del iris respecto al CENTRO de la
        # abertura del ojo (con signo inequivoco), no respecto a una esquina,
        # y se normaliza con el ancho del ojo para no depender de la
        # distancia a la camara.
        eye_l = self._dist(lm[L_EYE_L_OUT], lm[L_EYE_L_IN]) or 1e-6
        eye_r = self._dist(lm[L_EYE_R_OUT], lm[L_EYE_R_IN]) or 1e-6
        try:
            mid_lx = (lm[L_EYE_L_OUT].x + lm[L_EYE_L_IN].x) / 2
            mid_rx = (lm[L_EYE_R_OUT].x + lm[L_EYE_R_IN].x) / 2
            mid_y = (lm[L_EYE_L_OUT].y + lm[L_EYE_L_IN].y
                     + lm[L_EYE_R_OUT].y + lm[L_EYE_R_IN].y) / 4
            raw_x = (((lm[IRIS_L].x - mid_lx) / eye_l)
                     + ((lm[IRIS_R].x - mid_rx) / eye_r)) / 2
            raw_y = ((lm[IRIS_L].y + lm[IRIS_R].y) / 2 - mid_y) / eye_l
        except IndexError:
            raw_x = raw_y = 0.0
        gx, gy = self._gaze(raw_x, raw_y)

        # --- POSICION DE LA CARA en el encuadre: donde esta la persona.
        # El frame viene espejado, asi que x ya esta en coordenadas de
        # pantalla. Se centra la mirada en el rostro con un offset vertical
        # para que el avatar mire a la altura de los ojos y no de la nariz.
        face_cx = (lm[L_CHEEK_L].x + lm[L_CHEEK_R].x) / 2
        face_cy = (lm[L_EYE_L_OUT].y + lm[L_EYE_R_OUT].y) / 2
        pos_x = (face_cx - 0.5) * 2.0
        pos_y = (face_cy - 0.45) * 2.0

        # --- velocidad de la cara (px normalizados por frame), para que el
        # avatar "persiga" un movimiento rapido en vez de quedar por detras.
        vel_x = vel_y = 0.0
        if self._prev_face is not None:
            vel_x = pos_x - self._prev_face[0]
            vel_y = pos_y - self._prev_face[1]
        self._prev_face = (pos_x, pos_y)

        # --- boca abierta
        gap = self._dist(lm[L_MOUTH_UP], lm[L_MOUTH_DOWN])
        mouth_w = self._dist(lm[L_MOUTH_L], lm[L_MOUTH_R]) or 1e-6
        mouth_open = max(0.0, (gap / mouth_w - 0.08) * 6.5)

        # --- sonrisa: esquinas de boca mas arriba que el labio superior
        corners_y = (lm[61].y + lm[291].y) / 2
        smile = ((lm[L_MOUTH_UP].y - corners_y) / (0.22 * face_h)) * 1.7
        smile = max(0.0, min(1.0, smile))

        # --- cejas
        brow_y = (lm[L_BROW_L].y + lm[L_BROW_R].y) / 2
        brow_rel = (lm[L_MOUTH_UP].y - brow_y) / (0.55 * face_h)
        brow_up = brow_rel < -0.02
        brow_down = brow_rel > 0.07

        # --- roll (inclinacion)
        tilt = math.degrees(math.atan2(lm[L_EYE_R_OUT].y - lm[L_EYE_L_OUT].y,
                                       lm[L_EYE_R_OUT].x - lm[L_EYE_L_OUT].x))

        # --- apertura de cada ojo (EAR) para detectar el guino. Un parpadeo
        # cierra LOS DOS ojos; un guino cierra solo uno, asi que la asimetria
        # entre ambos es lo que lo distingue.
        ear_l = (self._dist(lm[L_EYE_L_UP], lm[L_EYE_L_DOWN])
                 / (self._dist(lm[L_EYE_L_OUT], lm[L_EYE_L_IN]) or 1e-6))
        ear_r = (self._dist(lm[L_EYE_R_UP], lm[L_EYE_R_DOWN])
                 / (self._dist(lm[L_EYE_R_OUT], lm[L_EYE_R_IN]) or 1e-6))
        ear_min, ear_max = min(ear_l, ear_r), max(ear_l, ear_r)
        # Asimetria clara + el ojo cerrado no del todo cerrado (si no, seria
        # un parpadeo normal, no un guino).
        wink = (ear_max > 0 and ear_min / ear_max < 0.62 and ear_min < 0.24)

        return dict(look=(gx, gy), pos=(pos_x, pos_y), vel=(vel_x, vel_y),
                    mouth_open=min(1.0, mouth_open), tilt=tilt, smile=smile,
                    brow_up=brow_up, brow_down=brow_down, wink=wink,
                    face_x=lm[NOSE_TIP].x, face_y=lm[NOSE_TIP].y)

    # ------------------------------------------------------------- hands
    def _hand_metrics(self, hands_lms) -> list[dict]:
        out = []
        for lm in hands_lms:
            wrist = lm[0]
            thumb, idx, mid = lm[4], lm[8], lm[12]
            ring, pinky = lm[16], lm[20]

            def up(p, margin=0.055):
                return p.y < wrist.y - margin

            extended = [up(idx), up(mid), up(ring, 0.05), up(pinky, 0.045)]
            n_ext = sum(extended)
            thumb_up = thumb.y < wrist.y - 0.10 and abs(thumb.x - wrist.x) < 0.25

            open_palm = n_ext >= 4 and abs(thumb.x - wrist.x) > 0.14
            victory = extended[0] and extended[1] and not extended[2] and not extended[3]
            fist = n_ext <= 1 and not thumb_up

            xs = [p.x for p in lm]
            ys = [p.y for p in lm]
            out.append(dict(thumb_up=thumb_up, open_palm=open_palm, victory=victory,
                            fist=fist, n_extended=n_ext,
                            x=sum(xs) / len(xs), y=sum(ys) / len(ys)))
        return out


class GestureEngine:
    """Convierte metricas por frame en eventos de gesto, con cooldown."""

    def __init__(self, definitions: list[dict], cfg: dict, log=print):
        self.defs = {d["id"]: d for d in definitions}
        self.cfg = cfg or {}
        self.cooldown = float(self.cfg.get("cooldown_ms", 800)) / 1000.0
        self.min_hold = int(self.cfg.get("min_hold_frames", 3))
        self.enabled = bool(self.cfg.get("enabled", True))
        self.tilt_threshold = float(self.cfg.get("head_tilt_threshold_deg", 15))
        self.nod_needed = int(self.cfg.get("head_nod_min_count", 2))
        self.shake_needed = int(self.cfg.get("head_shake_min_count", 2))
        self.shake_min_interval = float(
            self.cfg.get("head_shake_min_interval_s", 0.28))
        self.rearm_frames = int(self.cfg.get("rearm_frames", 6))
        self.log = log

        self._last: dict[str, float] = {}
        self._hold: dict[str, int] = {}
        self._armed: dict[str, bool] = {}
        self._off: dict[str, int] = {}
        self._nod: list[float] = []
        self._shake: list[float] = []
        self._sway: list[float] = []
        self._prev_y: Optional[float] = None
        self._prev_x: Optional[float] = None
        self._tilt_dir = 0.0
        self._tilt_since = 0.0

    def _ready(self, gid: str) -> bool:
        return (time.time() - self._last.get(gid, 0.0)) >= self.cooldown

    def _fire(self, gid: str, bucket: list):
        g = self.defs.get(gid)
        if g and self._ready(gid):
            bucket.append(g)
            self._last[gid] = time.time()

    def _hold_gate(self, gid: str, active: bool) -> bool:
        """Disparo POR FLANCO: un gesto suena una vez y no repite mientras
        se mantenga la postura. Se rearma tras varios frames en los que la
        postura se deshace, de modo que un alumno quieto no repite el sonido."""
        if not active:
            self._off[gid] = self._off.get(gid, 0) + 1
            if self._off[gid] >= self.rearm_frames:
                self._armed[gid] = True
                self._hold[gid] = 0
            return False
        self._off[gid] = 0
        if not self._armed.get(gid, True):
            return False
        self._hold[gid] = self._hold.get(gid, 0) + 1
        if self._hold[gid] >= self.min_hold:
            self._armed[gid] = False
            return True
        return False

    def update(self, m: dict) -> list[dict]:
        """Devuelve el gesto winner del frame (el de mayor prioridad).

        Solo se devuelve uno: si en el mismo frame se detectan varios gestos
        (boca abierta + cejas arriba, por ejemplo) se queda el mas
        especifico, de modo que la cara muestre siempre algo coherente.
        """
        if not self.enabled:
            return []
        fired: list[dict] = []

        if m.get("face"):
            mo = m["mouth_open"]
            smile = m["smile"]

            # Boca: tres bandas EXCLUYENTES para que no se pisen entre si.
            #   muy abierta        -> shock
            #   abierta y sin boca de sonreir -> tongue_out (el "aaah" tonto)
            #   abierta normal     -> mouth_open
            if mo > 0.85:
                if self._hold_gate("shock", True):
                    self._fire("shock", fired)
            else:
                self._hold_gate("shock", False)

            if 0.70 < mo <= 0.85 and smile < 0.35:
                if self._hold_gate("tongue_out", True):
                    self._fire("tongue_out", fired)
            else:
                self._hold_gate("tongue_out", False)

            if 0.55 < mo <= 0.70:
                if self._hold_gate("mouth_open", True):
                    self._fire("mouth_open", fired)
            else:
                self._hold_gate("mouth_open", False)

            if self._hold_gate("big_smile", smile > 0.75 and mo < 0.4):
                self._fire("big_smile", fired)
            if self._hold_gate("eyebrows_up", m.get("brow_up")):
                self._fire("eyebrows_up", fired)
            if self._hold_gate("frown", m.get("brow_down")):
                self._fire("frown", fired)
            if self._hold_gate("wink", m.get("wink")):
                self._fire("wink", fired)

            # inclinacion sostenida -> head_tilt; cambios de lado -> head_shake_fast
            now = time.time()
            if abs(m["tilt"]) > self.tilt_threshold:
                if self._hold_gate("head_tilt", True):
                    self._fire("head_tilt", fired)
                direction = 1 if m["tilt"] > 0 else -1
                if direction != self._tilt_dir and \
                        (now - self._tilt_since) > self.shake_min_interval:
                    self._tilt_dir = direction
                    self._tilt_since = now
                    self._shake.append(now)
                    if len(self._shake) > 8:
                        self._shake.pop(0)
                    if len(self._shake) >= self.shake_needed:
                        self._fire("head_shake_fast", fired)
                        self._shake.clear()
            else:
                self._hold["head_tilt"] = 0

            # nod: oscilacion vertical del centro de la cara
            if self._prev_y is not None:
                dy = m["face_y"] - self._prev_y
                if abs(dy) > 0.010:
                    self._nod.append(dy)
                    if len(self._nod) > 40:
                        self._nod.pop(0)
                    signs = [1 if v > 0 else -1 for v in self._nod if abs(v) > 0.006]
                    changes = sum(1 for a, b in zip(signs, signs[1:]) if a != b)
                    if changes >= self.nod_needed:
                        self._fire("nod", fired)
                        self._nod.clear()
            self._prev_y = m["face_y"]

            # shake ("no"): oscilacion horizontal. Se exige un recorrido
            # minimo para no confundirlo con mover la cabeza de sitio a sitio.
            if self._prev_x is not None:
                dx = m["face_x"] - self._prev_x
                if abs(dx) > 0.006:
                    self._sway.append(dx)
                    if len(self._sway) > 40:
                        self._sway.pop(0)
                    lo, hi = min(self._sway), max(self._sway)
                    signs = [1 if v > 0 else -1 for v in self._sway
                             if abs(v) > 0.004]
                    changes = sum(1 for a, b in zip(signs, signs[1:]) if a != b)
                    if changes >= self.shake_needed and (hi - lo) > 0.05:
                        self._fire("shake", fired)
                        self._sway.clear()
            self._prev_x = m["face_x"]
        else:
            for k in ("mouth_open", "big_smile", "eyebrows_up", "frown", "head_tilt"):
                self._hold[k] = 0
                self._armed[k] = True
                self._off[k] = 0
            for h in self.defs:
                self._hold[h] = 0
                self._armed[h] = True
                self._off[h] = 0
            self._nod.clear()
            self._shake.clear()
            self._sway.clear()
            self._prev_y = self._prev_x = None

        hands = m.get("hands", [])
        if self._hold_gate("hands_up", len(hands) >= 2):
            self._fire("hands_up", fired)
        for h in hands:
            if self._hold_gate("thumbs_up", h["thumb_up"]):
                self._fire("thumbs_up", fired)
            if self._hold_gate("open_palm", h["open_palm"]):
                self._fire("open_palm", fired)
            if self._hold_gate("victory", h["victory"]):
                self._fire("victory", fired)
            if self._hold_gate("fist", h["fist"]):
                self._fire("fist", fired)

        return self._winner(fired)

    @staticmethod
    def _winner(fired: list[dict]) -> list[dict]:
        """Se queda solo con el gesto de mayor prioridad del frame."""
        if not fired:
            return fired
        best = max(fired, key=lambda g: (g.get("reaction", {}) or {}).get("priority", 0))
        return [best]
