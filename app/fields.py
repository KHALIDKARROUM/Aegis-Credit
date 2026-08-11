"""Application-owned encrypted model fields.

These fields encrypt the entire value before it reaches the database.  They
are deliberately not queryable: sensitive applicant data must not be used for
database-side searching, filtering, or analytics.
"""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models


def _cipher() -> MultiFernet:
    configured = getattr(settings, "FIELD_ENCRYPTION_KEYS", None)
    keys = configured or [settings.FIELD_ENCRYPTION_KEY]
    return MultiFernet([Fernet(key.encode("ascii")) for key in keys])


class EncryptedJSONField(models.TextField):
    """Store JSON as an authenticated Fernet ciphertext, never plaintext JSON."""

    description = "Encrypted JSON"

    def get_prep_value(self, value: Any) -> str | None:
        if value is None:
            return None
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        return _cipher().encrypt(payload.encode("utf-8")).decode("ascii")

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> Any:
        if value is None or value == "":
            return self.get_default() if value is None else {}
        if isinstance(value, (dict, list)):
            # Transitional support for data written by the old JSONField.
            return value
        try:
            plaintext = _cipher().decrypt(str(value).encode("ascii"))
        except (InvalidToken, UnicodeEncodeError) as exc:
            raise ValueError("Encrypted database value cannot be authenticated or decrypted.") from exc
        return json.loads(plaintext.decode("utf-8"))

    def to_python(self, value: Any) -> Any:
        if value is None or isinstance(value, (dict, list)):
            return value
        return self.from_db_value(value, None, None)


class EncryptedTextField(models.TextField):
    """Store free text as authenticated Fernet ciphertext."""

    description = "Encrypted text"

    def get_prep_value(self, value: Any) -> str | None:
        if value is None:
            return None
        return _cipher().encrypt(str(value).encode("utf-8")).decode("ascii")

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> str:
        if value is None:
            return ""
        try:
            return _cipher().decrypt(str(value).encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeEncodeError) as exc:
            raise ValueError("Encrypted database value cannot be authenticated or decrypted.") from exc

    def to_python(self, value: Any) -> str:
        if value is None:
            return ""
        # Database values are authenticated and decrypted by ``from_db_value``.
        # ``to_python`` is also called by model validation for values that are
        # already plaintext (for example a bound ModelForm), so decrypting here
        # would reject every legitimate form update as an invalid Fernet token.
        return str(value)


class EncryptedBinaryField(models.BinaryField):
    """Store bounded uploaded bytes as authenticated ciphertext."""

    description = "Encrypted binary"

    def get_prep_value(self, value: Any) -> bytes | None:
        if value is None:
            return None
        raw = bytes(value)
        return _cipher().encrypt(raw)

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> bytes:
        if value is None:
            return b""
        try:
            return _cipher().decrypt(bytes(value))
        except (InvalidToken, TypeError, ValueError) as exc:
            raise ValueError("Encrypted binary value cannot be authenticated or decrypted.") from exc

    def to_python(self, value: Any) -> bytes:
        if value is None:
            return b""
        return bytes(value)
