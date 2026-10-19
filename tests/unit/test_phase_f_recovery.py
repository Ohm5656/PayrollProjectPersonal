import pytest

from app.db.database import Database
from app.excel.workbook_source import file_hash
from app.safety import SafetyError
from app.services.recovery_rehearsal import restore_workbook_copy, sqlite_snapshot


def test_phase_f_restore_requires_fresh_destination_and_matching_hash(workbook_workspace):
    backup = workbook_workspace / 'backup.xlsx'; backup.write_bytes(b'synthetic')
    digest = file_hash(backup)
    restored = restore_workbook_copy(backup, workbook_workspace / 'restore' / 'copy.xlsx', digest)
    assert file_hash(restored) == digest
    with pytest.raises(SafetyError): restore_workbook_copy(backup, restored, digest)
    with pytest.raises(SafetyError): restore_workbook_copy(backup, workbook_workspace / 'other.xlsx', '0' * 64)


def test_phase_f_sqlite_backup_api_produces_integrity_checked_disposable_snapshot(workbook_workspace):
    source = Database(workbook_workspace / 'source.db').path
    restored = sqlite_snapshot(source, workbook_workspace / 'restore.db')
    assert restored.is_file()
