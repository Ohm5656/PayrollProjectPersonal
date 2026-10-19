from pathlib import Path

import pytest

from app.safety import SafetyError, TEST_ROOT, development_target


def test_phase_f_deployment_readiness_never_changes_test_workspace_boundary(tmp_path):
    outside = tmp_path / "outside.xlsx"
    with pytest.raises(SafetyError):
        development_target(outside)
    with pytest.raises(SafetyError):
        development_target(TEST_ROOT)


def test_phase_f_path_traversal_and_reference_named_targets_fail_closed():
    escaped = TEST_ROOT / "uat_synthetic" / ".." / ".." / "outside.xlsx"
    with pytest.raises(SafetyError):
        development_target(escaped)
