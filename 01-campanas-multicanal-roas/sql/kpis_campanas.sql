-- =====================================================================
-- KPIs de campañas pagadas multicanal  |  Motor: SQLite (compatible con
-- PostgreSQL / BigQuery cambiando strftime por DATE_TRUNC / FORMAT_DATE)
-- Tabla: campanas(fecha, plataforma, campana, objetivo, spend, impressions,
--                 clicks, conversions, revenue)
-- Cada consulta empieza con "-- name:" para que src/analisis.py la ejecute.
-- =====================================================================

-- name: kpis_por_plataforma
SELECT
    plataforma,
    SUM(spend)                                            AS inversion,
    SUM(revenue)                                          AS ingresos,
    ROUND(SUM(revenue) * 1.0 / SUM(spend), 2)             AS roas,
    ROUND(SUM(spend)   * 1.0 / SUM(conversions), 0)       AS cpa,
    ROUND(100.0 * SUM(clicks) / SUM(impressions), 2)      AS ctr_pct,
    ROUND(SUM(spend)   * 1.0 / SUM(clicks), 0)            AS cpc,
    ROUND(1000.0 * SUM(spend) / SUM(impressions), 0)      AS cpm,
    ROUND(100.0 * SUM(conversions) / SUM(clicks), 2)      AS cvr_pct,
    ROUND(100.0 * SUM(spend) / (SELECT SUM(spend) FROM campanas), 1) AS participacion_inversion_pct
FROM campanas
GROUP BY plataforma
ORDER BY roas DESC;

-- name: kpis_por_campana
SELECT
    plataforma,
    campana,
    objetivo,
    SUM(spend)                                       AS inversion,
    SUM(revenue)                                     AS ingresos,
    SUM(conversions)                                 AS conversiones,
    ROUND(SUM(revenue) * 1.0 / SUM(spend), 2)        AS roas,
    ROUND(SUM(spend) * 1.0 / SUM(conversions), 0)    AS cpa,
    ROUND(100.0 * SUM(clicks) / SUM(impressions), 2) AS ctr_pct,
    ROUND(100.0 * SUM(conversions) / SUM(clicks), 2) AS cvr_pct,
    RANK() OVER (ORDER BY SUM(revenue) * 1.0 / SUM(spend) DESC) AS ranking_roas
FROM campanas
GROUP BY plataforma, campana, objetivo
ORDER BY roas DESC;

-- name: tendencia_mensual
SELECT
    strftime('%Y-%m', fecha)                          AS mes,
    plataforma,
    SUM(spend)                                        AS inversion,
    SUM(revenue)                                      AS ingresos,
    ROUND(SUM(revenue) * 1.0 / SUM(spend), 2)         AS roas
FROM campanas
GROUP BY mes, plataforma
ORDER BY mes, plataforma;

-- name: variacion_mes_a_mes
WITH mensual AS (
    SELECT strftime('%Y-%m', fecha) AS mes, SUM(revenue) AS ingresos, SUM(spend) AS inversion
    FROM campanas GROUP BY mes
)
SELECT
    mes,
    ingresos,
    inversion,
    ROUND(100.0 * (ingresos - LAG(ingresos) OVER (ORDER BY mes)) / LAG(ingresos) OVER (ORDER BY mes), 1) AS var_ingresos_pct
FROM mensual
ORDER BY mes;

-- name: desempeno_dia_semana
SELECT
    CASE strftime('%w', fecha)
        WHEN '0' THEN '7-Domingo' WHEN '1' THEN '1-Lunes' WHEN '2' THEN '2-Martes'
        WHEN '3' THEN '3-Miércoles' WHEN '4' THEN '4-Jueves' WHEN '5' THEN '5-Viernes'
        ELSE '6-Sábado' END                            AS dia_semana,
    ROUND(AVG(revenue), 0)                             AS ingreso_promedio_campana_dia,
    ROUND(SUM(revenue) * 1.0 / SUM(spend), 2)          AS roas
FROM campanas
GROUP BY dia_semana
ORDER BY dia_semana;

-- name: impacto_dia_de_la_madre
SELECT
    CASE WHEN fecha BETWEEN '2026-04-25' AND '2026-05-10' THEN 'Temporada Día de la Madre'
         ELSE 'Resto del semestre' END                 AS periodo,
    COUNT(DISTINCT fecha)                              AS dias,
    ROUND(SUM(revenue) * 1.0 / COUNT(DISTINCT fecha), 0) AS ingreso_diario_promedio,
    ROUND(SUM(revenue) * 1.0 / SUM(spend), 2)          AS roas
FROM campanas
GROUP BY periodo;
