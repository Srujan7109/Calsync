# CalSync Agent Test Cases

This file is a comprehensive test catalog for the current agent workflow.

Notes:

- "Every single test case" is practically unbounded, so this document enumerates the full set of meaningful and distinct cases for the current architecture.
- Test IDs are stable so you can track pass/fail quickly during demo prep.
- Priority labels: P0 = must pass for demo, P1 = important, P2 = hardening.

## 1. Inbound Ingestion And Intake

- TC-001 (P0): Webhook receives valid scheduling email; dedup misses; agent task is queued.
- TC-002 (P0): Webhook receives non-scheduling email; stored as IGNORED; no agent task queued.
- TC-003 (P0): Webhook receives duplicate delivery (same sender + message_id); returns DuplicateResponse.
- TC-004 (P1): Webhook payload missing headers; thread_id falls back correctly to message_id.
- TC-005 (P1): Webhook payload has malformed headers blob; request still processes without crash.
- TC-006 (P1): Webhook receives large body text; classification still works.
- TC-007 (P1): Webhook receives attachments; attachments ignored safely.
- TC-008 (P1): IMAP poll fetches batch with mixed scheduling and non-scheduling emails.
- TC-009 (P0): IMAP poll marks each processed UID as \Seen (not only last one).
- TC-010 (P1): IMAP fetch_status != OK for one UID; remaining UIDs continue.
- TC-011 (P1): IMAP raw_email malformed/non-bytes; message skipped safely.
- TC-012 (P1): IMAP mailbox credentials missing; poller logs warning and continues loop.

## 2. Deduplication

- TC-020 (P0): Duplicate webhook retry within TTL is blocked.
- TC-021 (P0): Duplicate IMAP re-fetch within TTL is blocked.
- TC-022 (P0): Same email arrives via IMAP and webhook; second intake is blocked.
- TC-023 (P1): Dedup backend auto-selects Redis when REDIS_URL exists.
- TC-024 (P1): Dedup backend auto-selects Supabase when Redis missing and Supabase creds exist.
- TC-025 (P1): Dedup backend auto-selects memory when no external backend exists.
- TC-026 (P1): Redis backend configured but REDIS_URL missing; clear runtime error raised.
- TC-027 (P1): Supabase backend configured but credentials missing; clear runtime error raised.
- TC-028 (P2): TTL expiry allows reprocessing after window, as expected.
- TC-029 (P2): Memory backend loses dedup state after restart.
- TC-030 (P2): Sender casing differs; ensure dedup behavior is understood and documented.

## 3. Thread Identity Derivation

- TC-040 (P0): References header present; thread_id derives from first reference item.
- TC-041 (P0): No references, In-Reply-To present; thread_id derives from In-Reply-To.
- TC-042 (P0): Neither present; thread_id falls back to message_id.
- TC-043 (P1): Message-ID wrapped in angle brackets is normalized.
- TC-044 (P1): In-Reply-To wrapped in angle brackets is normalized.
- TC-045 (P1): References with multiple IDs parses full chain correctly.
- TC-046 (P1): References contains mixed tokens/spaces/newlines; parser remains stable.
- TC-047 (P1): Empty/whitespace thread fields do not crash.
- TC-048 (P2): Unknown header encodings still produce deterministic thread_id.

## 4. Thread Memory Persistence (emails table)

- TC-060 (P0): Inbound accepted email stored with PENDING status.
- TC-061 (P0): Inbound filtered email stored with IGNORED status.
- TC-062 (P0): Stored row includes thread_id, in_reply_to, references_header.
- TC-063 (P1): Stored row includes parsed to_emails and cc_emails arrays.
- TC-064 (P1): Supabase unavailable during store_email logs warning but intake continues.
- TC-065 (P1): get_thread_emails returns rows ordered by received_at ascending.
- TC-066 (P1): get_thread_emails limit is honored.
- TC-067 (P1): Empty thread history returns [] and agent continues.
- TC-068 (P2): Outbound emails from Gmail MCP also appear in thread memory path (if integrated).

