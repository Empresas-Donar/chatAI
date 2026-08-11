"""
apps/sync_cc.py
---------------
Syncs Odoo analytic accounts (CC_analiticos in BigQuery) into:
  - appsheet.tarjas_cc  : inserts new CC, fixes {"": 100} valor_odoo
  - appsheet.despacho_cc: fixes {"": 100} id_odoo

Also syncs Odoo analytic distribution models (Modelos_Distribucion_Analitica in BigQuery) into:
  - appsheet.tarjas_cc  : inserts distribution models as "virtual CCs" using x_studio_numeracin as id_cc

Run manually:
  python apps/sync_cc.py

Run as cron (example, daily at 6am):
  0 6 * * * cd /path/to/project && python apps/sync_cc.py >> logs/sync_cc.log 2>&1
"""

import datetime
import json
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import psycopg2
from google.cloud import bigquery
from google.oauth2 import service_account

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

BQ_PROJECT = "ace-scarab-484515-v1"
BQ_KEY_PATH = os.environ.get(
    "BQ_KEY_PATH",
    "/Users/bedomax/startups/donar/bigquery-odoo-key.json",
)

# company_id → id_campo (appsheet.tarjas_campo): 1=TALAGANTE, 2=ISLA DE MAIPO, 3=ZUÑIGA, 4=KONTROLAG
# company_id=3's CC are confirmed Zuñiga crop CCs (cerezos Santina/Lapins/Rainier, ciruelos,
# kiwis — verified against production usage, issue #90 follow-up), not Isla de Maipo — it shares
# campo 3 with company_id=5. Campo 2 (Isla de Maipo) has no dedicated Odoo company_id today.
COMPANY_TO_CAMPO = {1: 1, 2: 1, 3: 3, 5: 3, 7: 4}
DEFAULT_CAMPO = 1

# Only sync CC from these Odoo companies (issue #90): Agrícola Donar Uno / Dos and Kontrolag.
# Confirmed via BigQuery CC_analiticos:
#   1, 2, 5 → Talagante-side Donar entities (admin + "Campo Talagante" crop CCs)
#   3       → Zuñiga Donar entity ("Campo Zuñiga", cerezos/ciruelas/kiwis)
#   7       → Kontrolag (only company_id with K0001-K0147 codes, e.g. K0001="KONTROLAG")
# company_id 6 looks like Kontrolag at a glance (also mapped to campo 4 historically) but is
# actually an unrelated equipment/logistics company ("SERVICIOS FB", "GRUA HORQUILLA CLARK", ...)
# — it must stay excluded. company_id 9, 11, 12, 15 are unrelated investment/holding shells that
# were leaking into appsheet.tarjas_cc via the DEFAULT_CAMPO fallback below.
ALLOWED_COMPANY_IDS = {1, 2, 3, 5, 7}


def _bq_client():
    creds = service_account.Credentials.from_service_account_file(BQ_KEY_PATH)
    return bigquery.Client(project=BQ_PROJECT, credentials=creds)


