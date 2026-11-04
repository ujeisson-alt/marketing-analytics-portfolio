# Reporte de calidad de datos

## Transformaciones

- Google Ads: 543 filas leídas; columna Cost convertida de texto '1.234.567' a número
- Meta Ads: 549 filas leídas; 6 filas duplicadas eliminadas
- TikTok Ads: 362 filas leídas; fecha AAAA/MM/DD estandarizada; 4 conversiones vacías imputadas con ingresos / ticket promedio de la campaña

## Controles automáticos

| Control | Resultado |
|---|---|
| Sin fechas fuera de ene-jun 2026 | ✅ OK |
| Sin gasto negativo | ✅ OK |
| Clics <= impresiones | ✅ OK |
| Conversiones <= clics | ✅ OK |
| Sin nulos en la tabla final | ✅ OK |
| Una fila por fecha y campaña | ✅ OK |
| 181 días x 8 campañas = 1.448 filas | ✅ OK |

Tabla final: **1,448 filas**, 8 campañas, 3 plataformas.
