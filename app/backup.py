"""Streaming, authenticated database-backup primitives.

The current format keeps PostgreSQL dump bytes off disk in plaintext.  A small
legacy reader is retained for backups created by the original Fernet command.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from django.conf import settings


MAGIC = b"AEGIS-CREDIT-BACKUP\x01"
# Stream backups written before the project rename remain readable.
LEGACY_MAGIC = bytes.fromhex("42414e4b5249534b2d4241434b555001")
NONCE_SIZE = 12
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024


class BackupIntegrityError(RuntimeError):
    """Raised when an encrypted backup is malformed or cannot be authenticated."""


@dataclass(frozen=True)
class PostgresConnection:
    database_name: str
    command_arguments: tuple[str, ...]
    environment: dict[str, str]


def backup_key() -> bytes:
    try:
        key = base64.urlsafe_b64decode(settings.BACKUP_ENCRYPTION_KEY.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise BackupIntegrityError("The configured backup encryption key is invalid.") from exc
    if len(key) != 32:
        raise BackupIntegrityError("The configured backup encryption key must contain 32 bytes.")
    return key


def encrypt_stream(source: BinaryIO, destination: BinaryIO, key: bytes) -> None:
    nonce = os.urandom(NONCE_SIZE)
    header = MAGIC + nonce
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    destination.write(header)
    while chunk := source.read(CHUNK_SIZE):
        destination.write(encryptor.update(chunk))
    destination.write(encryptor.finalize())
    destination.write(encryptor.tag)


def _encrypted_layout(source: BinaryIO) -> tuple[bytes, bytes, int]:
    magic = _stream_magic(source)
    if magic is None:
        raise BackupIntegrityError("The encrypted backup format is not recognized.")
    header_size = len(magic) + NONCE_SIZE
    source.seek(0, os.SEEK_END)
    total_size = source.tell()
    if total_size < header_size + TAG_SIZE:
        raise BackupIntegrityError("The encrypted backup is truncated.")
    source.seek(0)
    header = source.read(header_size)
    nonce = header[len(magic) :]
    source.seek(-TAG_SIZE, os.SEEK_END)
    tag = source.read(TAG_SIZE)
    source.seek(header_size)
    return header, tag, total_size - header_size - TAG_SIZE


def _stream_magic(source: BinaryIO) -> bytes | None:
    for magic in (MAGIC, LEGACY_MAGIC):
        source.seek(0)
        if source.read(len(magic)) == magic:
            return magic
    return None


def decrypt_stream(source: BinaryIO, destination: BinaryIO | None, key: bytes) -> None:
    header, tag, remaining = _encrypted_layout(source)
    magic = _stream_magic(source)
    if magic is None:
        raise BackupIntegrityError("The encrypted backup format is not recognized.")
    source.seek(len(magic) + NONCE_SIZE)
    nonce = header[len(magic) :]
    decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
    decryptor.authenticate_additional_data(header)
    try:
        while remaining:
            chunk = source.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                raise BackupIntegrityError("The encrypted backup is truncated.")
            remaining -= len(chunk)
            plaintext = decryptor.update(chunk)
            if destination is not None:
                destination.write(plaintext)
        final = decryptor.finalize()
        if destination is not None:
            destination.write(final)
    except InvalidTag as exc:
        raise BackupIntegrityError("The encrypted backup failed authentication.") from exc


def backup_format(path: Path) -> str:
    with path.open("rb") as source:
        return "stream-v1" if _stream_magic(source) is not None else "legacy-fernet"


def verify_backup(path: Path, key: bytes) -> str:
    format_name = backup_format(path)
    if format_name == "stream-v1":
        with path.open("rb") as source:
            decrypt_stream(source, None, key)
        return format_name

    try:
        Fernet(base64.urlsafe_b64encode(key)).decrypt(path.read_bytes())
    except (InvalidToken, OSError) as exc:
        raise BackupIntegrityError("The legacy backup failed authentication.") from exc
    return format_name


def decrypt_legacy_backup(path: Path, key: bytes) -> bytes:
    try:
        return Fernet(base64.urlsafe_b64encode(key)).decrypt(path.read_bytes())
    except (InvalidToken, OSError) as exc:
        raise BackupIntegrityError("The legacy backup failed authentication.") from exc


def postgres_connection() -> PostgresConnection:
    database = settings.DATABASES["default"]
    if "postgresql" not in str(database.get("ENGINE", "")):
        raise RuntimeError("PostgreSQL is required for database backup and restore commands.")

    database_name = str(database.get("NAME", "")).strip()
    if not database_name:
        raise RuntimeError("The configured PostgreSQL database name is blank.")

    arguments: list[str] = []
    for setting_name, option in (
        ("HOST", "--host"),
        ("PORT", "--port"),
        ("USER", "--username"),
    ):
        value = str(database.get(setting_name, "")).strip()
        if value:
            arguments.extend((option, value))

    inherited_names = (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
    )
    environment = {
        name: os.environ[name]
        for name in inherited_names
        if name in os.environ
    }
    password = str(database.get("PASSWORD", ""))
    if password:
        environment["PGPASSWORD"] = password
    option_environment = {
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
    }
    for option_name, environment_name in option_environment.items():
        value = database.get("OPTIONS", {}).get(option_name)
        if value:
            environment[environment_name] = str(value)

    return PostgresConnection(database_name, tuple(arguments), environment)
