"""
Análisis de desempeño multicanal y optimización de presupuesto.

1. Ejecuta las consultas de sql/kpis_campanas.sql sobre SQLite y guarda cada resultado.
2. Estima la curva de respuesta (rendimientos decrecientes) de cada campaña:
       ln(ingresos) = ln(a) + b * ln(inversión) + controles de temporada
3. Calcula el ROAS marginal (lo que devuelve el SIGUIENTE peso invertido).
4. Redistribuye el MISMO presupuesto total para maximizar ingresos,
   con límites prudentes (cada campaña entre 50 % y 200 % de su inversión actual).
5. Genera los gráficos para el README.
"""
from pathlib import Path
import json
import re
import sqlite3
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from matplotlib.patches import Patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ.parent))
from estilo import aplicar_estilo, guardar, cop, COLOR_PLATAFORMA, TEXTO, TEXTO_2, GRIS  # noqa: E402

OUT = RAIZ / "outputs"
aplicar_estilo()

# ---------------------------------------------------------------- 1. SQL
sql = (RAIZ / "sql" / "kpis_campanas.sql").read_text(encoding="utf-8")
consultas = re.findall(r"-- name: (\w+)\n(.*?);", sql, flags=re.S)
resultados = {}
with sqlite3.connect(RAIZ / "data" / "processed" / "campanas.db") as con:
    for nombre, q in consultas:
        resultados[nombre] = pd.read_sql_query(q, con)
        resultados[nombre].to_csv(OUT / f"sql_{nombre}.csv", index=False)
print(f"{len(consultas)} consultas SQL ejecutadas")

plat = resultados["kpis_por_plataforma"]
camp = resultados["kpis_por_campana"]
df = pd.read_csv(RAIZ / "data" / "processed" / "campanas_unificado.csv", parse_dates=["fecha"])

# ---------------------------------------------------------------- 2. Curvas de respuesta
df["fin_semana"] = (df.fecha.dt.dayofweek >= 5).astype(int)
df["enero"] = (df.fecha.dt.month == 1).astype(int)
df["dia_madre"] = df.fecha.between("2026-04-25", "2026-05-10").astype(int)

curvas = []
for c, d in df[df.revenue > 0].groupby("campana"):
    X = np.column_stack([np.ones(len(d)), np.log(d.spend), d.fin_semana, d.enero, d.dia_madre])
    coef, *_ = np.linalg.lstsq(X, np.log(d.revenue), rcond=None)
    pred = X @ coef
    r2 = 1 - np.sum((np.log(d.revenue) - pred) ** 2) / np.sum((np.log(d.revenue) - np.log(d.revenue).mean()) ** 2)
    # Nivel "día normal": promedio de los efectos de temporada observados
    ln_a = coef[0] + coef[2] * d.fin_semana.mean() + coef[3] * d.enero.mean() + coef[4] * d.dia_madre.mean()
    gasto_prom = d.spend.mean()
    curvas.append(dict(campana=c, plataforma=d.plataforma.iloc[0], a=np.exp(ln_a), b=coef[1], r2=r2,
                       inversion_diaria=gasto_prom))
curvas = pd.DataFrame(curvas)
curvas["ingreso_modelo"] = curvas.a * curvas.inversion_diaria ** curvas.b
curvas["roas_promedio"] = curvas.ingreso_modelo / curvas.inversion_diaria
curvas["roas_marginal"] = curvas.b * curvas.roas_promedio   # derivada de a*s^b dividida por 1 peso

# ---------------------------------------------------------------- 3. Optimización
s0 = curvas.inversion_diaria.values
a, b = curvas.a.values, curvas.b.values
total = s0.sum()


def ingreso_negativo(s):
    return -np.sum(a * s ** b)


res = minimize(ingreso_negativo, s0, method="SLSQP",
               bounds=[(0.5 * x, 2.0 * x) for x in s0],
               constraints=[{"type": "eq", "fun": lambda s: s.sum() - total}])
curvas["inversion_recomendada"] = res.x
curvas["cambio_pct"] = 100 * (res.x / s0 - 1)
ingreso_actual, ingreso_opt = -ingreso_negativo(s0), -ingreso_negativo(res.x)
mejora_pct = 100 * (ingreso_opt / ingreso_actual - 1)
curvas.round(3).to_csv(OUT / "curvas_respuesta_y_presupuesto.csv", index=False)

# ---------------------------------------------------------------- 4. Gráficos
fmt_cop = FuncFormatter(cop)

# 4.1 ROAS por campaña
c_ord = camp.sort_values("roas")
fig, ax = plt.subplots(figsize=(9, 5))
barras = ax.barh(c_ord.campana, c_ord.roas, color=c_ord.plataforma.map(COLOR_PLATAFORMA), height=0.6)
ax.axvline(1, color=TEXTO_2, lw=1, ls="--")
ax.text(1.05, -0.9, "ROAS = 1 (punto de equilibrio)", color=TEXTO_2, fontsize=8)
for bar, v in zip(barras, c_ord.roas):
    ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2, f"{v:.1f}x", va="center", color=TEXTO, fontsize=9)
ax.set_title("ROAS por campaña (ingresos / inversión), ene–jun 2026")
ax.set_xlabel("ROAS")
ax.grid(axis="y", visible=False)
ax.legend(handles=[Patch(color=col, label=p) for p, col in COLOR_PLATAFORMA.items()], loc="lower right")
guardar(fig, OUT / "01_roas_por_campana.png")

