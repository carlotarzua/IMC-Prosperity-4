# Round 2 — Growing Your Outpost

## Challenge context

Round 2 continued the same two products from Round 1:

- `ASH_COATED_OSMIUM`
- `INTARIAN_PEPPER_ROOT`

Both products again had an 80-unit position limit. The new algorithmic feature was the Market Access Fee: the submission could include a `bid()` function to compete for 25% more market quotes. The fee was paid only if the bid cleared.

## Data used

The strategy was developed from the Round 2 public data capsule and the Round 1 behavior observed earlier:

```text
sources/round_2/prices_round_2_day_-1.csv
sources/round_2/prices_round_2_day_0.csv
sources/round_2/prices_round_2_day_1.csv
sources/round_2/trades_round_2_day_-1.csv
sources/round_2/trades_round_2_day_0.csv
sources/round_2/trades_round_2_day_1.csv
```

## Submitted algorithm

```text
algorithms/round_2_trader.py
```

## Strategy used

The Round 2 algorithm extends the Round 1 structure with stateful forecasting, microprice information, and the Market Access Fee bid.

### Market Access Fee

The submitted `bid()` function returns:

```python
return 12000
```

This was intended as a blind-auction bid for extra order-book flow: high enough to have a chance of clearing, but not so high that the fee would dominate the expected trading profit.

### `INTARIAN_PEPPER_ROOT`

The Round 2 version no longer uses the explicit linear formula from Round 1. Instead, it stores mid-price history in `traderData` and forecasts fair value with a rolling linear regression.

The trading logic is:

- keep a rolling mid-price history;
- forecast fair value several steps forward with linear regression;
- if there is not enough history, fall back to a small upward-drift estimate;
- build long inventory toward the 80-unit limit when asks are not too far above the forecast;
- once heavily long, place a passive ask above fair value to avoid accidentally selling too cheaply.

This makes `INTARIAN_PEPPER_ROOT` a directional/statistical component rather than a symmetric market-making component.

### `ASH_COATED_OSMIUM`

`ASH_COATED_OSMIUM` remains a mean-reversion and spread-capture strategy, but the fair value is more adaptive than in Round 1.

The trading logic is:

- compute a top-of-book microprice when bid and ask volumes are available;
- maintain recent price history in `traderData`;
- estimate fair value with a blend of fast EMA, slow EMA, and an anchor toward `10000`;
- take visible orders when prices are clearly better than fair;
- clear inventory opportunistically near fair;
- make passive markets inside the spread with inventory-adjusted quote sizes.

## Risk controls

The strategy clips all buys and sells against the 80-unit limits. `ASH_COATED_OSMIUM` also changes quote size depending on inventory: when long, it reduces buy size and increases sell size; when short, it does the reverse. `INTARIAN_PEPPER_ROOT` uses a target-position framework rather than unlimited directional buying.

## What this round contributed

Round 2 added persistent state, rolling statistical forecasts, microprice-based fair-value refinement, and auction-style access management.
