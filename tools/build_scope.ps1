# Build dist\NobodyHomeScope.exe: the live scope as one file, no Python needed.
#   powershell -ExecutionPolicy Bypass -File tools\build_scope.ps1
# Needs: py -m pip install --user pyinstaller numpy matplotlib

$root = Split-Path -Parent $PSScriptRoot
$work = Join-Path $env:TEMP "nobody_home_pyi"   # keep build junk out of Dropbox

py -m PyInstaller --noconfirm --onefile --name NobodyHomeScope `
  --paths "$root\tools" `
  --add-data "$root\firmware\include\config.h;." `
  --workpath "$work\build" --specpath "$work" --distpath "$root\dist" `
  "$root\tools\scope.py"
