from core.cleaners import clean_boolean, clean_date
from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_pagos"
CSV = "data/contratistas_isla_maipo/raw/pagos.csv"


def run():
    df = load_csv(CSV)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    cur.execute(
                        f"""
                        INSERT INTO {TABLE} (
                            id_resumen, campo, fecha, mes, contratista, cc,
                            labor, trabajador, jornada, bonificacion,
                            bono_especial_piso, horas_extras, trato,
                            unidades_trato, base_trato, dia_habil, nombre_labor,
                            valor_bonificacion_2, bono_extra, valor_jornada,
                            total_unidades, valor_trato, trabajador_jornal_mas_bonos,
                            trabajador_tratos, total_trabajador, contratista_jornada,
                            contratista_tratos, total_contratista, total_a_pagar,
                            total_jornada, dia, empresa, cultivo, dia_de_ayer, tipo_de_pago
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (id_resumen) DO UPDATE SET
                            campo = EXCLUDED.campo,
                            fecha = EXCLUDED.fecha,
                            mes = EXCLUDED.mes,
                            contratista = EXCLUDED.contratista,
                            cc = EXCLUDED.cc,
                            labor = EXCLUDED.labor,
                            trabajador = EXCLUDED.trabajador,
                            jornada = EXCLUDED.jornada,
                            bonificacion = EXCLUDED.bonificacion,
                            bono_especial_piso = EXCLUDED.bono_especial_piso,
                            horas_extras = EXCLUDED.horas_extras,
                            trato = EXCLUDED.trato,
                            unidades_trato = EXCLUDED.unidades_trato,
                            base_trato = EXCLUDED.base_trato,
                            dia_habil = EXCLUDED.dia_habil,
                            nombre_labor = EXCLUDED.nombre_labor,
                            valor_bonificacion_2 = EXCLUDED.valor_bonificacion_2,
                            bono_extra = EXCLUDED.bono_extra,
                            valor_jornada = EXCLUDED.valor_jornada,
                            total_unidades = EXCLUDED.total_unidades,
                            valor_trato = EXCLUDED.valor_trato,
                            trabajador_jornal_mas_bonos = EXCLUDED.trabajador_jornal_mas_bonos,
                            trabajador_tratos = EXCLUDED.trabajador_tratos,
                            total_trabajador = EXCLUDED.total_trabajador,
                            contratista_jornada = EXCLUDED.contratista_jornada,
                            contratista_tratos = EXCLUDED.contratista_tratos,
                            total_contratista = EXCLUDED.total_contratista,
                            total_a_pagar = EXCLUDED.total_a_pagar,
                            total_jornada = EXCLUDED.total_jornada,
                            dia = EXCLUDED.dia,
                            empresa = EXCLUDED.empresa,
                            cultivo = EXCLUDED.cultivo,
                            dia_de_ayer = EXCLUDED.dia_de_ayer,
                            tipo_de_pago = EXCLUDED.tipo_de_pago
                        """,
                        (
                            row.get("id_resumen") or None,
                            row.get("campo") or None,
                            clean_date(row.get("fecha")),
                            row.get("mes") or None,
                            row.get("contratista") or None,
                            row.get("cc") or None,
                            row.get("labor") or None,
                            row.get("trabajador") or None,
                            row.get("jornada") or None,
                            row.get("bonificacion") or None,
                            row.get("bono_especial_piso") or None,
                            row.get("horas_extras") or None,
                            row.get("trato") or None,
                            row.get("unidades_trato") or None,
                            row.get("base_trato") or None,
                            clean_boolean(row.get("dia_habil")),
                            row.get("nombre_labor") or None,
                            row.get("valor_bonificacion_2") or None,
                            row.get("bono_extra") or None,
                            row.get("valor_jornada") or None,
                            row.get("total_unidades") or None,
                            row.get("valor_trato") or None,
                            row.get("trabajador_jornal_mas_bonos") or None,
                            row.get("trabajador_tratos") or None,
                            row.get("total_trabajador") or None,
                            row.get("contratista_jornada") or None,
                            row.get("contratista_tratos") or None,
                            row.get("total_contratista") or None,
                            row.get("total_a_pagar") or None,
                            row.get("total_jornada") or None,
                            row.get("dia") or None,
                            row.get("empresa") or None,
                            row.get("cultivo") or None,
                            clean_boolean(row.get("dia_de_ayer")),
                            row.get("tipo_de_pago") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} filas procesadas.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
