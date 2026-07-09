"""Stateless request intent classifiers for Employee Chat."""

from __future__ import annotations

import re

LOCAL_TICKET_ID_RE = re.compile(r"\b(?:ticket-[A-Za-z0-9_.:-]+|(?:rd|pv|arch|rel|mem|doc|ops|trace)-\d{4,})\b", re.IGNORECASE)

_LIST_EMPLOYEES_EN_RE = re.compile(
    r"\b(list|show|display|view)\b.*\b(ai\s+)?employees\b|\bemployees\b.*\b(list|show|all|available)\b"
)
_CREATE_EMPLOYEE_EN_RE = re.compile(r"\b(create|add|new|setup|set up)\b.*\b(employee|profile|user|employee)\b")
_EDIT_EMPLOYEE_EN_RE = re.compile(r"\b(edit|update|modify|change)\b.*\b(employee|profile)\b")
_LIST_SKILLS_EN_RE = re.compile(r"\b(list|show|display|view)\b.*\bskills?\b|\bskills?\b.*\b(list|show|all|available)\b")
_CREATE_SKILL_EN_RE = re.compile(r"\b(create|add|new|setup|set up)\b.*\bskill\b")
_SEARCH_KNOWLEDGE_EN_RE = re.compile(r"\b(search|find|lookup|read|query)\b.*\b(knowledge|docs?|documents?|memories|decisions)\b")
_CREATE_TICKET_EN_RE = re.compile(r"\b(create|open|plan|delegate|assign)\b.*\bticket\b")
_REPORT_TICKET_EN_RE = re.compile(r"\b(report|record|complete|finish|validate)\b.*\bticket\b")
_LIST_CODE_REPOSITORIES_EN_RE = re.compile(
    r"\b(list|show|display|view)\b.*\b(code\s+)?(repos?|repositories)\b|"
    r"\b(code\s+)?(repos?|repositories)\b.*\b(list|show|all|available)\b"
)
_INSPECT_CODE_REPOSITORY_EN_RE = re.compile(
    r"\b(inspect|search|read|check|review|analy[sz]e|look)\b.*\b(codebase|source|files?|paths?|repos?|repositories|repository)\b|"
    r"\b(codebase|source|files?|paths?|repos?|repositories|repository)\b.*\b(inspect|search|read|check|review|analy[sz]e|look)\b"
)


def _normalized(message: str) -> str:
    return message.strip().lower()


def _compact(message: str) -> str:
    return re.sub(r"\s+", "", _normalized(message))


def is_list_employees_request(message: str) -> bool:
    normalized = _normalized(message)
    if "list_employees" in normalized:
        return True
    if _LIST_EMPLOYEES_EN_RE.search(normalized):
        return True

    compact = _compact(message)
    if not any(token in compact for token in ("成员", "员工", "employee", "employee")):
        return False
    return any(
        token in compact
        for token in (
            "列出",
            "列表",
            "清单",
            "有哪些",
            "所有",
            "全部",
            "团队成员",
            "成员列表",
            "成员清单",
        )
    )


def is_create_employee_request(message: str) -> bool:
    normalized = _normalized(message)
    if "create_employee" in normalized:
        return True
    if _CREATE_EMPLOYEE_EN_RE.search(normalized):
        return True
    compact = _compact(message)
    if not any(token in compact for token in ("成员", "员工", "employee", "employee", "用户", "user")):
        return False
    return any(token in compact for token in ("创建", "新增", "添加", "新建"))


def is_edit_employee_profile_request(message: str) -> bool:
    normalized = _normalized(message)
    if "edit_employee_profile" in normalized:
        return True
    if _EDIT_EMPLOYEE_EN_RE.search(normalized):
        return True
    compact = _compact(message)
    has_profile_token = any(token in compact for token in ("成员", "员工", "employee", "employee", "profile", "用户", "user"))
    has_field_token = any(token in compact for token in ("summary", "role", "skills", "skill", "技能", "ai_engine", "运行引擎", "名字", "角色", "摘要", "描述"))
    if not has_profile_token and not has_field_token:
        return False
    return any(token in compact for token in ("编辑", "修改", "更新", "调整", "改成", "改为"))


