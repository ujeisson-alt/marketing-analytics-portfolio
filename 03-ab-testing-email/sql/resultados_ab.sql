-- =====================================================================
-- Resultados del A/B test de asunto (HubSpot)  |  Motor: SQLite
-- Tabla: envios (una fila por destinatario)
-- =====================================================================

-- name: resumen_por_variante
SELECT
    email_variant                                                    AS variante,
    COUNT(*)                                                         AS enviados,
    SUM(delivered)                                                   AS entregados,
    ROUND(100.0 * SUM(opened) / SUM(delivered), 2)                   AS tasa_apertura_reportada_pct,
    ROUND(100.0 * SUM(CASE WHEN apple_mpp_open = 0 THEN opened END)
          / SUM(CASE WHEN apple_mpp_open = 0 THEN delivered END), 2)  AS tasa_apertura_sin_mpp_pct,
    ROUND(100.0 * SUM(clicked) / SUM(delivered), 2)                  AS ctr_pct,
    ROUND(100.0 * SUM(purchased) / SUM(delivered), 3)                AS tasa_conversion_pct,
    SUM(revenue)                                                     AS ingresos,
    ROUND(1.0 * SUM(revenue) / SUM(delivered), 1)                    AS ingreso_por_destinatario,
    ROUND(100.0 * SUM(unsubscribed) / SUM(delivered), 3)             AS tasa_bajas_pct
FROM envios
GROUP BY email_variant
ORDER BY email_variant;

-- name: ctr_por_segmento
SELECT
    lifecycle_segment                                                AS segmento,
    ROUND(100.0 * SUM(CASE WHEN email_variant = 'A' THEN clicked END)
          / SUM(CASE WHEN email_variant = 'A' THEN delivered END), 2) AS ctr_a_pct,
    ROUND(100.0 * SUM(CASE WHEN email_variant = 'B' THEN clicked END)
          / SUM(CASE WHEN email_variant = 'B' THEN delivered END), 2) AS ctr_b_pct,
    SUM(delivered)                                                   AS entregados
FROM envios
GROUP BY lifecycle_segment
ORDER BY ctr_a_pct DESC;

-- name: inflacion_apple_mpp
-- ¿Cuánto infla Apple Mail Privacy Protection la tasa de apertura?
SELECT
    CASE WHEN apple_mpp_open = 1 THEN 'Apertura automática (Apple MPP)' ELSE 'Resto de destinatarios' END AS grupo,
    SUM(delivered)                                    AS entregados,
    ROUND(100.0 * SUM(opened) / SUM(delivered), 1)    AS tasa_apertura_pct,
    ROUND(100.0 * SUM(clicked) / SUM(delivered), 2)   AS ctr_pct
FROM envios
WHERE delivered = 1
GROUP BY grupo;

-- name: ctr_por_dispositivo
SELECT
    device                                                           AS dispositivo,
    email_variant                                                    AS variante,
    SUM(delivered)                                                   AS entregados,
    ROUND(100.0 * SUM(clicked) / SUM(delivered), 2)                  AS ctr_pct
FROM envios
GROUP BY device, email_variant
ORDER BY device, email_variant;
