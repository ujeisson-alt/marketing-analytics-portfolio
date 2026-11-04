"""
Simula clientes y pedidos de la tienda ficticia "Kumbre Store" (ene 2025 – jun 2026),
como una exportación de Shopify / WooCommerce.

Cada cliente tiene un perfil oculto (comprador único, ocasional o leal) cuya probabilidad
depende del canal por el que llegó. El análisis RFM debe "descubrir" esos perfiles.
"""
from pathlib import Path
import numpy as np
import pandas as pd

rng = np.random.default_rng(99)
RAIZ = Path(__file__).resolve().parents[1]
(RAIZ / "data").mkdir(exist_ok=True)

N = 6_500
INICIO, CORTE = pd.Timestamp("2025-01-01"), pd.Timestamp("2026-06-30")
dias_totales = (CORTE - INICIO).days

CANALES = ["Google Ads", "Meta Ads", "TikTok Ads", "Orgánico / SEO", "Referidos"]
P_CANAL = [.30, .28, .17, .17, .08]
# Probabilidad de perfil (único, ocasional, leal) según canal de adquisición
PERFIL = {"Google Ads": [.52, .33, .15], "Meta Ads": [.58, .30, .12], "TikTok Ads": [.68, .25, .07],
          "Orgánico / SEO": [.45, .35, .20], "Referidos": [.38, .36, .26]}
DIAS_ENTRE_COMPRAS = {"ocasional": 110, "leal": 42}
SIGUE_COMPRANDO = {"ocasional": .62, "leal": .90}
CIUDADES = ["Bogotá", "Medellín", "Cali", "Barranquilla", "Bucaramanga", "Otras"]
P_CIUDAD = [.38, .20, .12, .08, .06, .16]
CATEGORIAS = {"Vestidos": .46, "Jeans": .44, "Calzado": .40, "Accesorios": .55,
              "Hogar - Textiles": .38, "Hogar - Decoración": .48}  # margen bruto

clientes, pedidos = [], []
n_ped = 0
for i in range(N):
    cid = f"CL{10000 + i}"
    canal = rng.choice(CANALES, p=P_CANAL)
    perfil = rng.choice(["unico", "ocasional", "leal"], p=PERFIL[canal])
    # Más clientes nuevos con el tiempo (la tienda crece)
    t = INICIO + pd.Timedelta(days=int(dias_totales * rng.beta(1.3, 1)))
    clientes.append(dict(customer_id=cid, acquisition_channel=canal, city=rng.choice(CIUDADES, p=P_CIUDAD),
                         first_order_date=t.date()))
    while t <= CORTE:
        n_ped += 1
        cat = rng.choice(list(CATEGORIAS))
        bruto = round(rng.lognormal(np.log(145_000 if perfil != "leal" else 165_000), 0.35), -2)
        descuento = round(bruto * rng.choice([0, 0, 0, .1, .2]), -2)
        neto = bruto - descuento
        pedidos.append(dict(order_id=f"#{100000 + n_ped}", customer_id=cid, order_date=t.date(),
                            category=cat, gross_sales=bruto, discount=descuento, net_sales=neto,
                            gross_margin=round(neto * CATEGORIAS[cat] - (0 if descuento == 0 else descuento * .2))))
        if perfil == "unico" or rng.random() > SIGUE_COMPRANDO[perfil]:
            break
        t += pd.Timedelta(days=int(rng.exponential(DIAS_ENTRE_COMPRAS[perfil])) + 7)

pd.DataFrame(clientes).to_csv(RAIZ / "data" / "clientes.csv", index=False)
ped = pd.DataFrame(pedidos).sort_values("order_date")
ped.to_csv(RAIZ / "data" / "pedidos.csv", index=False)
print(f"{N:,} clientes | {len(ped):,} pedidos | ventas netas ${ped.net_sales.sum()/1e6:,.1f} M")
