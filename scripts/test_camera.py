"""Pruebas de la seleccion de camara por nombre (no abre ningun dispositivo)."""

import sys
sys.path.insert(0, "src")

from camera import classify, pick_index

CASES = [
    (["Integrated Camera", "ViewSonic HD webcam"], "usb", 1),
    (["Integrated Camera", "ViewSonic HD webcam"], "internal", 0),
    (["Integrated Camera", "ViewSonic HD webcam"], "name:view", 1),
    (["Integrated Camera", "ViewSonic HD webcam"], "name:noexiste", 1),
    (["Integrated Camera"], "usb", 0),
    (["HD Webcam C270", "Integrated Camera"], "usb", 0),
    (["Integrated Camera", "Logitech C920"], "usb", 1),
    (["Integrated Camera", "USB 2.0 Camera"], "usb", 1),
    (["Integrated Camera", "FaceTime HD Camera"], "internal", 0),
    ([], "usb", None),
]

fails = []
for names, mode, expected in CASES:
    if mode == "usb":
        got = pick_index(names, prefer_usb=True)
    elif mode == "internal":
        got = pick_index(names, prefer_usb=False)
    else:
        got = pick_index(names, want_name=mode.split(":", 1)[1])
    ok = got == expected
    mark = "OK  " if ok else "FALLO"
    print(f"[{mark}] pick({names}, {mode}) -> {got} (esperado {expected})")
    if not ok:
        fails.append((names, mode, got, expected))

print()
print("[clasificacion]")
for n in ["Integrated Camera", "ViewSonic HD webcam", "USB 2.0 Camera",
          "FaceTime HD Camera", "Logitech StreamCam", "Cámara desconocida"]:
    print(f"  {n!r:28} -> {classify(n)}")

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLOS")
sys.exit(0 if not fails else 1)
