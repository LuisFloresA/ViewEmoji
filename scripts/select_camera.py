r"""Selector interactivo de camara.

Lista las camaras que ve el equipo (por nombre, sin abrir ninguna), deja
elegir cual usar y deja la eleccion anotada en config/config.yaml.

    python scripts\select_camera.py            lista y pregunta
    python scripts\select_camera.py --list     solo lista
    python scripts\select_camera.py --multiple exit 0 si hay >1 camara
    python scripts\select_camera.py --auto     vuelve a autodeteccion

Guarda el NOMBRE, no el indice.

Motivo: DirectShow no garantiza el mismo orden de indices entre
arranques ni entre equipos, asi que un indice guardado puede acabar
apuntando a otra camara (tipicamente a la integrada). Con
camera.device_name, src/camera.py:pick_index busca el texto en el
nombre en cada arranque y, si un dia no aparece, cae al indice
guardado como indice de reserva.

No usa yaml.safe_dump a proposito: ese volcado borraria los 23
comentarios de config.yaml, que explican los limites y el motivo de
cada valor. Aqui solo se reescribe la linea elegida.
"""

import argparse
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from camera import classify, list_camera_names, pick_index  # noqa: E402

CONFIG_PATH = ROOT / "config" / "config.yaml"


def set_yaml_key(text: str, key: str, value: str, found: list | None = None):
    """Reescribe solo la linea `key:` de un YAML, conservando su comentario.

    `value` se escribe tal cual (el llamante pone las comillas del YAML).
    Se conserva el separador previo al '#' y el espacio posterior, para que
    la linea quede igual que si no se hubiera tocado.

    Si se pasa `found` (lista), se le anade True/False segun existiera la
    clave. Hace falta porque devolver el texto no permite distinguir "la
    clave no existe" de "el valor ya era este", que es justo lo que pasa
    con `--auto` sobre un config ya en autodeteccion.
    """
    out = []
    done = False
    for line in text.splitlines(keepends=True):
        if done or not line.lstrip().startswith(key + ":"):
            out.append(line)
            continue
        done = True
        indent = line[: len(line) - len(line.lstrip())]
        newline = "\n" if line.endswith("\n") else ""
        body = line.rstrip("\n")
        comment = ""
        if "#" in body:
            body, _, raw = body.partition("#")
            # Se conserva el separador previo al '#' y el espacio posterior,
            # para que la linea quede igual que si no se hubiera tocado.
            comment = body[len(body.rstrip()):] + "#" + raw
        out.append(f"{indent}{key}: {value.rstrip()}{comment.rstrip()}"
                   f"{newline}")
    if found is not None:
        found.append(done)
    return "".join(out) if done else text


def save_choice(index: int, name: str = "", remember: bool = True) -> bool:
    """Anota la eleccion en config/config.yaml. True si se escribio.

    `name` vacio significa que la camara no tiene nombre en DirectShow: en
    ese caso hay que dejar device_index FIJO, porque no hay texto con el
    que buscarla en el proximo arranque.
    """
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[ERROR] no se pudo leer {CONFIG_PATH.name}: {exc}")
        return False

    if remember:
        idx = str(index)
        dev = f'"{name}"' if name else '""'
    else:
        # -1 = autodeteccion por nombre, sin texto de busqueda.
        idx, dev = "-1", '""'

    # Cada clave se comprueba por separado: con un config ya en
    # autodeteccion, set_yaml_key devuelve el texto sin cambios, y eso no
    # debe confundirse con "la clave no existe".
    falta = []
    new = set_yaml_key(text, "device_index", idx, falta)
    if falta and not falta[0]:
        print(f"[ERROR] {CONFIG_PATH.name} no tiene la clave 'device_index'")
        return False
    falta.clear()
    new = set_yaml_key(new, "device_name", dev, falta)
    if falta and not falta[0]:
        print(f"[ERROR] {CONFIG_PATH.name} no tiene la clave 'device_name'")
        return False

    try:
        CONFIG_PATH.write_text(new, encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"[ERROR] no se pudo escribir {CONFIG_PATH.name}: {exc}")
        return False
    return True


@contextmanager
def _silencioso():
    """Tapa stderr/stdout de OpenCV durante el sondeo.

    `cv2.utils.logging.setLogLevel` no sirve: los avisos de
    "backend ... can't be used to capture by index" y "Camera index out of
    range" los escribe el backend de captura directamente en el descriptor,
    no por el logger. Al explorar indices a proposito salen siempre, y
    taparian el listado que tiene que leer el usuario.
    """
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        fd1, fd2 = os.dup(1), os.dup(2)
        os.dup2(null, 1)
        os.dup2(null, 2)
        try:
            yield
        finally:
            os.dup2(fd1, 1)
            os.dup2(fd2, 2)
            os.close(fd1)
            os.close(fd2)
    finally:
        os.close(null)


