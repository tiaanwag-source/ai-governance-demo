<script lang="ts">
  import { onMount } from "svelte";

  type PipelineStep = {
    id: string;
    stepLabel: string;
    title: string;
    description: string;
    endpoint: string;
    buttonText: string;
    danger?: boolean;
  };

  const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
  const DEFAULT_AGENT =
    "projects/acme-ml-dev/locations/us-central1/agents/019c163c";

  type ActionPolicy = {
    id: number;
    action_name: string;
  };

  const steps: PipelineStep[] = [
    {
      id: "generate",
      stepLabel: "Step 1",
      title: "Generate synthetic logs",
      description: "Reset the registry and synthesize fresh Vertex + Copilot logs.",
      endpoint: "/demo/generate_logs",
      buttonText: "Generate logs"
    },
    {
      id: "adapter",
      stepLabel: "Step 2",
      title: "Run adapter (upload to registry)",
      description: "Normalize the logs and register agents in the canonical store.",
      endpoint: "/demo/run_adapter",
      buttonText: "Run adapter"
    },
    {
      id: "score",
      stepLabel: "Step 3",
      title: "Apply risk scoring",
      description: "Derive data_class/output_scope/autonomy/reach/tools and compute red/amber/green bands.",
      endpoint: "/demo/apply_scoring",
      buttonText: "Apply scoring"
    },
    {
      id: "flag",
      stepLabel: "Step 4",
      title: "Flag high-risk agents",
      description: "Promote a small sample of agents into red-band overrides so approvals/watchdog have targets.",
      endpoint: "/demo/flag_high_risk",
      buttonText: "Flag high-risk"
    },
    {
      id: "sdk",
      stepLabel: "Step 5",
      title: "SDK approvals",
      description: "Trigger the safeguard logic so pending approvals (with prompts) show up in the console.",
      endpoint: "/demo/sdk_seed",
      buttonText: "Seed approvals"
    },
    {
      id: "drift",
      stepLabel: "Step 6",
      title: "Simulate agent drift",
      description: "Flip a trusted agent into an unsafe configuration so the watchdog has something to catch.",
      endpoint: "/demo/simulate_drift",
      buttonText: "Simulate drift"
    },
    {
      id: "watchdog",
      stepLabel: "Step 7",
      title: "Run watchdog",
      description: "Re-score agents, log the drift detection, and record a watchdog run entry.",
      endpoint: "/demo/watchdog",
      buttonText: "Run watchdog"
    },
    {
      id: "reset",
      stepLabel: "Step 8",
      title: "Reset demo",
      description: "Clear synthetic logs, approvals, and risk state so you can rerun the pipeline end-to-end.",
      endpoint: "/demo/clear",
      buttonText: "Clear everything",
      danger: true
    }
  ];

  let stepStatus: Record<string, { message: string; tone: "info" | "success" | "error" }> =
    {};

  let actions: ActionPolicy[] = [];
  let actionAgents: Record<string, string[]> = {};
  let sdkAction = "";
  let sdkAgentId = DEFAULT_AGENT;
  let sdkBusy = false;
  let sdkResult: string | null = null;
  let sdkError: string | null = null;

  onMount(async () => {
    await loadActions();
    await loadActionAgents();
  });

  async function loadActions() {
    try {
      const resp = await fetch(`${API_BASE}/policies/actions`);
      if (!resp.ok) {
        throw new Error(`Failed to load actions (${resp.status})`);
      }
      const payload: ActionPolicy[] = await resp.json();
      actions = payload;
      if (!sdkAction && actions.length) {
        sdkAction = actions[0].action_name;
      }
    } catch (err) {
      console.error("loadActions failed", err);
    }
  }

  async function loadActionAgents() {
    try {
      const resp = await fetch(`${API_BASE}/admin/metrics`);
      if (!resp.ok) {
        throw new Error(`Failed to load metrics (${resp.status})`);
      }
      const payload = await resp.json();
      const map: Record<string, string[]> = {};
      const impacts = payload.action_policy_impacts ?? [];
      for (const row of impacts) {
        const bucket = new Set<string>();
        (row.pending_agents ?? []).forEach((id: string) => {
          if (id) bucket.add(id);
        });
        (row.recent_agents ?? []).forEach((id: string) => {
          if (id) bucket.add(id);
        });
        if (bucket.size) {
          map[row.action_name] = Array.from(bucket);
        }
      }
      actionAgents = map;
      if ((!sdkAgentId || sdkAgentId === DEFAULT_AGENT) && sdkAction && map[sdkAction]?.length) {
        sdkAgentId = map[sdkAction][0];
      }
    } catch (err) {
      console.error("loadActionAgents failed", err);
    }
  }

  async function runSdkCheck() {
    if (!sdkAction) return;
    sdkBusy = true;
    sdkResult = null;
    sdkError = null;
    try {
      const resp = await fetch(`${API_BASE}/sdk/check_and_header`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_id: sdkAgentId,
          action: sdkAction,
          prompt: `Demo request exercising ${sdkAction}`,
          metadata: { channel: "demo", contains_pii: true },
          requested_by: "demo.pipeline@acme.example"
        })
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || `HTTP ${resp.status}`);
      }
      const json = await resp.json();
      sdkResult = JSON.stringify(json, null, 2);
    } catch (err: any) {
      sdkError = err?.message ?? "SDK call failed";
    } finally {
      sdkBusy = false;
    }
  }

  async function runStep(step: PipelineStep) {
    stepStatus = {
      ...stepStatus,
      [step.id]: { message: "Running…", tone: "info" }
    };
    try {
      const resp = await fetch(`${API_BASE}${step.endpoint}`, {
        method: "POST"
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || `HTTP ${resp.status}`);
      }
      const payload = await resp.json();
      stepStatus = {
        ...stepStatus,
        [step.id]: {
          message: JSON.stringify(payload),
          tone: "success"
        }
      };
    } catch (error: any) {
      stepStatus = {
        ...stepStatus,
        [step.id]: {
          message: error?.message ?? "Step failed",
          tone: "error"
        }
      };
    }
  }
