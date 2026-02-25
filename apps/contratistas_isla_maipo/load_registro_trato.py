from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_registro_trato"
CSV = "data/contratistas_isla_maipo/raw/registro_trato.csv"


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
                            id_registro_trato, id_registro, contratista,
                            trabajador, unidades_trato, base, id_busqueda
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id_registro_trato) DO UPDATE SET
                            id_registro = EXCLUDED.id_registro,
                            contratista = EXCLUDED.contratista,
                            trabajador = EXCLUDED.trabajador,
                            unidades_trato = EXCLUDED.unidades_trato,
                            base = EXCLUDED.base,
                            id_busqueda = EXCLUDED.id_busqueda
                        """,
                        (
                            row.get("id_registro_trato") or None,
                            row.get("id_registro") or None,
                            row.get("contratista") or None,
                            row.get("trabajador") or None,
                            row.get("unidades_trato") or None,
                            row.get("base") or 0,
                            row.get("id_busqueda") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} filas procesadas.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
