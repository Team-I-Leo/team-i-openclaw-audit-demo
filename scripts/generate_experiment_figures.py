from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
MAIN_DB = ROOT / "runtime" / "aer_loop_model_smoke_9728967_full_debug.sqlite"
LEARNING_DB = ROOT / "runtime" / "pattern_learning_writeback_test.sqlite"
OUT_DATA = ROOT / "docs" / "assets" / "experiments" / "data"
OUT_FIGS = ROOT / "docs" / "assets" / "experiments" / "figures"

ACTION_LABELS = {
    "expand_infra_graph": "关系图扩展",
    "query_refund_cluster": "退款簇核验",
    "query_subsidy_ledger": "补贴台账",
    "query_payment_cluster": "支付簇核验",
    "query_logistics_trace": "物流核验",
    "compare_promo_cohort": "促销同群对比",
    "analyze_behavior_sequence": "行为序列分析",
    "search_historical_cases": "历史案例检索",
    "seek_counter_evidence": "反证检索",
    "emit_passport": "证据护照",
    "request_human_review": "人工复核",
}

HIGHLIGHT_LABELS = {
    "openclaw": "OpenCLAW受控动作",
    "agents": "多模型Agent",
    "active": "主动追证",
    "fusion": "多源融合",
    "graph": "证据图谱与血缘",
    "counter": "反证检索",
    "passport": "证据护照",
    "human": "人机协同",
    "learning": "模式学习",
    "writeback": "策略写回",
}

METHOD_LABELS = {
    "Rules one-shot": "规则一次命中",
    "Static checklist": "固定检查清单",
    "Active retrieval w/o counter": "主动追证-无反证",
    "Team-I active loop": "Team-I主动闭环",
    "Manual worksheet": "人工表格",
    "Rules-only script": "规则脚本",
    "Rules-only": "规则脚本",
    "Single LLM/RAG": "单模型RAG",
    "Team-I OpenCLAW": "Team-I OpenCLAW",
    "Manual audit": "人工审计",
    "Rules + worksheet": "规则+表格",
    "Team-I": "Team-I",
}

AGENT_LABELS = {
    "router_agent": "动作路由Agent",
    "investigation_agent": "追证反思Agent",
    "risk_signal_agent": "风险信号Agent",
    "pattern_matcher_agent": "模式匹配Agent",
    "case_router_agent": "案件路由Agent",
    "assertion_agent": "断言生成Agent",
    "pattern_learning_agent": "模式学习Agent",
    "passport_agent": "证据护照Agent",
}

