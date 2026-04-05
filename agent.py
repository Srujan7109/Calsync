import os
import json
import httpx
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

client   = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL    = "gemini-2.5-flash"
GMAIL_MCP = os.getenv("GMAIL_MCP_URL", "http://localhost:8006")
CAL_MCP   = os.getenv("CALENDAR_MCP_URL", "http://localhost:8002")
TIMEOUT   = 60.0

# ================================================================
# TOOL DEFINITIONS
# ================================================================

TOOLS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="check_freebusy",
            description="Check if all participants are free for given time slots. Always call before booking.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "participants": types.Schema(
                        type="ARRAY",
                        items=types.Schema(type="STRING"),
                        description="Participant emails"
                    ),
                    "slots": types.Schema(
                        type="ARRAY",
                        items=types.Schema(
                            type="OBJECT",
                            properties={
                                "start": types.Schema(type="STRING"),
                                "end":   types.Schema(type="STRING")
                            },
                            required=["start","end"]
                        ),
                        description="Time slots to check in ISO 8601 UTC"
                    )
                },
                required=["participants","slots"]
            )
        ),
        types.FunctionDeclaration(
            name="book_meeting",
            description="Book a Google Calendar meeting with Meet link. Only call after check_freebusy confirms free slot.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "title":           types.Schema(type="STRING"),
                    "organizer_email": types.Schema(type="STRING"),
                    "participants":    types.Schema(
                        type="ARRAY",
                        items=types.Schema(type="STRING")
                    ),
                    "start":       types.Schema(type="STRING", description="ISO 8601 UTC"),
                    "end":         types.Schema(type="STRING", description="ISO 8601 UTC"),
                    "description": types.Schema(type="STRING"),
                    "session_id":  types.Schema(type="STRING")
                },
                required=["title","organizer_email","participants","start","end"]
            )
        ),
        types.FunctionDeclaration(
            name="send_email",
            description=(
                "Send an email via Gmail. You write the full subject and body. "
                "Use for availability requests, confirmations, clarifications. "
                "Always set in_reply_to and references when replying to a thread."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "to_emails":    types.Schema(
                        type="ARRAY",
                        items=types.Schema(type="STRING")
                    ),
                    "subject":      types.Schema(type="STRING"),
                    "body_text":    types.Schema(type="STRING", description="Full professional email body"),
                    "thread_id":    types.Schema(type="STRING", description="Gmail thread ID to keep this reply in the same thread"),
                    "in_reply_to":  types.Schema(type="STRING", description="Message-ID header value of the email being replied to (from fetch_thread last message's message_id_header). Enables proper email threading in all clients."),
                    "references":   types.Schema(type="STRING", description="Space-separated list of Message-IDs from the thread (from fetch_thread). Set this to the full References chain."),
                    "session_id":   types.Schema(type="STRING")
                },
                required=["to_emails","subject","body_text"]
            )
        ),
        types.FunctionDeclaration(
            name="fetch_thread",
            description="Fetch full email thread history. Call this first whenever thread_id is available to read prior messages and extract message_id_header for in_reply_to.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "thread_id":    types.Schema(type="STRING"),
                    "max_messages": types.Schema(type="INTEGER")
                },
                required=["thread_id"]
            )
        ),
        types.FunctionDeclaration(
            name="detect_intent",
            description="Detect scheduling intent of an incoming email.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "subject":   types.Schema(type="STRING"),
                    "body_text": types.Schema(type="STRING"),
                    "thread_id": types.Schema(type="STRING")
                },
                required=["subject","body_text"]
            )
        ),
        types.FunctionDeclaration(
            name="mark_done",
            description=(
                "Signal that your task is fully complete. ALWAYS call this as the LAST "
                "action after all emails are sent and/or meeting is booked. "
                "Do not call any other tools after mark_done."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "action_type": types.Schema(
                        type="STRING",
                        description=(
                            "What was accomplished. One of: "
                            "'availability_requested' | 'meeting_booked_and_confirmed' | "
                            "'clarification_sent' | 'no_action_needed'"
                        )
                    ),
                    "summary": types.Schema(
                        type="STRING",
                        description="One-sentence human-readable summary of what was done."
                    )
                },
                required=["action_type"]
            )
        )
    ])
]

