-- =============================================================================
-- BigQuery: apuntes analíticos desglosados por centro de costo
-- Project/dataset: ace-scarab-484515-v1.odoo_data
-- Issue: #144, #148
--
-- Explota analytic_distribution (un CC por fila) sobre Reporte_Analitico.
-- Si el JSON directo viene vacío, resuelve el modelo via
-- Modelos_Distribucion_Analitica (analytic_distribution_code_id).
--
-- producto: nombre del insumo/producto de la línea.
-- 1) Catálogo Producto (template) solo si el nombre aparece en la etiqueta
--    (evita colisiones id variante vs id template).
-- 2) Fallback: limpia prefijos Odoo del campo name (OC, MO, [código]).
-- 3) Último recurso: nombre del catálogo aunque no esté en la etiqueta.
-- Variantes_del_producto no está exportada; Producto tiene ~96 templates.
--
-- referencia_interna: Producto.default_code del mismo JOIN por product_id.
--   Cobertura baja (~3% de filas) por la misma limitación de catálogo que
--   afecta a producto: solo ~96 templates vs ~2.100 product_id distintos.
-- producto_con_referencia: referencia_interna + " - " + producto, o solo
--   producto cuando no hay referencia interna.
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
),
con_nombre AS (
    SELECT
        ad.*,
        COALESCE(
            JSON_VALUE(p.name, '$.es_CL'),
            JSON_VALUE(p.name, '$.en_US')
        ) AS _producto_catalogo,
        NULLIF(TRIM(p.default_code), '') AS referencia_interna,
        NULLIF(TRIM(REGEXP_REPLACE(
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                COALESCE(ad.name, ''),
                                r'(?i)[\r\n]*Rounding Adjustment.*$',
                                ''
                            ),
                            r'(?i)(\(Modification of past move\)|\(NEGATIVE INVENTORY\)|,?\s*ENTREGA\s+\d{1,2}[-/]\d{1,2}[-/]\d{2,4}.*$)',
                            ''
                        ),
                        r'(?i)^(Correction of\s+|Revaluation of\s+|Cantidad de producto[^:\-]*[-:]?\s*)',
                        ''
                    ),
                    r'(?i)^[A-ZÁÉÍÓÚÑÜ0-9._-]+/[A-ZÁÉÍÓÚÑÜ0-9._-]+/[0-9A-Z-]+\s*[-:]\s*',
                    ''
                ),
                r'(?i)^[A-Z0-9_-]+:\s*',
                ''
            ),
            r'^\[.*?\]\s*',
            ''
        )), '') AS _producto_etiqueta
    FROM apuntes_desarmados ad
    LEFT JOIN `ace-scarab-484515-v1.odoo_data.Producto` p
        ON p.id = ad.product_id
),
con_producto AS (
    SELECT
        cn.* EXCEPT(_producto_catalogo, _producto_etiqueta),
        SUM(cn.porcentaje_asignado) OVER (PARTITION BY cn.id) AS pct_total_distribucion,
        (cn.balance * (cn.porcentaje_asignado / 100.0)) AS balance_asignado,
        (cn.debit  * (cn.porcentaje_asignado / 100.0)) AS debito_asignado,
        (cn.credit * (cn.porcentaje_asignado / 100.0)) AS credito_asignado,
        CASE cn.company_id
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
            ELSE CONCAT('Desconocida (id=', CAST(cn.company_id AS STRING), ')')
        END AS empresa_nombre,
        cc.name       AS cc_nombre,
        cc.company_id AS cc_company_id,
        cc.code       AS cc_codigo,
        cc.active     AS cc_activo,
        COALESCE(
            CASE
                WHEN cn._producto_catalogo IS NOT NULL
                 AND STRPOS(UPPER(COALESCE(cn.name, '')), UPPER(cn._producto_catalogo)) > 0
                THEN cn._producto_catalogo
            END,
            cn._producto_etiqueta,
            cn._producto_catalogo
        ) AS producto
    FROM con_nombre cn
    LEFT JOIN `ace-scarab-484515-v1.odoo_data.CC_analiticos` cc
        ON SAFE_CAST(cn.cc_id_str AS INT64) = cc.id
)
SELECT
    cp.*,
    CASE
        WHEN cp.referencia_interna IS NOT NULL
            THEN CONCAT(cp.referencia_interna, ' - ', cp.producto)
        ELSE cp.producto
    END AS producto_con_referencia
FROM con_producto cp
;
