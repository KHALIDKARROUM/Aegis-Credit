"""Application-owned encrypted model fields.

These fields encrypt the entire value before it reaches the database.  They
are deliberately not queryable: sensitive applicant data must not be used for
database-side searching, filtering, or analytics.
"""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _cipher() -> Fernet:
    return Fernet(settings.FIELD_ENCRYPTION_KEY.encode("ascii"))


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
            # This path exists only while migration 0005 converts records from
            # the former JSONField. New plaintext writes are impossible.
            try:
                return json.loads(str(value))
            except json.JSONDecodeError:
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
        except (InvalidToken, UnicodeEncodeError):
            # Legacy reviewer notes are converted by migration 0005.
            return str(value)

    def to_python(self, value: Any) -> str:
        if value is None:
            return ""
        return self.from_db_value(value, None, None)
