"""Reproductor de sonidos: prioriza assets/sounds (CC0) y usa fallback sintetizado."""

from pathlib import Path
from typing import Optional

try:
    import pygame
except ImportError:  # pygame es opcional si audio.enabled == false
    pygame = None

from config import ROOT

SOUNDS_DIR = ROOT / "assets" / "sounds"
FALLBACK_DIR = ROOT / "assets" / "sounds_fallback"


class SoundEngine:
    def __init__(self, cfg: dict, log=print):
        self.enabled = bool(cfg.get("audio", {}).get("enabled", True))
        self.volume = float(cfg.get("audio", {}).get("volume", 0.7))
        self.log = log
        self._cache: dict[str, object] = {}
        self._ready = False
        self._silent = object()

        if not self.enabled:
            log("[audio] deshabilitado por configuracion")
            return
        if pygame is None:
            log("[audio] pygame no instalado: audio deshabilitado")
            self.enabled = False
            return
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self._ready = True
            log("[audio] mixer listo")
        except Exception as exc:  # sin dispositivo de salida
            log(f"[audio] no se pudo iniciar mixer ({exc}): audio deshabilitado")
            self.enabled = False

    def _resolve(self, sound_name: Optional[str], fallback_name: Optional[str]) -> Optional[Path]:
        """Busca el archivo: primero assets/sounds, luego sounds_fallback."""
        candidates = []
        if sound_name:
            stem = Path(sound_name).stem
            for ext in (".ogg", ".wav", ".mp3", ".flac"):
                candidates.append(SOUNDS_DIR / f"{stem}{ext}")
        if fallback_name:
            for ext in (".ogg", ".wav", ".mp3"):
                candidates.append(FALLBACK_DIR / f"{fallback_name}{ext}")
        for path in candidates:
            if path.exists():
                return path
        return None

    def play(self, sound_name: Optional[str], fallback_name: Optional[str] = None) -> bool:
        if not self._ready:
            return False
        key = sound_name or fallback_name or ""
        if key in self._cache:
            path = self._cache[key]
        else:
            path = self._resolve(sound_name, fallback_name)
            if path is None:
                self.log(f"[audio] sin archivo para '{sound_name}' / '{fallback_name}'")
                self._cache[key] = None  # cacheamos el fallo
                return False
            self._cache[key] = path
        if path is None:
            return False
        try:
            snd = pygame.mixer.Sound(str(path))
            snd.set_volume(self.volume)
            snd.play()
            return True
        except Exception as exc:
            self.log(f"[audio] error reproduciendo {path.name}: {exc}")
            return False
