from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_trabajadores"
CSV = "data/contratistas_isla_maipo/raw/trabajadores.csv"


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
                            id_trabajador, nombre_trabajador, campo,
                            contratista, ingresar_nombre, rut
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id_trabajador) DO UPDATE SET
                            nombre_trabajador = EXCLUDED.nombre_trabajador,
                            campo = EXCLUDED.campo,
                            contratista = EXCLUDED.contratista,
                            ingresar_nombre = EXCLUDED.ingresar_nombre,
                            rut = EXCLUDED.rut
                        """,
                        (
                            row.get("id_trabajador") or None,
                            row.get("nombre_trabajador") or None,
                            row.get("campo") or "Isla de Maipo",
                            row.get("contratista") or None,
                            row.get("ingresar_nombre") or None,
                            row.get("rut") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} filas procesadas.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
