"""Autoinstalador: deja el proyecto listo para ejecutar en una maquina limpia.

Se ejecuta con el Python que haya en el sistema y hace, en este orden y de
forma idempotente (se puede repetir sin romper nada):

    1. Comprueba que la version de Python sirve (3.10 - 3.14).
    2. Crea "venv/" si no existe.
    3. Instala las dependencias de requirements.txt.
    4. Arregla el conflicto de OpenCV (mediapipe arrastra la 5.x, y este
       proyecto necesita la 4.10; las dos escriben en el mismo modulo cv2).
    5. Descarga los modelos de deteccion (~11 MB) si no estan.

Por que la logica va en Python y no en el .bat: en batch hay que parsear
versiones y rutas de forma fragil. Aqui es codigo normal y testeable.

Uso:  python scripts/bootstrap.py
      python scripts/bootstrap.py --only models     # solo descargar modelos
"""

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = ROOT / "venv"
REQUIREMENTS = ROOT / "requirements.txt"
MODELS_SCRIPT = ROOT / "scripts" / "download_models.py"

# Rango de Python con el que esta verificado el proyecto. Por encima no hay
# ruedas de pygame-ce ni de mediapipe y el fallo seria incomprensible.
MIN_PY = (3, 10)
MAX_PY = (3, 14)

# opencv-python esta fijado a 4.10 porque las 5.x no funcionan en este equipo
# (Smart App Control). Ver la nota de requirements.txt.
WANT_CV2 = "4.10"


def venv_python() -> Path:
    """Ruta al interprete del venv (distinto en Windows y en Unix)."""
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    """Ejecuta un comando mostrando lo que hace, y devuelve su resultado."""
    printable = " ".join(str(c) for c in cmd)
    if kw.get("show", True):
        print(f"    $ {printable}")
    return subprocess.run([str(c) for c in cmd], **kw)


def check_python() -> bool:
    v = sys.version_info[:2]
    if MIN_PY <= v <= MAX_PY:
        print(f"    Python {v[0]}.{v[1]} sirve "
              f"({MIN_PY[0]}.{MIN_PY[1]} - {MAX_PY[0]}.{MAX_PY[1]})")
        return True
    print(f"    [ERROR] Python {v[0]}.{v[1]} no sirve.")
    print(f"            Se necesita {MIN_PY[0]}.{MIN_PY[1]} a {MAX_PY[0]}.{MAX_PY[1]}.")
    if v > MAX_PY:
        print("            Python muy reciente: no hay ruedas de pygame-ce ni de")
        print("            mediapipe para esa version. Instala una anterior, por")
        print("            ejemplo con:  py -3.14")
    else:
        print("            Instala Python desde https://www.python.org/downloads/")
        print("            marcando 'Add python.exe to PATH'.")
    return False


def create_venv() -> bool:
    print("[2/5] Entorno virtual (venv/)")
    vp = venv_python()
    if vp.exists():
        print(f"    ya existe: {vp.relative_to(ROOT)}")
        return True
    print("    creando venv/ ...")
    try:
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV_DIR)
    except Exception as exc:
        print(f"    [ERROR] no se pudo crear el venv: {exc}")
        print("            Borra la carpeta venv/ y vuelve a intentarlo.")
        return False
    print("    creado.")
    return True


def install_requirements() -> bool:
    print("[3/5] Dependencias (requirements.txt)")
    vp = venv_python()
    run([vp, "-m", "pip", "install", "--upgrade", "pip"],
        capture_output=True, text=True)
    res = run([vp, "-m", "pip", "install", "-r", REQUIREMENTS])
    if res.returncode != 0:
        print("    [ERROR] fallo la instalacion de dependencias.")
        print("            Suele ser falta de conexion a internet.")
        return False
    return True


def current_cv2(vp: Path) -> str:
    """Devuelve la version de cv2 TAL COMO queda tras instalar."""
    try:
        res = subprocess.run([str(vp), "-c", "import cv2;print(cv2.__version__)"],
                             capture_output=True, text=True, timeout=120)
        return res.stdout.strip()
    except Exception:
        return ""


def fix_opencv() -> bool:
    """mediapipe depende de opencv-contrib-python (5.x) y este proyecto fija
    opencv-python 4.10. Ambas distribuciones escriben en el MISMO modulo cv2,
    asi que gana la que se instalo la ultima, y la 5.x no funciona aqui."""
    print("[4/5] OpenCV (conflicto 4.10 vs 5.x)")
    vp = venv_python()
    got = current_cv2(vp)
    if got.startswith(WANT_CV2):
        print(f"    cv2 {got} correcto.")
        return True
    print(f"    cv2 es '{got or 'desconocida'}'; se espera {WANT_CV2}.x")
    print("    reinstalando la version correcta ...")
    run([vp, "-m", "pip", "install", "--force-reinstall", "--no-deps",
         f"opencv-python=={WANT_CV2}.0.84"])
    got2 = current_cv2(vp)
    if got2.startswith(WANT_CV2):
        print(f"    corregido: cv2 {got2}")
        return True
    print(f"    [ERROR] sigue siendo '{got2}' tras el arreglo.")
    print("            Cierra cualquier proceso que use cv2 y reintenta.")
    return False


def download_models() -> bool:
    print("[5/5] Modelos de deteccion (~11 MB)")
    vp = venv_python()
    if not MODELS_SCRIPT.exists():
        print(f"    [ERROR] no encuentro {MODELS_SCRIPT}")
        return False
    res = run([vp, str(MODELS_SCRIPT)])
    return res.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepara el proyecto para ejecutar.")
    ap.add_argument("--only", choices=["models"],
                    help="Ejecutar solo esa parte (por ahora: models).")
    args = ap.parse_args()

    print("=" * 56)
    print("  Avatar Interactivo - preparacion del entorno")
    print("=" * 56)

    if args.only == "models":
        ok = check_python() and download_models()
    else:
        print("[1/5] Version de Python")
        ok = check_python()
        if ok:
            ok = create_venv()
        if ok:
            ok = install_requirements()
        if ok:
            ok = fix_opencv()
        if ok:
            ok = download_models()

    print("-" * 56)
    if not ok:
        print("La preparacion NO ha terminado bien. Revisa los mensajes de arriba.")
        return 1
    print("Listo. Arranca con:  scripts\\run.bat")
    print("O directamente:       venv\\Scripts\\python.exe src\\main.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())