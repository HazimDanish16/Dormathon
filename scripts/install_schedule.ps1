param(
    [ValidateSet('Poll', 'Daily')][string]$Task = 'Poll',
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Run uv sync first.' }
if ($Task -eq 'Daily') {
    & $pythonPath (Join-Path $PSScriptRoot 'validate_handoff.py')
    if ($LASTEXITCODE -ne 0) { throw 'Daily scheduling requires a valid real handoff.' }
    & $pythonPath -c 'from mymarket.config import Settings; s=Settings.from_env(); assert s.data_mode == "real" and s.environment().get("MYMARKET_PRICE_REFRESH_COMMAND"), "Configure a real price-refresh command first"'
    if ($LASTEXITCODE -ne 0) { throw 'Real data mode and a price refresh command are required.' }
    $scriptPath = Join-Path $PSScriptRoot 'daily_refresh.py'
    $trigger = New-ScheduledTaskTrigger -Daily -At '14:00'
} else {
    $scriptPath = Join-Path $PSScriptRoot 'poll_news.py'
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours 3)
}
$taskName = "MyMarket-$Task"
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$scriptPath`"" -WorkingDirectory $projectRoot
$taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -StartWhenAvailable
if ($Apply) {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $taskSettings -Description 'MyMarket news and price-awareness refresh' -Force | Out-Null
    Write-Output "Registered $taskName. Daily time uses this computer's local timezone; set it to Asia/Kuala_Lumpur."
} else {
    Write-Output "Preview: $taskName runs $scriptPath. Use -Apply to register it."
}
