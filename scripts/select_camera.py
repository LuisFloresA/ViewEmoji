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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from camera import classify, list_camera_names, pick_index  # noqa: E402

CONFIG_PATH = ROOT / "config" / "config.yaml"


def set_yaml_key(text: str, key: str, value: str) -> str:
    """Reescribe solo la linea `key:` de un YAML, conservando su comentario.

    Devuelve el texto cambiado, o el original si la clave no existe.
    `value` se escribe tal cual (el llamante pone las comillas del YAML).

    Se conserva el separador previo al '#' para que los comentarios del
    bloque no pierdan la alineacion.
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
    return "".join(out) if done else text


def save_choice(index: int, name: str, remember: bool) -> bool:
    """Anota la eleccion en config/config.yaml. True si se escribio."""
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[ERROR] no se pudo leer {CONFIG_PATH.name}: {exc}")
        return False

    if remember:
        idx, dev = str(index), f'"{name}"'
    else:
        # -1 = autodeteccion por nombre, sin texto de busqueda.
        idx, dev = "-1", '""'

    new = set_yaml_key(text, "device_index", idx)
    new = set_yaml_key(new, "device_name", dev)
    if new == text:
        print("[ERROR] no se encontro 'device_index'/'device_name' en "
              f"{CONFIG_PATH.name}")
        return False

    try:
        CONFIG_PATH.write_text(new, encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"[ERROR] no se pudo escribir {CONFIG_PATH.name}: {exc}")
        return False
    return True


def show(names):
    print("Camaras detectadas (aun no se ha abierto ninguna):\n")
    for i, n in enumerate(names):
        mark = "  <- USB" if classify(n) == "usb" else ""
        print(f"  [{i}]  {n}{mark}")
    auto = pick_index(names, prefer_usb=True)
    if auto is not None:
        print(f"\n  Eleccion automatica: indice {auto} ({names[auto]!r})")


def ask(names) -> int:
    """Pregunta el indice. Devuelve el elegido, o -1 si se cancela."""
    while True:
        try:
            raw = input(f"\nNumero de camara a usar (0-{len(names) - 1}) "
                        "[Enter = la de antes]: ").strip()
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
        if not 0 <= idx < len(names):
            print(f"  Fuera de rango (0-{len(names) - 1}).")
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
    args = ap.parse_args()

    names = list_camera_names()

    if args.multiple:
        return 0 if len(names) > 1 else 1

    if not names:
        print("No se detecto ninguna camara.")
        if not args.list:
            print("Comprueba que este conectada y que otro programa no la "
                  "este usando.")
        return 1

    if args.auto:
        if not save_choice(-1, "", remember=False):
            return 1
        print("Vuelto a autodeteccion. Se usara la USB si aparece.")
        return 0

    show(names)
    if args.list:
        return 0

    if args.index is not None:
        if not 0 <= args.index < len(names):
            print(f"Indice {args.index} fuera de rango (0-{len(names) - 1}).")
            return 1
        idx = args.index
    else:
        idx = ask(names)
    if idx < 0:
        print("No se cambio nada.")
        return 0

    if not save_choice(idx, names[idx], remember=not args.no_remember):
        return 1
    print(f"\nGuardado en {CONFIG_PATH.name}:")
    print(f"  device_index: {idx}   (solo de reserva)")
    print(f"  device_name : \"{names[idx]}\"")
    if args.no_remember:
        print("\n(--no-remember: este equipo no lo recordara)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())