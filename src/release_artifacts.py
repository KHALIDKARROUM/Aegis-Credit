"""Model-release integrity, signing, and immutable report-bundle helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import joblib
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


class ArtifactIntegrityError(RuntimeError):
    """Raised when an artifact cannot be tied to an approved release."""


@dataclass(frozen=True)
class VerifiedModelArtifact:
    bundle: dict[str, Any]
    manifest: dict[str, Any]
    model_path: Path
    model_sha256: str
    signed_release: bool


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_manifest(manifest: dict[str, Any]) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_manifest(
    manifest: dict[str, Any],
    *,
    private_key_base64: str | None = None,
    key_id: str | None = None,
) -> dict[str, Any]:
    encoded_key = private_key_base64 or os.getenv("MODEL_SIGNING_PRIVATE_KEY", "")
    if not encoded_key:
        raise RuntimeError(
            "MODEL_SIGNING_PRIVATE_KEY must be supplied by the release secret manager."
        )
    try:
        private_key = Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(encoded_key, validate=True)
        )
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "MODEL_SIGNING_PRIVATE_KEY must be a base64-encoded Ed25519 private key."
        ) from exc

    signed = dict(manifest)
    signed["signature_algorithm"] = "ed25519"
    signed["signing_key_id"] = key_id or os.getenv("MODEL_SIGNING_KEY_ID", "default")
    signed["signature"] = base64.b64encode(
        private_key.sign(canonical_manifest(signed))
    ).decode("ascii")
    return signed


def verify_manifest_signature(
    manifest: dict[str, Any],
    *,
    public_key_base64: str | None = None,
) -> None:
    signature = manifest.get("signature")
    if manifest.get("signature_algorithm") != "ed25519" or not signature:
        raise ArtifactIntegrityError("Model manifest is unsigned.")
    encoded_key = public_key_base64 or os.getenv("MODEL_SIGNING_PUBLIC_KEY", "")
    if not encoded_key:
        raise ArtifactIntegrityError(
            "MODEL_SIGNING_PUBLIC_KEY is required to verify a signed release."
        )

    unsigned = dict(manifest)
    unsigned.pop("signature", None)
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(encoded_key, validate=True)
        )
        public_key.verify(
            base64.b64decode(str(signature), validate=True),
            canonical_manifest(unsigned),
        )
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ArtifactIntegrityError(
            "Model manifest signature verification failed."
        ) from exc


def _confined_release_path(models_dir: Path, relative_path: str, *, name: str) -> Path:
    candidate = (models_dir / relative_path).resolve()
    releases_dir = (models_dir / "releases").resolve()
    if releases_dir not in candidate.parents or candidate.name != name:
        raise ArtifactIntegrityError(f"Release path is invalid: {relative_path}")
    return candidate


def resolve_signed_model_path(manifest: dict[str, Any], models_dir: Path) -> Path:
    relative_path = manifest.get("artifact_path")
    if not isinstance(relative_path, str) or not relative_path:
        raise ArtifactIntegrityError(
            "Model manifest does not identify an immutable release artifact."
        )
    candidate = _confined_release_path(models_dir, relative_path, name="model.pkl")
    expected_hash = str(manifest.get("model_sha256", ""))
    if candidate.parent.name != expected_hash:
        raise ArtifactIntegrityError(
            "Content-addressed release directory does not match the model digest."
        )
    return candidate


def verify_signed_release_manifest(
    manifest: dict[str, Any],
    *,
    public_key_base64: str | None = None,
) -> None:
    verify_manifest_signature(manifest, public_key_base64=public_key_base64)
    if manifest.get("git_dirty") is not False or not manifest.get("git_tag"):
        raise ArtifactIntegrityError(
            "Model was not released from a clean, versioned Git tag."
        )
    if manifest.get("data_provenance_verified") is not True:
        raise ArtifactIntegrityError(
            "Model manifest does not attest to verified training-data provenance."
        )
    if not manifest.get("feature_contract_version") or not manifest.get("features"):
        raise ArtifactIntegrityError("Model manifest has no versioned feature contract.")
    if manifest.get("threshold") is None:
        raise ArtifactIntegrityError("Model manifest has no decision threshold.")
    if not manifest.get("report_bundle"):
        raise ArtifactIntegrityError("Model manifest has no immutable report bundle.")


def load_verified_model_artifact(
    manifest_path: Path,
    *,
    demo_model_path: Path | None = None,
    allow_unsigned_demo: bool = False,
    public_key_base64: str | None = None,
) -> VerifiedModelArtifact:
    """Verify integrity/authenticity before deserializing a model bundle.

    Unsigned legacy artifacts are rejected unless the caller deliberately opts
    into demonstration mode.  A manifest that claims to be a release is never
    downgraded to the demonstration path after a verification failure.
    """

    if not manifest_path.exists():
        raise FileNotFoundError(f"Model manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    models_dir = manifest_path.parent
    signed_release = bool(manifest.get("artifact_path") or manifest.get("signature"))

    if signed_release:
        verify_signed_release_manifest(
            manifest,
            public_key_base64=public_key_base64,
        )
        model_path = resolve_signed_model_path(manifest, models_dir)
    else:
        if not allow_unsigned_demo:
            raise ArtifactIntegrityError(
                "Unsigned demonstration model rejected. Pass --allow-unsigned-demo "
                "only for an isolated local demonstration."
            )
        model_path = (demo_model_path or models_dir / "credit_risk_model.pkl").resolve()

    expected_hash = str(manifest.get("model_sha256", ""))
    if not model_path.exists() or not expected_hash:
        raise ArtifactIntegrityError("Model artifact or expected digest is missing.")
    actual_hash = file_sha256(model_path)
    if not hmac.compare_digest(actual_hash, expected_hash):
        raise ArtifactIntegrityError("Model artifact integrity verification failed.")

    bundle = joblib.load(model_path)
    if not isinstance(bundle, dict):
        raise ArtifactIntegrityError("Model bundle must be a dictionary.")
    if str(bundle.get("model_version")) != str(manifest.get("model_version")):
        raise ArtifactIntegrityError("Model version does not match its manifest.")
    if signed_release:
        if bundle.get("git_dirty") is not False:
            raise ArtifactIntegrityError("Model bundle records a dirty Git worktree.")
        if bundle.get("git_tag") != manifest.get("git_tag"):
            raise ArtifactIntegrityError("Model bundle tag does not match its manifest.")
        if bundle.get("data_sha256") != manifest.get("data_sha256"):
            raise ArtifactIntegrityError("Model bundle data digest does not match its manifest.")
        if bundle.get("feature_contract_version") != manifest.get("feature_contract_version"):
            raise ArtifactIntegrityError(
                "Model bundle feature-contract version does not match its manifest."
            )
        if list(bundle.get("features", [])) != list(manifest.get("features", [])):
            raise ArtifactIntegrityError("Model bundle features do not match its manifest.")
        try:
            threshold_matches = float(bundle.get("threshold")) == float(
                manifest.get("threshold")
            )
        except (TypeError, ValueError):
            threshold_matches = False
        if not threshold_matches:
            raise ArtifactIntegrityError("Model bundle threshold does not match its manifest.")
        verified_report_paths(manifest, models_dir=models_dir)

    return VerifiedModelArtifact(
        bundle=bundle,
        manifest=manifest,
        model_path=model_path,
        model_sha256=actual_hash,
        signed_release=signed_release,
    )


def snapshot_report_bundle(
    *,
    reports_dir: Path,
    release_dir: Path,
    artifact_names: Iterable[str],
    models_dir: Path,
) -> dict[str, Any]:
    """Copy generated reports beside an immutable model and return signed metadata."""

    destination_dir = release_dir / "reports"
    destination_dir.mkdir(parents=True, exist_ok=True)
    artifact_hashes: dict[str, str] = {}

    for name in sorted(set(artifact_names)):
        if Path(name).name != name:
            raise RuntimeError(f"Report artifact name must be a basename: {name}")
        source = reports_dir / name
        if not source.is_file():
            raise RuntimeError(f"Required release report is missing: {source}")
        source_hash = file_sha256(source)
        destination = destination_dir / name
        if destination.exists():
            if not hmac.compare_digest(file_sha256(destination), source_hash):
                raise RuntimeError(
                    f"Refusing to overwrite immutable report artifact: {destination}"
                )
        else:
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
        artifact_hashes[name] = source_hash

    return {
        "path": destination_dir.relative_to(models_dir).as_posix(),
        "artifacts": artifact_hashes,
    }


def verified_report_paths(
    manifest: dict[str, Any],
    *,
    models_dir: Path,
) -> dict[str, Path]:
    """Resolve and hash-check every report bound into a signed manifest."""

    report_bundle = manifest.get("report_bundle")
    if not isinstance(report_bundle, dict):
        raise ArtifactIntegrityError("Signed model manifest has no report bundle.")
    relative_dir = report_bundle.get("path")
    hashes = report_bundle.get("artifacts")
    if not isinstance(relative_dir, str) or not isinstance(hashes, dict) or not hashes:
        raise ArtifactIntegrityError("Signed report-bundle metadata is incomplete.")

    report_dir = (models_dir / relative_dir).resolve()
    releases_dir = (models_dir / "releases").resolve()
    if releases_dir not in report_dir.parents or report_dir.name != "reports":
        raise ArtifactIntegrityError("Signed report-bundle path is invalid.")

    model_path = resolve_signed_model_path(manifest, models_dir)
    if report_dir.parent != model_path.parent:
        raise ArtifactIntegrityError("Reports are not bound to the model release directory.")

    resolved: dict[str, Path] = {}
    for name, expected_hash in hashes.items():
        if not isinstance(name, str) or Path(name).name != name:
            raise ArtifactIntegrityError("Report manifest contains an invalid artifact name.")
        path = (report_dir / name).resolve()
        if path.parent != report_dir:
            raise ArtifactIntegrityError(f"Report path escapes its release directory: {name}")
        if not path.is_file() or not hmac.compare_digest(
            file_sha256(path), str(expected_hash)
        ):
            raise ArtifactIntegrityError(f"Report artifact verification failed: {name}")
        resolved[name] = path
    return resolved
