"""Genera la hoja de contactos de expresiones para el README.

Renderiza cada expresion del avatar en una celda y las une en una sola imagen
`docs/img/expresiones.png`. No necesita camara ni pantalla.

Uso:  python scripts/make_expr_sheet.py
"""

import sys
from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from avatar import EXPRESSIONS, Avatar  # noqa: E402

CELL_W, CELL_H = 260, 300
COLS = 7
BG = (18, 20, 32)
FG = (150, 158, 180)


def main() -> int:
    pygame.init()
    names = list(EXPRESSIONS)
    rows = (len(names) + COLS - 1) // COLS
    sheet = pygame.Surface((COLS * CELL_W, rows * CELL_H))
    sheet.fill(BG)

    font = pygame.font.SysFont("consolas", 15)
    av = Avatar({"avatar": {"idle_enabled": False, "size": 200}})

    for i, name in enumerate(names):
        col, row = i % COLS, i // COLS
        cell = pygame.Surface((CELL_W, CELL_H), pygame.SRCALPHA)
        cell.fill((30, 33, 48, 255))

        av.expression = name
        av.expr_until = float("inf")
        av._expr_priority = -1
        av._expr_from_idle = False
        av._t = 0.6          # fase fija: sin parpadeo ni movimiento de pupilas
        av.look = [0.0, 0.0]
        av._look_target = [0.0, 0.0]
        av.size_abs = 200
        av.draw(cell, (CELL_W // 2, int(CELL_H * 0.44)))

        label = font.render(name, True, FG)
        cell.blit(label, label.get_rect(center=(CELL_W // 2, CELL_H - 18)))
        sheet.blit(cell, (col * CELL_W, row * CELL_H))

    out = ROOT / "docs" / "img"
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "expresiones.png"
    pygame.image.save(sheet, str(dest))
    pygame.quit()
    print(f"[OK] {len(names)} expresiones -> {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
