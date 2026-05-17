import os
from google.cloud import bigquery
from google.oauth2 import service_account

GCP_PROJECT = "ace-scarab-484515-v1"
DATASET = "odoo_data"
KEY_PATH = os.environ.get(
    "BIGQUERY_KEY_PATH",
    "/Users/bedomax/startups/donar/bigquery-odoo-key.json"
)


def get_client() -> bigquery.Client:
    credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
    return bigquery.Client(project=GCP_PROJECT, credentials=credentials)


def list_tables() -> list[dict]:
    client = get_client()
    tables = client.list_tables(f"{GCP_PROJECT}.{DATASET}")
    result = []
    for t in tables:
        table = client.get_table(t.reference)
        result.append({
            "table_id": t.table_id,
            "num_rows": table.num_rows,
            "description": table.description or "",
        })
    return result


def describe_table(table_id: str) -> dict:
    client = get_client()
    table = client.get_table(f"{GCP_PROJECT}.{DATASET}.{table_id}")
    fields = [
        {"name": f.name, "type": f.field_type, "description": f.description or ""}
        for f in table.schema
    ]
    # sample 3 rows
    df = client.query(
        f"SELECT * FROM `{GCP_PROJECT}.{DATASET}.{table_id}` LIMIT 3"
    ).to_dataframe()
    sample = df.to_dict(orient="records")
    return {
        "table_id": table_id,
        "num_rows": table.num_rows,
        "fields": fields,
        "sample": sample,
    }


def run_query(sql: str, max_rows: int = 100) -> list[dict]:
    client = get_client()
    df = client.query(sql).to_dataframe()
    if len(df) > max_rows:
        df = df.head(max_rows)
    # convert non-serializable types to str
    for col in df.columns:
        if df[col].dtype == "object":
            pass
        else:
            df[col] = df[col].astype(str)
    return df.to_dict(orient="records")
