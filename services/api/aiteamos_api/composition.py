"""
API Gateway — Composition Root (plan.md §1.5.1).

依赖注入容器：注册所有仓储实现、应用服务、事件总线。
按 Bounded Context 组装路由。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI

from aiteamos_knowledge.application.handlers import (
    AppendMemoryVersionHandler,
    ChangeLifecycleHandler,
    CreateMemoryEdgeHandler,
    CreateMemoryNodeHandler,
    DeprecateMemoryNodeHandler,
    MergeMemoryNodesHandler,
    RemoveMemoryEdgeHandler,
    UpdateMemoryContentHandler,
)
from aiteamos_knowledge.application.queries import (
    GetMemoryNodeDetailExecutor,
    ListMemoryNodesExecutor,
    SearchMemoryByKeywordExecutor,
)
from aiteamos_knowledge.application.recall_engine import (
    MemoryRecallEngine,
    RecallChannelOrchestrator,
)
from aiteamos_knowledge.infrastructure.recall_channels import (
    PgvectorTopKFetcher,
    SqlAssignedMemoryFetcher,
    SqlConflictChecker,
    SqlMemoryDetailFetcher,
    SqlRecallAuditLogger,
    SqlScopeMemoryFetcher,
)

from aiteamos_capability.application.handlers import (
    DeprecateSkillHandler,
    PublishSkillHandler,
    RegisterSkillHandler,
)
from aiteamos_capability.application.queries import (
    GetSkillDetailExecutor,
    ListSkillsExecutor,
)

from aiteamos_workforce.application.handlers import (
    AssignMemberToProjectHandler,
    AssignMemoryToMemberHandler,
    AssignSkillToMemberHandler,
    CreateDepartmentHandler,
    CreateMemberHandler,
    CreateProjectHandler,
    UpdateProjectHandler,
)
from aiteamos_workforce.application.queries import (
    ListDepartmentsExecutor,
    ListMembersExecutor,
    ListProjectsExecutor,
)

from aiteamos_execution.application.context_assembler import ContextAssembler
from aiteamos_execution.application.handlers import (
    AssignTaskHandler,
    CreateTaskHandler,
    StartRunHandler,
    SubmitDeliverableHandler,
    TransitionTaskHandler,
)
from aiteamos_execution.application.queries import (
    GetTaskDetailExecutor,
    ListTasksExecutor,
)
from aiteamos_execution.infrastructure.repository import SqlSnapshotRepository

from aiteamos_shared.outbox import OutboxWriter
from aiteamos_knowledge.infrastructure.repository import (
    PostgresMemoryEdgeRepository,
    PostgresMemoryNodeRepository,
)
from aiteamos_knowledge.infrastructure.event_publisher import KnowledgeEventPublisher
from aiteamos_capability.infrastructure.repository import PostgresSkillRepository
from aiteamos_capability.infrastructure.event_publisher import CapabilityEventPublisher
from aiteamos_workforce.infrastructure.repository import (
    PostgresDepartmentRepository,
    PostgresMemberRepository,
    PostgresProjectRepository,
)
from aiteamos_workforce.infrastructure.event_publisher import WorkforceEventPublisher
from aiteamos_execution.infrastructure.repository import PostgresTaskRepository
from aiteamos_execution.infrastructure.event_publisher import ExecutionEventPublisher

from .acl_bridges import RecallEngineKnowledgeACL, SqlCapabilityACL
from .command import memory_commands, member_commands, skill_commands, task_commands, runtime_commands, delete_routes
from .read import member_routes, memory_routes, metrics_routes, skill_routes, task_routes, runtime_routes

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Simple service container for dependency injection.

    In production, repositories would be backed by real PostgreSQL connections.
    For testing, mock implementations can be injected.
    """

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}

    def register(self, name: str, service: Any) -> None:
        self._services[name] = service

    def get(self, name: str) -> Any:
        return self._services.get(name)


