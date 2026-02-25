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
                            id_usuario, nombre_usuario, correo, rol, contrasena
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (id_usuario) DO UPDATE SET
                            nombre_usuario = EXCLUDED.nombre_usuario,
                            correo = EXCLUDED.correo,
                            rol = EXCLUDED.rol,
                            contrasena = EXCLUDED.contrasena
                        """,
                        (
                            row.get("id_usuario") or None,
                            row.get("nombre_usuario") or None,
                            row.get("correo") or None,
                            row.get("rol") or None,
                            row.get("contrasena") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} filas procesadas.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
