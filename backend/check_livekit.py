"""
Check that LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET actually belong
together.

"invalid token" from the browser means LiveKit refused a token this backend
signed. The token code itself is rarely the problem. Far more often the key and
secret are from a DIFFERENT LiveKit project than the URL points at, because
LiveKit issues keys per project and it is easy to mix two projects' values.

This script signs nothing for the browser. It calls LiveKit's management API
directly with the same three values, which fails loudly and specifically when
they do not match.

Run it from the backend folder:

    cd backend
    .venv\\Scripts\\python.exe check_livekit.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def describe(name: str, value: str | None, *, secret: bool = False) -> str | None:
    """Report a value without printing a secret, and flag the usual copy slips."""
    if not value:
        print(f"  {name:<22} MISSING")
        return None

    shown = f"{value[:6]}...{value[-4:]}" if secret and len(value) > 12 else value
    notes = []

    if value != value.strip():
        notes.append("HAS LEADING OR TRAILING WHITESPACE")
    if value.startswith(('"', "'")) or value.endswith(('"', "'")):
        notes.append("WRAPPED IN QUOTES, remove them")

    suffix = "   <-- " + "; ".join(notes) if notes else ""
    print(f"  {name:<22} {shown}   ({len(value)} chars){suffix}")
    return value.strip().strip("\"'")


async def main() -> int:
    print("\nValues found in backend/.env")
    print("-" * 70)

    url = describe("LIVEKIT_URL", os.environ.get("LIVEKIT_URL"))
    key = describe("LIVEKIT_API_KEY", os.environ.get("LIVEKIT_API_KEY"))
    secret = describe("LIVEKIT_API_SECRET", os.environ.get("LIVEKIT_API_SECRET"), secret=True)

    if not (url and key and secret):
        print("\nFill in the missing values in backend/.env, then run this again.\n")
        return 1

    print()

    # Shape checks before the network call, because a wrong shape has a clearer
    # cause than a 401 does.
    if not key.startswith("API"):
        print("  [warn] LIVEKIT_API_KEY does not start with 'API'. LiveKit Cloud keys")
        print("         always do. You may have pasted the secret into the key field.")
    if len(secret) < 30:
        print("  [warn] LIVEKIT_API_SECRET looks short. LiveKit secrets are long.")
        print("         You may have pasted the key into the secret field.")

    # The realtime URL is wss://; the management API is the same host over https.
    http_url = url.replace("wss://", "https://").replace("ws://", "http://")

    print(f"Asking {http_url} whether these credentials are valid...\n")

    from livekit import api  # imported here so the checks above run even if it is missing

    client = api.LiveKitAPI(url=http_url, api_key=key, api_secret=secret)
    try:
        rooms = await client.room.list_rooms(api.ListRoomsRequest())
    except Exception as exc:  # noqa: BLE001 - the provider's own words are the point
        message = str(exc)
        print("  RESULT: REJECTED")
        print(f"  LiveKit said: {message}\n")

        if "401" in message or "unauthorized" in message.lower() or "invalid" in message.lower():
            print("  That is an authentication failure, which means this key and secret")
            print("  are not valid for the project at LIVEKIT_URL.\n")
            print("  Fix it in the LiveKit Cloud console:")
            print("    1. Check the project name in the top left corner.")
            print("    2. Settings, then Keys. Confirm the key shown there matches")
            print("       the LIVEKIT_API_KEY above, character for character.")
            print("    3. If it does not, you are looking at a different project than")
            print("       your URL points at. Either switch projects, or generate a")
            print("       new key HERE and copy both halves into backend/.env.")
            print("    4. The secret is shown ONCE, when the key is created. If you")
            print("       no longer have it, create a new key rather than guessing.")
            print("    5. Put the same three values in agent/.env too.\n")
        else:
            print("  That does not look like an auth failure. Check the URL is reachable")
            print("  and that you are online.\n")
        return 1
    finally:
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001 - closing is best effort
            pass

    print("  RESULT: VALID")
    print(f"  These credentials work. LiveKit reports {len(rooms.rooms)} active room(s).\n")
    print("  So the problem is not the key and secret. Next things to check:")
    print("    - agent/.env has these SAME three values")
    print("    - your laptop clock is correct; tokens carry a timestamp and a")
    print("      clock off by more than a minute or two invalidates them")
    print("    - the backend window was restarted after you last edited .env\n")

    # ---- Phone path: does the outbound SIP trunk exist? --------------------
    trunk_id = (os.environ.get("LIVEKIT_SIP_TRUNK_ID") or "").strip()
    from_number = (os.environ.get("PLIVO_FROM_NUMBER") or "").strip()
    print("Phone path (docs/PHONE.md)")
    print("-" * 70)
    if not trunk_id:
        print("  LIVEKIT_SIP_TRUNK_ID is blank: browser calls only. Fine for now.\n")
        return 0

    client = api.LiveKitAPI(url=http_url, api_key=key, api_secret=secret)
    try:
        # Newer livekit-api renamed this; use whichever the installed one has.
        if hasattr(client.sip, "list_outbound_trunk"):
            listing = await client.sip.list_outbound_trunk(api.ListSIPOutboundTrunkRequest())
        else:
            listing = await client.sip.list_sip_outbound_trunk(api.ListSIPOutboundTrunkRequest())
    except Exception as exc:  # noqa: BLE001
        print(f"  Could not list SIP trunks: {exc}\n")
        return 1
    finally:
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001
            pass

    trunks = {t.sip_trunk_id: t for t in listing.items}
    if trunk_id not in trunks:
        print(f"  LIVEKIT_SIP_TRUNK_ID={trunk_id} NOT FOUND in this project.")
        if trunks:
            print("  Trunks that do exist here:")
            for t in trunks.values():
                print(f"    {t.sip_trunk_id}  {t.name}  -> {t.address}")
        else:
            print("  This project has no outbound trunks yet. Create one: docs/PHONE.md step 2.")
        print()
        return 1

    t = trunks[trunk_id]
    print(f"  Trunk {t.sip_trunk_id} ({t.name}) -> {t.address}")
    if "plivo" not in t.address:
        print("  [warn] address does not look like a Plivo termination domain (*.zt.plivo.com)")
    if not t.auth_username:
        print("  [warn] trunk has no auth_username; Plivo will refuse the calls")
    if from_number and from_number not in list(t.numbers):
        print(f"  [warn] PLIVO_FROM_NUMBER {from_number} is not in the trunk's numbers {list(t.numbers)}")
    print("  Trunk looks usable. Next: CALL_TRANSPORT=phone, TELEPHONY_ENABLED=true, restart, test.\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
