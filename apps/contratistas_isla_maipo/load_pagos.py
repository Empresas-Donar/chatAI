from core.cleaners import clean_boolean, clean_currency, clean_date
from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger, print_progress

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_pagos"
CSV = "data/contratistas_isla_maipo/raw/pagos.csv"


def run():
    df = load_csv(CSV)
    # Skip rows with empty ID_Resumen (invalid/export artifacts from Sheets)
    before = len(df)
    id_col = df["ID_Resumen"].fillna("").astype(str).str.strip()
    df = df[id_col != ""].reset_index(drop=True)
    skipped = before - len(df)
    if skipped > 0:
        logger.warning(f"Skipping {skipped} rows with empty ID_Resumen")
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
                            "ID_Resumen", "Campo", "Fecha", "Mes", "Contratista", "CC",
                            "Labor", "Trabajador", "Jornada", "Bonificación",
                            "Bono_Especial_Piso", "Horas_Extras", "Trato",
                            "Unidades Trato", "Base Trato", "Dia_Habil", "Nombre Labor",
                            "Valor Bonificación 2", "Bono Extra", "Valor Jornada",
                            "Total Unidades", "Valor Trato",
                            "Trabajador Jornal mas Bonos", "Trabajador Tratos",
                            "Total Trabajador", "Contratista Jornada",
                            "Contratista Tratos", "Total Contratista",
                            "Total a Pagar", "Total Jornada",
                            "dia", "Empresa", "Cultivo", "Dia de Ayer", "Tipo de Pago"
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        ON CONFLICT ("ID_Resumen") DO UPDATE SET
                            "Campo" = EXCLUDED."Campo",
                            "Fecha" = EXCLUDED."Fecha",
                            "Mes" = EXCLUDED."Mes",
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
                            "Nombre Labor" = EXCLUDED."Nombre Labor",
                            "Valor Bonificación 2" = EXCLUDED."Valor Bonificación 2",
                            "Bono Extra" = EXCLUDED."Bono Extra",
                            "Valor Jornada" = EXCLUDED."Valor Jornada",
                            "Total Unidades" = EXCLUDED."Total Unidades",
                            "Valor Trato" = EXCLUDED."Valor Trato",
                            "Trabajador Jornal mas Bonos" = EXCLUDED."Trabajador Jornal mas Bonos",
                            "Trabajador Tratos" = EXCLUDED."Trabajador Tratos",
                            "Total Trabajador" = EXCLUDED."Total Trabajador",
                            "Contratista Jornada" = EXCLUDED."Contratista Jornada",
                            "Contratista Tratos" = EXCLUDED."Contratista Tratos",
                            "Total Contratista" = EXCLUDED."Total Contratista",
                            "Total a Pagar" = EXCLUDED."Total a Pagar",
                            "Total Jornada" = EXCLUDED."Total Jornada",
                            "dia" = EXCLUDED."dia",
                            "Empresa" = EXCLUDED."Empresa",
                            "Cultivo" = EXCLUDED."Cultivo",
                            "Dia de Ayer" = EXCLUDED."Dia de Ayer",
                            "Tipo de Pago" = EXCLUDED."Tipo de Pago"
                        """,
                        (
                            row.get("ID_Resumen") or None,
                            row.get("Campo") or None,
                            clean_date(row.get("Fecha")),
                            row.get("Mes") or None,
                            row.get("Contratista") or None,
                            row.get("CC") or None,
                            row.get("Labor") or None,
                            row.get("Trabajador") or None,
                            clean_currency(row.get("Jornada")) or None,
                            clean_currency(row.get("Bonificación")) or None,
                            clean_currency(row.get("Bono Especial PISO")) or None,
                            clean_currency(row.get("Horas Extras")) or None,
                            row.get("Trato") or None,
                            clean_currency(row.get("Unidades Trato")) or None,
                            clean_currency(row.get("Base Tato")) or None,
                            clean_boolean(row.get("Día Hábil")),
                            row.get("Nombre Labor") or None,
                            clean_currency(row.get("Valor Bonificación 2")) or None,
                            clean_currency(row.get("Bono Extra")) or None,
                            clean_currency(row.get("Valor Jornada")) or None,
                            clean_currency(row.get("Total Unidades")) or None,
                            clean_currency(row.get("Valor Trato")) or None,
                            clean_currency(row.get("Trabajador Jor + Bonos")) or None,
                            clean_currency(row.get("Trabajador Tratos")) or None,
                            clean_currency(row.get("Total Trabajador")) or None,
                            clean_currency(row.get(" Contratista\nJornada ")) or None,
                            clean_currency(row.get(" Contratista\nTratos ")) or None,
                            clean_currency(row.get("Total Contratista")) or None,
                            clean_currency(row.get("Total a Pagar")) or None,
                            clean_currency(row.get("Total Jornada")) or None,
                            row.get("Dia") or None,
                            row.get("Empresa") or None,
                            row.get("Cultivo") or None,
                            clean_boolean(row.get("Día de Ayer")),
                            row.get("Tipo de pago") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} rows loaded.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
