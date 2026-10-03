# 여유 RAM 감시 → 기준을 넘는 순간 night.ps1 -Now 로 색인 시작 (10/4 CEO 지시). 가벼운 루프: 1분마다 RAM·잠금만 본다.
param([double]$MinFree = 2.4, [string]$Until = '09:20', [string]$Deadline = '09:25')
Set-Location $PSScriptRoot
$log = Join-Path $PSScriptRoot 'watch.log'
function Say($m) { "$(Get-Date -Format 'MM-dd HH:mm') $m" | Out-File -Append -Encoding utf8 $log }
$end = [datetime]::ParseExact($Until, 'HH:mm', $null)
Say "watch start (>= $MinFree GB, until $Until)"
while ((Get-Date) -lt $end) {
  $free = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 2)
  if ($free -ge $MinFree -and -not (Test-Path 'C:/Users/quite/.mlpc-heavy.lock')) {
    Say "LAUNCH free=$free"
    Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','night.ps1','-Now','-MinFree',"$MinFree",'-Deadline',$Deadline -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
    exit 0
  }
  Start-Sleep 60
}
Say "NO LAUNCH by $Until (last free=$free)"
