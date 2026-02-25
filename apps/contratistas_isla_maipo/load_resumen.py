from core.cleaners import clean_boolean, clean_currency, clean_date
from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger, print_progress

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_resumen"
CSV = "data/contratistas_isla_maipo/raw/resumen.csv"


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
                            "ID_Resumen", "ID_Registro", "Campo", "Fecha", "Contratista",
                            "CC", "Labor", "Trabajador", "Jornada", "Bonificación",
                            "Bono_Especial_Piso", "Horas_Extras", "Trato",
                            "Unidades Trato", "Base Trato", "Dia_Habil",
                            "Id_Busqueda", "Nombre Labor"
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT ("ID_Resumen") DO UPDATE SET
                            "ID_Registro" = EXCLUDED."ID_Registro",
                            "Campo" = EXCLUDED."Campo",
                            "Fecha" = EXCLUDED."Fecha",
                            "Contratista" = EXCLUDED."Contratista",
                            "CC" = EXCLUDED."CC",
                            "Labor" = EXCLUDED."Labor",
                            "Trabajador" = EXCLUDED."Trabajador",
                            "Jornada" = EXCLUDED."Jornada",
                            "Bonificación" = EXCLUDED."Bonificación",
                            "Bono_Especial_Piso" = EXCLUDED."Bono_Especial_Piso",
                            "Horas_Extras" = EXCLUDED."Horas_Extras",
                            "Trato" = EXCLUDED."Trato",
                            "Unidades Trato" = EXCLUDED."Unidades Trato",
                            "Base Trato" = EXCLUDED."Base Trato",
                            "Dia_Habil" = EXCLUDED."Dia_Habil",
                            "Id_Busqueda" = EXCLUDED."Id_Busqueda",
                            "Nombre Labor" = EXCLUDED."Nombre Labor"
                        """,
                        (
                            row.get("ID_Resumen") or None,
                            row.get("Id_Registro") or row.get("ID_Registro") or None,
                            row.get("Campo") or None,
                            clean_date(row.get("Fecha")),
                            row.get("Contratista") or None,
                            row.get("CC") or None,
                            row.get("Labor") or None,
                            row.get("Trabajador") or None,
                            clean_currency(row.get("Jornada")) or None,
                            clean_currency(row.get("Bonificación")) or None,
                            clean_currency(row.get("Bono_Especial_Piso")) or None,
                            clean_currency(row.get("Horas_Extras")) or None,
                            row.get("Trato") or None,
                            clean_currency(row.get("Unidades Trato")) or None,
                            clean_currency(row.get("Base Trato")) or None,
                            clean_boolean(row.get("Día_Habil")),
                            row.get("Id_Busqueda") or None,
                            row.get("Nombre Labor") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} rows loaded.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