## 5. Session State (sessions table)

- TC-080 (P0): New thread creates session with AWAITING_REPLIES.
- TC-081 (P0): Existing thread restores same session_id.
- TC-082 (P0): Existing participants merge with new participants without duplicates.
- TC-083 (P0): replied_participants are restored and used for pending calculation.
- TC-084 (P0): Session persisted after action completes.
- TC-085 (P1): Session persistence failure logs warning and does not crash agent.
- TC-086 (P1): BOOKED session prevents duplicate booking attempt.
- TC-087 (P0): NO_OVERLAP session persists and is not overwritten by READY_TO_COMPUTE logic.

## 6. Gemini Analysis And Fallbacks

- TC-100 (P0): Gemini returns valid strict JSON; parsed and used.
- TC-101 (P0): Gemini API key missing; deterministic fallback path used.
- TC-102 (P1): google.genai module missing; deterministic fallback path used.
- TC-103 (P1): Gemini call throws 429; exponential backoff retries happen.
- TC-104 (P1): Gemini call fails after retries; deterministic fallback used.
- TC-105 (P0): Gemini response malformed JSON; JSON repair retry attempt 1 executes.
- TC-106 (P0): Gemini response malformed JSON; JSON repair retry attempt 2 executes.
- TC-107 (P0): JSON still malformed; deterministic fallback used.
- TC-108 (P1): Valid JSON but missing action/title keys; defaults applied safely.
- TC-109 (P1): Response contains extra prose around JSON; parser extracts JSON region.

## 7. Participant Resolution

- TC-120 (P0): Participants deduped case-insensitively.
- TC-121 (P0): Agent sender email excluded from participant pools.
- TC-122 (P0): Current inbound sender is added to replied_participants.
- TC-123 (P1): Thread history adds late joiner participant; reasoning trace marks it.
- TC-124 (P1): Participant appears in To and Cc; dedup keeps one instance.
- TC-125 (P1): Empty participants list falls back to from_email.
- TC-126 (P2): Invalid email tokens are ignored by regex parser.

## 8. Availability Request Action

- TC-140 (P0): action=SENT_AVAILABILITY_REQUEST sends follow-up email to participant pool.
- TC-141 (P0): send_gmail_message returns OK; reasoning trace records tool status.
- TC-142 (P1): Gmail MCP unavailable; tool status ERROR/SKIPPED is handled gracefully.
- TC-143 (P1): Subject fallback works when payload subject is empty.

## 9. Reminder Logic

- TC-160 (P0): Pending participants exist and cooldown passed; reminder is sent.
- TC-161 (P0): Pending participants exist but cooldown not passed; reminder not sent.
- TC-162 (P1): No pending participants; reminder is not sent.
- TC-163 (P1): Reminder send fails; session still persists.
- TC-164 (P1): last_reminder_at updated when reminder succeeds.
- TC-165 (P2): malformed last_reminder_at timestamp defaults to reminder-allowed behavior.
- TC-166 (P0): "participant never replies" repeated cycles keep session in AWAITING_REPLIES and send reminders per cooldown.

## 10. Booking Logic

- TC-180 (P0): action=BOOKED_CALENDAR but pending participants exist -> downgraded to SENT_AVAILABILITY_REQUEST.
- TC-181 (P0): BOOKED_CALENDAR with missing slot fields -> asks for slot instead of booking.
- TC-182 (P0): check_freebusy indicates free -> proceeds to book_calendar.
- TC-183 (P0): book_calendar OK -> session set to BOOKED and confirmation email sent.
- TC-184 (P1): check_freebusy tool error -> treated as non-free path safely.
- TC-185 (P1): book_calendar tool error -> no false BOOKED state.

## 11. NO_OVERLAP Scenarios

