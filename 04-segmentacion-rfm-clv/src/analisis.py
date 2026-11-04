"""
Segmentación RFM, retención por cohortes y valor del cliente (CLV) vs. costo de adquisición (CAC).

R (Recencia)   = días desde la última compra a la fecha de corte (30-jun-2026)  -> quintiles (5 = más reciente)
F (Frecuencia) = número de pedidos -> regla de negocio (el 74 % compra una sola vez, los quintiles no sirven):
                 1 pedido = 1 · 2 = 2 · 3 = 3 · 4-5 = 4 · 6 o más = 5
M (Monto)      = ventas netas acumuladas -> quintiles
"""
from pathlib import Path
import json
import re
import sqlite3
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter, FuncFormatter
from matplotlib.colors import LinearSegmentedColormap

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ.parent))
from estilo import aplicar_estilo, guardar, cop, AZUL, GRIS, NARANJA, TEXTO, TEXTO_2, FONDO  # noqa: E402

OUT = RAIZ / "outputs"
OUT.mkdir(exist_ok=True)
aplicar_estilo()

ped = pd.read_csv(RAIZ / "data" / "pedidos.csv")
cli = pd.read_csv(RAIZ / "data" / "clientes.csv")
con = sqlite3.connect(":memory:")
ped.to_sql("pedidos", con, index=False)
cli.to_sql("clientes", con, index=False)
res = {}
for nombre, q in re.findall(r"-- name: (\w+)\n(.*?);", (RAIZ / "sql" / "rfm_cohortes.sql").read_text(encoding="utf-8"), re.S):
    res[nombre] = pd.read_sql_query(q, con)
    res[nombre].to_csv(OUT / f"sql_{nombre}.csv", index=False)

