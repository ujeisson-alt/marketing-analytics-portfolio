"""
ETL: unifica las tres exportaciones (Google, Meta, TikTok) en una sola tabla limpia
y genera un reporte de calidad de datos con controles automáticos.

Salida:
  data/processed/campanas_unificado.csv
  data/processed/campanas.db           (SQLite, para las consultas SQL)
  outputs/reporte_calidad_datos.md
"""
from pathlib import Path
import sqlite3
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
RAW, PROC, OUT = RAIZ / "data" / "raw", RAIZ / "data" / "processed", RAIZ / "outputs"
PROC.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

COLUMNAS = ["fecha", "plataforma", "campana", "spend", "impressions", "clicks", "conversions", "revenue"]
log = []

# ---------- Google Ads ----------
g = pd.read_csv(RAW / "google_ads_export.csv")
log.append(f"Google Ads: {len(g)} filas leídas; columna Cost convertida de texto '1.234.567' a número")
g = pd.DataFrame({
    "fecha": pd.to_datetime(g["Day"], format="%Y-%m-%d"),
    "plataforma": "Google Ads",
    "campana": g["Campaign"],
    "spend": g["Cost"].astype(str).str.replace(".", "", regex=False).astype(float),
    "impressions": g["Impr."], "clicks": g["Clicks"],
    "conversions": g["Conversions"], "revenue": g["Conv. value"],
})

# ---------- Meta Ads ----------
m = pd.read_csv(RAW / "meta_ads_export.csv")
dup = m.duplicated().sum()
m = m.drop_duplicates()
log.append(f"Meta Ads: {len(m) + dup} filas leídas; {dup} filas duplicadas eliminadas")
m = pd.DataFrame({
    "fecha": pd.to_datetime(m["Reporting starts"], format="%Y-%m-%d"),
    "plataforma": "Meta Ads",
    "campana": m["Campaign name"],
    "spend": m["Amount spent (COP)"], "impressions": m["Impressions"], "clicks": m["Link clicks"],
    "conversions": m["Purchases"], "revenue": m["Purchases conversion value"],
})

# ---------- TikTok Ads ----------
t = pd.read_csv(RAW / "tiktok_ads_export.csv")
t = pd.DataFrame({
    "fecha": pd.to_datetime(t["By Day"], format="%Y/%m/%d"),
    "plataforma": "TikTok Ads",
    "campana": t["Campaign name"],
    "spend": t["Cost"], "impressions": t["Impression"], "clicks": t["Clicks (Destination)"],
    "conversions": t["Complete Payment"], "revenue": t["Total Complete Payment Value"],
})
nulos = t["conversions"].isna().sum()
# Imputación: conversiones = ingresos del día / ticket promedio de la campaña (calculado sin los nulos)
ticket = (t.dropna().groupby("campana").revenue.sum() / t.dropna().groupby("campana").conversions.sum())
faltan = t["conversions"].isna()
t.loc[faltan, "conversions"] = (t.loc[faltan, "revenue"] / t.loc[faltan, "campana"].map(ticket)).round()
log.append(f"TikTok Ads: {len(t)} filas leídas; fecha AAAA/MM/DD estandarizada; "
           f"{nulos} conversiones vacías imputadas con ingresos / ticket promedio de la campaña")

df = pd.concat([g, m, t], ignore_index=True)[COLUMNAS]
df[["impressions", "clicks", "conversions"]] = df[["impressions", "clicks", "conversions"]].astype(int)

# ---------- Controles de calidad (fallan el proceso si algo no cuadra) ----------
controles = {
    "Sin fechas fuera de ene-jun 2026": df.fecha.between("2026-01-01", "2026-06-30").all(),
    "Sin gasto negativo": (df.spend >= 0).all(),
    "Clics <= impresiones": (df.clicks <= df.impressions).all(),
    "Conversiones <= clics": (df.conversions <= df.clicks).all(),
    "Sin nulos en la tabla final": df.notna().all().all(),
    "Una fila por fecha y campaña": not df.duplicated(["fecha", "campana"]).any(),
    "181 días x 8 campañas = 1.448 filas": len(df) == 181 * 8,
}
for nombre, ok in controles.items():
    assert ok, f"Control de calidad fallido: {nombre}"

objetivo = {"GA_Search_Marca": "Conversiones", "GA_Search_Genericas": "Conversiones", "GA_PMax_Catalogo": "Ventas",
            "META_Prospecting_Lookalike": "Ventas", "META_Retargeting_Carrito": "Ventas",
            "META_AdvantagePlus_Shopping": "Ventas", "TT_Awareness_UGC": "Alcance", "TT_Conversiones_Spark": "Conversiones"}
df.insert(3, "objetivo", df.campana.map(objetivo))
df = df.sort_values(["fecha", "plataforma", "campana"])
df.to_csv(PROC / "campanas_unificado.csv", index=False, date_format="%Y-%m-%d")

with sqlite3.connect(PROC / "campanas.db") as con:
    df.assign(fecha=df.fecha.dt.strftime("%Y-%m-%d")).to_sql("campanas", con, if_exists="replace", index=False)

with open(OUT / "reporte_calidad_datos.md", "w", encoding="utf-8") as f:
    f.write("# Reporte de calidad de datos\n\n## Transformaciones\n\n")
    f.writelines(f"- {linea}\n" for linea in log)
    f.write("\n## Controles automáticos\n\n| Control | Resultado |\n|---|---|\n")
    f.writelines(f"| {n} | {'✅ OK' if ok else '❌ Falla'} |\n" for n, ok in controles.items())
    f.write(f"\nTabla final: **{len(df):,} filas**, {df.campana.nunique()} campañas, 3 plataformas.\n")

print("\n".join(log))
print(f"ETL OK -> {len(df)} filas")
