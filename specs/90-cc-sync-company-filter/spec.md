# Sync de CC (tarjas_cc) incluye empresas Odoo ajenas a Donar/Kontrolag
# Path: specs/90-cc-sync-company-filter/spec.md
issue: #90 · branch: 90-cc-sync-company-filter · date: 2026-08-11

## What
`apps/sync_cc.py` sincroniza CC de **cualquier** `company_id` de Odoo hacia `appsheet.tarjas_cc`; debe limitarse solo a Agrícola Donar Uno, Agrícola Donar Dos y Kontrolag.

## Acceptance
<!-- Copiado del issue #90 -->
- [x] `apps/sync_cc.py` define una lista explícita de `company_id` permitidos (Agrícola Donar Uno, Agrícola Donar Dos, Kontrolag).
- [x] `fetch_odoo_cc` descarta filas cuyo `company_id` no esté en esa lista antes de construir `by_code` (nunca deben llegar a `sync_tarjas_cc`).
- [x] `fetch_odoo_distribucion_models` aplica el mismo filtro de `company_id`.
- [x] Tests de regresión que confirmen que un CC de una empresa fuera de la lista queda excluido, y que las empresas permitidas no se ven afectadas.
- [ ] Limpieza puntual (aparte, con aprobación explícita) de filas ya existentes en `appsheet.tarjas_cc` en producción que provengan de empresas fuera de la lista. (Deferred — separate step pending user go-ahead.)

## Context
- Module: `apps/sync_cc.py` — script standalone (no FastAPI/Alembic), corre vía `.github/workflows/sync_cc.yml`.
- `COMPANY_TO_CAMPO = {1: 1, 2: 1, 3: 2, 5: 3, 6: 4, 7: 4}` + `DEFAULT_CAMPO = 1`: solo determina el "campo" visual, no filtra. Cualquier `company_id` fuera del dict cae en `DEFAULT_CAMPO=1` en vez de excluirse — ese es el bug.
- `fetch_odoo_cc()` (BigQuery `CC_analiticos`) construye `active_by_composite` iterando `rows` (~línea 110-124); ahí debe aplicarse el filtro antes de poblar `by_code`.
- `fetch_odoo_distribucion_models()` (BigQuery `Modelos_Distribucion_Analitica`) ya filtra `WHERE x_studio_numeracin IS NOT NULL`; se le agrega el mismo filtro de `company_id`.
- Postgres `appsheet.tarjas_campo`: `1=TALAGANTE, 2=ISLA DE MAIPO, 3=ZUÑIGA, 4=KONTROLAG` — son "campos" (predios) visuales, no las 3 razones sociales del issue.
- BigQuery `odoo_data` no tiene tabla `res_company` / nombres de empresa — `company_id` es solo un entero sin nombre asociado en ese dataset.
- Test file: `chatai/tests/test_sync_cc.py` (patrón `MockRow`/dict con `_cc()` y `_model_row()` helpers, funciones `_run_fetch_odoo_cc()` / `_run_fetch_distribucion_models()`).

