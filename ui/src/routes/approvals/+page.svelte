<script lang="ts">
  import { onMount } from "svelte";
  import type { ApprovalSummary } from "$lib/api";
  import { fetchApprovals, decideApproval } from "$lib/api";

  let pendingApprovals: ApprovalSummary[] = [];
  let historyApprovals: ApprovalSummary[] = [];
  let loading = true;
  let error: string | null = null;
  let working: Record<number, boolean> = {};
  let notes: Record<number, string> = {};

  onMount(loadApprovals);

  async function loadApprovals() {
    loading = true;
    error = null;
    try {
      const [pending, approved, rejected] = await Promise.all([
        fetchApprovals("pending", 100),
        fetchApprovals("approved", 20),
        fetchApprovals("rejected", 20)
      ]);
      pendingApprovals = pending;
      historyApprovals = [...approved, ...rejected].sort((a, b) => {
        const aTime = a.decided_at ? new Date(a.decided_at).getTime() : 0;
        const bTime = b.decided_at ? new Date(b.decided_at).getTime() : 0;
        return bTime - aTime;
      });
    } catch (e: any) {
      error = e?.message ?? "Failed to load approvals";
    } finally {
      loading = false;
    }
  }

  async function handleDecision(id: number, status: "approved" | "rejected") {
    working = { ...working, [id]: true };
    try {
      await decideApproval(id, {
        status,
        decided_by: "demo.admin@acme.example",
        note: notes[id] || undefined
      });
      await loadApprovals();
    } catch (e: any) {
      error = e?.message ?? "Failed to update approval";
    } finally {
      working = { ...working, [id]: false };
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
  <h1 style="margin:0 0 8px; font-size:24px;">Approvals queue</h1>
  <p style="color:#94a3b8; margin:0 0 16px;">
    These actions were flagged by the SDK and require a human decision before the agent can continue.
  </p>

  {#if error}
    <div style="margin-bottom:12px; color:#f87171;">{error}</div>
  {/if}

  {#if loading}
    <p style="color:#94a3b8;">Loading approvals…</p>
  {:else if pendingApprovals.length === 0}
    <p style="color:#94a3b8;">No pending approvals 🎉</p>
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
            <th style="text-align:left; padding:10px;">Action</th>
            <th style="text-align:left; padding:10px;">Risk</th>
            <th style="text-align:left; padding:10px;">Requested by</th>
            <th style="text-align:left; padding:10px;">Violations / reasons</th>
            <th style="text-align:left; padding:10px;">Decision</th>
          </tr>
        </thead>
        <tbody>
          {#each pendingApprovals as approval}
            <tr style="border-top:1px solid #1f2937;">
              <td style="padding:10px; font-family:monospace; font-size:12px;">
                {approval.agent_id}
              </td>
              <td style="padding:10px;">{approval.action}</td>
              <td style="padding:10px;">{approval.risk_band ?? "—"}</td>
              <td style="padding:10px;">{approval.requested_by ?? "sdk"}</td>
              <td style="padding:10px; color:#f97316;">
                {(approval.violations && approval.violations.length
                  ? approval.violations.join(", ")
                  : approval.reasons.join(", ")) || "policy guardrail"}
                {#if approval.request?.prompt}
                  <details style="margin-top:6px;">
                    <summary style="cursor:pointer; color:#e5e7eb;">View prompt</summary>
                    <pre
                      style="
                        margin-top:4px;
                        font-size:12px;
                        background:#0f172a;
                        padding:6px;
                        border-radius:8px;
                        white-space:pre-wrap;
                      "
                    >
{approval.request.prompt}</pre>
                  </details>
                {/if}
              </td>
              <td style="padding:10px; min-width:220px;">
                <textarea
                  placeholder="Optional note"
                  rows="2"
                  value={notes[approval.id] ?? ""}
                  on:input={(event) => {
                    const value = (event.currentTarget as HTMLTextAreaElement).value;
                    notes = { ...notes, [approval.id]: value };
                  }}
                  style="
                    width:100%;
                    background:#020617;
                    border:1px solid #374151;
                    border-radius:8px;
                    color:#e5e7eb;
                    padding:6px;
                    margin-bottom:6px;
                  "
                ></textarea>
                <div style="display:flex; gap:8px;">
                  <button
                    on:click={() => handleDecision(approval.id, "approved")}
                    disabled={working[approval.id]}
                    style="
                      flex:1;
                      background:#14532d;
                      border:1px solid #166534;
                      color:#e5e7eb;
                      padding:6px;
                      border-radius:8px;
                      cursor:pointer;
                    "
                  >
                    {working[approval.id] ? "Saving…" : "Approve"}
                  </button>
                  <button
                    on:click={() => handleDecision(approval.id, "rejected")}
                    disabled={working[approval.id]}
                    style="
                      flex:1;
                      background:#7f1d1d;
                      border:1px solid #b91c1c;
                      color:#e5e7eb;
                      padding:6px;
                      border-radius:8px;
                      cursor:pointer;
                    "
                  >
                    {working[approval.id] ? "Saving…" : "Reject"}
                  </button>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  <h2 style="margin:32px 0 12px; font-size:18px;">Decision history</h2>
  <p style="color:#94a3b8; margin:0 0 12px;">
    Recently approved or rejected actions. Approved agents resume activity, rejected ones remain blocked.
  </p>
  {#if historyApprovals.length === 0}
    <p style="color:#94a3b8;">No decisions yet.</p>
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
            <th style="text-align:left; padding:10px;">Action</th>
            <th style="text-align:left; padding:10px;">Status</th>
            <th style="text-align:left; padding:10px;">Decided by</th>
            <th style="text-align:left; padding:10px;">Prompt / note</th>
          </tr>
        </thead>
        <tbody>
          {#each historyApprovals as approval}
            <tr style="border-top:1px solid #1f2937;">
              <td style="padding:10px; font-family:monospace; font-size:12px;">
                {approval.agent_id}
              </td>
              <td style="padding:10px;">{approval.action}</td>
              <td style="padding:10px;">
                <span
                  style={`
                    padding:2px 8px;
                    border-radius:999px;
                    font-size:11px;
                    border:1px solid ${approval.status === "approved" ? "#22c55e" : "#ef4444"};
                    color:${approval.status === "approved" ? "#bbf7d0" : "#fecaca"};
                  `}
                >
                  {approval.status}
                </span>
                <div style="color:#94a3b8; font-size:11px;">
                  {approval.decided_at
                    ? new Date(approval.decided_at).toLocaleString()
                    : ""}
                </div>
              </td>
              <td style="padding:10px;">{approval.decided_by ?? "—"}</td>
              <td style="padding:10px;">
                {#if approval.request?.prompt}
                  <details>
                    <summary style="cursor:pointer; color:#e5e7eb;">View prompt</summary>
                    <pre
                      style="
                        margin-top:4px;
                        font-size:12px;
                        background:#0f172a;
                        padding:6px;
                        border-radius:8px;
                        white-space:pre-wrap;
                      "
                    >
{approval.request.prompt}</pre>
                  </details>
                {/if}
                {#if approval.admin_note}
                  <div style="color:#fbbf24; font-size:12px; margin-top:4px;">
                    Note: {approval.admin_note}
                  </div>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>
