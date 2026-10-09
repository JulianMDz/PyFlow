FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# docker-compose builds with INSTALL_DEV=true to get pytest, ruff and mypy; production doesn't
ARG INSTALL_DEV=false
COPY requirements.txt requirements-dev.txt ./
RUN if [ "$INSTALL_DEV" = "true" ]; then pip install --no-cache-dir -r requirements-dev.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi

COPY . .

RUN useradd --create-home payflow
USER payflow

EXPOSE 8000

# Hosting platforms choose the port through $PORT. --proxy-headers makes the client IP
# (used by the risk rate limit) the visitor's, not the platform's load balancer.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
