# Round 4 — The More the Merrier

## Challenge context

Round 4 kept the Round 3 product set:

- `HYDROGEL_PACK`
- `VELVETFRUIT_EXTRACT`
- `VEV_4000` through `VEV_6500`

The new feature was named counterparty information. Historical trades now included buyer and seller IDs, so the algorithm could use market-participant behavior as a signal.

## Data used

The repository contains Round 4 price data:

```text
sources/round_4/prices_round_4_day_1.csv
sources/round_4/prices_round_4_day_2.csv
sources/round_4/prices_round_4_day_3.csv
```

The final algorithm also uses the Round 4 counterparty fields available in live `market_trades`. Those fields are accessed through each trade's `buyer` and `seller` attributes.

## Submitted algorithm

```text
algorithms/round_4_trader.py
```

## Strategy used

The Round 4 algorithm keeps the Round 3 structure but adds counterparty-aware fair-value shifts.

### Counterparty signal engine

The code maintains two signal dictionaries in `traderData`:

- `sig`: slower participant signal by product;
- `fsig`: faster participant signal for the delta-one products.

For each public market trade, the algorithm reads:

```python
trade.buyer
trade.seller
trade.quantity
```

It then applies two types of signal weights:

- pair-specific buyer/seller weights from `PAIR_ALPHA`;
- participant-level weights from `MARK_ALPHA`.

Signals decay over time, so old counterparty information gradually loses influence. Larger trades receive a larger signal contribution through quantity scaling.

### Delta-one products

For `HYDROGEL_PACK` and `VELVETFRUIT_EXTRACT`, fair value combines:

- a fixed anchor;
- a slow EMA of observed mids;
- the counterparty signal;
- a faster flow signal;
- book-pressure imbalance from the top levels of the order book.

The strategy then:

- takes visible orders when the book is far enough away from signal-adjusted fair;
- posts passive quotes around the adjusted fair;
- skews quotes by inventory.

### Voucher products

The voucher model still uses option-style pricing on `VELVETFRUIT_EXTRACT`, but Round 4 updates the parameters for shorter time to expiry.

The option fair value uses:

- current `VELVETFRUIT_EXTRACT` mid-price;
- a signal-adjusted underlying price;
- strike-specific voucher parameters;
- a quadratic volatility smile;
- observed surface shift from current voucher mids;
- Black-Scholes-style call pricing.

For execution, the algorithm uses two fair values:

- `active_fair` for aggressive taking;
- `quote_fair` for passive quoting.

`active_fair` is strike-specific and designed for stricter visible-book opportunities. `quote_fair` blends recent voucher market information with a quote bias. The strategy disables `VEV_6000` and `VEV_6500`.

## Risk controls

The algorithm enforces position limits for every product and uses per-strike long/short limits for vouchers. It tracks cash, mark-to-market PnL, and product-level peak PnL. The final submitted configuration keeps the main trading logic focused on counterparty-adjusted fair values and controlled passive quoting rather than large late-round flattening rules.

## What this round contributed

Round 4 added informed-flow features: participant IDs became real-time signals that shifted fair values and changed how aggressively the algorithm traded.
