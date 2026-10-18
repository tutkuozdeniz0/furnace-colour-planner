"""
Core model for the furnace colour-campaign planner.

A glass furnace cannot be switched off between jobs. When the production plan
moves from one glass colour to another, the furnace keeps running while the old
colour washes out, and everything pulled during that window is off-spec and has
to be sold at a downgrade or recycled. Switching from a dark colour to a light
one takes far longer than the other way round, so the *order* in which colour
campaigns are run matters as much as which orders are accepted.

All numbers below are illustrative assumptions, not plant data.
"""
from __future__ import annotations

from itertools import permutations

import numpy as np
import pandas as pd

COLOURS = ["flint", "green", "amber"]  # light -> dark

# Days of off-spec glass when switching colour. Row = from, column = to.
# Going dark -> light (green/amber -> flint) is deliberately the slow direction.
TRANSITION_DAYS = np.array(
    [
        [0.0, 2.0, 2.5],  # from flint
        [4.0, 0.0, 1.5],  # from green
        [5.0, 1.5, 0.0],  # from amber
    ]
)

PULL_T_PER_DAY = 250.0        # furnace pull rate, tonnes per day
DOWNGRADE_EUR_PER_T = 60.0    # value lost per tonne of off-spec glass
LATE_EUR_PER_DAY = 8000.0     # penalty per order per day of lateness

TRANSITION_EUR_PER_DAY = PULL_T_PER_DAY * DOWNGRADE_EUR_PER_T

_PERM_CACHE: dict[int, np.ndarray] = {}


def all_permutations(n: int) -> np.ndarray:
    if n not in _PERM_CACHE:
        _PERM_CACHE[n] = np.array(list(permutations(range(n))), dtype=np.int8)
    return _PERM_CACHE[n]


def make_orders(rng: np.random.Generator, n: int = 8) -> pd.DataFrame:
    """Generate one planning window of customer orders (synthetic)."""
    colour_idx = rng.choice(len(COLOURS), size=n, p=[0.5, 0.25, 0.25])
    tonnes = rng.integers(300, 1201, size=n)
    prod_days = tonnes / PULL_T_PER_DAY
    horizon = prod_days.sum()
    due = np.round(rng.uniform(0.35, 1.3, size=n) * horizon + 3, 1)
    return pd.DataFrame(
        {
            "order_id": [f"O{i + 1}" for i in range(n)],
            "colour": [COLOURS[c] for c in colour_idx],
            "colour_idx": colour_idx,
            "tonnes": tonnes,
            "prod_days": prod_days,
            "due_day": due,
        }
    )


def evaluate(orders: pd.DataFrame, start_colour: int, seqs: np.ndarray):
    """Vectorised evaluation of many sequences at once.

    Returns (transition_days, late_days, completion_times) per sequence.
    """
    seqs = np.atleast_2d(seqs)
    colours = orders["colour_idx"].to_numpy()[seqs]
    prev = np.concatenate(
        [np.full((len(seqs), 1), start_colour), colours[:, :-1]], axis=1
    )
    trans = TRANSITION_DAYS[prev, colours]
    prod = orders["prod_days"].to_numpy()[seqs]
    completion = np.cumsum(trans + prod, axis=1)
    late = np.maximum(0.0, completion - orders["due_day"].to_numpy()[seqs])
    return trans.sum(axis=1), late.sum(axis=1), completion


def total_cost(trans_days, late_days):
    return trans_days * TRANSITION_EUR_PER_DAY + late_days * LATE_EUR_PER_DAY


# ---- sequencing strategies -------------------------------------------------

def fifo(orders: pd.DataFrame, start_colour: int) -> np.ndarray:
    """Run orders in the order they were received."""
    return np.arange(len(orders))


def earliest_due_date(orders: pd.DataFrame, start_colour: int) -> np.ndarray:
    return np.argsort(orders["due_day"].to_numpy(), kind="stable")


def colour_block(orders: pd.DataFrame, start_colour: int) -> np.ndarray:
    """Group by colour, light to dark, due date inside each block."""
    return np.lexsort((orders["due_day"].to_numpy(), orders["colour_idx"].to_numpy()))


def optimal(orders: pd.DataFrame, start_colour: int) -> np.ndarray:
    """Exact search over every sequence (fine up to ~9 orders)."""
    perms = all_permutations(len(orders))
    trans, late, _ = evaluate(orders, start_colour, perms)
    return perms[np.argmin(total_cost(trans, late))].astype(int)


STRATEGIES = {
    "FIFO": fifo,
    "Earliest due date": earliest_due_date,
    "Colour blocks (light to dark)": colour_block,
    "Optimal (exhaustive)": optimal,
}


def timeline(orders: pd.DataFrame, start_colour: int, seq: np.ndarray) -> pd.DataFrame:
    """Expand a sequence into production and transition blocks for plotting."""
    rows, t, prev = [], 0.0, start_colour
    for i in seq:
        o = orders.iloc[int(i)]
        tr = TRANSITION_DAYS[prev, int(o["colour_idx"])]
        if tr > 0:
            rows.append(("transition", f"{COLOURS[prev]}→{o['colour']}", t, t + tr, np.nan))
            t += tr
        rows.append((o["colour"], o["order_id"], t, t + o["prod_days"], o["due_day"]))
        t += o["prod_days"]
        prev = int(o["colour_idx"])
    return pd.DataFrame(rows, columns=["kind", "label", "start", "end", "due"])
