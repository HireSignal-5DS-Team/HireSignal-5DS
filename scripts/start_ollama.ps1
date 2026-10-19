# Start / stop our own Ollama server for the Reader's vision path (T10), with its model store inside this project:
# OLLAMA_MODELS = models\ollama (git-ignored, CLAUDE.md rule 7b), OLLAMA_HOST = 127.0.0.1:11434. Both are set for this
# process only; no global setting is changed. The Ollama desktop app must not be running (it holds port 11434).
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start_ollama.ps1          # start (background), wait until it answers
#   powershell -ExecutionPolicy Bypass -File scripts\start_ollama.ps1 -Stop    # stop the server started by this script
#   powershell -ExecutionPolicy Bypass -File scripts\start_ollama.ps1 list      # other words = an Ollama CLI command
#   (pull models through the API: curl http://127.0.0.1:11434/api/pull -d '{"model": "qwen2.5vl:3b", "stream": false}')
param([switch]$Stop, [Parameter(ValueFromRemainingArguments = $true)][string[]]$Cli)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$exe = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $exe) { $exe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe" }
$pidFile = Join-Path $root "tools\ollama.pid"
$log = Join-Path $root "tools\ollama.log"
$port = "11434"
$env:OLLAMA_MODELS = Join-Path $root "models\ollama"
$env:OLLAMA_HOST = "127.0.0.1:$port"

if ($Cli) { & $exe @Cli; exit $LASTEXITCODE }

if ($Stop) {
    if (-not (Test-Path $pidFile)) { "No PID file; Ollama not started by this script."; exit 0 }
    $p = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue
    if ($p -and $p.Path -eq $exe) { Stop-Process -Id $p.Id -Confirm:$false; "Stopped Ollama (pid $($p.Id))." }
    else { "PID file is stale; nothing to stop." }
    Remove-Item $pidFile -Confirm:$false
    exit 0
}

if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $port is already in use (quit the Ollama desktop app first)"
}
New-Item -ItemType Directory -Force $env:OLLAMA_MODELS | Out-Null
$p = Start-Process -FilePath $exe -ArgumentList @("serve") -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err"
Set-Content -Path $pidFile -Value $p.Id -Encoding ascii
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    if ($p.HasExited) { throw "ollama exited (code $($p.ExitCode)); see $log.err" }
    try { Invoke-RestMethod "http://127.0.0.1:$port/api/version" -TimeoutSec 2 | Out-Null; "Ollama ready on port $port (pid $($p.Id), models in $env:OLLAMA_MODELS)"; exit 0 } catch {}
}
throw "Ollama did not answer within 60 s; see $log.err"
