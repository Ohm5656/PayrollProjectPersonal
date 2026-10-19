"""Explicit isolated recovery helpers; never restore over a current target."""
from pathlib import Path
import sqlite3

from app.excel.workbook_source import file_hash
from app.safety import SafetyError, development_target


def restore_workbook_copy(backup, destination, expected_hash):
    backup, destination = Path(backup), development_target(destination)
    if not backup.is_file() or file_hash(backup) != expected_hash:
        raise SafetyError('Backup is missing or its hash does not match recorded evidence')
    if destination.exists():
        raise SafetyError('Recovery destination already exists; explicit separate destination required')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(backup.read_bytes())
    if file_hash(destination) != expected_hash:
        raise SafetyError('Restored workbook hash mismatch')
    return destination


def sqlite_snapshot(source, destination):
    source, destination = Path(source), development_target(destination)
    if not source.is_file() or destination.exists():
        raise SafetyError('Snapshot source is missing or destination is not a fresh isolated file')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as read, sqlite3.connect(destination) as write:
        read.backup(write)
    with sqlite3.connect(f'file:{destination.resolve().as_posix()}?mode=ro', uri=True) as check:
        if check.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SafetyError('SQLite snapshot integrity check failed')
    return destination
