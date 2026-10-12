param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryUrl,
    [string]$Destination = (Join-Path $HOME "wedding-studio-desk")
)

$ErrorActionPreference = "Stop"
$source = Split-Path -Parent $MyInvocation.MyCommand.Path
$files = @(
    "app.py", "Dockerfile", "README.md", "RECORDING_SCRIPT.md",
    "docker-compose.yml", "render.yaml", "render.standalone.yaml",
    "requirements.txt", "test_app.py", ".gitignore"
)

if (Test-Path $Destination) {
    throw "Destination already exists: $Destination. Choose another path or remove it yourself."
}
New-Item -ItemType Directory -Path $Destination | Out-Null
foreach ($file in $files) { Copy-Item (Join-Path $source $file) (Join-Path $Destination $file) }
New-Item -ItemType Directory -Path (Join-Path $Destination "data") | Out-Null
Copy-Item (Join-Path $source "data\studio_bookings.csv") (Join-Path $Destination "data\studio_bookings.csv")

Push-Location $Destination
try {
    git init
    git add .
    git commit -m "Initial wedding studio desk assignment"
    git branch -M main
    git remote add origin $RepositoryUrl
    git push -u origin main
} finally {
    Pop-Location
}
Write-Host "Published standalone assignment from $Destination"
