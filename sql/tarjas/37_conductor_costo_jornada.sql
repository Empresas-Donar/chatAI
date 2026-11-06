-- Precio propio de la jornada de un conductor.
-- NULL sigue la tarifa de tarjas_labor y el carnet de la ficha.
-- Un monto escrito reemplaza esa jornada. Las tarjas ya guardadas no se reescriben.

ALTER TABLE appsheet.tarjas_esquema_tractorista
    ADD COLUMN IF NOT EXISTS costo_9h NUMERIC,
    ADD COLUMN IF NOT EXISTS costo_75 NUMERIC;

COMMENT ON COLUMN appsheet.tarjas_esquema_tractorista.costo_9h IS
    'Jornada normal de 9 h de este conductor. NULL usa la tarifa y el carnet.';
COMMENT ON COLUMN appsheet.tarjas_esquema_tractorista.costo_75 IS
    'Jornada normal de 7,5 h de este conductor. NULL usa la tarifa y el carnet.';

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
    v_costo_9h NUMERIC;
    v_costo_75 NUMERIC;
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
    SELECT e.esquema, e.con_operador, e.carnet, e.costo_9h, e.costo_75
      INTO v_esquema, v_con, v_tiene_carnet, v_costo_9h, v_costo_75
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
        v_costo_9h := NULL;
        v_costo_75 := NULL;
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

    IF v_horas_jornada = 9 AND v_costo_9h IS NOT NULL THEN
        v_base := v_costo_9h;
        v_carnet := 0;
    ELSIF v_horas_jornada = 7.5 AND v_costo_75 IS NOT NULL THEN
        v_base := v_costo_75;
        v_carnet := 0;
    END IF;

    IF v_horas > 0 AND v_horas < v_horas_jornada THEN
        IF v_horas = 7.5 AND v_horas_jornada = 9 AND v_costo_75 IS NOT NULL THEN
            RETURN v_costo_75;
        END IF;
        RETURN ROUND((v_base + v_carnet) * v_horas / v_horas_jornada, 0);
    END IF;
    RETURN v_base + v_carnet;
END;
$function$;

COMMENT ON FUNCTION appsheet.costo_tractorista(TEXT, TEXT, NUMERIC, DATE) IS
    'Costo tractorista desde tarjas_labor. Carnet 6.000 solo si el esquema lo tiene. costo_9h y costo_75, si están, reemplazan esa jornada.';
