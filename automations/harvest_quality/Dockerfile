FROM python:3.12-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY harvest_quality ./harvest_quality
COPY config ./config

ENV TZ=America/Santiago
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "harvest_quality", "run"]
