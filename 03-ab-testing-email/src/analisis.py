"""
Análisis estadístico del A/B test de asunto de email.

Pasos (en el orden en que se hacen en la práctica):
  0. Diseño: tamaño de muestra necesario y efecto mínimo detectable (MDE).
  1. Control de calidad: Sample Ratio Mismatch (SRM) con prueba chi-cuadrado.
  2. Métrica principal: CTR (clics / entregados) con prueba z de dos proporciones e IC 95 %.
  3. Métricas secundarias: apertura sin Apple MPP, conversión, ingreso por destinatario (bootstrap), bajas.
  4. Efecto por segmento con corrección de Bonferroni.
"""
from pathlib import Path
import json
import re
import sqlite3
import sys

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ.parent))
from estilo import aplicar_estilo, guardar, GRIS, AZUL, NARANJA, TEXTO, TEXTO_2  # noqa: E402

OUT = RAIZ / "outputs"
OUT.mkdir(exist_ok=True)
aplicar_estilo()
COLOR = {"A": GRIS, "B": AZUL}
rng = np.random.default_rng(1)

df = pd.read_csv(RAIZ / "data" / "hubspot_ab_test_export.csv")

# ---------------------------------------------------------------- SQL
con = sqlite3.connect(":memory:")
df.to_sql("envios", con, index=False)
res = {}
for nombre, q in re.findall(r"-- name: (\w+)\n(.*?);", (RAIZ / "sql" / "resultados_ab.sql").read_text(encoding="utf-8"), re.S):
    res[nombre] = pd.read_sql_query(q, con)
    res[nombre].to_csv(OUT / f"sql_{nombre}.csv", index=False)


# ---------------------------------------------------------------- 0. Diseño del experimento
def n_por_grupo(p1, p2, alpha=0.05, poder=0.8):
    za, zb = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(poder)
    pbar = (p1 + p2) / 2
    return ((za * np.sqrt(2 * pbar * (1 - pbar)) + zb * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) / (p2 - p1)) ** 2


CTR_HISTORICO = 0.024
n_20 = n_por_grupo(CTR_HISTORICO, CTR_HISTORICO * 1.20)  # diseño: detectar +20 % relativo
ent = df[df.delivered == 1]
n_real = ent.groupby("email_variant").size()
# MDE alcanzable con la muestra real (búsqueda simple)
mde = next(m for m in np.arange(0.01, 1, 0.001) if n_por_grupo(CTR_HISTORICO, CTR_HISTORICO * (1 + m)) <= n_real.min())

# ---------------------------------------------------------------- 1. SRM
chi2, p_srm = stats.chisquare(n_real.values)  # entregados por variante: ¿se mantiene el 50/50?
assert p_srm > 0.01, "Sample Ratio Mismatch: la asignación no fue 50/50, no confiar en el test"


# ---------------------------------------------------------------- 2-3. Pruebas
def prueba_proporciones(x_a, n_a, x_b, n_b):
    pa, pb = x_a / n_a, x_b / n_b
    pp = (x_a + x_b) / (n_a + n_b)
    z = (pb - pa) / np.sqrt(pp * (1 - pp) * (1 / n_a + 1 / n_b))
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    se = np.sqrt(pa * (1 - pa) / n_a + pb * (1 - pb) / n_b)
    return dict(a=pa, b=pb, dif=pb - pa, ic_bajo=pb - pa - 1.96 * se, ic_alto=pb - pa + 1.96 * se,
                lift=(pb / pa - 1), z=z, p=p)


A, B = ent[ent.email_variant == "A"], ent[ent.email_variant == "B"]
sin_mpp = ent[ent.apple_mpp_open == 0]
Am, Bm = sin_mpp[sin_mpp.email_variant == "A"], sin_mpp[sin_mpp.email_variant == "B"]
pruebas = {
    "CTR (principal)": prueba_proporciones(A.clicked.sum(), len(A), B.clicked.sum(), len(B)),
    "Apertura sin Apple MPP": prueba_proporciones(Am.opened.sum(), len(Am), Bm.opened.sum(), len(Bm)),
    "Conversión": prueba_proporciones(A.purchased.sum(), len(A), B.purchased.sum(), len(B)),
    "Tasa de bajas": prueba_proporciones(A.unsubscribed.sum(), len(A), B.unsubscribed.sum(), len(B)),
}

# Ingreso por destinatario: bootstrap (la distribución tiene muchos ceros, no es normal)
ra, rb = A.revenue.values, B.revenue.values
boot = np.array([rng.choice(rb, len(rb)).mean() - rng.choice(ra, len(ra)).mean() for _ in range(10_000)])
rpr = dict(a=ra.mean(), b=rb.mean(), dif=rb.mean() - ra.mean(),
           ic_bajo=np.percentile(boot, 2.5), ic_alto=np.percentile(boot, 97.5),
           p=2 * min((boot <= 0).mean(), (boot >= 0).mean()))

