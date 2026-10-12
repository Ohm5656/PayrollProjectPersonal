from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4

from app.db.migrations import MIGRATIONS
from app.safety import development_target


class Database:
    """Short-lived connections allow worker threads without sharing a connection."""
    def __init__(self, path: Path):
        self.path = development_target(path)
        self._local = threading.local()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connection(self):
        active = getattr(self._local, 'connection', None)
        if active is not None:
            yield active
            return
        con = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA busy_timeout=15000')
        try:
            yield con
        finally:
            con.close()

    @contextmanager
    def transaction(self):
        active = getattr(self._local, 'connection', None)
        if active is not None:
            savepoint = 'sp_' + uuid4().hex
            active.execute('SAVEPOINT ' + savepoint)
            try:
                yield active
                active.execute('RELEASE SAVEPOINT ' + savepoint)
            except BaseException:
                active.execute('ROLLBACK TO SAVEPOINT ' + savepoint)
                active.execute('RELEASE SAVEPOINT ' + savepoint)
                raise
            return
        with self.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            self._local.connection = con
            try:
                yield con
                con.commit()
            except BaseException:
                con.rollback()
                raise
            finally:
                del self._local.connection

    def migrate(self):
        with self.connection() as con:
            con.execute('PRAGMA journal_mode=WAL')
        with self.transaction() as con:
            con.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            current = {r[0] for r in con.execute('SELECT version FROM schema_migrations')}
            known = {version for version, _ in MIGRATIONS}
            if current - known:
                raise RuntimeError('Database schema is newer than this application')
            for version, statements in MIGRATIONS:
                if version not in current:
                    for sql in statements:
                        con.execute(sql)
                    con.execute("INSERT INTO schema_migrations VALUES (?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (version,))

    def query(self, sql, args=()):
        with self.connection() as con:
            return [dict(r) for r in con.execute(sql, args)]

    @contextmanager
    def read_snapshot(self):
        """One consistent read transaction for an entire draft calculation."""
        active = getattr(self._local, 'connection', None)
        if active is not None:
            yield active
            return
        with self.connection() as con:
            con.execute('PRAGMA query_only=ON')
            con.execute('BEGIN')
            self._local.connection = con
            try:
                yield con
            finally:
                con.rollback()
                del self._local.connection
