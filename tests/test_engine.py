from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from career_twin.engine import CareerConciergeEngine


class _FakeFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict[str, Any]) -> None:
        self.id = call_id
        self.function = _FakeFunction(name=name, arguments=json.dumps(arguments))


class _FakeMessage:
    def __init__(self, content: str = "", tool_calls: Optional[list[Any]] = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeChoice:
    def __init__(self, message: _FakeMessage, finish_reason: str) -> None:
        self.message = message
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, message: _FakeMessage, finish_reason: str) -> None:
        self.choices = [_FakeChoice(message=message, finish_reason=finish_reason)]


class _UnknownQuestionLLM:
    def __init__(self) -> None:
        self.chat = self
        self.completions = self
        self.calls = 0

    def create(self, **_: Any) -> _FakeResponse:
        self.calls += 1
        if self.calls == 1:
            return _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall(
                            call_id="call_gap_1",
                            name="record_unknown_question",
                            arguments={"question": "Do you have production COBOL experience?"},
                        )
                    ]
                ),
                finish_reason="tool_calls",
            )
        return _FakeResponse(
            _FakeMessage(content="I have logged your question about COBOL for follow-up."),
            finish_reason="stop",
        )


class _InfiniteToolLoopLLM:
    def __init__(self) -> None:
        self.chat = self
        self.completions = self
        self.calls = 0

    def create(self, **_: Any) -> _FakeResponse:
        self.calls += 1
        return _FakeResponse(
            _FakeMessage(
                tool_calls=[
                    _FakeToolCall(
                        call_id=f"loop_{self.calls}",
                        name="record_unknown_question",
                        arguments={"question": f"Repeated unknown skill {self.calls}"},
                    )
                ]
            ),
            finish_reason="tool_calls",
        )


def test_unsupported_skill_logs_unknown_question(tmp_path: Path) -> None:
    db_file = tmp_path / "unknown_question.db"
    engine = CareerConciergeEngine(
        db_path=db_file,
        llm_client=_UnknownQuestionLLM(),
        pushover_sender=lambda _: None,
    )

    result = engine.chat("Do you have production COBOL experience?")

    assert "COBOL" in result.reply
    assert "record_unknown_question" in result.tool_calls_executed
    gaps = engine.list_unknown_questions()
    assert len(gaps) == 1
    assert "COBOL" in gaps[0].question


def test_malformed_email_is_rejected(tmp_path: Path) -> None:
    db_file = tmp_path / "bad_email.db"
    notifications: list[str] = []
    engine = CareerConciergeEngine(
        db_path=db_file,
        llm_client=_UnknownQuestionLLM(),
        pushover_sender=notifications.append,
    )

    try:
        outcome = engine.record_user_details(
            email="not-a-valid-email",
            name="Recruiter",
            notes="Should be rejected",
        )
    except ValueError:
        outcome = {"recorded": "rejected"}

    assert outcome.get("recorded") != "ok"
    assert engine.list_leads() == []
    assert notifications == []


def test_pushover_outage_preserves_sqlite_persistence(tmp_path: Path) -> None:
    db_file = tmp_path / "pushover_outage.db"

    def _failing_pushover(_: str) -> None:
        raise RuntimeError("Pushover HTTP 503 Service Unavailable")

    engine = CareerConciergeEngine(
        db_path=db_file,
        llm_client=_UnknownQuestionLLM(),
        pushover_sender=_failing_pushover,
    )

    lead_res = engine.record_user_details(
        email="hiring@example.com",
        name="Hiring Manager",
        notes="Staff AI Engineer role",
    )
    gap_res = engine.record_unknown_question("Do you have Zig kernel experience?")

    assert lead_res.get("recorded") == "ok"
    assert gap_res.get("recorded") == "ok"
    leads = engine.list_leads()
    gaps = engine.list_unknown_questions()
    assert len(leads) == 1
    assert leads[0].email == "hiring@example.com"
    assert len(gaps) == 1
    assert "Zig" in gaps[0].question


def test_tool_loop_terminates_at_max_iterations(tmp_path: Path) -> None:
    db_file = tmp_path / "tool_loop.db"
    loop_llm = _InfiniteToolLoopLLM()
    engine = CareerConciergeEngine(
        db_path=db_file,
        max_tool_rounds=3,
        llm_client=loop_llm,
        pushover_sender=lambda _: None,
    )

    result = engine.chat("Keep calling tools forever")

    assert result.tool_rounds <= 3
    assert loop_llm.calls <= 4
    assert isinstance(result.reply, str) and len(result.reply) > 0
