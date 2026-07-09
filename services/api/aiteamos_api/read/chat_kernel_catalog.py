"""Kernel command catalog constants for Employee Chat."""

from __future__ import annotations

import re

from .kernel_command_service import KernelCommandSpec


COMMAND_PLANNING_SIGNAL_RE = re.compile(
    r"employees\.manage|assets\.manage|tickets\.manage|knowledge\.search|repositories\.(?:list|inspect)|terminal\.run|"
    r"kernel\.permissions|permissions\.inspect|"
    r"create_employee|edit_employee_profile|delete_employee|list_employees|"
    r"list_skills|create_skill|assign_skill_to_employee|delete_skill|"
    r"search_knowledge|create_ticket|implement_ticket|record_ticket_report|record_validation|record_failure|request_ticket_validation|request_validation|request_human_review|self_bootstrap_close|self_bootstrap_complete|self_bootstrap_start|start_self_bootstrap|self_bootstrap_summary|bootstrap_summary|learning_summary|list_tickets|list_code_repositories|inspect_code_repository|"
    r"创建|新增|添加|新建|补|配置|设置|编辑|修改|更新|调整|改成|改为|删除|移除|删掉|分配|关联|权限|授权|请求|复核|审核|审批|确认|人工|人类|"
    r"列出|列表|清单|有哪些|所有|员工|成员|用户|委派|派给|交给|推进|汇报|验证|完成|"
    r"技能|知识库|文档|决策|记忆|代码仓库|代码库|仓库|工单|任务|终端|命令|执行|\brepos?\b|\brepository\b|\brepositories\b|"
    r"\b(create|add|new|setup|edit|update|modify|change|delete|remove|drop|assign|list|show|employee|employee|profile|user|skills?|terminal|command|run|permissions?|capabilities)\b",
    re.IGNORECASE,
)
TERMINAL_RUN_EN_RE = re.compile(
    r"\b(terminal\.run|run|execute)\b.*\b(command|terminal|shell|pytest|npm|git|pwd|ls)\b|"
    r"\b(pytest|npm\s+(?:test|run\s+build)|git\s+(?:status|diff|show)|pwd|ls)\b",
    re.IGNORECASE,
)
TERMINAL_ALLOWED_EXECUTABLES = {"git", "ls", "npm", "pwd", "pytest"}
TERMINAL_ALLOWED_NPM_COMMANDS = {("npm", "test"), ("npm", "run", "build")}
TERMINAL_ALLOWED_GIT_COMMANDS = {("git", "status"), ("git", "diff"), ("git", "show")}


