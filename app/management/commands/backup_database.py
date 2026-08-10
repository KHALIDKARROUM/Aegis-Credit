from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a PostgreSQL dump encrypted before it is written to disk."

    def add_arguments(self, parser):
        parser.add_argument("--destination", required=True, help="Directory for encrypted backup files.")

    def handle(self, *args, **options):
        database_url = __import__("os").environ.get("DATABASE_URL")
        if not database_url:
            raise CommandError("DATABASE_URL is required; SQLite backups are not supported by this command.")
        destination = Path(options["destination"]).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = destination / f"bankrisk-{timestamp}.sql.fernet"
        dump = subprocess.run(
            ["pg_dump", "--format=plain", "--no-owner", database_url],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if dump.returncode:
            raise CommandError(dump.stderr.decode("utf-8", errors="replace").strip())
        output.write_bytes(Fernet(settings.BACKUP_ENCRYPTION_KEY.encode("ascii")).encrypt(dump.stdout))
        self.stdout.write(self.style.SUCCESS(f"Encrypted backup written to {output}"))
