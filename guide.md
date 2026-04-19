# VoxEngine — private recruiter / interview notes

*(Not for public repo listing — keep local or in a private doc.)*

## One-liner pitch

**VoxEngine** is a backend platform that turns **appointment reminder text** into **phone calls**: TTS (Edge or OpenAI), campaign orchestration with **Celery**, optional **Twilio** telephony with **TwiML** bridging, **DNC** enforcement for compliance-minded workflows, **webhook** notifications, and **usage metering** with monthly-style quotas.

## What to emphasize in conversation

1. **Separation of concerns**: API layer vs **service layer** (TTS abstraction, campaign manager, telephony adapter) vs **async SQLAlchemy** persistence vs **background workers**.
2. **Operational realism**: env-driven config, Docker Compose with **Postgres + Redis + API + worker**, shared storage volume for generated audio.
3. **Compliance hooks**: DNC list, idempotent-ish Twilio status handling (avoid double-counting delivered/failed), explicit simulated mode when Twilio is not configured (useful for demos and CI).
4. **Extensibility**: swap TTS engines via `VoiceProfile.tts_engine`; add org-level tenancy later by scoping queries; add Alembic when moving beyond bootstrap `create_all`.

## Suggested live demo flow

1. Register (first user → admin) → create JWT.
2. `GET /api/voices/catalog/available` → pick Edge voice → `POST /api/voices`.
3. `POST /api/tts/generate` with short text → `GET .../audio`.
4. `POST /api/campaigns` with template `Hello {{name}}, your appointment is tomorrow.` and one recipient.
5. `POST .../start` with Celery worker running → observe **simulated** delivery if Twilio unset; check `/api/campaigns/{id}/progress`.

## Known simplifications (be honest)

- Table creation on startup instead of migrations.
- Twilio signature verification not implemented (called out in README).
- Rate limiting is configured but not wired as middleware (easy add with Redis).
- Global DNC list (not per-tenant); RBAC is basic (admin / operator / viewer).

## File map (memory aid)

- `app/core/config.py` — all env knobs.
- `app/services/tts_engine.py` — provider abstraction.
- `app/services/campaign_manager.py` — campaign + template + DNC.
- `app/tasks/tts_tasks.py` — worker-side TTS, call pipeline, webhook POST.

Use this doc to rehearse **architecture**, **tradeoffs**, and **next steps** without memorizing filenames in the interview.
