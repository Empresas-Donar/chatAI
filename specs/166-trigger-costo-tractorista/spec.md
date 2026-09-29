# Costo de tractorista en la base

## Qué

AppSheet no calcula el monto de tractorista. Al guardar una fila en `appsheet.tarjas_pagos`, el trigger `trg_costo_tractorista` escribe el costo en `total_tractor`, `total_trabajado` y `total_pagar`. Esas son las columnas que muestra la pestaña de aprobación.

El precio está en `appsheet.tarjas_labor`, la tabla que ya usa AppSheet. `appsheet.tarjas_esquema_tractorista` dice el horario de cada persona. La función `appsheet.costo_tractorista(trabajador, labor, horas, fecha)` es el único cálculo.

## Regla

| Labor | Precio |
|---|---|
| Jornada Tractor normal, lunes a viernes, con operador | $66.000 + $6.000 carnet, en 9 h |
| Jornada Tractor normal, lunes a sábado, con operador | $55.000 + $6.000 carnet, en 7,5 h |
| Jornada Tractor normal sin operador (antes Angel Celis) | $27.600 en 9 h, $23.000 en 7,5 h, sin carnet |
| Jornada Tractor chico, simple o Gilberto | $25.000 |
| Hora extra | $3.400 por hora |
| Labor extraordinaria | $10.000 |
| Operario solo | $60.000 |

## Cómo se calcula

1. Se busca el esquema de la persona vigente en esa fecha (`desde` / `hasta`). Si no hay fila, se usa lunes a viernes con operador. Operario Fundo está como sin operador.
2. Se lee el precio en `tarjas_labor` para esa labor.
3. Jornada normal completa: el valor de la columna (lunes a viernes o lunes a sábado, con o sin operador) más el carnet si lleva operador.
4. Jornada normal más corta: ese valor × horas / horas de la jornada, más el carnet entero.
5. Hora extra: horas × valor.
6. Chico, simple, Gilberto, extraordinaria y operario solo: el `valor` de la fila, sin carnet y sin prorrateo.

Una segunda fila del mismo trabajador, misma fecha y misma labor no vuelve a cobrar el día: si la otra ya tiene monto, esta queda en 0.

## Qué no hace

- No corre cuando solo cambia `estado`. Aprobar no recalcula.
- Si editan el pago y no cambian fecha, trabajador, labor, horas ni tipo de pago, se guarda el monto que escribieron en las tres columnas. Si cambian las horas o la labor, el trigger vuelve a calcular.
- No toca filas que no son `tipo_pago = Tractorista`.
- No reescribió el historial al instalarse. Las filas ya guardadas cambian la próxima vez que se edite la fecha, la persona, la labor o las horas.
- Operario solo en el catálogo quedó en $60.000. Las 23 filas de julio ya aprobadas siguen en $30.000 o $36.000 hasta que alguien edite la fecha, la persona, la labor o las horas. Una jornada simple de Nivaldo aprobada en $31.000 también se queda así.

## Cómo ver que está activo

```sql
SELECT tgname, tgenabled
FROM pg_trigger
WHERE tgname = 'trg_costo_tractorista';
```

`tgenabled = 'O'` significa que el trigger está activo.

```sql
SELECT appsheet.costo_tractorista(
    'Felipe Cordova', 'Jornada Tractor normal', 9, DATE '2026-09-01'
);
-- 72000
```

## Cómo cambiar un precio

Se actualiza la fila de `tarjas_labor` con `tipo = 'Tractorista'`. El carnet de $6.000 está en la función, no en una columna.

Para pasar a una persona de lunes a viernes a lunes a sábado, se cierra la fila vigente (`hasta`) y se inserta otra con `esquema = 'lun_sab'` y un `desde` nuevo. Los días anteriores no cambian.

## Implementado

- `sql/tarjas/26_trigger_costo_tractorista.sql`
- `chatai/tests/test_166_trigger_costo_tractorista.py`
