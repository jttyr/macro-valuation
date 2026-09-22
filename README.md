# Macro Valuation

Valuación relativa de 5 activos macro — **PETROLEOS (WTI), DXY, US02Y, US10Y,
US30Y** — que dice qué tan **sobrevaluado / subvaluado** cotiza hoy cada uno
frente a su propio rango reciente en tres ventanas: **semanal (W)**,
**mensual (M)** y **trimestral (Q)**. Por ventana entrega **promedio, máximo y
mínimo**, además de la posición actual dentro de ese rango.

Genera una tarjeta PNG por activo, en el mismo lenguaje visual que GEX /
Market Drivers (fondo negro, mono, acento morado), lista para el dashboard.

## Uso

```bash
python run.py            # genera las 5 tarjetas en output/
python run.py --keep 8   # conserva solo las 8 más recientes por activo
python valuation.py      # solo los números en consola, sin renderizar
```

Usa el Python 3.12 del framework (el mismo que corre `gex_drivers`, ya tiene
plotly + kaleido + yfinance):

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 run.py
```

## Cómo se calcula

Para cada ventana (W=5, M=21, Q=63 sesiones de bolsa) sobre el cierre diario:

- **Promedio / Máximo / Mínimo** de la ventana.
- **Posición en rango** `= (actual − mín) / (máx − mín)` → 0 % en el mínimo,
  100 % en el máximo. Es el criterio principal de valuación.
- **Desviación** `= (actual − promedio) / promedio` en %.
- **Z-score** `= (actual − promedio) / desviación estándar`, para reforzar
  extremos estadísticos.

Etiquetas: `SUBVALUADO` (≤20 % o z≤−1.5) · `BARATO` (≤38 %) · `NEUTRAL` ·
`CARO` (≥62 %) · `SOBREVALUADO` (≥80 % o z≥+1.5). La valuación **global** es el
promedio de las tres ventanas.

> **Tasas (2Y/10Y/30Y):** aquí "sobrevaluado" = el *nivel* del activo está
> arriba de su rango. En un rendimiento eso significa **tasa alta**, lo
> contrario a un bono caro. La métrica describe el nivel del activo, no el
> precio del bono.

## Datos (Yahoo Finance)

| Activo | Ticker | Fallback |
|--------|--------|----------|
| PETROLEOS | `CL=F` | `BZ=F` |
| DXY | `DX-Y.NYB` | — |
| US02Y | `2YY=F` | `^IRX` |
| US10Y | `^TNX` | — |
| US30Y | `^TYX` | — |

## Integración con el dashboard

`market-dashboard/app.py` ya trae la fuente `valuation` apuntando a este
`output/` y las 5 pestañas macro. Cada activo solo pinta las columnas donde
tiene tarjeta, así el macro se ve centrado (una sola columna) y ES/NQ siguen
con sus dos. Basta con que `run.py` deje tarjetas frescas en `output/`.

Para refrescarlas en automático, agrega `python run.py` al mismo scheduler que
ya usas para GEX (cron-job.org + GitHub Actions).
