"""사후 추가 실험(CEO-77, 2026-10-04) — 사전 등록 밖. 색인은 그대로 두고 30문항을 지정 모드로 다시 묻는다.
설정은 환경변수로 받는다(lr_common: MLPC_NUM_CTX · MLPC_MAX_TOTAL_TOKENS · MLPC_MAX_ENTITY_TOKENS · MLPC_MAX_RELATION_TOKENS).
사용: python query_post.py <tag> <mode> [<mode> ...]   → answers_post_<tag>.jsonl (이어 하기 가능)
각 답에 설정값과 최종 컨텍스트의 청크 수(로그에서 파싱)를 함께 남겨 "청크가 실제로 들어갔는가" 를 증명한다."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time

import heavy
from lr_common import HERE, MAX_ENTITY_TOKENS, MAX_RELATION_TOKENS, MAX_TOTAL_TOKENS, NUM_CTX, make_rag, param, ready

THINK = re.compile(r"<think>.*?</think>", re.S)
FINAL = re.compile(r"Final context: (?:(\d+) entities, (\d+) relations, )?(\d+) chunks")


class ContextCatcher(logging.Handler):
    """LightRAG 가 INFO 로 찍는 'Final context: N entities, M relations, K chunks' 를 잡아 둔다."""

    def __init__(self) -> None:
        super().__init__()
        self.last: dict | None = None

    def emit(self, record: logging.LogRecord) -> None:
        m = FINAL.search(record.getMessage())
        if m:
            self.last = {"entities": int(m.group(1) or 0), "relations": int(m.group(2) or 0), "chunks": int(m.group(3))}


def done(out) -> set[tuple[str, str]]:
    if not out.exists():
        return set()
    return {(r["id"], r["mode"]) for r in map(json.loads, out.read_text(encoding="utf-8").splitlines()) if r}


async def main(tag: str, modes: list[str]) -> None:
    out = HERE / f"answers_post_{tag}.jsonl"
    qs = [json.loads(l) for l in (HERE / "questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    have = done(out)
    cfg = {"num_ctx": NUM_CTX, "max_total_tokens": MAX_TOTAL_TOKENS,
           "max_entity_tokens": MAX_ENTITY_TOKENS, "max_relation_tokens": MAX_RELATION_TOKENS}
    print("config", cfg, "modes", modes, "already", len(have), flush=True)
    catcher = ContextCatcher()
    logging.getLogger("lightrag").addHandler(catcher)
    try:
        heavy.acquire(f"LightRAG 사후 질의 {tag}")
        rag = await ready(make_rag(HERE / "rag_storage"))
        with out.open("a", encoding="utf-8") as f:
            for q in qs:
                for mode in modes:
                    if (q["id"], mode) in have:
                        continue
                    heavy.check()
                    catcher.last = None
                    t = time.time()
                    ans = THINK.sub("", (await rag.aquery(q["q"], param=param(mode))) or "").strip()
                    row = {"id": q["id"], "mode": mode, "answer": ans, "sec": round(time.time() - t, 1),
                           "context": catcher.last, "config": cfg, "tag": tag}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    print(q["id"], mode, f"{time.time() - t:.0f}s", len(ans), catcher.last, flush=True)
        await rag.finalize_storages()
        print("DONE", flush=True)
    except heavy.Stop as e:
        print("STOP:", e, flush=True)
    finally:
        heavy.release()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2:]))
