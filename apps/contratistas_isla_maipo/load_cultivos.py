from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
CSV_CULTIVOS = "data/contratistas_isla_maipo/raw/cultivos.csv"
CSV_DETALLE = "data/contratistas_isla_maipo/raw/cultivos_detalle.csv"


def _load_table(table: str, csv_path: str):
    df = load_csv(csv_path)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    cur.execute(
                        f"""
                        INSERT INTO {table} ("CC", "Cultivo", "Tipo", "Id", "Valor odoo")
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT ("CC") DO UPDATE SET
                            "Cultivo" = EXCLUDED."Cultivo",
                            "Tipo" = EXCLUDED."Tipo",
                            "Id" = EXCLUDED."Id",
                            "Valor odoo" = EXCLUDED."Valor odoo"
                        """,
                        (
                            row.get("CC") or None,
                            row.get("Cultivo") or None,
                            row.get("Tipo") or None,
                            row.get("Id") or None,
                            row.get("Valor odoo") or None,
                        ),
                    )
        logger.info(f"{table}: {len(df)} rows loaded.")
    finally:
        conn.close()


def run():
    _load_table("appsheet.contratistas_isla_maipo_cultivos", CSV_CULTIVOS)
    _load_table("appsheet.contratistas_isla_maipo_cultivos_detalle", CSV_DETALLE)


if __name__ == "__main__":
    run()
