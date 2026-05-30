"""
Shared Kernel — LLM / Embedding 抽象层 (plan.md §0.3)。

所有 LLM 调用通过 litellm 统一封装，支持运行时切换模型提供商。
当 OPENAI_API_KEY 未设置时，自动降级为离线 mock 模式：
- embedding 返回随机向量
- LLM 返回固定 mock 文本

确保所有 Stage 测试不依赖真实 API 调用。
"""

from __future__ import annotations

import logging
import os
import random
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = os.environ.get("AITEAMOS_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = int(os.environ.get("AITEAMOS_EMBEDDING_DIM", "1536"))
LLM_MODEL = os.environ.get("AITEAMOS_LLM_MODEL", "gpt-4o-mini")


def _is_offline_mode() -> bool:
    """Return True when no API key is configured (test/dev mode)."""
    return not os.environ.get("OPENAI_API_KEY")


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


async def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for the given text.

    In offline mode (no OPENAI_API_KEY), returns a random vector of
    EMBEDDING_DIM dimensions. This ensures tests can run without
    external API calls.
    """
    if _is_offline_mode():
        logger.debug("LLM offline mode: returning random embedding (dim=%d)", EMBEDDING_DIM)
        rng = random.Random(hash(text))
        return [rng.gauss(0, 1) for _ in range(EMBEDDING_DIM)]

    import litellm

    response = await litellm.aembedding(
        model=EMBEDDING_MODEL,
        input=[text],
    )
    return response.data[0]["embedding"]


# ---------------------------------------------------------------------------
# LLM 提取 / 反思
# ---------------------------------------------------------------------------

_MOCK_LLM_RESPONSE = (
    "This is a mock LLM response for offline/testing mode. "
    "Set OPENAI_API_KEY environment variable to use real LLM calls."
)


async def llm_extract(prompt: str, system: str) -> str:
    """Call LLM for extraction/reflection tasks.

    In offline mode, returns a fixed mock response.

    Args:
        prompt: The user prompt content.
        system: The system message / instruction.

    Returns:
        LLM-generated text response.
    """
    if _is_offline_mode():
        logger.debug("LLM offline mode: returning mock response")
        return _MOCK_LLM_RESPONSE

    import litellm

    response = await litellm.acompletion(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content
