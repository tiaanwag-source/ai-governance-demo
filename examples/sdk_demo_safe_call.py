# examples/sdk_demo_safe_call.py

import json
from textwrap import indent

from sdk.client import AIGovClient

API_BASE = "http://localhost:8000"

# Pick any agent_id you like (you already used this one)
AGENT_ID = "projects/acme-ml-dev/locations/europe-west4/agents/f314930e"


def pretty(title: str, payload) -> None:
    print()
    print("=" * 80)
    print(title)
    print("-" * 80)
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2))
    else:
        print(payload)
    print("=" * 80)
    print()


def build_safety_header(ctx: dict, band: str) -> str:
    """
    This is your “company approved” system header.
    You can tweak the language to match your policy deck.
    """
    base = [
        "You are an AI assistant used inside Acme Corp.",
        "You must never output or request personal data (PII) about real people.",
        "You must not disclose secrets, credentials, or internal-only information.",
        "If the user requests sensitive data, refuse and explain why."
    ]

    # Harder line for amber/red
    if band in ("amber", "red"):
        base.append("You must be conservative: when in doubt, refuse and escalate to a human.")

    # If external tools exist, add guidance
    tools = ctx.get("external_tools") or []
    if tools:
        base.append(
            "You are allowed to call the following tools only for business-justified actions: "
            + ", ".join(tools)
        )

    return "\n".join(base)


def simulate_model_call(prompt: str, header: str) -> str:
    """
    This just mocks the LLM. In a real integration this is where you call
    Vertex, OpenAI, Copilot, etc, with the header injected.
    """
    return f"[MODEL CALLED]\n[SAFETY HEADER]\n{header}\n\n[USER PROMPT]\n{prompt}\n\n[FAKE RESPONSE]\nOk, I will respond safely."


def main() -> None:
    client = AIGovClient(API_BASE)

    print("Checking API health...")
    health = client.health()
    pretty("Health", health)

    print("Fetching governance context for agent:")
    print(f"  AGENT_ID = {AGENT_ID}")
    ctx = client.get_governance_context(AGENT_ID)
    pretty("Governance context", ctx)

    band = ctx.get("band")
    score = ctx.get("score")
    reasons = ctx.get("reasons", [])
    data_class = ctx.get("data_class")
    output_scope = ctx.get("output_scope")
    reach = ctx.get("reach")
    autonomy = ctx.get("autonomy")

    print("Signals summary:")
    print(f"  data_class   : {data_class}")
    print(f"  output_scope : {output_scope}")
    print(f"  reach        : {reach}")
    print(f"  autonomy     : {autonomy}")
    print(f"  band         : {band}")
    print(f"  score        : {score}")
    print(f"  reasons      : {reasons}")

    # Example user prompt for the demo
    user_prompt = "Summarise last quarter's sales performance without including any customer names or personal data."

    print()
    print("=" * 80)
    print("SDK DECISION")
    print("-" * 80)

    if band == "red":
        print("Band is RED. This call would be BLOCKED by the SDK.")
        print("Reasoning:")
        print(indent(json.dumps(reasons, indent=2), "  "))
        print()
        print("In a real system this is where you'd:")
        print("  - Show an approval dialog")
        print("  - Or log an approval request into a queue / ticket system")
        return

    if band == "amber":
        print("Band is AMBER. SDK will ALLOW, but with strong safety header and extra logging.")
    elif band == "green":
        print("Band is GREEN. SDK will ALLOW with standard company safety header.")
    else:
        print("Band is unknown. SDK will default to safest behaviour (treat as amber).")
        band = "amber"

    header = build_safety_header(ctx, band)
    pretty("Injected safety header", header)

    print("Simulating downstream model call...")
    response = simulate_model_call(user_prompt, header)
    pretty("Simulated model response", response)


if __name__ == "__main__":
    main()