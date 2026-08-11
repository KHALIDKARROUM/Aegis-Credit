from __future__ import annotations

import os
import secrets
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from app.backup import BackupIntegrityError, backup_key, encrypt_stream, postgres_connection


class Command(BaseCommand):
    help = "Create an authenticated, encrypted PostgreSQL backup without writing plaintext to disk."

    def add_arguments(self, parser):
        parser.add_argument("--destination", required=True, help="Directory for encrypted backup files.")

    def handle(self, *args, **options):
        try:
            connection = postgres_connection()
            encryption_key = backup_key()
        except (RuntimeError, BackupIntegrityError) as exc:
            raise CommandError(str(exc)) from exc

        destination = Path(options["destination"]).resolve()
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = destination / f"aegis-credit-{timestamp}.dump.brc"
        temporary_output = destination / f".{output.name}.{secrets.token_hex(8)}.tmp"
        command = [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            *connection.command_arguments,
            "--dbname",
            connection.database_name,
        ]

        process = None
        try:
            descriptor = os.open(
                temporary_output,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as encrypted_output, tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=errors,
                    env=connection.environment,
                )
                if process.stdout is None:
                    raise CommandError("pg_dump did not provide an output stream.")
                encrypt_stream(process.stdout, encrypted_output, encryption_key)
                process.stdout.close()
                return_code = process.wait()
                if return_code:
                    errors.seek(0)
                    detail = errors.read().decode("utf-8", errors="replace").strip()
                    raise CommandError(detail or "pg_dump failed without an error message.")
                encrypted_output.flush()
                os.fsync(encrypted_output.fileno())
            os.replace(temporary_output, output)
            if os.name != "nt":
                output.chmod(0o600)
        except OSError as exc:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait()
            raise CommandError(f"Unable to create the encrypted backup: {exc}") from exc
        finally:
            temporary_output.unlink(missing_ok=True)

        self.stdout.write(self.style.SUCCESS(f"Encrypted backup written to {output}"))
