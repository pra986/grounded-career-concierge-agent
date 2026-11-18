from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from career_twin.models import (
    KnowledgeGapRecord,
    LeadCaptureRecord,
    TwinChatResponse,
)

DEFAULT_PROFILE = (
    "Pranil Deshmukh is an AI & Agentic Systems Engineer specializing in "
    "Python, OpenAI function calling, SQLite persistence, and pytest."
)


class CareerConciergeEngine:
    """Grounded career digital twin with SQLite-first persistence and bounded tool loops."""

    def __init__(
        self,
        name: str = "Pranil Deshmukh",
        profile_text: str = DEFAULT_PROFILE,
        db_path: str | Path = "career_concierge.db",
        max_tool_rounds: int = 5,
        llm_client: Any = None,
        pushover_sender: Optional[Callable[[str], None]] = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self.name = name
        self.profile_text = profile_text
        self.db_path = str(db_path)
        self.max_tool_rounds = max_tool_rounds
        self.model = model
        self._client = llm_client
        self._pushover_sender = pushover_sender or self._default_pushover_sender
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    name TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS unknown_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _default_pushover_sender(self, message: str) -> None:
        token = os.getenv("PUSHOVER_TOKEN")
        user = os.getenv("PUSHOVER_USER")
        if not token or not user:
            return
        resp = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token": token, "user": user, "message": message},
            timeout=5,
        )
        resp.raise_for_status()

    def _notify_after_persist(self, message: str, created_at: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO pending_notifications (message, status, created_at) VALUES (?, 'pending', ?)",
                (message, created_at),
            )
            notif_id = cur.lastrowid
            conn.commit()
        try:
            self._pushover_sender(message)
        except Exception:
            return False
        with self._connect() as conn:
            conn.execute(
                "UPDATE pending_notifications SET status = 'sent' WHERE id = ?",
                (notif_id,),
            )
            conn.commit()
        return True

    def record_user_details(
        self, email: str, name: str = "Not provided", notes: str = "Not provided"
    ) -> Dict[str, Any]:
        record = LeadCaptureRecord(email=email, name=name, notes=notes)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO leads (email, name, notes, created_at) VALUES (?, ?, ?, ?)",
                (record.email, record.name, record.notes, record.created_at),
            )
            conn.commit()
        notified = self._notify_after_persist(
            f"Lead from {record.name} ({record.email}): {record.notes}",
            record.created_at,
        )
        return {"recorded": "ok", "lead": record.model_dump(), "notified": notified}

    def record_unknown_question(self, question: str) -> Dict[str, Any]:
        record = KnowledgeGapRecord(question=question)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO unknown_questions (question, created_at) VALUES (?, ?)",
                (record.question, record.created_at),
            )
            conn.commit()
        notified = self._notify_after_persist(
            f"Unknown question logged: {record.question}",
            record.created_at,
        )
        return {"recorded": "ok", "gap": record.model_dump(), "notified": notified}

    def list_leads(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT email, name, notes, created_at FROM leads ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def list_unknown_questions(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT question, created_at FROM unknown_questions ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def system_prompt(self) -> str:
        return (
            f"You are acting as {self.name}'s grounded career concierge. "
            "Answer ONLY using the verified profile below. Never invent skills or credentials. "
            "If asked about anything not in the profile, call record_unknown_question. "
            "If a visitor shares contact details, call record_user_details.\n\n"
            f"Verified Profile:\n{self.profile_text}"
        )

    @staticmethod
    def tool_schemas() -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "record_user_details",
                    "description": "Persist recruiter or visitor contact details.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string"},
                            "name": {"type": "string"},
                            "notes": {"type": "string"},
                        },
                        "required": ["email"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_unknown_question",
                    "description": "Log a question that cannot be answered from the verified profile.",
                    "parameters": {
                        "type": "object",
                        "properties": {"question": {"type": "string"}},
                        "required": ["question"],
                    },
                },
            },
        ]

    def _dispatch_tool(
        self,
        name: str,
        args: Dict[str, Any],
        leads: List[LeadCaptureRecord],
        gaps: List[KnowledgeGapRecord],
    ) -> Dict[str, Any]:
        if name == "record_user_details":
            res = self.record_user_details(**args)
            leads.append(LeadCaptureRecord(**res["lead"]))
            return res
        if name == "record_unknown_question":
            res = self.record_unknown_question(**args)
            gaps.append(KnowledgeGapRecord(**res["gap"]))
            return res
        return {"error": f"Unknown tool: {name}"}

    def chat(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> TwinChatResponse:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()

        messages: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt()}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": message})

        tool_calls_made: List[str] = []
        recorded_leads: List[LeadCaptureRecord] = []
        recorded_gaps: List[KnowledgeGapRecord] = []

        for round_idx in range(1, self.max_tool_rounds + 1):
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tool_schemas(),
            )
            choice = response.choices[0]
            msg = choice.message
            tool_calls = getattr(msg, "tool_calls", None) or []

            if not tool_calls:
                return TwinChatResponse(
                    reply=msg.content or "",
                    tool_calls_made=tool_calls_made,
                    tool_rounds=round_idx - 1,
                    terminated_by_limit=False,
                    recorded_leads=recorded_leads,
                    recorded_unknown_questions=recorded_gaps,
                )

            messages.append(msg)
            for tc in tool_calls:
                fn_name = tc.function.name
                tool_calls_made.append(fn_name)
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result = self._dispatch_tool(fn_name, args, recorded_leads, recorded_gaps)
                except Exception as exc:
                    result = {"error": str(exc)}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    }
                )

        return TwinChatResponse(
            reply="Tool loop limit reached before final response.",
            tool_calls_made=tool_calls_made,
            tool_rounds=self.max_tool_rounds,
            terminated_by_limit=True,
            recorded_leads=recorded_leads,
            recorded_unknown_questions=recorded_gaps,
        )
