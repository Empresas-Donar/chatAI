FROM python:3.12-slim

WORKDIR /app

COPY chatai/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source, shared modules, and BigQuery client used by chat
COPY chatai/ ./chatai/
COPY core/ ./core/
COPY mcp_server/bigquery_client.py ./mcp_server/bigquery_client.py

RUN mkdir -p /app/uploads

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "chatai.backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