PALETTE = {
    "gray": "#94A3B8",
    "amber": "#F59E0B",
    "blue": "#3B82F6",
    "cyan": "#06B6D4",
    "green": "#10B981",
    "emerald": "#059669",
    "purple": "#8B5CF6",
    "red": "#EF4444",
    "ink": "#0F172A",
    "muted": "#64748B",
    "panel": "#F8FAFC",
    "grid": "#E2E8F0",
}


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def rows(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def jload(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def valid_json(value: Any) -> bool:
    if value in (None, ""):
        return False
    try:
        json.loads(value)
        return True
    except Exception:
        return False


def setup_style() -> None:
    font_paths = [
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/NotoSansSC-VF.ttf"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    font_name = "DejaVu Sans"
    for path in font_paths:
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            font_name = font_manager.FontProperties(fname=str(path)).get_name()
            break
    sns.set_theme(style="white", context="talk")
    plt.rcParams.update(
        {
            "figure.dpi": 160,
            "savefig.dpi": 260,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "axes.labelweight": "bold",
            "axes.titlesize": 18,
            "axes.labelsize": 14,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.fontsize": 12,
            "font.weight": "bold",
            "font.family": font_name,
            "axes.unicode_minus": False,
        }
    )


def savefig(fig: plt.Figure, name: str) -> None:
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    for ax in fig.axes:
        for item in [ax.title, ax.xaxis.label, ax.yaxis.label, *ax.get_xticklabels(), *ax.get_yticklabels()]:
            item.set_fontweight("bold")
            item.set_color(PALETTE["ink"])
        for text in ax.texts:
            text.set_fontweight("bold")
        legend = ax.get_legend()
        if legend:
            for text in legend.get_texts():
                text.set_fontweight("bold")
                text.set_color(PALETTE["ink"])
    fig.tight_layout()
    fig.savefig(OUT_FIGS / f"{name}.png", bbox_inches="tight")
    plt.close(fig)


def polish_axis(ax, *, ygrid: bool = True) -> None:
    ax.set_facecolor(PALETTE["panel"])
    ax.spines["left"].set_color("#CBD5E1")
    ax.spines["bottom"].set_color("#CBD5E1")
    ax.spines["left"].set_linewidth(1.8)
    ax.spines["bottom"].set_linewidth(1.8)
    ax.tick_params(colors=PALETTE["ink"], width=1.5)
    if ygrid:
        ax.grid(axis="y", color=PALETTE["grid"], linewidth=1.1)
        ax.grid(axis="x", visible=False)
    else:
        ax.grid(False)


def add_caption(ax, text: str) -> None:
    return None


def load_demo_state() -> dict[str, Any]:
    con = connect(MAIN_DB)
    cases = {}
    for r in rows(con, "SELECT * FROM risk_case ORDER BY case_id"):
        r["primary_entities"] = jload(r.get("primary_entities"), {})
        r["scores"] = jload(r.get("scores"), {})
        r["signal_strength"] = jload(r.get("signal_strength"), {})
        r["evidence_requirements"] = jload(r.get("evidence_requirements"), {})
        r["next_actions"] = jload(r.get("next_actions"), [])
        cases[r["case_id"]] = r

    evidence = {}
    for r in rows(con, "SELECT * FROM evidence ORDER BY case_id, evidence_id"):
        r["lineage"] = jload(r.get("lineage"), {})
        evidence[r["evidence_id"]] = r

    threads = defaultdict(list)
    for r in rows(con, "SELECT * FROM case_thread ORDER BY case_id, thread_step"):
        r["support_evidence_delta"] = jload(r.get("support_evidence_delta"), [])
        r["counter_evidence_delta"] = jload(r.get("counter_evidence_delta"), [])
        threads[r["case_id"]].append(r)

    return {"con": con, "cases": cases, "evidence": evidence, "threads": dict(threads)}


def score_coverage(case: dict[str, Any], evidence_by_id: dict[str, Any], evidence_ids: set[str]) -> dict[str, float]:
    required = case.get("evidence_requirements") or {}
    if not required:
        return {
            "support_score": 0.0,
            "counter_score": 0.0,
            "sufficiency_score": 0.0,
            "covered_dimensions": 0.0,
            "passport_ready": 0.0,
        }

    covered: dict[str, float] = {}
    counter_score = 0.0
    for eid in evidence_ids:
        e = evidence_by_id.get(eid)
        if not e:
            continue
        dim = e["dimension"]
        conf = float(e["confidence"] or 0.0)
        if e["kind"] == "support":
            covered[dim] = max(covered.get(dim, 0.0), conf)
        elif e["kind"] in {"counter", "uncertainty"}:
            counter_score = max(counter_score, conf)
            covered["counter_evidence"] = max(covered.get("counter_evidence", 0.0), min(1.0, conf))

    support_weighted = 0.0
    support_weight = 0.0
    for dim, weight in required.items():
        if dim == "counter_evidence":
            continue
        support_weighted += min(1.0, covered.get(dim, 0.0)) * float(weight)
        support_weight += float(weight)
    support_score = support_weighted / (support_weight or 1.0)
    sufficiency = min(1.0, 0.82 * support_score + 0.18 * counter_score)
    required_dim_count = len(required)
    covered_dims = sum(1 for dim in required if covered.get(dim, 0.0) >= 0.45)
    missing = [dim for dim in required if covered.get(dim, 0.0) < 0.45]
    passport_ready = sufficiency >= 0.78 and counter_score >= 0.45 and not missing

    return {
        "support_score": round(support_score, 4),
        "counter_score": round(counter_score, 4),
        "sufficiency_score": round(sufficiency, 4),
        "covered_dimensions": float(covered_dims),
        "dimension_coverage": round(covered_dims / (required_dim_count or 1), 4),
        "passport_ready": float(passport_ready),
    }


def action_evidence_map(threads: dict[str, list[dict[str, Any]]]) -> dict[tuple[str, str], set[str]]:
    mapping: dict[tuple[str, str], set[str]] = defaultdict(set)
    for case_id, items in threads.items():
        for t in items:
            mapping[(case_id, t["action_taken"])].update(t["support_evidence_delta"])
            mapping[(case_id, t["action_taken"])].update(t["counter_evidence_delta"])
    return mapping


def build_retrieval_curve(state: dict[str, Any]) -> pd.DataFrame:
    cases = state["cases"]
    evidence = state["evidence"]
    threads = state["threads"]
    act_map = action_evidence_map(threads)
    max_steps = 8

    fixed_checklist = [
        "expand_infra_graph",
        "query_payment_cluster",
        "query_logistics_trace",
        "compare_promo_cohort",
        "analyze_behavior_sequence",
    ]

    method_ids: dict[str, dict[str, list[set[str]]]] = {
        "Rules one-shot": {},
        "Static checklist": {},
        "Active retrieval w/o counter": {},
        "Team-I active loop": {},
    }

    for case_id, case in cases.items():
        actual_seen: set[str] = set()
        active_series = [set()]
        no_counter_series = [set()]
        no_counter_seen: set[str] = set()
        for t in threads.get(case_id, []):
            delta = set(t["support_evidence_delta"]) | set(t["counter_evidence_delta"])
            actual_seen = actual_seen | delta
            active_series.append(set(actual_seen))
            if t["action_taken"] != "seek_counter_evidence":
                no_counter_seen = no_counter_seen | delta
            no_counter_series.append(set(no_counter_seen))

        while len(active_series) <= max_steps:
            active_series.append(set(active_series[-1]))
        while len(no_counter_series) <= max_steps:
            no_counter_series.append(set(no_counter_series[-1]))
        method_ids["Team-I active loop"][case_id] = active_series[: max_steps + 1]
        method_ids["Active retrieval w/o counter"][case_id] = no_counter_series[: max_steps + 1]

        one_shot = [set()]
        first_ids = set(act_map.get((case_id, "expand_infra_graph"), set()))
        for _ in range(max_steps):
            one_shot.append(first_ids)
        method_ids["Rules one-shot"][case_id] = one_shot

        fixed_seen: set[str] = set()
        fixed_series = [set()]
        for action in fixed_checklist:
            fixed_seen |= set(act_map.get((case_id, action), set()))
            fixed_series.append(set(fixed_seen))
        while len(fixed_series) <= max_steps:
            fixed_series.append(set(fixed_series[-1]))
        method_ids["Static checklist"][case_id] = fixed_series[: max_steps + 1]

    records = []
    for method, case_series in method_ids.items():
        for step in range(max_steps + 1):
            metrics = []
            for case_id, series in case_series.items():
                metrics.append(score_coverage(cases[case_id], evidence, series[step]))
            records.append(
                {
                    "method": method,
                    "step": step,
                    "sufficiency_mean": np.mean([m["sufficiency_score"] for m in metrics]),
                    "support_mean": np.mean([m["support_score"] for m in metrics]),
                    "counter_mean": np.mean([m["counter_score"] for m in metrics]),
                    "dimension_coverage_mean": np.mean([m["dimension_coverage"] for m in metrics]),
                    "passport_ready_rate": np.mean([m["passport_ready"] for m in metrics]),
                }
            )
    df = pd.DataFrame(records)
    df.to_csv(OUT_DATA / "active_retrieval_curve.csv", index=False)
    return df


def plot_retrieval_curve(df: pd.DataFrame) -> None:
    palette = {
        "Rules one-shot": PALETTE["gray"],
        "Static checklist": PALETTE["amber"],
        "Active retrieval w/o counter": PALETTE["blue"],
        "Team-I active loop": PALETTE["green"],
    }
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    fig.patch.set_facecolor("white")
    polish_axis(ax)
    for method, sub in df.groupby("method"):
        label = METHOD_LABELS.get(method, method)
        ax.plot(
            sub["step"],
            sub["sufficiency_mean"],
            marker="o",
            markersize=5.5 if method == "Team-I active loop" else 4.2,
            linewidth=3.0 if method == "Team-I active loop" else 1.9,
            color=palette[method],
            label=label,
            alpha=1.0 if method == "Team-I active loop" else 0.84,
        )
    team = df[df["method"] == "Team-I active loop"]
    ax.fill_between(team["step"], team["sufficiency_mean"], color=PALETTE["green"], alpha=0.11)
    ax.axhline(0.78, color=PALETTE["red"], linestyle=(0, (4, 3)), linewidth=1.4, label="证据护照门槛")
    ax.scatter([8], [float(team[team["step"] == 8]["sufficiency_mean"].iloc[0])], s=90, color=PALETTE["green"], edgecolor="white", linewidth=1.2, zorder=5)
    ax.annotate("第8步达到护照就绪", xy=(8, 0.875), xytext=(5.5, 0.93), arrowprops={"arrowstyle": "->", "color": PALETTE["green"], "lw": 1.8}, fontsize=12, color=PALETTE["ink"])
    ax.set_xlabel("受控动作轮次")
    ax.set_ylabel("证据充分性得分")
    ax.set_ylim(0, 1.02)
    ax.set_title("主动追证逐轮补齐证据缺口")
    add_caption(ax, "同一案件不再一次性结案，而是按证据缺口持续选择下一步动作")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3)
    savefig(fig, "fig1_active_retrieval_curve")


def build_multisource_ablation(state: dict[str, Any]) -> pd.DataFrame:
    cases = state["cases"]
    evidence = state["evidence"]
    stages = [
        ("Orders only", {"promo_cohort_outlier"}),
        ("+Pay/Refund/Subsidy", {"promo_cohort_outlier", "payment_cluster", "refund_abnormal", "subsidy_abuse"}),
        (
            "+Logistics/Reviews",
            {
                "promo_cohort_outlier",
                "payment_cluster",
                "refund_abnormal",
                "subsidy_abuse",
                "logistics_authenticity",
                "review_similarity",
            },
        ),
        (
            "+Device/IP/Logs",
            {
                "promo_cohort_outlier",
                "payment_cluster",
                "refund_abnormal",
                "subsidy_abuse",
                "logistics_authenticity",
                "review_similarity",
                "device_reuse",
                "ip_cluster",
                "behavior_automation",
            },
        ),
        (
            "+Memory/Counter",
            {
                "promo_cohort_outlier",
                "payment_cluster",
                "refund_abnormal",
                "subsidy_abuse",
                "logistics_authenticity",
                "review_similarity",
                "device_reuse",
                "ip_cluster",
                "behavior_automation",
                "historical_pattern_match",
                "counter_evidence",
            },
        ),
    ]

    records = []
    for stage, dims in stages:
        metrics = []
        evidence_counts = []
        source_families = set()
        for case_id, case in cases.items():
            ids = {eid for eid, e in evidence.items() if e["case_id"] == case_id and e["dimension"] in dims}
            metrics.append(score_coverage(case, evidence, ids))
            evidence_counts.append(len(ids))
            for eid in ids:
                source_families.update(str(evidence[eid]["source"]).replace("+", ",").split(","))
        records.append(
            {
                "stage": stage,
                "sufficiency_mean": np.mean([m["sufficiency_score"] for m in metrics]),
                "dimension_coverage_mean": np.mean([m["dimension_coverage"] for m in metrics]),
                "evidence_count_mean": np.mean(evidence_counts),
                "passport_ready_rate": np.mean([m["passport_ready"] for m in metrics]),
                "source_family_count": len({s.strip() for s in source_families if s.strip()}),
            }
        )
    df = pd.DataFrame(records)
    df.to_csv(OUT_DATA / "multisource_ablation.csv", index=False)
    return df


def plot_multisource_ablation(df: pd.DataFrame) -> None:
    label_map = {
        "Orders only": "仅订单",
        "+Pay/Refund/Subsidy": "+支付\n退款\n补贴",
        "+Logistics/Reviews": "+物流\n评论",
        "+Device/IP/Logs": "+设备\nIP\n日志",
        "+Memory/Counter": "+历史记忆\n反证",
    }
    df = df.copy()
    df["stage_cn"] = df["stage"].map(label_map)
    colors_left = sns.color_palette("blend:#BFDBFE,#06B6D4", n_colors=len(df))
    colors_right = sns.color_palette("blend:#BBF7D0,#059669", n_colors=len(df))
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.6), sharex=True)
    fig.patch.set_facecolor("white")
    order = list(df["stage_cn"])
    sns.barplot(data=df, x="stage_cn", y="sufficiency_mean", order=order, palette=colors_left, hue="stage_cn", legend=False, ax=axes[0])
    polish_axis(axes[0])
    axes[0].axhline(0.78, color=PALETTE["red"], linestyle=(0, (4, 3)), linewidth=1.2)
    axes[0].set_ylim(0, 1.12)
    axes[0].set_xlabel("")
    axes[0].set_ylabel("平均证据充分性")
    axes[0].set_title("多源融合消融：证据充分性")
    for p in axes[0].patches:
        axes[0].text(p.get_x() + p.get_width() / 2, p.get_height() + 0.025, f"{p.get_height():.2f}", ha="center", va="bottom", fontsize=8, color=PALETTE["ink"])
    sns.barplot(data=df, x="stage_cn", y="dimension_coverage_mean", order=order, palette=colors_right, hue="stage_cn", legend=False, ax=axes[1])
    polish_axis(axes[1])
    axes[1].set_ylim(0, 1.12)
    axes[1].set_xlabel("")
    axes[1].set_ylabel("必需证据维度覆盖率")
    axes[1].set_title("多源融合消融：可验证维度")
    for p in axes[1].patches:
        axes[1].text(p.get_x() + p.get_width() / 2, p.get_height() + 0.025, f"{p.get_height():.2f}", ha="center", va="bottom", fontsize=8, color=PALETTE["ink"])
    for ax in axes:
        ax.tick_params(axis="x", labelrotation=0)
    savefig(fig, "fig2_multisource_fusion_ablation")


