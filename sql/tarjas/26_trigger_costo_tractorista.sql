-- =============================================================================
-- TARJAS: costo de tractorista al guardar
--
-- El precio sale de appsheet.tarjas_labor (tipo Tractorista). No hay una
-- segunda tabla de tarifas.
--
--   Jornada Tractor normal
--     lunes a viernes, con operador:  valor 66.000 + 6.000 carnet, en 9 h
--     lunes a sábado, con operador:   valor 55.000 + 6.000 carnet, en 7,5 h
--     sin operador (antes Angel Celis): 27.600 en 9 h, 23.000 en 7,5 h, sin carnet
--   Jornada Tractor simple / Chico / Gilberto: 25.000
--   Hora Extra:              3.400 por hora
--   Labor Extraordinaria:    10.000
--   OPERARIO SOLO:           60.000
--
-- appsheet.tarjas_esquema_tractorista dice el horario de cada persona.
-- Quien no está ahí se toma como lunes a viernes con operador.
-- Operario Fundo es sin operador.
--
-- Al insertar o cambiar fecha, trabajador, labor, horas o tipo_pago, el
-- trigger llena total_tractor, total_trabajado y total_pagar. Aprobar no
-- recalcula.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS appsheet.tarjas_esquema_tractorista (
    id              TEXT PRIMARY KEY,
    trabajador      TEXT NOT NULL,
    desde           DATE NOT NULL,
    hasta           DATE,
    esquema         TEXT NOT NULL,
    con_operador    BOOLEAN NOT NULL,
    carnet          BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT esquema_tractorista_esquema
        CHECK (esquema IN ('lun_vie', 'lun_sab')),
    CONSTRAINT esquema_tractorista_rango
        CHECK (hasta IS NULL OR hasta >= desde),
    UNIQUE (trabajador, desde)
);

COMMENT ON TABLE appsheet.tarjas_esquema_tractorista IS
    'Horario vigente de cada tractorista. lun_vie = 9 h, lun_sab = 7,5 h. carnet suma 6.000 en la jornada normal.';

ALTER TABLE appsheet.tarjas_esquema_tractorista
    ADD COLUMN IF NOT EXISTS carnet BOOLEAN NOT NULL DEFAULT TRUE;

INSERT INTO appsheet.tarjas_esquema_tractorista
    (id, trabajador, desde, hasta, esquema, con_operador, carnet)
VALUES
    ('andres-diaz',     'ANDRÉS DÍAZ HERRRRA',          DATE '2026-01-01', NULL, 'lun_vie', TRUE,  TRUE),
    ('cristian',        'Cristian Gonzalez',            DATE '2026-01-01', NULL, 'lun_vie', TRUE,  FALSE),
    ('felipe',          'Felipe Cordova',               DATE '2026-01-01', NULL, 'lun_vie', TRUE,  TRUE),
    ('gabriel',         'Gabriel Necupil',              DATE '2026-01-01', NULL, 'lun_vie', TRUE,  TRUE),
    ('luis-bravo',      'Luis Bravo Huerta',            DATE '2026-01-01', NULL, 'lun_vie', TRUE,  TRUE),
    ('luis-ivan',       'LUIS IVÁN CONTRERAS PERALTA',  DATE '2026-01-01', NULL, 'lun_vie', TRUE,  TRUE),
    ('nivaldo',         'NIVALDO MALDONADO VALENZUELA', DATE '2026-01-01', NULL, 'lun_vie', TRUE,  TRUE),
    ('operario-fundo',  'Operario Fundo',               DATE '2026-01-01', NULL, 'lun_vie', FALSE, FALSE)
ON CONFLICT (id) DO UPDATE SET
    trabajador = EXCLUDED.trabajador,
    desde = EXCLUDED.desde,
    hasta = EXCLUDED.hasta,
    esquema = EXCLUDED.esquema,
    con_operador = EXCLUDED.con_operador,
    carnet = EXCLUDED.carnet;

-- El catálogo de AppSheet tenía Operario Solo en 30.000. La regla es 60.000.
UPDATE appsheet.tarjas_labor
   SET valor = 60000,
       valor_c_operador_lunes_viernes = '60000',
       valor_s_operador_lunes_viernes = '60000',
       "valor_c_Operador_lunes_sabado" = '60000',
       valor_s_operador_lunes_sabado = '60000'
 WHERE lower(trim(nombre)) = 'operario solo'
   AND lower(trim(COALESCE(tipo, ''))) = 'tractorista';

