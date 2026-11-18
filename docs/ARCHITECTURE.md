# Architecture — Grounded Career Concierge Agent

## Overview
`grounded-career-concierge-agent` is a function-calling career digital twin (`CareerConciergeEngine`) backed by durable SQLite persistence, strict profile grounding, and bounded tool execution.

## Core Components
1. **Verified Career Profile Grounding**
   - Every response is anchored to a verified candidate profile (`CareerProfile` / profile text).
   - When a user asks about a skill, role, or credential not present in the verified profile, the engine refuses to fabricate an answer and invokes `record_unknown_question`.

2. **Durable SQLite-First Persistence (`career_twin/engine.py`)**
   - `record_user_details(email, name, notes)` validates email format before persistence and writes to the `leads` table first.
   - `record_unknown_question(question)` writes to the `unknown_questions` table first.
   - Pushover notifications are enqueued in `pending_notifications` and dispatched *after* SQLite commit so network or API outages never drop captured leads or knowledge gaps.

3. **Bounded Tool-Calling Loop**
   - `CareerConciergeEngine.chat()` enforces `max_tool_rounds` (default `5`).
   - If the LLM/tool loop exceeds `max_tool_rounds`, execution terminates gracefully with a bounded-loop status rather than spinning indefinitely.

4. **Data Contracts (`career_twin/models.py`)**
   - `LeadCaptureRecord`: Validated lead contact payload (`email`, `name`, `notes`, `created_at`).
   - `KnowledgeGapRecord`: Logged unanswered/unsupported question (`question`, `created_at`).
   - `TwinChatResponse`: Structured response (`reply`, `tool_calls_made`, `tool_rounds`, `terminated_by_limit`, `recorded_leads`, `recorded_unknown_questions`).
