"""Motor de valuacion relativa para activos macro.

Idea: para cada activo (petroleo, DXY, y las tasas 2Y/10Y/30Y) mide donde
esta cotizando HOY respecto a su propio comportamiento reciente en tres
ventanas -- semanal (W), mensual (M) y trimestral (Q). Por ventana entrega
promedio, maximo y minimo, y a partir de eso califica que tan
"sobrevaluado" o "subvaluado" esta el activo (mas alto/bajo que su rango
estadistico normal).

Nota sobre las tasas: aqui "sobrevaluado" significa simplemente que el
NIVEL del activo esta arriba de su rango reciente. Para un rendimiento
(2Y/10Y/30Y) eso quiere decir tasa alta -- que es lo contrario a un bono
caro. La metrica describe el nivel del activo tal cual, no el precio del
bono subyacente.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yfinance as yf

# --- Definicion de activos -------------------------------------------------
# ticker: simbolo primario en Yahoo. fallback: alterno si el primario falla.
# unit: "price" o "%" -- solo cambia como se formatea el numero en la tarjeta.
# front_root: para petroleo NO se usa el continuo de Yahoo (CL=F/BZ=F) porque
# BZ=F apunta a un contrato "Last Day Financial" ~$5 abajo del front-month que
# cotizan Investing/brokers. En su lugar se resuelve el contrato front-month
# real (p.ej. BZX26.NYM = Brent Nov 2026) de forma dinamica, para que ademas
# ruede solo cada mes. Si falla, cae al continuo (ticker).
ASSETS = [
    {"key": "OIL",   "label": "WTI",       "name": "Crudo WTI (front-month)", "ticker": "CL=F",     "fallback": None,    "front_root": "CL", "unit": "price", "decimals": 2},
    {"key": "BRENT", "label": "BRENT",     "name": "Crudo Brent (front-month)", "ticker": "BZ=F",   "fallback": None,    "front_root": "BZ", "unit": "price", "decimals": 2},
    {"key": "DXY",   "label": "DXY",       "name": "US Dollar Index",         "ticker": "DX-Y.NYB", "fallback": None,    "unit": "price", "decimals": 3},
    {"key": "US02Y", "label": "US02Y",     "name": "Rendimiento Tesoro 2A",   "ticker": "2YY=F",    "fallback": "^IRX",  "unit": "%",     "decimals": 3},
    {"key": "US10Y", "label": "US10Y",     "name": "Rendimiento Tesoro 10A",  "ticker": "^TNX",     "fallback": None,    "unit": "%",     "decimals": 3},
    {"key": "US30Y", "label": "US30Y",     "name": "Rendimiento Tesoro 30A",  "ticker": "^TYX",     "fallback": None,    "unit": "%",     "decimals": 3},
]

# Ventanas en dias HABILES de bolsa (no calendario).
WINDOWS = [
    ("W", "SEMANAL",    5),
    ("M", "MENSUAL",    21),
    ("Q", "TRIMESTRAL", 63),
]

# Umbrales de posicion dentro del rango [min, max] de la ventana (0=min, 100=max).
# La posicion es el criterio principal; el z-score se usa para reforzar los extremos.
def classify(range_pos: float, z: float) -> tuple[str, str]:
    """Devuelve (etiqueta, sesgo) donde sesgo in {'over','under','neutral'}."""
    if range_pos >= 80 or z >= 1.5:
        return "SOBREVALUADO", "over"
    if range_pos >= 62:
        return "CARO", "over"
    if range_pos <= 20 or z <= -1.5:
        return "SUBVALUADO", "under"
    if range_pos <= 38:
        return "BARATO", "under"
    return "NEUTRAL", "neutral"


@dataclass
class WindowStat:
    code: str
    name: str
    n: int
    avg: float
    high: float
    low: float
    std: float
    dev_pct: float      # (actual - promedio) / promedio * 100
    range_pos: float    # 0..100 dentro de [low, high]
    z: float            # (actual - promedio) / std
    chg_period: float   # variacion vs el inicio del periodo (hace n sesiones)
    label: str
    bias: str


@dataclass
class AssetValuation:
    key: str
    label: str
    name: str
    ticker: str
    unit: str
    decimals: int
    current: float
    change_1d_pct: float
    asof: dt.datetime
    windows: list[WindowStat] = field(default_factory=list)
    series_dates: list = field(default_factory=list)   # ultimas ~63 fechas
    series_close: list = field(default_factory=list)
    overall_label: str = "NEUTRAL"
    overall_bias: str = "neutral"
    overall_pos: float = 50.0
    # extremos historicos (toda la serie disponible en Yahoo)
    ath: float = float("nan")
    ath_date: dt.date | None = None
    atl: float = float("nan")
    atl_date: dt.date | None = None
    at_pos: float = 50.0            # posicion actual dentro del rango historico
    at_chg: float = 0.0             # variacion vs el inicio del historico
    history_from: dt.date | None = None
    error: str | None = None


# El "historico" se mide desde aqui (el usuario lo quiere acotado, no toda la
# serie de decadas). Extremos y posicion historica se calculan solo con esto.
HISTORY_START = "2021-01-01"


def _download(ticker: str, period: str = "max"):
    """Descarga OHLC completo. Devuelve el DataFrame con High/Low/Close o None."""
    df = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    if df is None or df.empty:
        return None
    df = df.dropna(subset=["Close"])
    return df if len(df) else None


# Codigos de mes de futuros (ene..dic).
_FUT_MONTH_CODES = "FGHJKMNQUVXZ"


def resolve_front_month(root: str, fallback: str) -> str:
    """Devuelve el ticker del contrato front-month para 'root' (p.ej. 'BZ'/'CL')
    -- el mas cercano que SIGUE cotizando hoy. Prueba los proximos meses y elige,
    entre los que operaron en la ultima fecha disponible, el de vencimiento mas
    proximo. Si no logra resolver, cae a 'fallback' (el continuo)."""
    today = dt.date.today()
    candidates = []          # (ticker, ultima_fecha, (anio, mes))
    latest = None
    for i in range(0, 7):    # este mes y los proximos 6
        m = (today.month - 1 + i) % 12 + 1
        y = today.year + (today.month - 1 + i) // 12
        tk = f"{root}{_FUT_MONTH_CODES[m - 1]}{y % 100:02d}.NYM"
        try:
            h = yf.Ticker(tk).history(period="5d")
        except Exception:
            continue
        if h is None or h.empty:
            continue
        last = h.index[-1].date()
        candidates.append((tk, last, (y, m)))
        if latest is None or last > latest:
            latest = last
    if not candidates:
        return fallback
    # entre los que operaron en la ultima fecha global (activos), el mes mas cercano
    active = [c for c in candidates if c[1] == latest]
    active.sort(key=lambda c: c[2])
    return active[0][0] if active else fallback


def compute_asset(spec: dict) -> AssetValuation:
    primary = spec["ticker"]
    if spec.get("front_root"):
        primary = resolve_front_month(spec["front_root"], spec["ticker"])

    df = _download(primary)
    used_ticker = primary
    if df is None and spec.get("fallback"):
        df = _download(spec["fallback"])
        used_ticker = spec["fallback"]
    if df is None and primary != spec["ticker"]:   # el front fallo -> continuo
        df = _download(spec["ticker"])
        used_ticker = spec["ticker"]

    if df is None or len(df) < 6:
        return AssetValuation(
            key=spec["key"], label=spec["label"], name=spec["name"],
            ticker=used_ticker, unit=spec["unit"], decimals=spec["decimals"],
            current=float("nan"), change_1d_pct=float("nan"),
            asof=dt.datetime.now(), error="sin datos suficientes",
        )

    close = df["Close"]
    vals = close.values.astype(float)

    # --- Extremos historicos, acotados a HISTORY_START (usa High/Low reales) ---
    start = pd.Timestamp(HISTORY_START, tz=df.index.tz) if df.index.tz else pd.Timestamp(HISTORY_START)
    hist = df[df.index >= start]
    if len(hist) < 2:            # serie mas corta que la ventana pedida
        hist = df
    high_col = (hist["High"].dropna() if "High" in hist else hist["Close"])
    low_col = (hist["Low"].dropna() if "Low" in hist else hist["Close"])
    high_col = high_col[high_col > 0]
    low_col = low_col[low_col > 0]
    ath = float(high_col.max()); ath_date = high_col.idxmax().date()
    atl = float(low_col.min()); atl_date = low_col.idxmin().date()
    history_from = hist.index[0].date()
    current = float(vals[-1])
    prev = float(vals[-2]) if len(vals) >= 2 else current
    change_1d = (current - prev) / prev * 100 if prev else 0.0

    windows: list[WindowStat] = []
    pos_accum = []
    z_accum = []
    for code, name, n in WINDOWS:
        w = vals[-n:] if len(vals) >= n else vals
        avg = float(np.mean(w))
        hi = float(np.max(w))
        lo = float(np.min(w))
        std = float(np.std(w, ddof=1)) if len(w) > 1 else 0.0
        dev_pct = (current - avg) / avg * 100 if avg else 0.0
        rng = hi - lo
        range_pos = (current - lo) / rng * 100 if rng > 0 else 50.0
        range_pos = max(0.0, min(100.0, range_pos))
        z = (current - avg) / std if std > 0 else 0.0
        first = float(w[0])
        chg_period = (current - first) / first * 100 if first else 0.0
        label, bias = classify(range_pos, z)
        windows.append(WindowStat(code, name, len(w), avg, hi, lo, std,
                                   dev_pct, range_pos, z, chg_period, label, bias))
        pos_accum.append(range_pos)
        z_accum.append(z)

    overall_pos = float(np.mean(pos_accum))
    overall_z = float(np.mean(z_accum))
    overall_label, overall_bias = classify(overall_pos, overall_z)

    at_rng = ath - atl
    at_pos = (current - atl) / at_rng * 100 if at_rng > 0 else 50.0
    at_pos = max(0.0, min(100.0, at_pos))
    hist_first = float(hist["Close"].iloc[0])
    at_chg = (current - hist_first) / hist_first * 100 if hist_first else 0.0

    tail = close.tail(63)
    return AssetValuation(
        key=spec["key"], label=spec["label"], name=spec["name"],
        ticker=used_ticker, unit=spec["unit"], decimals=spec["decimals"],
        current=current, change_1d_pct=change_1d, asof=dt.datetime.now(),
        windows=windows,
        series_dates=[d.to_pydatetime() for d in tail.index],
        series_close=[float(v) for v in tail.values],
        overall_label=overall_label, overall_bias=overall_bias,
        overall_pos=overall_pos,
        ath=ath, ath_date=ath_date, atl=atl, atl_date=atl_date,
        at_pos=at_pos, at_chg=at_chg, history_from=history_from,
    )


def compute_all() -> list[AssetValuation]:
    return [compute_asset(s) for s in ASSETS]


if __name__ == "__main__":
    for av in compute_all():
        if av.error:
            print(f"{av.label:10} ERROR {av.error}")
            continue
        print(f"\n{av.label:10} {av.name}  ({av.ticker})  actual={av.current:.{av.decimals}f}  {av.change_1d_pct:+.2f}%  => {av.overall_label}")
        print(f"   ATH={av.ath:.{av.decimals}f} ({av.ath_date})  ATL={av.atl:.{av.decimals}f} ({av.atl_date})  pos.hist={av.at_pos:.1f}%  desde {av.history_from}")
        for w in av.windows:
            print(f"   {w.name:11} avg={w.avg:.{av.decimals}f}  hi={w.high:.{av.decimals}f}  lo={w.low:.{av.decimals}f}  pos={w.range_pos:5.1f}%  dev={w.dev_pct:+6.2f}%  z={w.z:+.2f}  {w.label}")
