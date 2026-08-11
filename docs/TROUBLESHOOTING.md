# Troubleshooting and Removal

## Windows launcher closes or reports missing Python

- Install 64-bit Python 3.12 or newer from python.org.
- Select **Add Python to PATH**.
- Close and reopen File Explorer or the terminal.
- Delete `.venv` only if the launcher reports that its Python version is unsupported.

## Package installation fails

- Confirm internet and proxy access to PyPI.
- Check available disk space.
- Run `.venv\Scripts\python.exe -m pip check`.
- Delete `.venv` and rerun the launcher if the environment is incomplete.

## Port 8000 is already in use

Stop the other local server or run:

```bash
python run.py --port 8001
```

## Assessment unavailable

Run:

```bash
python run.py --check
```

This applies migrations, bootstraps roles, and runs Django checks with the
stable local keys. For deeper `manage.py` diagnostics, first load
`.aegis-credit-local.env` as shown in the README developer setup; direct management
commands intentionally fail when mandatory secrets are absent.

An integrity failure means the model file and manifest do not match. Regenerate
both together with the training command; do not bypass the check.

## Docker does not start

- Start Docker Desktop and wait for its engine to report ready.
- Run `docker compose --env-file .aegis-credit-docker.env config` after using the
  Docker launcher, or provide the required secrets through `.env`/your secret
  manager before running `docker compose config` directly.
- Inspect with `docker compose logs web database`.
- If port 8000 is occupied, change the host-side port in `docker-compose.yml`.

## Reset local demonstration data

Native SQLite:

1. Stop the application.
2. Delete `db.sqlite3`.
3. Run `python run.py --check` to recreate the schema and role groups.

Docker:

```bash
docker compose down
```

To also permanently delete the local PostgreSQL volume:

```bash
docker compose down -v
```

The `-v` form destroys local case and audit data. Export anything required first.

## Remove the local installation

Stop the server, then delete `.venv`, `db.sqlite3`, and `staticfiles`. The source
project and generated model/report artifacts remain until the project folder is
removed.
