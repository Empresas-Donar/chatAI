from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_trabajadores"
CSV = "data/contratistas_isla_maipo/raw/trabajadores.csv"


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
                            "Id_Trabajador", "Nombre_Trabajador", "Campo",
                            "Contratista", "Ingresar_Nombre", "Rut"
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT ("Id_Trabajador") DO UPDATE SET
                            "Nombre_Trabajador" = EXCLUDED."Nombre_Trabajador",
                            "Campo" = EXCLUDED."Campo",
                            "Contratista" = EXCLUDED."Contratista",
                            "Ingresar_Nombre" = EXCLUDED."Ingresar_Nombre",
                            "Rut" = EXCLUDED."Rut"
                        """,
                        (
                            row.get("Id_Trabajador") or None,
                            row.get("Nombre_Trabajador") or None,
                            row.get("Campo") or "Isla de Maipo",
                            row.get("Contratista") or None,
                            row.get("Ingresar_Nombre") or None,
                            row.get("Rut") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} rows loaded.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
