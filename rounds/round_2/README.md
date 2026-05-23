# 🛰️ Round 2 — Growing Your Outpost

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![IMC Prosperity](https://img.shields.io/badge/IMC_Prosperity-Round_2-0B1F3A?style=for-the-badge)
![Stateful Strategy](https://img.shields.io/badge/Model-Stateful_Forecasting-7c3aed?style=for-the-badge)
![Auction Bid](https://img.shields.io/badge/Feature-Market_Access_Fee-f97316?style=for-the-badge)

Round 2 continued the same two products from Round 1, but added a **Market Access Fee** mechanism. My algorithm combined a blind-auction bid for extra order-book flow with a more stateful trading model using stored price history, microprice, and rolling forecasts.

---

## ✨ Features

- 🧾 **Market Access Fee Bid** — Implements `bid()` to compete for extra market visibility
- 🧠 **Persistent Trader State** — Stores recent mid-price history in `traderData`
- 📈 **Linear Forecasting** — Uses rolling regression for `INTARIAN_PEPPER_ROOT`
- ⚖️ **Adaptive Mean Reversion** — Uses EMA and microprice for `ASH_COATED_OSMIUM`
- 🧹 **Inventory Clearing Logic** — Attempts to reduce inventory near fair-value levels
- 🧯 **Position-Aware Order Sizing** — Adjusts order quantities based on current inventory

---

## 🎯 Round Objective

Round 2 reused the same products and limits:

| Product | Strategy Role | Position Limit |
|---|---|---:|
| `ASH_COATED_OSMIUM` | Adaptive mean-reversion and spread capture | 80 |
| `INTARIAN_PEPPER_ROOT` | Directional/statistical forecast strategy | 80 |

The new challenge was deciding how much to bid for extra market access while improving the Round 1 algorithm.

---

## 📊 Data Used

The strategy was developed using the Round 2 database files:

```text
../../sources/round_2/prices_round_2_day_-1.csv
../../sources/round_2/prices_round_2_day_0.csv
../../sources/round_2/prices_round_2_day_1.csv
../../sources/round_2/trades_round_2_day_-1.csv
../../sources/round_2/trades_round_2_day_0.csv
../../sources/round_2/trades_round_2_day_1.csv
```

The Round 1 behavior was also useful as background for understanding spread width, mean reversion, and directional drift.

---

## 🧠 How It Works

```text
Start round
   │
   ├── Submit Market Access Fee bid
   │
   ▼
Read live order books
   │
   ▼
Load stored price history from traderData
   │
   ├── Pepper Root: rolling linear regression forecast
   └── Osmium: microprice + EMA fair value
   │
   ▼
Take clearly mispriced visible orders
   │
   ▼
Clear inventory when favorable
   │
   ▼
Post passive inventory-aware quotes
   │
   ▼
Save updated traderData
```

---

## 📐 Strategy Details

### 1. Market Access Fee

The submitted algorithm includes:

```python
def bid(self):
    return 12000
```

This was a blind-auction decision. The goal was to bid high enough to have a reasonable chance of receiving the extra 25% market access, while keeping the fee low enough that trading profit could still offset it.

### 2. `INTARIAN_PEPPER_ROOT`

In Round 2, the strategy moves away from the exact Round 1 formula and instead uses stored mid-price history.

The logic is:

- store recent mid-prices in `traderData`,
- run a rolling linear regression on the recent price sequence,
- forecast fair value several steps forward,
- buy toward a target long inventory when asks are not too expensive,
- avoid selling too much inventory too early,
- leave a passive ask above fair when inventory is close to the long target.

This turns `INTARIAN_PEPPER_ROOT` into a directional forecast strategy rather than a purely symmetric market maker.

### 3. `ASH_COATED_OSMIUM`

For `ASH_COATED_OSMIUM`, the algorithm remains mean-reversion focused but uses a better fair-value estimate.

It combines:

- top-of-book mid-price,
- microprice weighted by bid/ask size,
- fast EMA,
- slow EMA,
- an anchor toward `10000`.

The strategy then takes favorable orders, clears inventory when the book allows it, and posts passive quotes around the adaptive fair value.

---

## 🛡️ Risk Controls

| Risk | Control Used |
|---|---|
| State overflow | `traderData` is JSON-compressed and truncated safely |
| Position limits | Buy and sell quantities are clipped separately |
| Overbuying Pepper Root | Uses a target inventory framework |
| Inventory imbalance in Osmium | Quote sizes shift toward reducing inventory |
| Noisy history | Falls back to simple estimates when history is short |

---

## 📂 Files for This Round

```text
round_2/
└── README.md

../../algorithms/
└── round_2_trader.py

../../sources/round_2/
├── prices_round_2_day_-1.csv
├── prices_round_2_day_0.csv
├── prices_round_2_day_1.csv
├── trades_round_2_day_-1.csv
├── trades_round_2_day_0.csv
└── trades_round_2_day_1.csv
```

---

## ▶️ Running / Reviewing the Algorithm

The submitted trader is located at:

```text
../../algorithms/round_2_trader.py
```

Important functions to inspect:

```text
bid()
_trade_ipr()
_trade_ash()
_linreg_forecast()
_microprice()
_load_data() / _dump_data()
```

---

## 🌱 Future Improvements

- [ ] Tune the Market Access Fee with a more explicit expected-value model
- [ ] Compare rolling regression with the deterministic Round 1 fair-value formula
- [ ] Add product-level PnL attribution for directional versus passive fills
- [ ] Improve inventory exit logic near the end of the round
