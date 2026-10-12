from pathlib import Path

from app.db.repositories import Repository
from app.domain import decimal_value, utc_now


def import_history(repo: Repository, evidence: dict, reference_root: Path, *, year=2026):
    """Import exact payroll names and observations, not approved business rules."""
    count = 0
    for file in evidence['files']:
        if file['kind'] != 'payroll' or not file.get('payroll') or file['payroll']['template_issues']:
            continue
        path = str((reference_root / file['file']).resolve())
        already = repo.db.query('SELECT hash FROM processed_files WHERE path=?', (path,))
        if already and already[0]['hash'] == file['sha256']:
            continue
        for employee in file['payroll']['employees']:
            eid = repo.create_employee(employee['name'], actor='historical exact name')
            # Only the complete payroll identity is imported. Attendance aliases
            # and contradictory sheet labels are never merged by this operation.
            if not repo.db.query('SELECT id FROM employee_aliases WHERE employee_id=? AND source=? AND alias_norm=?',
                                 (eid, 'payroll_full', employee['normalized_name'])):
                repo.confirm_alias(eid, employee['name'], 'payroll_full', actor='historical exact name', reason='Exact full payroll name')
            with repo.db.transaction() as con:
                for key, item in employee['fields'].items():
                    if item.get('present', True):
                        value = decimal_value(item['value']) if item['value'] is not None else None
                        con.execute('INSERT INTO payroll_observations VALUES (?,?,?,?,?,?,?,?) '
                                    'ON CONFLICT(employee_id,year,month,field_key) DO UPDATE SET value=excluded.value,'
                                    'formula=excluded.formula,source_path=excluded.source_path,source_hash=excluded.source_hash',
                                    (eid, year, file['month'], key, str(value) if value is not None else None,
                                     item.get('formula'), path, file['sha256']))
        with repo.db.transaction() as con:
            con.execute('INSERT INTO processed_files VALUES (?,?,?,?) ON CONFLICT(path) DO UPDATE SET '
                        'modified_time=excluded.modified_time,hash=excluded.hash,processed_at=excluded.processed_at',
                        (path, 0, file['sha256'], utc_now()))
            repo.audit(con, 'HISTORY_IMPORTED', year=year, month=file['month'], new={'source_hash': file['sha256']}, actor='system')
        count += 1
    return count
