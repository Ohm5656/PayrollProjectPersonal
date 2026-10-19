from pathlib import Path
import json

import pytest

from app.packaging_safety import (
    CANDIDATE_EXE,
    CANDIDATE_NAME,
    PackagingSafetyError,
    stage_distribution,
    validate_payload,
)
from app.safety import SafetyError, frozen_candidate_test_root


def _distribution(root: Path) -> Path:
    dist = root / 'dist' / CANDIDATE_NAME
    (dist / '_internal').mkdir(parents=True)
    (dist / CANDIDATE_EXE).write_bytes(b'candidate exe')
    (dist / '_internal' / 'Qt6Svg.dll').write_bytes(b'qt asset')
    return dist


def test_installer_stage_uses_allowlist_and_manifest_excludes_runtime_state(tmp_path):
    source = _distribution(tmp_path)
    (source / 'test_workspace' / 'qa_sessions').mkdir(parents=True)
    (source / 'test_workspace' / 'qa_sessions' / 'employee.db').write_text('private', encoding='utf-8')
    (source / 'runtime.log').write_text('runtime', encoding='utf-8')

    stage, manifest, files = stage_distribution(tmp_path)

    assert {value.name for value in stage.iterdir()} == {CANDIDATE_EXE, '_internal'}
    assert all('test_workspace' not in value.parts for value in files)
    evidence = json.loads(manifest.read_text(encoding='utf-8'))
    assert {entry['path'] for entry in evidence['files']} == {
        CANDIDATE_EXE, '_internal/Qt6Svg.dll'
    }
    assert validate_payload(stage) == files


def test_installer_stage_rejects_sensitive_workbook_in_allowlisted_payload(tmp_path):
    source = _distribution(tmp_path)
    (source / '_internal' / 'payroll.xlsx').write_bytes(b'not a workbook')

    with pytest.raises(PackagingSafetyError, match='Prohibited payload file'):
        stage_distribution(tmp_path)


def test_installer_staging_rejects_unexpected_top_level_data(tmp_path):
    stage = tmp_path / 'stage'
    stage.mkdir()
    (stage / CANDIDATE_EXE).write_bytes(b'candidate exe')
    (stage / '_internal').mkdir()
    (stage / 'test_workspace').mkdir()

    with pytest.raises(PackagingSafetyError, match='only'):
        validate_payload(stage)


def test_frozen_candidate_root_is_fixed_under_local_appdata(tmp_path):
    root = frozen_candidate_test_root(local_app_data=tmp_path)

    assert root == tmp_path.resolve() / 'NTP Payroll Assistant Test Candidate' / 'State' / 'test_workspace'
    with pytest.raises(SafetyError):
        frozen_candidate_test_root(local_app_data='relative-path')
