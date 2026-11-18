from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from dotenv import load_dotenv

from career_twin.engine import CareerConciergeEngine


class _DemoCompletionMessage:
    def __init__(self, content: str = "", tool_calls: Optional[list[Any]] = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class _DemoToolCallFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _DemoToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict[str, Any]) -> None:
        self.id = call_id
        self.function = _DemoToolCallFunction(name=name, arguments=json.dumps(arguments))


class _DemoChoice:
    def __init__(self, message: _DemoCompletionMessage, finish_reason: str) -> None:
        self.message = message
        self.finish_reason = finish_reason


class _DemoResponse:
    def __init__(self, message: _DemoCompletionMessage, finish_reason: str) -> None:
        self.choices = [_DemoChoice(message=message, finish_reason=finish_reason)]


class OfflineDemoLLMClient:
    """Deterministic offline stub so `career-twin --demo` runs without API keys."""

    def __init__(self) -> None:
        self.chat = self
        self.completions = self

    def create(self, *, messages: list[dict[str, Any]], **_: Any) -> _DemoResponse:
        last = messages[-1]
        if last.get("role") == "tool":
            return _DemoResponse(
                _DemoCompletionMessage(
                    content=(
                        "Thanks for reaching out! I have logged your inquiry and details "
                        "in the local SQLite store."
                    )
                ),
                finish_reason="stop",
            )

        user_text = str(last.get("content", "")).lower()
        if "@" in user_text:
            return _DemoResponse(
                _DemoCompletionMessage(
                    tool_calls=[
                        _DemoToolCall(
                            call_id="demo_lead_1",
                            name="record_user_details",
                            arguments={
                                "email": "recruiter@example.com",
                                "name": "Demo Recruiter",
                                "notes": "CLI demo outreach",
                            },
                        )
                    ]
                ),
                finish_reason="tool_calls",
            )

        if "rust" in user_text or "kubernetes" in user_text or "unknown" in user_text:
            return _DemoResponse(
                _DemoCompletionMessage(
                    tool_calls=[
                        _DemoToolCall(
                            call_id="demo_gap_1",
                            name="record_unknown_question",
                            arguments={"question": str(last.get("content", ""))},
                        )
                    ]
                ),
                finish_reason="tool_calls",
            )

        return _DemoResponse(
            _DemoCompletionMessage(
                content=(
                    "Hello! I am Pranil Deshmukh's grounded Career Concierge. "
                    "Ask about Pranil's engineering background or share your email to connect."
                )
            ),
            finish_reason="stop",
        )


def _build_llm_client(demo: bool) -> Any:
    if demo or not os.getenv("OPENAI_API_KEY"):
        return OfflineDemoLLMClient()
    from openai import OpenAI

    return OpenAI()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="career-twin",
        description="CLI entrypoint for the Grounded Career Concierge Agent.",
    )
    parser.add_argument(
        "--db",
        default="career_concierge.db",
        help="Path to the SQLite persistence database (default: career_concierge.db).",
    )
    parser.add_argument(
        "--name",
        default="Pranil Deshmukh",
        help="Persona display name (default: Pranil Deshmukh).",
    )
    parser.add_argument(
        "--message",
        "-m",
        help="Single user message to send non-interactively.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run a self-contained offline demonstration sequence.",
    )
    return parser


def run_demo(engine: CareerConciergeEngine) -> int:
    sample_prompts = [
        "Hi, what does Pranil work on?",
        "Does Pranil have production Rust kernel experience?",
        "Please connect me at recruiter@example.com for a backend role.",
    ]
    for prompt in sample_prompts:
        result = engine.chat(prompt)
        print(f"USER: {prompt}")
        print(f"TWIN: {result.reply}")
        print(f"TOOLS: {result.tool_calls_executed} | ROUNDS: {result.tool_rounds}")
        print("-" * 60)

    print(f"Stored leads: {len(engine.list_leads())}")
    print(f"Stored unknown questions: {len(engine.list_unknown_questions())}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    load_dotenv(override=False)
    args = build_parser().parse_args(argv)
    llm_client = _build_llm_client(demo=args.demo)
    engine = CareerConciergeEngine(
        name=args.name,
        db_path=Path(args.db),
        llm_client=llm_client,
    )

    if args.demo:
        return run_demo(engine)

    if args.message:
        result = engine.chat(args.message)
        print(result.reply)
        return 0

    print(f"Career Concierge CLI ready for {args.name}. Type 'exit' or 'quit' to stop.")
    history: list[dict[str, str]] = []
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input or user_input.lower() in {"exit", "quit"}:
            break
        result = engine.chat(user_input, history=history)
        print(f"Twin: {result.reply}")
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": result.reply})
    return 0


if __name__ == "__main__":
    sys.exit(main())