- TC-200 (P0): All participants replied, freebusy says slot not free -> session set NO_OVERLAP.
- TC-201 (P0): NO_OVERLAP path sends "share more slots" email.
- TC-202 (P0): calendar_mcp returns ALL_SLOTS_CONFLICTED -> session set NO_OVERLAP.
- TC-203 (P0): ALL_SLOTS_CONFLICTED path does not send calendar confirmation.
- TC-204 (P0): Final status rewrite does not overwrite NO_OVERLAP.
- TC-205 (P0): Agent continues conversation after NO_OVERLAP when new slots arrive.
- TC-206 (P0): "No overlap then ask for more slots repeatedly" loop continues until overlap found, then BOOKED.

## 12. Timezone And Time Handling

- TC-220 (P0): Email includes explicit timezone; model outputs UTC Z slot values.
- TC-221 (P0): Email timezone missing; model does not choose BOOKED_CALENDAR and asks timezone.
- TC-222 (P0): Ambiguous timezone abbreviation; model requests clarification.
- TC-223 (P1): UTC timestamps from model pass unchanged to Calendar MCP.
- TC-224 (P1): Internal timestamps (received_at, ingested_at, reminders) are UTC.
- TC-225 (P2): Non-UTC local input with explicit timezone converts correctly to UTC Z.

## 13. Thread Context Utilization

- TC-240 (P0): Thread rows available in DB -> context built from last N messages.
- TC-241 (P1): Thread context includes direction labels and body previews.
- TC-242 (P1): Very long body is truncated in context to avoid prompt bloat.
- TC-243 (P1): No thread rows -> fallback fetch_thread from Gmail MCP when thread_id differs from message_id.
- TC-244 (P1): fetch_thread success enriches participant and replied pools.
- TC-245 (P1): fetch_thread failure does not crash run.

## 14. Action And Status Consistency

- TC-260 (P0): action_taken reflects actual path (request, booking, or no_action).
- TC-261 (P0): session status and action_taken are not contradictory for BOOKED and NO_OVERLAP.
- TC-262 (P1): reasoning_trace captures key tool outcomes.
- TC-263 (P1): emails_sent_to reflects intended recipients for action path.

## 15. End-To-End Demo Flows

- TC-280 (P0): New scheduling thread -> availability request -> replies collected -> overlap found -> booked.
- TC-281 (P0): New scheduling thread -> one participant silent -> reminders sent on cooldown.
- TC-282 (P0): New scheduling thread -> all reply but no overlap -> NO_OVERLAP and re-request slots.
- TC-283 (P0): After NO_OVERLAP, participants send more slots -> overlap found -> booked.
- TC-284 (P0): Duplicate inbound during active thread does not re-trigger duplicate action.
- TC-285 (P1): Agent/server restart mid-thread still restores session and continues.
- TC-286 (P1): Gemini unavailable during run still produces deterministic request path.

## 16. Negative And Security/Hardening Cases

- TC-300 (P1): Malicious prompt-injection in email body does not break JSON contract handling.
- TC-301 (P1): Empty subject/body inbound does not crash flow.
- TC-302 (P1): Non-ASCII names and email display names parsed safely.
- TC-303 (P1): High-volume burst does not crash poller loop.
- TC-304 (P2): Supabase transient timeout during session persist logs warning and continues.
- TC-305 (P2): Gmail MCP returns non-JSON error body; tool wrapper still returns safe ERROR payload.

## 17. Suggested Demo Run Order

- Demo-01: TC-280 end-to-end happy path.
- Demo-02: TC-281 reminder path (one participant silent).
- Demo-03: TC-282 no-overlap path.
- Demo-04: TC-283 no-overlap recovery to booked.
- Demo-05: TC-284 duplicate protection.
- Demo-06: TC-286 Gemini fallback resilience.

## 18. Pass/Fail Recording Template

Use this for each test run:

- Test ID:
- Date/Time:
- Input email(s):
- Expected:
- Actual:
- Status: PASS/FAIL
- Logs evidence:
- DB evidence (sessions/emails rows):
- Notes/fixes:
