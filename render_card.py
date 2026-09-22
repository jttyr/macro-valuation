"""Render de la tarjeta de valuacion (PNG). Banner ancho horizontal,
principalmente blanco y negro: el color (un morado sobrio) se usa SOLO para
marcar el precio actual. Sin categorias ni veredictos -- solo datos, para que
el usuario interprete.

Estructura:
  - Izquierda: identidad + precio actual centrado.
  - Derecha: tabla por periodo (SEMANAL / MENSUAL / TRIMESTRAL) con minimo,
    promedio, maximo y una barra simple de posicion del precio en el rango.
  - Fila HISTORICO: solo maximo y minimo historicos con su fecha, sin barra.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import plotly.graph_objects as go

from valuation import AssetValuation

# --- Paleta blanco / negro, morado solo de marcador -----------------------
COLORS = {
    "bg": "#000000",
    "white": "#f4f4f6",
    "soft": "#c8c8ce",
    "muted": "#7d7d86",
    "dim": "#4a4a52",
    "dim2": "#2c2c32",
    "hair": "#1d1d22",       # separadores / hairlines
    "track": "#232329",      # riel de la barra
    "fill": "#42424a",       # tramo min -> actual
    "mark": "#9d78d6",       # morado: marcador de precio actual (unico color)
}

# Misma fuente que la terminal (Share Tech Mono). Debe estar instalada en el
# sistema para que kaleido/Chromium la use: ~/Library/Fonts/ShareTechMono-Regular.ttf
FONT = "Share Tech Mono, DejaVu Sans Mono, monospace"

# Banner ancho ~3.5:1. Se exporta con scale=2 -> 4400x1264.
W, H = 2200, 632

_MES = ["", "ene", "feb", "mar", "abr", "may", "jun",
        "jul", "ago", "sep", "oct", "nov", "dic"]


def _fmt(v: float, decimals: int, unit: str) -> str:
    if v != v:
        return "--"
    return f"{v:,.{decimals}f}" + ("%" if unit == "%" else "")


def _fmt_date(d) -> str:
    return f"{_MES[d.month]} {d.year}" if d else ""


def _rect(fig, x0, y0, x1, y1, fill, line=None, width=0, layer="below"):
    fig.add_shape(type="rect", xref="paper", yref="paper", x0=x0, y0=y0, x1=x1, y1=y1,
                  fillcolor=fill, line=dict(color=line or fill, width=width), layer=layer)


def _line(fig, x0, y0, x1, y1, color, width=1, layer="above"):
    fig.add_shape(type="line", xref="paper", yref="paper", x0=x0, y0=y0, x1=x1, y1=y1,
                  line=dict(color=color, width=width), layer=layer)


def _text(fig, x, y, s, size, color=None, xanchor="left", yanchor="middle"):
    fig.add_annotation(xref="paper", yref="paper", x=x, y=y, text=s, showarrow=False,
                       xanchor=xanchor, yanchor=yanchor,
                       font=dict(family=FONT, size=size, color=color or COLORS["white"]))


def _dot(fig, cx, cy, r_px, fill, line=None, lw=0):
    """Circulo redondo de radio r_px, corrigiendo el aspecto del lienzo."""
    hw = r_px / W
    hh = r_px / H
    fig.add_shape(type="circle", xref="paper", yref="paper",
                  x0=cx - hw, y0=cy - hh, x1=cx + hw, y1=cy + hh,
                  fillcolor=fill, line=dict(color=line or fill, width=lw), layer="above")


def _bar(fig, bx0, bx1, cy, pos, avg_pos=None):
    """Barra tipo lollipop: linea base tenue de min(izq) a max(der); el tramo
    recorrido (min -> actual) mas claro; punto redondo morado en el precio
    actual y un tick fino para el promedio. Limpia y facil de leer."""
    span = bx1 - bx0
    cx = bx0 + span * (max(0, min(100, pos)) / 100.0)
    # linea base (todo el rango)
    _line(fig, bx0, cy, bx1, cy, COLORS["track"], 2)
    # topes finos en min y max
    _line(fig, bx0, cy - 0.024, bx0, cy + 0.024, COLORS["dim"], 1.4)
    _line(fig, bx1, cy - 0.024, bx1, cy + 0.024, COLORS["dim"], 1.4)
    # tramo recorrido min -> actual
    _line(fig, bx0, cy, cx, cy, COLORS["soft"], 2)
    # tick del promedio
    if avg_pos is not None:
        ax = bx0 + span * (max(0, min(100, avg_pos)) / 100.0)
        _line(fig, ax, cy - 0.020, ax, cy + 0.020, COLORS["muted"], 1.2)
    # marcador del precio actual: ovalo vertical (unico color)
    hw, hh = 5.5 / W, 17.0 / H
    fig.add_shape(type="circle", xref="paper", yref="paper",
                  x0=cx - hw, y0=cy - hh, x1=cx + hw, y1=cy + hh,
                  fillcolor=COLORS["mark"], line=dict(color=COLORS["bg"], width=1.5),
                  layer="above")


def render(av: AssetValuation, out_dir: Path) -> Path:
    fig = go.Figure()
    fig.update_layout(width=W, height=H, paper_bgcolor=COLORS["bg"],
                      plot_bgcolor=COLORS["bg"], margin=dict(l=0, r=0, t=0, b=0),
                      showlegend=False, font=dict(family=FONT, color=COLORS["white"]),
                      xaxis=dict(visible=False, range=[0, 1], fixedrange=True),
                      yaxis=dict(visible=False, range=[0, 1], fixedrange=True))
    _rect(fig, 0, 0, 1, 1, COLORS["bg"])
    d, u = av.decimals, av.unit

    # ================= Izquierda: precio actual (centrado) =================
    # Sin bloque de identidad: la terminal ya rotula el activo (tab + titulo)
    # justo arriba de la tarjeta.
    lcx = 0.165   # centro del bloque izquierdo
    _text(fig, lcx, 0.60, "PRECIO ACTUAL", 12, COLORS["dim"], xanchor="center")
    _text(fig, lcx, 0.465, _fmt(av.current, d, u), 64, COLORS["white"], xanchor="center")
    arrow = "▲" if av.change_1d_pct >= 0 else "▼"
    _text(fig, lcx, 0.325, f"{arrow}  {av.change_1d_pct:+.2f}%  hoy", 15,
          COLORS["soft"], xanchor="center")

    _line(fig, 0.315, 0.10, 0.315, 0.90, COLORS["hair"], 1)

    # ================= Derecha: tabla por periodo =================
    px0 = 0.35
    # bordes derechos de cada columna numerica, barra y columna de variacion
    cMin, cAvg, cMax = 0.545, 0.645, 0.745
    bx0, bx1 = 0.775, 0.885
    cChg = 0.985   # variacion % del precio en el periodo (der)

    # encabezados
    hy = 0.885
    _text(fig, px0, hy, "PERIODO", 11, COLORS["dim"])
    _text(fig, cMin, hy, "MINIMO", 11, COLORS["dim"], xanchor="right")
    _text(fig, cAvg, hy, "PROMEDIO", 11, COLORS["dim"], xanchor="right")
    _text(fig, cMax, hy, "MAXIMO", 11, COLORS["dim"], xanchor="right")
    _text(fig, (bx0 + bx1) / 2, hy, "POSICION", 11, COLORS["dim"], xanchor="center")
    _text(fig, cChg, hy, "CAMBIO", 11, COLORS["dim"], xanchor="right")
    _line(fig, px0, 0.845, 0.985, 0.845, COLORS["hair"], 1)

    # filas de ventanas (semanal arriba -> trimestral)
    order = {w.code: w for w in av.windows}
    rows = []
    for code, name, sub in [("W", "SEMANAL", "5 sesiones"),
                            ("M", "MENSUAL", "21 sesiones"),
                            ("Q", "TRIMESTRAL", "63 sesiones")]:
        w = order.get(code)
        if w:
            rows.append((name, sub, w))

    top_b, bot_b = 0.82, 0.235
    step = (top_b - bot_b) / len(rows)
    for i, (name, sub, w) in enumerate(rows):
        cy = top_b - step * (i + 0.5)
        _text(fig, px0, cy + 0.028, name, 15, COLORS["white"])
        _text(fig, px0, cy - 0.038, sub, 10.5, COLORS["dim"])
        _text(fig, cMin, cy, _fmt(w.low, d, u), 16, COLORS["soft"], xanchor="right")
        _text(fig, cAvg, cy, _fmt(w.avg, d, u), 16, COLORS["white"], xanchor="right")
        _text(fig, cMax, cy, _fmt(w.high, d, u), 16, COLORS["soft"], xanchor="right")
        avg_pos = (w.avg - w.low) / (w.high - w.low) * 100 if w.high > w.low else 50
        _bar(fig, bx0, bx1, cy, w.range_pos, avg_pos=avg_pos)
        _text(fig, cChg, cy, f"{w.chg_period:+.2f}%", 16,
              COLORS["white"] if w.chg_period >= 0 else COLORS["soft"], xanchor="right")
        if i < len(rows):
            _line(fig, px0, top_b - step * (i + 1), 0.985, top_b - step * (i + 1),
                  COLORS["hair"], 1)

    # ================= Fila HISTORICO (solo datos, sin barra) =================
    hcy = 0.155
    _text(fig, px0, hcy + 0.030, "HISTORICO", 15, COLORS["white"])
    _text(fig, px0, hcy - 0.036,
          f"desde {av.history_from.year if av.history_from else ''}", 10.5, COLORS["dim"])
    # minimo historico
    _text(fig, cMin, hcy + 0.020, _fmt(av.atl, d, u), 16, COLORS["soft"], xanchor="right")
    _text(fig, cMin, hcy - 0.036, _fmt_date(av.atl_date), 10.5, COLORS["dim"], xanchor="right")
    # promedio no aplica
    _text(fig, cAvg, hcy, "—", 15, COLORS["dim"], xanchor="right")
    # maximo historico
    _text(fig, cMax, hcy + 0.020, _fmt(av.ath, d, u), 16, COLORS["soft"], xanchor="right")
    _text(fig, cMax, hcy - 0.036, _fmt_date(av.ath_date), 10.5, COLORS["dim"], xanchor="right")
    # variacion desde el inicio del historico
    _text(fig, cChg, hcy, f"{av.at_chg:+.2f}%", 16,
          COLORS["white"] if av.at_chg >= 0 else COLORS["soft"], xanchor="right")

    # ================= Footer =================
    stamp = av.asof.strftime("%d/%m/%Y %H:%M")
    _text(fig, 0.044, 0.045, "el marcador morado indica el precio actual dentro del rango",
          10.5, COLORS["dim"])
    _text(fig, 0.985, 0.045, f"actualizado {stamp}", 10.5, COLORS["dim2"], xanchor="right")

    out_dir.mkdir(parents=True, exist_ok=True)
    ts = av.asof.strftime("%Y%m%d_%H%M")
    path = out_dir / f"val_{av.key}_{ts}.png"
    fig.write_image(str(path), scale=2)
    return path