def build_container(container: ServiceContainer, db: Any) -> None:
    """Instantiate all repositories, publishers, handlers and executors.

    Call this after creating the DatabasePool and before register_routes().
    The *db* object (DatabasePool) also serves as the transaction manager
    since it exposes a ``transaction()`` context manager.
    """
    outbox_writer = OutboxWriter()

    # -- Knowledge context --
    memory_node_repo = PostgresMemoryNodeRepository(db=db)
    memory_edge_repo = PostgresMemoryEdgeRepository(db=db)
    knowledge_pub = KnowledgeEventPublisher(outbox_writer=outbox_writer)

    container.register("memory_create_handler", CreateMemoryNodeHandler(
        node_repo=memory_node_repo, tx_manager=db, event_publisher=knowledge_pub))
    container.register("memory_update_handler", UpdateMemoryContentHandler(
        node_repo=memory_node_repo, tx_manager=db, event_publisher=knowledge_pub))
    container.register("memory_version_handler", AppendMemoryVersionHandler(
        node_repo=memory_node_repo, tx_manager=db, event_publisher=knowledge_pub))
    container.register("memory_lifecycle_handler", ChangeLifecycleHandler(
        node_repo=memory_node_repo, tx_manager=db, event_publisher=knowledge_pub))
    container.register("memory_edge_handler", CreateMemoryEdgeHandler(
        edge_repo=memory_edge_repo, tx_manager=db, event_publisher=knowledge_pub))
    container.register("memory_remove_edge_handler", RemoveMemoryEdgeHandler(
        edge_repo=memory_edge_repo, tx_manager=db, event_publisher=knowledge_pub))
    container.register("memory_deprecate_handler", DeprecateMemoryNodeHandler(
        node_repo=memory_node_repo, tx_manager=db, event_publisher=knowledge_pub))
    container.register("memory_merge_handler", MergeMemoryNodesHandler(
        node_repo=memory_node_repo, tx_manager=db, event_publisher=knowledge_pub))

    # Store db reference for metrics routes
    container.register("db", db)

    container.register("memory_list_executor", ListMemoryNodesExecutor(read_repo=memory_node_repo))
    container.register("memory_detail_executor", GetMemoryNodeDetailExecutor(read_repo=memory_node_repo))
    container.register("memory_search_executor", SearchMemoryByKeywordExecutor(read_repo=memory_node_repo))

    # -- Knowledge: Reflection Pipeline (H4) + Review → Memory Bridge (H5) --
    from aiteamos_knowledge.application.extraction import MemoryReviewQueue, ReflectionEngine
    from aiteamos_knowledge.application.reflection_consumer import ReflectionConsumer
    from aiteamos_knowledge.application.review_extractor import ReviewMemoryExtractor

    reflection_engine = ReflectionEngine(
        memory_repo=memory_node_repo, tx_manager=db, event_publisher=knowledge_pub,
    )
    container.register("reflection_consumer", ReflectionConsumer(
        engine=reflection_engine, db=db))
    container.register("review_memory_extractor", ReviewMemoryExtractor(
        memory_repo=memory_node_repo, tx_manager=db,
        event_publisher=knowledge_pub, db=db))

    # Register memory_node_repo and MemoryReviewQueue for proposal management
    container.register("memory_node_repo", memory_node_repo)
    container.register("memory_review_queue", MemoryReviewQueue(
        memory_repo=memory_node_repo, tx_manager=db, event_publisher=knowledge_pub,
    ))

    # -- Capability context --
    skill_repo = PostgresSkillRepository(db=db)
    capability_pub = CapabilityEventPublisher(outbox_writer=outbox_writer)

    container.register("skill_register_handler", RegisterSkillHandler(
        skill_repo=skill_repo, tx_manager=db, event_publisher=capability_pub))
    container.register("skill_publish_handler", PublishSkillHandler(
        skill_repo=skill_repo, tx_manager=db, event_publisher=capability_pub))
    container.register("skill_deprecate_handler", DeprecateSkillHandler(
        skill_repo=skill_repo, tx_manager=db, event_publisher=capability_pub))

    container.register("skill_list_executor", ListSkillsExecutor(read_repo=skill_repo))
    container.register("skill_detail_executor", GetSkillDetailExecutor(read_repo=skill_repo))

    # -- Workforce context --
    dept_repo = PostgresDepartmentRepository(db=db)
    member_repo = PostgresMemberRepository(db=db)
    project_repo = PostgresProjectRepository(db=db)
    workforce_pub = WorkforceEventPublisher(outbox_writer=outbox_writer)

    container.register("member_create_handler", CreateMemberHandler(
        repo=member_repo, tx_manager=db, event_publisher=workforce_pub))
    container.register("department_create_handler", CreateDepartmentHandler(
        repo=dept_repo, tx_manager=db, event_publisher=workforce_pub))
    container.register("project_create_handler", CreateProjectHandler(
        repo=project_repo, tx_manager=db, event_publisher=workforce_pub))
    container.register("project_update_handler", UpdateProjectHandler(
        repo=project_repo, tx_manager=db, event_publisher=workforce_pub))
    container.register("assign_member_handler", AssignMemberToProjectHandler(
        repo=project_repo, tx_manager=db, event_publisher=workforce_pub))
    container.register("assign_skill_handler", AssignSkillToMemberHandler(
        repo=member_repo, tx_manager=db, event_publisher=workforce_pub))
    container.register("assign_memory_handler", AssignMemoryToMemberHandler(
        repo=member_repo, tx_manager=db, event_publisher=workforce_pub))

    container.register("members_executor", ListMembersExecutor(read_repo=member_repo))
    container.register("departments_executor", ListDepartmentsExecutor(read_repo=dept_repo))
    container.register("projects_executor", ListProjectsExecutor(read_repo=project_repo))
    container.register("member_repo", member_repo)
    container.register("project_repo", project_repo)

    # -- Execution context --
    task_repo = PostgresTaskRepository(db=db)
    execution_pub = ExecutionEventPublisher(outbox_writer=outbox_writer)

    container.register("task_create_handler", CreateTaskHandler(
        task_repo=task_repo, tx_manager=db, event_publisher=execution_pub))
    container.register("task_assign_handler", AssignTaskHandler(
        task_repo=task_repo, tx_manager=db, event_publisher=execution_pub))
    container.register("task_start_handler", StartRunHandler(
        task_repo=task_repo, tx_manager=db, event_publisher=execution_pub))
    container.register("task_submit_handler", SubmitDeliverableHandler(
        task_repo=task_repo, tx_manager=db, event_publisher=execution_pub))
    container.register("task_transition_handler", TransitionTaskHandler(
        task_repo=task_repo, tx_manager=db, event_publisher=execution_pub))

    container.register("task_list_executor", ListTasksExecutor(read_repo=task_repo))
    container.register("task_detail_executor", GetTaskDetailExecutor(read_repo=task_repo))
    container.register("execution_event_publisher", execution_pub)

    # -- Governance context --
    from aiteamos_governance.infrastructure.repository import (
        PostgresReviewCaseRepository,
        PostgresConflictCaseRepository,
    )
    from aiteamos_governance.application.services import (
        ConflictService,
        ReviewService,
    )
    review_repo = PostgresReviewCaseRepository(db=db)
    conflict_repo = PostgresConflictCaseRepository(db=db)
    container.register("review_repo", review_repo)
    container.register("conflict_repo", conflict_repo)

    # Governance event publisher (shares outbox writer)
    from aiteamos_governance.domain.events import (
        ConflictDetected,
        ConflictResolved,
        ReviewCaseCreated,
        ReviewDecisionMade,
    )

    class GovernanceEventPublisher:
        """Lightweight publisher that writes governance events to outbox."""
        def __init__(self, outbox_writer: OutboxWriter):
            self._writer = outbox_writer
        async def publish_events(self, events: list, *, partition_key: str, tx: Any) -> None:
            for event in events:
                await self._writer.write(event, partition_key=partition_key, tx=tx)

    gov_publisher = GovernanceEventPublisher(outbox_writer=outbox_writer)
    review_service = ReviewService(
        review_repo=review_repo, tx_manager=db, event_publisher=gov_publisher,
    )
    conflict_service = ConflictService(
        conflict_repo=conflict_repo, tx_manager=db, event_publisher=gov_publisher,
    )
    container.register("review_service", review_service)
    container.register("conflict_service", conflict_service)

    logger.info("All handlers and executors registered")