HANDLER_TO_COMMAND_ID: dict[str, str] = {
    "list_employees": "employees.manage:list",
    "create_employee": "employees.manage:create",
    "edit_employee_profile": "employees.manage:update",
    "delete_employee": "employees.manage:delete",
    "list_skills": "assets.manage:list_skills",
    "create_skill": "assets.manage:create_skill",
    "assign_skill_to_employee": "assets.manage:assign_skill",
    "delete_skill": "assets.manage:delete_skill",
    "search_knowledge": "knowledge.search:search",
    "create_ticket": "tickets.manage:create",
    "list_tickets": "tickets.manage:list",
    "record_ticket_report": "tickets.manage:report",
    "request_ticket_validation": "tickets.manage:request_validation",
    "request_human_review": "tickets.manage:request_human_review",
    "self_bootstrap_close": "tickets.manage:self_bootstrap_close",
    "self_bootstrap_start": "tickets.manage:self_bootstrap_start",
    "self_bootstrap_summary": "tickets.manage:self_bootstrap_summary",
    "list_code_repositories": "repositories.list:list",
    "inspect_code_repository": "repositories.inspect:inspect",
    "terminal_run": "terminal.run:run",
    "inspect_permissions": "kernel.permissions:inspect",
}
CHAT_ACTION_TO_COMMAND_ID: dict[str, str] = {
    "answer_only": "none",
    "list_employees": "employees.manage:list",
    "create_employee": "employees.manage:create",
    "edit_employee_profile": "employees.manage:update",
    "delete_employee": "employees.manage:delete",
    "list_skills": "assets.manage:list_skills",
    "create_skill": "assets.manage:create_skill",
    "assign_skill_to_employee": "assets.manage:assign_skill",
    "delete_skill": "assets.manage:delete_skill",
    "inspect_permissions": "kernel.permissions:inspect",
    "search_knowledge": "knowledge.search:search",
    "inspect_code_repository": "repositories.inspect:inspect",
    "implement_ticket": "runtime.external:repo_mutation",
    "create_ticket": "tickets.manage:create",
    "append_report": "tickets.manage:report",
    "record_validation": "tickets.manage:report",
    "record_failure": "tickets.manage:report",
    "request_validation": "tickets.manage:request_validation",
    "request_human_review": "tickets.manage:request_human_review",
    "self_bootstrap_close": "tickets.manage:self_bootstrap_close",
    "self_bootstrap_start": "tickets.manage:self_bootstrap_start",
    "self_bootstrap_summary": "tickets.manage:self_bootstrap_summary",
    "list_code_repositories": "repositories.list:list",
    "terminal_run": "terminal.run:run",
}
COMMAND_ID_TO_CHAT_ACTION: dict[str, str] = {
    "none": "answer_only",
    "employees.manage:list": "list_employees",
    "employees.manage:create": "create_employee",
    "employees.manage:update": "edit_employee_profile",
    "employees.manage:delete": "delete_employee",
    "assets.manage:list_skills": "list_skills",
    "assets.manage:create_skill": "create_skill",
    "assets.manage:assign_skill": "assign_skill_to_employee",
    "assets.manage:delete_skill": "delete_skill",
    "kernel.permissions:inspect": "inspect_permissions",
    "knowledge.search:search": "search_knowledge",
    "repositories.inspect:inspect": "inspect_code_repository",
    "runtime.external:repo_mutation": "implement_ticket",
    "tickets.manage:create": "create_ticket",
    "tickets.manage:report": "append_report",
    "tickets.manage:request_validation": "request_validation",
    "tickets.manage:request_human_review": "request_human_review",
    "tickets.manage:self_bootstrap_close": "self_bootstrap_close",
    "tickets.manage:self_bootstrap_start": "self_bootstrap_start",
    "tickets.manage:self_bootstrap_summary": "self_bootstrap_summary",
    "repositories.list:list": "list_code_repositories",
    "terminal.run:run": "terminal_run",
}


