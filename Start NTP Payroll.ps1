$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot
$localPython = Join-Path $project '.venv\Scripts\pythonw.exe'
if (Test-Path -LiteralPath $localPython) { $python = $localPython }
else { $python = (Get-Command pythonw.exe -ErrorAction Stop).Source }
# pythonw has no console. This is the user-requested interactive GUI process;
# SW_HIDE here hides its first Qt window while Qt believes it is already shown.
Start-Process -FilePath $python -ArgumentList @('-m', 'app.main') -WorkingDirectory $project -WindowStyle Normal
