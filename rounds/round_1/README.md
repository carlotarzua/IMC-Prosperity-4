# 🪨 Round 1 — Trading Groundwork

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![IMC Prosperity](https://img.shields.io/badge/IMC_Prosperity-Round_1-0B1F3A?style=for-the-badge)
![Market Making](https://img.shields.io/badge/Strategy-Market_Making-1f6feb?style=for-the-badge)
![Fair Value](https://img.shields.io/badge/Model-Fair_Value-0f766e?style=for-the-badge)

Round 1 introduced the first two tradable products in the challenge: **Ash-Coated Osmium** and **Intarian Pepper Root**. My algorithm focused on estimating fair value, taking clearly mispriced orders, and placing inventory-aware passive quotes around the market.

---

## ✨ Features

- 📈 **Fair-Value Modeling** — Computes reference prices for both products
- 🪴 **Trend-Aware Pepper Root Strategy** — Uses a deterministic time-based fair value for `INTARIAN_PEPPER_ROOT`
- ⚖️ **Mean-Reversion Osmium Strategy** — Anchors `ASH_COATED_OSMIUM` around a stable central value
- 🧾 **Passive Market Making** — Posts bid/ask quotes around estimated fair value
- ⚡ **Aggressive Taking** — Crosses the spread only when visible prices are far from fair
- 🧯 **Inventory Control** — Skews quotes and clips order sizes to respect position limits

---

## 🎯 Round Objective

The goal was to write a Python trader for:

| Product | Role in Strategy | Position Limit |
|---|---|---:|
| `ASH_COATED_OSMIUM` | Mean-reverting asset around a stable anchor | 80 |
| `INTARIAN_PEPPER_ROOT` | Time-trending asset with a deterministic fair-value curve | 80 |

The algorithm needed to generate profit from the historical order-book structure while avoiding excessive inventory risk.

---

## 📊 Data Used

The strategy was developed using the Round 1 public database files:

```text
../../datasets/round1/prices_round_1_day_-2.csv
../../datasets/round1/prices_round_1_day_-1.csv
../../datasets/round1/prices_round_1_day_0.csv
../../datasets/round1/trades_round_1_day_-2.csv
../../datasets/round1/trades_round_1_day_-1.csv
../../datasets/round1/trades_round_1_day_0.csv
```

These files were used to inspect mid-price behavior, spreads, fills, and the relationship between timestamp and product value.

---

## 🧠 How It Works

```text
Read order book
      │
      ▼
Estimate fair value for each product
      │
      ▼
Check visible bid/ask for large mispricings
      │
      ├── Buy cheap asks
      ├── Sell rich bids
      │
      ▼
Place passive quotes around fair value
      │
      ▼
Apply inventory skew and position-limit clipping
      │
      ▼
Return orders to the exchange
```

---

## 📐 Strategy Details

### 1. `INTARIAN_PEPPER_ROOT`

The algorithm models `INTARIAN_PEPPER_ROOT` with a deterministic fair-value formula:

```text
fair = 9998.5 + 1000 × (day + 2) + timestamp × 0.001
```

Because the trading state does not directly provide the day, the algorithm infers it from the current mid-price. Once fair value is estimated, it:

- buys if the best ask is far below fair value,
- sells if the best bid is far above fair value,
- posts a passive bid below fair,
- posts a passive ask above fair,
- applies an inventory skew so quotes become more conservative near the limit.

The bid and ask edges are asymmetric, which gives the strategy a slight long bias while still keeping a market-making structure.

### 2. `ASH_COATED_OSMIUM`

The algorithm treats `ASH_COATED_OSMIUM` as mean-reverting around:

```text
fair = 10000
```

The strategy:

- buys asks that are meaningfully below `10000`,
- sells bids that are meaningfully above `10000`,
- places passive quotes around the anchor,
- adjusts quote levels based on inventory.

This makes the product a spread-capture and mean-reversion component.

---

## 🛡️ Risk Controls

| Risk | Control Used |
|---|---|
| Position limit breach | Every order is clipped before submission |
| Inventory accumulation | Quote skew moves prices toward reducing inventory |
| Bad fills near fair | Aggressive taking only happens beyond a threshold |
| Crossed own spread | Bid and ask are checked before submission |

The most important helper is the quantity clamp, which ensures the algorithm cannot send orders that would exceed the 80-unit limit.

---

## 📂 Files for This Round

```text
round_1/
└── README.md

../../algorithms/
└── round_1_trader.py

../../sources/round_1/
├── prices_round_1_day_-2.csv
├── prices_round_1_day_-1.csv
├── prices_round_1_day_0.csv
├── trades_round_1_day_-2.csv
├── trades_round_1_day_-1.csv
└── trades_round_1_day_0.csv
```

---

## ▶️ Running / Reviewing the Algorithm

The submitted trader is located at:

```text
../../algorithms/round_1_trader.py
```

To review the strategy, open the file and inspect:

```text
_trade_ash()
_trade_ipr()
_ipr_fair()
_clamp()
```

These functions contain the fair-value, execution, and risk-control logic.

---

## 🌱 Future Improvements

- [ ] Backtest several quote edges instead of using fixed hand-tuned values
- [ ] Add automatic spread detection for adaptive market making
- [ ] Track realized fills to adjust passive order size dynamically
- [ ] Add a round-level PnL attribution script by product
