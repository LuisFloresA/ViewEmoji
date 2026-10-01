"""Calibra la normalizacion del iris para la direccion de la mirada.

Compara varias formulas sobre los landmarks crudos de MediaPipe y muestra
cual queda centrada (mediana ~0) cuando la persona mira al frente. Una gaze
sesgada deja los ojos del avatar clavados a un lado.

Uso:  python scripts/calibrate_gaze.py [segundos]
"""

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402

from camera import open_camera  # noqa: E402
from config import load_config  # noqa: E402
from gestures import FACE_MODEL, _to_mp_image  # noqa: E402
from mediapipe.tasks import python as mp_python  # noqa: E402
from mediapipe.tasks.python import vision  # noqa: E402

L_OUT, L_IN = 33, 133
R_OUT, R_IN = 362, 263
IRIS_L, IRIS_R = 468, 473


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    cfg = load_config()
    cap = open_camera(cfg)
    if cap is None:
        return 1

    opts = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(FACE_MODEL)),
        running_mode=vision.RunningMode.VIDEO, num_faces=1,
        min_face_detection_confidence=0.5, min_tracking_confidence=0.5,
    )
    lm_det = vision.FaceLandmarker.create_from_options(opts)

    raw = []
    t0, ts = time.time(), 0
    while time.time() - t0 < seconds:
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        ts = max(ts + 1, int(time.time() * 1000))
        rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
        res = lm_det.detect_for_video(_to_mp_image(rgb), ts)
        lms = getattr(res, "face_landmarks", None)
        if not lms:
            continue
        lm = lms[0]
        raw.append((
            (lm[IRIS_L].x - lm[L_OUT].x) / ((lm[L_IN].x - lm[L_OUT].x) or 1e-6),
            (lm[IRIS_R].x - lm[R_OUT].x) / ((lm[R_IN].x - lm[R_OUT].x) or 1e-6),
            lm[IRIS_L].y, lm[IRIS_R].y, lm[L_OUT].y, lm[L_IN].y,
            lm[R_OUT].y, lm[R_IN].y, lm[1].y, lm[152].y,
            lm[L_OUT].x, lm[R_OUT].x,
        ))

    cap.release()
    lm_det.close()
    if len(raw) < 10:
        print(f"[AVISO] solo {len(raw)} frames con rostro")
        return 0

    a = np.array(raw)
    print(f"frames con rostro: {len(a)}")
    print()
    print("formulas de gaze horizontal (mediana ideal ~0.50, rango 0..1):")
    f1 = (a[:, 0] + a[:, 1]) / 2                                    # absoluta
    f2 = (a[:, 0] - a[:, 1]) / 2                                    # diferencial
    for name, v in (("(irisL+irisR)/2", f1), ("(irisL-irisR)/2", f2)):
        print(f"  {name:22s} med {np.median(v):+.3f}  "
              f"[{v.min():+.3f}, {v.max():+.3f}]  recorrido {v.max() - v.min():.3f}")

    # vertical: linea de ojos relativa a la altura de la cara
    face_h = np.abs(a[:, 9] - a[:, 8]) + 1e-6
    eye_y = (a[:, 4] + a[:, 5] + a[:, 6] + a[:, 7]) / 4
    eye_line = (a[:, 4] + a[:, 5]) / 2
    rel = (eye_line - a[:, 8]) / face_h
    rel2 = (eye_y - a[:, 8]) / face_h
    print()
    print("formulas de gaze vertical:")
    print(f"  (linea_ojos-nariz)/h  med {np.median(rel):+.3f}  "
          f"[{rel.min():+.3f}, {rel.max():+.3f}]  recorrido {rel.max() - rel.min():.3f}")
    print(f"  (ojos4-nariz)/h       med {np.median(rel2):+.3f}  "
          f"[{rel2.min():+.3f}, {rel2.max():+.3f}]  recorrido {rel2.max() - rel2.min():.3f}")
    print()
    print(f"  ancho de cara (L_OUT..R_OUT) med {np.median(a[:, 10] - a[:, 11]):+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
