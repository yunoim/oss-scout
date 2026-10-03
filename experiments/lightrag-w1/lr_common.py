"""공통 설정 — 인덱싱·질의·무검색 기준선이 모두 같은 값을 쓴다 (PREREG.md 와 일치해야 한다)."""
from __future__ import annotations

import os
from pathlib import Path

from lightrag import LightRAG, QueryParam
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.llm.ollama import ollama_embed, ollama_model_complete
from lightrag.utils import EmbeddingFunc

HERE = Path(__file__).parent
LLM = "qwen3:8b"
EMBED = "bge-m3:latest"
NUM_CTX = 12288          # 8GB VRAM 에 qwen3:8b Q4 + bge-m3 가 같이 올라가는 상한(ollama ps 로 확인)
MAX_TOTAL_TOKENS = 8000  # 질의 컨텍스트 예산 — 두 모드 공통. NUM_CTX 안에 프롬프트·답이 들어가야 한다
LLM_OPTIONS = {"num_ctx": NUM_CTX, "temperature": 0, "seed": 42, "think": False}

os.environ.setdefault("RERANK_BY_DEFAULT", "false")  # 리랭커 미구성 — 두 모드 공통으로 끈다


def make_rag(working_dir: Path) -> LightRAG:
    async def embed(texts, **kw):
        return await ollama_embed.func(texts, embed_model=EMBED, **kw)

    return LightRAG(
        working_dir=str(working_dir),
        llm_model_func=ollama_model_complete,
        llm_model_name=LLM,
        llm_model_kwargs={"options": LLM_OPTIONS, "timeout": 600},
        llm_model_max_async=1,
        embedding_func=EmbeddingFunc(embedding_dim=1024, max_token_size=8192, func=embed, model_name=EMBED),
        embedding_func_max_async=1,
        default_llm_timeout=600,
        addon_params={"language": "Korean"},
    )


async def ready(rag: LightRAG) -> LightRAG:
    await rag.initialize_storages()
    await initialize_pipeline_status()
    return rag


def param(mode: str) -> QueryParam:
    return QueryParam(mode=mode, max_total_tokens=MAX_TOTAL_TOKENS, enable_rerank=False)