def register_routes(app: FastAPI, container: ServiceContainer) -> None:
    """Register all API routes with their executors/handlers from the container."""

    # --- Read routes ---
    memory_list_exec = container.get("memory_list_executor")
    memory_detail_exec = container.get("memory_detail_executor")
    memory_search_exec = container.get("memory_search_executor")
    if memory_list_exec and memory_detail_exec and memory_search_exec:
        memory_routes.init_routes(
            list_executor=memory_list_exec,
            detail_executor=memory_detail_exec,
            search_executor=memory_search_exec,
            db=container.get("db"),
        )

    skill_list_exec = container.get("skill_list_executor")
    skill_detail_exec = container.get("skill_detail_executor")
    if skill_list_exec and skill_detail_exec:
        skill_routes.init_routes(
            list_executor=skill_list_exec,
            detail_executor=skill_detail_exec,
        )

    members_exec = container.get("members_executor")
    departments_exec = container.get("departments_executor")
    projects_exec = container.get("projects_executor")
    member_detail_repo = container.get("member_repo")
    project_detail_repo = container.get("project_repo")
    if members_exec and departments_exec and projects_exec:
        member_routes.init_routes(
            members_executor=members_exec,
            departments_executor=departments_exec,
            projects_executor=projects_exec,
            member_detail_repo=member_detail_repo,
            project_detail_repo=project_detail_repo,
            db=container.get("db"),
        )

    # --- Write routes ---
    memory_create_handler = container.get("memory_create_handler")
    memory_update_handler = container.get("memory_update_handler")
    memory_version_handler = container.get("memory_version_handler")
    memory_lifecycle_handler = container.get("memory_lifecycle_handler")
    memory_edge_handler = container.get("memory_edge_handler")
    memory_remove_edge_handler = container.get("memory_remove_edge_handler")
    memory_deprecate_handler = container.get("memory_deprecate_handler")
    memory_merge_handler = container.get("memory_merge_handler")
    if all([memory_create_handler, memory_update_handler, memory_version_handler,
            memory_lifecycle_handler, memory_edge_handler]):
        memory_commands.init_routes(
            create_handler=memory_create_handler,
            update_handler=memory_update_handler,
            version_handler=memory_version_handler,
            lifecycle_handler=memory_lifecycle_handler,
            edge_handler=memory_edge_handler,
            remove_edge_handler=memory_remove_edge_handler,
            deprecate_handler=memory_deprecate_handler,
            merge_handler=memory_merge_handler,
        )

    skill_register_handler = container.get("skill_register_handler")
    skill_publish_handler = container.get("skill_publish_handler")
    skill_deprecate_handler = container.get("skill_deprecate_handler")
    if all([skill_register_handler, skill_publish_handler, skill_deprecate_handler]):
        skill_commands.init_routes(
            register_handler=skill_register_handler,
            publish_handler=skill_publish_handler,
            deprecate_handler=skill_deprecate_handler,
        )

    member_create_handler = container.get("member_create_handler")
    department_create_handler = container.get("department_create_handler")
    project_create_handler = container.get("project_create_handler")
    project_update_handler = container.get("project_update_handler")
    assign_member_handler = container.get("assign_member_handler")
    assign_skill_handler = container.get("assign_skill_handler")
    assign_memory_handler = container.get("assign_memory_handler")
    if all([member_create_handler, department_create_handler, project_create_handler,
            project_update_handler, assign_member_handler, assign_skill_handler, assign_memory_handler]):
        member_commands.init_routes(
            create_member_handler=member_create_handler,
            create_department_handler=department_create_handler,
            create_project_handler=project_create_handler,
            update_project_handler=project_update_handler,
            assign_member_handler=assign_member_handler,
            assign_skill_handler=assign_skill_handler,
            assign_memory_handler=assign_memory_handler,
            db=container.get("db"),
        )

    # --- Task routes ---
    task_list_exec = container.get("task_list_executor")
    task_detail_exec = container.get("task_detail_executor")
    if task_list_exec and task_detail_exec:
        task_routes.init_routes(
            list_executor=task_list_exec,
            detail_executor=task_detail_exec,
        )

    task_create_handler = container.get("task_create_handler")
    task_assign_handler = container.get("task_assign_handler")
    task_start_handler = container.get("task_start_handler")
    task_submit_handler = container.get("task_submit_handler")
    task_transition_handler = container.get("task_transition_handler")
    if all([task_create_handler, task_assign_handler, task_start_handler,
            task_submit_handler, task_transition_handler]):
        task_commands.init_routes(
            create_handler=task_create_handler,
            assign_handler=task_assign_handler,
            start_handler=task_start_handler,
            submit_handler=task_submit_handler,
            transition_handler=task_transition_handler,
        )

    # --- Metrics routes ---
    db_pool = container.get("db")
    if db_pool:
        runtime_routes.init_routes(db=db_pool)
        runtime_commands.init_routes(db=db_pool)
        metrics_routes.init_routes(db=db_pool)
        delete_routes.init_routes(db=db_pool)

    # --- Governance routes ---
    from .read import governance_routes
    from .command import governance_commands

    review_repo = container.get("review_repo")
    conflict_repo = container.get("conflict_repo")
    review_service = container.get("review_service")
    conflict_service = container.get("conflict_service")
    if review_repo and conflict_repo:
        governance_routes.init_routes(review_repo=review_repo, conflict_repo=conflict_repo)
    if review_service and conflict_service:
        governance_commands.init_routes(
            review_service=review_service, conflict_service=conflict_service,
        )

    # Include routers
    app.include_router(memory_routes.router)
    app.include_router(skill_routes.router)
    app.include_router(member_routes.router)
    app.include_router(task_routes.router)
    app.include_router(runtime_routes.router)
    app.include_router(memory_commands.router)
    app.include_router(skill_commands.router)
    app.include_router(member_commands.router)
    app.include_router(task_commands.router)
    app.include_router(runtime_commands.router)
    app.include_router(metrics_routes.router)
    app.include_router(governance_routes.router)
    app.include_router(governance_commands.router)
    app.include_router(delete_routes.router)

    logger.info("All API routes registered")