SYSTEM = """You are CalSync.ai, an autonomous AI scheduling assistant.
You coordinate meetings by sending emails and booking Google Calendar events.
You operate via calsync1.ai@gmail.com.

RULES:
1. Write all email content yourself — professional, friendly, concise.
2. Sign emails as CalSync.ai coordinating on behalf of the organizer.
3. Always append this to every email body:
   ---
   This email was sent by CalSync.ai, an AI scheduling assistant.
   To modify or cancel, reply to this thread.
   ---
4. Always check_freebusy BEFORE book_meeting.
5. After book_meeting succeeds, send ONE confirmation email to ALL participants
   (including the organizer) with the time in IST, event link, and Meet link.
   Google Calendar does NOT send its own invites — you are the only notifier.
6. Show times in IST (UTC+5:30) in email bodies.
7. THREAD CONTEXT — whenever situation contains a thread_id:
   a. Call fetch_thread(thread_id) FIRST to read the conversation history.
   b. Use the last email's message_id_header value as in_reply_to.
   c. Build the references field as all message_id_header values in the thread joined by a space.
   d. This keeps the email thread intact for all email clients.
8. ORGANIZER EXCLUSION — never include the organizer in to_emails for
   availability request emails. Only include participants who are not the organizer.
9. For AWAITING_REPLIES: send availability request emails to non-organizer
   participants only, then call mark_done(action_type='availability_requested').
10. For READY_TO_COMPUTE: check_freebusy → book_meeting → send_email confirmation
    to ALL participants → call mark_done(action_type='meeting_booked_and_confirmed').
11. For NO_OVERLAP: send clarification email to all participants asking for
    more slots → call mark_done(action_type='clarification_sent').
12. ALWAYS call mark_done as the VERY LAST action. Never call any tool after mark_done.
13. Make sure you always say - \"happy to be always there for you, need any help, cc me please!\""""

# ================================================================
# TOOL EXECUTION
# ================================================================

def execute_tool(name: str, args: dict, ctx: dict) -> dict:
    print(f"\n  🔧 {name}")
    print(f"     {json.dumps(args, indent=4)[:250]}")
    try:
        if name == "check_freebusy":
            r = httpx.post(f"{CAL_MCP}/freebusy", json={
                "participants": args["participants"],
                "slots": args["slots"]
            }, timeout=TIMEOUT)
            return r.json()

        elif name == "book_meeting":
            r = httpx.post(f"{CAL_MCP}/book", json={
                "action":          "BOOK_MEETING",
                "title":           args["title"],
                "slot":            {"start": args["start"], "end": args["end"]},
                "participants":    args["participants"],
                "organizer_email": args["organizer_email"],
                "description":     args.get("description",""),
                "fallback_slots":  [],
                "session_id":      args.get("session_id")
            }, timeout=TIMEOUT)
            result = r.json()
            if result.get("status") == "BOOKED":
                ctx.update({
                    "booked":      True,
                    "event_link":  result.get("event_link"),
                    "meet_link":   result.get("meet_link"),
                    "booked_slot": result.get("booked_slot"),
                    "title":       args["title"],
                    "participants": args["participants"]
                })
                print(f"\n  🎉 BOOKED!")
                print(f"     Event: {result.get('event_link')}")
                print(f"     Meet:  {result.get('meet_link')}")
            return result

        elif name == "send_email":
            r = httpx.post(f"{GMAIL_MCP}/send", json={
                "to_emails":   args["to_emails"],
                "subject":     args["subject"],
                "body_text":   args["body_text"],
                "thread_id":   args.get("thread_id"),
                "in_reply_to": args.get("in_reply_to"),  # RFC 2822 threading header
                "references":  args.get("references"),   # RFC 2822 references chain
                "session_id":  args.get("session_id")
            }, timeout=TIMEOUT)
            result = r.json()
            print(f"  📧 Sent to: {args['to_emails']}")
            # Note: ctx flags for early-exit are now set exclusively by mark_done.
            return result

        elif name == "fetch_thread":
            r = httpx.post(f"{GMAIL_MCP}/thread/fetch", json={
                "thread_id":    args["thread_id"],
                "max_messages": args.get("max_messages", 20)
            }, timeout=TIMEOUT)
            return r.json()

        elif name == "detect_intent":
            r = httpx.post(f"{GMAIL_MCP}/intent/detect", json={
                "subject":   args["subject"],
                "body_text": args["body_text"],
                "thread_id": args.get("thread_id")
            }, timeout=TIMEOUT)
            return r.json()

        elif name == "mark_done":
            action_type = args.get("action_type", "no_action_needed")
            summary     = args.get("summary", "")
            ctx["done"]        = True
            ctx["action_type"] = action_type
            print(f"\n  ✅ mark_done: {action_type}")
            if summary:
                print(f"     {summary}")
            return {"status": "done", "action_type": action_type}

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"error": str(e)}

# ================================================================
# AGENT LOOP
# ================================================================

