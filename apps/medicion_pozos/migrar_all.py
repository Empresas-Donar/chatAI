# Ejecuta la migración completa de medicion_pozos en orden correcto.

from core.utils import get_logger

logger = get_logger("medicion_pozos")


def run():
    logger.info("Iniciando migración completa: medicion_pozos")
    # TODO: importar y llamar cada migrar_*.py en orden
    logger.info("Migración completa finalizada")


if __name__ == "__main__":
    run()
