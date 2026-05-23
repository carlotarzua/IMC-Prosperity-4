# 🍇 Round 3 — Gloves Off

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![IMC Prosperity](https://img.shields.io/badge/IMC_Prosperity-Round_3-0B1F3A?style=for-the-badge)
![Options](https://img.shields.io/badge/Strategy-Options_Pricing-9333ea?style=for-the-badge)
![Black Scholes](https://img.shields.io/badge/Model-Black--Scholes_Style-2563eb?style=for-the-badge)

Round 3 reset the leaderboard and introduced a new product family: two delta-one assets and ten vouchers on `VELVETFRUIT_EXTRACT`. My algorithm combined anchored trading in the underlying products with option-style theoretical pricing for the vouchers.

---

## ✨ Features

- 🍇 **Voucher Pricing** — Treats `VEV_*` products as call-option-style instruments
- 📉 **Volatility Smile Model** — Uses a quadratic implied-volatility curve by moneyness
- ⚖️ **Delta-One Anchors** — Trades `HYDROGEL_PACK` and `VELVETFRUIT_EXTRACT` around calibrated fair values
- 🧾 **Surface Shift Estimation** — Adjusts voucher fair value using current voucher mids
- ⚡ **Taker + Passive Execution** — Takes large mispricings and quotes around fair value
- 🧯 **PnL-Aware Risk Mode** — Reduces exposure after large drawdowns

---

## 🎯 Round Objective

The goal was to trade a new Solvenar product set:

| Product Group | Instruments | Position Limit |
|---|---|---:|
| Delta-one products | `HYDROGEL_PACK`, `VELVETFRUIT_EXTRACT` | 200 each |
| Vouchers | `VEV_4000` to `VEV_6500` | 300 each |

The vouchers represented the right to buy Velvetfruit Extract at a specific strike price. Because they behave like options, the strategy needed more than simple mid-price mean reversion.

---

## 📊 Data Used

The strategy was developed using the Round 3 database files:

```text
../../datasets/round3/prices_round_3_day_0.csv
../../datasets/round3/prices_round_3_day_1.csv
../../datasets/round3/prices_round_3_day_2.csv
../../datasets/round3/trades_round_3_day_0.csv
../../datasets/round3/trades_round_3_day_1.csv
../../datasets/round3/trades_round_3_day_2.csv
```

These files were used to calibrate fair-value anchors, voucher strike behavior, and implied-volatility parameters.

---

## 🧠 How It Works

```text
Read order books
      │
      ▼
Compute mids for underlying and vouchers
      │
      ├── Delta-one products: fixed anchor + EMA adjustment
      │
      └── Vouchers: Black-Scholes-style fair value
              │
              ├── underlying mid
              ├── strike
              ├── time to expiry
              ├── quadratic volatility smile
              └── strike-specific vol bias
      │
      ▼
Compare market price to theoretical fair value
      │
      ├── Take cheap asks / rich bids
      └── Post passive quotes around fair
      │
      ▼
Scale exposure using risk mode and position limits
```

---

## 📐 Strategy Details

### 1. Delta-One Products

The algorithm trades the two non-voucher products around fixed anchors:

```text
HYDROGEL_PACK fair ≈ 10000
VELVETFRUIT_EXTRACT fair ≈ 5251
```

For each product, the strategy:

- computes a taker fair value,
- computes a passive quote fair value,
- buys asks far below fair,
- sells bids far above fair,
- places passive quotes around fair,
- skews reservation price based on inventory.

### 2. Voucher Fair Value

Each voucher is priced as a call-option-style product using:

```text
underlying = VELVETFRUIT_EXTRACT mid-price
strike = number in VEV product name
time to expiry ≈ Round 3 TTE
volatility = quadratic smile + strike-specific adjustment + surface shift
```

The model estimates theoretical option value and compares it to the current market.

### 3. Voucher Execution

The algorithm trades voucher deviations from theoretical value:

- buy if an ask is below fair by enough edge,
- sell if a bid is above fair by enough edge,
- quote passively around fair for selected strikes,
- skip or disable strikes that were not attractive in the submitted configuration.

In the submitted version, the deepest out-of-the-money vouchers `VEV_6000` and `VEV_6500` are skipped, and `VEV_5500` is disabled.

---

## 🛡️ Risk Controls

| Risk | Control Used |
|---|---|
| Product position limits | 200 for delta-one products, 300 for each voucher |
| Option overexposure | Per-strike lots and disabled strike list |
| Drawdown risk | Tracks estimated mark-to-market PnL and peak PnL |
| Bad risk regime | Defensive and lock modes reduce order size |
| Stale state | Memory is JSON encoded and refreshed every timestamp |

---

## 📂 Files for This Round

```text
round_3/
└── README.md

../../algorithms/
└── round_3_trader.py

../../sources/round_3/
├── prices_round_3_day_0.csv
├── prices_round_3_day_1.csv
├── prices_round_3_day_2.csv
├── trades_round_3_day_0.csv
├── trades_round_3_day_1.csv
└── trades_round_3_day_2.csv
```

---

## ▶️ Running / Reviewing the Algorithm

The submitted trader is located at:

```text
../../algorithms/round_3_trader.py
```

Important sections to inspect:

```text
STRIKES
SMILE_A / SMILE_B / SMILE_C
STRIKE_VOL_BIAS
_voucher_fair_value()
_surface_shift()
_take_option_edges()
_quote_option()
```

---

## 🌱 Future Improvements

- [ ] Add explicit delta-hedging between vouchers and `VELVETFRUIT_EXTRACT`
- [ ] Backtest strike-by-strike contribution to identify which vouchers add value
- [ ] Make risk mode less dependent on estimated mark-to-market noise
- [ ] Add plots for implied volatility and voucher residuals
