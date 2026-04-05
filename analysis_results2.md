# CalSync — Hidden Edge Cases (Deep Analysis)

---

## Edge Case 1 — Fail-Open FreeBusy Causes Silent Phantom Booking

**File**: [conflict_resolver.py L62-67](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/mcp_servers/calendar_mcp/conflict_resolver.py#L62-L67)

```python
except Exception as exc:
    logger.warning("check_slot_conflicts: FreeBusy API error (fail-open, treating as free): %s", exc)
    return []  # Fail-open: allow booking to proceed
```

**The issue**: If the Google Calendar FreeBusy API call throws any exception (network blip, quota hit, bad credentials, etc.), the conflict resolver returns an **empty conflict list**, treating the slot as free. The agent then proceeds to book the meeting unconditionally.

**Real scenario**: Google Calendar API goes briefly rate-limited. Every concurrent booking attempt sees `[]` conflicts → all proceed. A meeting gets double-booked, or a slot that conflicts for participants gets booked anyway.

**Risk**: 🔴 High — silent wrong booking with no user-visible error.

**Fix**: Change to fail-closed for the booking path. Return a sentinel like `[{"participant": "__API_ERROR__", "conflict_count": -1}]` that the caller can distinguish from a real free slot.

---

## Edge Case 2 — Race Condition: Two Concurrent Webhooks for Same Email

**Files**: [webhook.py L83-86](file:///d:/My%20Files/Ameya/Coding/COEP Inspiron/Calsync/ingestion/app/routers/webhook.py#L83-L86), [dedup_service.py L19-28](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/dedup_service.py#L19-L28)

**The issue**: The memory dedup backend is a plain `dict`. If two requests for the same email arrive within milliseconds (SendGrid often retries), there's a TOCTOU (time-of-check-time-of-use) window:

```
Thread A: check → not in dict → (context switch)
Thread B: check → not in dict → marks → proceeds
Thread A: marks → proceeds   ← both threads got in
```

FastAPI runs in an async event loop — typically no true thread parallelism unless running with multiple workers. But with **multiple Gunicorn workers** (common in production), each has its own memory store. The Redis/Supabase backends are atomic (`SET NX` / `409`), but memory backend has no distributed lock.

**Real scenario**: Gunicorn with 4 workers. Same webhook retry hits 2 workers simultaneously. Both pass dedup → both queue agent tasks → agent runs twice for same email → double availability request sent.

**Risk**: 🟠 Medium — in single-worker dev mode this is safe, but the `memory` backend is documented as the auto-fallback.

**Fix**: Add a comment in config/docs that `memory` backend must not be used with multiple workers. Or use `asyncio.Lock` for the memory path (only protects within one worker though).

---

## Edge Case 3 — Session Created Twice Under Concurrency (upsert gap)

**File**: [thread_state_service.py L67-90](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/thread_state_service.py#L67-L90)

```python
session_row = await self._get_session_by_thread(thread_id)
if not session_row:
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    await self._upsert_session_row(...)
```

**The issue**: `_get_session_by_thread` is a read, and `_upsert_session_row` is a separate write. If two concurrent agent runs for the same `thread_id` both see `None` from the read (race), they both generate a new `session_id` and both try to insert. The second insert may fail (primary key conflict) or succeed, leaving **two session rows for the same thread_id**.

**Real scenario**: Two participants reply to the same thread within seconds. Both emails arrive via IMAP poll simultaneously and agent tasks are spawned concurrently. Both see no session → both insert. Now `_get_session_by_thread` returns `limit=1` arbitrarily — one session is orphaned.

**Risk**: 🟠 Medium — `limit=1` masks the problem, but the orphaned session accumulates state that's never used.

**Fix**: Use a `ON CONFLICT (thread_id) DO NOTHING` upsert pattern on the Supabase sessions table, keyed by `thread_id` not `session_id`.

---

## Edge Case 4 — Outbound Dedup Permanently Blocks Legitimate Re-sends

**File**: [server.py L156-175](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/mcp_servers/gmail_mcp/server.py#L156-L175)

```python
intent = _subject_intent(req.subject)
if intent:
    existing = get_outbound_emails_for_session(req.session_id, intent)
    if existing:
        return {"status": "already_sent", ...}
```

**The issue**: The dedup check is `session_id + subject keyword`. There is **no TTL or per-round counter**. This means:

- Round 1: availability request sent → stored with intent `"available"`
- Round 2 (NO_OVERLAP resolved, new slots, same session): agent tries to send **another** availability request after the first booking attempt fails
- Dedup sees `session_id + "available"` already exists → **blocks the second availability request**

The session stays alive but the agent can never send another availability email for the same session. Participants never hear back.

**Risk**: 🔴 High for multi-round sessions. Every NO_OVERLAP recovery and every reminder follow-up is potentially blocked.

**Fix**: The dedup check needs to be per-round or per-agent-run, not per-session. One approach: include the `round_number` or a `slot_attempt_id` in the `session_id` field passed to the MCP, or use a timestamp window rather than a simple existence check.

---

## Edge Case 5 — Thread ID Sanitization Strips Valid Short IDs

**File**: [tools.py L50-51](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/tools.py#L50-L51)

```python
if not re.fullmatch(r"[A-Za-z0-9]{8,}", sanitized_thread_id):
    sanitized_thread_id = ""
```

**The issue**: Gmail thread IDs are alphanumeric hex strings, typically 16 characters. But this regex also rejects any thread ID with a **hyphen, underscore, or less than 8 chars**. The `thread_id` in early bootstrapping comes from `derive_thread_id(message_id, in_reply_to, references)` which normalizes RFC Message-IDs like `abc123@mail.example.com` — these contain `@` and `.` and would be stripped to `""`.

**Real scenario**: First email in a thread. `thread_id = derive_thread_id(message_id)` → value like `abc123def456@mail.gmail.com`. This gets passed to `send_gmail_message`. The sanitization strips it → reply goes as a new thread, breaking email threading.

**Risk**: 🟡 Low-Medium — RFC Message-IDs (used when Gmail thread ID isn't available) always fail this regex. All IMAP-originated emails will have their threading broken on first reply.

**Fix**: The comment says "RFC message-id values are not valid here" — which is correct for the Gmail API's `threadId` field. But the fix should be applied **earlier** in `derive_thread_id` or at ingestion, not silently at send time. Log a warning and document that `threadId` must be a real Gmail thread ID, not an RFC message-id.

---

## Edge Case 6 — Organizer Email Overwritten on Every Agent Run

**File**: [react_agent.py L355-356](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L355-L356)

```python
session.meeting_title = meeting_title
session.organizer_email = payload.from_email
```

**The issue**: `session.organizer_email` is **always overwritten** with `payload.from_email` — the sender of the **current** inbound email. If a participant (not the original organizer) replies, their email becomes the new `organizer_email`. This gets persisted.

**Real scenario**:
- Alice initiates: `organizer_email = alice@co.com` ✅
- Bob replies (availability): `organizer_email = bob@co.com` ❌ — now Bob is stored as the organizer
- Agent books the meeting listing Bob as organizer in Calendar

**Risk**: 🔴 High — affects all multi-participant threads. Calendar events will have wrong organizer, confirmation emails may address the wrong person.

**Fix**: Only set `session.organizer_email` on **session creation**, not on every run. The `get_or_create_session` already returns the stored `organizer_email` — just don't overwrite it:

```python
# Only set if not already stored
if not session.organizer_email:
    session.organizer_email = payload.from_email
```

---

## Edge Case 7 — Participant Pool Contaminated by Outbound Emails in thread_rows

**File**: [react_agent.py L366-372](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L366-L372)

```python
if thread_rows:
    thread_participants, thread_replied = _collect_participants_from_thread_rows(thread_rows, excluded)
    participant_pool = dedupe_emails(participant_pool + thread_participants)
    replied_pool = dedupe_emails(replied_pool + thread_replied)
```

And `_collect_participants_from_thread_rows` pulls `from_email` from **all rows** including those with `direction="OUTBOUND"`. CalSync's own outbound emails have `from_email = settings.CALSYNC_EMAIL`.

`excluded` at line 302 is:
```python
excluded = dedupe_emails([settings.gmail_sender_email or "", payload.from_email])
```

So CalSync's email IS in `excluded`, but only if `settings.gmail_sender_email` is set. If it's blank (misconfiguration), CalSync's own outbound `from_email` gets added to `participant_pool` and `replied_pool`. The agent could end up sending emails to itself.

**Additionally**, the `to_emails` of OUTBOUND rows contains the actual participants — these get added correctly. But the `from_email` of OUTBOUND rows is CalSync, which would be excluded if configured. If not excluded, CalSync appears in `replied_pool` → reduces `pending_participants` incorrectly.

**Risk**: 🟡 Medium — depends on configuration. If `GMAIL_SENDER_EMAIL` is not set, this is a real bug.

**Fix**: Filter `thread_rows` by `direction="INBOUND"` before passing to `_collect_participants_from_thread_rows`. Outbound rows should only contribute their `to_emails`, not `from_email`.

---

## Edge Case 8 — Confirmation Email Body Shows UTC, But System Prompt Says IST

**File**: [react_agent.py L559-561](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L559-L561)

```python
confirmation_body = (
    "Your meeting has been coordinated and added to the calendar. "
    f"Slot: {calendar_slot['start']} to {calendar_slot['end']} (UTC)."
)
```

**The issue**: The standalone `agent.py` system prompt (rule 6) says *"Show times in IST (UTC+5:30) in email bodies"*. But the `react_agent.py` hardcodes UTC timestamps directly into the confirmation email body. The booking confirmation will always show raw UTC strings like `2026-04-08T09:30:00Z`, not the human-friendly `3:00 PM IST` that the system prompt promises.

**Risk**: 🟡 Medium — UX issue. Participants receive confusing UTC timestamps instead of their local time.

**Fix**: Add a `_to_ist_display` utility:
```python
from datetime import timezone, timedelta
IST = timezone(timedelta(hours=5, minutes=30))

def _to_ist_display(utc_iso: str) -> str:
    dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    ist = dt.astimezone(IST)
    return ist.strftime("%B %d, %Y at %I:%M %p IST")
```

---

## Edge Case 9 — Reminder Double-Send on First AWAITING_REPLIES Transition

**File**: [react_agent.py L418-436](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L418-L436)

```python
if (
    session.status == "AWAITING_REPLIES"   # ← reads persisted status
    and pending_participants
    and _should_send_reminder(session.last_reminder_at, ...)
):
    # send reminder
```

**The issue**: `session.status` here is the **restored** status from the DB. On the very first reply from any participant (say Bob replies), the session is **still** `AWAITING_REPLIES` (not yet changed). `last_reminder_at` is `None` because no reminder was ever sent. `_should_send_reminder(None, ...)` returns `True`.

So on Bob's reply:
1. Agent sends an availability-request update (action = `SENT_AVAILABILITY_REQUEST`, triggered by Gemini)  
2. Then **immediately** sends a reminder to the still-pending participants

This means Bob's reply triggers both an acknowledgement email AND a reminder email in the same agent run. Participants receive: "Thanks for your reply, please share slot..." AND "Quick reminder: please reply..." in one shot.

**Risk**: 🟡 Medium — confusing UX, minor but noticeable in demos.

**Fix**: The reminder block should only fire when the **previous** session status was `AWAITING_REPLIES` **AND** the current incoming email is NOT a fresh availability request (i.e., not the originating email). Check `session.last_reminder_at is not None` as an additional gate, or only trigger when `action` was decided by Gemini (not when it's the initial request being sent for the first time).

---

## Edge Case 10 — NO_OVERLAP Override Fires Even When Gemini Picks NO_ACTION

**File**: [react_agent.py L345-353](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L345-L353)

```python
slot_from_analysis = analysis.get("slot") if isinstance(analysis.get("slot"), dict) else {}
if (
    session.status == "NO_OVERLAP"
    and slot_from_analysis.get("start_iso")
    and slot_from_analysis.get("end_iso")
    and action != "BOOKED_CALENDAR"
):
    action = "BOOKED_CALENDAR"
```

**The issue**: This override fires when `action != "BOOKED_CALENDAR"` — which includes `action == "NO_ACTION"`. If a participant in a `NO_OVERLAP` session sends an unrelated email ("hey, any updates?") that Gemini analyzes as `NO_ACTION`, but the email body happens to contain dates that Gemini extracts as a `slot` object, this override incorrectly **forces a booking attempt**.

**Real scenario**: Participant sends: "Hey, I was thinking November 15th would be a good time to reconnect." Gemini might extract `slot.start_iso` from this and return `NO_ACTION`. The override kicks in → agent attempts to book November 15th without asking others.

**Risk**: 🟠 Medium — wrong booking triggered by an ambiguous email.

**Fix**: Change the condition to only override `SENT_AVAILABILITY_REQUEST`, not `NO_ACTION`:
```python
and action == "SENT_AVAILABILITY_REQUEST"
```

---

## Edge Case 11 — `_record_sent_recipients` Misses `already_sent` Dedup Case

**File**: [react_agent.py L341-343](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L341-L343) + [tools.py L33](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/tools.py#L33)

```python
def _record_sent_recipients(outcome_status: str, recipients_list: list[str]) -> None:
    if outcome_status == "OK":
        sent_recipients.extend(recipients_list)
```

**The issue**: When the Gmail MCP deduplicates an outbound send (returns `{"status": "already_sent"}`), `_post_json` maps it as `status="OK"` because `response.raise_for_status()` passes (HTTP 200). So `_record_sent_recipients` adds those recipients to `sent_recipients`.

BUT — when Gmail MCP returns `{"status": "already_sent"}`, the email was **NOT actually sent** in this run. The `emails_sent_to` response falsely claims recipients were emailed.

**Risk**: 🟡 Low — observability gap, not a functional bug. But dashboards/logs will show emails as sent when they were silently skipped.

**Fix**: Check the JSON body, not just the HTTP status:
```python
# In _post_json or send_gmail_message:
payload = response.json()
actual_status = "SKIPPED" if payload.get("skipped") else "OK"
return ToolCallOutcome(name=tool_name, status=actual_status, payload=payload)
```

---

## Edge Case 12 — Supabase `_upsert_session_row` Loses `NO_OVERLAP` / `BOOKED` on HTTP Error

**File**: [thread_state_service.py L166-176](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/thread_state_service.py#L166-L176)

```python
patch_response.raise_for_status()
updated_rows = patch_response.json()
if isinstance(updated_rows, list) and updated_rows:
    return
# Row doesn't exist yet — insert fresh
```

**The issue**: If Supabase returns a `5xx` on the PATCH, `raise_for_status()` throws an exception. The `persist_state` call is wrapped in `try/except: logger.warning`. So the `NO_OVERLAP` or `BOOKED` status is never saved.

On next agent run for the same thread, session restores as `AWAITING_REPLIES` (the last successfully persisted state). The agent re-runs the booking or availability flow that just completed.

**Real scenario**: Supabase has a 500ms blip exactly when a booking confirms. `persist_state` throws → swallowed by the warning. Next participant email arrives → session appears as `AWAITING_REPLIES` → agent sends another availability request after the meeting is already booked.

**Risk**: 🟠 Medium — can cause double-booking attempts or availability emails after a meeting is confirmed.

**Fix**: Implement retry with exponential backoff on `persist_state`, or at minimum retry once. The single most critical write in the entire system should not silently fail.

---

## Edge Case 13 — `_extract_json_payload` Can Match JSON Inside Escaped Strings

**File**: [react_agent.py L29-37](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L29-L37)

```python
def _extract_json_payload(raw_text: str) -> dict[str, Any] | None:
    left = raw_text.find("{")
    right = raw_text.rfind("}")
```

**The issue**: If Gemini outputs something like:

```
Here is the JSON:
```json
{"action": "SENT_AVAILABILITY_REQUEST", "title": "Meeting", ...}
```
Note the example: {"action": "NO_ACTION"}
```

`rfind("}")` finds the **last** `}` which closes the example note `{"action": "NO_ACTION"}`. The extracted substring is `{"action": "SENT_AVAILABILITY_REQUEST"..., "title": "Meeting", ...}\n\`\`\`\nNote the example: {"action": "NO_ACTION"}` which is invalid JSON. The primary parse fails → JSON repair is triggered even though the first JSON was valid.

It also means if Gemini includes a JSON example later in its output, the extracted region will span across both valid JSON and markdown prose → parse fails → one unnecessary repair call to Gemini is made.

**Risk**: 🟡 Low — adds latency from unnecessary repair attempts, but fallback eventually works.

**Fix**: Use `find("{")` for the start but find the **matching closing brace** (balanced bracket search) instead of `rfind("}")`.

---

## Edge Case 14 — `get_or_create_session` Creates Ghost Session When Supabase Is Disabled

**File**: [thread_state_service.py L55-65](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/thread_state_service.py#L55-L65)

```python
if not self._enabled():
    return ThreadSessionState(
        session_id=f"sess_{uuid.uuid4().hex[:8]}",
        ...
        replied_participants=[],
        last_reminder_at=None,
    )
```

**The issue**: When Supabase is not configured, a fresh `ThreadSessionState` is returned with a **random new session_id every single run**. Every agent invocation for the same thread is treated as a brand-new session:
- `replied_pool` always starts empty → everyone is always in `pending_participants`
- `last_reminder_at = None` → reminders fire every single run with no cooldown
- Status never advances past `AWAITING_REPLIES`

**Risk**: 🔴 High in local/offline dev — the agent spam-sends availability emails and reminders on every inbound IMAP poll tick. Makes local testing painful and could exhaust Gmail send quotas rapidly.

**Fix**: Add an in-memory fallback session store keyed by `thread_id`, so sessions survive at least within one server process lifetime even without Supabase.

---

## Edge Case 15 — Thread Context Shows CalSync's Own Outbound Emails Mislabeled

**File**: [react_agent.py L111-112](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L111-L112)

```python
direction = str(row.get("direction") or "INBOUND")
role = "CalSync → Participant" if direction == "OUTBOUND" else "Participant → CalSync"
```

**The issue**: If a DB row has a `NULL` direction (possible if stored via a code path that doesn't set it), `row.get("direction") or "INBOUND"` defaults to `"INBOUND"`. A CalSync outbound email would then appear to Gemini as `"Participant → CalSync"`. Gemini reads the thread context and sees CalSync's OWN previous availability request as if a participant sent it — potentially confusing its analysis of who has replied and what the current state is.

**Risk**: 🟡 Low — depends on whether rows can have NULL direction. Worth guarding.

**Fix**: Store a default `direction="INBOUND"` at the DB schema level (NOT NULL constraint), and add an explicit check: if `from_email` matches `gmail_sender_email`, override direction to `OUTBOUND`.

---

## Edge Case 16 — Subject Fallback `"Meeting coordination"` Breaks Outbound Dedup

**File**: [react_agent.py L408](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L408) + [server.py L156-175](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/mcp_servers/gmail_mcp/server.py#L156-L175)

```python
subject=f"Re: {payload.subject}" if payload.subject else "Meeting coordination"
```

**The issue**: When `payload.subject` is empty, every email from every session gets subject `"Meeting coordination"`. The Gmail MCP outbound dedup checks `session_id + ilike(subject, "%available%")`. The subject `"Meeting coordination"` doesn't match any intent keyword → dedup is skipped entirely. Good? Not quite.

But there's a second problem: the `_subject_intent` map checks for keywords in the subject. All reminder and availability emails sent when subject is empty get subject `"Reminder: availability needed for Meeting coordination"`. That **does** match `"available"` → dedup fires → after the first reminder, all future reminders for that session are blocked (see Edge Case 4).

**Risk**: 🟠 Medium — reminder loop is permanently broken for sessions where the original email had no subject.

---

## Priority Summary

| # | Issue | Severity | File |
|---|---|---|---|
| 6 | Organizer email overwritten on every run | 🔴 | react_agent.py L355 |
| 1 | Fail-open FreeBusy causes phantom booking | 🔴 | conflict_resolver.py L62 |
| 4 | Outbound dedup permanently blocks re-sends | 🔴 | server.py L156 |
| 14 | No-Supabase ghost session → spam reminders | 🔴 | thread_state_service.py L55 |
| 12 | persist_state swallowed silently → session reset | 🟠 | thread_state_service.py L173 |
| 3 | Concurrent session double-creation | 🟠 | thread_state_service.py L67 |
| 10 | NO_OVERLAP override fires on NO_ACTION emails | 🟠 | react_agent.py L346 |
| 2 | Memory dedup race with multiple workers | 🟠 | dedup_service.py L19 |
| 16 | Empty subject → reminder dedup permanently blocked | 🟠 | react_agent.py L408 |
| 8 | Confirmation email shows UTC not IST | 🟡 | react_agent.py L559 |
| 9 | Reminder double-send on first AWAITING reply | 🟡 | react_agent.py L418 |
| 7 | Participant pool contaminated by outbound rows | 🟡 | react_agent.py L366 |
| 11 | `already_sent` reported as sent in response | 🟡 | react_agent.py L341 |
| 5 | Thread ID sanitization strips valid RFC IDs | 🟡 | tools.py L50 |
| 13 | JSON extractor matches wrong closing brace | 🟡 | react_agent.py L29 |
| 15 | NULL direction mislabels CalSync emails in context | 🟡 | react_agent.py L111 |
