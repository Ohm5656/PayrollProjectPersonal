# PyInstaller onedir candidate: never bundles reference_data or test_workspace.
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files('app', includes=['ui/checkmark.svg'])
a = Analysis(['app/main.py'], datas=datas, hiddenimports=['win32timezone'],)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, name='NTP Payroll Assistant - Test Candidate', console=False)
COLLECT(exe, a.binaries, a.zipfiles, a.datas, name='NTP Payroll Assistant - Test Candidate')
