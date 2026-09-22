"""Publica las tarjetas de valuacion en el repo de datos que lee el dashboard
(Render): jttyr/macro-valuation-data, rama `data`, un PNG por ticker en
latest/<KEY>.png -- sobreescribiendo siempre el mismo nombre y con push --force,
igual que market-drivers y gex-terminal.

    python publish.py            # toma lo ultimo de output/ y lo sube
    python run.py && python publish.py   # regenerar + subir

Requiere `gh`/git autenticados con permiso de escritura al repo.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from valuation import ASSETS

HERE = Path(__file__).parent
OUT = HERE / "output"
REPO_URL = "https://github.com/jttyr/macro-valuation-data.git"
BRANCH = "data"
CLONE = HERE / "_repo"                # clon de trabajo (no es parte de output/)

# key en valuation -> nombre del archivo destino en latest/
DEST_NAME = {a["key"]: f"{a['key']}.png" for a in ASSETS}


def _run(cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True)


def latest_card(key: str) -> Path | None:
    files = sorted(OUT.glob(f"val_{key}_*.png"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def ensure_clone():
    if (CLONE / ".git").exists():
        _run(["git", "-C", str(CLONE), "fetch", "origin", BRANCH])
        _run(["git", "-C", str(CLONE), "checkout", BRANCH])
        _run(["git", "-C", str(CLONE), "reset", "--hard", f"origin/{BRANCH}"])
    else:
        _run(["git", "clone", "--branch", BRANCH, "--single-branch", REPO_URL, str(CLONE)])


def main():
    ensure_clone()
    dest_dir = CLONE / "latest"
    dest_dir.mkdir(exist_ok=True)

    published = []
    for a in ASSETS:
        card = latest_card(a["key"])
        if card is None:
            print(f"[skip] {a['label']}: no hay tarjeta en output/")
            continue
        dest = dest_dir / DEST_NAME[a["key"]]
        dest.write_bytes(card.read_bytes())
        published.append(f"{a['label']}->{dest.name}")

    if not published:
        print("nada que publicar")
        sys.exit(1)

    _run(["git", "-C", str(CLONE), "add", "-A"])
    # --allow-empty por si se corre dos veces seguidas sin cambios
    _run(["git", "-C", str(CLONE), "commit", "-m", "actualizar imagenes de valuacion",
          "--allow-empty"])
    _run(["git", "-C", str(CLONE), "push", "origin", BRANCH, "--force"])
    print("publicado:", ", ".join(published))


if __name__ == "__main__":
    main()
