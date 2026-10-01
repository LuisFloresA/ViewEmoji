"""Descarga los modelos .task de MediaPipe (FaceLandmarker + HandLandmarker).

Uso:
    python scripts/download_models.py
"""

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "models"

BASE = "https://storage.googleapis.com/mediapipe-models"
MODELS = {
    "face_landmarker.task":
        f"{BASE}/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    "hand_landmarker.task":
        f"{BASE}/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
}


def download(name: str, url: str, force: bool = False) -> bool:
    dest = OUT / name
    if dest.exists() and dest.stat().st_size > 100_000 and not force:
        print(f"[model] {name} ya existe ({dest.stat().st_size:,} bytes)")
        return True
    print(f"[model] descargando {name} ...")
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=180) as r, open(tmp, "wb") as fh:
            total = int(r.headers.get("Content-Length", 0))
            got = 0
            while chunk := r.read(262144):
                fh.write(chunk)
                got += len(chunk)
                if total:
                    pct = got * 100 // total
                    print(f"\r[model]   {pct:3d}%  {got:,}/{total:,}", end="", flush=True)
        print()
        tmp.replace(dest)
        print(f"[model] {name} descargado ({dest.stat().st_size:,} bytes)")
        return True
    except Exception as exc:
        print(f"[model] ERROR descargando {name}: {exc}")
        tmp.unlink(missing_ok=True)
        return False


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    force = "--force" in sys.argv
    ok = all(download(n, u, force) for n, u in MODELS.items())
    if ok:
        print("\nModelos listos. Ejecuta:  python src/main.py")
        return 0
    print("\nFallo la descarga. Revisa la conexion y reintenta.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
