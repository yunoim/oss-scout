"""공통 설정 — 인덱싱·질의·무검색 기준선이 모두 같은 값을 쓴다 (PREREG.md 와 일치해야 한다)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from lightrag import LightRAG, QueryParam
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.llm.ollama import ollama_embed, ollama_model_complete
from lightrag.utils import EmbeddingFunc

HERE = Path(__file__).parent
LLM = "qwen3:8b"
EMBED = "bge-m3:latest"
# 사전 등록 값. 사후 추가 실험(CEO-77, 10/4)만 환경변수로 덮어쓴다 — 기본값은 PREREG 와 같아야 한다
NUM_CTX = int(os.environ.get("MLPC_NUM_CTX", "8192"))           # 8GB VRAM 에 qwen3:8b 가 GPU 100% 로 올라가는 값(10/3 CEO 결정 — 12288 은 13% CPU 로 넘쳤다)
MAX_TOTAL_TOKENS = int(os.environ.get("MLPC_MAX_TOTAL_TOKENS", "5000"))  # 질의 컨텍스트 예산 — 두 모드 공통. NUM_CTX 안에 시스템 프롬프트·질문·답이 함께 들어가야 한다
# mix/hybrid 에서 개체·관계 컨텍스트 상한(1.5.7 기본 6000/8000). 기본값(None)이면 건드리지 않는다.
# 10/4 본 실험에서 예산 5000 을 개체+관계가 다 써 청크 0 이 됐다 — 사후 실험은 이 둘을 줄여 청크가 들어가게 한다
MAX_ENTITY_TOKENS = int(os.environ["MLPC_MAX_ENTITY_TOKENS"]) if os.environ.get("MLPC_MAX_ENTITY_TOKENS") else None
MAX_RELATION_TOKENS = int(os.environ["MLPC_MAX_RELATION_TOKENS"]) if os.environ.get("MLPC_MAX_RELATION_TOKENS") else None
# mmap: Ollama 가 Windows+CUDA 에서 이미 끈다(server.log "disabling mmap ... reason=windows_cuda") — 설정 불필요.
# num_predict: 반복 생성 폭주 차단(10/3 2019626 첫 청크가 600초 시간초과). 정상 추출·답변은 이보다 훨씬 짧다
LLM_OPTIONS = {"num_ctx": NUM_CTX, "num_predict": 3072, "temperature": 0, "seed": 42, "think": False}

os.environ.setdefault("RERANK_BY_DEFAULT", "false")  # 리랭커 미구성 — 두 모드 공통으로 끈다


async def guarded_complete(*args, **kwargs):
    """LLM 호출마다 MLPC 무거운 작업 조건을 다시 본다. 어긋나면 잠금을 풀고 프로세스를 바로 끝낸다 —
    처리 중이던 문서는 LightRAG 상태가 processing 으로 남아 다음 실행이 이어 간다."""
    import heavy
    try:
        heavy.check()
    except heavy.Stop as e:
        print("STOP(mid-doc):", e, flush=True)
        heavy.release()
        os._exit(3)
    return await ollama_model_complete(*args, **kwargs)


def make_rag(working_dir: Path) -> LightRAG:
    async def embed(texts, **kw):
        return await ollama_embed.func(texts, embed_model=EMBED, **kw)

    return LightRAG(
        working_dir=str(working_dir),
        llm_model_func=guarded_complete,
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
    extra = {}
    if MAX_ENTITY_TOKENS is not None:
        extra["max_entity_tokens"] = MAX_ENTITY_TOKENS
    if MAX_RELATION_TOKENS is not None:
        extra["max_relation_tokens"] = MAX_RELATION_TOKENS
    return QueryParam(mode=mode, max_total_tokens=MAX_TOTAL_TOKENS, enable_rerank=False, **extra)
