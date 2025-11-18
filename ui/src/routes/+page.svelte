<script lang="ts">
  import { onMount } from "svelte";
  import type {
    AdminMetrics,
    PolicyViolation,
    SdkCheckResponse,
    ApprovalSummary,
    ActionPolicyImpact
  } from "$lib/api";
  import {
    fetchAdminMetrics as getAdminMetrics,
    recomputeAllSignals,
    sdkCheck
  } from "$lib/api";

  type PipelineStep = {
    id: string;
    stepLabel: string;
    title: string;
    description: string;
    buttonLabel: string;
    note: string;
    action?: "recompute" | "sdk";
  };

  const DEFAULT_DEMO_AGENT =
    "projects/acme-ml-dev/locations/us-central1/agents/019c163c";
  const bandOrder = [
    { key: "green", label: "Green" },
    { key: "amber", label: "Amber" },
    { key: "red", label: "Red" }
  ] as const;

  const pipelineSteps: PipelineStep[] = [
    {
      id: "logs",
      stepLabel: "Step 1",
      title: "Generate synthetic logs",
      description: "Create Vertex + Copilot JSONL logs for the demo data lake.",
      buttonLabel: "Show command",
      note: "Run `python tools/generate_synthetic_logs.py` to write fresh vertex/copilot JSONL files into ./data/"
    },
    {
      id: "adapter",
      stepLabel: "Step 2",
      title: "Run adapter (upload to registry)",
      description: "Map raw logs into the canonical envelope and POST to /ingest/canonical.",
      buttonLabel: "Show command",
      note: "Use `docker compose run adapter_loader /data/vertex_big.jsonl /data/copilot_big.jsonl` to replay events into the API."
    },
    {
      id: "score",
      stepLabel: "Step 3",
      title: "Apply risk scoring",
      description: "Derive the five signals, recompute risk bands, and mirror them to agents.",
      buttonLabel: "Recompute now",
      note: "POST /admin/recompute_all to run See → Score end-to-end.",
      action: "recompute"
    },
    {
      id: "flag",
      stepLabel: "Step 4",
      title: "Flag high-risk agents",
      description: "Apply overrides to a handful of agents so the dashboards/approvals have red-band samples.",
      buttonLabel: "See notes",
      note: "POST /demo/flag_high_risk to promote a small set of agents into red band."
    },
    {
      id: "sdk",
      stepLabel: "Step 5",
      title: "SDK",
      description: "Call the safe SDK samples to query health, metrics, and governance context.",
      buttonLabel: "Run SDK check",
      note: "Invoke the /sdk/check_and_header endpoint to fetch the company-approved system header.",
      action: "sdk"
    },
    {
      id: "watchdog",
      stepLabel: "Step 6",
      title: "Watchdog",
      description: "Schedule periodic rescoring / drift detection (placeholder in this demo).",
      buttonLabel: "See notes",
      note: "Future work: hook up the watchdog job to detect drift and request approvals automatically."
    }
  ];

  let metrics: AdminMetrics | null = null;
  let loading = true;
  let error: string | null = null;
  let recomputeBusy = false;
  let pipelineNotice:
    | { title: string; message: string; tone: "info" | "success" | "error" }
    | null = null;
  let violations: PolicyViolation[] = [];
  let pendingApprovals: ApprovalSummary[] = [];
  let sdkResult: SdkCheckResponse | null = null;
  let sdkRunning = false;
  let demoAgentId = DEFAULT_DEMO_AGENT;
  $: actionImpacts =
    (metrics?.action_policy_impacts ?? []) as ActionPolicyImpact[];

  onMount(async () => {
    await loadMetrics();
  });

  async function loadMetrics() {
    loading = true;
    error = null;
    try {
      const json = await getAdminMetrics();
      metrics = json;
    } catch (e: any) {
      console.error("fetchAdminMetrics error", e);
      error = e?.message ?? String(e);
      metrics = null;
    } finally {
      loading = false;
    }
  }

  function formatNumber(
    n: number | null | undefined,
    opts?: Intl.NumberFormatOptions
  ): string {
    if (!n) return "0";
    return n.toLocaleString("en-NZ", opts);
  }

  function shortAgent(agentId: string | null | undefined): string {
    if (!agentId) return "—";
    if (agentId.length <= 28) return agentId;
    return `${agentId.slice(0, 14)}…${agentId.slice(-6)}`;
  }

  function formatAgentList(list: string[] | undefined | null): string {
    if (!list || list.length === 0) return "—";
    return list.map(shortAgent).join(", ");
  }

  $: bandSummary = ["red", "amber", "green"].map((band) => {
    const colors: Record<string, string> = {
      red: "#7f1d1d",
      amber: "#854d0e",
      green: "#166534"
    };
    const labelMap: Record<string, string> = {
      red: "Red",
      amber: "Amber",
      green: "Green"
    };
    const count =
      metrics?.risk_bands?.find((b) => b.band === band)?.count ?? 0;
    return {
      band,
      label: labelMap[band],
      color: colors[band],
      count
    };
  });
  $: totalBands = bandSummary.reduce((sum, b) => sum + b.count, 0);
  $: violations = metrics?.violations ?? [];
  $: pendingApprovals = metrics?.pending_approvals ?? [];
  $: eventSeries = metrics?.events_over_time ?? [];
  $: eventMax = eventSeries.reduce(
    (max, point) => Math.max(max, point.count || 0),
    1
  );
  $: approvalsStats = metrics?.approvals_stats;
  $: approvalDonut = (() => {
    if (!approvalsStats) return { total: 0, pending: 0, approved: 0, rejected: 0 };
    const total =
      (approvalsStats.pending ?? 0) +
      (approvalsStats.approved ?? 0) +
      (approvalsStats.rejected ?? 0);
    return {
      total,
      pending: approvalsStats.pending ?? 0,
      approved: approvalsStats.approved ?? 0,
      rejected: approvalsStats.rejected ?? 0
    };
  })();
  $: approvalDonutStyle = (() => {
    if (!approvalDonut.total) {
      return "#1f2937";
    }
    const pendingPct = (approvalDonut.pending / approvalDonut.total) * 100;
    const approvedPct = (approvalDonut.approved / approvalDonut.total) * 100;
    const rejectedPct = 100 - pendingPct - approvedPct;
    const firstStop = pendingPct;
    const secondStop = pendingPct + approvedPct;
    return `conic-gradient(#f59e0b 0 ${firstStop}%, #22c55e ${firstStop}% ${secondStop}%, #ef4444 ${secondStop}% 100%)`;
  })();
  $: topRiskyAgents = metrics?.top_risky_agents ?? [];
  $: signalCoverage = metrics?.signal_coverage;
  $: coveragePercent = (() => {
    if (!signalCoverage || !signalCoverage.total_agents) {
      return { reach: 0, autonomy: 0, tools: 0 };
    }
    const total = signalCoverage.total_agents;
    return {
      reach: Math.round((signalCoverage.reach_known / total) * 100),
      autonomy: Math.round((signalCoverage.autonomy_known / total) * 100),
      tools: Math.round((signalCoverage.external_tools_known / total) * 100)
    };
  })();
  $: dataClassByPlatform = metrics?.data_class_by_platform ?? [];
  $: recentEvents = metrics?.recent_events ?? [];
  $: demoAgentId =
    pendingApprovals[0]?.agent_id ?? violations[0]?.agent_id ?? DEFAULT_DEMO_AGENT;

  function prettyScope(scope: string[] | null | undefined): string {
    if (!scope || scope.length === 0) return "internal_only";
    return scope.join(", ");
  }

  async function handlePipelineClick(step: PipelineStep) {
    pipelineNotice = {
      title: step.title,
      message: step.note,
      tone: "info"
    };

    if (step.action === "recompute") {
      recomputeBusy = true;
      pipelineNotice = {
        title: step.title,
        message: "Recomputing signals & risk bands…",
        tone: "info"
      };
      try {
        await recomputeAllSignals();
        await loadMetrics();
        pipelineNotice = {
          title: step.title,
          message: "Risk scoring completed successfully.",
          tone: "success"
        };
      } catch (e: any) {
        pipelineNotice = {
          title: step.title,
          message: e?.message ?? "Failed to run risk scoring.",
          tone: "error"
        };
      } finally {
        recomputeBusy = false;
      }
    } else if (step.action === "sdk") {
      await runSdkDemo(step);
    }
  }

  async function runSdkDemo(step?: PipelineStep) {
    sdkRunning = true;
    sdkResult = null;
    pipelineNotice = {
      title: step?.title ?? "SDK safeguard",
      message: "Calling /sdk/check_and_header…",
      tone: "info"
    };
    try {
      const resp = await sdkCheck({
        agent_id: demoAgentId,
        action: "send_email",
        prompt:
          "Send an email to finance leadership summarising customer spend with attachments.",
        metadata: { contains_pii: true, channel: "email" },
        requested_by: "demo.sdk@acme.example"
      });
      sdkResult = resp;
      const tone = resp.blocked ? "error" : resp.approval_required ? "info" : "success";
      const statusMsg = resp.blocked
        ? "Action blocked by policy."
        : resp.approval_required
          ? `Approval ${resp.approval_status ?? "pending"} (id ${resp.approval_id ?? "?"})`
          : "Action allowed with safety header.";
      pipelineNotice = {
        title: step?.title ?? "SDK safeguard",
        message: statusMsg,
        tone
      };
      await loadMetrics();
    } catch (e: any) {
      pipelineNotice = {
        title: "SDK safeguard",
        message: e?.message ?? "SDK call failed",
        tone: "error"
      };
    } finally {
      sdkRunning = false;
    }
  }