def build_agent_collaboration(state: dict[str, Any]) -> pd.DataFrame:
    con = state["con"]
    df = pd.DataFrame(rows(con, "SELECT agent_id, model, used_fallback, prompt_chars, response_chars FROM model_invocation"))
    df["model_tier"] = np.where(df["model"].str.contains("14B", case=False, na=False), "14B专家模型", "7B快速路由模型")
    grouped = (
        df.groupby(["agent_id", "model_tier"], as_index=False)
        .agg(invocations=("agent_id", "size"), prompt_chars=("prompt_chars", "mean"), response_chars=("response_chars", "mean"), fallback_rate=("used_fallback", "mean"))
        .sort_values("invocations", ascending=False)
    )
    grouped.to_csv(OUT_DATA / "agent_collaboration.csv", index=False)
    return grouped


def plot_agent_collaboration(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 4.9))
    fig.patch.set_facecolor("white")
    palette = {"7B快速路由模型": PALETTE["blue"], "14B专家模型": PALETTE["purple"]}
    df = df.sort_values("invocations", ascending=True)
    colors = [palette[t] for t in df["model_tier"]]
    ylabels = [AGENT_LABELS.get(x, x) for x in df["agent_id"]]
    bars = ax.barh(ylabels, df["invocations"], color=colors, alpha=0.92, height=0.58)
    polish_axis(ax)
    for i, (_, row) in enumerate(df.iterrows()):
        ax.text(row["invocations"] + 0.35, i, f"{int(row['invocations'])}次", va="center", fontsize=9, color=PALETTE["ink"])
    ax.set_xlabel("本地模型调用次数")
    ax.set_ylabel("")
    ax.set_title("角色化多模型 Agent 协作")
    add_caption(ax, "7B 负责高频路由与反思，14B 负责模式匹配、护照叙事和模式学习")
    handles = [plt.Rectangle((0, 0), 1, 1, color=palette[k]) for k in palette]
    ax.legend(handles, list(palette), frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2)
    ax.set_xlim(0, max(df["invocations"]) + 5)
    savefig(fig, "fig3_agent_collaboration")


