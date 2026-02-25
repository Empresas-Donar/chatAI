# Ejecuta la migración completa de contratistas_isla_maipo en orden correcto.
#
# Orden:
#   1. empresa
#   2. labor
#   3. contratistas
#   4. trabajadores
#   5. tratos
#   6. registro
#   7. registro_trato
#   8. resumen
#   9. pagos
#  10. usuarios

from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")


def run():
    logger.info("Iniciando migración completa: contratistas_isla_maipo")
    # TODO: importar y llamar cada migrar_*.py en orden
    logger.info("Migración completa finalizada")


if __name__ == "__main__":
    run()
