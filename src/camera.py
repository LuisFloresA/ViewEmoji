"""Seleccion y apertura de la camara USB por nombre, sin abrir las demas.

Clave: enumerar dispositivos NO es lo mismo que abrirlos. Este modulo pide a
DirectShow la lista de nombres (instantaneo, no enciende ningun LED) y solo
abre la camara elegida. El brute force de indices encendia y apagaba todos los
sensores, lo que hacia parpadear los LED y dejaba camaras en mal estado.
"""

import time
from typing import Optional

import cv2

# Palabras que identifican una camara externa (USB) frente a la integrada.
USB_KEYWORDS = (
    "usb", "webcam", "web cam", "hd webcam", "external", "viewsonic",
    "logitech", "c270", "c310", "brio", "c920", "c930", "kn640", "k13",
    "g30", "c525", "c615", "hd pro", "ultra hd", "capture", "sn330",
    "f200", "q2n", "live", "streamcam", "facecam", "deley", "anker",
    "trust", " genius", "easeus", "obs", "capture", "caddx", "sunplus",
)

# Palabras que identifican la camara integrada del equipo.
INTERNAL_KEYWORDS = (
    "integrated", "integrada", "built-in", "internal", "internal camera",
    "hp wide", "hd camera", "user facing", "facetime", "idea", "thinkpad",
)


def list_camera_names() -> list[str]:
    """Nombres de camara EN ORDEN DE INDICE de OpenCV, sin abrir ninguna.

    DirectShow (pygrabber) es la unica fuente fiable: OpenCV numera sus
    indices siguiendo el orden de los filtros DirectShow. Una consulta PnP
    devuelve otro orden, asi que no sirve para elegir indice.
    Si pygrabber no esta disponible devuelve [] y el llamante cae al indice
    configurado en vez de arriesgarse a abrir la camara equivocada.
    """
    try:
        from pygrabber.dshow_graph import FilterGraph
        return [str(n) for n in FilterGraph().get_input_devices()]
    except Exception:
        return []


def classify(name: str) -> str:
    """Devuelve 'internal', 'usb' o 'unknown' segun el nombre del dispositivo."""
    low = name.lower()
    if any(k in low for k in INTERNAL_KEYWORDS):
        return "internal"
    if any(k in low for k in USB_KEYWORDS):
        return "usb"
    return "unknown"


def pick_index(names: list[str], prefer_usb: bool = True,
               want_name: Optional[str] = None) -> Optional[int]:
    """Elige indice de camara segun config, sin abrir ningun dispositivo."""
    if not names:
        return None

    # 1) Coincidencia explicita por nombre (config)
    if want_name:
        want = want_name.strip().lower()
        for i, n in enumerate(names):
            if want in n.lower():
                return i
        for i, n in enumerate(names):
            if classify(n) == want:
                return i

    # 2) Clasificacion por palabras clave
    kinds = [classify(n) for n in names]
    if prefer_usb:
        if "usb" in kinds:
            return kinds.index("usb")
        # 3) Fallback: primer indice no interno
        for i, k in enumerate(kinds):
            if k != "internal":
                return i

    # 4) Sin preferencia o sin USB: el primero disponible
    return 0


def _open(index: int, width: int, height: int, fps: int,
          backend=cv2.CAP_DSHOW, warmup: float = 1.2):
    """Abre un indice concreto y espera a que entregue frames de verdad."""
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    # Las webcams necesitan unos fotogramas para estabilizar la exposicion.
    deadline = time.time() + warmup
    got = False
    while time.time() < deadline:
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(0.05)
            continue
        got = True
        break
    if not got:
        cap.release()
        return None
    # un par de frames extra para estabilizar
    for _ in range(3):
        cap.read()
    return cap


def open_camera(cfg: dict, log=print) -> Optional[cv2.VideoCapture]:
    """Abre la camara indicada en cfg (prioriza la USB) y devuelve el capture.

    Claves de config relevantes (ver config/config.yaml):
        device_index   indice fijo; -1 = autodetectar por nombre
        device_name    texto a buscar en el nombre del dispositivo
        prefer_usb     True = elegir la externa antes que la integrada
    """
    cam = cfg.get("camera", {})
    width = int(cam.get("width", 1280))
    height = int(cam.get("height", 720))
    fps = int(cam.get("fps", 30))
    fixed = int(cam.get("device_index", -1))
    want_name = cam.get("device_name") or None
    prefer_usb = bool(cam.get("prefer_usb", True))

    names = list_camera_names()
    if names:
        for i, n in enumerate(names):
            log(f"[camera] indice {i}: {n!r} ({classify(n)})")
    else:
        log("[camera] AVISO: sin pygrabber no se pueden leer los nombres. "
            "Instala pygrabber o fija camera.device_index en config.yaml "
            "(indice de la USB).")

    if fixed < 0:
        if not names:
            # Sin nombres no se puede elegir con seguridad: usar el indice 0 y
            # avisar, en vez de abrir camaras a ciegas.
            log("[camera] sin nombres: usando indice 0 (puede ser la integrada)")
            fixed = 0
        else:
            fixed = pick_index(names, prefer_usb=prefer_usb, want_name=want_name)
            if fixed is None:
                log("[camera] ERROR: no se encontro ninguna camara")
                return None
            log(f"[camera] seleccion automatica -> indice {fixed} ({names[fixed]!r})")
    else:
        label = names[fixed] if fixed < len(names) else "?"
        log(f"[camera] indice fijo {fixed} ({label!r})")

    cap = _open(fixed, width, height, fps)
    if cap is None:
        log(f"[camera] fallo al abrir {width}x{height}@{fps}, reintentando 640x480")
        cap = _open(fixed, 640, 480, fps)
    if cap is None:
        log(f"[camera] fallo al abrir {fixed}; probando con backend MSMF")
        cap = _open(fixed, width, height, fps, backend=cv2.CAP_MSMF)
    if cap is None:
        log("[camera] ERROR: no se pudo abrir la camara seleccionada")
        return None

    actual = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
              int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    log(f"[camera] lista: indice {fixed} en {actual[0]}x{actual[1]}")
    return cap
