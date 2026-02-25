from core.cleaners import clean_currency, clean_percentage
from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_contratistas"
CSV = "data/contratistas_isla_maipo/raw/contratistas.csv"


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
                            "Id_Supervisor", "Campo", "Supervisor", "Empresa_Contratista",
                            "Valor_Jornada", "Valor_Hora_Extra",
                            "%%Jornada_Bono", "%%Trato",
                            "Fijo_Jornada", "Bono_Extra"
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT ("Id_Supervisor") DO UPDATE SET
                            "Campo" = EXCLUDED."Campo",
                            "Supervisor" = EXCLUDED."Supervisor",
                            "Empresa_Contratista" = EXCLUDED."Empresa_Contratista",
                            "Valor_Jornada" = EXCLUDED."Valor_Jornada",
                            "Valor_Hora_Extra" = EXCLUDED."Valor_Hora_Extra",
                            "%%Jornada_Bono" = EXCLUDED."%%Jornada_Bono",
                            "%%Trato" = EXCLUDED."%%Trato",
                            "Fijo_Jornada" = EXCLUDED."Fijo_Jornada",
                            "Bono_Extra" = EXCLUDED."Bono_Extra"
                        """,
                        (
                            row.get("Id_Supervisor") or None,
                            row.get("Campo") or None,
                            row.get("Supervisor") or None,
                            row.get("Empresa_Contratista") or None,
                            clean_currency(row.get("Valor_Jornada")),
                            clean_currency(row.get("Valor_Hora_Extra")),
                            clean_percentage(row.get("%Jornada_Bono")),
                            clean_percentage(row.get("%Trato")),
                            clean_currency(row.get("Fijo_Jornada")),
                            clean_currency(row.get("Bono_Extra")),
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} rows loaded.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
