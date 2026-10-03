# CEO-16 야간 단독 실행 (10/3 CEO 결정). 22:00 까지 기다렸다가, Ollama 가 유휴(truenjoy 21시 발행 끝)인지 확인하고
# 색인 -> 질의를 이어 돌린다. 06:30 이면 heavy 가드가 멈추고, 끝나거나 멈추면 모델을 내린다. 로그는 night.log.
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:MLPC_DEADLINE = '06:30'
$env:MLPC_MIN_FREE_START = '2.3'  # 10/3 22:12 CEO 허용(다른 창 유휴)
$log = Join-Path $PSScriptRoot 'night.log'
function Say($m) { "$(Get-Date -Format 'MM-dd HH:mm') $m" | Out-File -Append -Encoding utf8 $log }
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$docs = 'docs/2019599.txt','docs/2019600.txt','docs/2019625.txt','docs/2019626.txt','docs/2019873.txt','docs/2019611.txt','docs/2019612.txt'

Say 'waiting for 22:00'
while ((Get-Date).Hour -lt 22 -and (Get-Date).Hour -ge 7) { Start-Sleep 60 }
$until = (Get-Date).AddMinutes(60)
while ((& ollama ps | Select-Object -Skip 1 | Where-Object { $_.Trim() }).Count -gt 0) {
  if ((Get-Date) -gt $until) { Say 'ollama still busy after 60 min — abort'; exit 1 }
  Say 'ollama busy (truenjoy?) — waiting'; Start-Sleep 120
}
Say 'ollama idle — start index'
& $py index.py rag_storage @docs *>> (Join-Path $PSScriptRoot 'night-index.log')
$done = Select-String -Path (Join-Path $PSScriptRoot 'night-index.log') -Pattern '^(DONE|all processed)' -Quiet
Say "index finished: done=$done"
if ($done) {
  Say 'start query'
  & $py query.py *>> (Join-Path $PSScriptRoot 'night-query.log')
  $n = (Get-Content (Join-Path $PSScriptRoot 'answers.jsonl') -ErrorAction SilentlyContinue | Measure-Object).Count
  Say "query finished: answers=$n/120"
}
& ollama stop qwen3:8b 2>$null; & ollama stop bge-m3 2>$null
Say 'models unloaded — end'