## Decisions
- **Investigación BigQuery (`CC_analiticos`, tras restaurar ADC) — evidencia por `company_id`:**

  | company_id | # CC (activos) | Nombres representativos | Conclusión |
  |---|---|---|---|
  | 1 | 7 (5) | "ADMIN. TALAGANTE", "ADMIN. ISLA DE MAIPO", "ADMIN. ZUÑIGA", "Administraciones Donar" (código 270) | Holding/admin Donar — ya mapeado a campo 1 (Talagante) en prod, código 270 activo y coherente |
  | 2 | 80 (24) | "Campo Talagante", CCs de cultivo activos (PIMENTONES, ZAPALLO, etc. 24/25) | Empresa operativa principal — Talagante |
  | 3 | 41 (35) | "Campo Isla de Maipo", "Campo Zuñiga", CEREZOS/CIRUELAS activos (SANTINA, RED PACIFIC, D'AGEN 2025...) | Empresa operativa principal — Isla de Maipo + Zuñiga |
  | 5 | 8 (6) | "ADMINISTRACIÓN TALAGANTE/ISLA DE MAIPO/ZUÑIGA", "Agricola Los Almendros" (código 150, ya en prod bajo campo 3) | Holding/admin Donar (patrón igual a company 1) |
  | **7** | 57 (55) | **`K0001`=KONTROLAG, `K0002`=INNOVACION Y DESARROLLO, `K0102`=AGRICOLA EL MILAGRO, `K0103`=TRIO RIEGO, `K0106`=AGROBERRIES, `K0128`=AGRICOLA DONAR UNO PEONIAS...** (K0001-K0147, único company_id con códigos `K%` en todo BigQuery) | **Kontrolag confirmado sin ambigüedad** — coincide exactamente con los nombres ya vigentes en prod (`tarjas_cc` id_campo=4) |
  | 6 | 85 (83) | "SERVICIOS FB", "VENTA REPUESTOS (FB)", "CARRO DESPARRAMADOR...", "CAMIONETA MITSUBISHI", "GRUA HORQUILLA CLARK", órdenes de trabajo "OT-S-XX-20XX" — **cero** referencias a Talagante/Isla de Maipo/Zuñiga/Kontrolag, cero coincidencia con nombres ya en prod | **Empresa distinta ("FB"), no es Kontrolag ni Donar** → excluir |
  | 9 | 6 (6) | "RANCO", "CONSTRUCCIÓN", "COYHAIQUE", "INVERSIONES DONAR" (260), "ISLA DE MAIPO" (400) | Holding/inmobiliaria no relacionada — ya contaminó prod vía `DEFAULT_CAMPO=1` (códigos 260, 290, 400 aparecen hoy bajo campo 1 Talagante) → excluir |
  | 11 | 3 (1) | "INVERSIONES SAN JUAN" (700) | No relacionada — también filtró a prod vía fallback → excluir |
  | 12, 15 | 4, 4 | "FD SPA", "VIVEROS" | No relacionadas → excluir |

  Verificado en Postgres prod: los códigos 260 ("INVERSIONES DONAR"), 290 ("COYHAIQUE") y 400 ("ISLA DE MAIPO") de company_id=9, y 700 ("INVERSIONES SAN JUAN") de company_id=11, ya existen hoy en `appsheet.tarjas_cc` bajo `id_campo=1` — confirmando en vivo el bug del `DEFAULT_CAMPO` fallback.

- **Conflicto resuelto con el usuario:** la primera respuesta del usuario fue "company_id 6 y 7 son otras empresas, no incluir ninguna" — pero la evidencia de BigQuery contradecía esto para el 7: `company_id=7` es el **único** company_id con códigos `K0001`-`K0147` en todo el dataset, y esos códigos incluyen exactamente los nombres que el propio usuario citó como firma de Kontrolag en producción ("KONTROLAG", "INNOVACIÓN Y DESARROLLO", "AGRICOLA EL MILAGRO", "AGROBERRIES", "TRIO RIEGO"). Se presentó esta evidencia y el usuario **confirmó** que `company_id=7` es Kontrolag y que `ALLOWED_COMPANY_IDS = {1, 2, 3, 5, 7}` es correcto (excluye 6, 9, 11, 12, 15).
- `COMPANY_TO_CAMPO` se corrigió quitando la entrada `6: 4` (estaba mal atribuida a Kontrolag); se mantiene `7: 4` como único company_id de campo 4.
- El filtro se aplica temprano, en las tres iteraciones sobre `rows`/resultados de BigQuery (dos en `fetch_odoo_cc` — CCs activos y archivados — y una en `fetch_odoo_distribucion_models`), antes de construir `active_by_composite`/`by_plan`/`archived_to_replacements`/`result`, para que ninguna fila de una empresa excluida participe siquiera en la lógica de deduplicación por código.
- No se tocó la consulta SQL de BigQuery (se mantiene el filtro en Python) para no duplicar lógica de filtrado entre SQL y Python y mantener el diff mínimo.
- No se modificó `DEFAULT_CAMPO`/su uso en `sync_tarjas_cc` y `fetch_odoo_distribucion_models`: tras el filtro, todo `company_id` que llega a esas líneas ya está garantizado en `ALLOWED_COMPANY_IDS ⊆ COMPANY_TO_CAMPO.keys()`, así que el fallback queda inalcanzable en la práctica pero se deja como red de seguridad, sin refactor adicional.
- Limpieza de `appsheet.tarjas_cc` en producción (filas de company_id 6/9/11/12/15 ya sincronizadas) queda **deferida**: es un paso separado que requiere mostrar la lista exacta de filas y obtener aprobación explícita antes de cualquier DELETE.

## Implemented
### Script
- `apps/sync_cc.py` — agrega `ALLOWED_COMPANY_IDS = {1, 2, 3, 5, 7}`; corrige `COMPANY_TO_CAMPO` quitando `6: 4`; filtra por `company_id` en `fetch_odoo_cc()` (CCs activos y archivados) y en `fetch_odoo_distribucion_models()`.

### Tests
- `chatai/tests/test_sync_cc.py` — actualiza `test_5_sync_cc_duplicate_codes_regression` (usaba company_id=6 para el caso de colisión de código; ahora usa company_id=3, empresa permitida, para no depender de una empresa que el propio fix excluye); agrega clase `TestFetchOdooCCCompanyAllowlist` (5 tests) y clase `TestFetchDistribucionModelsCompanyAllowlist` (2 tests).

## Tests
```
pytest chatai/tests/test_sync_cc.py -v
20 passed in 0.19s
```
Cross-farm isolation: ✅ (`test_cross_farm_isolation`, `test_excluded_company_does_not_steal_bare_code`)

## Manual QA
1. `python apps/sync_cc.py` contra un entorno con credenciales BigQuery válidas (`BQ_KEY_PATH`) y `DATABASE_URL`/`DB_*` apuntando a una BD de prueba — confirmar en los logs que ya no se listan inserciones para `company_id` fuera de `{1,2,3,5,7}`.
2. Tras correr el sync, `SELECT id_cc, cultivo FROM appsheet.tarjas_cc WHERE id_cc IN ('601','260','700')` (códigos conocidos de company_id 6/9/11) debe devolver 0 filas nuevas (las existentes de antes del fix quedan hasta el paso de limpieza aparte).
3. `SELECT id_cc, cultivo FROM appsheet.tarjas_cc WHERE id_cc LIKE 'K0%'` debe seguir devolviendo los CCs de Kontrolag sin cambios (company_id=7 sigue permitido).

## Deferred
- Limpieza de datos ya existentes en `tarjas_cc` en producción (filas de company_id 6, 9, 11, 12, 15) — se hará como paso separado, explícito, con lista de filas mostrada al usuario antes de cualquier DELETE.

## Implemented
_(pendiente — no implementado aún, esperando confirmación de `company_id`)_

## Tests
_(pendiente)_

## Manual QA
_(pendiente)_

## Deferred
- Limpieza de datos ya existentes en `tarjas_cc` en producción — se hará como paso separado, explícito, con lista de filas mostrada al usuario antes de cualquier DELETE.
