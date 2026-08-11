FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client && \
    rm -rf /var/lib/apt/lists/* && \
    addgroup --system aegis_credit && adduser --system --ingroup aegis_credit aegis_credit

COPY requirements-prod.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements-prod.txt

COPY . .
RUN BUILD_FERNET_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" && \
    DEBUG=True SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
    AUDIT_HMAC_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
    FIELD_ENCRYPTION_KEY="$BUILD_FERNET_KEY" BACKUP_ENCRYPTION_KEY="$BUILD_FERNET_KEY" \
    MODEL_SIGNING_PUBLIC_KEY="$(python -c 'import base64, os; print(base64.b64encode(os.urandom(32)).decode())')" \
    python manage.py collectstatic --no-input && \
    chown -R aegis_credit:aegis_credit /app

USER aegis_credit
EXPOSE 8000

CMD ["sh", "/app/docker-entrypoint.sh"]
