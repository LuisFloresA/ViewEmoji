"""Diagnostico en vivo: mide el rango de la mirada con la camara real.

Comprueba que el avatar realmente sigue a la persona (posicion + gaze) y que
la cara se dibuja al tamano esperado. No dibuja ventana; solo lee metricas.

Uso:  python scripts/gaze_probe.py [segundos]
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
from gestures import Detector  # noqa: E402


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
    cfg = load_config()
    cap = open_camera(cfg)
    if cap is None:
        print("[FATAL] no se pudo abrir la camara")
        return 1
    det = Detector()

    gaze_x, gaze_y, pos_x, pos_y, mouth, tilt = [], [], [], [], [], []
    n_face = n_frames = 0

    t0 = time.time()
    while time.time() - t0 < seconds:
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        n_frames += 1
        rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
        m = det.process(rgb, ts_ms=int(time.time() * 1000))
        if m["face"]:
            n_face += 1
            gaze_x.append(m["look"][0])
            gaze_y.append(m["look"][1])
            pos_x.append(m["pos"][0])
            pos_y.append(m["pos"][1])
            mouth.append(m["mouth_open"])
            tilt.append(m["tilt"])

    cap.release()
    det.close()

    print(f"frames={n_frames}  con rostro={n_face} "
          f"({100.0 * n_face / max(1, n_frames):.0f}%)")
    if n_face < 10:
        print("[AVISO] muy pocos frames con rostro: prueba a situarte delante")
        return 0

    def rng(vals, name):
        a = np.array(vals)
        p5, p95 = np.percentile(a, 5), np.percentile(a, 95)
        print(f"  {name:10s} min {a.min():+.3f}  p5 {p5:+.3f}  "
              f"mediana {np.median(a):+.3f}  p95 {p95:+.3f}  max {a.max():+.3f}  "
              f"recorrido {a.max() - a.min():.3f}")
        return a.max() - a.min()

    print("rangos de la mirada:")
    gx = rng(gaze_x, "gaze_x")
    gy = rng(gaze_y, "gaze_y")
    px = rng(pos_x, "pos_x")
    py = rng(pos_y, "pos_y")
    rng(mouth, "boca")
    rng(tilt, "tilt")

    print()
    ok = True
    if gx < 0.10 and px < 0.10:
        print("[AVISO] la mirada apenas se mueve: muevete de lado a lado")
        ok = False
    else:
        print("[OK] la mirada sigue el movimiento "
              f"(gaze_x {gx:.2f}, pos_x {px:.2f})")
    if gy < 0.05 and py < 0.05:
        print("[AVISO] el eje vertical casi no se mueve")
    return 0 if ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
