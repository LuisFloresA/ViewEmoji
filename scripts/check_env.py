"""Comprobación de dependencias y entorno (diagnóstico rápido).

Uso:  python scripts/check_env.py
"""

import importlib
import importlib.metadata
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

REQUIRED = [
    ("cv2", "opencv-python"),
    ("numpy", "numpy"),
    ("pygame", "pygame"),
    ("yaml", "PyYAML"),
    ("screeninfo", "screeninfo"),
    ("mediapipe", "mediapipe"),
]


def main() -> int:
    print(f"Python : {sys.version.split()[0]} ({platform.system()} {platform.machine()})")
    print("-" * 52)
    missing = []
    for mod, pkg in REQUIRED:
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "?")
            print(f"[OK]   {pkg:16s} {ver}")
        except Exception as exc:
            print(f"[FALTA] {pkg:16s} ({type(exc).__name__})")
            missing.append(pkg)

    print("-" * 52)
    # mediapipe arrastra opencv-contrib-python y este proyecto fija
    # opencv-python: las dos distribuciones escriben en el MISMO modulo cv2, asi
    # que la que este de ultima gana. Si gana la 5.x, aqui falla por Smart App
    # Control, asi que conviene avisar en vez de dejar un fallo misterioso.
    try:
        import cv2
        if not cv2.__version__.startswith("4.10"):
            print(f"[AVISO] cv2 es {cv2.__version__}, se espera 4.10.x")
            print("        Reinstala:  pip install --force-reinstall "
                  "--no-deps opencv-python==4.10.0.84")
        else:
            others = [d.metadata["Name"] + " " + d.version for d in
                      importlib.metadata.distributions()
                      if (d.metadata["Name"] or "").startswith("opencv")]
            if len(others) > 1:
                print(f"[AVISO] hay varias distribuciones de OpenCV "
                      f"instaladas: {', '.join(others)}")
                print("        Ambas escriben en cv2; gana la ultima. "
                      "Debe quedar cv2 4.10.")
    except Exception as exc:
        print(f"[opencv] no se pudo comprobar: {exc}")

    try:
        from screeninfo import get_monitors
        for i, m in enumerate(get_monitors()):
            print(f"[monitor {i}] {m.width}x{m.height} @ ({m.x},{m.y}) {m.name}")
    except Exception as exc:
        print(f"[monitor] no se pudieron enumerar: {exc}")

    sys.path.insert(0, str(ROOT / "src"))
    try:
        from camera import classify, list_camera_names, pick_index
        names = list_camera_names()
        if names:
            for i, n in enumerate(names):
                print(f"[camera {i}] {n}  ({classify(n)})")
            chosen = pick_index(names, prefer_usb=True)
            print(f"[camera] seleccion automatica -> indice {chosen} ({names[chosen]!r})")
        else:
            print("[camera] no se detectaron camaras")
    except Exception as exc:
        print(f"[cameras] error: {exc}")

    try:
        from config import load_gestures
        g = load_gestures()
        print(f"[gestos] {len(g)} definidos en config/gestures.yaml")
    except Exception as exc:
        print(f"[gestos] error: {exc}")

    print("-" * 52)
    if missing:
        print("Faltan paquetes. Ejecuta:")
        print("  pip install -r requirements.txt")
        return 1
    print("Todo listo:  python src/main.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
