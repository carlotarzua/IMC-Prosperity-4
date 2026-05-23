# Round 3 — Gloves Off

## Challenge context

Round 3 reset the leaderboard and introduced a new product set:

- `HYDROGEL_PACK`
- `VELVETFRUIT_EXTRACT`
- 10 Velvetfruit Extract vouchers: `VEV_4000`, `VEV_4500`, `VEV_5000`, `VEV_5100`, `VEV_5200`, `VEV_5300`, `VEV_5400`, `VEV_5500`, `VEV_6000`, `VEV_6500`

`HYDROGEL_PACK` and `VELVETFRUIT_EXTRACT` are delta-one products. The vouchers behave like call-option-style instruments on `VELVETFRUIT_EXTRACT`, with different strikes and time to expiry.

## Data used

The strategy was developed from the Round 3 public data capsule:

```text
sources/round_3/prices_round_3_day_0.csv
sources/round_3/prices_round_3_day_1.csv
sources/round_3/prices_round_3_day_2.csv
sources/round_3/trades_round_3_day_0.csv
sources/round_3/trades_round_3_day_1.csv
sources/round_3/trades_round_3_day_2.csv
```

## Submitted algorithm

```text
algorithms/round_3_trader.py
```

## Strategy used

The Round 3 algorithm has two main parts: anchored trading for the delta-one products and option-style pricing for the vouchers.

### Delta-one products

The algorithm trades `HYDROGEL_PACK` and `VELVETFRUIT_EXTRACT` with fixed fair-value anchors plus light EMA adjustment.

The configured anchors are:

```python
HYDROGEL_PACK fair ≈ 10000
VELVETFRUIT_EXTRACT fair ≈ 5251
```

For each delta-one product, the strategy:

- computes a taker fair value and a passive quote fair value;
- buys asks below fair by more than a product-specific take edge;
- sells bids above fair by more than the take edge;
- places passive bid/ask quotes around fair;
- skews quotes based on inventory.

### Voucher pricing

The voucher strategy treats each active `VEV_*` product as a call-option-style contract on `VELVETFRUIT_EXTRACT`.

The pricing model uses:

- the current `VELVETFRUIT_EXTRACT` mid-price as the underlying;
- the strike embedded in the product name;
- Round 3 time to expiry, starting from roughly 5 days;
- a quadratic implied-volatility smile as a function of moneyness;
- strike-specific volatility bias adjustments;
- Black-Scholes-style call pricing.

The code estimates a volatility-surface shift from observed voucher mids, then converts the fitted volatility back into a theoretical voucher fair value.

### Voucher execution

The strategy trades voucher mispricings in two ways:

- aggressively takes visible asks below theoretical fair value;
- aggressively sells visible bids above theoretical fair value;
- posts passive quotes around the option fair value for selected strikes.

The deepest out-of-the-money strikes `VEV_6000` and `VEV_6500` are skipped. `VEV_5500` is also disabled in the submitted version. Deep in-the-money vouchers are priced close to intrinsic value.

## Risk controls

The algorithm tracks cash and mark-to-market PnL in `traderData`. It maintains a peak-PnL estimate and can enter defensive or lock modes if drawdown becomes too large. In those modes, order sizes are reduced and the strategy can become reduce-only. Position limits are enforced for all products: 200 for the two delta-one products and 300 for each voucher.

## What this round contributed

Round 3 introduced the first options-pricing layer: implied-volatility fitting, strike-level fair-value estimation, and PnL-aware risk scaling.
