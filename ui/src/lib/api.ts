// ui/src/lib/api.ts
export type BandCount = {
  band: string;
  count: number;
};

export type KeyCount = {
  key: string | null;
  count: number;
};

export type PolicyViolation = {
  agent_id: string;
  platform: string | null;
  data_class: string | null;
  output_scope: string[];
  dlp_template: string | null;
  risk_band: string | null;
  risk_score: number | null;
  rule: string;
};

export type ApprovalSummary = {
  id: number;
  agent_id: string;
  action: string;
  risk_band: string | null;
  status: string;
  requested_by: string | null;
  requested_at: string;
  decided_by: string | null;
  decided_at: string | null;
  violations: string[];
  reasons: string[];
  signals: Record<string, any>;
  request: Record<string, any>;
  admin_note?: string | null;
};

export type AgentSummary = {
  agent_id: string;
  platform: string;
  project_id?: string | null;
  location?: string | null;
  owner_email?: string | null;
  data_class?: string | null;
  output_scope: string[];
  autonomy?: string | null;
  reach?: string | null;
  external_tools: string[];
  risk_band?: string | null;
  risk_score?: number | null;
  updated_at?: string | null;
  recent_actions?: string[];
};

export type AdminMetrics = {
  canonical_total: number;
  agents_total: number;
  classification_rules: number;
  risk_scores: number;
  approvals: number;
  watchdog_runs: number;
  agents_by_platform: KeyCount[];
  agents_by_data_class: KeyCount[];
  agents_by_autonomy: KeyCount[];
  risk_bands: BandCount[];
  violations_count: number;
  violations: PolicyViolation[];
  pending_approvals: ApprovalSummary[];
  events_over_time: { day: string; count: number }[];
  approvals_stats: {
    pending: number;
    approved: number;
    rejected: number;
    avg_latency_minutes: number;
    processed_last_24h: number;
  };
  top_risky_agents: {
    agent_id: string;
    platform: string;
    owner_email?: string | null;
    score: number;
    band: string;
  }[];
  signal_coverage: {
    reach_known: number;
    autonomy_known: number;
    external_tools_known: number;
    total_agents: number;
  };
  data_class_by_platform: {
    platform: string | null;
    data_class: string | null;
    count: number;
  }[];
  risk_trend: {
    day: string;
    red: number;
    amber: number;
    green: number;
  }[];
  recent_events: {
    timestamp: string;
    type: string;
    message: string;
  }[];
  action_policy_impacts: ActionPolicyImpact[];
};

export type RiskConfig = {
  weights: Record<string, Record<string, number>>;
  band_thresholds: Record<string, number>;
};

export type ClassificationPolicy = {
  rules: {
    id?: number;
    selector_type: string;
    selector_value: string;
    data_class: string;
    default_output_scope: string[];
    required_dlp_template?: string | null;
  }[];
  project_audience: {
    project_id: string;
    reach_count: number;
  }[];
};

export type ActionPolicy = {
  id: number;
  action_name: string;
  description?: string | null;
  status: string;
  allow: { green: boolean; amber: boolean; red: boolean };
  approval: { green: boolean; amber: boolean; red: boolean };
  last_seen_at?: string | null;
};

export type ActionPolicyImpact = {
  id: number;
  action_name: string;
  status: string;
  allow: { green: boolean; amber: boolean; red: boolean };
  approval: { green: boolean; amber: boolean; red: boolean };
  last_seen_at?: string | null;
  agent_count: number;
  last_invoked_at?: string | null;
  recent_agents: string[];
  pending_approvals: number;
  pending_agents: string[];
};

export type SdkCheckPayload = {
  agent_id: string;
  action: string;
  prompt?: string;
  metadata?: Record<string, any>;
  requested_by?: string;
};

export type SdkCheckResponse = {
  agent_id: string;
  risk_band?: string;
  risk_score?: number;
  approval_required: boolean;
  blocked: boolean;
  system_header: string;
  reasons: string[];
  violations: string[];
  signals: Record<string, any>;
  approval_id?: number;
  approval_status?: string;
};

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";  // configurable API target
const JSON_HEADERS = { "Content-Type": "application/json" };

async function handle(resp: Response) {
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`metrics_failed: ${resp.status} ${text}`);
  }
  return resp.json();
}

export async function fetchAdminMetrics(): Promise<AdminMetrics> {
  const resp = await fetch(`${API_BASE}/admin/metrics`);
  return handle(resp);
}

export async function recomputeAllSignals(): Promise<any> {
  const resp = await fetch(`${API_BASE}/admin/recompute_all`, {
    method: "POST"
  });
  return handle(resp);
}

export async function sdkCheck(payload: SdkCheckPayload): Promise<SdkCheckResponse> {
  const resp = await fetch(`${API_BASE}/sdk/check_and_header`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload)
  });
  return handle(resp);
}

export type AgentListParams = {
  limit?: number;
  search?: string;
  risk_band?: string;
};

export async function fetchAgents(params: AgentListParams = {}): Promise<AgentSummary[]> {
  const query = new URLSearchParams();
  if (params.limit) query.set("limit", params.limit.toString());
  if (params.search) query.set("search", params.search);
  if (params.risk_band) query.set("risk_band", params.risk_band);
  const qs = query.toString();
  const resp = await fetch(`${API_BASE}/agents${qs ? `?${qs}` : ""}`);
  return handle(resp);
}

export async function fetchApprovals(status = "pending", limit = 50): Promise<ApprovalSummary[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (limit) params.set("limit", String(limit));
  const qs = params.toString() ? `?${params.toString()}` : "";
  const resp = await fetch(`${API_BASE}/admin/approvals${qs}`);
  return handle(resp);
}

export type ApprovalDecisionInput = {
  status: "approved" | "rejected";
  decided_by: string;
  note?: string;
};

export async function decideApproval(id: number, body: ApprovalDecisionInput): Promise<ApprovalSummary> {
  const resp = await fetch(`${API_BASE}/admin/approvals/${id}/decision`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body)
  });
  return handle(resp);
}

export async function fetchRiskConfig(): Promise<RiskConfig> {
  const resp = await fetch(`${API_BASE}/policies/risk_scoring`);
  return handle(resp);
}

export async function saveRiskConfig(config: RiskConfig): Promise<RiskConfig> {
  const resp = await fetch(`${API_BASE}/policies/risk_scoring`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify({ config })
  });
  return handle(resp);
}

export async function fetchClassificationPolicy(): Promise<ClassificationPolicy> {
  const resp = await fetch(`${API_BASE}/policies/classifications`);
  return handle(resp);
}

export async function saveClassificationPolicy(policy: ClassificationPolicy): Promise<ClassificationPolicy> {
  const resp = await fetch(`${API_BASE}/policies/classifications`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(policy)
  });
  return handle(resp);
}

export async function fetchActionPolicies(): Promise<ActionPolicy[]> {
  const resp = await fetch(`${API_BASE}/policies/actions`);
  return handle(resp);
}

export async function updateActionPolicyApi(id: number, payload: Partial<ActionPolicy>): Promise<ActionPolicy> {
  const resp = await fetch(`${API_BASE}/policies/actions/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload)
  });
  return handle(resp);
}

export async function applyPolicies(): Promise<any> {
  const resp = await fetch(`${API_BASE}/policies/apply`, {
    method: "POST"
  });
  return handle(resp);
}
