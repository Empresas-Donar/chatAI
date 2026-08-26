-- =============================================================================
-- BigQuery: apuntes analíticos desglosados por centro de costo
-- Project/dataset: ace-scarab-484515-v1.odoo_data
-- Issue: #144
--
-- Explota analytic_distribution (un CC por fila) sobre Reporte_Analitico.
-- Si el JSON directo viene vacío, resuelve el modelo via
-- Modelos_Distribucion_Analitica (analytic_distribution_code_id).
--
-- producto: nombre en español del catálogo Producto (product.template).
-- Variantes_del_producto no está exportada a odoo_data, así que el JOIN es
-- Producto.id = product_id (mejor esfuerzo; cobertura parcial).
-- =============================================================================
CREATE OR REPLACE VIEW `ace-scarab-484515-v1.odoo_data.vw_apuntes_analiticos_desglosados` AS
WITH normalizado AS (
    SELECT
        r.*,
        (r.analytic_distribution IS NOT NULL
            AND TRIM(r.analytic_distribution) NOT IN ('', '{}')
            AND LOWER(r.analytic_distribution) NOT IN ('false', 'null')
        ) AS tiene_json_directo,
        m.analytic_distribution AS distribucion_via_codigo
    FROM `ace-scarab-484515-v1.odoo_data.Reporte_Analitico` r
    LEFT JOIN `ace-scarab-484515-v1.odoo_data.Modelos_Distribucion_Analitica` m
        ON r.analytic_distribution_code_id = m.analytic_distribution_code_id
),
resuelto AS (
    SELECT
        * EXCEPT(tiene_json_directo, distribucion_via_codigo),
        CASE
            WHEN tiene_json_directo THEN analytic_distribution
            WHEN distribucion_via_codigo IS NOT NULL
                 AND TRIM(distribucion_via_codigo) NOT IN ('', '{}')
                 AND LOWER(distribucion_via_codigo) NOT IN ('false', 'null')
                THEN distribucion_via_codigo
            ELSE NULL
        END AS distribucion_resuelta,
        CASE
            WHEN tiene_json_directo THEN 'directo'
            WHEN distribucion_via_codigo IS NOT NULL THEN 'via_codigo'
            ELSE NULL
        END AS origen_distribucion
    FROM normalizado
),
apuntes_filtrados AS (
    SELECT *
    FROM resuelto
    WHERE distribucion_resuelta IS NOT NULL
),
apuntes_desarmados AS (
    SELECT
        a.*,
        cc_id_str,
        LAX_FLOAT64(PARSE_JSON(a.distribucion_resuelta)[cc_id_str]) AS porcentaje_asignado
    FROM apuntes_filtrados a
    LEFT JOIN UNNEST(REGEXP_EXTRACT_ALL(a.distribucion_resuelta, r'"(\d+)"')) AS cc_id_str
)
SELECT
    ad.*,
    SUM(ad.porcentaje_asignado) OVER (PARTITION BY ad.id) AS pct_total_distribucion,
    (ad.balance * (ad.porcentaje_asignado / 100.0)) AS balance_asignado,
    (ad.debit  * (ad.porcentaje_asignado / 100.0)) AS debito_asignado,
    (ad.credit * (ad.porcentaje_asignado / 100.0)) AS credito_asignado,
    CASE ad.company_id
        WHEN 1  THEN 'Administraciones Donar SpA'
        WHEN 2  THEN 'Agricola Donar Uno SpA'
        WHEN 3  THEN 'Agricola Donar Dos SpA'
        WHEN 5  THEN 'Agricola Los Almendros SpA'
        WHEN 6  THEN 'Servicios FB Limitada'
        WHEN 7  THEN 'Kontrolag SpA'
        WHEN 9  THEN 'Inversiones Donar SpA'
        WHEN 11 THEN 'Inversiones San Juan SpA'
        WHEN 12 THEN 'FD SpA'
        WHEN 15 THEN 'Agricola y Viveros SpA'
        ELSE CONCAT('Desconocida (id=', CAST(ad.company_id AS STRING), ')')
    END AS empresa_nombre,
    cc.name       AS cc_nombre,
    cc.company_id AS cc_company_id,
    cc.code       AS cc_codigo,
    cc.active     AS cc_activo,
    COALESCE(
        JSON_VALUE(p.name, '$.es_CL'),
        JSON_VALUE(p.name, '$.en_US')
    ) AS producto
FROM apuntes_desarmados ad
LEFT JOIN `ace-scarab-484515-v1.odoo_data.CC_analiticos` cc
    ON SAFE_CAST(ad.cc_id_str AS INT64) = cc.id
LEFT JOIN `ace-scarab-484515-v1.odoo_data.Producto` p
    ON p.id = ad.product_id
;
