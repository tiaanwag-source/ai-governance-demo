# examples/sdk_demo_governance.py

import json
import textwrap

from sdk.client import AIGovClient

API_BASE = "http://localhost:8000"

# You can change this to any agent_id you like
AGENT_ID = "projects/acme-ml-dev/locations/europe-west4/agents/f314930e"


def pretty_block(title: str, payload) -> None:
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


def main() -> None:
    client = AIGovClient(API_BASE)

    # 1. Health
    print("Checking API health...")
    health = client.health()
    pretty_block("Health", health)

    # 2. Registry metrics
    metrics = client.get_metrics()
    pretty_block("Registry metrics (/admin/metrics)", metrics)

    # 3. Governance context for one agent
    print("Fetching governance context for agent:")
    print(f"  AGENT_ID = {AGENT_ID}")
    ctx = client.get_governance_context(AGENT_ID)
    pretty_block("Governance context for agent", ctx)

    # 4. Human readable summary from the flattened fields
    data_class = ctx.get("data_class")
    output_scope = ctx.get("output_scope")
    reach = ctx.get("reach")
    autonomy = ctx.get("autonomy")
    external_tools = ctx.get("external_tools")

    band = ctx.get("band")
    score = ctx.get("score")
    reasons = ctx.get("reasons")

    print("Signals summary:")
    print(f"  data_class    : {data_class}")
    print(f"  output_scope  : {output_scope}")
    print(f"  reach         : {reach}")
    print(f"  autonomy      : {autonomy}")
    print(f"  external_tools: {external_tools}")

    print()
    print("Risk summary:")
    print(f"  band          : {band}")
    print(f"  score         : {score}")
    print(f"  reasons       : {reasons}")

    # 5. Example of how an SDK would decide what to do
    print()
    print("SDK decision example:")
    if band == "red":
        print("  -> Block or require human approval before calling the model.")
    elif band == "amber":
        print("  -> Allow, but with strong safety header and logging.")
    elif band == "green":
        print("  -> Allow with standard company safety header.")
    else:
        print("  -> No band available, fall back to safest behaviour.")


if __name__ == "__main__":
    main()