</script>

<main
  style="
    min-height:100vh;
    background:#020617;
    color:#e5e7eb;
    padding:24px;
    font-family: system-ui, -apple-system, Segoe UI, sans-serif;
  "
>
  <header style="margin-bottom:24px;">
    <h1 style="font-size:28px; margin:0 0 4px;">AI Governance Demo</h1>
    <p style="color:#9ca3af; font-size:14px; margin:0;">
      Registry metrics coming from FastAPI on <code>localhost:8000</code>.
    </p>
  </header>

  <section
    style="
      display:flex;
      align-items:center;
      gap:12px;
      margin-bottom:16px;
    "
  >
    <button
      on:click={loadMetrics}
      style="
        background:#111827;
        border:1px solid #374151;
        color:#e5e7eb;
        padding:8px 14px;
        border-radius:8px;
        cursor:pointer;
        font-size:14px;
      "
      disabled={loading}
    >
      {#if loading}
        Loading…
      {:else}
        Fetch metrics
      {/if}
    </button>

    {#if error}
      <span style="color:#f97373; font-size:13px;">
        {error}
      </span>
    {/if}
  </section>

  {#if !metrics && !loading}
    <p style="color:#9ca3af; font-size:14px;">
      No metrics yet. Click "Fetch metrics" to load from the API.
    </p>
  {/if}

  {#if metrics}
    <!-- KPI cards -->
    <section
      style="
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
        gap:14px;
        margin-bottom:24px;
      "
    >
      {#each [
        { label: "Agents in registry", value: formatNumber(metrics.agents_total) },
        { label: "Canonical events", value: formatNumber(metrics.canonical_total) },
        {
          label: "Pending approvals",
          value: formatNumber(approvalsStats?.pending ?? pendingApprovals.length)
        },
        { label: "Policy violations", value: formatNumber(metrics.violations_count) },
        { label: "Watchdog runs", value: formatNumber(metrics.watchdog_runs) }
      ] as card}
        <div
          style="
            background:radial-gradient(circle at top left, #0f172a, #020617);
            border-radius:14px;
            border:1px solid #1f2937;
            padding:16px;
            box-shadow:0 10px 30px rgba(2,6,23,0.4);
          "
        >
          <div style="font-size:12px; text-transform:uppercase; color:#9ca3af;">
            {card.label}
          </div>
          <div style="font-size:30px; font-weight:700; letter-spacing:0.02em;">
            {card.value}
          </div>
        </div>
      {/each}
    </section>

    <!-- Risk posture & approvals -->
    <section
      style="
        margin-top:24px;
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(320px,1fr));
        gap:16px;
      "
    >
      <div
        style="
          background:#020617;
          border:1px solid #1f2937;
          border-radius:14px;
          padding:18px;
        "
      >
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <h2 style="font-size:18px; margin:0;">Risk posture</h2>
            <p style="color:#9ca3af; font-size:13px; margin:4px 0 16px;">
              Distribution of agents and the riskiest services to investigate next.
            </p>
          </div>
        </div>
        <div
          style="
            display:flex;
            align-items:stretch;
            border-radius:8px;
            overflow:hidden;
            border:1px solid #1f2937;
            background:#020617;
            height:42px;
          "
        >
          {#if totalBands > 0}
            {#each bandSummary as band}
              <div style={`flex:${band.count}; background:${band.color};`}></div>
            {/each}
          {:else}
            <div style="flex:1; background:#111827;"></div>
          {/if}
        </div>
        <div
          style="
            display:flex;
            gap:16px;
            margin:10px 0 16px;
            font-size:13px;
          "
        >
          {#each bandSummary as band}
            <div style="display:flex; align-items:center; gap:6px;">
              <span
                style={`
                  width:10px;
                  height:10px;
                  border-radius:999px;
                  background:${band.color};
                `}
              ></span>
              <span>
                {band.label}: {formatNumber(band.count)}
                {#if totalBands > 0}
                  ({Math.round((band.count / totalBands) * 100)}%)
                {/if}
              </span>
            </div>
          {/each}
        </div>
        <div
          style="
            border:1px solid #1f2937;
            border-radius:12px;
            overflow:hidden;
          "
        >
          <table style="width:100%; border-collapse:collapse; font-size:13px;">
            <thead style="background:#0f172a; color:#94a3b8;">
              <tr>
                <th style="text-align:left; padding:10px;">Top risky agents</th>
                <th style="text-align:left; padding:10px;">Owner</th>
                <th style="text-align:left; padding:10px;">Band</th>
              </tr>
            </thead>
            <tbody>
              {#if topRiskyAgents.length === 0}
                <tr>
                  <td colspan="3" style="padding:12px; color:#94a3b8; text-align:center;">
                    No risk scores yet. Run the pipeline to populate this table.
                  </td>
                </tr>
              {:else}
                {#each topRiskyAgents as agent}
                  <tr style="border-top:1px solid #1f2937;">
                    <td style="padding:10px; font-family:monospace; font-size:12px;">
                      {agent.agent_id}
                    </td>
                    <td style="padding:10px;">{agent.owner_email ?? "—"}</td>
                    <td style="padding:10px;">{agent.band} · {formatNumber(agent.score)}</td>
                  </tr>
                {/each}
              {/if}
            </tbody>
          </table>
        </div>
      </div>

      <div
        style="
          background:#020617;
          border:1px solid #1f2937;
          border-radius:14px;
          padding:18px;
        "
      >
        <h2 style="font-size:18px; margin:0 0 8px;">Approvals workload</h2>
        <p style="color:#9ca3af; font-size:13px; margin:0 0 16px;">
          Track reviewer pressure and turnaround time for escalation requests.
        </p>
        <div style="display:flex; gap:20px; flex-wrap:wrap; align-items:center;">
          <div
            style={`
              width:120px;
              height:120px;
              border-radius:999px;
              background:${approvalDonutStyle};
              position:relative;
            `}
          >
            <div
              style="
                position:absolute;
                top:50%;
                left:50%;
                transform:translate(-50%,-50%);
                background:#020617;
                border-radius:999px;
                width:64px;
                height:64px;
                display:flex;
                align-items:center;
                justify-content:center;
                font-size:14px;
                color:#cbd5f5;
              "
            >
              {formatNumber(approvalDonut.total)}
            </div>
          </div>
          <div style="display:flex; flex-direction:column; gap:6px;">
            <div style="font-size:13px; color:#f59e0b;">
              Pending · {formatNumber(approvalsStats?.pending ?? 0)}
            </div>
            <div style="font-size:13px; color:#22c55e;">
              Approved · {formatNumber(approvalsStats?.approved ?? 0)}
            </div>
            <div style="font-size:13px; color:#ef4444;">
              Rejected · {formatNumber(approvalsStats?.rejected ?? 0)}
            </div>
            <div style="font-size:13px; color:#cbd5f5; margin-top:8px;">
              Avg decision time:
              <strong>
                {formatNumber(approvalsStats?.avg_latency_minutes ?? 0, {
                  maximumFractionDigits: 1
                })}
              </strong>
              min
            </div>
            <div style="font-size:13px; color:#cbd5f5;">
              Processed last 24h:
              <strong>{formatNumber(approvalsStats?.processed_last_24h ?? 0)}</strong>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Signals & policy -->
    <section
      style="
        margin-top:24px;
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(320px,1fr));
        gap:16px;
      "
    >
      <div
        style="
          background:#020617;
          border:1px solid #1f2937;
          border-radius:14px;
          padding:18px;
        "
      >
        <h2 style="font-size:18px; margin:0 0 8px;">Governance signals</h2>
        <p style="color:#9ca3af; font-size:13px; margin:0 0 16px;">
          Coverage across data class, output scope, autonomy, reach, and platform classification.
        </p>
        {#if !signalCoverage || !signalCoverage.total_agents}
          <p style="color:#94a3b8; font-size:13px;">
            No signal data yet. Run the pipeline to populate governance signals.
          </p>
        {:else}
          <div style="display:flex; flex-direction:column; gap:8px; margin-bottom:12px;">
            <div>
              <strong>{coveragePercent.reach}%</strong> have reach classified
            </div>
            <div
              style="
                height:4px;
                background:#1f2937;
                border-radius:999px;
                margin-bottom:6px;
              "
            >
              <span style={`width:${coveragePercent.reach}%; background:#6366f1;`}></span>
            </div>
            <div>
              <strong>{coveragePercent.autonomy}%</strong> have autonomy set
            </div>
            <div
              style="
                height:4px;
                background:#1f2937;
                border-radius:999px;
                margin-bottom:6px;
              "
            >
              <span style={`width:${coveragePercent.autonomy}%; background:#22d3ee;`}></span>
            </div>
            <div>
              <strong>{coveragePercent.tools}%</strong> have external-tool lists
            </div>
            <div
              style="
                height:4px;
                background:#1f2937;
                border-radius:999px;
                margin-bottom:6px;
              "
            >
              <span style={`width:${coveragePercent.tools}%; background:#f472b6;`}></span>
            </div>
          </div>
        {/if}
        <div style="margin:12px 0;">
          <div style="font-size:12px; text-transform:uppercase; color:#9ca3af; margin-bottom:6px;">
            Data class by platform
          </div>
          {#if dataClassByPlatform.length === 0}
            <p style="color:#94a3b8; font-size:13px;">
              No agents yet.
            </p>
          {:else}
            <div style="display:flex; flex-wrap:wrap; gap:8px;">
              {#each dataClassByPlatform as row}
                <span
                  style="
                    padding:6px 10px;
                    border-radius:999px;
                    background:#0f172a;
                    border:1px solid #1f2937;
                    font-size:12px;
                  "
                >
                  {row.platform ?? "unknown"} · {row.data_class ?? "unset"} · {row.count}
                </span>
              {/each}
            </div>
          {/if}
        </div>
        <div style="margin-top:16px;">
          <div style="font-size:12px; text-transform:uppercase; color:#9ca3af; margin-bottom:6px;">
            Events ingested (7 days)
          </div>
          <div
            style="
              display:flex;
              gap:8px;
              align-items:flex-end;
              min-height:80px;
            "
          >
            {#each eventSeries as point}
              <div style="text-align:center; flex:1;">
                <div
                  style={`
                    width:100%;
                    height:${Math.max((point.count / eventMax) * 60, 4)}px;
                    background:#2563eb;
                    border-radius:4px 4px 0 0;
                    margin:0 auto;
                  `}
                ></div>
                <div style="font-size:10px; color:#9ca3af; margin-top:4px;">
                  {point.day.split("-").slice(1).join("/")}
                </div>
                <div style="font-size:11px;">{formatNumber(point.count)}</div>
              </div>
            {/each}
          </div>
        </div>
      </div>

      <div
        style="
          background:#020617;
          border:1px solid #1f2937;
          border-radius:14px;
          padding:18px;
        "
      >
        <h2 style="font-size:18px; margin:0 0 8px;">Action policy impact</h2>
        <p style="color:#9ca3af; font-size:13px; margin:0 0 12px;">
          See which verbs are governed, what the Allow/Approval matrix looks like, and who triggered them recently.
        </p>
        {#if actionImpacts.length === 0}
          <p style="color:#94a3b8; font-size:13px;">
            No actions yet. Run the pipeline to ingest logs and auto-discover action verbs.
          </p>
        {:else}
          <div style="border:1px solid #1f2937; border-radius:12px; overflow:auto; max-height:360px;">
            <table style="width:100%; border-collapse:collapse; font-size:12px;">
              <thead style="background:#0f172a; color:#94a3b8;">
                <tr>
                  <th style="text-align:left; padding:10px;">Action</th>
                  <th style="text-align:left; padding:10px;">Bands</th>
                  <th style="text-align:left; padding:10px;">Agents & pending</th>
                  <th style="text-align:left; padding:10px;">Last seen</th>
                </tr>
              </thead>
              <tbody>
                {#each actionImpacts as action}
                  <tr style="border-top:1px solid #1f2937;">
                    <td style="padding:10px; width:26%; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                      <div style="font-weight:600; color:#e5e7eb;">{action.action_name}</div>
                      {#if action.status === "needs_review"}
                        <span
                          style="
                            display:inline-block;
                            margin-top:4px;
                            font-size:11px;
                            color:#fbbf24;
                            border:1px solid #fbbf24;
                            border-radius:999px;
                            padding:2px 8px;
                            text-transform:uppercase;
                          "
                        >
                          Needs review
                        </span>
                      {/if}
                    </td>
                    <td style="padding:10px; width:28%;">
                      <div style="display:flex; flex-wrap:wrap; gap:6px;">
                        {#each bandOrder as band}
                          <span
                            style="
                              font-size:11px;
                              padding:4px 6px;
                              border-radius:999px;
                              background:#0f172a;
                              border:1px solid #1f2937;
                              white-space:nowrap;
                            "
                          >
                            {band.label.charAt(0)}:
                            {action.allow[band.key] ? "Allow" : "Block"}
                            {#if action.approval[band.key]}
                              +Appr
                            {/if}
                          </span>
                        {/each}
                      </div>
                    </td>
                    <td style="padding:10px; width:32%; font-size:12px;">
                      <div style="display:flex; flex-direction:column; gap:4px;">
                        <span style="color:#cbd5f5;">
                          {formatNumber(action.agent_count)} agents · Pending {formatNumber(action.pending_approvals)}
                        </span>
                        <span style="color:#9ca3af;">
                          Pending: <span style="color:#e5e7eb;">{formatAgentList(action.pending_agents)}</span>
                        </span>
                        <span style="color:#9ca3af;">
                          Recent: <span style="color:#e5e7eb;">{formatAgentList(action.recent_agents)}</span>
                        </span>
                      </div>
                    </td>
                    <td style="padding:10px; width:14%; font-size:11px; color:#cbd5f5; white-space:nowrap;">
                      {#if action.last_invoked_at}
                        {new Date(action.last_invoked_at).toLocaleString()}
                      {:else}
                        —
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>
    </section>

    <section style="margin-top:24px;">
      <h2 style="font-size:16px; margin:0 0 8px;">Recent events</h2>
      <p style="color:#9ca3af; font-size:13px; margin:0 0 12px;">
        Watchdog runs and approval activity happening across the registry.
      </p>
      {#if recentEvents.length === 0}
        <p style="color:#94a3b8;">No recent events.</p>
      {:else}
        <div style="border-left:2px solid #1f2937; padding-left:16px;">
          {#each recentEvents as event}
            <div style="margin-bottom:12px; position:relative;">
              <span
                style="
                  position:absolute;
                  left:-19px;
                  top:4px;
                  width:10px;
                  height:10px;
                  border-radius:999px;
                  background:#22c55e;
                "
              ></span>
              <div style="font-size:11px; color:#94a3b8;">
                {new Date(event.timestamp).toLocaleString()}
              </div>
              <div style="font-size:13px; color:#e5e7eb;">
                {event.message}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </section>

    {#if sdkResult}
      <section style="margin-top:16px;">
        <div
          style="
            border:1px solid #1f2937;
            border-radius:12px;
            padding:16px;
            background:#020617;
          "
        >
          <h3 style="margin:0 0 8px; font-size:15px;">Latest SDK decision</h3>
          <p style="color:#9ca3af; font-size:13px; margin:0 0 12px;">
            Agent <code>{sdkResult.agent_id}</code> · Risk band {sdkResult.risk_band ?? "unknown"} · Score {sdkResult.risk_score ?? "—"}
          </p>
          <div style="display:flex; flex-wrap:wrap; gap:12px; font-size:13px;">
            <span>
              {#if sdkResult.blocked}
                🚫 Blocked by policy
              {:else if sdkResult.approval_required}
                ⏳ Awaiting approval #{sdkResult.approval_id ?? "—"} ({sdkResult.approval_status ?? "pending"})
              {:else}
                ✅ Allowed with safeguards
              {/if}
            </span>
            <span>Reasons: {sdkResult.reasons.join(", ") || "n/a"}</span>
          </div>
          <details style="margin-top:12px;">
            <summary style="cursor:pointer;">View injected system header</summary>
            <pre style="margin-top:8px; white-space:pre-wrap;">{sdkResult.system_header}</pre>
          </details>
        </div>
      </section>
    {/if}

    <!-- Violations table -->
    <section style="margin-top:24px;">
      <div style="display:flex; align-items:center; justify-content:space-between;">
        <div>
          <h2 style="font-size:16px; margin:0 0 4px;">Policy violations</h2>
          <p style="color:#9ca3af; font-size:13px; margin:0;">
            Real-time checks for confidential + external egress without DLP and autonomous high-reach agents.
          </p>
        </div>
        <span
          style="
            border:1px solid #374151;
            border-radius:999px;
            padding:4px 10px;
            font-size:12px;
            color:#9ca3af;
          "
        >
          {formatNumber(metrics.violations_count)} open
        </span>
      </div>

      <div
        style="
          margin-top:12px;
          border:1px solid #1f2937;
          border-radius:12px;
          overflow:auto;
        "
      >
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
          <thead style="background:#0f172a; color:#94a3b8;">
            <tr>
              <th style="text-align:left; padding:10px;">Agent</th>
              <th style="text-align:left; padding:10px;">Platform</th>
              <th style="text-align:left; padding:10px;">Data class</th>
              <th style="text-align:left; padding:10px;">Output scope</th>
              <th style="text-align:left; padding:10px;">DLP template</th>
              <th style="text-align:left; padding:10px;">Risk</th>
              <th style="text-align:left; padding:10px;">Rule</th>
            </tr>
          </thead>
          <tbody>
            {#if violations.length === 0}
              <tr>
                <td colspan="7" style="padding:12px; color:#94a3b8; text-align:center;">
                  No open violations. Run more adapter data to surface controls in action.
                </td>
              </tr>
            {:else}
              {#each violations as violation}
                <tr style="border-top:1px solid #1f2937;">
                  <td style="padding:10px; font-family:monospace; font-size:12px;">
                    {violation.agent_id}
                  </td>
                  <td style="padding:10px;">{violation.platform ?? "—"}</td>
                  <td style="padding:10px;">
                    <span
                      style="
                        padding:2px 8px;
                        border-radius:999px;
                        border:1px solid #1f2937;
                        background:#0f172a;
                      "
                    >
                      {violation.data_class ?? "unknown"}
                    </span>
                  </td>
                  <td style="padding:10px;">
                    <code style="font-size:12px;">{prettyScope(violation.output_scope)}</code>
                  </td>
                  <td style="padding:10px;">{violation.dlp_template ?? "—"}</td>
                  <td style="padding:10px;">
                    {#if violation.risk_band}
                      <span
                        style={`
                          padding:2px 8px;
                          border-radius:999px;
                          border:1px solid #1f2937;
                          background:${
                            violation.risk_band === "red"
                              ? "#7f1d1d"
                              : violation.risk_band === "amber"
                                ? "#854d0e"
                                : "#14532d"
                          };
                        `}
                      >
                        {violation.risk_band} · {formatNumber(violation.risk_score ?? 0)}
                      </span>
                    {:else}
                      —
                    {/if}
                  </td>
                  <td style="padding:10px; color:#f97316;">
                    {violation.rule}
                  </td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>
    </section>

    <!-- Approvals summary -->
    <section style="margin-top:24px;">
      <div style="display:flex; align-items:center; justify-content:space-between;">
        <div>
          <h2 style="font-size:16px; margin:0 0 4px;">Approvals queue</h2>
          <p style="color:#9ca3af; font-size:13px; margin:0;">
            Requests requiring a human decision before the agent can continue.
          </p>
        </div>
        <a
          href="/approvals"
          style="
            border:1px solid #374151;
            border-radius:8px;
            padding:6px 12px;
            color:#e5e7eb;
            text-decoration:none;
            font-size:13px;
          "
        >
          Open approvals console →
        </a>
      </div>
      <div
        style="
          margin-top:12px;
          border:1px solid #1f2937;
          border-radius:12px;
          overflow:auto;
        "
      >
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
          <thead style="background:#0f172a; color:#94a3b8;">
            <tr>
              <th style="text-align:left; padding:10px;">Agent</th>
              <th style="text-align:left; padding:10px;">Action</th>
              <th style="text-align:left; padding:10px;">Risk</th>
              <th style="text-align:left; padding:10px;">Requested by</th>
              <th style="text-align:left; padding:10px;">Triggers</th>
            </tr>
          </thead>
          <tbody>
            {#if pendingApprovals.length === 0}
              <tr>
                <td colspan="5" style="padding:12px; color:#94a3b8; text-align:center;">
                  No approvals pending. SDK guardrails are clear.
                </td>
              </tr>
            {:else}
              {#each pendingApprovals as approval}
                <tr style="border-top:1px solid #1f2937;">
                  <td style="padding:10px; font-family:monospace; font-size:12px;">
                    {approval.agent_id}
                  </td>
                  <td style="padding:10px;">{approval.action}</td>
                  <td style="padding:10px;">
                    {approval.risk_band ?? "—"}
                  </td>
                  <td style="padding:10px;">
                    {approval.requested_by ?? "sdk"}
                  </td>
                  <td style="padding:10px; color:#f97316;">
                    {(approval.violations && approval.violations.length
                      ? approval.violations.join(", ")
                      : approval.reasons.join(", ")) || "policy guardrail"}
                  </td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>
    </section>

  {/if}
</main>