def probe(max_indice: int = 8) -> list[tuple[int, str, int, int]]:
    """Abre cada indice uno a uno y ve cuales dan imagen de verdad.

    Hace falta ademas de list_camera_names() porque DirectShow no siempre
    lista lo que OpenCV si abre: si la USB se registra solo bajo
    Media Foundation, pygrabber no la ve pero `cv2.VideoCapture(i)` con
    CAP_MSMF si. Sin este sondeo, el selector no podria ofrecerla y
    pareceria que no hay camara.

    Devuelve [(indice, backend, ancho, alto), ...] solo con los que
    entregaron al menos un frame.
    """
    import cv2

    halladas = []
    with _silencioso():
        for idx in range(max_indice + 1):
            for etiqueta, backend in (("DSHOW", cv2.CAP_DSHOW),
                                      ("MSMF", cv2.CAP_MSMF),
                                      ("ANY", cv2.CAP_ANY)):
                cap = cv2.VideoCapture(idx, backend)
                if not cap.isOpened():
                    cap.release()
                    continue
                limite = time.time() + 2.5
                ancho = alto = 0
                while time.time() < limite:
                    ok, frame = cap.read()
                    if ok and frame is not None and frame.size:
                        ancho, alto = frame.shape[1], frame.shape[0]
                        break
                cap.release()
                if ancho:
                    halladas.append((idx, etiqueta, ancho, alto))
                    break
    return halladas


def show(names, halladas=None):
    """Muestra el catalogo: nombres de DirectShow + sondeos que si abren."""
    print("Camaras:")
    vistos = set()
    for i, n in enumerate(names):
        marca = "  <- USB" if classify(n) == "usb" else ""
        abierto = ""
        for idx, _b, w, h in (halladas or []):
            if idx == i:
                abierto = f"   [abre {w}x{h}]"
        print(f"  [{i}]  {n}{abierto}{marca}")
        vistos.add(i)

    extras = [t for t in (halladas or []) if t[0] not in vistos]
    for idx, backend, w, h in extras:
        print(f"  [{idx}]  (sin nombre en DirectShow, "
              f"abre {w}x{h} por {backend})")

    if not names and not extras:
        print("  (ninguna)")
        return
    if names:
        auto = pick_index(names, prefer_usb=True)
        if auto is not None:
            print(f"\n  Automatica: indice {auto} ({names[auto]!r})")
    else:
        print("\n  Automatica: sin nombres, no se puede elegir por nombre")


def ask(total: int) -> int:
    """Pregunta el indice. Devuelve el elegido, o -1 si se cancela."""
    while True:
        try:
            raw = input(f"\nCamara a usar (0-{total - 1}) "
                        "[Enter = cancelar]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return -1
        if not raw:
            return -1
        try:
            idx = int(raw)
        except ValueError:
            print("  Eso no es un numero.")
            continue
        if not 0 <= idx < total:
            print(f"  Fuera de rango (0-{total - 1}).")
            continue
        return idx


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Elegir camara y anotarla en config/config.yaml.")
    grupo = ap.add_mutually_exclusive_group()
    grupo.add_argument("--list", action="store_true",
                       help="solo listar las camaras")
    grupo.add_argument("--multiple", action="store_true",
                       help="exit 0 si hay mas de una camara (para run.bat)")
    grupo.add_argument("--auto", action="store_true",
                       help="volver a autodeteccion")
    grupo.add_argument("--no-remember", action="store_true",
                       help="usar el indice una vez, sin guardarlo")
    ap.add_argument("--index", type=int, metavar="N",
                    help="elige el indice N sin preguntar (para scripts)")
    ap.add_argument("--sin-sondeo", action="store_true",
                    help="no abrir camaras para buscarlas (solo nombres)")
    args = ap.parse_args()

    names = list_camera_names()

    if args.multiple:
        return 0 if len(names) > 1 else 1

    if args.auto:
        if not save_choice(-1, "", remember=False):
            return 1
        print("Vuelto a autodeteccion. Se usara la USB si aparece.")
        return 0

    halladas = None if args.sin_sondeo else probe()

    if not names and not halladas:
        print("No se detecto ninguna camara.")
        print("Comprueba que este conectada y que otro programa no la este "
              "usando (Zoom, Teams, el navegador o la Camara de Windows).")
        return 1

    show(names, halladas)
    if args.list:
        return 0

    # Catalogo unico: los nombres de DirectShow primero y despues los
    # indices que solo aparecen al abrirlos. El numero que se teclea es
    # el indice real de OpenCV, no la posicion en esta lista.
    if args.index is not None:
        idx = args.index
    else:
        extra = [t for t in halladas if t[0] >= len(names)] if halladas else []
        total = max(len(names), max((t[0] for t in extra), default=-1) + 1)
        idx = ask(total)
    if idx < 0:
        print("No se cambio nada.")
        return 0

    nombre = names[idx] if idx < len(names) else ""
    if not save_choice(idx, nombre, remember=not args.no_remember):
        return 1

    print(f"\nGuardado en {CONFIG_PATH.name}:")
    if nombre:
        print(f"  device_index: {idx}   (solo de reserva)")
        print(f'  device_name : "{nombre}"')
    else:
        print(f"  device_index: {idx}   FIJO (esta camara no tiene nombre "
              f"en DirectShow)")
        print('  device_name : ""')
        print("\n  Ojo: al no tener nombre se usara SIEMPRE este indice. Si")
        print("  tras reiniciar el equipo las camaras cambian de orden, hay")
        print("  que volver a elegir. Ejecuta de nuevo este script.")
    if args.no_remember:
        print("\n(--no-remember: este equipo no lo recordara)")
    print("\nAhora:  scripts\\run.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())