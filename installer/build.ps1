# installer/build.ps1
# One-shot Windows build orchestrator: bump version -> PyInstaller -> Inno Setup -> portable zip.
#
# Usage (in PowerShell on Windows, repo root):
#     .\installer\build.ps1
#     .\installer\build.ps1 -SkipPyInstaller    # only re-run Inno + zip
#     .\installer\build.ps1 -SkipInno           # only re-run PyInstaller + zip
#     .\installer\build.ps1 -InnoSetupPath "D:\InnoSetup6\ISCC.exe"
#
# If installer\vendored\MVS_SDK_*.exe is present, it is bundled into the
# installer and silently invoked during install. If absent (e.g. CI), the
# installer is built without it and a warning is emitted.
#
# Prerequisites: see docs/build/RELEASE_WINDOWS.md §A (one-time environment setup).

[CmdletBinding()]
param(
    [switch]$SkipPyInstaller,
    [switch]$SkipInno,
    [string]$InnoSetupPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo

# --- 1. 校验构建 venv -----------------------------------------------------
$python = Join-Path $repo ".venv-build\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "构建 venv 不存在：$python`n请先按 docs/build/RELEASE_WINDOWS.md §A.5 创建 .venv-build。"
}

# --- 2. 同步版本号 -------------------------------------------------------
& $python "installer\bump_version.py"
if ($LASTEXITCODE -ne 0) { throw "bump_version 失败 ($LASTEXITCODE)" }
$version = (Get-Content "installer\version.json" | ConvertFrom-Json).version
Write-Host "[build] target version: $version" -ForegroundColor Cyan

# --- 3. 检测 MVS SDK exe (可选) ------------------------------------------
$vendored = Join-Path $repo "installer\vendored"
$mvsExe   = Get-ChildItem $vendored -Filter "MVS_SDK_*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($mvsExe) {
    Write-Host "[build] using MVS SDK: $($mvsExe.Name)" -ForegroundColor Cyan
} else {
    Write-Warning "未找到 installer\vendored\MVS_SDK_*.exe；安装器将不带 MVS SDK 静默安装。"
    Write-Warning "如果你打算给海康相机用户用，请按 RELEASE_WINDOWS.md §B.2 把 SDK exe 放到 vendored/ 后重跑。"
}

# --- 4. PyInstaller -------------------------------------------------------
if (-not $SkipPyInstaller) {
    Write-Host "[build] running PyInstaller..." -ForegroundColor Cyan
    # Override PyInstaller defaults so dist lands in build/dist/ — that's where
    # PsfScan.iss and the validation step below both look for it.
    & $python -m PyInstaller --noconfirm --clean `
        --distpath "build\dist" `
        --workpath "build\temp" `
        "installer\psf_scan.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败 ($LASTEXITCODE)" }
}

$dist = Join-Path $repo "build\dist\PsfScan"
if (-not (Test-Path (Join-Path $dist "PsfScan.exe"))) {
    throw "PyInstaller 产物缺失：$dist\PsfScan.exe"
}

# --- 5. Inno Setup --------------------------------------------------------
if (-not $SkipInno) {
    if (-not (Test-Path $InnoSetupPath)) {
        throw "ISCC.exe 不在：$InnoSetupPath；请装 Inno Setup 6 或用 -InnoSetupPath 指定。"
    }
    Write-Host "[build] running Inno Setup..." -ForegroundColor Cyan
    & $InnoSetupPath "installer\PsfScan.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno 编译失败 ($LASTEXITCODE)" }
}

# --- 6. Portable zip -----------------------------------------------------
$releaseDir = Join-Path $repo "release"
if (-not (Test-Path $releaseDir)) { New-Item -ItemType Directory -Path $releaseDir | Out-Null }
$zip = Join-Path $releaseDir "PsfScan-$version-portable.zip"
if (Test-Path $zip) { Remove-Item $zip }
Write-Host "[build] building portable zip..." -ForegroundColor Cyan
Compress-Archive -Path "$dist\*" -DestinationPath $zip -CompressionLevel Optimal

# --- 7. 报告 -------------------------------------------------------------
$exe = Join-Path $releaseDir "PsfScan-Setup-$version.exe"

Write-Host ""
if (Test-Path $exe) {
    $sz  = "{0:N1} MB" -f ((Get-Item $exe).Length / 1MB)
    $sha = (Get-FileHash $exe -Algorithm SHA256).Hash
    Write-Host "[OK] 安装包: $exe  ($sz)" -ForegroundColor Green
    Write-Host "[OK] SHA256: $sha"      -ForegroundColor Green
}
if (Test-Path $zip) {
    $zsz  = "{0:N1} MB" -f ((Get-Item $zip).Length / 1MB)
    $zsha = (Get-FileHash $zip -Algorithm SHA256).Hash
    Write-Host "[OK] 便携包: $zip  ($zsz)" -ForegroundColor Green
    Write-Host "[OK] SHA256: $zsha"        -ForegroundColor Green
}
if ($mvsExe) {
    Write-Host "[OK] 此包含 MVS SDK 静默安装。" -ForegroundColor Green
} else {
    Write-Host "[OK] 此包不含 MVS SDK；MVS 相机用户需自行安装。" -ForegroundColor Yellow
}
