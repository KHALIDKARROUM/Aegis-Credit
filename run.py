#!/usr/bin/env python3
"""Start BankRisk Compass locally with one command.

Run ``python run.py`` (or ``py run.py`` on Windows).  The script keeps all
local-only configuration in ``.bankrisk-local.env`` so encryption keys stay
stable between launches and existing local cases remain readable.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import secrets
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS = PROJECT_ROOT / "requirements-app.txt"
LOCAL_ENV = PROJECT_ROOT / ".bankrisk-local.env"
REQUIREMENTS_MARKER = VENV_DIR / ".bankrisk-requirements.sha256"


def venv_python() -> Path:
    """Return the virtual-environment interpreter for the active platform."""
    return VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def require_supported_python() -> None:
    if sys.version_info < (3, 12):
        raise SystemExit(
            "BankRisk Compass requires Python 3.12 or newer. "
            "Install a supported Python version and run this command again."
        )


def create_venv_if_needed() -> Path:
    python = venv_python()
    if python.exists():
        return python

    print("Creating local Python environment...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    if not python.exists():
        raise RuntimeError("The local Python environment was not created successfully.")
    return python


def requirements_digest() -> str:
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def install_dependencies(python: Path) -> None:
    digest = requirements_digest()
    installed_digest = REQUIREMENTS_MARKER.read_text().strip() if REQUIREMENTS_MARKER.exists() else ""
    if digest == installed_digest:
        return

    print("Installing required packages (this may take a few minutes the first time)...")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(REQUIREMENTS)],
        check=True,
    )
    REQUIREMENTS_MARKER.write_text(f"{digest}\n", encoding="utf-8")


def parse_env_file(path: Path) -> dict[str, str]:
    """Read the deliberately simple KEY=VALUE local launcher file."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip()
    return values


def fernet_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def create_local_environment() -> dict[str, str]:
    """Create stable, untracked development settings without touching ``.env``."""
    values = parse_env_file(LOCAL_ENV)
    defaults = {
        "DEBUG": "True",
        "SECURE_SSL_REDIRECT": "False",
        "ALLOWED_HOSTS": "127.0.0.1,localhost",
        "LOGIN_REQUIRED": "False",
        # The included demonstration data is deliberately not an operational
        # model release. Keep the governance gate in place for local demos too.
        "DATA_PROVENANCE_VERIFIED": "False",
        "SECRET_KEY": secrets.token_urlsafe(48),
        "AUDIT_HMAC_KEY": secrets.token_urlsafe(48),
        "FIELD_ENCRYPTION_KEY": fernet_key(),
        "BACKUP_ENCRYPTION_KEY": fernet_key(),
        "MODEL_SIGNING_PUBLIC_KEY": base64.b64encode(os.urandom(32)).decode("ascii"),
    }
    changed = False
    for name, value in defaults.items():
        if not values.get(name):
            values[name] = value
            changed = True

    if changed or not LOCAL_ENV.exists():
        header = (
            "# Generated for local development by run.py. Keep this file private: it\n"
            "# contains keys needed to read locally stored encrypted case data.\n"
        )
        contents = header + "".join(f"{name}={value}\n" for name, value in sorted(values.items()))
        LOCAL_ENV.write_text(contents, encoding="utf-8")
        print("Created local development settings in .bankrisk-local.env.")
    return values


def command_environment() -> dict[str, str]:
    # This is a local-only launcher. Its saved configuration deliberately wins
    # over ambient CI/editor variables (for example DEBUG=release), which could
    # otherwise make a development server look for a production static manifest.
    # Edit .bankrisk-local.env when an intentional local override is needed.
    environment = os.environ.copy()
    environment.update(create_local_environment())
    return environment


def run_manage(python: Path, environment: dict[str, str], *arguments: str) -> None:
    subprocess.run([str(python), "manage.py", *arguments], cwd=PROJECT_ROOT, env=environment, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run BankRisk Compass locally.")
    parser.add_argument("--host", default="127.0.0.1", help="Address to bind (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000).")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the local URL in a browser.")
    parser.add_argument("--check", action="store_true", help="Prepare the project and run Django checks without starting the server.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    require_supported_python()
    python = create_venv_if_needed()
    install_dependencies(python)
    environment = command_environment()

    print("Preparing the local database...")
    run_manage(python, environment, "migrate", "--no-input")
    run_manage(python, environment, "bootstrap_roles")
    if args.check:
        run_manage(python, environment, "check")
        print("BankRisk Compass is ready to start with: python run.py")
        return

    url = f"http://{args.host}:{args.port}/"
    print(f"\nBankRisk Compass is running at {url}")
    print("Press Ctrl+C to stop it.\n")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    try:
        run_manage(python, environment, "runserver", f"{args.host}:{args.port}")
    except KeyboardInterrupt:
        print("\nBankRisk Compass stopped.")


if __name__ == "__main__":
    main()
