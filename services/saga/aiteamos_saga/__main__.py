"""
Saga Worker 启动入口 (plan.md §2.3.1)。

生产环境使用 Temporal Worker:
    python -m aiteamos_saga

当前为骨架实现，Stage 2.3 聚焦于 Workflow 逻辑 + 测试。
Temporal 集成在后续 Stage 中完成。
"""

import logging

logger = logging.getLogger(__name__)


def main() -> None:
    """Saga Worker 入口 (骨架)。

    生产实现:
        import asyncio
        from temporalio.client import Client
        from temporalio.worker import Worker
        from .workflows.task_execution import TaskExecutionWorkflow
        from .activities import all_activities

        async def run():
            client = await Client.connect("localhost:7233")
            worker = Worker(
                client,
                task_queue="aiteamos-task-execution",
                workflows=[TaskExecutionWorkflow],
                activities=all_activities,
            )
            await worker.run()

        asyncio.run(run())
    """
    logger.info("Saga Worker starting (skeleton — Temporal integration pending)")
    logger.info("Task queue: aiteamos-task-execution")
    logger.info("Workflows: TaskExecutionWorkflow")


if __name__ == "__main__":
    main()
