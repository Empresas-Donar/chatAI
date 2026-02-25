from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
CSV_CULTIVOS = "data/contratistas_isla_maipo/raw/cultivos.csv"
CSV_DETALLE = "data/contratistas_isla_maipo/raw/cultivos_detalle.csv"


def _migrate_table(table: str, csv_path: str):
    df = load_csv(csv_path)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    cur.execute(
                        f"""
                        INSERT INTO {table} (cc, cultivo, tipo, id, valor_odoo)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (cc) DO UPDATE SET
                            cultivo = EXCLUDED.cultivo,
                            tipo = EXCLUDED.tipo,
                            id = EXCLUDED.id,
                            valor_odoo = EXCLUDED.valor_odoo
                        """,
                        (
                            row.get("cc") or None,
                            row.get("cultivo") or None,
                            row.get("tipo") or None,
                            row.get("id") or None,
                            row.get("valor_odoo") or None,
                        ),
                    )
        logger.info(f"{table}: {len(df)} filas procesadas.")
    finally:
        conn.close()


def run():
    _migrate_table("appsheet.contratistas_isla_maipo_cultivos", CSV_CULTIVOS)
    _migrate_table("appsheet.contratistas_isla_maipo_cultivos_detalle", CSV_DETALLE)


if __name__ == "__main__":
    run()
