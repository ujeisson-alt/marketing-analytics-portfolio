-- =====================================================================
-- Embudo de e-commerce y atribución con eventos de GA4
-- Motor: SQLite. En BigQuery la lógica es la misma sobre `events_*`
-- (cambiando ga_session_id por el parámetro de evento correspondiente).
-- "-- name: setup_*" = instrucción que crea objetos; el resto devuelve tablas.
-- =====================================================================

-- name: setup_vista_sesiones
-- Agrupación de canales al estilo "Default Channel Group" de GA4
CREATE VIEW IF NOT EXISTS eventos AS
SELECT
    *,
    user_pseudo_id || '-' || ga_session_id AS session_key,
    CASE
        WHEN session_source = '(direct)' AND session_medium IN ('(none)', '(not set)') THEN 'Direct'
        WHEN session_medium = 'cpc'         THEN 'Paid Search'
        WHEN session_medium = 'organic'     THEN 'Organic Search'
        WHEN session_medium = 'paid_social' AND session_source = 'tiktok' THEN 'Paid Social - TikTok'
        WHEN session_medium = 'paid_social' THEN 'Paid Social - Meta'
        WHEN session_medium = 'social'      THEN 'Organic Social'
        WHEN session_medium = 'email'       THEN 'Email'
        WHEN session_medium = 'referral'    THEN 'Referral'
        ELSE 'Unassigned'
    END AS canal
FROM ga4_events;

-- name: embudo_general
WITH pasos AS (
    SELECT 1 AS orden, 'session_start' AS paso UNION ALL
    SELECT 2, 'view_item' UNION ALL SELECT 3, 'add_to_cart' UNION ALL
    SELECT 4, 'begin_checkout' UNION ALL SELECT 5, 'purchase'
),
conteo AS (
    SELECT p.orden, p.paso, COUNT(DISTINCT e.session_key) AS sesiones
    FROM pasos p LEFT JOIN eventos e ON e.event_name = p.paso
    GROUP BY p.orden, p.paso
)
SELECT
    orden,
    paso,
    sesiones,
    ROUND(100.0 * sesiones / FIRST_VALUE(sesiones) OVER (ORDER BY orden), 2)  AS pct_del_total,
    ROUND(100.0 * sesiones / LAG(sesiones) OVER (ORDER BY orden), 1)          AS pct_paso_anterior,
    ROUND(100.0 - 100.0 * sesiones / LAG(sesiones) OVER (ORDER BY orden), 1)  AS abandono_pct
FROM conteo
ORDER BY orden;

-- name: embudo_por_dispositivo
SELECT
    device_category                                                         AS dispositivo,
    COUNT(DISTINCT session_key)                                             AS sesiones,
    COUNT(DISTINCT CASE WHEN event_name = 'add_to_cart'    THEN session_key END) AS add_to_cart,
    COUNT(DISTINCT CASE WHEN event_name = 'begin_checkout' THEN session_key END) AS begin_checkout,
    COUNT(DISTINCT CASE WHEN event_name = 'purchase'       THEN session_key END) AS compras,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN event_name = 'purchase' THEN session_key END)
          / COUNT(DISTINCT CASE WHEN event_name = 'begin_checkout' THEN session_key END), 1) AS checkout_a_compra_pct,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN event_name = 'purchase' THEN session_key END)
          / COUNT(DISTINCT session_key), 2)                                 AS tasa_conversion_pct
FROM eventos
GROUP BY device_category
ORDER BY sesiones DESC;

-- name: conversion_por_canal
SELECT
    canal,
    COUNT(DISTINCT session_key)                                            AS sesiones,
    COUNT(DISTINCT CASE WHEN ga_session_number = 1 THEN session_key END)   AS sesiones_nuevas,
    COUNT(DISTINCT transaction_id)                                         AS compras,
    ROUND(100.0 * COUNT(DISTINCT transaction_id) / COUNT(DISTINCT session_key), 2) AS tasa_conversion_pct,
    ROUND(SUM(purchase_revenue), 0)                                        AS ingresos_last_click
FROM eventos
GROUP BY canal
ORDER BY ingresos_last_click DESC;

-- name: first_vs_last_click_sql
-- Atribución de un solo toque con funciones de ventana: ¿qué canal ABRIÓ y qué canal CERRÓ cada venta?
WITH compradores AS (
    SELECT user_pseudo_id, SUM(purchase_revenue) AS ingreso
    FROM eventos WHERE event_name = 'purchase' GROUP BY user_pseudo_id
),
sesiones AS (
    SELECT DISTINCT e.user_pseudo_id, e.ga_session_number, e.canal
    FROM eventos e JOIN compradores c USING (user_pseudo_id)
    WHERE e.event_name = 'session_start'
),
ordenadas AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY ga_session_number ASC)  AS n_asc,
           ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY ga_session_number DESC) AS n_desc
    FROM sesiones
)
SELECT
    o.canal,
    ROUND(SUM(CASE WHEN o.n_asc  = 1 THEN c.ingreso ELSE 0 END), 0) AS ingresos_first_click,
    ROUND(SUM(CASE WHEN o.n_desc = 1 THEN c.ingreso ELSE 0 END), 0) AS ingresos_last_click
FROM ordenadas o JOIN compradores c USING (user_pseudo_id)
GROUP BY o.canal
ORDER BY ingresos_first_click DESC;

-- name: sesiones_hasta_comprar
SELECT
    ga_session_number                       AS sesion_de_compra,
    COUNT(*)                                AS compras,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_compras
FROM eventos
WHERE event_name = 'purchase'
GROUP BY ga_session_number
ORDER BY ga_session_number;
