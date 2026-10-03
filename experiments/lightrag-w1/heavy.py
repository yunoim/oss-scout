"""MLPC 무거운 작업 규칙(wiki hq/README.md, 2026-10-03) 가드.
- 잠금 파일 C:/Users/quite/.mlpc-heavy.lock — 다른 창이 2시간 안에 잡았으면 시작하지 않는다
- 남은 RAM 3GB 미만이면 시작하지 않는다 · 20:30~21:30 은 Ollama 금지
매 문서/문항 전에 check() 를 다시 불러 중간에도 멈춘다. 진행은 progress.json 에 남아 다음 실행이 이어 간다."""
from __future__ import annotations

import ctypes
import subprocess
import time
from datetime import datetime
from pathlib import Path

LOCK = Path("C:/Users/quite/.mlpc-heavy.lock")
OWNER = "github 스카우터"
MIN_FREE_GB = 3.0
MAX_LLAMA_GB = 2.0  # 깨끗한 qwen3:8b·8192 로드는 0.85GB(10/3 실측)


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


def check() -> None:
    now = datetime.now()
    if (now.hour, now.minute) >= (20, 30) and (now.hour, now.minute) < (21, 30):
        raise Stop("20:30~21:30 Ollama 금지 시간")
    gb = free_gb()
    if gb < MIN_FREE_GB:
        raise Stop(f"남은 RAM {gb:.2f}GB < {MIN_FREE_GB}GB")
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
    check()
    LOCK.write_text(f"{OWNER} · {task} · {datetime.now():%Y-%m-%d %H:%M}\n", encoding="utf-8")


def release() -> None:
    if LOCK.exists() and LOCK.read_text(encoding="utf-8", errors="replace").startswith(OWNER):
        LOCK.unlink()
