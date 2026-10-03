"""인덱싱(이어 하기 가능). 사용: python index.py <working_dir> <doc.txt> [<doc.txt> ...]
1) 실패·중단된 문서부터 다시 처리(LightRAG 파이프라인 재시도) 2) 아직 없는 문서를 하나씩 넣는다.
진행은 LightRAG 문서 상태(processed)를 기준으로 progress.json 에 적는다 — ainsert 는 실패해도 예외를 안 던지므로
"끝났다" 는 상태값으로만 판단한다. 매 문서 전에 heavy.check() — RAM·시간대 조건이 안 맞으면 멈추고 잠금을 푼다."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import heavy
from lr_common import HERE, make_rag, ready

PROGRESS = HERE / "progress.json"


def statuses(wd: Path) -> dict[str, str]:
    p = wd / "kv_store_doc_status.json"
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for k, v in json.loads(p.read_text(encoding="utf-8")).items():
        if k.startswith("dup-"):
            continue
        out[v.get("file_path")] = str(v.get("status")).split(".")[-1].lower()
    return out


def write_progress(wd: Path) -> dict[str, str]:
    st = statuses(wd)
    PROGRESS.write_text(json.dumps({"status": st}, ensure_ascii=False, indent=1), encoding="utf-8")
    return st


async def main(wd: Path, docs: list[Path]) -> None:
    st = write_progress(wd)
    if all(st.get(d.name) == "processed" for d in docs):
        print("all processed", st, flush=True)
        return
    try:
        heavy.acquire("LightRAG 색인")
        rag = await ready(make_rag(wd))
        if any(s in ("failed", "processing", "pending") for s in st.values()):
            heavy.check()
            t = time.time()
            await rag.apipeline_process_enqueue_documents()
            print(f"retried failed/interrupted in {time.time() - t:.0f}s", write_progress(wd), flush=True)
        for d in docs:
            if d.name in statuses(wd):
                continue
            heavy.check()
            t = time.time()
            await rag.ainsert(d.read_text(encoding="utf-8"), file_paths=d.name)
            print(f"{d.name}: {write_progress(wd).get(d.name)} in {time.time() - t:.0f}s", flush=True)
        await rag.finalize_storages()
        print("DONE", write_progress(wd), flush=True)
    except heavy.Stop as e:
        print("STOP:", e, flush=True)
    finally:
        heavy.release()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]]))
