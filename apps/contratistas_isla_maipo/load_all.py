# Migración completa de contratistas_isla_maipo
# Orden respeta dependencias de FK:
#   empresa → labor → contratistas → trabajadores → tratos
#   → registro → registro_trato → resumen → pagos → cultivos → usuarios

import sys
import time
from datetime import datetime

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


def _print(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run():
    total = len(STEPS)
    _print(f"{'='*55}")
    _print(f"  Migración: contratistas_isla_maipo  ({total} tablas)")
    _print(f"{'='*55}")

    migration_start = time.time()
    for i, (name, module) in enumerate(STEPS, 1):
        _print(f"[{i}/{total}] Cargando: {name} ...")
        step_start = time.time()
        try:
            module.run()
            elapsed = time.time() - step_start
            _print(f"[{i}/{total}] ✓ {name}  ({elapsed:.1f}s)")
        except Exception as e:
            _print(f"[{i}/{total}] ✗ ERROR en {name}: {e}")
            logger.error(f"Error loading {name}: {e}")
            raise

    total_elapsed = time.time() - migration_start
    _print(f"{'='*55}")
    _print(f"  Migración completa en {total_elapsed:.1f}s")
    _print(f"{'='*55}")


if __name__ == "__main__":
    run()
