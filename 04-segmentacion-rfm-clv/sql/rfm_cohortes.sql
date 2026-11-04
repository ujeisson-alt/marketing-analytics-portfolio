-- =====================================================================
-- RFM, cohortes y concentración de ventas  |  Motor: SQLite
-- Tablas: pedidos(order_id, customer_id, order_date, category, gross_sales,
--                 discount, net_sales, gross_margin)
--         clientes(customer_id, acquisition_channel, city, first_order_date)
-- Fecha de corte del análisis: 2026-06-30
-- =====================================================================

-- name: rfm_base
SELECT
    customer_id,
    CAST(julianday('2026-06-30') - julianday(MAX(order_date)) AS INTEGER) AS recencia_dias,
    COUNT(DISTINCT order_id)                                             AS frecuencia,
    ROUND(SUM(net_sales), 0)                                             AS monto,
    ROUND(SUM(gross_margin), 0)                                          AS margen,
    MIN(order_date)                                                      AS primera_compra,
    MAX(order_date)                                                      AS ultima_compra
FROM pedidos
GROUP BY customer_id;

-- name: retencion_cohortes
-- % de clientes de cada cohorte (mes de primera compra) que vuelve a comprar k meses después
WITH primera AS (
    SELECT customer_id, strftime('%Y-%m', MIN(order_date)) AS cohorte
    FROM pedidos GROUP BY customer_id
),
actividad AS (
    SELECT DISTINCT p.customer_id, f.cohorte,
           (CAST(strftime('%Y', p.order_date) AS INTEGER) - CAST(substr(f.cohorte, 1, 4) AS INTEGER)) * 12
         + (CAST(strftime('%m', p.order_date) AS INTEGER) - CAST(substr(f.cohorte, 6, 2) AS INTEGER)) AS mes_k
    FROM pedidos p JOIN primera f USING (customer_id)
),
tamano AS (SELECT cohorte, COUNT(*) AS clientes FROM primera GROUP BY cohorte)
SELECT
    a.cohorte,
    t.clientes,
    a.mes_k,
    COUNT(DISTINCT a.customer_id)                              AS activos,
    ROUND(100.0 * COUNT(DISTINCT a.customer_id) / t.clientes, 1) AS retencion_pct
FROM actividad a JOIN tamano t USING (cohorte)
GROUP BY a.cohorte, t.clientes, a.mes_k
ORDER BY a.cohorte, a.mes_k;

-- name: concentracion_pareto
-- ¿Qué % de las ventas genera cada decil de clientes?
WITH ventas AS (
    SELECT customer_id, SUM(net_sales) AS monto FROM pedidos GROUP BY customer_id
),
deciles AS (
    SELECT *, NTILE(10) OVER (ORDER BY monto DESC) AS decil FROM ventas
)
SELECT
    decil,
    COUNT(*)                                                            AS clientes,
    ROUND(SUM(monto), 0)                                                AS ventas,
    ROUND(100.0 * SUM(monto) / (SELECT SUM(monto) FROM ventas), 1)      AS pct_ventas,
    ROUND(100.0 * SUM(SUM(monto)) OVER (ORDER BY decil) / (SELECT SUM(monto) FROM ventas), 1) AS pct_acumulado
FROM deciles
GROUP BY decil
ORDER BY decil;

-- name: valor_por_canal_adquisicion
-- Margen bruto por cliente en sus primeros 12 meses (solo clientes adquiridos hasta jun-2025, que ya cumplieron 12 meses)
WITH primera AS (
    SELECT customer_id, MIN(order_date) AS f0 FROM pedidos GROUP BY customer_id
)
SELECT
    c.acquisition_channel                                              AS canal,
    COUNT(DISTINCT p.customer_id)                                      AS clientes,
    ROUND(1.0 * COUNT(DISTINCT p.order_id) / COUNT(DISTINCT p.customer_id), 2) AS pedidos_por_cliente,
    ROUND(SUM(p.net_sales) / COUNT(DISTINCT p.customer_id), 0)         AS ventas_12m_por_cliente,
    ROUND(SUM(p.gross_margin) / COUNT(DISTINCT p.customer_id), 0)      AS margen_12m_por_cliente
FROM pedidos p
JOIN primera f USING (customer_id)
JOIN clientes c USING (customer_id)
WHERE f.f0 <= '2025-06-30'
  AND julianday(p.order_date) - julianday(f.f0) < 365
GROUP BY c.acquisition_channel
ORDER BY margen_12m_por_cliente DESC;
