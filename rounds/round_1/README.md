# Round 1 — Trading Groundwork

## Challenge context

Round 1 introduced two products:

- `ASH_COATED_OSMIUM`
- `INTARIAN_PEPPER_ROOT`

Both products had an 80-unit position limit. The goal was to build the first automated trader for these two order books using the historical price and trade data in `sources/round_1/`.

## Data used

The strategy was developed from the Round 1 public data capsule:

```text
sources/round_1/prices_round_1_day_-2.csv
sources/round_1/prices_round_1_day_-1.csv
sources/round_1/prices_round_1_day_0.csv
sources/round_1/trades_round_1_day_-2.csv
sources/round_1/trades_round_1_day_-1.csv
sources/round_1/trades_round_1_day_0.csv
```

## Submitted algorithm

```text
algorithms/round_1_trader.py
```

## Strategy used

The Round 1 algorithm is a two-product fair-value and market-making strategy.

### `INTARIAN_PEPPER_ROOT`

For `INTARIAN_PEPPER_ROOT`, the algorithm uses a deterministic fair-value model:

```python
fair = 9998.5 + 1000 * (day + 2) + timestamp * 0.001
```

Because the live state does not directly provide the day, the code infers the day from the current mid-price and then quotes around the resulting fair value.

The trading logic is:

- compute the fair value from the inferred day and current timestamp;
- buy if the best ask is far below fair value;
- sell if the best bid is far above fair value;
- otherwise post passive bid and ask quotes around fair value;
- skew quotes based on current inventory so the position does not get stuck near the limit.

The passive quotes are asymmetric: the bid is placed closer to fair than the ask. This gives the strategy a small long bias while still keeping both-sided market-making logic.

### `ASH_COATED_OSMIUM`

For `ASH_COATED_OSMIUM`, the algorithm treats the product as mean-reverting around a central fair value of `10000`.

The trading logic is:

- use `10000` as the main fair-value anchor;
- buy visible asks that are meaningfully below fair;
- sell visible bids that are meaningfully above fair;
- place passive quotes around the anchor;
- adjust both bid and ask with an inventory skew.

## Risk controls

The core risk control is position clamping. Every order quantity is clipped so that the resulting position cannot exceed the 80-unit limit for either product. The strategy also changes quote levels when inventory grows, making it more likely to trade back toward neutral inventory.

## What this round contributed

Round 1 established the basic structure used throughout the project: fair-value estimation, taking clearly mispriced visible orders, passive spread capture, and inventory-aware quoting.
