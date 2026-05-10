OPENCLAW_ACTION_SPECS = [
    {
        "name": "expand_infra_graph",
        "description": "Expand account-device-IP-payment-logistics graph for a case.",
        "parameters": {"case_id": "string", "params": "object"},
    },
    {
        "name": "query_refund_cluster",
        "description": "Query fast refund and refund-concentration evidence.",
        "parameters": {"case_id": "string", "params": "object"},
    },
    {
        "name": "query_logistics_trace",
        "description": "Query logistics authenticity and counter explanations.",
        "parameters": {"case_id": "string", "params": "object"},
    },
    {
        "name": "query_payment_cluster",
        "description": "Query payment-account concentration evidence.",
        "parameters": {"case_id": "string", "params": "object"},
    },
    {
        "name": "compare_promo_cohort",
        "description": "Compare case metrics with dynamic promotion cohort baselines.",
        "parameters": {"case_id": "string", "params": "object"},
    },
    {
        "name": "seek_counter_evidence",
        "description": "Search normal-business counter-evidence.",
        "parameters": {"case_id": "string", "params": "object"},
    },
    {
        "name": "request_human_review",
        "description": "Route case to human audit review gate.",
        "parameters": {"case_id": "string", "params": "object"},
    },
    {
        "name": "emit_passport",
        "description": "Emit Evidence Passport readiness observation.",
        "parameters": {"case_id": "string", "params": "object"},
    },
]

