$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Version = if ($env:CINERECORD_VERSION) { $env:CINERECORD_VERSION } else { "0.1.0" }
$DistDir = Join-Path $RootDir "dist-rust"
$PackageName = "CineRecord-Windows-x64"
$PackageDir = Join-Path $DistDir $PackageName
$ArchivePath = Join-Path $DistDir "$PackageName.zip"
$StandalonePath = Join-Path $DistDir "$PackageName.exe"
$ChecksumPath = Join-Path $DistDir "$PackageName.sha256"

Remove-Item $PackageDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item $PackageDir -ItemType Directory -Force | Out-Null

Push-Location $RootDir
try {
    cargo build --locked --release -p cinerecord-server
} finally {
    Pop-Location
}

$BuiltBinary = Join-Path $RootDir "target\release\cinerecord-server.exe"
$PackagedBinary = Join-Path $PackageDir "CineRecord.exe"
Copy-Item $BuiltBinary $PackagedBinary
Copy-Item $BuiltBinary $StandalonePath -Force

@"
CineRecord $Version

Double-click CineRecord.exe. The app runs in the background and opens
http://127.0.0.1:18000 in your default browser.
User data is stored under %APPDATA%\CineRecord.
"@ | Set-Content (Join-Path $PackageDir "README.txt") -Encoding UTF8

Remove-Item $ArchivePath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ArchivePath

$ChecksumLines = @(
    "$((Get-FileHash $StandalonePath -Algorithm SHA256).Hash.ToLower())  $([IO.Path]::GetFileName($StandalonePath))"
    "$((Get-FileHash $ArchivePath -Algorithm SHA256).Hash.ToLower())  $([IO.Path]::GetFileName($ArchivePath))"
)
$ChecksumLines | Set-Content $ChecksumPath -Encoding Ascii

Write-Host "PACKAGE_DIR=$PackageDir"
Write-Host "STANDALONE_PATH=$StandalonePath"
Write-Host "ARCHIVE_PATH=$ArchivePath"
Write-Host "CHECKSUM_PATH=$ChecksumPath"
