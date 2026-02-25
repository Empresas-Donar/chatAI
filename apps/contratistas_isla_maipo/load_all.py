# Migración completa de contratistas_isla_maipo
# Orden respeta dependencias de FK:
#   empresa → labor → contratistas → trabajadores → tratos
#   → registro → registro_trato → resumen → pagos → cultivos → usuarios

from apps.contratistas_isla_maipo import (
    load_contratistas,
    load_cultivos,
    load_empresa,
    load_labor,
    load_pagos,
    load_registro,
    load_registro_trato,
    load_resumen,
    load_trabajadores,
    load_tratos,
    load_usuarios,
)
from core.utils import get_logger

logger = get_logger("contratistas_isla_maipo")

STEPS = [
    ("empresa",        load_empresa),
    ("labor",          load_labor),
    ("contratistas",   load_contratistas),
    ("trabajadores",   load_trabajadores),
    ("tratos",         load_tratos),
    ("registro",       load_registro),
    ("registro_trato", load_registro_trato),
    ("resumen",        load_resumen),
    ("pagos",          load_pagos),
    ("cultivos",       load_cultivos),
    ("usuarios",       load_usuarios),
]


def run():
    logger.info("=== Starting migration: contratistas_isla_maipo ===")
    for name, module in STEPS:
        logger.info(f"--- Loading: {name} ---")
        try:
            module.run()
        except Exception as e:
            logger.error(f"Error loading {name}: {e}")
            raise
    logger.info("=== Migration complete: contratistas_isla_maipo ===")


if __name__ == "__main__":
    run()
