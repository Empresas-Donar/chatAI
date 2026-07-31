# Tarifas de tractoristas incorrectas para Andrés Díaz y horas mal registradas
# Path: specs/64-fix-tractorista-rates/spec.md
issue: #64 · branch: 64-fix-tractorista-rates · date: 2026-07-31

## What
Corregir los montos de pago de tractoristas: Andrés Díaz Herrrra usaba la columna de tarifa "sin operador" en vez de "con operador sin bono", dos filas de sábado (Luis Iván/Nivaldo) usaban la columna lunes-sábado en vez de lunes-viernes, y una fila incompleta quedó en $0. Además, normalizar `horas_trabajadas` a 9 en todas las filas de tractoristas (el monto no depende de las horas).

## Acceptance
- [x] Todas las filas `tipo_pago='Tractorista'` tienen `horas_trabajadas = 9`
- [x] Andrés Díaz recibe $66.000 en "Jornada Tractor normal" (con operador, sin bono — no cumple licencia/certificado) — no $72.000 como se supuso inicialmente
- [x] "OPERARIO SOLO" no se toca: $30.000 (Andrés, sin bono) y $36.000 (Luis Iván/Nivaldo, con bono) ya eran correctos
- [x] Las filas de sábado (11/07) de Luis Iván y Nivaldo quedan en $72.000 (con operador + bono, columna lunes-viernes), igual que el resto de la semana
- [x] `total_trabajado` y `total_pagar` reflejan el mismo valor corregido (son espejo de `total_tractor`)
- [x] Tests de regresión contra la BD real
- [x] La fila de Luis Iván del 03/07/2026 (`horas_trabajadas=1`, `total_tractor=0`) se corrigió a $72.000/horas=9 igual que sus demás filas, confirmado por el usuario

## Context
- Tabla: `appsheet.tarjas_pagos`, filtro `tipo_pago='Tractorista'` (69 filas en total, todas `estado='Pendiente'`).
- Para tractoristas, `total_trabajado` y `total_pagar` son siempre un espejo exacto de `total_tractor` (verificado: 0 excepciones en las 69 filas); `contratista_jornada`, `contratista_trato`, `total_contratista` son siempre 0.
- `appsheet.tarjas_maquina.cumple` (SI/NO) indica si la máquina califica para el bono de $6.000. Las 3 máquinas usadas en "Jornada Tractor normal" (Same frutteto 80.4, Same frutetto 70, SAME FRUTTETO 65) tienen `cumple='SI'` — las tres ya calificarían para el bono, por lo que no hay grupo de comparación con `cumple='NO'` en los datos actuales.
- No existe tabla de tarifas para tractoristas (a diferencia de `tarjas_trato` para jornaleros) — el monto lo define directamente el supervisor al ingresar la tarja en AppSheet, sin fórmula de cálculo por hora.
- Valores de referencia (consenso de 2 de 3 tractoristas, mismo contratista RAMÓN DIAZ, mismo período):
  - "Jornada Tractor normal" (máquina con `cumple='SI'`): $72.000/día — Luis Iván (13 filas) y Nivaldo (17 filas) coinciden; Andrés muestra $27.600 (11 filas) y $23.000 (1 fila, sábado).
  - "OPERARIO SOLO" (sin máquina): $36.000/día — Luis Iván (8 filas) y Nivaldo (4 filas) coinciden; Andrés muestra $30.000 (11 filas).
  - Sábado 11/07/2026: Luis Iván y Nivaldo muestran $61.000 en vez de $72.000 para la misma labor — inconsistencia ligada al día de la semana, no confirmada como intencional por el usuario ("la tarifa... está de lunes a viernes siempre por el momento").
