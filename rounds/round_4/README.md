# 🤖 Round 4 — The More the Merrier

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![IMC Prosperity](https://img.shields.io/badge/IMC_Prosperity-Round_4-0B1F3A?style=for-the-badge)
![Counterparty Signals](https://img.shields.io/badge/Strategy-Counterparty_Signals-16a34a?style=for-the-badge)
![Options](https://img.shields.io/badge/Model-Options_%2B_Flow-9333ea?style=for-the-badge)

Round 4 kept the Round 3 products but added named counterparty information. My algorithm used those participant IDs as live trading signals, while still maintaining the voucher pricing and market-making framework from Round 3.

---

## ✨ Features

- 🧑‍💻 **Counterparty-Aware Signals** — Reads `buyer` and `seller` fields from public trades
- ⏳ **Signal Decay** — Old participant information fades over time
- ⚡ **Fast and Slow Flow Signals** — Tracks both slower and faster participant effects
- 📊 **Book Pressure Signal** — Uses order-book imbalance as an additional fair-value shift
- 🍇 **Updated Voucher Pricing** — Reprices vouchers with shorter Round 4 time to expiry
- 🧯 **Per-Product Risk Limits** — Uses position caps, strike controls, and inventory-aware quotes

---

## 🎯 Round Objective

Round 4 used the same tradable products as Round 3:

| Product Group | Instruments | Position Limit |
|---|---|---:|
| Delta-one products | `HYDROGEL_PACK`, `VELVETFRUIT_EXTRACT` | 200 each |
| Vouchers | `VEV_4000` to `VEV_6500` | 300 each |

The new task was to incorporate counterparty information from historical and live trades.

---

## 📊 Data Used

The repository includes the Round 4 price database:

```text
../../sources/round_4/prices_round_4_day_1.csv
../../sources/round_4/prices_round_4_day_2.csv
../../sources/round_4/prices_round_4_day_3.csv
```

The final algorithm also uses live trade data fields:

```text
trade.buyer
trade.seller
trade.price
trade.quantity
trade.timestamp
```

These fields allow the strategy to shift fair values based on observed participant behavior.

---

## 🧠 How It Works

```text
Read order books and public market trades
      │
      ▼
Update participant signals from buyer/seller IDs
      │
      ├── pair-specific buyer/seller effects
      ├── participant-level effects
      └── quantity-scaled signal updates
      │
      ▼
Apply signal decay
      │
      ▼
Compute fair value
      │
      ├── Delta-one: anchor + EMA + flow + book pressure
      └── Vouchers: option fair value + signal adjustments
      │
      ▼
Take strong mispricings and quote passively
      │
      ▼
Apply inventory and strike-level risk controls
```

---

## 📐 Strategy Details

### 1. Counterparty Signal Engine

The algorithm stores participant signals in `traderData`:

```text
sig   = slower product-level participant signal
fsig  = faster signal for delta-one products
```

For every public market trade, the algorithm checks the buyer and seller. It then applies:

- `PAIR_ALPHA` weights for specific buyer/seller pair effects,
- `MARK_ALPHA` weights for participant-level effects,
- signal decay so older observations become less important,
- quantity scaling so larger trades matter more.

### 2. Delta-One Products

For `HYDROGEL_PACK` and `VELVETFRUIT_EXTRACT`, fair value is built from:

```text
fixed anchor
+ EMA component
+ slow participant signal
+ fast participant signal
+ book-pressure signal
```

The algorithm then takes visible orders that are far from adjusted fair and posts passive quotes around the adjusted quote fair.

### 3. Voucher Products

The voucher strategy still uses the option-pricing framework, but it includes Round 4-specific updates:

- shorter time to expiry,
- updated volatility-smile parameters,
- signal-adjusted `VELVETFRUIT_EXTRACT` spot value,
- strike-level active fair values,
- quote bias by strike.

The algorithm disables `VEV_6000` and `VEV_6500` in the submitted configuration.

---

## 🛡️ Risk Controls

| Risk | Control Used |
|---|---|
| Counterparty signal noise | Signal decay and caps |
| Overtrading vouchers | Per-strike long/short limits and lot sizes |
| Inventory imbalance | Reservation prices are skewed by position |
| Product limit breach | Orders are clipped against product limits |
| Weak strikes | Selected voucher strikes are disabled |

---

## 📂 Files for This Round

```text
round_4/
└── README.md

../../algorithms/
└── round_4_trader.py

../../sources/round_4/
├── prices_round_4_day_1.csv
├── prices_round_4_day_2.csv
└── prices_round_4_day_3.csv
```

---

## ▶️ Running / Reviewing the Algorithm

The submitted trader is located at:

```text
../../algorithms/round_4_trader.py
```

Important sections to inspect:

```text
PAIR_ALPHA
MARK_ALPHA
_update_mark_signals()
_book_pressure_signal()
_take_anchor_edges()
_voucher_fair_value()
_quote_option()
```

---

## 🌱 Future Improvements

- [ ] Add a separate analysis notebook for participant-level PnL contribution
- [ ] Validate each counterparty coefficient with train/test splits
- [ ] Add automated plots of signal strength over time
- [ ] Add stronger controls for when participant signals disagree with option fair value
