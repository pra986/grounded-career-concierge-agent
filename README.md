# grounded-career-concierge-agent

Project 17: Function-calling career digital twin backed by durable SQLite lead capture, unknown-question logging, Pushover outage resilience, and bounded tool loops.

## Architecture

The career digital twin serves as a grounded conversational concierge over a candidate's verified profile (CV, LinkedIn summary, and project portfolio). Every interaction runs through a deterministic, testable orchestration engine (`career_twin/engine.py`):

- **Profile Grounding Layer**: Loads verified career facts and enforces strict abstention when a question falls outside documented experience.
- **Bounded Tool-Calling Loop**: Executes model tool requests (`record_user_details`, `record_unknown_question`) up to a hard `max_tool_rounds` ceiling to prevent infinite recursion or runaway API spend.
- **Durable SQLite Persistence**: Stores captured leads (`leads` table) and unanswered questions (`unknown_questions` table) in SQLite with transactional commits and notification delivery status tracking.
- **Pushover Outage Resilience**: Dispatches real-time alerts via Pushover with configurable timeouts; if Pushover is unreachable or returns an error, the event is durably queued in SQLite (`pending_notifications`) for retry without losing lead data or crashing the chat turn.
- **Gradio & CLI Interfaces**: Exposes both an interactive CLI demo (`career_twin/cli.py`) and a Gradio-compatible chat handler.

## 6-Stage Workflow

1. **Query Intake & Context Grounding**: Receives visitor prompt and attaches verified profile context and conversation history.
2. **Bounded Function-Calling Loop**: Invokes the LLM/tool-router up to `max_tool_rounds` (default `5`); rejects or halts loops exceeding the bound.
3. **Lead Capture (`record_user_details`)**: Validates visitor email/name/notes and persists a `LeadRecord` to SQLite.
4. **Unknown-Question Logging (`record_unknown_question`)**: Logs any out-of-scope or unanswerable question to SQLite for profile gap analysis.
5. **Outage-Resilient Pushover Dispatch**: Sends Pushover notification; on HTTP/network failure, marks `notification_sent=False` and records failure reason in SQLite for replay.
6. **Grounded Response & Audit Receipt**: Returns `ConciergeResponse` containing the assistant reply, tool trace, persistence IDs, and loop-bound status.

## Data Contract

Defined in `career_twin/models.py` using Pydantic v2:

- `AgentConfig`: `max_tool_rounds: int = 5`, `db_path: str = "career_twin.db"`, `pushover_timeout_sec: float = 5.0`
- `LeadRecord`: `lead_id`, `email`, `name`, `notes`, `created_at`, `notification_sent`
- `UnknownQuestionRecord`: `question_id`, `question`, `context`, `created_at`, `notification_sent`
- `ToolCallTrace`: `round_index`, `tool_name`, `arguments`, `status`, `error`
- `ConciergeResponse`: `reply`, `tool_traces`, `rounds_used`, `loop_bound_hit`, `lead_captured`, `unknown_logged`

## Production Controls

- **Bounded Tool Loops**: Hard cap (`max_tool_rounds`) prevents infinite tool-call cycles; exceeding the bound returns a safe fallback message and sets `loop_bound_hit=True`.
- **Durable SQLite Storage**: Leads and unknown questions are committed to SQLite *before* external notification calls so no data is lost during third-party outages.
- **Pushover Outage Resilience**: Network timeouts, DNS errors, or non-200 responses from Pushover are caught gracefully and recorded without failing the user response.
- **Zero-Hallucination Policy**: Questions lacking profile evidence trigger `record_unknown_question` instead of fabricated claims.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pytest -v
python -m career_twin.cli
```

## Attribution

Inspired by and adapted from the pinned reference implementation in [`ed-donner/agents`](https://github.com/ed-donner/agents) (`1_foundations/twin`).
 Pushover outage resilience, and bounded tool loops.
