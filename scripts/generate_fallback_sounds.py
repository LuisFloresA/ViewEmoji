"""
Genera los sonidos fallback (tonos sintetizados) en assets/sounds_fallback/.

Cada gesto referencia un "fallback" (nombre corto) que se mapea a un patrón
de tonos. Se generan archivos .wav reales con la librería estándar `wave`
para que sean compatibles con pygame sin dependencias extra.

Uso:
    python scripts/generate_fallback_sounds.py
"""

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 44100
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "sounds_fallback"


# Cada patrón: lista de (frecuencia_hz, duracion_s, tipo_onda, volumen)
PATTERNS = {
    "gasp": [(520, 0.12, "sine", 0.7), (760, 0.16, "sine", 0.6)],
    "yay": [(660, 0.10, "triangle", 0.7), (880, 0.14, "triangle", 0.7)],
    "pop": [(900, 0.06, "sine", 0.8), (300, 0.10, "sine", 0.5)],
    "hum": [(300, 0.20, "sine", 0.5), (330, 0.20, "sine", 0.5)],
    "buzz": [(140, 0.25, "square", 0.5)],
    "chime_up": [(660, 0.10, "sine", 0.6), (990, 0.16, "sine", 0.6)],
    "ooh": [(400, 0.18, "sine", 0.6), (520, 0.22, "sine", 0.6)],
    "nod": [(600, 0.08, "triangle", 0.6), (450, 0.12, "triangle", 0.6)],
    "womp": [(220, 0.20, "sine", 0.6), (180, 0.24, "sine", 0.6)],
    "whoosh": [(200, 0.06, "sine", 0.4), (700, 0.18, "sine", 0.5)],
    "whoa": [(500, 0.14, "triangle", 0.6), (400, 0.18, "triangle", 0.6)],
    "fanfare": [(523, 0.10, "triangle", 0.7), (659, 0.10, "triangle", 0.7), (784, 0.20, "triangle", 0.7)],
    "boom": [(90, 0.30, "sine", 0.9), (55, 0.30, "sine", 0.8)],
    "bleh": [(340, 0.10, "square", 0.5), (280, 0.14, "square", 0.5)],
    "womp_womp": [(220, 0.16, "sine", 0.6), (200, 0.16, "sine", 0.6), (180, 0.22, "sine", 0.6)],
    "pop2": [(950, 0.05, "sine", 0.8)],
}


def tone(freq, duration, wave_type, volume):
    n = int(SAMPLE_RATE * duration)
    frames = bytearray()
    for i in range(n):
        t = i / SAMPLE_RATE
        # envolvente para evitar clicks
        env = min(1.0, t / 0.01) * min(1.0, (duration - t) / 0.03)
        if wave_type == "sine":
            s = math.sin(2 * math.pi * freq * t)
        elif wave_type == "square":
            s = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
        elif wave_type == "triangle":
            s = 2.0 * abs(2.0 * ((freq * t) % 1.0) - 1.0) - 1.0
        else:
            s = math.sin(2 * math.pi * freq * t)
        val = int(max(-1.0, min(1.0, s * env * volume)) * 32767)
        frames += struct.pack("<h", val)
    return frames


def build(name, pattern):
    data = bytearray()
    for part in pattern:
        data += tone(*part)
    path = OUT_DIR / f"{name}.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(data))
    return path


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, pattern in PATTERNS.items():
        p = build(name, pattern)
        print(f"[fallback] generado {p.name}")


if __name__ == "__main__":
    main()
