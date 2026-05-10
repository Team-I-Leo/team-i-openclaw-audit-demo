async function callTool(action: string, params: Record<string, unknown>) {
  const backendUrl = process.env.AER_BACKEND_URL || "http://127.0.0.1:18081";
  const res = await fetch(`${backendUrl}/api/openclaw/tools/${action}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    throw new Error(`AER backend tool failed ${res.status}: ${await res.text()}`);
  }
  const json = await res.json();
  return { content: [{ type: "text", text: JSON.stringify(json) }] };
}

const toolParams = {
  type: "object",
  additionalProperties: false,
  required: ["case_id"],
  properties: {
    case_id: { type: "string", default: "AER-001" },
    params: { type: "object", additionalProperties: true },
  },
};

const toolSpecs = [
  ["aer_expand_infra_graph", "expand_infra_graph", "Expand account-device-IP-payment-logistics evidence graph."],
  ["aer_query_refund_cluster", "query_refund_cluster", "Query fast refund and refund-concentration evidence."],
  ["aer_query_logistics_trace", "query_logistics_trace", "Query logistics authenticity and batch-shipping counter evidence."],
  ["aer_query_payment_cluster", "query_payment_cluster", "Query payment-account reuse and concentration."],
  ["aer_compare_promo_cohort", "compare_promo_cohort", "Compare case metrics with promotion cohort baselines."],
  ["aer_query_subsidy_ledger", "query_subsidy_ledger", "Query promotion subsidy ledger, eligibility keys, and abuse signals."],
  ["aer_analyze_behavior_sequence", "analyze_behavior_sequence", "Fuse gateway/device logs and review similarity behavior evidence."],
  ["aer_search_historical_cases", "search_historical_cases", "Retrieve historical case memory and pattern matches."],
  ["aer_seek_counter_evidence", "seek_counter_evidence", "Search for legitimate business counter-evidence."],
  ["aer_request_human_review", "request_human_review", "Escalate to human audit gate."],
  ["aer_emit_passport", "emit_passport", "Emit Evidence Passport readiness observation."],
] as const;

export default {
  id: "aer-audit-tools",
  name: "AER Audit Tools",
  description: "Governed audit evidence tools for Team-I.",
  register(api) {
    for (const [name, action, description] of toolSpecs) {
      api.registerTool({
        name,
        description,
        parameters: toolParams,
        async execute(_id, params) {
          return callTool(action, params as Record<string, unknown>);
        },
      });
    }
  },
};
