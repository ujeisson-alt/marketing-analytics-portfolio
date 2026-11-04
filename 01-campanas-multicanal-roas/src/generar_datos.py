"""
Genera exportaciones SIMULADAS de Google Ads, Meta Ads y TikTok Ads (ene-jun 2026)
para la empresa ficticia "Kumbre Store" (e-commerce de moda y hogar, Colombia).

Cada plataforma exporta con su propio formato de columnas (como en la vida real)
e incluye problemas típicos de calidad de datos que el ETL debe resolver:
  - Google Ads: costos como texto con separador de miles colombiano ("1.234.567")
  - Meta Ads: filas duplicadas
  - TikTok Ads: conversiones vacías (nulos) y fechas en formato AAAA/MM/DD

La respuesta de las ventas a la inversión tiene rendimientos decrecientes
(ingresos = k * inversión^b, b < 1), así se puede estimar la curva y optimizar presupuesto.
"""
from pathlib import Path
import numpy as np
import pandas as pd

SEMILLA = 2026
rng = np.random.default_rng(SEMILLA)
RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "data" / "raw"
SALIDA.mkdir(parents=True, exist_ok=True)

FECHAS = pd.date_range("2026-01-01", "2026-06-30", freq="D")

# plataforma, campaña, objetivo, presupuesto diario base (COP), CPM, CTR, elasticidad b, ROAS base, ticket promedio
CAMPANAS = [
    ("Google Ads", "GA_Search_Marca",            "Conversiones", 350_000, 25_000, 0.090, 0.55, 9.0, 165_000),
    ("Google Ads", "GA_Search_Genericas",        "Conversiones", 700_000, 30_000, 0.045, 0.80, 3.6, 150_000),
    ("Google Ads", "GA_PMax_Catalogo",           "Ventas",       900_000, 14_000, 0.016, 0.82, 4.4, 140_000),
    ("Meta Ads",   "META_Prospecting_Lookalike", "Ventas",       800_000,  9_000, 0.013, 0.78, 2.4, 135_000),
    ("Meta Ads",   "META_Retargeting_Carrito",   "Ventas",       300_000, 16_000, 0.022, 0.50, 7.5, 145_000),
    ("Meta Ads",   "META_AdvantagePlus_Shopping","Ventas",       750_000, 10_000, 0.015, 0.85, 3.9, 138_000),
    ("TikTok Ads", "TT_Awareness_UGC",           "Alcance",      500_000,  5_000, 0.009, 0.75, 0.9, 120_000),
    ("TikTok Ads", "TT_Conversiones_Spark",      "Conversiones", 450_000,  7_000, 0.012, 0.85, 2.9, 125_000),
]


def estacionalidad(fecha):
    """Multiplicador de demanda: fines de semana, enero lento y temporada Día de la Madre (10 may 2026)."""
    m = 1.0
    if fecha.dayofweek >= 5:
        m *= 1.10
    if fecha.month == 1:
        m *= 0.85
    if pd.Timestamp("2026-04-25") <= fecha <= pd.Timestamp("2026-05-10"):
        m *= 1.45
    return m


filas = []
for plataforma, campana, objetivo, base, cpm, ctr, b, roas, ticket in CAMPANAS:
    k = roas * base ** (1 - b) / ticket                      # calibra la curva para que a "base" el ROAS sea el indicado
    ajuste_mes = {m: rng.uniform(0.6, 1.5) for m in range(1, 7)}  # cambios de presupuesto mes a mes
    for f in FECHAS:
        temporada = estacionalidad(f)
        impulso = 1.3 if pd.Timestamp("2026-04-25") <= f <= pd.Timestamp("2026-05-10") else 1.0
        gasto = base * ajuste_mes[f.month] * impulso * rng.lognormal(0, 0.18)
        impresiones = int(gasto / cpm * 1000 * rng.lognormal(0, 0.08))
        clics = rng.binomial(impresiones, min(ctr * rng.lognormal(0, 0.10), 0.5))
        conv_esperadas = k * gasto ** b * temporada
        conversiones = int(min(rng.poisson(conv_esperadas), clics))
        ingresos = conversiones * ticket * rng.normal(1, 0.12 / np.sqrt(max(conversiones, 1)))
        filas.append(dict(fecha=f, plataforma=plataforma, campana=campana, objetivo=objetivo,
                          gasto=round(gasto), impresiones=impresiones, clics=int(clics),
                          conversiones=conversiones, ingresos=round(max(ingresos, 0))))

df = pd.DataFrame(filas)

# ---------- Google Ads: formato de exportación con costo como texto "1.234.567" ----------
g = df[df.plataforma == "Google Ads"].copy()
google = pd.DataFrame({
    "Day": g.fecha.dt.strftime("%Y-%m-%d"),
    "Campaign": g.campana,
    "Campaign type": np.where(g.campana.str.contains("PMax"), "Performance Max", "Search"),
    "Currency code": "COP",
    "Cost": g.gasto.map(lambda x: f"{x:,.0f}".replace(",", ".")),
    "Impr.": g.impresiones,
    "Clicks": g.clics,
    "Conversions": g.conversiones.astype(float),
    "Conv. value": g.ingresos.astype(float),
})
google.to_csv(SALIDA / "google_ads_export.csv", index=False)

# ---------- Meta Ads: formato Ads Manager + 6 filas duplicadas ----------
m = df[df.plataforma == "Meta Ads"].copy()
meta = pd.DataFrame({
    "Reporting starts": m.fecha.dt.strftime("%Y-%m-%d"),
    "Reporting ends": m.fecha.dt.strftime("%Y-%m-%d"),
    "Campaign name": m.campana,
    "Objective": "OUTCOME_SALES",
    "Amount spent (COP)": m.gasto,
    "Impressions": m.impresiones,
    "Link clicks": m.clics,
    "Purchases": m.conversiones,
    "Purchases conversion value": m.ingresos,
})
meta = pd.concat([meta, meta.sample(6, random_state=SEMILLA)]).sort_values(["Reporting starts", "Campaign name"])
meta.to_csv(SALIDA / "meta_ads_export.csv", index=False)

# ---------- TikTok Ads: fechas AAAA/MM/DD + 4 conversiones vacías ----------
t = df[df.plataforma == "TikTok Ads"].copy()
tiktok = pd.DataFrame({
    "By Day": t.fecha.dt.strftime("%Y/%m/%d"),
    "Campaign name": t.campana,
    "Advertising objective": t.objetivo,
    "Cost": t.gasto.astype(float),
    "Impression": t.impresiones,
    "Clicks (Destination)": t.clics,
    "Complete Payment": t.conversiones.astype("float"),
    "Total Complete Payment Value": t.ingresos.astype(float),
})
idx_nulos = tiktok.sample(4, random_state=SEMILLA).index
tiktok.loc[idx_nulos, "Complete Payment"] = np.nan
tiktok.to_csv(SALIDA / "tiktok_ads_export.csv", index=False)

print(f"Exportaciones generadas en {SALIDA}: Google {len(google)}, Meta {len(meta)}, TikTok {len(tiktok)} filas")
