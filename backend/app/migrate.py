"""Small, explicit schema migrations for existing SQLite databases.

`Base.metadata.create_all` creates missing tables but never changes existing ones, so a
database made by an earlier version needs these steps. Each step checks the current
schema first, so running it again does nothing.

  v8-cartons-mm   cartons stored in centimetres -> millimetres, with nominal and internal
                  sizes, optional weight limit, predefined/sample flags. SQLite cannot change
                  column types or nullability in place, so the table is rebuilt with the
                  documented 12-step procedure (new table, copy, drop, rename) with foreign
                  keys switched off. Row ids are kept, so every plan, reservation, stock
                  movement and completion still points at the same carton.
  v8-order-idem   orders.idempotency_key for duplicate-safe checkout.
"""
import logging

from sqlalchemy import Engine, inspect, text
from sqlalchemy.schema import CreateIndex, CreateTable

log = logging.getLogger("tote.migrate")


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in inspect(conn).get_columns(table)}


def _tables(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _migrate_cartons(engine: Engine) -> bool:
    # This table-rebuild migration is specifically for old SQLite databases.
    # New databases on other engines are created from current SQLAlchemy metadata.
    if engine.dialect.name != "sqlite":
        return False
    from .models import Carton
    with engine.connect() as conn:
        if "cartons" not in _tables(conn) or "length_mm" in _columns(conn, "cartons"):
            return False
    table = Carton.__table__
    create_sql = str(CreateTable(table).compile(engine)).replace('CREATE TABLE cartons', 'CREATE TABLE cartons_v8', 1)
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("PRAGMA foreign_keys=OFF")
        cur.execute("BEGIN")
        cur.execute(create_sql)
        # Old rows were entered as internal sizes in cm. Nominal = internal; not verified.
        cur.execute("""
            INSERT INTO cartons_v8 (id, code, name, category,
                nominal_length_mm, nominal_width_mm, nominal_height_mm, length_mm, width_mm, height_mm,
                internal_verified, max_weight_g, unit_cost, stock, reserved, min_stock, is_active, is_baseline,
                is_predefined, sample_fields, notes, created_at, updated_at)
            SELECT id, code, name, 'Earlier catalogue',
                CAST(ROUND(length_cm * 10) AS INTEGER), CAST(ROUND(width_cm * 10) AS INTEGER),
                CAST(ROUND(height_cm * 10) AS INTEGER), CAST(ROUND(length_cm * 10) AS INTEGER),
                CAST(ROUND(width_cm * 10) AS INTEGER), CAST(ROUND(height_cm * 10) AS INTEGER),
                0, max_weight_g, unit_cost, stock, reserved, min_stock, is_active, is_baseline,
                0, '[]', notes, updated_at, updated_at
            FROM cartons""")
        cur.execute("DROP TABLE cartons")
        cur.execute("ALTER TABLE cartons_v8 RENAME TO cartons")
        for idx in table.indexes:
            cur.execute(str(CreateIndex(idx).compile(engine)))
        bad = cur.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(f"Foreign-key check failed after carton migration: {bad[:3]}")
        raw.commit()
        log.warning("Migrated the cartons table to millimetres (v8).")
        return True
    except Exception:
        raw.rollback()
        raise
    finally:
        try:
            raw.cursor().execute("PRAGMA foreign_keys=ON")
        finally:
            raw.close()


def _migrate_orders(engine: Engine) -> bool:
    with engine.begin() as conn:
        if "orders" not in _tables(conn) or "idempotency_key" in _columns(conn, "orders"):
            return False
        conn.execute(text("ALTER TABLE orders ADD COLUMN idempotency_key VARCHAR(80)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_idempotency_key ON orders (idempotency_key)"))
    log.warning("Added orders.idempotency_key (v8).")
    return True


def run(engine: Engine) -> list[str]:
    done = []
    if _migrate_cartons(engine):
        done.append("v8-cartons-mm")
    if _migrate_orders(engine):
        done.append("v8-order-idem")
    return done
