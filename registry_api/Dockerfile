FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    aiohttp \
    pydantic \
    asyncpg \
    "sqlalchemy[asyncio]" \
    opentelemetry-api \
    opentelemetry-sdk \
    opentelemetry-exporter-otlp-proto-grpc

COPY models/ /app/models/
COPY storage.py /app/
COPY tracing.py /app/
COPY main.py /app/

EXPOSE 9500

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9500"]
