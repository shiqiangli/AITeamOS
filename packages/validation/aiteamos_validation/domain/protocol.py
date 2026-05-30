"""
Validation Context — Harness Adapter Protocol (arch.md §4.2.1)。

所有外部验证适配器必须实现此 Protocol。
系统不内建任何业务验证逻辑 — 真理源外置。
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Protocol

from .models import (
    AdapterHealth,
    DeliverableRef,
    HarnessManifest,
    HarnessResult,
    HarnessTicket,
    ValidationContext,
)


class Pending:
    """异步验证等待中的哨兵值。"""
    pass


PENDING = Pending()


class HarnessAdapterProtocol(Protocol):
    """Harness 适配器协议 (arch.md §4.2.1)。

    设计原则:
    - 系统不内建任何业务验证逻辑
    - Adapter 不写 .aiteamos/, 只返回归一化结果
    - 同步与异步协议统一接口, 由 manifest.protocol 区分
    """

    @property
    @abstractmethod
    def manifest(self) -> HarnessManifest:
        """tier, protocol, endpoint, auth_ref。"""
        ...

    @abstractmethod
    async def trigger_regression(
        self, deliverable: DeliverableRef, ctx: ValidationContext
    ) -> HarnessTicket:
        """触发外部验证。

        同步 Harness: ticket.outcome 立即可读。
        异步 Harness: ticket.pending=True, 含 callback_token 与 ETA。
        """
        ...

    @abstractmethod
    async def poll_results(self, ticket: HarnessTicket) -> HarnessResult | Pending:
        """轮询拉取结果 (外部系统不支持 Webhook 时使用)。"""
        ...

    @abstractmethod
    async def on_callback(self, signed_payload: dict) -> HarnessResult:
        """Webhook 入站处理: HMAC 校验 + 归一化。"""
        ...

    @abstractmethod
    def normalize(self, raw: dict) -> HarnessResult:
        """Adapter-specific 结果归一化。"""
        ...

    @abstractmethod
    def healthcheck(self) -> AdapterHealth:
        """探测外部验证系统可达性。"""
        ...