- "Jornada Tractor simple" (Nivaldo, 1 sola fila histórica, $31.000) no tiene punto de comparación — fuera de alcance, sin evidencia de error.
- Fila excluida inicialmente: Luis Iván, 03/07/2026, `id_Resumen='08529b3c'`, horas_trabajadas=1, total_tractor=0 — el usuario confirmó que sí fue un día trabajado y pidió corregirla igual que el resto.
- **Hallazgo crítico durante la investigación**: existe una rama sin mergear (`45-fix-tractorista-jornada`, issue #45, PR #49 abierto) cuyo SQL (`sql/tarjas/09_fix_tractorista_jornada.sql`) **ya se había ejecutado contra producción** el 28/07/2026, 3 días antes de este fix. Ese fix movió las mismas filas de `horas_trabajadas=9` a `7.5` bajo la premisa de "con licencia/certificado ($72.000) vs sin licencia ($27.600)" — premisa que el usuario aclaró que era incorrecta: la licencia solo agrega un bono de $6.000, no define la tarifa base. Se verificó que el estado de la BD antes de este fix coincidía 64/65 filas con el resultado de esa rama (la fila restante ya no existe, probablemente eliminada/recreada). Este fix #64 revierte el criterio de horas (vuelve a 9) y corrige el criterio de montos usando la tabla de tarifas real.
- Tabla de tarifas real descubierta: `appsheet.tarjas_labor` (columnas `valor_c_operador_lunes_viernes`, `valor_s_operador_lunes_viernes`, `valor_c_Operador_lunes_sabado`, `valor_s_operador_lunes_sabado`) — no derivable del código, solo de la BD:
  - "Jornada Tractor normal": con operador L-V = $66.000, sin operador L-V = $27.600, con operador L-S = $55.000, sin operador L-S = $23.000
  - "OPERARIO SOLO": $30.000 flat en las 4 combinaciones
  - "Jornada Tractor simple": con operador L-V = $25.000 (todas las combinaciones iguales)
- El bono de $6.000 es **por trabajador**, no por máquina: `appsheet.tarjas_personal.licencia_clase_d` y `certificado_sag` (ambos deben ser 'SI'). Confirmado en BD:
  - ANDRÉS DÍAZ HERRRRA (`id_personal='73286f7f'`): `licencia_clase_d='NO'`, `certificado_sag='NO'` → sin bono
  - LUIS IVÁN CONTRERAS PERALTA (`a8961a38`) y NIVALDO MALDONADO VALENZUELA (`f83db9a0`): ambos `'SI'`/`'SI'` → con bono
- Regla de negocio confirmada por el usuario: todos los ingresos actuales son "con operador"; la tarifa a usar es siempre la columna lunes-viernes, independiente del día calendario real; horas_trabajadas no participa en el cálculo del monto.

## Decisions
- Se usó una lista explícita de `id_Resumen` en el UPDATE (en vez de `WHERE trabajador = ...`) para evitar problemas de comparación de texto por acentos/encoding entre el script SQL (UTF-8) y el valor real en la tabla.
- El primer análisis (antes de encontrar `tarjas_labor`) concluyó erróneamente que $72.000 era la tarifa correcta para Andrés Díaz, por consenso de mayoría (2 de 3 tractoristas). Se descartó al encontrar la tabla de tarifas real y la tabla de calificación personal — la mayoría no siempre es la tarifa correcta cuando hay una regla de negocio (bono por trabajador) que diferencia legítimamente entre ellos.
- No se recalculó "Jornada Tractor simple" ni las filas ya correctas de "Jornada Tractor normal"/"OPERARIO SOLO" — se verificó cada una contra `tarjas_labor` + `tarjas_personal` antes de decidir no tocarlas.
- El fix de horas (`horas_trabajadas = 9` para todo `tipo_pago='Tractorista'`) revierte explícitamente lo que hizo `sql/tarjas/09_fix_tractorista_jornada.sql` (issue #45, aún no mergeado) para estas mismas filas. Se deja constancia en este spec para quien revise el PR #49 más adelante — ese fix debe considerarse superado por este.

## Implemented
### SQL
- `sql/tarjas/15_fix_tractorista_rates_andres_diaz.sql` — 3 UPDATE idempotentes (horas_trabajadas masivo + 2 grupos de montos por `id_Resumen`). **Ya ejecutado contra la BD real.**

### Tests
- `chatai/tests/test_64_fix_tractorista_rates.py` — 7 tests: horas=9 en las 69 filas, Andrés Díaz en $66.000 sin bono, Luis Iván/Nivaldo en $72.000 con bono (incluye las 2 filas de sábado y la fila incompleta), OPERARIO SOLO sin cambios (bono por trabajador), total_trabajado/total_pagar espejo de total_tractor, Jornada Tractor simple sin tocar, isolation (solo 69 filas Tractorista afectadas)

## Routes
N/A — corrección de datos, sin cambios de código/endpoints.

## Tests
```
pytest tests/test_64_fix_tractorista_rates.py -v
7 passed in 2.06s

pytest tests/ -v
184 passed, 2 failed in 20.24s
```
Los 2 fallos (`test_50_odoo_export_tractorista.py`) son preexistentes en `main`, no relacionados con este fix (verificado con `git stash` antes de aplicar cualquier cambio).

Cross-farm isolation: ✅ (`test_64_no_other_tipo_pago_rows_touched_isolation`)

## Manual QA
1. En `/tarjas/detalle-tractorista` o `/tarjas/general-tractorista`, filtrar por contratista Ramón Díaz, 01/07–31/07 → Andrés Díaz debe mostrar $66.000 en "Jornada Tractor normal" (no $27.600 ni $72.000), Luis Iván y Nivaldo deben mostrar $72.000 en todas sus filas de esa labor (incluida la del 11/07 y la del 03/07).
2. Verificar que "OPERARIO SOLO" no cambió: Andrés en $30.000, Luis Iván/Nivaldo en $36.000.
3. `SELECT DISTINCT horas_trabajadas FROM appsheet.tarjas_pagos WHERE tipo_pago='Tractorista'` → debe devolver solo `9`.

## Deferred
- No existe corrección de código/endpoint — es una corrección de datos histórica. Si se detectan más ingresos futuros de tractoristas con la columna de tarifa equivocada, sería valioso agregar una validación en el formulario de AppSheet (fuera del alcance de este repo) o una vista de reconciliación contra `tarjas_labor` + `tarjas_personal`.
- El PR #49 (issue #45) sigue abierto con una premisa de negocio que este fix corrige; se recomienda cerrarlo o actualizarlo para evitar reejecutar su SQL por error.
