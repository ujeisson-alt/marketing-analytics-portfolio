"""Ejecuta los 4 proyectos de principio a fin: datos -> ETL -> SQL -> análisis -> gráficos."""
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PASOS = [
    ("01-campanas-multicanal-roas", ["generar_datos.py", "etl.py", "analisis.py"]),
    ("02-embudo-ga4-atribucion", ["generar_datos.py", "analisis.py"]),
    ("03-ab-testing-email", ["generar_datos.py", "analisis.py"]),
    ("04-segmentacion-rfm-clv", ["generar_datos.py", "analisis.py"]),
]

inicio = time.time()
for carpeta, scripts in PASOS:
    print(f"\n=== {carpeta} ===")
    for s in scripts:
        print(f"  → {s}")
        r = subprocess.run([sys.executable, str(RAIZ / carpeta / "src" / s)], capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-2000:], r.stderr[-4000:])
            sys.exit(f"Falló {carpeta}/src/{s}")
print(f"\n✅ Portafolio regenerado en {time.time() - inicio:.0f} s")
