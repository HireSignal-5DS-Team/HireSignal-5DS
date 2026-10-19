# Run the n8n CLI from our portable Node with our data folder (.n8n/), e.g.
#   powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 import:workflow --input=n8n\hiresignal_v1.json
#   powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 publish:workflow --id=HsV1Main00000001
#   powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 export:workflow --id=HsV1Main00000001 --output=n8n\hiresignal_v1.json --pretty
# Nothing global is changed: PATH and N8N_* are set for this process only. See n8n/README.md.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$node = Join-Path $root "tools\node"
$n8n = Join-Path $root "tools\n8n\node_modules\n8n\bin\n8n"
$env:PATH = "$node;$env:PATH"
$env:N8N_USER_FOLDER = $root
$env:N8N_DIAGNOSTICS_ENABLED = "false"
$env:N8N_RESTRICT_FILE_ACCESS_TO = "$(Join-Path $root 'data\processed');$(Join-Path $root 'eval\logs');$(Join-Path $root 'eval\outbox')"  # as start_n8n.ps1
Set-Location $root
& (Join-Path $node "node.exe") $n8n @args
exit $LASTEXITCODE
