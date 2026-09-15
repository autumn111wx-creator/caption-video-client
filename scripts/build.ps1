$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install requirements-lock.txt first.' }
    foreach ($name in @('ffmpeg.exe', 'ffprobe.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "bin\$name"))) { throw "Missing bin\$name" }
    }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $buildRoot = Join-Path $projectRoot "build\$stamp"
    $distRoot = Join-Path $projectRoot "dist\$stamp"
    & $python -m PyInstaller --noconfirm --distpath $distRoot --workpath $buildRoot CaptionVideoClient.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
    $package = Join-Path $distRoot '黑底字幕视频工具'
    foreach ($name in @('bin','音色配置','发音词典.tsv','客户端配置说明.txt','开源项目说明.txt','licenses')) {
        Copy-Item -LiteralPath (Join-Path $projectRoot $name) -Destination $package -Recurse
    }
    $archive = Join-Path $distRoot 'caption-video-client-windows-x64.zip'
    Compress-Archive -LiteralPath $package -DestinationPath $archive -CompressionLevel Optimal
    Get-FileHash -Algorithm SHA256 -LiteralPath $archive
    Write-Output "Built: $archive"
} finally { Pop-Location }
