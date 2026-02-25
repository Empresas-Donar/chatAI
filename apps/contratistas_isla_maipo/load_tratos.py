from core.cleaners import clean_date
from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")
TABLE = "appsheet.contratistas_isla_maipo_tratos"
CSV = "data/contratistas_isla_maipo/raw/tratos.csv"


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
                            id_tratos, campo, centro_de_costo, labor,
                            nombre_etiqueta_trato, fecha_inicio_trato,
                            fecha_termino_trato, valor_del_trato
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id_tratos) DO UPDATE SET
                            campo = EXCLUDED.campo,
                            centro_de_costo = EXCLUDED.centro_de_costo,
                            labor = EXCLUDED.labor,
                            nombre_etiqueta_trato = EXCLUDED.nombre_etiqueta_trato,
                            fecha_inicio_trato = EXCLUDED.fecha_inicio_trato,
                            fecha_termino_trato = EXCLUDED.fecha_termino_trato,
                            valor_del_trato = EXCLUDED.valor_del_trato
                        """,
                        (
                            row.get("id_tratos") or None,
                            row.get("campo") or "Isla de Maipo",
                            row.get("centro_de_costo") or None,
                            row.get("labor") or None,
                            row.get("nombre_etiqueta_trato") or None,
                            clean_date(row.get("fecha_inicio_trato")),
                            clean_date(row.get("fecha_termino_trato")),
                            row.get("valor_del_trato") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} filas procesadas.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
