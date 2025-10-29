Param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Resolve project root relative to this script
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# Ensure Python can import from project root
$env:PYTHONPATH = "$Root" + ($(if ($env:PYTHONPATH) { ";$env:PYTHONPATH" } else { "" }))

Write-Host "[start.ps1] Installing Python dependencies..."
if (Test-Path "$Root\requirements.txt") {
  python -m pip install --disable-pip-version-check -r "$Root\requirements.txt"
}

# Bind Lavalink to port and host from environment or defaults
if (-not $env:SERVER_PORT) { $env:SERVER_PORT = '2333' }
$env:PORT = $env:SERVER_PORT
if (-not $env:LAVALINK_HOST) { $env:LAVALINK_HOST = '127.0.0.1' }
if (-not $env:LAVALINK_PORT) { $env:LAVALINK_PORT = $env:PORT }
if (-not $env:LAVALINK_PASSWORD) { $env:LAVALINK_PASSWORD = 'youshallnotpass' }

# Detect Lavalink jar in ./lavalink or repo root
$JarPath = ''
if (Test-Path "$Root\lavalink\Lavalink.jar") { $JarPath = "$Root\lavalink\Lavalink.jar" }
elseif (Test-Path "$Root\Lavalink.jar") { $JarPath = "$Root\Lavalink.jar" }

$StartedLocalLavalink = $false
if ($JarPath -ne '') {
  if (Get-Command java -ErrorAction SilentlyContinue) {
    $LogDir = Join-Path $Root 'lavalink\logs'
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
    $LogFile = Join-Path $LogDir 'panel-start.log'
    Write-Host "[start.ps1] Starting Lavalink on $($env:LAVALINK_HOST):$($env:PORT) using $JarPath..."
    $javaArgs = @()
    if ($env:JAVA_FLAGS) { $javaArgs += $env:JAVA_FLAGS.Split(' ') }
    $javaArgs += '-jar'
    $javaArgs += $JarPath
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = 'java'
    $startInfo.Arguments = [string]::Join(' ', $javaArgs)
    $startInfo.WorkingDirectory = $Root
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    # Inherit env vars for Lavalink
    $startInfo.Environment['LAVALINK_HOST'] = $env:LAVALINK_HOST
    $startInfo.Environment['LAVALINK_PORT'] = $env:LAVALINK_PORT
    $startInfo.Environment['LAVALINK_PASSWORD'] = $env:LAVALINK_PASSWORD
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $null = $process.Start()
    $stdOutTask = $process.StandardOutput.ReadToEndAsync()
    $stdErrTask = $process.StandardError.ReadToEndAsync()
    $StartedLocalLavalink = $true
  }
  else {
    Write-Warning "[start.ps1] Java not found in PATH; skipping local Lavalink start."
  }
}
else {
  Write-Warning "[start.ps1] Lavalink.jar not found in ./lavalink or repo root; skipping local Lavalink start."
}

# Optional readiness check
if ($StartedLocalLavalink) {
  Write-Host "[start.ps1] Waiting for Lavalink to become ready..."
  $ready = $false
  for ($i = 1; $i -le 20; $i++) {
    try {
      $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$($env:LAVALINK_PORT)/v4/info" -UseBasicParsing -TimeoutSec 2
      if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) { $ready = $true; break }
    }
    catch { Start-Sleep -Milliseconds 500 }
  }
  if ($ready) { Write-Host "[start.ps1] Lavalink is up." }
  else { Write-Warning "[start.ps1] Lavalink readiness not confirmed; proceeding to start bot." }
}

Write-Host "[start.ps1] Starting Discord bot..."
# Use the resilient wrapper that fixes sys.path
python "$Root\bot.py"