CREATE OR REPLACE FUNCTION appsheet.costo_tractorista(
    p_trabajador TEXT,
    p_labor TEXT,
    p_horas NUMERIC,
    p_fecha DATE
) RETURNS NUMERIC
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE
    v_esquema TEXT := 'lun_vie';
    v_con BOOLEAN := TRUE;
    v_tiene_carnet BOOLEAN := TRUE;
    v_labor TEXT := lower(trim(COALESCE(p_labor, '')));
    v_lookup TEXT;
    v_horas NUMERIC := COALESCE(p_horas, 0);
    v_valor NUMERIC;
    v_cv NUMERIC;
    v_sv NUMERIC;
    v_cs NUMERIC;
    v_ss NUMERIC;
    v_base NUMERIC;
    v_carnet NUMERIC := 0;
    v_horas_jornada NUMERIC;
BEGIN
    SELECT e.esquema, e.con_operador, e.carnet
      INTO v_esquema, v_con, v_tiene_carnet
      FROM appsheet.tarjas_esquema_tractorista e
     WHERE e.trabajador = p_trabajador
       AND e.desde <= p_fecha
       AND (e.hasta IS NULL OR e.hasta >= p_fecha)
     ORDER BY e.desde DESC
     LIMIT 1;

    IF NOT FOUND THEN
        v_esquema := 'lun_vie';
        v_con := TRUE;
        v_tiene_carnet := TRUE;
    END IF;

    IF v_labor LIKE '%gilberto%' OR v_labor LIKE '%chico%'
       OR v_labor = 'jornada tractor simple' THEN
        v_lookup := 'jornada tractor simple';
    ELSIF v_labor LIKE '%hora extra%' THEN
        v_lookup := 'hora extra';
    ELSIF v_labor LIKE '%extraordinaria%' THEN
        v_lookup := 'labor extraordinaria';
    ELSIF v_labor LIKE '%operario solo%' THEN
        v_lookup := 'operario solo';
    ELSE
        v_lookup := 'jornada tractor normal';
        IF v_labor LIKE '%sin operador%' OR v_labor LIKE '%angel%' THEN
            v_con := FALSE;
        END IF;
    END IF;

    SELECT l.valor,
           CASE WHEN l.valor_c_operador_lunes_viernes ~ '^[0-9]+(\.[0-9]+)?$'
                THEN l.valor_c_operador_lunes_viernes::numeric END,
           CASE WHEN l.valor_s_operador_lunes_viernes ~ '^[0-9]+(\.[0-9]+)?$'
                THEN l.valor_s_operador_lunes_viernes::numeric END,
           CASE WHEN l."valor_c_Operador_lunes_sabado" ~ '^[0-9]+(\.[0-9]+)?$'
                THEN l."valor_c_Operador_lunes_sabado"::numeric END,
           CASE WHEN l.valor_s_operador_lunes_sabado ~ '^[0-9]+(\.[0-9]+)?$'
                THEN l.valor_s_operador_lunes_sabado::numeric END
      INTO v_valor, v_cv, v_sv, v_cs, v_ss
      FROM appsheet.tarjas_labor l
     WHERE lower(trim(l.nombre)) = v_lookup
       AND lower(trim(COALESCE(l.tipo, ''))) = 'tractorista'
     ORDER BY l.id_labor
     LIMIT 1;

    IF NOT FOUND OR v_valor IS NULL THEN
        RETURN NULL;
    END IF;

    IF v_lookup = 'hora extra' THEN
        RETURN ROUND(v_horas * v_valor, 0);
    ELSIF v_lookup <> 'jornada tractor normal' THEN
        RETURN v_valor;
    END IF;

    IF v_con AND v_esquema = 'lun_sab' THEN
        v_base := COALESCE(v_cs, v_valor);
        v_horas_jornada := 7.5;
        v_carnet := CASE WHEN v_tiene_carnet THEN 6000 ELSE 0 END;
    ELSIF v_con THEN
        v_base := COALESCE(v_cv, v_valor);
        v_horas_jornada := 9;
        v_carnet := CASE WHEN v_tiene_carnet THEN 6000 ELSE 0 END;
    ELSIF v_esquema = 'lun_sab' THEN
        v_base := COALESCE(v_ss, v_sv, v_valor);
        v_horas_jornada := 7.5;
        v_carnet := 0;
    ELSE
        v_base := COALESCE(v_sv, v_valor);
        v_horas_jornada := 9;
        v_carnet := 0;
    END IF;

    IF v_horas > 0 AND v_horas < v_horas_jornada THEN
        RETURN ROUND(v_base * v_horas / v_horas_jornada, 0) + v_carnet;
    END IF;
    RETURN v_base + v_carnet;
END;
$function$;

COMMENT ON FUNCTION appsheet.costo_tractorista(TEXT, TEXT, NUMERIC, DATE) IS
    'Costo tractorista desde tarjas_labor. Carnet 6.000 solo si el esquema de la persona lo tiene.';

