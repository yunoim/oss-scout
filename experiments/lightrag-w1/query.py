"""30문항을 naive · mix · hybrid · 무검색(nocontext) 으로 답하게 해 answers.jsonl 에 쓴다.
이미 답이 있는 (문항, 모드) 는 건너뛴다 — 중간에 끊겨도 이어서 돈다."""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

import ollama

import heavy

from lr_common import HERE, LLM, LLM_OPTIONS, make_rag, param, ready

MODES = ["naive", "mix", "hybrid", "nocontext"]
OUT = HERE / "answers.jsonl"
THINK = re.compile(r"<think>.*?</think>", re.S)


def done() -> set[tuple[str, str]]:
    if not OUT.exists():
        return set()
    return {(r["id"], r["mode"]) for r in map(json.loads, OUT.read_text(encoding="utf-8").splitlines())}


def nocontext(q: str) -> str:
    opts = {k: v for k, v in LLM_OPTIONS.items() if k != "think"}
    r = ollama.chat(model=LLM, messages=[{"role": "user", "content": q}], options=opts, think=False)
    return r["message"]["content"]


async def main() -> None:
    qs = [json.loads(l) for l in (HERE / "questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    have = done()
    try:
        heavy.acquire("LightRAG 질의 30문항x4")
        await run(qs, have)
    except heavy.Stop as e:
        print("STOP:", e, flush=True)
    finally:
        heavy.release()


async def run(qs: list[dict], have: set) -> None:
    rag = await ready(make_rag(HERE / "rag_storage"))
    with OUT.open("a", encoding="utf-8") as f:
        for q in qs:
            heavy.check()
            for mode in MODES:
                if (q["id"], mode) in have:
                    continue
                t = time.time()
                ans = nocontext(q["q"]) if mode == "nocontext" else await rag.aquery(q["q"], param=param(mode))
                ans = THINK.sub("", ans or "").strip()
                f.write(json.dumps({"id": q["id"], "mode": mode, "answer": ans, "sec": round(time.time() - t, 1)},
                                   ensure_ascii=False) + "\n")
                f.flush()
                print(q["id"], mode, f"{time.time() - t:.0f}s", len(ans), flush=True)
    await rag.finalize_storages()


if __name__ == "__main__":
    asyncio.run(main())
