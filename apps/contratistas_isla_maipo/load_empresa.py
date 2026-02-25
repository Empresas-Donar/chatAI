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
                        INSERT INTO {TABLE} ("CC", "Empresa")
                        VALUES (%s, %s)
                        ON CONFLICT ("CC") DO UPDATE SET
                            "Empresa" = EXCLUDED."Empresa"
                        """,
                        (
                            row.get("CC") or None,
                            row.get("Empresa") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} rows loaded.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