CREATE OR REPLACE FUNCTION appsheet.aplicar_costo_tractorista()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_fecha DATE;
    v_costo NUMERIC;
    v_manual NUMERIC;
    v_duplicada BOOLEAN;
BEGIN
    IF lower(trim(COALESCE(NEW.tipo_pago, ''))) IS DISTINCT FROM 'tractorista' THEN
        RETURN NEW;
    END IF;

    -- AppSheet rewrites the whole row when the user edits the payment.
    -- If the day itself did not change, keep the amount they typed.
    IF TG_OP = 'UPDATE'
       AND NEW.fecha IS NOT DISTINCT FROM OLD.fecha
       AND NEW.trabajador IS NOT DISTINCT FROM OLD.trabajador
       AND NEW.labor IS NOT DISTINCT FROM OLD.labor
       AND NEW.horas_trabajadas IS NOT DISTINCT FROM OLD.horas_trabajadas
       AND lower(trim(COALESCE(NEW.tipo_pago, '')))
           IS NOT DISTINCT FROM lower(trim(COALESCE(OLD.tipo_pago, '')))
    THEN
        IF NEW.total_pagar IS DISTINCT FROM OLD.total_pagar THEN
            v_manual := NEW.total_pagar;
        ELSIF NEW.total_tractor IS DISTINCT FROM OLD.total_tractor THEN
            v_manual := NEW.total_tractor;
        ELSIF NEW.total_trabajado IS DISTINCT FROM OLD.total_trabajado THEN
            v_manual := NEW.total_trabajado;
        ELSE
            RETURN NEW;
        END IF;
        NEW.total_tractor := v_manual;
        NEW.total_trabajado := v_manual;
        NEW.total_pagar := v_manual;
        RETURN NEW;
    END IF;

    BEGIN
        v_fecha := TO_DATE(SPLIT_PART(NEW.fecha, ' ', 1), 'MM/DD/YYYY');
    EXCEPTION WHEN OTHERS THEN
        RETURN NEW;
    END;

    -- Misma persona, fecha, labor, campo y CC: la segunda fila no se paga.
    -- Otro predio u otro cuartel el mismo día es otra jornada.
    SELECT EXISTS (
        SELECT 1
          FROM appsheet.tarjas_pagos p
         WHERE p.trabajador = NEW.trabajador
           AND p.fecha = NEW.fecha
           AND p.labor IS NOT DISTINCT FROM NEW.labor
           AND p.nombre_campo IS NOT DISTINCT FROM NEW.nombre_campo
           AND p.cuartel_cc IS NOT DISTINCT FROM NEW.cuartel_cc
           AND p."id_Resumen" IS DISTINCT FROM NEW."id_Resumen"
           AND lower(trim(COALESCE(p.tipo_pago, ''))) = 'tractorista'
           AND COALESCE(p.total_tractor, 0) > 0
    ) INTO v_duplicada;

    IF v_duplicada AND COALESCE(NEW.total_tractor, 0) = 0 THEN
        NEW.total_trabajado := 0;
        NEW.total_pagar := 0;
        RETURN NEW;
    END IF;

    v_costo := appsheet.costo_tractorista(
        NEW.trabajador, NEW.labor, NEW.horas_trabajadas, v_fecha
    );
    IF v_costo IS NULL THEN
        RETURN NEW;
    END IF;

    NEW.total_tractor := v_costo;
    NEW.total_trabajado := v_costo;
    NEW.total_pagar := v_costo;
    RETURN NEW;
END;
$function$;

COMMENT ON FUNCTION appsheet.aplicar_costo_tractorista() IS
    'Trigger de tractorista: escribe total_tractor, total_trabajado y total_pagar. Activo como trg_costo_tractorista.';

DROP TRIGGER IF EXISTS trg_costo_tractorista ON appsheet.tarjas_pagos;

CREATE TRIGGER trg_costo_tractorista
BEFORE INSERT OR UPDATE OF fecha, trabajador, labor, horas_trabajadas, tipo_pago,
    total_tractor, total_trabajado, total_pagar
ON appsheet.tarjas_pagos
FOR EACH ROW
WHEN (lower(trim(COALESCE(NEW.tipo_pago, ''))) = 'tractorista')
EXECUTE FUNCTION appsheet.aplicar_costo_tractorista();

COMMENT ON TRIGGER trg_costo_tractorista ON appsheet.tarjas_pagos IS
    'Activo solo si tipo_pago es Tractorista. No modifica trato, al día ni otras tarjas.';

DROP TABLE IF EXISTS appsheet.tarjas_tarifa_tractorista;

COMMIT;
