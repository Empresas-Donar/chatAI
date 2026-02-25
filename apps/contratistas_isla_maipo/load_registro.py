from core.cleaners import clean_boolean, clean_date, clean_enumlist
from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_registro"
CSV = "data/contratistas_isla_maipo/raw/registro.csv"


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
                            id_registro, campo, fecha, contratista, cc,
                            labor, tipo_de_registro, trabajador, jornada,
                            bonificacion, bono_especial_piso, horas_extras,
                            trato, dia_habil, contador, dia
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id_registro) DO UPDATE SET
                            campo = EXCLUDED.campo,
                            fecha = EXCLUDED.fecha,
                            contratista = EXCLUDED.contratista,
                            cc = EXCLUDED.cc,
                            labor = EXCLUDED.labor,
                            tipo_de_registro = EXCLUDED.tipo_de_registro,
                            trabajador = EXCLUDED.trabajador,
                            jornada = EXCLUDED.jornada,
                            bonificacion = EXCLUDED.bonificacion,
                            bono_especial_piso = EXCLUDED.bono_especial_piso,
                            horas_extras = EXCLUDED.horas_extras,
                            trato = EXCLUDED.trato,
                            dia_habil = EXCLUDED.dia_habil,
                            contador = EXCLUDED.contador,
                            dia = EXCLUDED.dia
                        """,
                        (
                            row.get("id_registro") or None,
                            row.get("campo") or "Isla de Maipo",
                            clean_date(row.get("fecha")),
                            row.get("contratista") or None,
                            row.get("cc") or None,
                            row.get("labor") or None,
                            row.get("tipo_de_registro") or None,
                            clean_enumlist(row.get("trabajador")),
                            row.get("jornada") or 1,
                            row.get("bonificacion") or None,
                            row.get("bono_especial_piso") or 0,
                            row.get("horas_extras") or 0,
                            row.get("trato") or None,
                            clean_boolean(row.get("dia_habil")),
                            row.get("contador") or None,
                            row.get("dia") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} filas procesadas.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
