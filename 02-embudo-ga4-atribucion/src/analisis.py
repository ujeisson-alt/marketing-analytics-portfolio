"""
Embudo de conversión y modelos de atribución multitoque a partir de eventos de GA4.

1. Carga los eventos en SQLite y ejecuta sql/embudo_y_atribucion.sql.
2. Reconstruye el camino de canales de cada comprador hasta su primera compra.
3. Reparte el ingreso de cada venta entre canales con 5 modelos:
     First click · Last click · Linear · Position-based (40/20/40) · Time decay (vida media 7 días)
4. Compara cuánto crédito pierde o gana cada canal frente a Last click.
"""
from pathlib import Path
import json
import re
import sqlite3
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, PercentFormatter
from matplotlib.patches import Patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ.parent))
from estilo import aplicar_estilo, guardar, cop, AZUL, NARANJA, AQUA, AMARILLO, TEXTO, TEXTO_2, GRIS  # noqa: E402

OUT = RAIZ / "outputs"
OUT.mkdir(exist_ok=True)
aplicar_estilo()

# ---------------------------------------------------------------- 1. SQL
crudo = pd.read_csv(RAIZ / "data" / "ga4_events_export.csv", dtype={"user_pseudo_id": str})
con = sqlite3.connect(":memory:")
crudo.to_sql("ga4_events", con, index=False)
sql = (RAIZ / "sql" / "embudo_y_atribucion.sql").read_text(encoding="utf-8")
res = {}
for nombre, q in re.findall(r"-- name: (\w+)\n(.*?);", sql, flags=re.S):
    if nombre.startswith("setup"):
        con.execute(q)
        continue
    res[nombre] = pd.read_sql_query(q, con)
    res[nombre].to_csv(OUT / f"sql_{nombre}.csv", index=False)
print(f"{len(res)} consultas SQL ejecutadas")

# ---------------------------------------------------------------- 2. Caminos de conversión
ev = pd.read_sql_query("SELECT user_pseudo_id, ga_session_number, ga_session_id, canal, event_name, "
                       "purchase_revenue FROM eventos", con)
compras = ev[ev.event_name == "purchase"].set_index("user_pseudo_id")
toques = (ev[(ev.event_name == "session_start") & ev.user_pseudo_id.isin(compras.index)]
          .sort_values(["user_pseudo_id", "ga_session_number"]))
caminos = toques.groupby("user_pseudo_id").agg(canales=("canal", list), tiempos=("ga_session_id", list))
caminos["ingreso"] = compras.purchase_revenue
caminos["t_compra"] = caminos.tiempos.map(lambda t: t[-1])


# ---------------------------------------------------------------- 3. Modelos de atribución
def pesos(n, modelo, tiempos=None, t_compra=None):
    if modelo == "First click":
        return np.eye(n)[0]
    if modelo == "Last click":
        return np.eye(n)[-1]
    if modelo == "Linear":
        return np.full(n, 1 / n)
    if modelo == "Position-based":
        if n == 1:
            return np.array([1.0])
        if n == 2:
            return np.array([0.5, 0.5])
        w = np.full(n, 0.2 / (n - 2))
        w[0] = w[-1] = 0.4
        return w
    if modelo == "Time decay":
        dias = (t_compra - np.array(tiempos)) / 86400
        w = 0.5 ** (dias / 7)
        return w / w.sum()


MODELOS = ["First click", "Linear", "Position-based", "Time decay", "Last click"]
credito = {m: defaultdict(float) for m in MODELOS}
for _, fila in caminos.iterrows():
    n = len(fila.canales)
    for m in MODELOS:
        for canal, w in zip(fila.canales, pesos(n, m, fila.tiempos, fila.t_compra)):
            credito[m][canal] += w * fila.ingreso

atrib = pd.DataFrame(credito).fillna(0)
atrib = atrib.sort_values("Last click", ascending=False)
atrib["cambio_vs_last_click_pct"] = 100 * (atrib["Position-based"] / atrib["Last click"] - 1)
atrib.round(0).to_csv(OUT / "atribucion_por_modelo.csv")
assert np.allclose(atrib[MODELOS].sum(), caminos.ingreso.sum()), "Cada modelo debe repartir el 100 % del ingreso"

# Caminos más frecuentes y métricas de recorrido
caminos["ruta"] = caminos.canales.map(lambda c: " → ".join(c))
top_rutas = (caminos.groupby("ruta").agg(compras=("ingreso", "size"), ingresos=("ingreso", "sum"))
             .sort_values("compras", ascending=False).head(10))
top_rutas.to_csv(OUT / "top_rutas_conversion.csv")
caminos["n_toques"] = caminos.canales.map(len)
caminos["dias_a_compra"] = (caminos.t_compra - caminos.tiempos.map(lambda t: t[0])) / 86400

# ---------------------------------------------------------------- 4. Gráficos
emb = res["embudo_general"]
nombres = {"session_start": "Sesión", "view_item": "Ver producto", "add_to_cart": "Agregar al carrito",
           "begin_checkout": "Iniciar pago", "purchase": "Compra"}
