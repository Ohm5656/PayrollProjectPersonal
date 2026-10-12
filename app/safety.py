"""Development safety boundary and immutable source baseline checks."""
from datetime import datetime, timezone
from pathlib import Path
import json

from app.excel.workbook_source import discover_workbooks, file_hash

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = ROOT / 'reference_data'
TEST_ROOT = ROOT / 'test_workspace'


class SafetyError(RuntimeError):
    pass


def development_target(path: Path, *, root: Path = TEST_ROOT) -> Path:
    target = Path(path).resolve()
    root = Path(root).resolve()
    reference = REFERENCE_ROOT.resolve()
    if root == reference or reference in root.parents:
        raise SafetyError('reference_data is read-only')
    if root != TEST_ROOT.resolve() and TEST_ROOT.resolve() not in root.parents:
        raise SafetyError('Development write roots must be inside test_workspace')
    if target == root or root not in target.parents or reference in target.parents:
        raise SafetyError('Development writes must use a file inside test_workspace')
    if target.is_file() and target.stat().st_nlink > 1:
        raise SafetyError('Development targets must be independent copies, not hard links')
    return target


def source_manifest():
    return {p.relative_to(REFERENCE_ROOT).as_posix():
            {'sha256': file_hash(p), 'modified_ns': p.stat().st_mtime_ns, 'size': p.stat().st_size}
            for p in discover_workbooks(REFERENCE_ROOT)}


def record_baseline(path: Path):
    current = source_manifest()
    if len(current) != 18:
        raise SafetyError(f'Expected 18 source workbooks, found {len(current)}')
    path = Path(path)
    if path.exists():
        baseline = json.loads(path.read_text(encoding='utf-8'))
        verify_baseline(baseline)
        return baseline
    baseline = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'files': current}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return baseline


def verify_baseline(baseline):
    current = source_manifest()
    if current != baseline['files']:
        raise SafetyError('CRITICAL FAILURE: source workbook inventory, hash or modification time changed')
    return current
