"""Development safety boundary and immutable source baseline checks."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sys

from app.excel.workbook_source import discover_workbooks, file_hash

_FROZEN_CANDIDATE = bool(getattr(sys, 'frozen', False))


class SafetyError(RuntimeError):
    pass


def frozen_candidate_test_root(*, local_app_data=None) -> Path:
    """Return the one fixed writable root for a frozen QA-only candidate."""
    value = local_app_data if local_app_data is not None else os.environ.get('LOCALAPPDATA')
    if not value:
        raise SafetyError('Frozen QA candidate requires the Windows LOCALAPPDATA directory')
    local = Path(value)
    if not local.is_absolute():
        raise SafetyError('LOCALAPPDATA must be an absolute path')
    local = local.resolve()
    state = local / 'NTP Payroll Assistant Test Candidate' / 'State'
    resolved = state.resolve()
    if resolved != local and local not in resolved.parents:
        raise SafetyError('Frozen QA candidate state must remain under LOCALAPPDATA')
    return state / 'test_workspace'


# Frozen code and resources still resolve from the onedir EXE.  Its mutable
# synthetic state is deliberately elsewhere so upgrades/uninstall cannot
# silently remove it. Source development behavior remains unchanged.
ROOT = Path(sys.executable).resolve().parent if _FROZEN_CANDIDATE else Path(__file__).resolve().parents[1]
REFERENCE_ROOT = ROOT / 'reference_data'
TEST_ROOT = frozen_candidate_test_root() if _FROZEN_CANDIDATE else ROOT / 'test_workspace'
MASTER_TEMPLATE_RELATIVE = 'template/ฟอร์มเปล่ารายเดือน.xlsx'
EXPECTED_REFERENCE_WORKBOOKS = 19


def development_target(path: Path, *, root: Path = TEST_ROOT) -> Path:
    target = Path(path).resolve()
    root = Path(root).resolve()
    reference = REFERENCE_ROOT.resolve()
    if root == reference or reference in root.parents:
        raise SafetyError('reference_data is read-only')
    if root != TEST_ROOT.resolve() and TEST_ROOT.resolve() not in root.parents:
        raise SafetyError('Development write roots must be inside test_workspace')
    if _FROZEN_CANDIDATE:
        candidate_root = frozen_candidate_test_root().resolve()
        if root != candidate_root and candidate_root not in root.parents:
            raise SafetyError('Frozen QA writes must remain inside the candidate state root')
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
    if len(current) != EXPECTED_REFERENCE_WORKBOOKS:
        raise SafetyError(f'Expected {EXPECTED_REFERENCE_WORKBOOKS} source workbooks, found {len(current)}')
    path = Path(path)
    if path.exists():
        baseline = json.loads(path.read_text(encoding='utf-8'))
        # The user deliberately introduced the one immutable monthly master after
        # the 18-file historical baseline was recorded.  Upgrade only if every
        # old source remains byte-for-byte and timestamp-for-timestamp intact,
        # and the sole addition is the declared master template.
        previous = baseline.get('files', {})
        additions = set(current) - set(previous)
        if (additions == {MASTER_TEMPLATE_RELATIVE}
                and all(current.get(name) == evidence for name, evidence in previous.items())):
            baseline = {
                **baseline,
                'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
                'files': current,
                'baseline_note': 'Added declared read-only monthly master after verifying all original 18 sources unchanged.',
            }
            path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            return baseline
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
