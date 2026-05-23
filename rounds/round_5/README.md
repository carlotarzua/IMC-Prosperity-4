# 🌌 Round 5 — The Final Stretch

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![IMC Prosperity](https://img.shields.io/badge/IMC_Prosperity-Round_5-0B1F3A?style=for-the-badge)
![PCA](https://img.shields.io/badge/Model-QAPCA_%2F_PCA-2563eb?style=for-the-badge)
![Relative Value](https://img.shields.io/badge/Strategy-Relative_Value-0f766e?style=for-the-badge)

Round 5 replaced the earlier products with **50 new instruments** across 10 product categories. My final algorithm used two main strategy layers: a structural relative-value model for **Purification Pebbles** and a PCA-style cross-sectional fair-value model across the full product universe.

---

## ✨ Features

- 🪨 **Pebbles Basket Constraint** — Uses the relationship between all five Pebbles products
- 🧠 **QAPCA / PCA Fair Value** — Reconstructs fair prices from cross-sectional log-price structure
- 📊 **Residual Trading** — Trades deviations between live prices and PCA-implied fair values
- 🧾 **Product Selection Buckets** — Separates products into core, secondary, reduced, and skipped groups
- ⏱️ **Session Profiles** — Changes risk settings across different parts of the round
- 🧯 **Strict 10-Unit Limits** — Keeps exposure small across the 50-product universe

---

## 🎯 Round Objective

Round 5 introduced 50 new products. Every product had a position limit of 10.

| Group | Example Products | Strategy Relevance |
|---|---|---|
| Purification Pebbles | `PEBBLES_XS`, `PEBBLES_S`, `PEBBLES_M`, `PEBBLES_L`, `PEBBLES_XL` | Structural relative value |
| Protein Snack Packs | `SNACKPACK_CHOCOLATE`, `SNACKPACK_VANILLA`, etc. | Relationship analysis / secondary signals |
| Domestic Robots | `ROBOT_DISHES`, `ROBOT_IRONING`, etc. | Selective PCA opportunities |
| Other categories | Galaxy Sounds, Microchips, Panels, Translators, Pods, Visors, Oxygen Shakes | Cross-sectional PCA universe |

The goal was to identify which products had exploitable structure in the provided database and build one final algorithm.

---

## 📊 Data Used

The submitted code contains parameters calibrated from Round 5 database analysis. The repository also includes the analysis summary:

```text
../../docs/round_5_pattern_discovery.md
```

The Round 5 source folder is included as a placeholder:

```text
../../sources/round_5/.gitkeep
```

The key database finding used directly in the submitted strategy was the Pebbles relationship:

```text
PEBBLES_XS + PEBBLES_S + PEBBLES_M + PEBBLES_L + PEBBLES_XL ≈ 50000
```

---

## 🧠 How It Works

```text
Read live mid-prices for 50 products
      │
      ├─────────────────────────────┐
      │                             │
      ▼                             ▼
Pebbles relative-value engine    QAPCA / PCA engine
      │                             │
      │                             ├── log-transform prices
      │                             ├── standardize with calibrated means/stds
      │                             ├── project onto principal components
      │                             ├── reconstruct fair values
      │                             └── compute residuals
      │                             │
      └──────────────┬──────────────┘
                     ▼
        Generate inventory-aware quotes
                     │
                     ▼
        Take strong visible mispricings
                     │
                     ▼
        Enforce 10-unit product limits
```

---

## 📐 Strategy Details

### 1. Purification Pebbles Engine

The analysis found that the five Pebbles products were linked by a near-fixed sum:

```text
sum(all five Pebbles mids) ≈ 50000
```

For each selected Pebble, the algorithm derives a fair value from the other four:

```text
fair_i = 50000 - sum(other four Pebbles mids)
```

The execution logic is:

- buy if the best ask is sufficiently below derived fair,
- sell if the best bid is sufficiently above derived fair,
- otherwise quote passively around fair,
- adjust quote size and price based on current inventory.

The final submitted version focuses most actively on selected Pebbles such as `PEBBLES_L`, `PEBBLES_M`, and `PEBBLES_XL`, with session-dependent adjustments.

### 2. QAPCA / PCA Fair-Value Engine

The main cross-sectional model stores:

```text
QAPCA_PRODUCTS  = 50-product universe
QAPCA_MU        = calibrated log-price means
QAPCA_SD        = calibrated log-price standard deviations
QAPCA_PCS       = principal-component loadings
```

At each timestamp, the algorithm:

1. reads live mid-prices,
2. converts prices to log space,
3. standardizes each product,
4. projects the standardized vector onto the PCA components,
5. reconstructs a fair-value estimate,
6. compares reconstructed fair value to the live mid-price,
7. trades only when the residual is large enough.

The final fair value is blended with the live mid-price to avoid overreacting to the PCA reconstruction.

### 3. Product Selection and Session Profiles

The code groups products into different risk buckets:

| Bucket | Purpose |
|---|---|
| `CORE_PRODUCTS` | Main products allowed to use larger exposure |
| `SECONDARY_PRODUCTS` | Products traded with smaller size |
| `REDUCED_PRODUCTS` | Products traded cautiously |
| `QAPCA_SKIP` | Products excluded from the PCA quote engine |

Session profiles adjust thresholds and product focus depending on the timestamp.

---

## 🛡️ Risk Controls

| Risk | Control Used |
|---|---|
| 50-product overexposure | Hard 10-unit limit for every product |
| Weak PCA residuals | Minimum residual thresholds before trading |
| Illiquid or poor products | Skip and reduced-product lists |
| Inventory imbalance | Quote fair value is skewed by current position |
| Late-round risk | Final flattening / exposure reduction logic |

---

## 📂 Files for This Round

```text
round_5/
└── README.md

../../algorithms/
└── round_5_trader.py

../../docs/
└── round_5_pattern_discovery.md

../../sources/round_5/
└── .gitkeep
```

---

## ▶️ Running / Reviewing the Algorithm

The submitted trader is located at:

```text
../../algorithms/round_5_trader.py
```

Important sections to inspect:

```text
QAPCA_PRODUCTS
QAPCA_MU
QAPCA_SD
QAPCA_PCS
_trade_pebbles()
_trade_qapca()
_session_profile()
```

---

## 🌱 Future Improvements

- [ ] Add the full Round 5 database files to `sources/round_5/`
- [ ] Add a notebook showing the PCA calibration process
- [ ] Add residual plots by product and timestamp
- [ ] Compare the PCA engine with simpler pair/basket-only strategies
- [ ] Add backtest metrics for each risk bucket
