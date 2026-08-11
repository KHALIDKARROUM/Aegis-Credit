from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from app.backup import (
    BackupIntegrityError,
    backup_key,
    decrypt_legacy_backup,
    decrypt_stream,
    postgres_connection,
    verify_backup,
)


class Command(BaseCommand):
    help = "Verify an encrypted backup and, with explicit confirmation, restore it to PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--backup", required=True, help="Encrypted .brc or legacy .fernet backup.")
        parser.add_argument(
            "--confirm-database",
            help="Restore only when this exactly matches the configured database name.",
        )

    def handle(self, *args, **options):
        path = Path(options["backup"]).resolve()
        if not path.is_file():
            raise CommandError(f"Backup file does not exist: {path}")
        try:
            encryption_key = backup_key()
            format_name = verify_backup(path, encryption_key)
        except BackupIntegrityError as exc:
            raise CommandError(str(exc)) from exc

        confirmation = options.get("confirm_database")
        if not confirmation:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Backup authentication succeeded ({format_name}). Dry run only; no database was changed."
                )
            )
            return

        try:
            connection = postgres_connection()
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
        if confirmation != connection.database_name:
            raise CommandError(
                "--confirm-database must exactly match the configured database name "
                f"({connection.database_name})."
            )

        if format_name == "stream-v1":
            command = [
                "pg_restore",
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-privileges",
                *connection.command_arguments,
                "--dbname",
                connection.database_name,
            ]
            self._restore_stream(path, encryption_key, command, connection.environment)
        else:
            command = [
                "psql",
                "--single-transaction",
                "--set",
                "ON_ERROR_STOP=1",
                *connection.command_arguments,
                "--dbname",
                connection.database_name,
            ]
            plaintext = decrypt_legacy_backup(path, encryption_key)
            completed = subprocess.run(
                command,
                input=plaintext,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=connection.environment,
                check=False,
            )
            if completed.returncode:
                detail = completed.stderr.decode("utf-8", errors="replace").strip()
                raise CommandError(detail or "psql restore failed without an error message.")

        self.stdout.write(self.style.SUCCESS(f"Backup restored to database {connection.database_name}."))

    @staticmethod
    def _restore_stream(
        path: Path,
        encryption_key: bytes,
        command: list[str],
        environment: dict[str, str],
    ) -> None:
        process = None
        with tempfile.TemporaryFile() as errors:
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=errors,
                    env=environment,
                )
                if process.stdin is None:
                    raise CommandError("pg_restore did not provide an input stream.")
                with path.open("rb") as source:
                    decrypt_stream(source, process.stdin, encryption_key)
                process.stdin.close()
                return_code = process.wait()
            except (BackupIntegrityError, BrokenPipeError, OSError) as exc:
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.wait()
                raise CommandError(f"Restore aborted before commit: {exc}") from exc

            if return_code:
                errors.seek(0)
                detail = errors.read().decode("utf-8", errors="replace").strip()
                raise CommandError(detail or "pg_restore failed without an error message.")
