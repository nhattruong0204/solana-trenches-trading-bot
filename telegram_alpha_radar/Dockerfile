FROM python:3.12-slim

# System deps for asyncpg
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app/telegram_alpha_radar/

# Non-root user
RUN useradd --create-home appuser
USER appuser

# Health + Prometheus
EXPOSE 8080 9090

ENTRYPOINT ["python", "-m", "telegram_alpha_radar.app"]
