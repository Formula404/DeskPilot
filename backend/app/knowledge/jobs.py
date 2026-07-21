from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from backend.app.api.events import event_bus
from backend.app.knowledge.backup import create_full_backup
from backend.app.knowledge.compiler import compile_source
from backend.app.knowledge.indexer import rebuild_index
from backend.app.knowledge.lint import lint_knowledge, semantic_lint_knowledge
from backend.app.knowledge.profiles import active_profile_id, use_profile
from backend.app.knowledge.repository import (
    add_job_event,
    create_job,
    get_job,
    recover_interrupted_jobs,
    request_job_cancel,
    reset_job_for_retry,
    update_job,
    update_job_progress,
)

logger = logging.getLogger(__name__)
SUPPORTED_JOB_TYPES = {"compile", "lint", "semantic_lint", "rebuild_index", "full_backup"}


class KnowledgeJobError(RuntimeError):
    def __init__(self, message: str, code: str = "KNOWLEDGE_JOB_FAILED") -> None:
        super().__init__(message)
        self.code = code


class KnowledgeJobManager:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def _emit(self, job_id: str, event_type: str, progress: int, message: str, payload: dict | None = None) -> None:
        update_job_progress(job_id, progress)
        add_job_event(job_id, event_type, progress, message, payload)
        await event_bus.publish(
            f"knowledge.job.{event_type}",
            message,
            task_id=job_id,
            payload={"job_id": job_id, "progress": progress, **(payload or {})},
        )

    def enqueue(self, job_type: str, target_id: str | None = None, input_data: dict | None = None) -> dict[str, Any]:
        if job_type not in SUPPORTED_JOB_TYPES:
            raise KnowledgeJobError(f"不支持的后台任务类型：{job_type}", "KNOWLEDGE_JOB_TYPE_UNSUPPORTED")
        job_id = create_job(job_type, target_id, input_data or {}, profile_id=active_profile_id())
        add_job_event(job_id, "queued", 0, "任务已进入后台队列。")
        self.schedule(job_id)
        return get_job(job_id) or {"id": job_id, "status": "queued"}

    def schedule(self, job_id: str) -> None:
        current = self._tasks.get(job_id)
        if current and not current.done():
            return
        self._tasks[job_id] = asyncio.create_task(self._run(job_id))

    async def _execute(self, job: dict[str, Any]) -> dict[str, Any]:
        job_type = str(job["job_type"])
        input_data = job.get("input") or json.loads(job.get("input_json") or "{}")
        if job_type == "compile":
            if not job.get("target_id"):
                raise KnowledgeJobError("编译任务缺少 source_id。", "KNOWLEDGE_JOB_INPUT_INVALID")
            return await compile_source(
                str(job["target_id"]),
                input_data.get("target_note_id"),
                resume_job_id=str(job["id"]),
            )
        if job_type == "semantic_lint":
            return await semantic_lint_knowledge()
        if job_type == "lint":
            return await asyncio.to_thread(lint_knowledge)
        if job_type == "rebuild_index":
            return await asyncio.to_thread(rebuild_index)
        if job_type == "full_backup":
            path = await asyncio.to_thread(create_full_backup)
            return {"path": str(path)}
        raise KnowledgeJobError("后台任务类型无处理器。", "KNOWLEDGE_JOB_TYPE_UNSUPPORTED")

    async def _run(self, job_id: str) -> None:
        job = get_job(job_id)
        if not job or job["status"] != "queued":
            return
        profile_id = str(job.get("profile_id") or active_profile_id())
        try:
            with use_profile(profile_id):
                update_job(job_id, status="running")
                await self._emit(job_id, "started", 5, "后台任务已开始。")
                await self._emit(job_id, "progress", 20, "正在执行知识库操作。")
                result = await self._execute(get_job(job_id) or job)
                latest = get_job(job_id) or {}
                if latest.get("cancel_requested"):
                    raise asyncio.CancelledError
                # compile_source owns the richer committed/proposed terminal state.
                if job["job_type"] != "compile":
                    update_job(job_id, status="completed", result=result)
                await self._emit(job_id, "completed", 100, "后台任务已完成。", {"result": result})
        except asyncio.CancelledError:
            update_job(job_id, status="cancelled", error_code="KNOWLEDGE_JOB_CANCELLED", error_message="任务已由用户取消。")
            await self._emit(job_id, "cancelled", 100, "后台任务已取消。")
        except Exception as exc:
            logger.exception("Knowledge background job failed", extra={"job_id": job_id})
            update_job(job_id, status="failed", error_code=getattr(exc, "code", "KNOWLEDGE_JOB_FAILED"), error_message=str(exc))
            await self._emit(job_id, "failed", 100, f"后台任务失败：{exc}")
        finally:
            self._tasks.pop(job_id, None)

    async def cancel(self, job_id: str) -> bool:
        if not request_job_cancel(job_id):
            return False
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
        else:
            update_job(job_id, status="cancelled", error_code="KNOWLEDGE_JOB_CANCELLED", error_message="任务在执行前被取消。")
            await self._emit(job_id, "cancelled", 100, "后台任务已取消。")
        return True

    def retry(self, job_id: str) -> bool:
        if not reset_job_for_retry(job_id):
            return False
        add_job_event(job_id, "retried", 0, "失败任务已重新排队。")
        self.schedule(job_id)
        return True

    def recover(self) -> dict[str, Any]:
        result = recover_interrupted_jobs()
        for job in result["jobs"]:
            self.schedule(str(job["id"]))
        return result

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


knowledge_job_manager = KnowledgeJobManager()
