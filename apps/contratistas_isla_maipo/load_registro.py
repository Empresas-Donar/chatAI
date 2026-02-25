from core.cleaners import clean_boolean, clean_date, clean_enumlist, clean_currency
from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger, print_progress

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_registro"
CSV = "data/contratistas_isla_maipo/raw/registro.csv"


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
                            "ID_Registro", "Campo", "Fecha", "Contratista", "CC",
                            "Labor", "Tipo de Registro", "Trabajador", "Jornada",
                            "Bonificación", "Bono_Especial_Piso", "Horas_Extras",
                            "Trato", "Dia_Habil", "Contador", "dia"
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT ("ID_Registro") DO UPDATE SET
                            "Campo" = EXCLUDED."Campo",
                            "Fecha" = EXCLUDED."Fecha",
                            "Contratista" = EXCLUDED."Contratista",
                            "CC" = EXCLUDED."CC",
                            "Labor" = EXCLUDED."Labor",
                            "Tipo de Registro" = EXCLUDED."Tipo de Registro",
                            "Trabajador" = EXCLUDED."Trabajador",
                            "Jornada" = EXCLUDED."Jornada",
                            "Bonificación" = EXCLUDED."Bonificación",
                            "Bono_Especial_Piso" = EXCLUDED."Bono_Especial_Piso",
                            "Horas_Extras" = EXCLUDED."Horas_Extras",
                            "Trato" = EXCLUDED."Trato",
                            "Dia_Habil" = EXCLUDED."Dia_Habil",
                            "Contador" = EXCLUDED."Contador",
                            "dia" = EXCLUDED."dia"
                        """,
                        (
                            row.get("ID_Registro") or None,
                            row.get("Campo") or "Isla de maipo",
                            clean_date(row.get("Fecha")),
                            row.get("Contratista") or None,
                            row.get("CC") or None,
                            row.get("Labor") or None,
                            row.get("Tipo de Registro") or None,
                            clean_enumlist(row.get("Trabajador")),
                            clean_currency(row.get("Jornada")) or 1,
                            clean_currency(row.get("Bonificación")) or None,
                            clean_currency(row.get("Bono_Especial_Piso")) or 0,
                            clean_currency(row.get("Horas_Extras")) or 0,
                            row.get("Trato") or None,
                            clean_boolean(row.get("Día_Habil")),
                            clean_currency(row.get("Contador")) or None,
                            row.get("dia") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} rows loaded.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
