FROM python:3.12-slim

WORKDIR /app

COPY web_migrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source and shared core module
COPY web_migrator/ ./web_migrator/
COPY core/ ./core/

RUN mkdir -p /app/uploads

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "web_migrator.backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
