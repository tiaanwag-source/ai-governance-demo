<script lang="ts">
  import { onMount } from "svelte";
  import type {
    RiskConfig,
    ClassificationPolicy,
    ActionPolicy
  } from "$lib/api";
  import {
    fetchRiskConfig,
    saveRiskConfig,
    fetchClassificationPolicy,
    saveClassificationPolicy,
    fetchActionPolicies,
    updateActionPolicyApi,
    applyPolicies
  } from "$lib/api";

  let riskConfig: RiskConfig | null = null;
  let classificationPolicy: ClassificationPolicy | null = null;
  let actions: ActionPolicy[] = [];
  let loading = true;
  let notice: string | null = null;

  onMount(async () => {
    await loadAll();
  });

  async function loadAll() {
    loading = true;
    notice = null;
    try {
      [riskConfig, classificationPolicy, actions] = await Promise.all([
        fetchRiskConfig(),
        fetchClassificationPolicy(),
        fetchActionPolicies()
      ]);
    } catch (e: any) {
      notice = e?.message ?? "Failed to load policies";
    } finally {
      loading = false;
    }
  }

  function updateRiskWeight(group: string, key: string, value: number) {
    if (!riskConfig) return;
    riskConfig = {
      ...riskConfig,
      weights: {
        ...riskConfig.weights,
        [group]: {
          ...riskConfig.weights[group],
          [key]: value
        }
      }
    };
  }

  async function saveRisk() {
    if (!riskConfig) return;
    await saveRiskConfig(riskConfig);
    notice = "Risk scoring updated";
  }

  async function saveClassifications() {
    if (!classificationPolicy) return;
    await saveClassificationPolicy(classificationPolicy);
    notice = "Classification policy saved";
  }

  async function updateAction(policy: ActionPolicy, band: string, field: "allow" | "approval", value: boolean) {
    await updateActionPolicyApi(policy.id, {
      [field]: {
        ...policy[field],
        [band]: value
      }
    });
    await loadAll();
    notice = `Updated ${policy.action_name}`;
  }

  async function markReviewed(policy: ActionPolicy) {
    await updateActionPolicyApi(policy.id, { status: "approved" });
    await loadAll();
    notice = `${policy.action_name} marked as reviewed`;
  }

  async function applyAndRefresh() {
    await applyPolicies();
    await loadAll();
    notice = "Policies applied and scoring rerun";
  }
</script>