def build_recall_and_assembler(
    container: ServiceContainer, *, db: Any, tx_manager: Any, event_publisher: Any
) -> None:
    """构建 Recall Engine + ACL Bridges + Context Assembler，注册到容器。

    调用时机：在 DB pool 创建后、路由注册前。
    """
    # -- Recall channel fetchers (SQL) --
    assigned_fetcher = SqlAssignedMemoryFetcher(db=db)
    scope_fetcher = SqlScopeMemoryFetcher(db=db)
    vector_fetcher = PgvectorTopKFetcher(db=db)
    detail_fetcher = SqlMemoryDetailFetcher(db=db)
    audit_logger = SqlRecallAuditLogger(db=db)
    conflict_checker = SqlConflictChecker(db=db)

    # Graph fetcher: SQL graph store backed by memory_edge table
    from aiteamos_knowledge.application.graph_projection import GraphTraversalChannel
    from aiteamos_knowledge.infrastructure.graph_store import SqlGraphStore

    graph_store = container.get("graph_store") or SqlGraphStore(db=db)
    graph_fetcher = GraphTraversalChannel(graph_store=graph_store)

    # -- Recall engine --
    orchestrator = RecallChannelOrchestrator(
        assigned_fetcher=assigned_fetcher,
        scope_fetcher=scope_fetcher,
        vector_fetcher=vector_fetcher,
        graph_fetcher=graph_fetcher,
    )
    recall_engine = MemoryRecallEngine(
        channel_orchestrator=orchestrator,
        detail_fetcher=detail_fetcher,
        audit_logger=audit_logger,
        conflict_checker=conflict_checker,
    )

    # -- ACL bridges --
    knowledge_acl = RecallEngineKnowledgeACL(recall_engine=recall_engine)
    capability_acl = SqlCapabilityACL(db=db)

    # -- Snapshot repository --
    snapshot_repo = SqlSnapshotRepository(db=db)

    # -- Context assembler --
    context_assembler = ContextAssembler(
        knowledge_acl=knowledge_acl,
        capability_acl=capability_acl,
        snapshot_repo=snapshot_repo,
        tx_manager=tx_manager,
        event_publisher=event_publisher,
    )

    # Register in container for handlers to use
    container.register("recall_engine", recall_engine)
    container.register("knowledge_acl", knowledge_acl)
    container.register("capability_acl", capability_acl)
    container.register("snapshot_repo", snapshot_repo)
    container.register("context_assembler", context_assembler)

    logger.info("Recall engine + Context Assembler wired")