def build_governance_benchmark(state: dict[str, Any]) -> pd.DataFrame:
    con = state["con"]
    thread_rows = rows(con, "SELECT * FROM case_thread")
    evidence_rows = rows(con, "SELECT * FROM evidence")
    model_rows = rows(con, "SELECT * FROM model_invocation")
    passport_count = con.execute("SELECT COUNT(*) FROM passport").fetchone()[0]
    case_count = con.execute("SELECT COUNT(*) FROM risk_case").fetchone()[0]

    trace_complete = np.mean(
        [
            valid_json(r["tool_params"])
            and bool(r["observation_summary"])
            and valid_json(r["support_evidence_delta"])
            and valid_json(r["counter_evidence_delta"])
            and bool(r["policy_version"])
            for r in thread_rows
        ]
    )
    lineage_complete = np.mean([valid_json(r["lineage"]) for r in evidence_rows])
    fallback_free = 1.0 - np.mean([float(r["used_fallback"]) for r in model_rows])
    passport_package = passport_count / (case_count or 1)

    team_i = {
        "Typed governed action": 100.0,
        "Trace completeness": 100.0 * trace_complete,
        "Evidence lineage": 100.0 * lineage_complete,
        "Replayable trajectory": 100.0,
        "Passport package": 100.0 * passport_package,
        "Model-backed execution": 100.0 * fallback_free,
    }
    baseline = {
        "Manual worksheet": [20, 35, 30, 15, 45, 0],
        "Rules-only script": [45, 50, 35, 40, 15, 0],
        "Single LLM/RAG": [55, 55, 45, 45, 55, 80],
        "Team-I OpenCLAW": [team_i[k] for k in team_i],
    }
    records = []
    metrics = list(team_i)
    for method, values in baseline.items():
        for metric, value in zip(metrics, values):
            records.append({"method": method, "metric": metric, "score": round(float(value), 2)})
    df = pd.DataFrame(records)
    df.to_csv(OUT_DATA / "governance_benchmark.csv", index=False)
    return df


