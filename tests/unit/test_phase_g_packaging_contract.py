from pathlib import Path


def test_phase_g_packaging_excludes_reference_data_and_disables_auto_run():
    root = Path(__file__).resolve().parents[2]
    spec = (root / 'packaging' / 'ntp_payroll.spec').read_text(encoding='utf-8')
    iss = (root / 'packaging' / 'installer' / 'ntp_payroll.iss').read_text(encoding='utf-8')
    assert 'reference_data' not in spec and 'test_workspace' not in spec
    assert 'PrivilegesRequired=lowest' in iss
    assert 'automatic launch, monitoring or startup registration' in iss
    assert 'SourceDir must be a verified fresh installer-staging directory' in iss
    assert 'Parameters: "--qa-ui"' in iss
    assert 'DefaultDirName={localappdata}\\Programs\\NTP Payroll Assistant Test Candidate' in iss
    assert '[UninstallDelete]' not in iss


def test_phase_g_frozen_candidate_forces_synthetic_qa_mode():
    root = Path(__file__).resolve().parents[2]
    entry = (root / 'app' / 'packaged_qa.py').read_text(encoding='utf-8')
    main = (root / 'app' / 'main.py').read_text(encoding='utf-8')
    safety = (root / 'app' / 'safety.py').read_text(encoding='utf-8')
    assert "sys.argv.append('--qa-ui')" in entry
    assert "requires --qa-ui and has no normal-payroll mode" in main
    assert "Path(sys.executable).resolve().parent" in safety
    assert "NTP Payroll Assistant Test Candidate' / 'State'" in safety


def test_phase_g6_build_uses_fresh_output_and_verified_staging_only():
    root = Path(__file__).resolve().parents[2]
    build = (root / 'packaging' / 'build_exe.ps1').read_text(encoding='utf-8')
    staging = (root / 'packaging' / 'prepare_installer_staging.ps1').read_text(encoding='utf-8')
    installer = (root / 'packaging' / 'build_installer.ps1').read_text(encoding='utf-8')
    assert "[guid]::NewGuid()" in build
    assert 'Refusing to overwrite an existing EXE output directory' in build
    assert '[Parameter(Mandatory=$true)][string]$DistributionPath' in staging
    assert 'prepare_installer_staging.ps1' in installer
    assert "Programs\\Inno Setup 6\\ISCC.exe" in installer
