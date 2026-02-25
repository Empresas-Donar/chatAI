from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_usuarios"
CSV = "data/contratistas_isla_maipo/raw/usuarios.csv"


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
                            "Id_Usuario", "Nombre Usuario", "Correo", "Rol", "Contraseña"
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT ("Id_Usuario") DO UPDATE SET
                            "Nombre Usuario" = EXCLUDED."Nombre Usuario",
                            "Correo" = EXCLUDED."Correo",
                            "Rol" = EXCLUDED."Rol",
                            "Contraseña" = EXCLUDED."Contraseña"
                        """,
                        (
                            row.get("Id_Usuario") or None,
                            row.get("Nombre Usuario") or None,
                            row.get("Correo") or None,
                            row.get("Rol") or None,
                            row.get("Contraseña") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} rows loaded.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
