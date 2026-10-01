"""Polling de actualizaciones: git fetch/pull y reinicio si hay cambios.

Diseñado para ejecutarse en bucle desde el AIO (Windows) sin depender de
Portainer. Cada `poll_minutes` comprueba si el remoto trae commits nuevos; si
los hay, hace pull y reinicia la app.

Uso:
    python scripts/update_check.py            # bucle continuo
    python scripts/update_check.py --once     # una sola comprobación
    python scripts/update_check.py --install  # crea la tarea programada
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(args: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, "comando no encontrado"
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def git_available() -> bool:
    code, _ = run(["git", "--version"], ROOT)
    return code == 0


def is_git_repo() -> bool:
    code, out = run(["git", "rev-parse", "--is-inside-work-tree"], ROOT)
    return code == 0 and out.strip() == "true"


def current_branch() -> str:
    _, out = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], ROOT)
    return out.strip() or "main"


def local_sha() -> str:
    _, out = run(["git", "rev-parse", "HEAD"], ROOT)
    return out.strip()


def poll_once(branch: str) -> bool:
    """Devuelve True si se aplicaron actualizaciones."""
    code, out = run(["git", "fetch", "--quiet", "origin", branch], ROOT)
    if code != 0:
        print(f"[update] fetch fallo: {out}")
        return False
    local = local_sha()
    _, remote = run(["git", "rev-parse", f"origin/{branch}"], ROOT)
    remote = remote.strip()
    if not remote or remote == local:
        print(f"[update] sin cambios (HEAD {local[:8]})")
        return False
    print(f"[update] cambios detectados: {local[:8]} -> {remote[:8]}")
    code, out = run(["git", "reset", "--hard", f"origin/{branch}"], ROOT)
    if code != 0:
        print(f"[update] pull fallo: {out}")
        return False
    print("[update] actualizado correctamente")
    return True


def restart_app() -> None:
    print("[update] reiniciando la aplicacion")
    run(["taskkill", "/F", "/IM", "python.exe"], ROOT, timeout=20)
    time.sleep(2)
    python = sys.executable
    try:
        subprocess.Popen([python, str(ROOT / "src" / "main.py")], cwd=str(ROOT))
    except Exception as exc:
        print(f"[update] no se pudo reiniciar: {exc}")


def install_scheduled_task(poll_minutes: int) -> int:
    """Crea una tarea de Windows que ejecuta el polling al iniciar sesion."""
    task_name = "AvatarInteractivoUpdate"
    cmd = f'"{sys.executable}" "{ROOT / "scripts" / "update_check.py"}"'
    commands = [
        "schtasks", "/Create", "/F",
        "/SC", "ONLOGON",
        "/RL", "HIGHEST",
        "/TN", task_name,
        "/TR", cmd,
    ]
    code, out = run(commands, ROOT)
    if code != 0:
        print(f"[install] schtasks fallo: {out}")
        return code
    print(f"[install] tarea '{task_name}' creada (al iniciar sesion)")
    print(f"[install] sugerencia: anade un segundo disparador cada {poll_minutes} min")
    print("[install] o ejecuta manualmente:  python scripts/update_check.py")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="una sola comprobacion")
    ap.add_argument("--install", action="store_true", help="crear tarea programada de Windows")
    ap.add_argument("--minutes", type=int, default=10, help="minutos entre comprobaciones")
    ap.add_argument("--no-restart", action="store_true", help="no reiniciar tras actualizar")
    args = ap.parse_args()

    if args.install:
        return install_scheduled_task(args.minutes)

    if not git_available():
        print("[update] git no esta instalado o no esta en el PATH")
        return 127
    if not is_git_repo():
        print(f"[update] {ROOT} no es un repositorio git")
        return 1

    branch = current_branch()
    print(f"[update] vigilando rama '{branch}' cada {args.minutes} min")

    if args.once:
        if poll_once(branch) and not args.no_restart:
            restart_app()
        return 0

    try:
        while True:
            if poll_once(branch) and not args.no_restart:
                restart_app()
                return 0
            time.sleep(args.minutes * 60)
    except KeyboardInterrupt:
        print("\n[update] detenido por el usuario")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
