# Furnace Colour-Campaign Planner

A small operations-research project about one of the quieter headaches in glass manufacturing: a furnace never really stops, so changing the glass colour is not a setup you can simply schedule around. While the old colour washes out, the furnace keeps pulling glass that cannot be sold at full value, and the washout is much slower when you go from a dark colour back to a light one than the other way round. That asymmetry means the order in which you run colour campaigns can be worth far more than the usual "oldest order first" habit suggests.

This repository models that problem, compares four sequencing rules on 500 simulated planning windows, and shows how much the choice of rule is worth.

> **Important:** every number in this project is an illustrative assumption on synthetic data. Nothing here comes from Şişecam or any other company, and the project is not affiliated with one. The transition times, pull rate and costs are plausible placeholders you can replace with real plant figures in `src/planner.py`.

## The setup

One furnace pulls 250 tonnes a day and produces three colours: flint, green and amber. A planning window contains 8 customer orders, each with a colour, a tonnage and a due date. Switching colour costs days of off-spec glass according to this matrix (rows are the colour you leave, columns the colour you move to):

| from \ to | flint | green | amber |
|-----------|-------|-------|-------|
| flint     | 0     | 2.0   | 2.5   |
| green     | 4.0   | 0     | 1.5   |
| amber     | 5.0   | 1.5   | 0     |

Each off-spec day costs 250 t × 60 EUR/t = 15,000 EUR, and each day an order is late costs 8,000 EUR. The planner picks the sequence of orders that minimises the sum of both.

## Strategies compared

- **FIFO**: run orders in the order they arrived.
- **Earliest due date**: the classic deadline-driven rule.
- **Colour blocks**: group by colour from light to dark, ordering by due date inside each block.
- **Optimal**: exhaustive search over all 8! = 40,320 sequences, vectorised with NumPy so that 500 scenarios run in seconds.

## Results (500 simulated windows, seed 42)

| Strategy | Colour-change days | Late days | Mean cost per window | vs FIFO |
|---|---|---|---|---|
| FIFO | 14.9 | 41.5 | 556k EUR | baseline |
| Earliest due date | 14.9 | 21.2 | 393k EUR | -29% |
| Colour blocks (light to dark) | 5.4 | 14.0 | 193k EUR | -65% |
| Optimal (exhaustive) | 5.5 | 5.1 | 123k EUR | -78% |

Two things stand out. Earliest due date fixes lateness but ignores colour entirely, so it pays exactly as much in colour changes as FIFO does. Colour blocking cuts colour changes by almost two thirds but lets deadlines slip. The optimal sequence is not simply a compromise: it often accepts one extra colour change when that saves several late days, which is why it beats the better of the two simple rules in 73% of windows, by about 61k EUR on average.

![Cost by strategy](results/cost_by_strategy.png)

![Example schedule](results/example_schedule.png)

The example above is the scenario whose saving is closest to the median, not a hand-picked best case. Hatched blocks are colour changes, and the triangles mark each order's due date (red where it is missed).

![Saving distribution](results/saving_distribution.png)

## Run it

```bash
pip install -r requirements.txt
cd src
python simulate.py
```

This regenerates everything in `results/`: `summary.csv`, `all_scenarios.csv` (one row per scenario and strategy) and the three charts.

## Project layout

```
src/planner.py     model, cost function, sequencing strategies
src/simulate.py    scenario generation, comparison, charts
results/           generated tables and figures
```

## Limitations

The windows are treated as independent, so the colour the furnace ends on is not carried into the next window, and a real planner would add a terminal cost for that. There is a single furnace and no maintenance or campaign-length limits. Exhaustive search is only practical up to about 9 orders, so larger windows would need a MILP formulation or a local-search heuristic, and comparing those against the exact answer on small cases would be a natural next step.

## Ideas for extending it

- Replace the synthetic orders with a real order book and the matrix with measured washout times.
- Add cullet (recycled glass) share as a decision variable, since it lowers furnace energy use and interacts with colour.
- Swap exhaustive search for OR-Tools or a simulated-annealing heuristic and test where it starts to lose to the exact solution.
- Carry the end-of-window colour into a rolling horizon over several months.
