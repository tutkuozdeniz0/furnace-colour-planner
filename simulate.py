"""Run many random planning windows, compare strategies, save tables and charts."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import planner as P

N_SCENARIOS = 500
N_ORDERS = 8
SEED = 42
OUT = Path(__file__).resolve().parent.parent / "results"

GLASS = {"flint": "#cfe3ea", "green": "#4f8a4b", "amber": "#c97b1a"}


def run() -> tuple[pd.DataFrame, list]:
    rows, cases = [], []
    for s in range(N_SCENARIOS):
        rng = np.random.default_rng(SEED + s)
        orders = P.make_orders(rng, N_ORDERS)
        start = int(rng.choice(len(P.COLOURS), p=[0.5, 0.25, 0.25]))
        case = {"orders": orders, "start": start, "seqs": {}}
        for name, fn in P.STRATEGIES.items():
            seq = fn(orders, start)
            trans, late, _ = P.evaluate(orders, start, seq)
            rows.append(
                {
                    "scenario": s,
                    "strategy": name,
                    "transition_days": trans[0],
                    "late_days": late[0],
                    "transition_cost": trans[0] * P.TRANSITION_EUR_PER_DAY,
                    "late_cost": late[0] * P.LATE_EUR_PER_DAY,
                }
            )
            case["seqs"][name] = seq
        cases.append(case)
    df = pd.DataFrame(rows)
    df["total_cost"] = df["transition_cost"] + df["late_cost"]
    return df, cases


def chart_costs(df: pd.DataFrame) -> None:
    g = df.groupby("strategy")[["transition_cost", "late_cost"]].mean().loc[list(P.STRATEGIES)]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    y = np.arange(len(g))
    ax.barh(y, g["transition_cost"] / 1e3, color="#5b7c99", label="Colour-change loss")
    ax.barh(y, g["late_cost"] / 1e3, left=g["transition_cost"] / 1e3, color="#d98c5f", label="Late-delivery penalty")
    ax.set_yticks(y, g.index)
    ax.invert_yaxis()
    ax.set_xlabel("Mean cost per 8-order planning window (thousand EUR)")
    ax.set_title("What the sequencing rule costs you")
    ax.legend(frameon=False, loc="lower right")
    for i, v in enumerate(g.sum(axis=1) / 1e3):
        ax.text(v + 2, i, f"{v:,.0f}k", va="center", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "cost_by_strategy.png", dpi=160)
    plt.close(fig)


def chart_savings(df: pd.DataFrame) -> None:
    p = df.pivot(index="scenario", columns="strategy", values="total_cost")
    saving = (p["FIFO"] - p["Optimal (exhaustive)"]) / 1e3
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(saving, bins=30, color="#5b7c99", edgecolor="white")
    ax.axvline(saving.mean(), color="#d98c5f", lw=2, label=f"mean {saving.mean():,.0f}k EUR")
    ax.set_xlabel("Saving of optimal vs FIFO, per window (thousand EUR)")
    ax.set_ylabel("Scenarios")
    ax.set_title(f"Saving distribution across {N_SCENARIOS} simulated windows")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "saving_distribution.png", dpi=160)
    plt.close(fig)


def chart_gantt(df: pd.DataFrame, cases: list) -> int:
    p = df.pivot(index="scenario", columns="strategy", values="total_cost")
    saving = p["FIFO"] - p["Optimal (exhaustive)"]
    s = int((saving - saving.median()).abs().idxmin())  # a typical case, not a cherry-picked one
    case = cases[s]
    fig, axes = plt.subplots(2, 1, figsize=(11, 4.6), sharex=True)
    for ax, name in zip(axes, ["FIFO", "Optimal (exhaustive)"]):
        tl = P.timeline(case["orders"], case["start"], case["seqs"][name])
        for _, r in tl.iterrows():
            w = r["end"] - r["start"]
            if r["kind"] == "transition":
                ax.barh(0, w, left=r["start"], color="#e5e5e5", edgecolor="#888", hatch="///", height=0.6)
            else:
                ax.barh(0, w, left=r["start"], color=GLASS[r["kind"]], edgecolor="white", height=0.6)
                ax.text(r["start"] + w / 2, 0, r["label"], ha="center", va="center", fontsize=8,
                        color="white" if r["kind"] != "flint" else "#234")
                late = r["end"] > r["due"]
                ax.plot(r["due"], 0.42, marker="v", color="#c0392b" if late else "#777", ms=6)
                ax.text(r["due"], 0.56, r["label"], ha="center", va="bottom", fontsize=7,
                        color="#c0392b" if late else "#555")
        trans, lat, _ = P.evaluate(case["orders"], case["start"], case["seqs"][name])
        cost = P.total_cost(trans, lat)[0] / 1e3
        ax.set_title(f"{name}: {trans[0]:.1f} transition days, {lat[0]:.1f} late days, cost {cost:,.0f}k EUR",
                     fontsize=10, loc="left")
        ax.set_yticks([])
        ax.set_ylim(-0.4, 0.8)
        ax.spines[["top", "right", "left"]].set_visible(False)
    axes[1].set_xlabel("Furnace day   (hatched = colour change; triangle = that order's due date, red if missed)")
    fig.tight_layout()
    fig.savefig(OUT / "example_schedule.png", dpi=160)
    plt.close(fig)
    return s


def main() -> None:
    OUT.mkdir(exist_ok=True)
    df, cases = run()
    df.to_csv(OUT / "all_scenarios.csv", index=False)

    summary = (
        df.groupby("strategy")[["transition_days", "late_days", "total_cost"]]
        .mean()
        .loc[list(P.STRATEGIES)]
        .round(1)
    )
    base = summary.loc["FIFO", "total_cost"]
    summary["vs_FIFO_%"] = ((summary["total_cost"] / base - 1) * 100).round(1)
    summary.to_csv(OUT / "summary.csv")

    p = df.pivot(index="scenario", columns="strategy", values="total_cost")
    chart_costs(df)
    chart_savings(df)
    s = chart_gantt(df, cases)

    print(summary.to_string())
    print(f"\nExample schedule shown: scenario {s}")
    sav = p["FIFO"] - p["Optimal (exhaustive)"]
    print(f"Mean saving optimal vs FIFO: {sav.mean():,.0f} EUR  (median {sav.median():,.0f}, p90 {sav.quantile(.9):,.0f})")
    best_heur = p[["Earliest due date", "Colour blocks (light to dark)"]].min(axis=1)
    gap = (best_heur - p["Optimal (exhaustive)"])
    print(f"Best simple rule vs optimal, mean gap: {gap.mean():,.0f} EUR; optimal strictly better in {(gap>1).mean():.0%} of windows")


if __name__ == "__main__":
    main()
