# PyInstaller onedir candidate: excludes private source and runtime artefacts.
from pathlib import Path

root = Path(SPECPATH).parent
datas = [(str(root / 'app' / 'ui' / 'checkmark.svg'), 'app/ui')]
a = Analysis([str(root / 'app' / 'packaged_qa.py')], datas=datas, hiddenimports=['win32timezone'],)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, name='NTP Payroll Assistant - Test Candidate', console=False)
COLLECT(exe, a.binaries, a.zipfiles, a.datas, name='NTP Payroll Assistant - Test Candidate')