<section style="padding:24px; color:#e5e7eb;">
  <h1 style="margin:0 0 16px;">Policies</h1>
  {#if loading}
    <p style="color:#94a3b8;">Loading policy data…</p>
  {:else}
    {#if notice}
      <div style="margin-bottom:16px; padding:10px 12px; border-radius:8px; background:#0f172a; border:1px solid #1f2937;">
        {notice}
      </div>
    {/if}

    <div
      style="
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
        gap:16px;
        align-items:stretch;
      "
    >
      <div style="border:1px solid #1f2937; border-radius:12px; padding:16px; display:flex; flex-direction:column;">
        <h2 style="margin:0 0 8px;">Risk scoring weights</h2>
        {#if riskConfig}
          {#each Object.entries(riskConfig.weights) as [group, weights]}
            <div style="margin-bottom:12px;">
              <div style="font-size:12px; color:#9ca3af; text-transform:uppercase;">
                {group}
              </div>
              {#each Object.entries(weights) as [key, value]}
                <label style="display:flex; flex-direction:column; font-size:13px; margin-top:6px;">
                  {key}
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={value}
                    on:input={(event) =>
                      updateRiskWeight(group, key, Number((event.target as HTMLInputElement).value))}
                    style="
                      margin-top:4px;
                      background:#020617;
                      border:1px solid #374151;
                      border-radius:8px;
                      padding:6px;
                      color:#e5e7eb;
                    "
                  />
                </label>
              {/each}
            </div>
          {/each}
          <button
            on:click={saveRisk}
            style="
              margin-top:8px;
              background:#111827;
              border:1px solid #374151;
              border-radius:8px;
              padding:8px 12px;
              color:#e5e7eb;
              cursor:pointer;
            "
          >
            Save risk weights
          </button>
        {:else}
          <p style="color:#94a3b8;">No risk config available.</p>
        {/if}
      </div>

      <div style="border:1px solid #1f2937; border-radius:12px; padding:16px; display:flex; flex-direction:column;">
        <h2 style="margin:0 0 8px;">Classification rules</h2>
        {#if classificationPolicy}
          <div style="flex:1; min-height:0; overflow:auto;">
            {#each classificationPolicy.rules as rule, idx}
              <div style="border-bottom:1px solid #1f2937; padding:8px 0;">
                <div style="font-size:12px; color:#9ca3af; text-transform:uppercase;">
                  Rule {idx + 1}
                </div>
                <label style="display:block; font-size:13px; margin-top:6px;">
                  Selector value
                  <input
                    type="text"
                    bind:value={rule.selector_value}
                    style="width:100%; margin-top:4px; background:#020617; border:1px solid #374151; border-radius:8px; color:#e5e7eb; padding:6px;"
                  />
                </label>
                <label style="display:block; font-size:13px; margin-top:6px;">
                  Data class
                  <input
                    type="text"
                    bind:value={rule.data_class}
                    style="width:100%; margin-top:4px; background:#020617; border:1px solid #374151; border-radius:8px; color:#e5e7eb; padding:6px;"
                  />
                </label>
              </div>
            {/each}
          </div>
          <button
            on:click={saveClassifications}
            style="
              margin-top:8px;
              background:#111827;
              border:1px solid #374151;
              border-radius:8px;
              padding:8px 12px;
              color:#e5e7eb;
              cursor:pointer;
            "
          >
            Save classification rules
          </button>
        {:else}
          <p style="color:#94a3b8;">No classification data.</p>
        {/if}
      </div>

      <div style="border:1px solid #1f2937; border-radius:12px; padding:16px; display:flex; flex-direction:column;">
        <h2 style="margin:0 0 8px;">Action policies</h2>
        {#if actions.length === 0}
          <p style="color:#94a3b8; font-size:13px;">No actions yet.</p>
        {:else}
          <div style="flex:1; min-height:0; overflow:auto; padding-right:8px;">
            {#each actions as action}
              <div style="border-bottom:1px solid #1f2937; padding:8px 0;">
                <div style="font-size:13px; font-weight:600;">{action.action_name}</div>
                <div style="font-size:12px; color:#9ca3af;">
                  Status:
                  {#if action.status === "needs_review"}
                    <span style="color:#fcd34d;">Needs review</span>
                  {:else}
                    <span style="color:#34d399;">{action.status}</span>
                  {/if}
                </div>
                <div style="display:flex; gap:6px; margin-top:6px; font-size:12px; flex-wrap:wrap;">
                  {#each ["green","amber","red"] as band}
                    <label style="white-space:nowrap;">
                      <input
                        type="checkbox"
                        checked={action.allow[band]}
                        on:change={(event) => updateAction(action, band, "allow", event.currentTarget.checked)}
                      />
                      Allow {band}
                    </label>
                  {/each}
                </div>
                <div style="display:flex; gap:6px; margin-top:4px; font-size:12px; flex-wrap:wrap;">
                  {#each ["green","amber","red"] as band}
                    <label style="white-space:nowrap;">
                      <input
                        type="checkbox"
                        checked={action.approval[band]}
                        on:change={(event) => updateAction(action, band, "approval", event.currentTarget.checked)}
                      />
                      Approval {band}
                    </label>
                  {/each}
                </div>
                {#if action.status === "needs_review"}
                  <button
                    on:click={() => markReviewed(action)}
                    style="
                      margin-top:8px;
                      background:#14532d;
                      border:1px solid #16a34a;
                      border-radius:6px;
                      padding:4px 10px;
                      color:#e5e7eb;
                      cursor:pointer;
                      font-size:12px;
                    "
                  >
                    Mark as reviewed
                  </button>
                {/if}
              </div>
            {/each}
          </div>
          {#if actions.length > 6}
            <div style="text-align:right; font-size:11px; color:#9ca3af; margin-top:4px;">
              Scroll to see more actions ↓
            </div>
          {/if}
        {/if}
      </div>
    </div>

    <button
      on:click={applyAndRefresh}
      style="
        margin-top:16px;
        background:#14532d;
        border:1px solid #16a34a;
        border-radius:8px;
        padding:10px 14px;
        color:#e5e7eb;
        cursor:pointer;
      "
    >
      Apply policies & rerun scoring
    </button>
  {/if}
</section>
