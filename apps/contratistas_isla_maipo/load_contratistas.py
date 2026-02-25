from core.cleaners import clean_percentage
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
                            id_supervisor, campo, supervisor, empresa_contratista,
                            valor_jornada, valor_hora_extra,
                            porcentaje_jornada_bono, porcentaje_trato,
                            fijo_jornada, bono_extra
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id_supervisor) DO UPDATE SET
                            campo = EXCLUDED.campo,
                            supervisor = EXCLUDED.supervisor,
                            empresa_contratista = EXCLUDED.empresa_contratista,
                            valor_jornada = EXCLUDED.valor_jornada,
                            valor_hora_extra = EXCLUDED.valor_hora_extra,
                            porcentaje_jornada_bono = EXCLUDED.porcentaje_jornada_bono,
                            porcentaje_trato = EXCLUDED.porcentaje_trato,
                            fijo_jornada = EXCLUDED.fijo_jornada,
                            bono_extra = EXCLUDED.bono_extra
                        """,
                        (
                            row.get("id_supervisor") or None,
                            row.get("campo") or None,
                            row.get("supervisor") or None,
                            row.get("empresa_contratista") or None,
                            row.get("valor_jornada") or None,
                            row.get("valor_hora_extra") or None,
                            clean_percentage(row.get("porcentaje_jornada_bono")),
                            clean_percentage(row.get("porcentaje_trato")),
                            row.get("fijo_jornada") or None,
                            row.get("bono_extra") or None,
                        ),
                    )
        logger.info(f"{TABLE}: {len(df)} filas procesadas.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
