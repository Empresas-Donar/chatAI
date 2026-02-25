from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_empresa"
CSV = "data/contratistas_isla_maipo/raw/empresa.csv"


def run():
    df = load_csv(CSV)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    cur.execute(
                        f"""
                        INSERT INTO {TABLE} (cc, empresa)
                        VALUES (%s, %s)
                        ON CONFLICT (cc) DO UPDATE SET
                            empresa = EXCLUDED.empresa
                        """,
                        (
                            row.get("cc") or None,
                            row.get("empresa") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} filas procesadas.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
