"""Genera las tarjetas de valuacion para todos los activos macro.

    python run.py                 # todas las tarjetas -> output/
    python run.py --keep 8        # deja solo las 8 mas recientes por activo

Las tarjetas quedan en output/ con nombre val_<KEY>_<fecha>.png; el
dashboard toma siempre la mas reciente por activo (igual que GEX).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from render_card import render
from valuation import compute_all

OUT = Path(__file__).parent / "output"


def prune(out_dir: Path, keep: int):
    from collections import defaultdict
    groups = defaultdict(list)
    for f in out_dir.glob("val_*.png"):
        key = f.stem.split("_")[1]
        groups[key].append(f)
    for key, files in groups.items():
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            old.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=10, help="tarjetas a conservar por activo")
    args = ap.parse_args()

    results = compute_all()
    for av in results:
        if av.error:
            print(f"[skip] {av.label}: {av.error}")
            continue
        path = render(av, OUT)
        print(f"[ok]   {av.label:10} {av.overall_label:14} -> {path.name}")

    prune(OUT, args.keep)


if __name__ == "__main__":
    main()
