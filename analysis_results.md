# CalSync Agent — Test Case Coverage Analysis

After scanning every source file in the codebase, here is a per-test-case verdict.

**Legend**: ✅ Handled | ⚠️ Partially Handled | ❌ Not Handled

---

## 1. Inbound Ingestion & Intake

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-001 | P0 | ✅ | [webhook.py](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/routers/webhook.py#L96-L133): keyword filter → `background_tasks.add_task` |
| TC-002 | P0 | ✅ | [webhook.py L96-117](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/routers/webhook.py#L96-L117): stores as IGNORED, returns `NotSchedulingResponse` |
| TC-003 | P0 | ✅ | [webhook.py L83-86](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/routers/webhook.py#L83-L86): `check_and_mark_duplicate` → `DuplicateResponse` |
| TC-004 | P1 | ✅ | [webhook.py L88-91](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/routers/webhook.py#L88-L91): `derive_thread_id` falls back to `message_id` |
| TC-005 | P1 | ✅ | `message_from_string("")` returns empty parsed obj; no crash path |
| TC-006 | P1 | ✅ | Body is truncated to 200 chars for classification; Gemini prompt caps at 2000 |
| TC-007 | P1 | ✅ | [webhook.py L70](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/routers/webhook.py#L70): `_ = attachments` — explicitly discarded |
| TC-008 | P1 | ✅ | [imap_ingestion.py](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/imap_ingestion.py#L37-L95): loops all emails, classifies each independently |
| TC-009 | P0 | ✅ | [imap_service.py L126-129](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/imap_service.py#L126-L129): `mail.store(uid, "+FLAGS", "\\Seen")` per UID inside loop |
| TC-010 | P1 | ✅ | [imap_service.py L95-96](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/imap_service.py#L95-L96): `if fetch_status != "OK": continue` |
| TC-011 | P1 | ✅ | [imap_service.py L99-100](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/imap_service.py#L99-L100): `if not isinstance(raw_email, (bytes, bytearray)): continue` |
| TC-012 | P1 | ✅ | [imap_poller.py L42-43](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/imap_poller.py#L42-L43): `except ValueError` logs warning, loop continues |

---

## 2. Deduplication

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-020 | P0 | ✅ | [dedup_service.py](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/dedup_service.py): `check_and_mark_duplicate` with TTL |
| TC-021 | P0 | ✅ | Same `build_email_hash` + `check_and_mark_duplicate` used in IMAP path |
| TC-022 | P0 | ✅ | Hash = `sha256(sender:message_id)` — identical across IMAP/webhook |
| TC-023 | P1 | ✅ | [dedup_service.py L98-104](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/dedup_service.py#L98-L104): auto-selects redis when `redis_url` set |
| TC-024 | P1 | ✅ | Same block: falls to supabase when redis missing |
| TC-025 | P1 | ✅ | Same block: falls to memory when no external backend |
| TC-026 | P1 | ✅ | [dedup_service.py L107-108](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/dedup_service.py#L107-L108): `raise RuntimeError` |
| TC-027 | P1 | ✅ | [dedup_service.py L112-113](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/dedup_service.py#L112-L113): `raise RuntimeError` |
| TC-028 | P2 | ✅ | Memory backend expires keys when `expires_at <= now` |
| TC-029 | P2 | ✅ | `_memory_store` is a module-level dict; lost on restart by definition |
| TC-030 | P2 | ⚠️ | Hash uses raw `sender` string — **casing is NOT normalized** before hashing. Same sender with different casing produces different hash. Behavior is consistent but undocumented. |

---

## 3. Thread Identity Derivation

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-040 | P0 | ✅ | [thread_identity.py L46-48](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/thread_identity.py#L46-L48): `reference_chain[0]` |
| TC-041 | P0 | ✅ | L50-52: falls to `normalize_message_id(in_reply_to)` |
| TC-042 | P0 | ✅ | L54: falls to `normalize_message_id(message_id)` |
| TC-043 | P1 | ✅ | `normalize_message_id` strips angle brackets |
| TC-044 | P1 | ✅ | Same normalization applied |
| TC-045 | P1 | ✅ | `extract_reference_chain` uses regex `finditer` to parse full chain |
| TC-046 | P1 | ✅ | Regex `<([^>]+)>|([^\s<>]+)` is whitespace-tolerant |
| TC-047 | P1 | ✅ | Empty/whitespace returns `""` — no crash |
| TC-048 | P2 | ⚠️ | `email.message_from_string` handles RFC headers but exotic encodings may produce garbled but deterministic output. No explicit encoding normalization. |

---

## 4. Thread Memory Persistence

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-060 | P0 | ✅ | [webhook.py L112](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/routers/webhook.py#L112): `processing_status="PENDING" if accepted` |
| TC-061 | P0 | ✅ | Same line: `"IGNORED"` when not accepted |
| TC-062 | P0 | ✅ | [thread_memory_service.py L57-78](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/thread_memory_service.py#L57-L78): stores `thread_id`, `in_reply_to`, `references_header` |
| TC-063 | P1 | ✅ | Same payload: `to_emails`, `cc_emails` arrays stored |
| TC-064 | P1 | ✅ | [thread_memory_service.py L88-89](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/thread_memory_service.py#L88-L89): `except Exception: logger.warning` |
| TC-065 | P1 | ✅ | [thread_memory_service.py L98](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/thread_memory_service.py#L98): `order: received_at.asc` |
| TC-066 | P1 | ✅ | L99: `limit: str(max(limit, 1))` |
| TC-067 | P1 | ✅ | Returns `[]` on empty; agent checks `if thread_rows:` |
| TC-068 | P2 | ✅ | Gmail MCP `/send` stores OUTBOUND records via `supabase_ops.store_email` with `thread_id` |

---

## 5. Session State

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-080 | P0 | ✅ | [thread_state_service.py L68-90](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/thread_state_service.py#L68-L90): new thread → `AWAITING_REPLIES` |
| TC-081 | P0 | ✅ | L92-114: existing session restored by `thread_id` lookup |
| TC-082 | P0 | ✅ | L98-103: `dict.fromkeys` merge deduplicates |
| TC-083 | P0 | ✅ | L112: `replied_participants` restored from DB row |
| TC-084 | P0 | ✅ | [react_agent.py L550-553](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L550-L553): `persist_state` called after action |
| TC-085 | P1 | ✅ | L552-553: `except Exception: logger.warning` — no crash |
| TC-086 | P1 | ✅ | [react_agent.py L399-412](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L399-L412): `if session.status == "BOOKED": return NO_ACTION` |
| TC-087 | P0 | ✅ | [react_agent.py L539](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L539): `if session.status not in ("BOOKED", "NO_OVERLAP")` — NO_OVERLAP is preserved |

---

## 6. Gemini Analysis & Fallbacks

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-100 | P0 | ✅ | `_extract_json_payload` parses valid JSON |
| TC-101 | P0 | ✅ | [react_agent.py L149-162](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L149-L162): missing key → deterministic fallback |
| TC-102 | P1 | ✅ | L164-179: `except ModuleNotFoundError` → fallback |
| TC-103 | P1 | ✅ | L192-213: exponential backoff on 429/RESOURCE_EXHAUSTED |
| TC-104 | P1 | ✅ | L214-221: after max retries → fallback |
| TC-105 | P0 | ✅ | L225-247: `format_retry_limit = 2`, attempt 1 |
| TC-106 | P0 | ✅ | Same loop: attempt 2 |
| TC-107 | P0 | ✅ | L249-262: still malformed → deterministic fallback |
| TC-108 | P1 | ✅ | [react_agent.py L312-314](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L312-L314): defaults applied via `str(... or "NO_ACTION")` |
| TC-109 | P1 | ✅ | `_extract_json_payload` finds first `{` to last `}` — strips surrounding prose |

---

## 7. Participant Resolution

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-120 | P0 | ✅ | `dedupe_emails` in [participant_utils.py](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/services/participant_utils.py) uses `.lower()` |
| TC-121 | P0 | ✅ | [react_agent.py L279,322](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L279): `exclude_emails([settings.gmail_sender_email])` |
| TC-122 | P0 | ✅ | L325: `replied_pool = dedupe_emails(session.replied_participants + [payload.from_email])` |
| TC-123 | P1 | ✅ | L330-345: late joiner detection from thread history with reasoning trace |
| TC-124 | P1 | ✅ | `dedupe_emails` handles To+Cc overlap |
| TC-125 | P1 | ✅ | [react_agent.py L41-43](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L41-L43): empty → `[payload.from_email]` |
| TC-126 | P2 | ✅ | `EMAIL_PATTERN` regex only matches valid tokens; invalid ones silently dropped |

---

## 8. Availability Request Action

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-140 | P0 | ✅ | [react_agent.py L363-375](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L363-L375): sends email to participant pool |
| TC-141 | P0 | ✅ | L375: `reasoning_trace` records tool status |
| TC-142 | P1 | ✅ | [tools.py L45-46](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/tools.py#L45-L46): returns `SKIPPED` if not configured; L34-35: returns `ERROR` on exception |
| TC-143 | P1 | ✅ | L370: `f"Re: {payload.subject}" if payload.subject else "Meeting coordination"` |

---

## 9. Reminder Logic

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-160 | P0 | ✅ | [react_agent.py L379-396](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L379-L396): pending + cooldown passed → send |
| TC-161 | P0 | ✅ | `_should_send_reminder` returns False when cooldown not passed |
| TC-162 | P1 | ✅ | Condition `pending_participants` must be truthy |
| TC-163 | P1 | ✅ | `reminders_sent` only set true on OK; session still persisted at L550 |
| TC-164 | P1 | ✅ | L547-548: `if reminders_sent: session.last_reminder_at = utcnow` |
| TC-165 | P2 | ✅ | `_parse_iso_timestamp` returns `None` on `ValueError` → `_should_send_reminder` returns `True` |
| TC-166 | P0 | ✅ | Session stays `AWAITING_REPLIES` (L540-541), reminders sent per cooldown each cycle |

---

## 10. Booking Logic

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-180 | P0 | ✅ | [react_agent.py L415-432](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L415-L432): pending → downgraded to `SENT_AVAILABILITY_REQUEST` |
| TC-181 | P0 | ✅ | L437-449: missing start/end → asks for slot |
| TC-182 | P0 | ✅ | L455-460: `slot_is_free` check → proceeds to book |
| TC-183 | P0 | ✅ | L505-506: `book_calendar OK` → `session.status = "BOOKED"` + confirmation email at L526-537 |
| TC-184 | P1 | ⚠️ | `check_freebusy` errors return `ToolCallOutcome(status="ERROR")`. Since `freebusy_results` won't have `is_free=True`, it falls to `not slot_is_free` path → **safe but not explicitly documented as "non-free"** |
| TC-185 | P1 | ⚠️ | `book_calendar` error returns `status="ERROR"`. Code checks `== "OK"` and `== "ALL_SLOTS_CONFLICTED"` — the `else` branch (L525-537) **sends a confirmation email even on error**. This is a **bug**: a false confirmation could be sent. |

---

## 11. NO_OVERLAP Scenarios

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-200 | P0 | ✅ | L476-477: all replied + not free → `session.status = "NO_OVERLAP"` |
| TC-201 | P0 | ✅ | L478-493: sends "share more slots" email |
| TC-202 | P0 | ✅ | L507-508: `ALL_SLOTS_CONFLICTED` → `NO_OVERLAP` |
| TC-203 | P0 | ✅ | L507-524: sends clarification, **not** confirmation |
| TC-204 | P0 | ✅ | L539: status rewrite skips `BOOKED` and `NO_OVERLAP` |
| TC-205 | P0 | ✅ | Session persists as `NO_OVERLAP`; next inbound restores session, new Gemini analysis runs |
| TC-206 | P0 | ⚠️ | The loop-until-booked flow works **only if Gemini correctly re-analyzes** the new slots as `BOOKED_CALENDAR`. The agent doesn't have explicit "retry with new slots" state — it relies on Gemini choosing the right action. |

---

## 12. Timezone & Time Handling

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-220 | P0 | ⚠️ | Handled by **Gemini prompt rule 6** in [prompts.py](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/prompts.py#L16-L17). No code-level enforcement — relies entirely on LLM compliance. |
| TC-221 | P0 | ⚠️ | Prompt rule 7 instructs Gemini not to choose `BOOKED_CALENDAR`. **No code guard** to reject booking when timezone is missing. |
| TC-222 | P0 | ⚠️ | Same — pure prompt instruction, no validation. |
| TC-223 | P1 | ✅ | Slot values are passed through as-is to Calendar MCP |
| TC-224 | P1 | ✅ | All internal timestamps use `datetime.now(timezone.utc).isoformat()` |
| TC-225 | P2 | ⚠️ | Conversion is delegated entirely to Gemini. No code-level timezone conversion. |

---

## 13. Thread Context Utilization

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-240 | P0 | ✅ | [react_agent.py L284-289](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L284-L289): fetches thread rows, builds context |
| TC-241 | P1 | ✅ | `_build_thread_context` includes direction labels and body previews |
| TC-242 | P1 | ✅ | Body truncated to 1000 chars in context builder |
| TC-243 | P1 | ✅ | L336-345: fallback `fetch_thread` from Gmail MCP when `thread_id != message_id` and no DB rows |
| TC-244 | P1 | ✅ | L340-345: `_collect_participants_from_thread_payload` enriches pools |
| TC-245 | P1 | ✅ | `_post_json` catches all exceptions → `ToolCallOutcome(status="ERROR")` |

---

## 14. Action & Status Consistency

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-260 | P0 | ✅ | `action` variable mutated inline to reflect actual path taken |
| TC-261 | P0 | ✅ | `BOOKED` set only on `calendar_outcome.status == "OK"`; `NO_OVERLAP` set on conflict paths; final guard at L539 preserves both |
| TC-262 | P1 | ✅ | `reasoning_trace` accumulates tool outcomes throughout |
| TC-263 | P1 | ⚠️ | `emails_sent_to` is set to `recipients` (the normalized inbound payload recipients), **not** the actual list the email was sent to (which is `participant_pool`). This may be misleading. |

---

## 15. End-to-End Demo Flows

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-280 | P0 | ✅ | Full path through AWAITING → READY_TO_COMPUTE → BOOKED is wired |
| TC-281 | P0 | ✅ | Reminder logic with cooldown is implemented |
| TC-282 | P0 | ✅ | NO_OVERLAP path with "share more slots" email |
| TC-283 | P0 | ⚠️ | Depends on Gemini re-analyzing new slots correctly (see TC-206) |
| TC-284 | P0 | ✅ | Dedup prevents re-trigger; BOOKED guard prevents duplicate booking |
| TC-285 | P1 | ✅ | Session restored from Supabase; dedup state survives if using Supabase/Redis backend |
| TC-286 | P1 | ✅ | Deterministic fallback path produces `SENT_AVAILABILITY_REQUEST` |

---

## 16. Negative & Security/Hardening

| TC | P | Verdict | Evidence |
|---|---|---|---|
| TC-300 | P1 | ✅ | Gemini output parsed via `_extract_json_payload` with fallback; prompt injection can't break the JSON contract handling |
| TC-301 | P1 | ✅ | Empty strings are defaults in `EmailWebhookPayload`; no crash paths |
| TC-302 | P1 | ✅ | `_decode_header_value` uses `errors="replace"`; email regex handles ASCII-range |
| TC-303 | P1 | ✅ | IMAP poller processes one batch at a time; poller loop catches exceptions |
| TC-304 | P2 | ✅ | `persist_state` wrapped in `except Exception: logger.warning` |
| TC-305 | P2 | ✅ | `_post_json` returns `ToolCallOutcome(status="ERROR", payload={"error": str(exc)})` |

---

## Summary

| Category | Total | ✅ | ⚠️ | ❌ |
|---|---|---|---|---|
| 1. Ingestion | 12 | 12 | 0 | 0 |
| 2. Dedup | 11 | 10 | 1 | 0 |
| 3. Thread Identity | 9 | 8 | 1 | 0 |
| 4. Thread Memory | 9 | 9 | 0 | 0 |
| 5. Session State | 8 | 8 | 0 | 0 |
| 6. Gemini & Fallbacks | 10 | 10 | 0 | 0 |
| 7. Participants | 7 | 7 | 0 | 0 |
| 8. Availability | 4 | 4 | 0 | 0 |
| 9. Reminders | 7 | 7 | 0 | 0 |
| 10. Booking | 6 | 4 | 2 | 0 |
| 11. NO_OVERLAP | 7 | 6 | 1 | 0 |
| 12. Timezone | 6 | 2 | 4 | 0 |
| 13. Thread Context | 6 | 6 | 0 | 0 |
| 14. Action Consistency | 4 | 3 | 1 | 0 |
| 15. E2E Flows | 7 | 6 | 1 | 0 |
| 16. Security | 6 | 6 | 0 | 0 |
| **TOTAL** | **119** | **108** | **11** | **0** |

---

## Critical Issues to Fix

> [!CAUTION]
> ### TC-185: `book_calendar` error sends false confirmation
> In [react_agent.py L525-537](file:///d:/My%20Files/Ameya/Coding/COEP%20Inspiron/Calsync/ingestion/app/agent/react_agent.py#L525-L537), the `else` branch after checking `== "OK"` and `== "ALL_SLOTS_CONFLICTED"` catches **all other statuses including `"ERROR"`**, and sends a confirmation email. This could send a bogus "meeting booked" email when the Calendar API actually failed.

> [!WARNING]
> ### TC-220/221/222/225: Timezone validation is prompt-only
> There is **no code-level guard** to reject a `BOOKED_CALENDAR` action when the slot lacks a timezone or uses an ambiguous one. The system relies entirely on Gemini following the prompt instructions. A hallucinating model could book at wrong times.

> [!WARNING]
> ### TC-263: `emails_sent_to` reports wrong recipients
> `AgentProcessResponse.emails_sent_to` is set to `recipients` (the deduplicated inbound payload participants), not the actual `participant_pool` that emails were dispatched to. This could cause confusion in observability.
