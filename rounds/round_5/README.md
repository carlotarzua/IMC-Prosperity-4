# Round 5 — The Final Stretch

## Challenge context

Round 5 replaced the earlier products with 50 new instruments across 10 categories. Every product had a position limit of 10. The goal was to identify useful structure in the public database and choose which products deserved risk.

## Data used

The final submitted code contains parameters calibrated from the Round 5 data analysis. The source folder for Round 5 is present as a placeholder in this archive:

```text
sources/round_5/.gitkeep
```

The Round 5 analysis that directly influenced the submitted algorithm is summarized in:

```text
docs/round_5_pattern_discovery.md
```

## Submitted algorithm

```text
algorithms/round_5_trader.py
```

## Strategy used

The Round 5 algorithm uses two active strategy layers:

1. a Purification Pebbles relative-value module;
2. a QAPCA/PCA-based cross-sectional fair-value module for the 50-product universe.

Some additional modules exist in the code as experimental scaffolding, but in the final submitted configuration they are inactive because their product dictionaries are empty or they are not called from `run()`.

### Purification Pebbles module

The data analysis found that the five Pebbles products were tightly linked by a basket-style constraint:

```text
PEBBLES_XS + PEBBLES_S + PEBBLES_M + PEBBLES_L + PEBBLES_XL ≈ 50000
```

The final code actively trades selected Pebbles using this fair-value relationship. For each selected Pebble:

```python
fair_i = 50000 - sum(other Pebbles mids)
```

The algorithm then compares this fair value against the current best bid and ask:

- if the ask is sufficiently below fair, it buys;
- if the bid is sufficiently above fair, it sells;
- otherwise it posts passive quotes around the derived fair value;
- quote levels and sizes are adjusted for current inventory.

The specific Pebbles traded changes by session profile. The strategy generally focuses on `PEBBLES_L`, `PEBBLES_M`, and `PEBBLES_XL`, with some session-dependent adjustments.

### QAPCA cross-sectional fair-value module

The main Round 5 model is QAPCA: a PCA-style reconstruction model across all 50 products.

The code stores:

- the 50-product universe in `QAPCA_PRODUCTS`;
- calibrated log-price means in `QAPCA_MU`;
- calibrated log-price standard deviations in `QAPCA_SD`;
- principal-component loadings in `QAPCA_PCS`.

At every timestamp, the algorithm:

1. reads live mid-prices for all 50 products;
2. converts each price into a standardized log-price z-score;
3. projects the z-score vector onto the principal components;
4. reconstructs a cross-sectional fair value for each product;
5. compares each product's PCA-implied fair value to its live mid-price;
6. places inventory-aware quotes when the residual is large enough.

The final fair value is intentionally blended with the live mid-price. This avoids trading the PCA reconstruction too aggressively when the current market is already close to fair.

### Product selection and sizing

The algorithm separates products into risk buckets:

- `CORE_PRODUCTS`: allowed to use the full 10-unit limit more often;
- `SECONDARY_PRODUCTS`: traded with smaller exposure;
- `REDUCED_PRODUCTS`: traded very lightly;
- `QAPCA_SKIP`: excluded from the PCA quote engine.

It also uses session profiles based on timestamp. Each session has:

- an opportunity set that can receive larger size and lower entry thresholds;
- a reduction set that is traded cautiously or flattened.

### Execution logic

For each active QAPCA product, the algorithm:

- skips products with very tight or very wide spreads;
- computes residual between PCA fair and live mid;
- adjusts quote fair using residual, order-book imbalance, and inventory skew;
- may take the best visible bid/ask for stronger boosted residuals;
- otherwise places passive bid/ask orders inside the spread.

## Risk controls

Every product has a hard 10-unit position limit. The algorithm also reduces maximum exposure for secondary and reduced products, lightens products in the session reduction set, skips specified symbols, and forces flattening at the configured final timestamp.

## What this round contributed

Round 5 moved from single-product fair values to portfolio-level relative value. The final strategy used the database to calibrate cross-sectional structure, then traded live residuals with strict product-level inventory limits.
