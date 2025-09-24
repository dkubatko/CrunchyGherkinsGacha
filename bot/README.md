# Crunchy Gherkins Bot Backend

## Database migrations

This project now uses [Alembic](https://alembic.sqlalchemy.org/) to manage the SQLite schema. The migration tooling is configured under `bot/alembic`.

### Installing dependencies

From the `bot` directory install the Python requirements (Alembic and SQLAlchemy are already listed):

```bash
pip install -r requirements.txt
```

### Running migrations

The bot automatically applies migrations on startup via the helper in `utils/database.py`, so a normal launch will keep the schema current. You can also run migrations manually:

```bash
alembic -c alembic.ini upgrade head
```

### Baseline an existing database

If you already have a populated SQLite database that predates Alembic, the startup logic detects the existing `cards`/`user_rolls` tables and stamps the baseline revision (`20240924_0001`) automatically before applying any newer migrations. You can do the same manually:

```bash
alembic -c alembic.ini stamp 20240924_0001
alembic -c alembic.ini upgrade head
```

### SQLite compatibility

Alembic runs with `render_as_batch=True`, which enables schema migrations against SQLite. No extra database engine is required; the existing `DB_PATH` configuration continues to work.
