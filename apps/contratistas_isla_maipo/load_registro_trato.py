from core.cleaners import clean_currency
from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger, print_progress

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_registro_trato"
CSV = "data/contratistas_isla_maipo/raw/registro_trato.csv"


def run():
    df = load_csv(CSV)
    total = len(df)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for i, (_, row) in enumerate(df.iterrows(), 1):
                    print_progress(i, total)
                    cur.execute(
                        f"""
                        INSERT INTO {TABLE} (
                            "Id_Registro_Trato", "Id_Registro", "Contratista",
                            "Trabajador", "Unidades Trato", "Base", "Id_Busqueda"
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT ("Id_Registro_Trato") DO UPDATE SET
                            "Id_Registro" = EXCLUDED."Id_Registro",
                            "Contratista" = EXCLUDED."Contratista",
                            "Trabajador" = EXCLUDED."Trabajador",
                            "Unidades Trato" = EXCLUDED."Unidades Trato",
                            "Base" = EXCLUDED."Base",
                            "Id_Busqueda" = EXCLUDED."Id_Busqueda"
                        """,
                        (
                            row.get("Id_Registro Trato") or row.get("Id_Registro_Trato") or None,
                            row.get("Id_Registro") or None,
                            row.get("Contratista") or None,
                            row.get("Trabajador") or None,
                            clean_currency(row.get("Unidades Trato")) or None,
                            clean_currency(row.get("Base")) or 0,
                            row.get("Id_Busqueda") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} rows loaded.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
