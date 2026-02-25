from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_labor"
CSV = "data/contratistas_isla_maipo/raw/labor.csv"


def run():
    df = load_csv(CSV)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    cur.execute(
                        f"""
                        INSERT INTO {TABLE} (codigo_labor, labor)
                        VALUES (%s, %s)
                        ON CONFLICT (codigo_labor) DO UPDATE SET
                            labor = EXCLUDED.labor
                        """,
                        (
                            row.get("codigo_labor") or None,
                            row.get("labor") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} filas procesadas.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
