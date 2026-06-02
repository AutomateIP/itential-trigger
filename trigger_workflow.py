"""
trigger_workflow.py — Trigger an Itential Operations Manager workflow via the API.

Supports basic auth and OAuth (client credentials). Auth mode is auto-detected
from the .env file: set ITENTIAL_CLIENT_ID + ITENTIAL_CLIENT_SECRET for OAuth,
or ITENTIAL_USER + ITENTIAL_PASSWORD for basic auth.

Usage:
    python trigger_workflow.py <trigger_name> [payload_json] [--wait] [--poll-interval N]

Examples:
    python trigger_workflow.py my-workflow-route
    python trigger_workflow.py my-workflow-route '{"device": "router1"}'
    python trigger_workflow.py my-workflow-route '{"devices": [{"name": "r1", "ip": "10.0.0.1"}], "options": {"dry_run": false}}'
    python trigger_workflow.py my-workflow-route '{"device": "router1"}' --wait
    python trigger_workflow.py my-workflow-route '{"device": "router1"}' --wait --poll-interval 5
"""

import argparse
import asyncio
import json
import os
import sys

import ipsdk
from dotenv import load_dotenv
from ipsdk.http import HTTPMethod

TERMINAL_STATUSES = {"complete", "error", "cancelled", "canceled", "failed"}

# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------

def load_env() -> dict:
    """Load credentials from .env and auto-detect auth mode.

    OAuth is used when ITENTIAL_CLIENT_ID + ITENTIAL_CLIENT_SECRET are set.
    Basic auth is used when ITENTIAL_USER + ITENTIAL_PASSWORD are set.
    Both being set is an error; neither being set is an error.
    """
    load_dotenv()

    host = os.getenv("ITENTIAL_HOST")
    if not host:
        print("ERROR: Missing required environment variable: ITENTIAL_HOST")
        print("Copy .env.example to .env and fill in the values.")
        sys.exit(1)

    client_id = os.getenv("ITENTIAL_CLIENT_ID", "")
    client_secret = os.getenv("ITENTIAL_CLIENT_SECRET", "")
    user = os.getenv("ITENTIAL_USER", "")
    password = os.getenv("ITENTIAL_PASSWORD", "")

    has_oauth = bool(client_id and client_secret)
    has_basic = bool(user and password)

    if has_oauth and has_basic:
        print("ERROR: Both OAuth (ITENTIAL_CLIENT_ID/SECRET) and basic auth (ITENTIAL_USER/PASSWORD) are set.")
        print("Set only one auth method.")
        sys.exit(1)

    if not has_oauth and not has_basic:
        print("ERROR: No auth credentials found. Set one of:")
        print("  OAuth:      ITENTIAL_CLIENT_ID + ITENTIAL_CLIENT_SECRET")
        print("  Basic auth: ITENTIAL_USER + ITENTIAL_PASSWORD")
        sys.exit(1)

    auth_mode = "oauth" if has_oauth else "basic"
    print(f"Auth mode: {auth_mode}")

    return {
        "host": host,
        "port": int(os.getenv("ITENTIAL_PORT", "443")),
        "use_tls": os.getenv("ITENTIAL_USE_TLS", "true").lower() == "true",
        "verify": os.getenv("ITENTIAL_VERIFY_TLS", "true").lower() == "true",
        "user": user or None,
        "password": password or None,
        "client_id": client_id or None,
        "client_secret": client_secret or None,
        "timeout": int(os.getenv("ITENTIAL_TIMEOUT", "30")),
    }


# ---------------------------------------------------------------------------
# Async trigger logic
# ---------------------------------------------------------------------------

async def trigger_workflow(
    config: dict,
    trigger_name: str,
    payload: dict | None,
    wait: bool = False,
    poll_interval: int = 3,
) -> None:
    """Authenticate, POST to the trigger endpoint, and print the result."""
    client = ipsdk.platform_factory(
        want_async=True,
        host=config["host"],
        port=config["port"],
        use_tls=config["use_tls"],
        verify=config["verify"],
        user=config["user"],
        password=config["password"],
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        timeout=config["timeout"],
        ttl=0,
    )

    endpoint = f"/operations-manager/triggers/endpoint/{trigger_name}"

    print(f"Triggering: POST {endpoint}")
    if payload is not None:
        print(f"Payload: {json.dumps(payload, indent=2)}")
    print()

    try:
        res = await client._send_request(HTTPMethod.POST, endpoint, None, payload)
    except Exception as exc:
        print(f"ERROR: Connection failed — {exc}")
        sys.exit(1)

    if res.status_code >= 400:
        print(f"ERROR: HTTP {res.status_code}")
        try:
            print(json.dumps(res.json(), indent=2))
        except Exception:
            print(res.text)
        sys.exit(1)

    try:
        result = res.json()
    except Exception:
        print(res.text)
        return

    job = result.get("data", result)
    job_id = job.get("_id")

    if not wait or not job_id:
        print(json.dumps(result, indent=2))
        return

    # Poll until the job reaches a terminal status
    print(f"Job ID: {job_id}")
    print(f"Polling every {poll_interval}s for completion...\n")

    while True:
        await asyncio.sleep(poll_interval)

        try:
            poll_res = await client._send_request(
                HTTPMethod.GET, f"/operations-manager/jobs/{job_id}", None, None
            )
        except Exception as exc:
            print(f"ERROR: Poll request failed — {exc}")
            sys.exit(1)

        if poll_res.status_code >= 400:
            print(f"ERROR: HTTP {poll_res.status_code} while polling job {job_id}")
            try:
                print(json.dumps(poll_res.json(), indent=2))
            except Exception:
                print(poll_res.text)
            sys.exit(1)

        try:
            poll_data = poll_res.json().get("data", {})
        except Exception:
            print(poll_res.text)
            sys.exit(1)

        status = poll_data.get("status", "unknown")
        print(f"  status: {status}")

        if status.lower() in TERMINAL_STATUSES:
            print()
            print(json.dumps(poll_data, indent=2))
            break


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trigger an Itential Operations Manager workflow endpoint.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python trigger_workflow.py my-workflow-route
  python trigger_workflow.py my-workflow-route '{"device": "router1"}'
  python trigger_workflow.py my-workflow-route '{"devices": [{"name": "r1"}], "options": {"dry_run": false}}'
  python trigger_workflow.py my-workflow-route '{"device": "router1"}' --wait
  python trigger_workflow.py my-workflow-route '{"device": "router1"}' --wait --poll-interval 5
        """,
    )
    parser.add_argument(
        "trigger_name",
        help="The Operations Manager trigger route name (endpoint path segment).",
    )
    parser.add_argument(
        "payload",
        nargs="?",
        default=None,
        help="Optional JSON string to send as the request body.",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        default=False,
        help="Block until the job reaches a terminal status (complete/error/cancelled).",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=10,
        metavar="SECONDS",
        help="Seconds between job status polls when --wait is set (default: 10).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Parse the optional payload JSON string
    payload_dict = None
    if args.payload is not None:
        try:
            payload_dict = json.loads(args.payload)
        except json.JSONDecodeError as exc:
            print(f"ERROR: Invalid JSON in payload argument — {exc}")
            sys.exit(1)

    config = load_env()
    asyncio.run(trigger_workflow(config, args.trigger_name, payload_dict, args.wait, args.poll_interval))


if __name__ == "__main__":
    main()