# 4.2 Ingresos mensuales por plataforma
tm = resultados["tendencia_mensual"]
MESES = {"2026-01": "Ene", "2026-02": "Feb", "2026-03": "Mar", "2026-04": "Abr", "2026-05": "May", "2026-06": "Jun"}
tm = tm.assign(mes=tm.mes.map(MESES))
fig, ax = plt.subplots(figsize=(9, 4.5))
for p, d in tm.groupby("plataforma"):
    ax.plot(d.mes, d.ingresos, marker="o", ms=6, color=COLOR_PLATAFORMA[p], label=p)
    ax.text(len(d) - 0.9, d.ingresos.iloc[-1], p, color=TEXTO, fontsize=9, va="center")
ax.yaxis.set_major_formatter(fmt_cop)
ax.set_xlim(-0.3, 6.2)
ax.set_title("Ingresos atribuidos por plataforma y mes, 2026")
ax.annotate("Día de la Madre", xy=(4, tm[tm.mes == "May"].ingresos.max()), xytext=(2.6, tm.ingresos.max() * 1.02),
            arrowprops=dict(arrowstyle="->", color=TEXTO_2), color=TEXTO_2, fontsize=9)
ax.legend(loc="upper left")
guardar(fig, OUT / "02_ingresos_mensuales.png")

# 4.3 ROAS promedio vs ROAS marginal
cv = curvas.sort_values("roas_marginal")
y = np.arange(len(cv))
fig, ax = plt.subplots(figsize=(9, 5))
ax.barh(y + 0.2, cv.roas_promedio, height=0.38, color=GRIS, label="ROAS promedio")
ax.barh(y - 0.2, cv.roas_marginal, height=0.38, color=cv.plataforma.map(COLOR_PLATAFORMA), label="ROAS marginal")
ax.set_yticks(y, cv.campana)
ax.axvline(1, color=TEXTO_2, lw=1, ls="--")
ax.set_title("El siguiente peso no rinde igual: ROAS promedio vs. marginal")
ax.set_xlabel("Ingresos por cada peso invertido")
ax.grid(axis="y", visible=False)
ax.legend(handles=[Patch(color=GRIS, label="ROAS promedio")] + [Patch(color=col, label=f"ROAS marginal – {p}") for p, col in COLOR_PLATAFORMA.items()], loc="lower right")
guardar(fig, OUT / "03_roas_marginal.png")

# 4.4 Presupuesto actual vs recomendado
cv = curvas.sort_values("cambio_pct")
fig, ax = plt.subplots(figsize=(9, 5))
ax.barh(y + 0.2, cv.inversion_diaria, height=0.38, color=GRIS, label="Inversión diaria actual")
ax.barh(y - 0.2, cv.inversion_recomendada, height=0.38, color=cv.plataforma.map(COLOR_PLATAFORMA), label="Recomendada")
for i, (v, ch) in enumerate(zip(cv.inversion_recomendada, cv.cambio_pct)):
    ax.text(v + 15_000, i - 0.2, f"{ch:+.0f} %", va="center", fontsize=9, color=TEXTO)
ax.set_yticks(y, cv.campana)
ax.xaxis.set_major_formatter(fmt_cop)
ax.set_title(f"Redistribución del mismo presupuesto: +{mejora_pct:.1f} % de ingresos estimados".replace(".", ","))
ax.grid(axis="y", visible=False)
ax.legend(handles=[Patch(color=GRIS, label="Inversión diaria actual")] + [Patch(color=col, label=f"Recomendada – {p}") for p, col in COLOR_PLATAFORMA.items()], loc="lower right")
guardar(fig, OUT / "04_presupuesto_recomendado.png")

# ---------------------------------------------------------------- 5. Resumen
dm = resultados["impacto_dia_de_la_madre"].set_index("periodo")
resumen = {
    "inversion_total": float(df.spend.sum()),
    "ingresos_total": float(df.revenue.sum()),
    "roas_total": round(df.revenue.sum() / df.spend.sum(), 2),
    "conversiones_total": int(df.conversions.sum()),
    "cpa_total": round(df.spend.sum() / df.conversions.sum()),
    "plataformas": plat.to_dict(orient="records"),
    "campanas": camp.to_dict(orient="records"),
    "curvas": curvas[["campana", "b", "r2", "roas_promedio", "roas_marginal", "inversion_diaria",
                      "inversion_recomendada", "cambio_pct"]].round(3).to_dict(orient="records"),
    "mejora_pct": round(mejora_pct, 1),
    "ingreso_diario_actual": round(ingreso_actual),
    "ingreso_diario_optimo": round(ingreso_opt),
    "dia_madre_ingreso_diario": float(dm.loc["Temporada Día de la Madre", "ingreso_diario_promedio"]),
    "resto_ingreso_diario": float(dm.loc["Resto del semestre", "ingreso_diario_promedio"]),
}
(OUT / "resumen_resultados.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: v for k, v in resumen.items() if k not in ("plataformas", "campanas", "curvas")}, indent=2))
print(curvas[["campana", "b", "r2", "roas_promedio", "roas_marginal", "cambio_pct"]].round(2).to_string())
print(plat.to_string())
