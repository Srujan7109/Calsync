"""
Run: python debug_poller.py
Shows exactly what the Gmail MCP is returning and why replies aren't processing.
"""
import asyncio
import httpx

GMAIL_MCP = "http://127.0.0.1:8006"
CALSYNC = "calsync1.ai@gmail.com"

async def main():
    async with httpx.AsyncClient(timeout=15) as c:
        # 1. What does the inbox query actually return?
        print("=== INBOX EMAILS (raw) ===")
        r = await c.get(f"{GMAIL_MCP}/messages/unread")
        msgs = r.json() if r.status_code == 200 else []
        print(f"Total fetched: {len(msgs)}")
        for m in msgs:
            print(f"  id={m.get('id')} from={m.get('from_email')} subject={m.get('subject','')[:60]} labels={m.get('labels')}")

        # 2. Check for ref in bodies
        print("\n=== CHECKING BODIES FOR CALSYNC-REF ===")
        for m in msgs:
            body = m.get("body_text", "") or m.get("snippet", "")
            has_ref = "[calsync-ref:" in body
            print(f"  from={m.get('from_email')} ref_in_body={has_ref} body_preview={body[:80]!r}")

asyncio.run(main())