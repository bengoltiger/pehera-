# Run the PEHRA backend so a phone on the same Wi-Fi can reach it (for APK demos).
# Usage:  powershell -ExecutionPolicy Bypass -File scripts/run_lan.ps1
#
#   * binds 0.0.0.0 (phones CANNOT reach a 127.0.0.1-only server)
#   * opens a firewall rule for TCP 8799 on the Private profile (best effort,
#     needs an elevated shell; otherwise click "Allow" on the Windows prompt)
#   * prints the laptop's LAN IP so you can type it in the app's Settings

$ErrorActionPreference = "Stop"

$RuleName = "PEHRA-Demo-8799"
$existing = netsh advfirewall firewall show rule name=$RuleName 2>$null
if ($LASTEXITCODE -ne 0 -or $existing -match "No rules match") {
    try {
        netsh advfirewall firewall add rule name=$RuleName dir=in action=allow protocol=TCP localport=8799 profile=private | Out-Null
        Write-Host "[fw] firewall rule '$RuleName' added (Private profile)."
    } catch {
        Write-Host "[fw] could not add firewall rule - run as Administrator, or allow Python when Windows prompts."
    }
} else {
    Write-Host "[fw] firewall rule '$RuleName' already present."
}

$ips = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notmatch "^(127\.|169\.254\.)" -and $_.PrefixOrigin -ne "WellKnown" } |
        Select-Object -ExpandProperty IPAddress)
if ($ips) { Write-Host "[lan] phone should connect to:  http://$($ips[0]):8799" }

$py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "[server] starting uvicorn on 0.0.0.0:8799 ..."
& $py -m uvicorn app.main:app --host 0.0.0.0 --port 8799