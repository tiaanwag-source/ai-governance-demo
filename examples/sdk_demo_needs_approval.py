from __future__ import annotations

import json

from sdk.client import AIGovClient


def main() -> None:
    client = AIGovClient()

    # Replace with an agent_id from your registry
    agent_id = "projects/acme-ml-dev/locations/us-central1/agents/019c163c"

    resp = client.check_action(
        agent_id=agent_id,
        action="send_email",
        prompt="Draft an announcement that includes customer spend numbers.",
        metadata={"contains_pii": True, "channel": "email"},
        requested_by="ciso@acme.example",
    )

    print("=== SDK safeguard response ===")
    print(json.dumps(resp, indent=2))

    approval_id = resp.get("approval_id")
    approval_status = resp.get("approval_status")
    if resp.get("blocked"):
        print("\nAction blocked by policy.")
    elif resp.get("approval_required"):
        print("\nApproval required before proceeding.")
        if approval_id:
            print(f"  Pending approval id: {approval_id} (status={approval_status})")
    else:
        print("\nSafe to continue with system header injection.")

    print("\nSystem header to prepend:\n")
    print(resp.get("system_header", "<no-header>"))


if __name__ == "__main__":
    main()
