"""인덱싱. 사용: python index.py <working_dir> <doc.txt> [<doc.txt> ...]"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from lr_common import make_rag, ready


async def main(wd: Path, docs: list[Path]) -> None:
    rag = await ready(make_rag(wd))
    t0 = time.time()
    for d in docs:
        t = time.time()
        await rag.ainsert(d.read_text(encoding="utf-8"), file_paths=d.name)
        print(f"indexed {d.name} in {time.time() - t:.0f}s", flush=True)
    await rag.finalize_storages()
    stats = {}
    for name in ("kv_store_text_chunks.json", "vdb_entities.json", "vdb_relationships.json"):
        p = wd / name
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            stats[name] = len(data.get("data", data)) if isinstance(data, dict) else len(data)
    print("total", f"{time.time() - t0:.0f}s", stats, flush=True)


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]]))
