"""
Simula la exportación por destinatario de un A/B test de asunto en HubSpot
para la campaña "Día del Padre 2026" de la tienda ficticia Kumbre Store.

  Variante A (control):    "Regalos para papá con 20 % OFF"
  Variante B (tratamiento): "{Nombre}, el regalo perfecto para tu papá está aquí 🎁"

Incluye aperturas automáticas por Apple Mail Privacy Protection (MPP), que inflan
la tasa de apertura: por eso la métrica principal del test es la tasa de clic.
"""
from pathlib import Path
import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
RAIZ = Path(__file__).resolve().parents[1]
(RAIZ / "data").mkdir(exist_ok=True)

N = 36_000
segmento = rng.choice(["Cliente recurrente", "Compró una vez", "Suscriptor sin compra"], N, p=[.22, .28, .50])
dispositivo = rng.choice(["Móvil", "Escritorio"], N, p=[.71, .29])
variante = rng.permutation(np.repeat(["A", "B"], N // 2))  # asignación aleatoria 50/50

# Efecto real (desconocido para el analista): la personalización ayuda más a quien ya compró
base_open = {"Cliente recurrente": .30, "Compró una vez": .22, "Suscriptor sin compra": .15}
base_click = {"Cliente recurrente": .045, "Compró una vez": .026, "Suscriptor sin compra": .014}
lift_click = {"Cliente recurrente": 1.32, "Compró una vez": 1.25, "Suscriptor sin compra": 1.05}

entregado = rng.random(N) < .985
usa_apple_mail = rng.random(N) < .33
filas = []
for i in range(N):
    s, v = segmento[i], variante[i]
    p_open = base_open[s] * (1.12 if v == "B" else 1.0)
    p_click = base_click[s] * (lift_click[s] if v == "B" else 1.0)
    if not entregado[i]:
        filas.append((0, 0, 0, 0, 0, 0, 0))
        continue
    mpp = int(usa_apple_mail[i] and rng.random() < .9)          # apertura automática del servidor de Apple
    abre_humano = rng.random() < p_open
    clic = int(rng.random() < p_click / p_open) if abre_humano else 0  # solo quien realmente abre puede hacer clic
    compra = int(clic and rng.random() < .11)
    ingreso = round(rng.choice([89_000, 139_000, 159_000, 189_000, 249_000]) * rng.uniform(.8, 1)) if compra else 0
    baja = int(rng.random() < (.0018 if v == "B" else .0015))
    filas.append((1, int(abre_humano or mpp), mpp, clic, compra, ingreso, baja))

df = pd.DataFrame(filas, columns=["delivered", "opened", "apple_mpp_open", "clicked", "purchased", "revenue",
                                  "unsubscribed"])
df.insert(0, "contact_id", [f"C{200000 + i}" for i in range(N)])
df.insert(1, "email_variant", variante)
df.insert(2, "subject_line", np.where(variante == "A", "Regalos para papá con 20 % OFF",
                                      "{Nombre}, el regalo perfecto para tu papá está aquí 🎁"))
df.insert(3, "lifecycle_segment", segmento)
df.insert(4, "device", dispositivo)
df["send_date"] = "2026-06-12"
df.to_csv(RAIZ / "data" / "hubspot_ab_test_export.csv", index=False)
print(df.groupby("email_variant")[["delivered", "opened", "clicked", "purchased", "revenue"]].sum())