# ---------------------------------------------------------------- RFM
rfm = res["rfm_base"].merge(cli[["customer_id", "acquisition_channel", "city"]], on="customer_id")
rfm["R"] = pd.qcut(rfm.recencia_dias.rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
rfm["F"] = pd.cut(rfm.frecuencia, [0, 1, 2, 3, 5, np.inf], labels=[1, 2, 3, 4, 5]).astype(int)
rfm["M"] = pd.qcut(rfm.monto.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
rfm["RFM"] = rfm.R.astype(str) + rfm.F.astype(str) + rfm.M.astype(str)

MAPA = [  # (patrón R+F, segmento) — mapa clásico de segmentos RFM
    (r"5[4-5]", "Campeones"), (r"[3-4][4-5]", "Leales"), (r"[4-5][2-3]", "Potenciales leales"),
    (r"51", "Nuevos"), (r"41", "Prometedores"), (r"33", "Necesitan atención"),
    (r"3[1-2]", "A punto de dormir"), (r"[1-2]5", "No se pueden perder"),
    (r"[1-2][3-4]", "En riesgo"), (r"[1-2][1-2]", "Hibernando"),
]


def segmento(rf):
    return next(s for patron, s in MAPA if re.fullmatch(patron, rf))


rfm["segmento"] = (rfm.R.astype(str) + rfm.F.astype(str)).map(segmento)

ACCION = {
    "Campeones": ("Programa VIP, acceso anticipado a colecciones, pedir reseñas y referidos", "Email + WhatsApp"),
    "Leales": ("Venta cruzada (moda → hogar), puntos de fidelidad", "Email"),
    "Potenciales leales": ("Incentivo para la 3.ª compra, recomendaciones personalizadas", "Email + Meta (audiencia personalizada)"),
    "Nuevos": ("Secuencia de bienvenida, guía de tallas, cupón para la 2.ª compra en 30 días", "Email automatizado"),
    "Prometedores": ("Recordar novedades de la categoría que compraron", "Email + retargeting"),
    "Necesitan atención": ("Oferta por tiempo limitado, encuesta de satisfacción", "Email"),
    "A punto de dormir": ("Contenido de valor y descuento moderado antes de que se pierdan", "Email + Meta"),
    "No se pueden perder": ("Contacto 1 a 1, oferta exclusiva de recuperación", "WhatsApp / llamada"),
    "En riesgo": ("Campaña de reactivación \"te extrañamos\" con beneficio fuerte", "Email + Meta"),
    "Hibernando": ("Solo campañas de temporada de bajo costo; excluir de pauta paga", "Email masivo"),
}
seg = (rfm.groupby("segmento")
       .agg(clientes=("customer_id", "size"), ventas=("monto", "sum"), margen=("margen", "sum"),
            recencia_prom=("recencia_dias", "mean"), frecuencia_prom=("frecuencia", "mean"))
       .assign(pct_clientes=lambda d: 100 * d.clientes / d.clientes.sum(),
               pct_ventas=lambda d: 100 * d.ventas / d.ventas.sum(),
               ticket_prom=lambda d: d.ventas / (d.frecuencia_prom * d.clientes))
       .sort_values("ventas", ascending=False))
seg["accion"] = seg.index.map(lambda s: ACCION[s][0])
seg["canal_sugerido"] = seg.index.map(lambda s: ACCION[s][1])
seg.round(1).to_csv(OUT / "segmentos_rfm.csv")
rfm.to_csv(OUT / "clientes_rfm_scores.csv", index=False)  # lista accionable para cargar en el CRM

# ---------------------------------------------------------------- CLV vs CAC
# CAC: el de los canales pagos se aproxima con el CPA del Proyecto 1; orgánico y referidos son supuestos.
CAC = {"Google Ads": 29_440, "Meta Ads": 35_530, "TikTok Ads": 66_609, "Orgánico / SEO": 12_000, "Referidos": 20_000}
clv = res["valor_por_canal_adquisicion"].set_index("canal")
clv["cac"] = clv.index.map(CAC)
clv["clv_cac"] = clv.margen_12m_por_cliente / clv.cac
clv = clv.sort_values("clv_cac", ascending=False)
clv.round(2).to_csv(OUT / "clv_vs_cac_por_canal.csv")

# ---------------------------------------------------------------- Cohortes
coh = res["retencion_cohortes"].pivot(index="cohorte", columns="mes_k", values="retencion_pct")
coh_meses = coh.loc[:, 1:12].dropna(how="all")  # la cohorte de jun-2026 aún no tiene meses posteriores
ret_m1 = coh[1].dropna().mean()
ret_m3 = coh_meses.loc[:, 1:3].dropna().sum(axis=1).mean()  # promedio de % que recompra en meses 1-3 (aprox.)
# Tasa de recompra a 90 días calculada exactamente por cliente
primera = ped.groupby("customer_id").order_date.min().rename("f0")
p2 = ped.merge(primera, on="customer_id")
p2["dias"] = (pd.to_datetime(p2.order_date) - pd.to_datetime(p2.f0)).dt.days
elegibles = primera[pd.to_datetime(primera) <= pd.Timestamp("2026-04-01")].index
recompra_90 = 100 * p2[(p2.customer_id.isin(elegibles)) & p2.dias.between(1, 90)].customer_id.nunique() / len(elegibles)

# ---------------------------------------------------------------- Gráficos
s = seg.sort_values("pct_ventas")
y = np.arange(len(s))
fig, ax = plt.subplots(figsize=(9.5, 5.2))
ax.barh(y + 0.2, s.pct_clientes, height=0.38, color=GRIS, label="% de clientes")
ax.barh(y - 0.2, s.pct_ventas, height=0.38, color=AZUL, label="% de ventas")
for yi, (pc, pv) in zip(y, zip(s.pct_clientes, s.pct_ventas)):
    ax.text(pc + 0.5, yi + 0.2, f"{pc:.1f} %".replace(".", ","), va="center", fontsize=8, color=TEXTO_2)
    ax.text(pv + 0.5, yi - 0.2, f"{pv:.1f} %".replace(".", ","), va="center", fontsize=8, color=TEXTO)
ax.set_yticks(y, s.index)
ax.xaxis.set_major_formatter(PercentFormatter(decimals=0))
ax.set_title("Segmentos RFM: peso en clientes vs. peso en ventas")
ax.grid(axis="y", visible=False)
ax.legend(loc="lower right")
guardar(fig, OUT / "01_segmentos_rfm.png")

cmap = LinearSegmentedColormap.from_list("azules", ["#eef4fc", "#9cc1ee", AZUL, "#123d73"])
fig, ax = plt.subplots(figsize=(10, 6))
datos = coh_meses.values
im = ax.imshow(datos, cmap=cmap, aspect="auto", vmin=0, vmax=np.nanmax(datos))
for i in range(datos.shape[0]):
    for j in range(datos.shape[1]):
        v = datos[i, j]
        if not np.isnan(v):
            ax.text(j, i, f"{v:.1f}".replace(".", ","), ha="center", va="center", fontsize=7.5,
                    color="white" if v > np.nanmax(datos) * 0.55 else TEXTO)
ax.set_xticks(range(12), [f"M{k}" for k in range(1, 13)])
ax.set_yticks(range(len(coh_meses)), [f"{c}  ({int(n)})" for c, n in
              zip(coh_meses.index, res["retencion_cohortes"].groupby("cohorte").clientes.first().loc[coh_meses.index])])
ax.set_title("Retención por cohorte: % de clientes que vuelve a comprar k meses después")
ax.set_xlabel("Meses desde la primera compra")
ax.set_ylabel("Cohorte (clientes nuevos)")
ax.grid(False)
cb = fig.colorbar(im, ax=ax, fraction=0.03)
cb.set_label("% de la cohorte", color=TEXTO_2)
cb.outline.set_visible(False)
guardar(fig, OUT / "02_retencion_cohortes.png")

fig, ax = plt.subplots(figsize=(8.5, 4.2))
cols = [AZUL if v >= 3 else (NARANJA if v < 1.5 else GRIS) for v in clv.clv_cac]
ax.bar(clv.index, clv.clv_cac, color=cols, width=0.55)
ax.axhline(3, color=TEXTO_2, lw=1, ls="--")
ax.set_ylim(0, clv.clv_cac.max() * 1.15)
ax.text(len(clv) - 0.5, 3.1, "Referencia saludable: 3x", ha="right", fontsize=8, color=TEXTO_2)
for i, v in enumerate(clv.clv_cac):
    ax.text(i, v + 0.1, f"{v:.1f}x".replace(".", ","), ha="center", color=TEXTO)
ax.set_title("Margen bruto a 12 meses por cliente ÷ costo de adquisición (CLV:CAC)")
ax.grid(axis="x", visible=False)
guardar(fig, OUT / "03_clv_cac_por_canal.png")

# ---------------------------------------------------------------- Resumen
par = res["concentracion_pareto"]
resumen = dict(
    clientes=int(len(rfm)), pedidos=int(len(ped)), ventas_netas=float(ped.net_sales.sum()),
    margen_bruto=float(ped.gross_margin.sum()), ticket_promedio=round(ped.net_sales.mean()),
    pct_compra_unica=round(100 * (rfm.frecuencia == 1).mean(), 1),
    top10_pct_ventas=float(par.pct_acumulado.iloc[0]), top20_pct_ventas=float(par.pct_acumulado.iloc[1]),
    retencion_m1_prom=round(ret_m1, 1), recompra_90_dias_pct=round(recompra_90, 1),
    segmentos=seg.round(1).reset_index().to_dict(orient="records"),
    clv=clv.round(2).reset_index().to_dict(orient="records"),
)
(OUT / "resumen_resultados.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
print({k: v for k, v in resumen.items() if not isinstance(v, list)})
print(seg.drop(columns=["accion"]).round(1).to_string())
print(clv.round(2).to_string())
print(par.to_string())
