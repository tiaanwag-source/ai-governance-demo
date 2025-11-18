<script lang="ts">
  import { onMount } from "svelte";
  import type { AgentSummary } from "$lib/api";
  import { fetchAgents } from "$lib/api";

  let agents: AgentSummary[] = [];
  let loading = true;
  let error: string | null = null;
  let search = "";
  let riskBand: "all" | "red" | "amber" | "green" = "all";

  onMount(loadAgents);

  async function loadAgents() {
    loading = true;
    error = null;
    try {
      agents = await fetchAgents({
        limit: 200,
        search: search || undefined,
        risk_band: riskBand === "all" ? undefined : riskBand
      });
    } catch (e: any) {
      error = e?.message ?? "Failed to load agents";
      agents = [];
    } finally {
      loading = false;
    }
  }

  function formatList(items: string[] | undefined): string {
    if (!items || items.length === 0) return "—";
    return items.join(", ");
  }
</script>

<section
  style="
    padding:24px;
    color:#e5e7eb;
    font-family: system-ui, -apple-system, Segoe UI, sans-serif;
  "
>
  <h1 style="margin:0 0 8px; font-size:26px;">Agent registry</h1>
  <p style="color:#94a3b8; margin:0 0 16px;">
    Live view of agents discovered by the adapters, including the derived governance signals and risk band.
  </p>

  <form
    on:submit|preventDefault={loadAgents}
    style="
      display:flex;
      gap:12px;
      margin-bottom:16px;
      flex-wrap:wrap;
      align-items:flex-end;
    "
  >
    <label style="display:flex; flex-direction:column; font-size:13px; color:#9ca3af;">
      Search
      <input
        type="text"
        bind:value={search}
        placeholder="agent id, owner email…"
        style="
          background:#020617;
          border:1px solid #374151;
          border-radius:8px;
          color:#e5e7eb;
          padding:8px;
          min-width:240px;
        "
      />
    </label>
    <label style="display:flex; flex-direction:column; font-size:13px; color:#9ca3af;">
      Risk band
      <select
        bind:value={riskBand}
        style="
          background:#020617;
          border:1px solid #374151;
          border-radius:8px;
          color:#e5e7eb;
          padding:8px;
          min-width:140px;
        "
      >
        <option value="all">All</option>
        <option value="red">Red</option>
        <option value="amber">Amber</option>
        <option value="green">Green</option>
      </select>
    </label>
    <button
      type="submit"
      style="
        background:#111827;
        border:1px solid #374151;
        color:#e5e7eb;
        padding:10px 16px;
        border-radius:8px;
        cursor:pointer;
        font-size:13px;
      "
      disabled={loading}
    >
      {loading ? "Loading…" : "Refresh"}
    </button>
  </form>

  {#if error}
    <div style="margin-bottom:16px; color:#f87171;">{error}</div>
  {/if}

  {#if loading && agents.length === 0}
    <p style="color:#94a3b8;">Loading agents…</p>
  {:else if agents.length === 0}
    <p style="color:#94a3b8;">No agents found. Run the adapter to ingest some events.</p>
  {:else}
    <div
      style="
        border:1px solid #1f2937;
        border-radius:12px;
        overflow:auto;
      "
    >
      <table style="width:100%; border-collapse:collapse; font-size:13px;">
        <thead style="background:#0f172a; color:#94a3b8;">
          <tr>
            <th style="text-align:left; padding:10px;">Agent</th>
            <th style="text-align:left; padding:10px;">Owner</th>
            <th style="text-align:left; padding:10px;">Platform</th>
            <th style="text-align:left; padding:10px;">Signals</th>
            <th style="text-align:left; padding:10px;">Risk</th>
          </tr>
        </thead>
        <tbody>
          {#each agents as agent}
            <tr style="border-top:1px solid #1f2937;">
              <td style="padding:10px; font-family:monospace; font-size:12px;">
                {agent.agent_id}
                <div style="color:#94a3b8; font-size:11px;">
                  {agent.project_id ?? "—"} · {agent.location ?? "—"}
                </div>
              </td>
              <td style="padding:10px;">{agent.owner_email ?? "—"}</td>
              <td style="padding:10px;">{agent.platform}</td>
              <td style="padding:10px;">
                <div style="font-size:12px; color:#cbd5f5;">
                  Data class: <strong>{agent.data_class ?? "—"}</strong>
                </div>
                <div style="font-size:12px; color:#cbd5f5;">
                  Output scope: {formatList(agent.output_scope)}
                </div>
                <div style="font-size:12px; color:#cbd5f5;">
                  Autonomy: {agent.autonomy ?? "—"} · Reach: {agent.reach ?? "—"}
                </div>
                <div style="font-size:12px; color:#cbd5f5;">
                  Tools: {formatList(agent.external_tools)}
                </div>
                <div style="font-size:12px; color:#cbd5f5;">
                  Recent actions: {formatList(agent.recent_actions)}
                </div>
              </td>
              <td style="padding:10px; font-size:12px;">
                {agent.risk_band ?? "unknown"} · {agent.risk_score ?? "—"}
                <div style="color:#94a3b8;">
                  Updated {agent.updated_at ? new Date(agent.updated_at).toLocaleString() : "—"}
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>
