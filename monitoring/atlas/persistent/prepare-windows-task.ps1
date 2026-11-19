# Preparation only: writes XML. Does not register/start a task or change WSL.
param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\wsl.exe" -Argument '-d Ubuntu-22.04 -- sleep infinity'
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$definition = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Keep only Ubuntu-22.04 running for the optional localhost ATLAS monitoring stack; no rover operations.'
$xml = $definition | Export-ScheduledTask
[System.IO.File]::WriteAllText([System.IO.Path]::GetFullPath($OutputPath), $xml, [System.Text.Encoding]::Unicode)
Write-Output "Prepared only: $OutputPath. No task registered or started."