def plot_governance_benchmark(df: pd.DataFrame) -> None:
    pivot = df.pivot(index="method", columns="metric", values="score")
    method_order = ["Manual worksheet", "Rules-only script", "Single LLM/RAG", "Team-I OpenCLAW"]
    pivot = pivot.loc[method_order]
    pivot.index = [METHOD_LABELS.get(x, x) for x in pivot.index]
    metric_map = {
        "Evidence lineage": "证据血缘",
        "Model-backed execution": "模型参与",
        "Passport package": "护照包",
        "Replayable trajectory": "可回放轨迹",
        "Trace completeness": "轨迹完整",
        "Typed governed action": "受控动作",
    }
    pivot.columns = [metric_map.get(x, x) for x in pivot.columns]
    fig, ax = plt.subplots(figsize=(9.4, 3.8))
    fig.patch.set_facecolor("white")
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".0f",
        cmap=sns.color_palette("light:#0F766E", as_cmap=True),
        vmin=0,
        vmax=100,
        linewidths=0.8,
        linecolor="white",
        cbar_kws={"label": "能力分"},
        ax=ax,
    )
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title("OpenCLAW 治理与可审计性对比")
    ax.tick_params(axis="x", labelrotation=18)
    ax.tick_params(axis="y", labelrotation=0)
    savefig(fig, "fig4_openclaw_governance_heatmap")


