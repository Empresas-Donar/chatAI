from core.cleaners import clean_boolean, clean_date
from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_resumen"
CSV = "data/contratistas_isla_maipo/raw/resumen.csv"


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
                            id_resumen, id_registro, campo, fecha, contratista,
                            cc, labor, trabajador, jornada, bonificacion,
                            bono_especial_piso, horas_extras, trato,
                            unidades_trato, base_trato, dia_habil,
                            id_busqueda, nombre_labor
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id_resumen) DO UPDATE SET
                            id_registro = EXCLUDED.id_registro,
                            campo = EXCLUDED.campo,
                            fecha = EXCLUDED.fecha,
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
                            id_busqueda = EXCLUDED.id_busqueda,
                            nombre_labor = EXCLUDED.nombre_labor
                        """,
                        (
                            row.get("id_resumen") or None,
                            row.get("id_registro") or None,
                            row.get("campo") or None,
                            clean_date(row.get("fecha")),
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
                            row.get("id_busqueda") or None,
                            row.get("nombre_labor") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} filas procesadas.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
