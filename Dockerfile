# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=botgpt.settings

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

RUN mkdir -p /app/media /app/staticfiles /app/chroma_db

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py shell -c \"from django.contrib.auth.models import User; User.objects.filter(username='vivekn').exists() or User.objects.create_superuser('vivekn', 'admin@example.com', 'vivek@123')\" && gunicorn botgpt.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120"]
