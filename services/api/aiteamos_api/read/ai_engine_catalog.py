"""Shared AI Engine catalog metadata."""

from __future__ import annotations

from typing import Any


AI_ENGINE_CATALOG: dict[str, dict[str, Any]] = {
    "stub": {
        "display_name": "File stub",
        "kind": "local_model",
        "description": "Local deterministic fallback for offline development and product dogfooding.",
        "support_status": "supported",
        "auth_kind": "none",
        "capabilities": ["offline", "trace", "deterministic"],
        "config_fields": [],
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "kind": "llm_api",
        "description": "OpenAI-compatible LLM API used for low-cost Clara and Employee chat testing.",
        "support_status": "supported",
        "auth_kind": "bearer",
        "default_base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-flash",
        "default_thinking": "enabled",
        "default_context_window": 1000000,
        "default_max_tokens": 384000,
        "default_api_key_env": "DEEPSEEK_API_KEY",
        "model_options": ["deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner"],
        "thinking_options": ["disabled", "enabled"],
        "capabilities": ["chat", "streaming", "tool_planning", "reasoning", "graphiti_llm", "openai_compatible"],
        "config_fields": [
            {"id": "model", "label": "Default model", "kind": "text", "required": True},
            {"id": "thinking", "label": "Thinking", "kind": "select", "options": ["disabled", "enabled"]},
            {
                "id": "context_window",
                "label": "Context window",
                "kind": "number",
                "placeholder": "1000000",
                "help": "Model context length used by AITeamOS context loading; DeepSeek V4 supports 1M.",
            },
            {
                "id": "max_tokens",
                "label": "Max output tokens",
                "kind": "number",
                "placeholder": "384000",
                "help": "Sent as DeepSeek max_tokens. DeepSeek V4 max output is 384K.",
            },
            {"id": "base_url", "label": "Base URL", "kind": "text", "required": True},
            {"id": "api_key_env", "label": "API key env", "kind": "text", "required": True, "secret": True},
        ],
        "chat_options": [
            {"id": "thinking", "label": "Reasoning", "kind": "select", "options": ["disabled", "enabled"]},
        ],
    },
    "openai": {
        "display_name": "ChatGPT / OpenAI API",
        "kind": "llm_api",
        "description": "OpenAI Responses API engine for ChatGPT/OpenAI-backed Employees.",
        "support_status": "supported",
        "auth_kind": "bearer",
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-5.5",
        "default_thinking": "medium",
        "default_speed": "standard",
        "default_context_window": 1050000,
        "default_max_tokens": 4096,
        "max_output_tokens": 128000,
        "default_api_key_env": "OPENAI_API_KEY",
        "model_options": ["gpt-5.5", "gpt-5.5-2026-04-23", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5", "gpt-5-mini", "gpt-5-nano"],
        "thinking_options": ["none", "low", "medium", "high", "xhigh"],
        "speed_options": ["standard", "priority", "flex"],
        "capabilities": ["chat", "responses", "tool_calling", "reasoning", "graphiti_llm", "openai_compatible"],
        "config_fields": [
            {
                "id": "model",
                "label": "Default model",
                "kind": "select",
                "options": ["gpt-5.5", "gpt-5.5-2026-04-23", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5", "gpt-5-mini", "gpt-5-nano"],
                "required": True,
            },
            {
                "id": "thinking",
                "label": "Reasoning level",
                "kind": "select",
                "options": ["none", "low", "medium", "high", "xhigh"],
                "help": "Sent as Responses API reasoning.effort. GPT-5.5 defaults to medium.",
            },
            {
                "id": "speed",
                "label": "Speed",
                "kind": "select",
                "options": ["standard", "priority", "flex"],
                "help": "standard uses the project default. priority sends service_tier=priority. flex sends service_tier=flex.",
            },
            {
                "id": "max_tokens",
                "label": "Max output tokens",
                "kind": "number",
                "placeholder": "4096",
                "help": "Sent as Responses API max_output_tokens. GPT-5.5 supports up to 128K output tokens.",
            },
            {"id": "base_url", "label": "Base URL", "kind": "text", "required": True},
            {"id": "api_key_env", "label": "API key env", "kind": "text", "required": True, "secret": True},
        ],
        "chat_options": [
            {"id": "thinking", "label": "Reasoning", "kind": "select", "options": ["none", "low", "medium", "high", "xhigh"]},
            {"id": "speed", "label": "Speed", "kind": "select", "options": ["standard", "priority", "flex"]},
        ],
    },
    "gemini": {
        "display_name": "Gemini",
        "kind": "llm_api",
        "description": "Google Gemini API engine. Native and OpenAI-compatible paths are planned.",
        "support_status": "planned",
        "auth_kind": "api_key_header",
        "default_api_key_env": "GEMINI_API_KEY",
        "default_model": "gemini-3-flash",
        "capabilities": ["chat", "thinking", "multimodal"],
        "config_fields": [
            {"id": "model", "label": "Default model", "kind": "text"},
            {"id": "api_key_env", "label": "API key env", "kind": "text", "secret": True},
            {"id": "project", "label": "Project", "kind": "text"},
            {"id": "location", "label": "Location", "kind": "text"},
        ],
    },
    "kimi": {
        "display_name": "Kimi",
        "kind": "llm_api",
        "description": "Kimi / Moonshot LLM API engine for Chinese and long-context workflows.",
        "support_status": "planned",
        "auth_kind": "bearer",
        "default_api_key_env": "KIMI_API_KEY",
        "default_model": "kimi-k2",
        "capabilities": ["chat", "long_context"],
        "config_fields": [
            {"id": "model", "label": "Default model", "kind": "text"},
            {"id": "base_url", "label": "Base URL", "kind": "text"},
            {"id": "api_key_env", "label": "API key env", "kind": "text", "secret": True},
        ],
    },
    "ollama": {
        "display_name": "Ollama",
        "kind": "local_model",
        "description": "Local OpenAI-compatible model endpoint. Execution adapter is planned.",
        "support_status": "planned",
        "auth_kind": "none",
        "default_base_url": "http://localhost:11434/v1",
        "default_model": "llama3.2",
        "capabilities": ["chat", "local_model", "openai_compatible"],
        "config_fields": [
            {"id": "model", "label": "Default model", "kind": "text"},
            {"id": "base_url", "label": "Base URL", "kind": "text"},
        ],
    },
    "lmstudio": {
        "display_name": "LM Studio",
        "kind": "local_model",
        "description": "Local OpenAI-compatible LM Studio server. Execution adapter is planned.",
        "support_status": "planned",
        "auth_kind": "none",
        "default_base_url": "http://localhost:1234/v1",
        "default_model": "local-model",
        "capabilities": ["chat", "local_model", "openai_compatible"],
        "config_fields": [
            {"id": "model", "label": "Default model", "kind": "text"},
            {"id": "base_url", "label": "Base URL", "kind": "text"},
        ],
    },
    "vllm": {
        "display_name": "vLLM",
        "kind": "local_model",
        "description": "Self-hosted OpenAI-compatible vLLM endpoint. Execution adapter is planned.",
        "support_status": "planned",
        "auth_kind": "bearer",
        "default_base_url": "http://localhost:8000/v1",
        "default_model": "served-model",
        "default_api_key_env": "AITEAMOS_VLLM_API_KEY",
        "capabilities": ["chat", "local_model", "openai_compatible"],
        "config_fields": [
            {"id": "model", "label": "Default model", "kind": "text"},
            {"id": "base_url", "label": "Base URL", "kind": "text"},
            {"id": "api_key_env", "label": "API key env", "kind": "text", "secret": True},
        ],
    },
    "codex": {
        "display_name": "Codex",
        "kind": "agent_platform",
        "description": "OpenAI coding agent platform for repo work, review, and execution handoffs.",
        "support_status": "planned",
        "auth_kind": "cli_login",
        "capabilities": ["coding_agent", "repo_edit", "test_run", "review"],
        "config_fields": [
            {"id": "command", "label": "Command", "kind": "text", "placeholder": "codex"},
            {"id": "profile", "label": "Profile", "kind": "text"},
            {"id": "workspace", "label": "Workspace root", "kind": "text"},
        ],
    },
    "claude-code": {
        "display_name": "Claude Code",
        "kind": "agent_platform",
        "description": "Claude Code agent platform for coding sessions and MCP-backed tools.",
        "support_status": "planned",
        "auth_kind": "cli_login",
        "default_api_key_env": "ANTHROPIC_API_KEY",
        "capabilities": ["coding_agent", "repo_edit", "mcp", "review"],
        "config_fields": [
            {"id": "command", "label": "Command", "kind": "text", "placeholder": "claude"},
            {"id": "api_key_env", "label": "API key env", "kind": "text", "secret": True},
            {"id": "workspace", "label": "Workspace root", "kind": "text"},
        ],
    },
    "cursor": {
        "display_name": "Cursor",
        "kind": "agent_platform",
        "description": "Cursor agent handoff target for IDE-backed coding sessions.",
        "support_status": "planned",
        "auth_kind": "ide_login",
        "capabilities": ["coding_agent", "ide_context", "repo_edit"],
        "config_fields": [
            {"id": "workspace", "label": "Workspace root", "kind": "text"},
            {"id": "profile", "label": "Profile", "kind": "text"},
        ],
    },
    "qoder": {
        "display_name": "Qoder",
        "kind": "agent_platform",
        "description": "Qoder agent platform handoff target for deeper Ticket work.",
        "support_status": "planned",
        "auth_kind": "platform_login",
        "capabilities": ["coding_agent", "repo_edit", "execution_handoff"],
        "config_fields": [
            {"id": "workspace", "label": "Workspace root", "kind": "text"},
            {"id": "profile", "label": "Profile", "kind": "text"},
        ],
    },
}

SUPPORTED_AI_ENGINE_IDS = {
    engine_id
    for engine_id, catalog in AI_ENGINE_CATALOG.items()
    if str(catalog.get("support_status")) == "supported"
}

GRAPHITI_AI_ENGINE_IDS = {
    engine_id
    for engine_id, catalog in AI_ENGINE_CATALOG.items()
    if str(catalog.get("support_status")) == "supported"
    and "graphiti_llm" in {str(capability) for capability in catalog.get("capabilities", [])}
}
