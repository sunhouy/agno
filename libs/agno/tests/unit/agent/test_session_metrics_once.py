"""Session metrics count a run's cumulative usage once, including pauses and checkpoints."""

import json
from typing import Any, AsyncIterator, Iterator, Optional

import pytest

from agno.agent import Agent
from agno.db.in_memory import InMemoryDb
from agno.db.sqlite import AsyncSqliteDb
from agno.metrics import MessageMetrics
from agno.models.base import Model
from agno.models.response import ModelResponse
from agno.tools.decorator import tool


@tool(requires_confirmation=True)
def finish(value: str) -> str:
    """Finish with the tool's answer.

    Args:
        value (str): The value to finish with.
    """
    return f"done: {value}"


@tool
def ping(value: str) -> str:
    """Echo the value back.

    Args:
        value (str): The value to echo.
    """
    return f"pong: {value}"


class ScriptedModel(Model):
    """Calls one tool and then answers, reporting 10 input / 5 output tokens per turn."""

    def __init__(self, tool_name: Optional[str] = None):
        super().__init__(id="scripted", name="scripted", provider="test")
        self.tool_name = tool_name
        self.turn = 0

    def _next(self) -> ModelResponse:
        self.turn += 1
        usage = MessageMetrics(input_tokens=10, output_tokens=5, total_tokens=15, cost=0.10)
        if self.tool_name is not None and self.turn == 1:
            return ModelResponse(
                role="assistant",
                tool_calls=[
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": self.tool_name, "arguments": json.dumps({"value": "x"})},
                    }
                ],
                response_usage=usage,
            )
        return ModelResponse(role="assistant", content="final", response_usage=usage)

    def invoke(self, *args: Any, **kwargs: Any) -> ModelResponse:
        return self._next()

    async def ainvoke(self, *args: Any, **kwargs: Any) -> ModelResponse:
        return self._next()

    def invoke_stream(self, *args: Any, **kwargs: Any) -> Iterator[ModelResponse]:
        yield self._next()

    async def ainvoke_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[ModelResponse]:
        yield self._next()

    def parse_args(self, *args: Any, **kwargs: Any) -> dict:
        return {}

    def _parse_provider_response(self, response: Any, **kwargs: Any) -> ModelResponse:
        return self._next()

    def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
        return self._next()


def _assert_usage_once(db: Any, session_id: str) -> None:
    session = db.get_session(session_id=session_id)
    metrics = session.session_data["session_metrics"]
    assert metrics["input_tokens"] == 20
    assert metrics["output_tokens"] == 10
    assert metrics["total_tokens"] == 30
    assert metrics["cost"] == pytest.approx(0.2)
    # The paused leg and the resume leg belong to the same model entry.
    model_entries = metrics["details"]["model"]
    assert len(model_entries) == 1
    assert model_entries[0]["total_tokens"] == 30


def test_pause_and_resume_count_usage_once():
    db = InMemoryDb()
    agent = Agent(model=ScriptedModel("finish"), tools=[finish], db=db, telemetry=False)

    paused = agent.run("go", session_id="session")
    for requirement in paused.requirements or []:
        if requirement.tool_execution is not None:
            requirement.tool_execution.confirmed = True

    resumed = agent.continue_run(run_id=paused.run_id, session_id="session", requirements=paused.requirements)
    assert resumed.metrics.total_tokens == 30
    _assert_usage_once(db, "session")


async def test_async_pause_and_resume_count_usage_once(tmp_path):
    db = AsyncSqliteDb(db_file=str(tmp_path / "sessions.db"))
    try:
        agent = Agent(model=ScriptedModel("finish"), tools=[finish], db=db, telemetry=False)

        paused = await agent.arun("go", session_id="session")
        for requirement in paused.requirements or []:
            if requirement.tool_execution is not None:
                requirement.tool_execution.confirmed = True

        resumed = await agent.acontinue_run(
            run_id=paused.run_id, session_id="session", requirements=paused.requirements
        )
        assert resumed.metrics.total_tokens == 30

        session = await db.get_session(session_id="session")
        metrics = session.session_data["session_metrics"]
        assert metrics["total_tokens"] == 30
        assert metrics["cost"] == pytest.approx(0.2)
        assert len(metrics["details"]["model"]) == 1
    finally:
        await db.close()


def test_tool_batch_checkpoints_count_usage_once():
    db = InMemoryDb()
    agent = Agent(
        model=ScriptedModel("ping"),
        tools=[ping],
        db=db,
        checkpoint="tool-batch",
        telemetry=False,
    )

    agent.run("go", session_id="session")
    _assert_usage_once(db, "session")


def test_separate_runs_still_add_up():
    db = InMemoryDb()
    agent = Agent(model=ScriptedModel(), db=db, telemetry=False)

    agent.run("first", session_id="session")
    agent.run("second", session_id="session")

    session = db.get_session(session_id="session")
    metrics = session.session_data["session_metrics"]
    assert metrics["input_tokens"] == 20
    assert metrics["output_tokens"] == 10
    assert metrics["total_tokens"] == 30
    assert metrics["cost"] == pytest.approx(0.2)
