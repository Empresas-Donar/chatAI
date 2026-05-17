import json
from mcp.server.fastmcp import FastMCP
import bigquery_client as bq

mcp = FastMCP(
    name="donar-data",
    instructions=(
        "MCP server for Donar / KONTROLAG business data. "
        "Sources: Odoo exported to BigQuery (project ace-scarab-484515-v1, dataset odoo_data). "
        "Tables: Cuentas_por_cobrar (invoices), Remuneraciones (payroll), "
        "Reporte_Analitico (cost center lines), Ordenes_de_aplicacion (field applications). "
        "Always call list_tables first if unsure which tables exist. "
        "Use query_bigquery for aggregations and cross-table analysis. "
        "Amounts are in Chilean pesos (CLP)."
    ),
)


@mcp.tool()
def list_tables() -> str:
    """List all available tables in the Odoo BigQuery dataset with row counts."""
    tables = bq.list_tables()
    return json.dumps(tables, ensure_ascii=False, indent=2)


@mcp.tool()
def describe_table(table_id: str) -> str:
    """
    Return schema and 3 sample rows for a table.

    Args:
        table_id: Exact table name, e.g. 'Cuentas_por_cobrar' or 'Ordenes_de_aplicacion'
    """
    result = bq.describe_table(table_id)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool()
def query_bigquery(sql: str, max_rows: int = 100) -> str:
    """
    Execute a SQL query against BigQuery and return results as JSON.

    Always use full table path: `ace-scarab-484515-v1.odoo_data.TABLE_NAME`
    Use list_tables to discover available tables before querying.
    Limit results sensibly — default cap is 100 rows.

    Args:
        sql: Standard SQL query
        max_rows: Maximum rows to return (default 100, max 500)
    """
    max_rows = min(max_rows, 500)
    rows = bq.run_query(sql, max_rows)
    return json.dumps(rows, ensure_ascii=False, indent=2, default=str)


if __name__ == "__main__":
    mcp.run()
