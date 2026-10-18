from pathlib import Path
import subprocess


def test_startup_scripts_parse_without_installing_any_task():
    root = Path(__file__).resolve().parents[2]
    scripts = [root/'scripts/install_startup.ps1', root/'scripts/remove_startup.ps1', root/'Start NTP Payroll.ps1']
    for path in scripts:
        # PowerShell parser only; never dot-source or execute these scripts.
        command = "$errorsFound=$null; $tokensFound=$null; [System.Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$tokensFound, [ref]$errorsFound) | Out-Null; if ($errorsFound.Count) { $errorsFound | Out-String | Write-Output; exit 1 }"
        escaped = str(path).replace("'", "''")
        command = command.replace('$args[0]', "'" + escaped + "'")
        result = subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    text = scripts[0].read_text(encoding='utf-8')
    assert '-RunLevel Limited' in text and '-LogonType Interactive' in text
    assert "NTP Payroll Assistant" in text and '-X utf8 -m app.main --startup' in text
    assert 'Start-ScheduledTask' not in text
