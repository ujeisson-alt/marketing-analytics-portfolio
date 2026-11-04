"""
Genera eventos SIMULADOS con el esquema de la exportación de GA4 a BigQuery (aplanado)
para la tienda ficticia "Kumbre Store", abril – junio 2026.

Eventos del embudo de e-commerce recomendado por GA4:
  session_start -> view_item -> add_to_cart -> begin_checkout -> purchase

Comportamientos realistas incluidos (para que el análisis los descubra):
  - Los usuarios llegan por primera vez sobre todo por canales de descubrimiento (TikTok, Meta, orgánico)
    y regresan por Directo, Email o búsqueda de marca.
  - El checkout en móvil convierte peor que en escritorio (fricción en el formulario de pago).
  - La probabilidad de compra crece con cada sesión (usuarios recurrentes).
"""
from pathlib import Path
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
RAIZ = Path(__file__).resolve().parents[1]
(RAIZ / "data").mkdir(exist_ok=True)

N_USUARIOS = 18_000
INICIO, FIN = pd.Timestamp("2026-04-01"), pd.Timestamp("2026-06-30 23:59")

# (source, medium, campaign) por canal. La agrupación de canales se hace después en SQL, como en GA4.
FUENTES = {
    "google_cpc":   ("google", "cpc", "GA_Search_Genericas"),
    "google_brand": ("google", "cpc", "GA_Search_Marca"),
    "organic":      ("google", "organic", "(organic)"),
    "meta":         ("facebook", "paid_social", "META_Prospecting_Lookalike"),
    "meta_rtg":     ("instagram", "paid_social", "META_Retargeting_Carrito"),
    "tiktok":       ("tiktok", "paid_social", "TT_Awareness_UGC"),
    "ig_organic":   ("instagram", "social", "(not set)"),
    "email":        ("hubspot", "email", "newsletter_semanal"),
    "referral":     ("blog.modacolombia.co", "referral", "(not set)"),
    "direct":       ("(direct)", "(none)", "(direct)"),
}
# Probabilidad del canal en la PRIMERA sesión vs. en sesiones de REGRESO
P_PRIMERA = {"google_cpc": .16, "google_brand": .03, "organic": .20, "meta": .20, "meta_rtg": .00,
             "tiktok": .17, "ig_organic": .06, "email": .00, "referral": .06, "direct": .12}
P_REGRESO = {"google_cpc": .08, "google_brand": .17, "organic": .12, "meta": .06, "meta_rtg": .12,
             "tiktok": .04, "ig_organic": .04, "email": .14, "referral": .02, "direct": .21}
# Intención de compra relativa por canal (multiplica la probabilidad de avanzar en el embudo)
INTENCION = {"google_cpc": 1.15, "google_brand": 1.45, "organic": 1.0, "meta": 0.75, "meta_rtg": 1.35,
             "tiktok": 0.55, "ig_organic": 0.8, "email": 1.3, "referral": 0.9, "direct": 1.25}
CATEGORIAS = ["Vestidos", "Jeans", "Calzado", "Accesorios", "Hogar - Textiles", "Hogar - Decoración"]
PRECIO = {"Vestidos": 159_000, "Jeans": 139_000, "Calzado": 189_000, "Accesorios": 59_000,
          "Hogar - Textiles": 119_000, "Hogar - Decoración": 89_000}

canales = list(FUENTES)
eventos, tx = [], 0
for u in range(N_USUARIOS):
    user_id = f"{rng.integers(10**9, 10**10)}.{rng.integers(10**9, 10**10)}"
    dispositivo = rng.choice(["mobile", "desktop", "tablet"], p=[.68, .28, .04])
    n_sesiones = min(rng.geometric(0.55), 8)
    t = INICIO + pd.Timedelta(seconds=int(rng.uniform(0, (FIN - INICIO).total_seconds() * 0.85)))
    for s in range(1, n_sesiones + 1):
        if t > FIN:
            break
        p = P_PRIMERA if s == 1 else P_REGRESO
        canal = rng.choice(canales, p=np.array(list(p.values())) / sum(p.values()))
        source, medium, campaign = FUENTES[canal]
        session_id = int(t.timestamp())
        cat = rng.choice(CATEGORIAS)
        intencion = INTENCION[canal] * (1 + 0.35 * (s - 1))  # los recurrentes compran más
        pasos = [("session_start", 1.0),
                 ("view_item", min(.62 * intencion ** .3, .95)),
                 ("add_to_cart", min(.13 * intencion, .9)),
                 ("begin_checkout", min(.55 * intencion ** .5, .95)),
                 ("purchase", .40 if dispositivo == "mobile" else .62)]
        ts = t
        compro = False
        for evento, prob in pasos:
            if rng.random() > prob:
                break
            ts += pd.Timedelta(seconds=int(rng.exponential(60)) + 5)
            fila = dict(event_date=ts.strftime("%Y%m%d"), event_timestamp=int(ts.timestamp() * 1e6),
                        event_name=evento, user_pseudo_id=user_id, ga_session_id=session_id,
                        ga_session_number=s, session_source=source, session_medium=medium,
                        session_campaign=campaign, device_category=dispositivo,
                        item_category=cat if evento != "session_start" else None,
                        transaction_id=None, purchase_revenue=None)
            if evento == "purchase":
                tx += 1
                unidades = rng.choice([1, 1, 1, 2, 2, 3])
                fila.update(transaction_id=f"T{100000 + tx}",
                            purchase_revenue=float(round(PRECIO[cat] * unidades * rng.uniform(0.85, 1.0), -2)))
                compro = True
            eventos.append(fila)
        if compro:
            break  # el análisis de atribución mira el camino hasta la primera compra
        t += pd.Timedelta(hours=float(rng.exponential(4 * 24)) + 1)

df = pd.DataFrame(eventos).sort_values("event_timestamp")
df.to_csv(RAIZ / "data" / "ga4_events_export.csv", index=False)
print(f"{len(df):,} eventos | {df.user_pseudo_id.nunique():,} usuarios | "
      f"{df.ga_session_id.astype(str).add(df.user_pseudo_id).nunique():,} sesiones | {tx:,} compras")
