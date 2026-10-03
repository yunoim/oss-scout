"""MLPC 무거운 작업 규칙(wiki hq/README.md, 2026-10-03) 가드.
- 잠금 파일 C:/Users/quite/.mlpc-heavy.lock — 다른 창이 2시간 안에 잡았으면 시작하지 않는다
- 남은 RAM 3GB 미만이면 시작하지 않는다 · 20:30~21:30 은 Ollama 금지
매 문서/문항 전에 check() 를 다시 불러 중간에도 멈춘다. 진행은 progress.json 에 남아 다음 실행이 이어 간다."""
from __future__ import annotations

import ctypes
import time
from datetime import datetime
from pathlib import Path

LOCK = Path("C:/Users/quite/.mlpc-heavy.lock")
OWNER = "github 스카우터"
MIN_FREE_GB = 3.0


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
