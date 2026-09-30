FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY . .
ENV FIELDGUARD_DATA_DIR=/data
# Set FIELDGUARD_SIGNING_KEY, FIELDGUARD_JWT_SECRET and FIELDGUARD_DEMO_PASSWORD as host environment variables.
# Mount a persistent volume at /data or records vanish on redeploy.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