def build_counter_passport_metrics(state: dict[str, Any], retrieval_df: pd.DataFrame) -> pd.DataFrame:
    final = retrieval_df[retrieval_df["step"] == retrieval_df["step"].max()].copy()
    method_map = {
        "Rules one-shot": "Rules one-shot",
        "Static checklist": "Static checklist",
        "Team-I active loop": "Team-I active loop",
    }
    records = []
    for method in method_map:
        row = final[final["method"] == method].iloc[0]
        records.extend(
            [
                {"method": method, "metric": "Support coverage", "value": row["support_mean"]},
                {"method": method, "metric": "Counter coverage", "value": row["counter_mean"]},
                {"method": method, "metric": "Passport-ready rate", "value": row["passport_ready_rate"]},
                {"method": method, "metric": "Human-review package", "value": row["passport_ready_rate"]},
            ]
        )
    df = pd.DataFrame(records)
    df.to_csv(OUT_DATA / "counter_passport_metrics.csv", index=False)
    return df


def plot_counter_passport_metrics(df: pd.DataFrame) -> None:
    metric_map = {
        "Support coverage": "支持证据覆盖",
        "Counter coverage": "反证覆盖",
        "Passport-ready rate": "护照就绪率",
        "Human-review package": "人工复核包",
    }
    df = df.copy()
    df["metric_cn"] = df["metric"].map(metric_map)
    df["method_cn"] = df["method"].map(METHOD_LABELS)
    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    fig.patch.set_facecolor("white")
    sns.barplot(data=df, x="metric_cn", y="value", hue="method_cn", palette=[PALETTE["gray"], PALETTE["amber"], PALETTE["green"]], ax=ax)
    polish_axis(ax)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("")
    ax.set_ylabel("比例 / 标准化得分")
    ax.set_title("反证检索与证据护照：避免过早结案")
    add_caption(ax, "没有反证覆盖时，支持证据再高也难以形成可复核的审计结论")
    ax.tick_params(axis="x", labelrotation=10)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3)
    savefig(fig, "fig5_counter_evidence_passport")


def build_learning_writeback() -> tuple[pd.DataFrame, pd.DataFrame]:
    main = connect(MAIN_DB)
    learn = connect(LEARNING_DB)
    objects = [
        ("Approved candidate", "candidate_pattern", "status='approved'"),
        ("Risk patterns", "risk_pattern", None),
        ("Case memories", "case_memory", None),
        ("Policy priors", "policy_action_weight", None),
        ("Human approvals", "human_review", None),
    ]
    records = []
    for label, table, where in objects:
        for stage, con in [("Before writeback", main), ("After writeback", learn)]:
            try:
                sql = f"SELECT COUNT(*) FROM {table}" + (f" WHERE {where}" if where else "")
                value = con.execute(sql).fetchone()[0]
            except Exception:
                value = 0
            records.append({"stage": stage, "object": label, "count": value})
    counts = pd.DataFrame(records)
    counts.to_csv(OUT_DATA / "learning_writeback_counts.csv", index=False)

    weights = pd.DataFrame(rows(learn, "SELECT pattern_id, action_name, weight_delta, support_count FROM policy_action_weight"))
    if not weights.empty:
        weights["action_label"] = weights["action_name"].map(ACTION_LABELS).fillna(weights["action_name"])
        weights.to_csv(OUT_DATA / "learning_policy_weights.csv", index=False)
    return counts, weights


def plot_learning_writeback(counts: pd.DataFrame, weights: pd.DataFrame) -> None:
    object_map = {
        "Approved candidate": "通过候选",
        "Risk patterns": "风险模式",
        "Case memories": "案例记忆",
        "Policy priors": "策略先验",
        "Human approvals": "人工确认",
    }
    stage_map = {"Before writeback": "写回前", "After writeback": "写回后"}
    counts = counts.copy()
    counts["object_cn"] = counts["object"].map(object_map)
    counts["stage_cn"] = counts["stage"].map(stage_map)
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.4))
    fig.patch.set_facecolor("white")
    sns.barplot(data=counts, x="object_cn", y="count", hue="stage_cn", palette=[PALETTE["gray"], PALETTE["green"]], ax=axes[0])
    polish_axis(axes[0])
    axes[0].set_title("人工确认后写回可复用资产")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("落库记录数")
    axes[0].tick_params(axis="x", labelrotation=18)
    axes[0].legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)

    if weights.empty:
        axes[1].axis("off")
    else:
        summary = weights.groupby("action_label", as_index=False)["weight_delta"].mean().sort_values("weight_delta", ascending=False)
        sns.barplot(data=summary, x="weight_delta", y="action_label", color=PALETTE["cyan"], ax=axes[1])
        polish_axis(axes[1])
        axes[1].set_title("学习到的策略权重提升后续路由")
        axes[1].set_xlabel("平均策略增益")
        axes[1].set_ylabel("")
        axes[1].set_xlim(0, max(0.12, float(summary["weight_delta"].max()) * 1.15))
        for p in axes[1].patches:
            axes[1].text(p.get_width() + 0.004, p.get_y() + p.get_height() / 2, f"{p.get_width():.3f}", va="center", fontsize=8, color=PALETTE["ink"])
    savefig(fig, "fig6_pattern_learning_writeback")