fig, ax = plt.subplots(figsize=(9, 4.5))
y = np.arange(len(emb))[::-1]
ax.barh(y, emb.sesiones, color=AZUL, height=0.6)
for yi, (_, r) in zip(y, emb.iterrows()):
    txt = f"{r.sesiones:,.0f}".replace(",", ".")
    if pd.notna(r.pct_paso_anterior):
        txt += f"   ({r.pct_paso_anterior:.0f} % del paso anterior)".replace(".", ",")
    ax.text(r.sesiones + 300, yi, txt, va="center", fontsize=9, color=TEXTO)
ax.set_yticks(y, emb.paso.map(nombres))
ax.set_xlim(0, emb.sesiones.max() * 1.45)
ax.set_title("Embudo de e-commerce (sesiones), abr–jun 2026")
ax.grid(axis="y", visible=False)
ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:,.0f}".replace(",", ".")))
guardar(fig, OUT / "01_embudo.png")

disp = res["embudo_por_dispositivo"]
fig, ax = plt.subplots(figsize=(7, 3.6))
ax.bar(disp.dispositivo, disp.checkout_a_compra_pct, color=AZUL, width=0.5)
for i, v in enumerate(disp.checkout_a_compra_pct):
    ax.text(i, v + 1, f"{v:.1f} %".replace(".", ","), ha="center", color=TEXTO)
ax.set_ylim(0, 80)
ax.yaxis.set_major_formatter(PercentFormatter())
ax.set_title("De 'Iniciar pago' a 'Compra' por dispositivo")
ax.grid(axis="x", visible=False)
guardar(fig, OUT / "02_checkout_por_dispositivo.png")

modelos_graf = ["First click", "Linear", "Position-based", "Last click"]
colores = [AZUL, NARANJA, AQUA, AMARILLO]
fig, ax = plt.subplots(figsize=(10, 5))
x = np.arange(len(atrib))
ancho = 0.2
for i, (m, col) in enumerate(zip(modelos_graf, colores)):
    ax.bar(x + (i - 1.5) * ancho, atrib[m], width=ancho - 0.02, color=col, label=m)
ax.set_xticks(x, [c.replace(" - ", "\n") for c in atrib.index], fontsize=8.5)
ax.yaxis.set_major_formatter(FuncFormatter(cop))
ax.set_title("Ingresos atribuidos a cada canal según el modelo de atribución")
ax.grid(axis="x", visible=False)
ax.legend(ncol=4, loc="upper right")
guardar(fig, OUT / "03_atribucion_modelos.png")

cmb = atrib.cambio_vs_last_click_pct.sort_values()
fig, ax = plt.subplots(figsize=(9, 4.8))
cols = [AZUL if v >= 0 else NARANJA for v in cmb]
ax.barh(cmb.index, cmb.values, color=cols, height=0.6)
ax.axvline(0, color=TEXTO_2, lw=1)
for i, v in enumerate(cmb.values):
    ax.text(v + (3 if v >= 0 else -3), i, f"{v:+.0f} %", va="center", ha="left" if v >= 0 else "right",
            fontsize=9, color=TEXTO)
lim = max(abs(cmb.min()), abs(cmb.max())) * 1.3
ax.set_xlim(-lim, lim)
ax.xaxis.set_major_formatter(PercentFormatter())
ax.set_title("¿Cuánto crédito gana o pierde cada canal\nal pasar de Last click a Position-based?")
ax.grid(axis="y", visible=False)
ax.legend(handles=[Patch(color=AZUL, label="Subvalorado por Last click"),
                   Patch(color=NARANJA, label="Sobrevalorado por Last click")], loc="lower right")
guardar(fig, OUT / "04_cambio_credito.png")

# ---------------------------------------------------------------- 5. Resumen
resumen = {
    "eventos": len(crudo), "usuarios": int(crudo.user_pseudo_id.nunique()),
    "sesiones": int(emb.sesiones.iloc[0]), "compras": int(len(caminos)),
    "ingresos": float(caminos.ingreso.sum()),
    "tasa_conversion_sesion_pct": float(emb.pct_del_total.iloc[-1]),
    "tasa_conversion_usuario_pct": round(100 * len(caminos) / crudo.user_pseudo_id.nunique(), 2),
    "embudo": emb.to_dict(orient="records"),
    "dispositivo": disp.to_dict(orient="records"),
    "pct_compras_multitoque": round(100 * (caminos.n_toques > 1).mean(), 1),
    "toques_promedio": round(caminos.n_toques.mean(), 2),
    "dias_promedio_a_compra": round(caminos.dias_a_compra.mean(), 1),
    "dias_mediana_a_compra": round(caminos.dias_a_compra.median(), 1),
    "atribucion": atrib.round(1).reset_index(names="canal").to_dict(orient="records"),
    "top_rutas": top_rutas.reset_index().to_dict(orient="records"),
    "canal": res["conversion_por_canal"].to_dict(orient="records"),
}
(OUT / "resumen_resultados.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
print({k: v for k, v in resumen.items() if not isinstance(v, list)})
print(emb.to_string()); print(disp.to_string()); print(res["conversion_por_canal"].to_string())
print(atrib.round(0).to_string()); print(top_rutas.to_string())
