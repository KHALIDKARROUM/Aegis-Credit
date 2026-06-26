FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system bankrisk && adduser --system --ingroup bankrisk bankrisk

COPY requirements-prod.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements-prod.txt

COPY . .
RUN DEBUG=True SECRET_KEY=container-build-only python manage.py collectstatic --no-input && \
    chown -R bankrisk:bankrisk /app

USER bankrisk
EXPOSE 8000

CMD ["sh", "/app/docker-entrypoint.sh"]