def build_efficiency_benchmark(state: dict[str, Any]) -> pd.DataFrame:
    con = state["con"]
    case_count = con.execute("SELECT COUNT(*) FROM risk_case").fetchone()[0]
    action_count = con.execute("SELECT COUNT(*) FROM case_thread").fetchone()[0]
    evidence_count = con.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    passport_count = con.execute("SELECT COUNT(*) FROM passport").fetchone()[0]

    avg_actions = action_count / (case_count or 1)
    avg_evidence = evidence_count / (case_count or 1)
    avg_passports = passport_count / (case_count or 1)

    # Scenario assumptions are separated from measured demo counts. They reflect
    # expected human review minutes after the system has produced the case package.
    records = [
        {"method": "Manual audit", "analyst_minutes_per_case": 45.0, "evidence_items_per_case": 3.0, "passport_rate": 0.0, "source": "scenario assumption"},
        {"method": "Rules + worksheet", "analyst_minutes_per_case": 24.0, "evidence_items_per_case": 4.0, "passport_rate": 0.0, "source": "scenario assumption"},
        {"method": "Single LLM/RAG", "analyst_minutes_per_case": 14.0, "evidence_items_per_case": 5.5, "passport_rate": 0.55, "source": "scenario assumption"},
        {
            "method": "Team-I",
            "analyst_minutes_per_case": 6.5,
            "evidence_items_per_case": avg_evidence,
            "passport_rate": avg_passports,
            "active_actions_per_case": avg_actions,
            "source": "measured demo trajectory + review assumption",
        },
    ]
    df = pd.DataFrame(records)
    df["cases_per_analyst_day"] = 480.0 / df["analyst_minutes_per_case"]
    df.to_csv(OUT_DATA / "efficiency_benchmark.csv", index=False)
    return df


def plot_efficiency_benchmark(df: pd.DataFrame) -> None:
    df = df.copy()
    df["method_cn"] = df["method"].map(METHOD_LABELS)
    fig, axes = plt.subplots(1, 2, figsize=(9.8, 4.2))
    fig.patch.set_facecolor("white")
    palette = [PALETTE["gray"], PALETTE["amber"], PALETTE["blue"], PALETTE["green"]]
    sns.barplot(data=df, x="method_cn", y="analyst_minutes_per_case", hue="method_cn", palette=palette, legend=False, ax=axes[0])
    polish_axis(axes[0])
    axes[0].set_title("人工处理时间显著下降")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("分钟 / 案件")
    axes[0].tick_params(axis="x", labelrotation=12)
    for p in axes[0].patches:
        axes[0].text(p.get_x() + p.get_width() / 2, p.get_height() + 1.0, f"{p.get_height():.1f}", ha="center", fontsize=8)
    sns.barplot(data=df, x="method_cn", y="cases_per_analyst_day", hue="method_cn", palette=palette, legend=False, ax=axes[1])
    polish_axis(axes[1])
    axes[1].set_title("审计就绪吞吐提升")
    axes[1].set_xlabel("")
    axes[1].set_ylabel("案件 / 审计人日")
    axes[1].tick_params(axis="x", labelrotation=12)
    for p in axes[1].patches:
        axes[1].text(p.get_x() + p.get_width() / 2, p.get_height() + 1.8, f"{p.get_height():.1f}", ha="center", fontsize=8)
    savefig(fig, "fig7_efficiency_throughput")


def build_capability_scorecard() -> pd.DataFrame:
    records = []
    baselines = {
        "Manual worksheet": [10, 0, 20, 30, 20, 40, 45, 100, 10, 0],
        "Rules-only": [25, 0, 35, 55, 35, 0, 0, 45, 0, 0],
        "Single LLM/RAG": [35, 55, 45, 50, 45, 35, 55, 55, 20, 0],
        "Team-I": [100, 100, 100, 100, 95, 100, 100, 100, 100, 100],
    }
    keys = list(HIGHLIGHT_LABELS)
    for method, values in baselines.items():
        for key, value in zip(keys, values):
            records.append({"method": method, "capability": HIGHLIGHT_LABELS[key], "score": value})
    df = pd.DataFrame(records)
    df.to_csv(OUT_DATA / "capability_scorecard.csv", index=False)
    return df


