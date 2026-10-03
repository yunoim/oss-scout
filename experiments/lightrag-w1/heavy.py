"""MLPC 무거운 작업 규칙(wiki hq/README.md, 2026-10-03) 가드.
- 잠금 파일 C:/Users/quite/.mlpc-heavy.lock — 다른 창이 2시간 안에 잡았으면 시작하지 않는다
- 남은 RAM 3GB 미만이면 시작하지 않는다 · 20:30~21:30 은 Ollama 금지
매 문서/문항 전에 check() 를 다시 불러 중간에도 멈춘다. 진행은 progress.json 에 남아 다음 실행이 이어 간다."""
from __future__ import annotations

import ctypes
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

LOCK = Path("C:/Users/quite/.mlpc-heavy.lock")
OWNER = "github 스카우터"
MIN_FREE_GB = float(os.environ.get("MLPC_MIN_FREE_START", "3.0"))  # 시작 조건(wiki hq/README.md). 10/3 22:12 CEO: 다른 창이 쉬면 2.4GB 도 허용
MIN_FREE_RUN_GB = 2.0  # 실행 중 조건(10/3 CEO: 실행 중 여유 2GB 이상 유지)
MAX_LLAMA_GB = 3.0     # qwen3:8b·8192 작업 중 정상치 2.07GB(10/3 실측, Ollama 가 Windows+CUDA 에서 mmap 을 이미 끈다). 멈춤 때는 5.3GB


class Stop(Exception):
    pass


def free_gb() -> float:
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1024**3


def check(starting: bool = False) -> None:
    now = datetime.now()
    if (now.hour, now.minute) >= (20, 30) and (now.hour, now.minute) < (21, 30):
        raise Stop("20:30~21:30 Ollama 금지 시간")
    dl = os.environ.get("MLPC_DEADLINE")  # 야간 실행 정지 시각 "HH:MM" (10/3 CEO: 늦어도 06:30)
    if dl:
        h, m = map(int, dl.split(":"))
        if (h, m) <= (now.hour, now.minute) < (21, 0):
            raise Stop(f"야간 실행 마감 {dl}")
    gb = free_gb()
    need = MIN_FREE_GB if starting else MIN_FREE_RUN_GB
    if gb < need:
        raise Stop(f"남은 RAM {gb:.2f}GB < {need}GB")
    # 10/3 CEO 지시: 모델이 VRAM 에 다 안 올라가 시스템 RAM 을 먹으면 이 PC 에서는 멈춘다
    ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    for line in ps.splitlines()[1:]:
        if line.strip() and "100% GPU" not in line:
            raise Stop(f"모델이 GPU 에 다 안 올라감: {line.split()[0]} — {' '.join(line.split()[3:6])}")
    ws = subprocess.run(["powershell", "-NoProfile", "-Command",
                         "(Get-Process llama-server -ErrorAction SilentlyContinue | Measure-Object WorkingSet64 -Sum).Sum/1GB"],
                        capture_output=True, text=True).stdout.strip()
    if ws and float(ws) > MAX_LLAMA_GB:
        raise Stop(f"llama-server 시스템 RAM {float(ws):.2f}GB > {MAX_LLAMA_GB}GB")


def acquire(task: str) -> None:
    if LOCK.exists():
        age = time.time() - LOCK.stat().st_mtime
        text = LOCK.read_text(encoding="utf-8", errors="replace").strip()
        if age < 2 * 3600 and not text.startswith(OWNER):
            raise Stop(f"다른 창이 작업 중: {text}")
    check(starting=True)
    LOCK.write_text(f"{OWNER} · {task} · {datetime.now():%Y-%m-%d %H:%M}\n", encoding="utf-8")


def release() -> None:
    if LOCK.exists() and LOCK.read_text(encoding="utf-8", errors="replace").startswith(OWNER):
        LOCK.unlink()
