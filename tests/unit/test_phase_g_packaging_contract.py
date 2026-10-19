from pathlib import Path


def test_phase_g_packaging_excludes_reference_data_and_disables_auto_run():
    root = Path(__file__).resolve().parents[2]
    spec = (root / 'packaging' / 'ntp_payroll.spec').read_text(encoding='utf-8')
    iss = (root / 'packaging' / 'installer' / 'ntp_payroll.iss').read_text(encoding='utf-8')
    assert 'reference_data' not in spec and 'test_workspace' not in spec
    assert 'PrivilegesRequired=lowest' in iss
    assert 'automatic launch, monitoring or startup registration' in iss


def test_phase_g_frozen_candidate_forces_synthetic_qa_mode():
    root = Path(__file__).resolve().parents[2]
    entry = (root / 'app' / 'packaged_qa.py').read_text(encoding='utf-8')
    main = (root / 'app' / 'main.py').read_text(encoding='utf-8')
    safety = (root / 'app' / 'safety.py').read_text(encoding='utf-8')
    assert "sys.argv.append('--qa-ui')" in entry
    assert "requires --qa-ui and has no normal-payroll mode" in main
    assert "Path(sys.executable).resolve().parent" in safety
