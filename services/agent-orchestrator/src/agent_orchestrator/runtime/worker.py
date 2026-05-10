from __future__ import annotations

import asyncio
import json
import logging
from builtins import BaseExceptionGroup
from typing import Any

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostClient, BifrostError
from agent_orchestrator.integrations.mcp.client import McpClientError
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.system_prompts import build_system_prompt
from agent_orchestrator.storage.models import Job
from agent_orchestrator.storage.repository import Repository

logger = logging.getLogger(__name__)


class WorkerService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: Repository,
        bifrost_client: BifrostClient,
        mcp_tool_catalog: McpToolCatalog,
        skill_registry: SkillRegistry,
    ):
        self._settings = settings
        self._repository = repository
        self._bifrost_client = bifrost_client
        self._mcp_tool_catalog = mcp_tool_catalog
        self._skill_registry = skill_registry
        self._stop_event = asyncio.Event()
        self.is_running = False

    async def run_forever(self) -> None:
        self.is_running = True
        try:
            while not self._stop_event.is_set():
                job = await self._repository.claim_next_job()
                if job is None:
                    await asyncio.sleep(self._settings.worker_poll_interval_seconds)
                    continue
                await self._run_job(job)
        finally:
            self.is_running = False

    async def stop(self) -> None:
        self._stop_event.set()

    async def _run_job(self, job: Job) -> None:
        if await self._repository.get_job_cancellation_requested(job.id):
            await self._repository.mark_job_cancelled(job.id, reason="cancelled before execution")
            return

        full_job = await self._repository.get_job(job.id)
        assert full_job is not None
        session = full_job.session
        prompt_run = full_job.prompt_run
        model_config = session.model_config
        if model_config is None:
            await self._repository.append_event(job.id, session.id, "failure", {"code": "missing_model_config"})
            await self._repository.mark_job_failed(
                job.id,
                error_code="missing_model_config",
                error_message="Session model configuration is required",
                retryable=False,
            )
            return

        try:
            system_prompt = build_system_prompt(self._skill_registry, session.skill_assignments)
            tool_definitions = await self._mcp_tool_catalog.list_session_tools(full_job.session.mcp_assignments)
            tools = self._mcp_tool_catalog.as_openai_tools(tool_definitions)
            tool_mapping = self._mcp_tool_catalog.as_mapping(tool_definitions)
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_run.prompt},
            ]
            await self._repository.append_event(job.id, session.id, "progress", {"status": "running"})

            for _ in range(self._settings.worker_max_tool_rounds):
                if await self._repository.get_job_cancellation_requested(job.id):
                    await self._repository.mark_job_cancelled(job.id, reason="cancelled during execution")
                    return

                response = await self._bifrost_client.chat_completion(
                    model_config.provider_id,
                    model_config.model_name,
                    messages,
                    tools,
                    model_config.gateway_options,
                    model_config.provider_options,
                )
                if response.content:
                    await self._repository.append_event(
                        job.id,
                        session.id,
                        "model_output",
                        {"text": response.content},
                    )

                if not response.tool_calls:
                    await self._repository.append_event(
                        job.id,
                        session.id,
                        "completion",
                        {"text": response.content},
                    )
                    await self._repository.mark_job_completed(job.id, response.content)
                    return

                assistant_message: dict[str, Any] = {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [],
                }
                messages.append(assistant_message)
                for tool_call in response.tool_calls:
                    if tool_call.name not in tool_mapping:
                        raise RuntimeError(f"Unknown tool requested: {tool_call.name}")
                    tool_definition = tool_mapping[tool_call.name]
                    assistant_message["tool_calls"].append(
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.name,
                                "arguments": json.dumps(tool_call.arguments),
                            },
                        }
                    )
                    await self._repository.append_event(
                        job.id,
                        session.id,
                        "tool_call",
                        {
                            "tool_call_id": tool_call.id,
                            "exposed_tool_name": tool_call.name,
                            "tool_name": tool_definition.actual_name,
                            "assignment": tool_definition.assignment_name,
                            "server_url": tool_definition.server_url,
                            "arguments": tool_call.arguments,
                        },
                    )
                    result = await self._mcp_tool_catalog.call_tool(tool_definition, tool_call.arguments)
                    await self._repository.append_event(
                        job.id,
                        session.id,
                        "tool_result",
                        {
                            "tool_call_id": tool_call.id,
                            "exposed_tool_name": tool_call.name,
                            "tool_name": tool_definition.actual_name,
                            "assignment": tool_definition.assignment_name,
                            "server_url": tool_definition.server_url,
                            "is_error": result.get("is_error", False),
                            "result": result,
                        },
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result),
                        }
                    )

            raise RuntimeError("tool round limit exceeded")
        except BifrostError as exc:
            await self._repository.append_event(
                job.id,
                session.id,
                "failure",
                {"code": exc.code, "message": str(exc), "retryable": exc.retryable},
            )
            await self._repository.mark_job_failed(
                job.id,
                error_code=exc.code,
                error_message=str(exc),
                retryable=exc.retryable,
            )
        except (McpClientError, RuntimeError, ValueError) as exc:
            logger.exception("Job %s failed", job.id)
            error_message = self._format_execution_error(exc)
            await self._repository.append_event(
                job.id,
                session.id,
                "failure",
                {"code": "execution_error", "message": error_message, "retryable": False},
            )
            await self._repository.mark_job_failed(
                job.id,
                error_code="execution_error",
                error_message=error_message,
                retryable=False,
            )

    def _format_execution_error(self, exc: Exception) -> str:
        if isinstance(exc, BaseExceptionGroup):
            nested_messages = [self._format_execution_error(item) for item in exc.exceptions]
            nested_messages = [message for message in nested_messages if message]
            if nested_messages:
                return nested_messages[0]
        return str(exc)