</script>

<section
  style="
    padding:24px;
    color:#e5e7eb;
    font-family: system-ui, -apple-system, Segoe UI, sans-serif;
  "
>
  <h1 style="margin:0 0 8px; font-size:26px;">Pipeline runbook</h1>
  <p style="color:#94a3b8; margin:0 0 16px;">
    End-to-end instructions for replaying logs, recomputing signals, and exercising the SDK safety checks.
  </p>
  <div
    style="
      border:1px solid #1f2937;
      border-radius:10px;
      padding:12px 14px;
      margin-bottom:18px;
      background:#0f172a;
      font-size:13px;
      color:#cbd5f5;
    "
  >
    Tip: you can also run <code>python tools/run_demo_pipeline.py</code> from the repo
    root to execute every step in one go.
  </div>

  <div
    style="
      display:grid;
      grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
      gap:16px;
    "
  >
    {#each steps as step}
      <article
        style="
          border:1px solid #1f2937;
          border-radius:12px;
          padding:16px;
          background:#020617;
        "
      >
        <div style="font-size:11px; color:#9ca3af; letter-spacing:0.08em;">
          {step.stepLabel}
        </div>
        <h2 style="margin:4px 0 8px; font-size:18px;">{step.title}</h2>
        <p style="color:#94a3b8; font-size:13px; min-height:72px;">
          {step.description}
        </p>
        <button
          on:click={() => runStep(step)}
          style={`
            margin-top:12px;
            width:100%;
            padding:10px 12px;
            border-radius:8px;
            border:1px solid ${step.danger ? "#b91c1c" : "#374151"};
            background:${step.danger ? "#7f1d1d" : "#111827"};
            color:#e5e7eb;
            cursor:pointer;
          `}
        >
          {step.buttonText}
        </button>
        {#if stepStatus[step.id]}
          <div
            style={`
              margin-top:10px;
              font-size:12px;
              padding:8px;
              border-radius:8px;
              background:${
                stepStatus[step.id].tone === "success"
                  ? "#022c22"
                  : stepStatus[step.id].tone === "error"
                    ? "#450a0a"
                    : "#0f172a"
              };
              border:1px solid ${
                stepStatus[step.id].tone === "success"
                  ? "#14532d"
                  : stepStatus[step.id].tone === "error"
                    ? "#b91c1c"
                    : "#1f2937"
              };
            `}
          >
            {stepStatus[step.id].message}
          </div>
        {/if}
      </article>
    {/each}
  </div>

  <section
    style="
      margin-top:32px;
      border:1px solid #1f2937;
      border-radius:12px;
      padding:20px;
      background:#020617;
      color:#e5e7eb;
    "
  >
    <h2 style="margin:0 0 8px; font-size:20px;">SDK policy tester</h2>
    <p style="margin:0 0 16px; color:#9ca3af; font-size:13px;">
      Pick any action verb discovered in the pipeline and call <code>/sdk/check_and_header</code>
      directly. This lets you prove the Allow/Approval toggles on the Policies tab actually gate the request.
    </p>
    {#if actions.length === 0}
      <p style="color:#94a3b8;">
        No actions yet. Run Steps 1‑3 above, then refresh this page.
      </p>
    {:else}
      <div
        style="
          display:flex;
          flex-wrap:wrap;
          gap:12px;
          align-items:flex-end;
          margin-bottom:16px;
        "
      >
        <label style="display:flex; flex-direction:column; font-size:13px; flex:1; min-width:200px;">
          Action verb
          <select
            bind:value={sdkAction}
            on:change={() => {
              const options = actionAgents[sdkAction];
              if (options && options.length) {
                sdkAgentId = options[0];
              }
            }}
            style="
              margin-top:4px;
              padding:8px;
              border-radius:8px;
              border:1px solid #374151;
              background:#020617;
              color:#e5e7eb;
            "
          >
            {#each actions as action}
              <option value={action.action_name}>{action.action_name}</option>
            {/each}
          </select>
        </label>
        <label style="display:flex; flex-direction:column; font-size:13px; flex:1; min-width:220px;">
          Agents that invoked this action
          <select
            disabled={!actionAgents[sdkAction] || actionAgents[sdkAction].length === 0}
            on:change={(event) => (sdkAgentId = (event.target as HTMLSelectElement).value)}
            style="
              margin-top:4px;
              padding:8px;
              border-radius:8px;
              border:1px solid #374151;
              background:#020617;
              color:#e5e7eb;
            "
          >
            {#if actionAgents[sdkAction] && actionAgents[sdkAction].length > 0}
              {#each actionAgents[sdkAction] as agent}
                <option value={agent} selected={agent === sdkAgentId}>{agent}</option>
              {/each}
            {:else}
              <option value="" disabled selected>
                No recent agents yet
              </option>
            {/if}
          </select>
        </label>
        <label style="display:flex; flex-direction:column; font-size:13px; flex:1; min-width:260px;">
          Agent ID
          <input
            type="text"
            bind:value={sdkAgentId}
            style="
              margin-top:4px;
              padding:8px;
              border-radius:8px;
              border:1px solid #374151;
              background:#020617;
              color:#e5e7eb;
            "
          />
        </label>
        <button
          on:click={runSdkCheck}
          disabled={sdkBusy}
          style="
            padding:10px 16px;
            border-radius:8px;
            border:1px solid #374151;
            background:#111827;
            color:#e5e7eb;
            cursor:pointer;
            min-width:160px;
          "
        >
          {#if sdkBusy}
            Calling…
          {:else}
            Run SDK check
          {/if}
        </button>
      </div>
      {#if sdkError}
        <div
          style="
            border:1px solid #b91c1c;
            background:#450a0a;
            border-radius:8px;
            padding:10px;
            font-size:13px;
            margin-bottom:12px;
          "
        >
          {sdkError}
        </div>
      {/if}
      {#if sdkResult}
        <pre
          style="
            background:#0f172a;
            border:1px solid #1f2937;
            border-radius:8px;
            padding:12px;
            font-size:12px;
            overflow:auto;
            max-height:240px;
          "
        >{sdkResult}</pre>
      {/if}
    {/if}
  </section>
</section>
