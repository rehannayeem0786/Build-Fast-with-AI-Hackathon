# NexusFlow AI — production image
# Chromium is installed at build time so the self-healing browser engine
# runs identically in the cloud and locally.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . .

ENV HOST=0.0.0.0 \
    PORT=8000 \
    APPROVAL_TIMEOUT_SEC=120

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