KERNEL_COMMAND_SPECS: dict[str, KernelCommandSpec] = {
    "employees.manage:list": KernelCommandSpec(
        id="employees.manage:list",
        capability="employees.manage",
        operation="list",
        permissions=("employees:read",),
        description="List local Employee workforce records.",
    ),
    "employees.manage:create": KernelCommandSpec(
        id="employees.manage:create",
        capability="employees.manage",
        operation="create",
        permissions=("employees:write",),
        description="Create an Employee workforce record.",
    ),
    "employees.manage:update": KernelCommandSpec(
        id="employees.manage:update",
        capability="employees.manage",
        operation="update",
        permissions=("employees:write",),
        description="Update an Employee profile.",
    ),
    "employees.manage:delete": KernelCommandSpec(
        id="employees.manage:delete",
        capability="employees.manage",
        operation="delete",
        permissions=("employees:delete",),
        risk="destructive",
        description="Delete a non-protected Employee profile.",
    ),
    "assets.manage:list_skills": KernelCommandSpec(
        id="assets.manage:list_skills",
        capability="assets.manage",
        operation="list_skills",
        permissions=("skills:read",),
        description="List local Skill assets.",
    ),
    "assets.manage:create_skill": KernelCommandSpec(
        id="assets.manage:create_skill",
        capability="assets.manage",
        operation="create_skill",
        permissions=("skills:write",),
        description="Create a Skill asset.",
    ),
    "assets.manage:assign_skill": KernelCommandSpec(
        id="assets.manage:assign_skill",
        capability="assets.manage",
        operation="assign_skill",
        permissions=("assets:assign", "employees:write", "skills:read"),
        description="Assign a Skill asset to an Employee.",
    ),
    "assets.manage:delete_skill": KernelCommandSpec(
        id="assets.manage:delete_skill",
        capability="assets.manage",
        operation="delete_skill",
        permissions=("skills:delete", "employees:write"),
        risk="destructive",
        description="Delete a Skill asset and detach it from Employees.",
    ),
    "knowledge.search:search": KernelCommandSpec(
        id="knowledge.search:search",
        capability="knowledge.search",
        operation="search",
        permissions=("knowledge:read",),
        description="Search local Knowledge.",
    ),
    "tickets.manage:create": KernelCommandSpec(
        id="tickets.manage:create",
        capability="tickets.manage",
        operation="create",
        permissions=("tickets:write",),
        description="Create and assign a Ticket.",
    ),
    "tickets.manage:list": KernelCommandSpec(
        id="tickets.manage:list",
        capability="tickets.manage",
        operation="list",
        permissions=("tickets:read",),
        description="List Tickets.",
    ),
    "tickets.manage:report": KernelCommandSpec(
        id="tickets.manage:report",
        capability="tickets.manage",
        operation="report",
        permissions=("tickets:write",),
        description="Append a report to a Ticket.",
    ),
    "tickets.manage:request_validation": KernelCommandSpec(
        id="tickets.manage:request_validation",
        capability="tickets.manage",
        operation="request_validation",
        permissions=("tickets:write",),
        description="Request PV or validator review for an existing Ticket.",
    ),
    "tickets.manage:request_human_review": KernelCommandSpec(
        id="tickets.manage:request_human_review",
        capability="tickets.manage",
        operation="request_human_review",
        permissions=("tickets:write",),
        description="Request human review for a blocked or high-risk Ticket.",
    ),
    "tickets.manage:self_bootstrap_close": KernelCommandSpec(
        id="tickets.manage:self_bootstrap_close",
        capability="tickets.manage",
        operation="self_bootstrap_close",
        permissions=("tickets:write",),
        description="Close a self-bootstrap Ticket with Clara learning summary and recall usefulness feedback.",
    ),
    "tickets.manage:self_bootstrap_summary": KernelCommandSpec(
        id="tickets.manage:self_bootstrap_summary",
        capability="tickets.manage",
        operation="self_bootstrap_summary",
        permissions=("tickets:read",),
        description="Summarize self-bootstrap learning facts from Tickets, evidence, and recalled assets.",
    ),
    "tickets.manage:self_bootstrap_start": KernelCommandSpec(
        id="tickets.manage:self_bootstrap_start",
        capability="tickets.manage",
        operation="self_bootstrap_start",
        permissions=("tickets:write",),
        description="Start a governed self-bootstrap improvement Ticket batch from current learning facts.",
    ),
    "repositories.list:list": KernelCommandSpec(
        id="repositories.list:list",
        capability="repositories.list",
        operation="list",
        permissions=("repositories:read",),
        description="List configured code repositories.",
    ),
    "repositories.inspect:inspect": KernelCommandSpec(
        id="repositories.inspect:inspect",
        capability="repositories.inspect",
        operation="inspect",
        permissions=("repositories:read", "repo:read"),
        description="Inspect configured repository text for Ticket evidence.",
    ),
    "terminal.run:run": KernelCommandSpec(
        id="terminal.run:run",
        capability="terminal.run",
        operation="run",
        permissions=("terminal:run",),
        risk="execution",
        streaming=True,
        description="Run an approved non-interactive terminal command as Ticket-bound evidence.",
    ),
    "kernel.permissions:inspect": KernelCommandSpec(
        id="kernel.permissions:inspect",
        capability="kernel.permissions",
        operation="inspect",
        permissions=("employees:read",),
        description="Inspect an Employee's effective Kernel permissions and command access.",
    ),
}