tabla = pd.DataFrame(pruebas).T
tabla.to_csv(OUT / "pruebas_estadisticas.csv")

# ---------------------------------------------------------------- 4. Segmentos (Bonferroni)
alpha_bonf = 0.05 / 3
seg = []
for s, d in ent.groupby("lifecycle_segment"):
    a, b = d[d.email_variant == "A"], d[d.email_variant == "B"]
    r = prueba_proporciones(a.clicked.sum(), len(a), b.clicked.sum(), len(b))
    seg.append(dict(segmento=s, n=len(d), **r, significativo=r["p"] < alpha_bonf))
seg = pd.DataFrame(seg).sort_values("lift")
seg.to_csv(OUT / "efecto_por_segmento.csv", index=False)

# ---------------------------------------------------------------- Gráficos
fig, axes = plt.subplots(1, 3, figsize=(11, 3.8))
for ax, (nombre, r) in zip(axes, [(k, pruebas[k]) for k in ["Apertura sin Apple MPP", "CTR (principal)", "Conversión"]]):
    for i, (v, n) in enumerate([("A", len(A) if "MPP" not in nombre else len(Am)),
                                ("B", len(B) if "MPP" not in nombre else len(Bm))]):
        p = r[v.lower()]
        e = 1.96 * np.sqrt(p * (1 - p) / n)
        ax.errorbar(i, p * 100, yerr=e * 100, fmt="o", ms=9, color=COLOR[v], capsize=6, lw=2)
        ax.text(i + 0.12, p * 100, f"{p*100:.2f} %".replace(".", ","), va="center", fontsize=9, color=TEXTO)
    ax.set_xticks([0, 1], ["A · control", "B · personalizado"])
    ax.set_xlim(-0.5, 1.8)
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=2 if nombre == "Conversión" else 1))
    estado = "significativo" if r["p"] < 0.05 else "no significativo"
    txt_p = "p < 0,001" if r["p"] < 0.001 else f"p = {r['p']:.3f}".replace(".", ",")
    ax.set_title(f"{nombre}\n{txt_p} ({estado})", fontsize=10.5)
    ax.grid(axis="x", visible=False)
fig.suptitle("Resultados por variante con intervalo de confianza del 95 %", x=0.01, ha="left",
             fontweight="bold", fontsize=13, color=TEXTO)
guardar(fig, OUT / "01_resultados_variantes.png")

fig, ax = plt.subplots(figsize=(9, 3.6))
y = np.arange(len(seg))
for yi, (_, r) in zip(y, seg.iterrows()):
    lift, lo, hi = r.lift * 100, (r.ic_bajo / r.a) * 100, (r.ic_alto / r.a) * 100
    col = AZUL if r.significativo else GRIS
    ax.errorbar(lift, yi, xerr=[[lift - lo], [hi - lift]], fmt="o", ms=9, color=col, capsize=5, lw=2)
    ax.text(hi + 2, yi, f"{lift:+.0f} %  (p = {r.p:.3f})".replace(".", ","), va="center", fontsize=9, color=TEXTO)
ax.axvline(0, color=TEXTO_2, lw=1)
ax.set_yticks(y, seg.segmento)
ax.set_ylim(-0.6, len(seg) - 0.4)
ax.xaxis.set_major_formatter(PercentFormatter())
ax.set_xlim(min(-40, (seg.ic_bajo / seg.a).min() * 100 - 5), (seg.ic_alto / seg.a).max() * 100 + 45)
ax.set_title("Mejora del CTR de B vs. A por segmento (IC 95 %)")
ax.grid(axis="y", visible=False)
ax.text(0.99, 0.02, f"Azul = significativo con Bonferroni (α = {alpha_bonf:.4f})".replace(".", ","),
        transform=ax.transAxes, ha="right", fontsize=8, color=TEXTO_2)
guardar(fig, OUT / "02_efecto_por_segmento.png")

# ---------------------------------------------------------------- Resumen
c = pruebas["CTR (principal)"]
resumen = dict(
    n_necesario_por_grupo_mde20=int(np.ceil(n_20)), n_real_por_grupo=n_real.to_dict(), mde_alcanzable_pct=round(mde * 100, 1),
    srm_p=round(p_srm, 3), pruebas={k: {kk: float(vv) for kk, vv in v.items()} for k, v in pruebas.items()},
    ingreso_por_destinatario={k: float(v) for k, v in rpr.items()},
    segmentos=seg.to_dict(orient="records"),
    clics_extra_por_envio_36k=round(c["dif"] * 36_000),
)
(OUT / "resumen_resultados.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps({k: v for k, v in resumen.items() if k != "segmentos"}, indent=2, default=str))
print(seg.round(4).to_string())
for k in res:
    print(res[k].to_string())