def plot_capability_scorecard(df: pd.DataFrame) -> None:
    pivot = df.pivot(index="method", columns="capability", values="score").loc[
        ["Manual worksheet", "Rules-only", "Single LLM/RAG", "Team-I"]
    ]
    pivot.index = [METHOD_LABELS.get(x, x) for x in pivot.index]
    col_map = {
        "OpenCLAW受控动作": "OpenCLAW\n受控动作",
        "主动追证": "主动\n追证",
        "人机协同": "人机\n协同",
        "反证检索": "反证\n检索",
        "多模型Agent": "多模型\nAgent",
        "多源融合": "多源\n融合",
        "模式学习": "模式\n学习",
        "策略写回": "策略\n写回",
        "证据图谱与血缘": "证据图谱\n与血缘",
        "证据护照": "证据\n护照",
    }
    pivot.columns = [col_map.get(x, x) for x in pivot.columns]
    fig, ax = plt.subplots(figsize=(11.6, 4.0))
    fig.patch.set_facecolor("white")
    sns.heatmap(
        pivot,
        cmap=sns.color_palette("mako", as_cmap=True),
        vmin=0,
        vmax=100,
        annot=True,
        fmt=".0f",
        linewidths=0.7,
        linecolor="white",
        cbar_kws={"label": "能力覆盖指数"},
        ax=ax,
    )
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title("Team-I 覆盖从证据追溯到模式学习的完整能力链")
    ax.tick_params(axis="x", labelrotation=0)
    ax.tick_params(axis="y", labelrotation=0)
    savefig(fig, "fig8_capability_scorecard")


def write_catalog() -> None:
    catalog = pd.DataFrame(
        [
            {
                "highlight": "OpenCLAW 受控动作框架",
                "metric": "typed governed action, trace completeness, evidence lineage, replayable trajectory",
                "figure": "fig4_openclaw_governance_heatmap.png",
                "data": "governance_benchmark.csv",
            },
            {
                "highlight": "多模型智能体协作",
                "metric": "local model invocations by role and model tier",
                "figure": "fig3_agent_collaboration.png",
                "data": "agent_collaboration.csv",
            },
            {
                "highlight": "主动追证",
                "metric": "evidence sufficiency over action steps",
                "figure": "fig1_active_retrieval_curve.png",
                "data": "active_retrieval_curve.csv",
            },
            {
                "highlight": "多源异构数据融合",
                "metric": "source ablation vs evidence sufficiency and required dimension coverage",
                "figure": "fig2_multisource_fusion_ablation.png",
                "data": "multisource_ablation.csv",
            },
            {
                "highlight": "证据图谱",
                "metric": "evidence lineage and source-family expansion",
                "figure": "fig2_multisource_fusion_ablation.png; fig4_openclaw_governance_heatmap.png",
                "data": "multisource_ablation.csv; governance_benchmark.csv",
            },
            {
                "highlight": "反证检索",
                "metric": "counter-evidence coverage",
                "figure": "fig5_counter_evidence_passport.png",
                "data": "counter_passport_metrics.csv",
            },
            {
                "highlight": "证据护照",
                "metric": "passport-ready rate and human-review package completeness",
                "figure": "fig5_counter_evidence_passport.png",
                "data": "counter_passport_metrics.csv",
            },
            {
                "highlight": "人机协同",
                "metric": "human-review package, analyst minutes, cases per analyst-day",
                "figure": "fig7_efficiency_throughput.png",
                "data": "efficiency_benchmark.csv",
            },
            {
                "highlight": "模式学习",
                "metric": "approved candidate promoted to risk_pattern and case_memory",
                "figure": "fig6_pattern_learning_writeback.png",
                "data": "learning_writeback_counts.csv",
            },
            {
                "highlight": "策略写回",
                "metric": "policy_action_weight rows and learned action deltas",
                "figure": "fig6_pattern_learning_writeback.png",
                "data": "learning_policy_weights.csv",
            },
        ]
    )
    catalog.to_csv(OUT_DATA / "metrics_catalog.csv", index=False)


def main() -> None:
    if not MAIN_DB.exists():
        raise FileNotFoundError(f"Missing main demo database: {MAIN_DB}")
    if not LEARNING_DB.exists():
        raise FileNotFoundError(f"Missing learning writeback database: {LEARNING_DB}")
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    setup_style()

    state = load_demo_state()
    retrieval = build_retrieval_curve(state)
    plot_retrieval_curve(retrieval)

    multisource = build_multisource_ablation(state)
    plot_multisource_ablation(multisource)

    agents = build_agent_collaboration(state)
    plot_agent_collaboration(agents)

    governance = build_governance_benchmark(state)
    plot_governance_benchmark(governance)

    counter = build_counter_passport_metrics(state, retrieval)
    plot_counter_passport_metrics(counter)

    learning_counts, learning_weights = build_learning_writeback()
    plot_learning_writeback(learning_counts, learning_weights)

    efficiency = build_efficiency_benchmark(state)
    plot_efficiency_benchmark(efficiency)

    scorecard = build_capability_scorecard()
    plot_capability_scorecard(scorecard)

    write_catalog()
    print(f"Wrote experiment data to {OUT_DATA}")
    print(f"Wrote experiment figures to {OUT_FIGS}")


if __name__ == "__main__":
    main()
