"""인덱싱(이어 하기 가능). 사용: python index.py <working_dir> <doc.txt> [<doc.txt> ...]
문서 하나씩 넣고 끝날 때마다 progress.json 에 적는다. 끊기면 같은 명령을 다시 돌리면 남은 문서부터 간다.
매 문서 전에 heavy.check() — RAM·시간대 조건이 안 맞으면 멈추고 잠금을 푼다."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import heavy
from lr_common import HERE, make_rag, ready

PROGRESS = HERE / "progress.json"


def load() -> dict:
    return json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {"indexed": {}}


async def main(wd: Path, docs: list[Path]) -> None:
    prog = load()
    todo = [d for d in docs if d.name not in prog["indexed"]]
    if not todo:
        print("all indexed", prog, flush=True)
        return
    heavy.acquire(f"LightRAG 색인 {len(todo)}건")
    try:
        rag = await ready(make_rag(wd))
        for d in todo:
            heavy.check()
            t = time.time()
            await rag.ainsert(d.read_text(encoding="utf-8"), file_paths=d.name)
            prog["indexed"][d.name] = round(time.time() - t)
            PROGRESS.write_text(json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"indexed {d.name} in {time.time() - t:.0f}s", flush=True)
        await rag.finalize_storages()
    except heavy.Stop as e:
        print("STOP:", e, flush=True)
    finally:
        heavy.release()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]]))
