from core.cleaners import clean_currency, clean_date
from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger, print_progress

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_tratos"
CSV = "data/contratistas_isla_maipo/raw/tratos.csv"


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
                            "Id_Tratos", "Campo", "Centro de Costo", "Labor",
                            "Nombre etiqueta trato", "Fecha Inicio Trato",
                            "Fecha Termino Trato", "Valor del Trato"
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT ("Id_Tratos") DO UPDATE SET
                            "Campo" = EXCLUDED."Campo",
                            "Centro de Costo" = EXCLUDED."Centro de Costo",
                            "Labor" = EXCLUDED."Labor",
                            "Nombre etiqueta trato" = EXCLUDED."Nombre etiqueta trato",
                            "Fecha Inicio Trato" = EXCLUDED."Fecha Inicio Trato",
                            "Fecha Termino Trato" = EXCLUDED."Fecha Termino Trato",
                            "Valor del Trato" = EXCLUDED."Valor del Trato"
                        """,
                        (
                            row.get("Id_Tratos") or None,
                            row.get("Campo") or "Isla de Maipo",
                            row.get("Centro de Costo") or None,
                            row.get("Labor") or None,
                            row.get("Nombre etiqueta trato") or None,
                            clean_date(row.get("Fecha Inicio Trato")),
                            clean_date(row.get("Fecha Termino Trato")),
                            clean_currency(row.get("Valor del Trato")),
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} rows loaded.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
