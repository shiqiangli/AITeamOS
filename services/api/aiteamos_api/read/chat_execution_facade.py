"""Concrete Chat execution entrypoint for non-HTTP runtimes."""

from .chat_models import ChatMessageRequest, ChatMessageResponse


async def run_chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
    from .chat_runtime_factory import build_chat_execution_runtime

    return await build_chat_execution_runtime().run_message(request)