def run_agent(situation: dict):
    print("\n" + "="*60)
    print("  CalSync.ai Agent  |  Gemini 2.5 Flash")
    print("="*60)
    print(f"  Meeting  : {situation.get('meeting_title')}")
    print(f"  Organizer: {situation.get('organizer')}")
    print(f"  Status   : {situation.get('status')}")
    print("="*60)

    ctx    = {}
    status = situation.get("status","")

    if status == "AWAITING_REPLIES":
        prompt = f"""New scheduling request. Send availability request emails to all participants (not the organizer).

Situation:
{json.dumps(situation, indent=2)}

Write professional availability request emails. Include meeting title, 24-hour deadline, and ask for specific dates and times."""

    elif status == "READY_TO_COMPUTE":
        prompt = f"""All participants replied. Complete the booking flow.

Situation:
{json.dumps(situation, indent=2)}

Steps:
1. check_freebusy for all proposed_slots
2. book_meeting on first free slot
3. send_email confirmation to ALL participants with time in IST, event link, Meet link"""

    elif status == "NO_OVERLAP":
        prompt = f"""No overlapping slots found.

Situation:
{json.dumps(situation, indent=2)}

Send clarification emails to all participants explaining no common slot was found and asking for more availability."""

    else:
        prompt = f"Handle this scheduling situation:\n{json.dumps(situation, indent=2)}"

    # Build conversation history
    contents = [
        types.Content(role="user", parts=[types.Part(text=prompt)])
    ]

    for step in range(1, 11):
        print(f"\n[Step {step}] Calling Gemini...")

        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM,
                tools=TOOLS,
                temperature=0
            )
        )

        # Add model response to history
        contents.append(
            types.Content(role="model", parts=response.candidates[0].content.parts)
        )

        # Extract function calls
        fn_calls = [
            p.function_call
            for p in response.candidates[0].content.parts
            if hasattr(p, "function_call") and p.function_call
        ]

        if not fn_calls:
            text = "".join(
                p.text for p in response.candidates[0].content.parts
                if hasattr(p,"text") and p.text
            )
            if text:
                print(f"\n  Agent: {text}")
            print("\n" + "="*60)
            print("✅ Agent completed.")
            print("="*60)
            break

        # Execute tool calls and collect responses
        tool_parts = []
        for fn in fn_calls:
            result = execute_tool(fn.name, dict(fn.args), ctx)
            print(f"  ✓ Result: {json.dumps(result, indent=4)[:300]}")
            tool_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fn.name,
                        response={"result": result}
                    )
                )
            )

        contents.append(
            types.Content(role="user", parts=tool_parts)
        )

        # ── Early exit: mark_done was called ─────────────────────────────────
        if ctx.get("done"):
            action = ctx.get("action_type", "")
            print("\n" + "="*60)
            if action == "meeting_booked_and_confirmed":
                print("✅ Full scheduling flow complete!")
                print(f"   Event: {ctx.get('event_link')}")
                print(f"   Meet:  {ctx.get('meet_link')}")
            elif action == "availability_requested":
                print("✅ Availability requests sent. Waiting for replies.")
            elif action == "clarification_sent":
                print("✅ Clarification emails sent.")
            else:
                print(f"✅ Agent completed: {action}")
            print("="*60)
            break

    else:
        print("\n⚠️  Max steps reached.")


# ================================================================
# SCENARIOS
# ================================================================

if __name__ == "__main__":
    scenario = sys.argv[1] if len(sys.argv) > 1 else "1"

    if scenario == "1":
        situation = {
            "meeting_title": "INSPIRON 5.0 Final Demo Prep",
            "organizer":     "ameyapict@gmail.com",
            "participants": [
                "ameyapict@gmail.com",
                "ameyans0905@gmail.com",
                "samhp924@gmail.com",
                "konarknehetepict@gmail.com"
            ],
            "session_id":   "sess_test02",
            "status":       "READY_TO_COMPUTE",
            "all_replied":  True,
            "proposed_slots": [
                {"start": "2025-04-20T05:30:00Z", "end": "2025-04-20T07:00:00Z"},
                {"start": "2025-04-21T05:00:00Z", "end": "2025-04-21T06:30:00Z"},
                {"start": "2025-04-22T06:00:00Z", "end": "2025-04-22T07:30:00Z"}
            ]
        }

    elif scenario == "2":
        situation = {
            "meeting_title": "Q1 Sprint Planning",
            "organizer":     "ameyapict@gmail.com",
            "participants": [
                "ameyans0905@gmail.com",
                "samhp924@gmail.com",
                "konarknehetepict@gmail.com"
            ],
            "session_id":  "sess_test01",
            "status":      "AWAITING_REPLIES",
            "all_replied": False
        }

    elif scenario == "3":
        situation = {
            "meeting_title": "Code Review Session",
            "organizer":     "ameyans0905@gmail.com",
            "participants": [
                "ameyans0905@gmail.com",
                "samhp924@gmail.com",
                "konarknehetepict@gmail.com"
            ],
            "session_id":        "sess_test04",
            "status":            "NO_OVERLAP",
            "all_replied":       True,
            "no_overlap_reason": "samhp924 free 9:30-11:30 AM IST only. konark free 6:30-8:30 PM IST only. No common window."
        }

    else:
        print("Usage: python agent.py [1|2|3]")
        sys.exit(1)

    run_agent(situation)