def is_list_skills_request(message: str) -> bool:
    normalized = _normalized(message)
    if "list_skills" in normalized:
        return True
    if _LIST_SKILLS_EN_RE.search(normalized):
        return True

    compact = _compact(message)
    if not any(token in compact for token in ("skill", "skills", "技能")):
        return False
    return any(token in compact for token in ("列出", "列表", "清单", "有哪些", "所有", "全部"))


def is_create_skill_request(message: str) -> bool:
    normalized = _normalized(message)
    if "create_skill" in normalized:
        return True
    if _CREATE_SKILL_EN_RE.search(normalized):
        return True
    compact = _compact(message)
    if not any(token in compact for token in ("skill", "skills", "技能")):
        return False
    if any(token in compact for token in ("成员", "员工", "employee", "employee", "用户", "user")):
        return False
    return any(token in compact for token in ("创建", "新增", "新建"))


def is_search_knowledge_request(message: str) -> bool:
    normalized = _normalized(message)
    if "search_knowledge" in normalized:
        return True
    if _SEARCH_KNOWLEDGE_EN_RE.search(normalized):
        return True
    compact = _compact(message)
    if not any(token in compact for token in ("知识库", "文档", "docs", "doc", "memory", "memories", "记忆", "decision", "决策")):
        return False
    return any(token in compact for token in ("搜索", "查找", "查询", "读取", "检索", "看看", "相关"))


def is_create_ticket_request(message: str) -> bool:
    normalized = _normalized(message)
    if "create_ticket" in normalized:
        return True
    if _CREATE_TICKET_EN_RE.search(normalized):
        return True
    compact = _compact(message)
    if any(token in compact for token in ("ticket", "工单", "本地ticket", "本地任务", "任务")) and any(
        token in compact for token in ("创建", "新增", "打开", "分解", "委派", "分配", "派给", "交给")
    ):
        return True
    return any(token in compact for token in ("委派给", "派给", "交给")) and any(
        token in compact for token in ("alex", "rd", "pv", "architect", "架构", "研发", "验证")
    )


def is_list_tickets_request(message: str) -> bool:
    normalized = _normalized(message)
    if "list_tickets" in normalized:
        return True
    compact = _compact(message)
    if any(token in compact for token in ("ticket", "tickets", "工单", "本地ticket", "本地任务", "任务")):
        return any(token in compact for token in ("列出", "列表", "清单", "查看", "有哪些", "所有", "list", "show"))
    return False


def is_record_ticket_report_request(message: str) -> bool:
    normalized = _normalized(message)
    if "record_ticket_report" in normalized:
        return True
    if not LOCAL_TICKET_ID_RE.search(message):
        return False
    if _REPORT_TICKET_EN_RE.search(normalized):
        return True
    compact = _compact(message)
    return any(token in compact for token in ("汇报", "报告", "完成", "验证", "记录", "结果"))


def is_request_ticket_validation_request(message: str) -> bool:
    normalized = _normalized(message)
    if any(token in normalized for token in ("request_validation", "validation_request", "request_ticket_validation")):
        return True
    if not LOCAL_TICKET_ID_RE.search(message):
        return False
    if re.search(r"\b(request|ask|assign|send)\b.*\b(validation|validator|verify|pv|review)\b", normalized):
        return True
    compact = _compact(message)
    return any(
        token in compact
        for token in (
            "请求验证",
            "发起验证",
            "要求验证",
            "请求pv",
            "让pv",
            "请pv",
            "交给pv验证",
            "请求peter验证",
            "让peter验证",
        )
    )


def is_request_human_review_request(message: str) -> bool:
    normalized = _normalized(message)
    compact = _compact(message)
    if any(token in normalized for token in ("request_human_review", "human_review_request", "ask_human_review")):
        return True
    if not LOCAL_TICKET_ID_RE.search(message):
        return False
    if re.search(r"\b(request|ask|need|require|send)\b.*\b(human|manual)\b.*\b(review|approval|approve)\b", normalized):
        return True
    if re.search(r"\b(human|manual)\b.*\b(review|approval|approve)\b", normalized):
        return True
    return any(
        token in compact
        for token in (
            "人工复核",
            "人工审核",
            "人工确认",
            "人工审批",
            "人类复核",
            "人类审核",
            "人类确认",
            "人类审批",
            "请求人工",
            "请求人类",
            "交给人工",
            "让人类",
            "请人类",
        )
    )


def is_list_code_repositories_request(message: str) -> bool:
    normalized = _normalized(message)
    if "list_code_repositories" in normalized:
        return True
    if _LIST_CODE_REPOSITORIES_EN_RE.search(normalized):
        return True
    compact = _compact(message)
    has_repo_token = any(token in compact for token in ("代码仓库", "代码库", "仓库")) or bool(
        re.search(r"\b(repos?|repositories|repository)\b", normalized)
    )
    if not has_repo_token:
        return False
    return any(token in compact for token in ("列出", "列表", "清单", "查看", "有哪些", "所有", "全部", "配置", "可用"))


def is_inspect_code_repository_request(message: str) -> bool:
    normalized = _normalized(message)
    if "inspect_code_repository" in normalized:
        return True
    if _INSPECT_CODE_REPOSITORY_EN_RE.search(normalized):
        return True
    compact = _compact(message)
    has_repo_token = any(token in compact for token in ("代码仓库", "代码库", "仓库", "代码", "源码", "文件", "实现")) or bool(
        re.search(r"\b(codebase|source|files?|paths?|repos?|repositories|repository)\b", normalized)
    )
    if not has_repo_token and not LOCAL_TICKET_ID_RE.search(message):
        return False
    return any(
        token in compact
        for token in ("检查", "读取", "搜索", "分析", "查看", "review", "inspect", "search", "read", "check", "analyze", "analyse")
    )


def is_permission_inspection_request(message: str, *, is_human_review_request: bool) -> bool:
    if is_human_review_request:
        return False
    normalized = _normalized(message)
    if "kernel.permissions" in normalized or "permissions.inspect" in normalized:
        return True
    compact = _compact(message)
    if any(token in compact for token in ("权限", "授权", "可执行", "能做什么", "能不能", "可以做什么", "具备哪些", "有哪些能力")):
        return any(token in compact for token in ("权限", "授权", "command", "命令", "能力", "employee", "clara", "你", "我"))
    return bool(
        re.search(
            r"\b(what|which|list|show|describe|inspect)\b.*\b(permissions?|authorization|commands?|capabilities)\b|"
            r"\b(can|could)\b.*\b(create|delete|update|assign|run)\b",
            normalized,
        )
    )


def is_self_bootstrap_summary_request(message: str) -> bool:
    normalized = _normalized(message)
    if any(token in normalized for token in ("self_bootstrap_summary", "bootstrap_summary", "learning_summary", "tickets.manage:self_bootstrap_summary")):
        return True
    compact = _compact(message)
    if any(token in compact for token in ("自举", "越用越聪明", "学到了什么", "学习总结", "批次总结", "下一批")):
        return any(token in compact for token in ("总结", "学到", "复用", "召回", "经验", "下一批", "blocker", "验证"))
    return bool(
        re.search(
            r"\b(self[-_\s]?bootstrap|learning|learned|batch)\b.*\b(summary|delta|reused|recall|next)\b|"
            r"\b(what|which|show|summarize)\b.*\b(aiteamos)\b.*\b(learned|reused|next)\b",
            normalized,
        )
    )