def _pg_conn():
    # Support DATABASE_URL (used in CI) or individual vars (used locally)
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)
    host = os.environ["DB_HOST"]
    kwargs = dict(
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    if host.startswith("/"):
        return psycopg2.connect(host=host, **kwargs)
    return psycopg2.connect(
        host=host, port=int(os.environ.get("DB_PORT", 5432)), **kwargs
    )


def fetch_odoo_cc(
    bq: bigquery.Client,
) -> tuple[dict[str, dict], dict[str, list[tuple[str, float]]]]:
    """
    Fetch ALL Odoo CCs (active + archived) and return:
      by_code: {id_cc → {id, nombre, company_id}} — active CCs only, for insertions.
        id_cc is normally the bare Odoo code.  When two active CCs from different companies
        share the same code, the one with the lower (company_id, id) keeps the bare code and
        the rest get "<code>-c<company_id>" to remain unique in appsheet.tarjas_cc.
      archived_to_replacements: {archived_id → [(active_id, fraction), ...]}
        - 1:1 when same code exists in active CCs
        - 1:N when CC was split (e.g. CC-421 → ORIENTE + PONIENTE), fraction = 1/N
    """
    rows = list(
        bq.query("""
        SELECT
          CAST(id AS STRING) AS id,
          COALESCE(
            JSON_EXTRACT_SCALAR(name, '$.es_CL'),
            JSON_EXTRACT_SCALAR(name, '$.en_US'),
            CAST(id AS STRING)
          ) AS nombre,
          code,
          company_id,
          active,
          CAST(root_plan_id AS STRING) AS root_plan_id
        FROM `ace-scarab-484515-v1.odoo_data.CC_analiticos`
    """).result()
    )

    # Collect ALL active CCs keyed by (code, company_id) — no silent drops due to code
    # collisions (see ALLOWED_COMPANY_IDS filter above for the only intentional drop).
    active_by_composite: dict[tuple[str, int], dict] = {}
    by_plan: dict[str, list[dict]] = {}
    active_ids: set[str] = set()

    for r in rows:
        if int(r["company_id"]) not in ALLOWED_COMPANY_IDS:
            continue

        odoo_id = str(r["id"])
        code = str(r["code"]).strip() if r["code"] else None
        plan = str(r["root_plan_id"]) if r["root_plan_id"] else None

        if r["active"]:
            active_ids.add(odoo_id)
            if code:
                composite_key = (code, int(r["company_id"]))
                if composite_key not in active_by_composite:
                    active_by_composite[composite_key] = {
                        "id": odoo_id,
                        "nombre": r["nombre"],
                        "company_id": int(r["company_id"]),
                    }

        if plan:
            by_plan.setdefault(plan, []).append(
                {
                    "id": odoo_id,
                    "code": code,
                    "active": r["active"],
                    "nombre": r["nombre"] or "",
                    "root_plan_id": plan,
                }
            )

    # Resolve id_cc for each active CC.
    # CCs with a unique code keep id_cc = code.
    # When multiple companies share the same code, sort by (company_id, id) ascending:
    # the first keeps bare code; the rest get "<code>-c<company_id>" to stay unique.
    by_code: dict[str, dict] = {}
    per_code: dict[str, list[tuple[int, int, str, dict]]] = defaultdict(list)
    for (code, company_id), info in active_by_composite.items():
        per_code[code].append((company_id, int(info["id"]), code, info))

    for code, candidates in per_code.items():
        candidates.sort(key=lambda t: (t[0], t[1]))  # sort by (company_id, odoo_id)
        for rank, (company_id, _odoo_id_int, _code, info) in enumerate(candidates):
            id_cc = code if rank == 0 else f"{code}-c{company_id}"
            by_code[id_cc] = info

    _DIR_SUFFIX = re.compile(r"[-\s]*(NORTE|SUR|ORIENTE|PONIENTE)\s*$", re.IGNORECASE)

    def _stem(name: str) -> str:
        """Strip direction suffixes so CEREZOS X-NORTE and CEREZOS X-SUR both yield CEREZOS X."""
        return _DIR_SUFFIX.sub("", name).strip()

    def _lev(a: str, b: str) -> int:
        a, b = a.lower(), b.lower()
        if len(a) > len(b):
            a, b = b, a
        curr = list(range(len(a) + 1))
        for cb in b:
            prev = curr[:]
            curr[0] = prev[0] + 1
            for i, ca in enumerate(a):
                curr[i + 1] = (
                    prev[i] if ca == cb else 1 + min(prev[i], prev[i + 1], curr[i])
                )
        return curr[len(a)]

    def _matches(base: str, stem: str) -> bool:
        """
        Returns True if `stem` (active CC name, direction-stripped) is a valid
        replacement candidate for `base` (archived CC name, CC-NNN-stripped).

        Two allowed patterns:
          1. startswith: year was added to the name in Odoo (e.g. "CEREZOS RED PACIFIC"
             → "CEREZOS RED PACIFIC 2023"). Numbers in stem must extend base.
          2. Levenshtein ≤ 1: single-char typo (e.g. "CREZOS" vs "CEREZOS").
             Numbers must match exactly to avoid cross-year false positives.
        """
        b, s = base.lower(), stem.lower()
        if s.startswith(b):
            return True
        if _lev(b, s) <= 1:
            return re.findall(r"\d+", b) == re.findall(r"\d+", s)
        return False

    # Build archived → replacements map
    archived_to_replacements: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        if int(r["company_id"]) not in ALLOWED_COMPANY_IDS:
            continue

        oid = str(r["id"])
        if r["active"]:
            continue
        code = str(r["code"]).strip() if r["code"] else None

        # Strategy 1: direct code match
        if code and code in by_code:
            archived_to_replacements[oid] = [(by_code[code]["id"], 1.0)]
            continue

        # Strategy 2: fuzzy name-prefix siblings in same plan (handles splits + typos)
        nombre = r["nombre"] or ""
        base = re.sub(r"\s+CC-\d+\s*$", "", nombre, flags=re.IGNORECASE).strip()
        plan = str(r["root_plan_id"]) if r["root_plan_id"] else None

        if base and plan:
            siblings = [
                s
                for s in by_plan.get(plan, [])
                if s["active"] and _matches(base, _stem(s["nombre"]))
            ]
            if siblings:
                fraction = 1.0 / len(siblings)
                archived_to_replacements[oid] = [(s["id"], fraction) for s in siblings]
                log.info(
                    f"CC {oid} ({nombre!r}) → split {len(siblings)} hermanos: {[s['id'] for s in siblings]}"
                )
            else:
                log.warning(f"CC {oid} ({nombre!r}) archivado sin reemplazo detectado")

    log.info(
        f"CC activos: {len(by_code)}, archivados con reemplazo: {len(archived_to_replacements)}"
    )
    return by_code, archived_to_replacements


def sync_tarjas_cc(
    odoo: dict[str, dict],
    archived_to_replacements: dict[str, list[tuple[str, float]]],
    conn,
) -> None:
    active_ids = {info["id"] for info in odoo.values()}

    with conn.cursor() as cur:
        cur.execute("SELECT id_cc::text, valor_odoo FROM appsheet.tarjas_cc")
        existing = {r[0]: r[1] for r in cur.fetchall()}

    to_insert, to_fix = [], []

    for code, info in odoo.items():
        odoo_id = info["id"]
        new_json = json.dumps({odoo_id: 100})

        if code not in existing:
            to_insert.append(
                {
                    "id_cc": code,
                    "cultivo": info["nombre"],
                    "id_campo": COMPANY_TO_CAMPO.get(info["company_id"], DEFAULT_CAMPO),
                    "valor_odoo": new_json,
                }
            )
        else:
            current = existing[code] or {}
            stored_keys = (
                [k for k in current.keys() if k != ""]
                if isinstance(current, dict)
                else []
            )

            if not stored_keys or list(current.keys()) == [""]:
                to_fix.append((new_json, code))
            else:
                # Replace archived IDs; support 1:N splits (pct divided evenly)
                updated: dict[str, float] = {}
                changed = False
                for kid, pct in current.items():
                    if kid == "":
                        continue
                    if kid not in active_ids and kid in archived_to_replacements:
                        for repl_id, fraction in archived_to_replacements[kid]:
                            updated[repl_id] = round(
                                updated.get(repl_id, 0) + pct * fraction, 4
                            )
                        changed = True
                        log.info(
                            f"tarjas_cc [{code}]: {kid} ({pct}%) → {archived_to_replacements[kid]}"
                        )
                    else:
                        updated[kid] = pct
                if changed:
                    to_fix.append((json.dumps(updated), code))

    # Second pass: fix AppSheet-native rows (id_cc not matching any Odoo code)
    # e.g. multi-CC distributions entered manually in AppSheet with their own IDs
    already_processed = set(odoo.keys())
    for id_cc, current in existing.items():
        if id_cc in already_processed or not isinstance(current, dict):
            continue
        updated: dict[str, float] = {}
        changed = False
        for kid, pct in current.items():
            if kid == "":
                continue
            if kid not in active_ids and kid in archived_to_replacements:
                for repl_id, fraction in archived_to_replacements[kid]:
                    updated[repl_id] = round(
                        updated.get(repl_id, 0) + pct * fraction, 4
                    )
                changed = True
                log.info(
                    f"tarjas_cc [{id_cc}]: {kid} ({pct}%) → {archived_to_replacements[kid]}"
                )
            else:
                updated[kid] = pct
        if changed:
            to_fix.append((json.dumps(updated), id_cc))

    now_iso = datetime.datetime.utcnow().isoformat()
    with conn.cursor() as cur:
        for r in to_insert:
            cur.execute(
                """
                INSERT INTO appsheet.tarjas_cc (id_cc, cultivo, id_campo, valor_odoo)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (id_cc) DO NOTHING
                """,
                (r["id_cc"], r["cultivo"], r["id_campo"], r["valor_odoo"]),
            )
        for new_json, code in to_fix:
            cur.execute(
                "UPDATE appsheet.tarjas_cc SET valor_odoo = %s::jsonb WHERE id_cc = %s",
                (new_json, code),
            )
        # Record sync timestamp so the UI can display it
        cur.execute("""
            CREATE TABLE IF NOT EXISTS appsheet.sync_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cur.execute(
            """
            INSERT INTO appsheet.sync_meta (key, value) VALUES ('last_cc_sync', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """,
            (now_iso,),
        )

    log.info(f"tarjas_cc → insertados: {len(to_insert)}, corregidos: {len(to_fix)}")


def fetch_odoo_distribucion_models(
    bq: bigquery.Client,
    by_code: dict[str, dict],
) -> list[dict]:
    """
    Fetch all Odoo analytic distribution models (Modelos_Distribucion_Analitica) and
    return a list of rows ready to insert into appsheet.tarjas_cc.

    Each model becomes a "virtual CC" in tarjas_cc:
      - id_cc       = x_studio_numeracin  (the model's Odoo numeración)
      - cultivo     = name from CC_analiticos (first by code match, then by id match,
                      fallback to x_studio_numeracin itself)
      - id_campo    = derived from company_id via COMPANY_TO_CAMPO
      - valor_odoo  = analytic_distribution JSON as-is from Odoo

    Models with no x_studio_numeracin are skipped.
    """
    rows = list(
        bq.query("""
        SELECT
          CAST(id AS STRING) AS id,
          x_studio_numeracin,
          analytic_distribution,
          company_id,
          CAST(analytic_distribution_code_id AS STRING) AS analytic_distribution_code_id
        FROM `ace-scarab-484515-v1.odoo_data.Modelos_Distribucion_Analitica`
        WHERE x_studio_numeracin IS NOT NULL
    """).result()
    )

    # Build reverse lookup: odoo_id → nombre, using all entries in by_code.
    by_odoo_id: dict[str, str] = {info["id"]: info["nombre"] for info in by_code.values()}

    result: list[dict] = []
    for r in rows:
        if int(r["company_id"]) not in ALLOWED_COMPANY_IDS:
            continue

        numeracion = str(r["x_studio_numeracin"]).strip()
        if not numeracion:
            continue

        # Resolve cultivo: code match → id match → fallback to numeracion
        cultivo = None  # type: Optional[str]
        if numeracion in by_code:
            cultivo = by_code[numeracion]["nombre"]
        elif r["analytic_distribution_code_id"]:
            cc_id = str(r["analytic_distribution_code_id"])
            cultivo = by_odoo_id.get(cc_id)

        if cultivo is None:
            log.warning(
                f"Modelo distribución {numeracion}: sin nombre CC, usando numeración como cultivo"
            )
            cultivo = numeracion

        analytic_dist = r["analytic_distribution"] or "{}"

        result.append(
            {
                "id_cc": numeracion,
                "cultivo": cultivo,
                "id_campo": COMPANY_TO_CAMPO.get(int(r["company_id"]), DEFAULT_CAMPO),
                "valor_odoo": analytic_dist,
            }
        )

    log.info(f"Modelos distribución analítica obtenidos de BigQuery: {len(result)}")
    return result


def sync_distribucion_models(models: list[dict], conn) -> None:
    """
    Insert analytic distribution models into appsheet.tarjas_cc.
    Uses ON CONFLICT (id_cc) DO NOTHING — never overwrites existing rows.
    """
    if not models:
        log.info("Modelos distribución → sin registros para insertar")
        return

    with conn.cursor() as cur:
        cur.execute("SELECT id_cc::text FROM appsheet.tarjas_cc")
        existing_ids = {r[0] for r in cur.fetchall()}

    to_insert = [m for m in models if m["id_cc"] not in existing_ids]

    with conn.cursor() as cur:
        for m in to_insert:
            cur.execute(
                """
                INSERT INTO appsheet.tarjas_cc (id_cc, cultivo, id_campo, valor_odoo)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (id_cc) DO NOTHING
                """,
                (m["id_cc"], m["cultivo"], m["id_campo"], m["valor_odoo"]),
            )

    log.info(f"Modelos distribución → insertados: {len(to_insert)}, omitidos (ya existían): {len(models) - len(to_insert)}")


def sync_despacho_cc(odoo: dict[str, dict], conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT id_producto, producto, id_odoo FROM appsheet.despacho_cc")
        rows = cur.fetchall()

    to_fix = []
    for id_producto, producto, id_odoo_raw in rows:
        match = re.match(r"^(\S+?)-", producto or "")
        if not match:
            continue
        code = match.group(1).strip()
        if code not in odoo:
            continue

        current = {}
        if id_odoo_raw:
            try:
                current = json.loads(id_odoo_raw.strip().rstrip("\r\n"))
            except json.JSONDecodeError:
                pass

        if isinstance(current, dict) and list(current.keys()) == [""]:
            odoo_id = str(odoo[code]["id"])
            to_fix.append((json.dumps({odoo_id: 100}), id_producto))

    with conn.cursor() as cur:
        for new_json, id_producto in to_fix:
            cur.execute(
                "UPDATE appsheet.despacho_cc SET id_odoo = %s WHERE id_producto = %s",
                (new_json, id_producto),
            )

    log.info(f"despacho_cc → corregidos: {len(to_fix)}")


def run() -> None:
    log.info("=== sync_cc start ===")
    bq = _bq_client()
    odoo, archived_to_active = fetch_odoo_cc(bq)
    distribucion_models = fetch_odoo_distribucion_models(bq, odoo)

    conn = _pg_conn()
    try:
        sync_tarjas_cc(odoo, archived_to_active, conn)
        sync_distribucion_models(distribucion_models, conn)
        sync_despacho_cc(odoo, conn)
        conn.commit()
    except Exception:
        conn.rollback()
        log.exception("Sync failed — rolled back")
        raise
    finally:
        conn.close()

    log.info("=== sync_cc done ===")


if __name__ == "__main__":
    run()
