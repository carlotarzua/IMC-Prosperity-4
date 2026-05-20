from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Optional, Tuple
import json
import math


class Trader:
    """
    Round 4 strategy:
      1) Delta-one market-making/taking core for HYDROGEL and VELVETFRUIT.
      2) Counterparty-aware fair-value shifts from disclosed Mark IDs.
      3) Product-level option fair bands for active taking.
      4) Option surface model only used for passive quote placement.
    """

    LIMITS = {
        "HYDROGEL_PACK": 200,
        "VELVETFRUIT_EXTRACT": 200,
        "VEV_4000": 300,
        "VEV_4500": 300,
        "VEV_5000": 300,
        "VEV_5100": 300,
        "VEV_5200": 300,
        "VEV_5300": 300,
        "VEV_5400": 300,
        "VEV_5500": 300,
        "VEV_6000": 300,
        "VEV_6500": 300,
    }

    STRIKES = {
        "VEV_4000": 4000,
        "VEV_4500": 4500,
        "VEV_5000": 5000,
        "VEV_5100": 5100,
        "VEV_5200": 5200,
        "VEV_5300": 5300,
        "VEV_5400": 5400,
        "VEV_5500": 5500,
        "VEV_6000": 6000,
        "VEV_6500": 6500,
    }

    # Refit on the supplied Round 4 price files, using historical TTEs:
    # day 1 => 7d, day 2 => 6d, day 3 => 5d.
    # IV = a*m^2 + b*m + c + strike_bias, m = log(K/S)/sqrt(T).
    SMILE_A = 0.01289221
    SMILE_B = 0.00222875
    SMILE_C = 0.22986081
    STRIKE_VOL_BIAS = {
        5000: 0.000918,
        5100: -0.003327,
        5200: 0.002180,
        5300: 0.005571,
        5400: -0.010352,
        5500: 0.005014,
    }

    DELTA_PRODUCTS = {
        "HYDROGEL_PACK": {
            "fair": 10026.0,
            # Slightly more active than v5; the flow layer now decides direction.
            "take_edge": 18.5,
            "passive_edge": 3.0,
            "skew": 0.055,
            "lot": 30,
            "ema_blend": 0.06,
            "signal_blend": 1.05,
            "signal_cap": 7.0,
        },
        "VELVETFRUIT_EXTRACT": {
            "fair": 5250.0,
            "take_edge": 13.8,
            "passive_edge": 1.8,
            "skew": 0.052,
            "lot": 42,
            "ema_blend": 0.20,
            "signal_blend": 1.00,
            "signal_cap": 7.0,
        },
    }

    # Pair-level forward-mid alphas extracted from trades_round_4_day_1..3.
    # Positive means buyer->seller trades were followed by higher mids.
    PAIR_ALPHA = {
        "HYDROGEL_PACK": {
            # Directional Mark 14/38 flow is the useful Hydrogel signal.
            ("Mark 14", "Mark 38"): 1.05,
            ("Mark 38", "Mark 14"): -1.45,
            ("Mark 22", "Mark 38"): -4.20,
            ("Mark 38", "Mark 22"): 2.20,
        },
        "VELVETFRUIT_EXTRACT": {
            # Mark 67 buying is strongly upward; Mark 49/22 as buyers are usually weak.
            ("Mark 67", "Mark 49"): 2.45,
            ("Mark 67", "Mark 22"): 2.25,
            ("Mark 55", "Mark 22"): 2.05,
            ("Mark 22", "Mark 49"): 2.15,
            ("Mark 55", "Mark 14"): 1.10,
            ("Mark 55", "Mark 49"): 1.10,
            ("Mark 14", "Mark 55"): -0.85,
            ("Mark 49", "Mark 22"): -2.20,
            ("Mark 22", "Mark 55"): -1.10,
            ("Mark 55", "Mark 01"): -0.45,
            ("Mark 01", "Mark 55"): 0.25,
        },
        "VEV_5200": {
            ("Mark 01", "Mark 22"): 1.20,  # shrunk from a small-sample 2.7
            ("Mark 14", "Mark 22"): 0.25,
        },
        "VEV_5300": {
            ("Mark 14", "Mark 22"): 0.35,
        },
        "VEV_5400": {
            ("Mark 01", "Mark 22"): 0.15,
            ("Mark 14", "Mark 22"): -0.45,
        },
    }

    # Participant fallback if an unseen pair appears. These are deliberately
    # smaller than pair alphas to reduce overfit.
    MARK_ALPHA = {
        "HYDROGEL_PACK": {
            "Mark 14": 0.70,
            "Mark 38": -0.70,
            "Mark 22": -1.35,
        },
        "VELVETFRUIT_EXTRACT": {
            "Mark 67": 1.65,
            "Mark 55": 0.45,
            "Mark 14": -0.45,
            "Mark 49": -1.25,
            "Mark 22": -0.65,
            "Mark 01": 0.05,
        },
        "VEV_5200": {"Mark 01": 0.50, "Mark 14": 0.20, "Mark 22": -0.30},
        "VEV_5300": {"Mark 14": 0.25, "Mark 22": -0.20},
        "VEV_5400": {"Mark 01": 0.10, "Mark 14": -0.25, "Mark 22": -0.05},
    }

    SIGNAL_DECAY = 0.92
    OPTION_SIGNAL_DECAY = 0.88

    # Delta-one informed-flow extras.  `sig` is the slow signal already used by v5;
    # `fsig` reacts faster to fresh Mark prints and top-of-book imbalance.
    DELTA_FAST_DECAY = {
        "HYDROGEL_PACK": 0.72,
        "VELVETFRUIT_EXTRACT": 0.78,
    }
    DELTA_FAST_WEIGHT = {
        "HYDROGEL_PACK": 0.55,
        "VELVETFRUIT_EXTRACT": 0.45,
    }
    DELTA_BOOK_WEIGHT = {
        "HYDROGEL_PACK": 0.85,
        "VELVETFRUIT_EXTRACT": 0.60,
    }
    DELTA_FLOW_CAP = {
        "HYDROGEL_PACK": 9.0,
        "VELVETFRUIT_EXTRACT": 8.0,
    }

    # Extra live-signal layers from the round hint notes:
    # - activity_signal: persistent Mark arrival/burst read, not just one trade.
    # - reversal guard: small mean-reversion nudge only when price is stretched
    #   and momentum starts turning back.
    # - option delta hedge: uses VFE quotes to soften large VEV inventory exposure
    #   without changing the successful VEV engine.
    DELTA_ACTIVITY_DECAY = {
        "HYDROGEL_PACK": 0.84,
        "VELVETFRUIT_EXTRACT": 0.86,
    }
    DELTA_ACTIVITY_WEIGHT = {
        "HYDROGEL_PACK": 0.24,
        "VELVETFRUIT_EXTRACT": 0.16,
    }
    REVERSAL_WEIGHT = {
        "HYDROGEL_PACK": 0.62,
        "VELVETFRUIT_EXTRACT": 0.34,
    }
    REVERSAL_CAP = {
        "HYDROGEL_PACK": 1.35,
        "VELVETFRUIT_EXTRACT": 0.85,
    }
    REVERSAL_THRESHOLD = {
        "HYDROGEL_PACK": 16.0,
        "VELVETFRUIT_EXTRACT": 12.0,
    }
    OPTION_DELTA_HEDGE_WEIGHT = 0.0045
    OPTION_DELTA_HEDGE_CAP = 1.65

    # Options: use guarded market-making instead of letting the model
    # open large one-way shorts.  The v3 table showed that the main issue was
    # not delta-one, but VEV_5000/5100/5200 being allowed to accumulate large
    # short inventory before the model was proven right.
    DISABLED_OPTION_STRIKES = {6000, 6500}

    OPTION_TAKE_EDGE = {
        4000: 10.0,
        4500: 8.0,
        5000: 10.0,
        5100: 10.0,
        5200: 10.0,
        5300: 5.0,
        5400: 3.0,
        5500: 1.0,
    }

    # Calibrated active option centers. These are product-level bands,
    # not timestamp/path rules.
    OPTION_ACTIVE_FAIR = {
        4000: 1252.0,
        4500: 745.5,
        5000: 250.5,
        5100: 167.0,
        5200: 79.5,
        5300: 47.0,
        5400: 16.0,
        5500: 4.5,
    }

    OPTION_PASSIVE_EDGE = {
        4000: 1.20,
        4500: 1.15,
        5000: 0.95,
        5100: 0.90,
        5200: 0.80,
        5300: 0.65,
        5400: 0.45,
        5500: 0.35,
    }
    OPTION_LOT = {
        4000: 10,
        4500: 10,
        5000: 10,
        5100: 10,
        5200: 10,
        5300: 10,
        5400: 10,
        5500: 10,
    }

    # Long side can be meaningful; short side is capped much lower because the
    # last run's negative VEV rows came from max-short inventories.
    OPTION_LONG_LIMIT = {
        4000: 300,
        4500: 300,
        5000: 300,
        5100: 300,
        5200: 300,
        5300: 300,
        5400: 300,
        5500: 300,
        6000: 0,
        6500: 0,
    }
    OPTION_SHORT_LIMIT = {
        4000: 300,
        4500: 300,
        5000: 300,
        5100: 300,
        5200: 300,
        5300: 300,
        5400: 300,
        5500: 300,
        6000: 0,
        6500: 0,
    }

    # Small quote-fair biases keep the option maker from repeatedly leaning
    # short when the Black-Scholes surface is below the visible market.
    OPTION_QUOTE_BIAS = {
        4000: 0.50,
        4500: 0.50,
        5000: 1.25,
        5100: 1.15,
        5200: 0.90,
        5300: 0.55,
        5400: 0.20,
        5500: 0.05,
    }

    # If an individual VEV starts losing, stop opening new risk in that product.
    OPTION_STOP_LOSS = {
        4000: -1_000_000.0,
        4500: -1_000_000.0,
        5000: -1_000_000.0,
        5100: -1_000_000.0,
        5200: -1_000_000.0,
        5300: -1_000_000.0,
        5400: -1_000_000.0,
        5500: -1_000_000.0,
    }
    OPTION_DRAWDOWN_STOP = {
        4000: 1_000_000.0,
        4500: 1_000_000.0,
        5000: 1_000_000.0,
        5100: 1_000_000.0,
        5200: 1_000_000.0,
        5300: 1_000_000.0,
        5400: 1_000_000.0,
        5500: 1_000_000.0,
    }

    # Do not let a portfolio-level drawdown lock switch off the option maker too early.
    # Product-level option guardrails below control risk strike-by-strike; these
    # large absolute thresholds are a last resort.
    PROFIT_LOCK_MIN_PEAK = 1_000_000_000.0
    DEFENSIVE_DRAWDOWN_ABS = 80_000.0
    DEFENSIVE_DRAWDOWN_FRAC = 0.90
    HARD_LOCK_DRAWDOWN_ABS = 160_000.0
    HARD_LOCK_DRAWDOWN_FRAC = 0.95
    DEFENSIVE_COOLDOWN = 3000
    HARD_LOCK_COOLDOWN = 6000
    OPTION_REDUCE_TS = 10**9
    FORCE_FLAT_TS = 10**9

    def bid(self):
        return 0

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        memory = self._load_memory(state.traderData)

        mids = {product: self._mid_price(depth) for product, depth in state.order_depths.items()}

        # Update fair anchors and counterparty signal state.
        ema = memory.setdefault("ema", {})
        for product, mid in mids.items():
            if mid is None:
                continue
            previous = float(ema.get(product, mid))
            ema[product] = 0.04 * float(mid) + 0.96 * previous

        self._update_mid_state(memory, mids)
        self._update_mark_signals(memory, state)
        self._update_cash_from_own_trades(memory, state)

        current_pnl = self._estimate_mtm_pnl(memory, state.position, mids)
        peak_pnl = max(float(memory.get("peak_pnl", current_pnl)), current_pnl)
        memory["peak_pnl"] = peak_pnl
        drawdown = peak_pnl - current_pnl
        risk_mode = self._risk_mode(memory, state.timestamp, peak_pnl, drawdown)

        if state.timestamp >= self.FORCE_FLAT_TS:
            result = self._flatten_all(state)
            return result, 0, self._dump_memory(memory)

        if risk_mode == "LOCK":
            delta_scale = 0.45
            option_scale = 0.15
            delta_reduce_only = True
            option_reduce_only = True
        elif risk_mode == "DEFENSIVE":
            delta_scale = 0.75
            option_scale = 0.35
            delta_reduce_only = False
            option_reduce_only = False
        else:
            delta_scale = 1.00
            option_scale = 1.00
            delta_reduce_only = False
            option_reduce_only = False

        if state.timestamp >= self.OPTION_REDUCE_TS:
            option_reduce_only = True
            option_scale = min(option_scale, 0.35)

        mark_signals = memory.get("sig", {}) if isinstance(memory.get("sig", {}), dict) else {}
        hedge_shift = self._option_delta_hedge_shift(state.position, mids, state.timestamp)

        # Delta-one products are the main engine.
        for product, config in self.DELTA_PRODUCTS.items():
            depth = state.order_depths.get(product)
            if depth is None:
                continue

            orders: List[Order] = []
            position = int(state.position.get(product, 0))
            anchor = float(config["fair"])
            ema_fair = float(ema.get(product, anchor))
            raw_signal = float(mark_signals.get(product, 0.0))
            raw_signal = self._clip(raw_signal, -float(config["signal_cap"]), float(config["signal_cap"]))

            fast_signals = memory.get("fsig", {}) if isinstance(memory.get("fsig", {}), dict) else {}
            fast_signal = float(fast_signals.get(product, 0.0))
            fast_signal = self._clip(
                fast_signal,
                -float(self.DELTA_FLOW_CAP.get(product, float(config["signal_cap"]))),
                float(self.DELTA_FLOW_CAP.get(product, float(config["signal_cap"]))),
            )
            book_signal = self._book_pressure_signal(product, depth)
            activity_signals = memory.get("asig", {}) if isinstance(memory.get("asig", {}), dict) else {}
            activity_signal = self._clip(float(activity_signals.get(product, 0.0)), -6.0, 6.0)

            flow_shift = (
                float(config["signal_blend"]) * raw_signal
                + float(self.DELTA_FAST_WEIGHT.get(product, 0.0)) * fast_signal
                + float(self.DELTA_BOOK_WEIGHT.get(product, 0.0)) * book_signal
                + float(self.DELTA_ACTIVITY_WEIGHT.get(product, 0.0)) * activity_signal
            )
            flow_shift = self._agreement_adjusted_flow(
                product, flow_shift, raw_signal, fast_signal, book_signal, activity_signal
            )

            reversal_shift = self._reversal_adjustment(
                product,
                mids.get(product),
                anchor,
                ema_fair,
                memory,
                flow_shift,
            )
            if product == "VELVETFRUIT_EXTRACT":
                reversal_shift += hedge_shift

            adjusted_shift = flow_shift + reversal_shift

            fair = (
                (1.0 - float(config["ema_blend"])) * anchor
                + float(config["ema_blend"]) * ema_fair
                + adjusted_shift
            )
            passive_fair = (
                0.84 * anchor
                + 0.16 * ema_fair
                + 0.55 * raw_signal
                + 0.35 * fast_signal
                + 0.30 * book_signal
                + 0.12 * activity_signal
                + 0.45 * reversal_shift
            )

            used_buy, used_sell = self._take_anchor_edges(
                product,
                depth,
                orders,
                position,
                fair,
                float(config["take_edge"]),
                0,
                0,
                delta_scale,
                delta_reduce_only,
            )
            self._make_market(
                product,
                depth,
                orders,
                position,
                passive_fair,
                float(config["passive_edge"]),
                float(config["skew"]),
                int(config["lot"]),
                used_buy,
                used_sell,
                delta_scale,
                delta_reduce_only,
            )
            if orders:
                result[product] = orders

        # Options: aggressive passive market-making + selective visible-book taking.
        velvet_mid = mids.get("VELVETFRUIT_EXTRACT")
        if velvet_mid is not None:
            tte_years = self._time_to_expiry_years(state.timestamp)
            vol_shift = self._surface_shift(state.order_depths, float(velvet_mid), tte_years)
            underlying_signal = float(mark_signals.get("VELVETFRUIT_EXTRACT", 0.0))
            signal_spot = float(velvet_mid) + 0.35 * self._clip(underlying_signal, -5.0, 5.0)

            for product, strike in self.STRIKES.items():
                depth = state.order_depths.get(product)
                if depth is None:
                    continue
                if strike in self.DISABLED_OPTION_STRIKES:
                    continue

                model_fair = self._voucher_fair_value(signal_spot, strike, tte_years, vol_shift)
                if model_fair is None:
                    continue
                model_fair += self._clip(float(mark_signals.get(product, 0.0)), -1.5, 1.5)

                # For quoting, anchor mostly to the option's own mid/EMA so the
                # maker keeps earning spread even if the theoretical surface is
                # a few ticks off.
                opt_mid = mids.get(product)
                opt_ema = float(ema.get(product, opt_mid if opt_mid is not None else model_fair))
                if opt_mid is None:
                    quote_fair = model_fair
                else:
                    quote_fair = 0.20 * opt_ema + 0.80 * float(opt_mid)

                quote_fair += float(self.OPTION_QUOTE_BIAS.get(strike, 0.0))

                orders = []
                position = int(state.position.get(product, 0))

                product_pnl = self._product_mtm_pnl(memory, product, position, opt_mid if opt_mid is not None else model_fair)
                peaks = memory.setdefault("prod_peak", {})
                if isinstance(peaks, dict):
                    prev_peak = float(peaks.get(product, product_pnl))
                    peaks[product] = max(prev_peak, product_pnl)
                    product_drawdown = float(peaks[product]) - product_pnl
                else:
                    product_drawdown = 0.0

                local_reduce_only = option_reduce_only
                if product_pnl <= float(self.OPTION_STOP_LOSS.get(strike, -10**9)):
                    local_reduce_only = True
                if product_drawdown >= float(self.OPTION_DRAWDOWN_STOP.get(strike, 10**9)):
                    local_reduce_only = True

                active_fair = float(self.OPTION_ACTIVE_FAIR.get(strike, quote_fair))
                used_buy, used_sell = self._take_option_edges(
                    product,
                    strike,
                    depth,
                    orders,
                    position,
                    active_fair,
                    0,
                    0,
                    option_scale,
                    local_reduce_only,
                )
                self._quote_option(
                    product,
                    strike,
                    depth,
                    orders,
                    position,
                    quote_fair,
                    used_buy,
                    used_sell,
                    option_scale,
                    local_reduce_only,
                )
                if orders:
                    result[product] = orders

        trader_data = self._dump_memory(memory)
        return result, 0, trader_data

    # -------------------------- signal layer --------------------------

    def _update_mark_signals(self, memory: Dict, state: TradingState) -> None:
        signals = memory.setdefault("sig", {})
        if not isinstance(signals, dict):
            signals = {}
            memory["sig"] = signals

        fast_signals = memory.setdefault("fsig", {})
        if not isinstance(fast_signals, dict):
            fast_signals = {}
            memory["fsig"] = fast_signals

        activity_signals = memory.setdefault("asig", {})
        if not isinstance(activity_signals, dict):
            activity_signals = {}
            memory["asig"] = activity_signals

        # Slow signal: persistent information from repeated bot prints.
        for product in list(signals.keys()):
            decay = self.OPTION_SIGNAL_DECAY if product.startswith("VEV_") else self.SIGNAL_DECAY
            signals[product] = float(signals.get(product, 0.0)) * decay
            if abs(float(signals[product])) < 0.02:
                signals[product] = 0.0

        # Fast signal: fresh delta-one flow. This decays faster and only affects
        # HYDROGEL/VFE fair shifts, so it can improve entries without altering the VEV engine.
        for product in list(fast_signals.keys()):
            decay = float(self.DELTA_FAST_DECAY.get(product, 0.70))
            fast_signals[product] = float(fast_signals.get(product, 0.0)) * decay
            if abs(float(fast_signals[product])) < 0.03:
                fast_signals[product] = 0.0

        # Activity signal: keeps a small memory of repeated Mark arrivals/bursts.
        # This follows the hint to anticipate repeated bot behavior without using timestamps.
        for product in list(activity_signals.keys()):
            decay = float(self.DELTA_ACTIVITY_DECAY.get(product, 0.82))
            activity_signals[product] = float(activity_signals.get(product, 0.0)) * decay
            if abs(float(activity_signals[product])) < 0.03:
                activity_signals[product] = 0.0

        market_trades = getattr(state, "market_trades", {}) or {}
        for product, trades in market_trades.items():
            if not trades:
                continue
            for trade in trades:
                buyer = getattr(trade, "buyer", "") or ""
                seller = getattr(trade, "seller", "") or ""
                if buyer == "SUBMISSION" or seller == "SUBMISSION":
                    continue
                qty = max(1, int(getattr(trade, "quantity", 1)))
                alpha = self._trade_alpha(product, buyer, seller)
                if alpha == 0.0:
                    continue

                qty_scale = min(1.8, max(0.65, math.sqrt(qty / 5.0)))
                add = alpha * qty_scale
                cap = self._signal_cap(product)
                signals[product] = self._clip(float(signals.get(product, 0.0)) + add, -cap, cap)

                if product in self.DELTA_PRODUCTS:
                    fcap = float(self.DELTA_FLOW_CAP.get(product, cap))
                    # Fast layer is slightly amplified because the most useful delta flow
                    # is short-lived; the cap prevents a single print from dominating.
                    fast_signals[product] = self._clip(
                        float(fast_signals.get(product, 0.0)) + 1.20 * add,
                        -fcap,
                        fcap,
                    )
                    # Activity layer is slower than fast flow and slightly smaller than
                    # the main signal. It helps when the same Mark-style behavior repeats.
                    activity_signals[product] = self._clip(
                        float(activity_signals.get(product, 0.0)) + 0.72 * add,
                        -fcap,
                        fcap,
                    )

    def _trade_alpha(self, product: str, buyer: str, seller: str) -> float:
        pair_map = self.PAIR_ALPHA.get(product, {})
        if (buyer, seller) in pair_map:
            return float(pair_map[(buyer, seller)])

        mark_map = self.MARK_ALPHA.get(product, {})
        if mark_map:
            # buyer is +1 side, seller is -1 side.
            return 0.45 * (float(mark_map.get(buyer, 0.0)) - float(mark_map.get(seller, 0.0)))
        return 0.0

    def _signal_cap(self, product: str) -> float:
        if product == "HYDROGEL_PACK":
            return 7.0
        if product == "VELVETFRUIT_EXTRACT":
            return 7.0
        if product.startswith("VEV_"):
            return 2.0
        return 3.0

    def _book_pressure_signal(self, product: str, depth: OrderDepth) -> float:
        if product not in self.DELTA_PRODUCTS:
            return 0.0

        bid_qty = 0
        ask_qty = 0
        for _, volume in sorted(depth.buy_orders.items(), reverse=True)[:3]:
            bid_qty += max(0, int(volume))
        for _, volume in sorted(depth.sell_orders.items())[:3]:
            ask_qty += max(0, -int(volume))

        total = bid_qty + ask_qty
        if total <= 0:
            return 0.0

        imbalance = (bid_qty - ask_qty) / total
        if product == "HYDROGEL_PACK":
            return self._clip(1.65 * imbalance, -1.65, 1.65)
        if product == "VELVETFRUIT_EXTRACT":
            return self._clip(1.25 * imbalance, -1.25, 1.25)
        return 0.0

    def _update_mid_state(self, memory: Dict, mids: Dict[str, Optional[float]]) -> None:
        fast = memory.setdefault("mid_fast", {})
        slow = memory.setdefault("mid_slow", {})
        trend = memory.setdefault("mid_trend", {})
        prev_trend = memory.setdefault("prev_trend", {})
        if not isinstance(fast, dict):
            fast = {}; memory["mid_fast"] = fast
        if not isinstance(slow, dict):
            slow = {}; memory["mid_slow"] = slow
        if not isinstance(trend, dict):
            trend = {}; memory["mid_trend"] = trend
        if not isinstance(prev_trend, dict):
            prev_trend = {}; memory["prev_trend"] = prev_trend

        for product in self.DELTA_PRODUCTS:
            mid = mids.get(product)
            if mid is None:
                continue
            old_fast = float(fast.get(product, mid))
            old_slow = float(slow.get(product, mid))
            old_trend = float(trend.get(product, 0.0))
            new_fast = 0.36 * float(mid) + 0.64 * old_fast
            new_slow = 0.08 * float(mid) + 0.92 * old_slow
            fast[product] = new_fast
            slow[product] = new_slow
            prev_trend[product] = old_trend
            trend[product] = new_fast - new_slow

    def _agreement_adjusted_flow(
        self,
        product: str,
        flow_shift: float,
        raw_signal: float,
        fast_signal: float,
        book_signal: float,
        activity_signal: float,
    ) -> float:
        pieces = [raw_signal, fast_signal, book_signal, activity_signal]
        signs = [1 if x > 0.15 else -1 if x < -0.15 else 0 for x in pieces]
        non_zero = [s for s in signs if s != 0]
        if len(non_zero) < 2:
            return flow_shift

        same_direction = max(non_zero.count(1), non_zero.count(-1))
        if same_direction >= 3:
            cap = 9.25 if product == "HYDROGEL_PACK" else 8.25
            return self._clip(1.04 * flow_shift, -cap, cap)

        if 1 in non_zero and -1 in non_zero:
            return 0.82 * flow_shift
        return flow_shift

    def _reversal_adjustment(
        self,
        product: str,
        mid: Optional[float],
        anchor: float,
        ema_fair: float,
        memory: Dict,
        flow_shift: float,
    ) -> float:
        if mid is None:
            return 0.0
        trend = memory.get("mid_trend", {}) if isinstance(memory.get("mid_trend", {}), dict) else {}
        prev = memory.get("prev_trend", {}) if isinstance(memory.get("prev_trend", {}), dict) else {}
        current_trend = float(trend.get(product, 0.0))
        previous_trend = float(prev.get(product, current_trend))

        fair_ref = 0.68 * float(anchor) + 0.32 * float(ema_fair)
        stretch = float(mid) - fair_ref
        threshold = float(self.REVERSAL_THRESHOLD.get(product, 12.0))
        if abs(stretch) <= threshold:
            return 0.0

        turning_down = current_trend < previous_trend and current_trend < 0.05
        turning_up = current_trend > previous_trend and current_trend > -0.05
        weight = float(self.REVERSAL_WEIGHT.get(product, 0.0))
        cap = float(self.REVERSAL_CAP.get(product, 0.75))
        excess = abs(stretch) - threshold

        adjustment = 0.0
        if stretch > 0 and turning_down:
            adjustment = -weight * min(cap, 0.12 * excess)
        elif stretch < 0 and turning_up:
            adjustment = weight * min(cap, 0.12 * excess)

        if adjustment != 0.0 and flow_shift * adjustment < 0 and abs(flow_shift) > 5.0:
            adjustment *= 0.45
        return self._clip(adjustment, -cap, cap)

    def _option_delta_hedge_shift(
        self,
        positions: Dict[str, int],
        mids: Dict[str, Optional[float]],
        timestamp: int,
    ) -> float:
        spot = mids.get("VELVETFRUIT_EXTRACT")
        if spot is None or spot <= 0:
            return 0.0
        tte = self._time_to_expiry_years(timestamp)
        net_delta = 0.0
        for product, strike in self.STRIKES.items():
            if strike in self.DISABLED_OPTION_STRIKES:
                continue
            pos = int(positions.get(product, 0))
            if pos == 0:
                continue
            delta = self._voucher_delta(float(spot), strike, tte)
            net_delta += pos * delta

        if abs(net_delta) < 60.0:
            return 0.0
        raw = -float(self.OPTION_DELTA_HEDGE_WEIGHT) * net_delta
        return self._clip(raw, -float(self.OPTION_DELTA_HEDGE_CAP), float(self.OPTION_DELTA_HEDGE_CAP))

    def _voucher_delta(self, spot: float, strike: int, tte: float) -> float:
        if strike in (4000, 4500):
            return 1.0 if spot > strike else 0.0
        moneyness = math.log(strike / spot) / math.sqrt(max(tte, 1e-9))
        vol = (
            self.SMILE_A * moneyness * moneyness
            + self.SMILE_B * moneyness
            + self.SMILE_C
            + self.STRIKE_VOL_BIAS.get(strike, 0.0)
        )
        vol = self._clip(vol, 0.08, 0.45)
        sqrt_t = math.sqrt(max(tte, 1e-9))
        d1 = (math.log(spot / strike) + 0.5 * vol * vol * tte) / (vol * sqrt_t)
        return self._norm_cdf(d1)


    # -------------------------- order logic --------------------------

    def _take_anchor_edges(
        self,
        product: str,
        depth: OrderDepth,
        orders: List[Order],
        position: int,
        fair: float,
        edge: float,
        used_buy: int,
        used_sell: int,
        scale: float = 1.0,
        reduce_only: bool = False,
    ) -> Tuple[int, int]:
        limit = self.LIMITS[product]
        scale = self._clip(scale, 0.05, 1.0)

        for price, volume in sorted(depth.sell_orders.items()):
            if price > fair - edge:
                break
            if reduce_only and position >= 0:
                break
            room = limit - position - used_buy
            if reduce_only:
                room = min(room, max(0, -position - used_buy))
            else:
                room = int(room * scale)
            if room <= 0:
                break
            quantity = min(-int(volume), int(room))
            if quantity > 0:
                orders.append(Order(product, int(price), int(quantity)))
                used_buy += quantity

        for price, volume in sorted(depth.buy_orders.items(), reverse=True):
            if price < fair + edge:
                break
            if reduce_only and position <= 0:
                break
            room = limit + position - used_sell
            if reduce_only:
                room = min(room, max(0, position - used_sell))
            else:
                room = int(room * scale)
            if room <= 0:
                break
            quantity = min(int(volume), int(room))
            if quantity > 0:
                orders.append(Order(product, int(price), -int(quantity)))
                used_sell += quantity

        return used_buy, used_sell

    def _make_market(
        self,
        product: str,
        depth: OrderDepth,
        orders: List[Order],
        position: int,
        fair: float,
        edge: float,
        skew: float,
        lot: int,
        used_buy: int,
        used_sell: int,
        scale: float = 1.0,
        reduce_only: bool = False,
    ) -> None:
        best_bid = self._best_bid(depth)
        best_ask = self._best_ask(depth)
        if best_bid is None or best_ask is None:
            return
        if best_ask - best_bid < 2:
            return

        limit = self.LIMITS[product]
        scale = self._clip(scale, 0.05, 1.0)
        lot = max(1, int(lot * scale))
        reservation = fair - skew * position
        if reduce_only:
            reservation = fair - 0.5 * skew * position

        bid_price = min(best_bid + 1, math.floor(reservation - edge))
        ask_price = max(best_ask - 1, math.ceil(reservation + edge))

        buy_room = limit - position - used_buy
        sell_room = limit + position - used_sell
        if reduce_only:
            buy_room = min(buy_room, max(0, -position - used_buy))
            sell_room = min(sell_room, max(0, position - used_sell))

        if buy_room > 0 and bid_price < best_ask and bid_price < fair:
            quantity = min(lot, buy_room)
            orders.append(Order(product, int(bid_price), int(quantity)))

        if sell_room > 0 and ask_price > best_bid and ask_price > fair:
            quantity = min(lot, sell_room)
            orders.append(Order(product, int(ask_price), -int(quantity)))

    def _take_option_edges(
        self,
        product: str,
        strike: int,
        depth: OrderDepth,
        orders: List[Order],
        position: int,
        fair: float,
        used_buy: int,
        used_sell: int,
        scale: float = 1.0,
        reduce_only: bool = False,
    ) -> Tuple[int, int]:
        if strike in self.DISABLED_OPTION_STRIKES:
            return used_buy, used_sell

        hard_limit = self.LIMITS[product]
        long_limit = min(hard_limit, int(self.OPTION_LONG_LIMIT.get(strike, 0)))
        short_limit = min(hard_limit, int(self.OPTION_SHORT_LIMIT.get(strike, 0)))
        if long_limit <= 0 and short_limit <= 0:
            return used_buy, used_sell

        edge = float(self.OPTION_TAKE_EDGE.get(strike, 5.0))
        max_lot = max(1, int(self.OPTION_LOT.get(strike, 6) * self._clip(scale, 0.05, 1.0)))

        # Buy underpriced asks, but only inside the smaller soft inventory limit.
        for price, volume in sorted(depth.sell_orders.items()):
            if price > fair - edge:
                break
            if reduce_only and position >= 0:
                break
            room = min(hard_limit - position - used_buy, long_limit - position - used_buy)
            if reduce_only:
                room = min(room, max(0, -position - used_buy))
            if room <= 0:
                break
            quantity = min(-int(volume), int(room), max_lot)
            if quantity > 0:
                orders.append(Order(product, int(price), int(quantity)))
                used_buy += quantity

        # Sell overpriced bids, with symmetric soft limit.
        for price, volume in sorted(depth.buy_orders.items(), reverse=True):
            if price < fair + edge:
                break
            if reduce_only and position <= 0:
                break
            room = min(hard_limit + position - used_sell, short_limit + position - used_sell)
            if reduce_only:
                room = min(room, max(0, position - used_sell))
            if room <= 0:
                break
            quantity = min(int(volume), int(room), max_lot)
            if quantity > 0:
                orders.append(Order(product, int(price), -int(quantity)))
                used_sell += quantity

        return used_buy, used_sell

    def _quote_option(
        self,
        product: str,
        strike: int,
        depth: OrderDepth,
        orders: List[Order],
        position: int,
        fair: float,
        used_buy: int,
        used_sell: int,
        scale: float = 1.0,
        reduce_only: bool = False,
    ) -> None:
        if strike in self.DISABLED_OPTION_STRIKES:
            return
        if strike not in self.OPTION_PASSIVE_EDGE:
            return

        best_bid = self._best_bid(depth)
        best_ask = self._best_ask(depth)
        if best_bid is None or best_ask is None:
            return
        if best_ask <= best_bid:
            return

        hard_limit = self.LIMITS[product]
        long_limit = min(hard_limit, int(self.OPTION_LONG_LIMIT.get(strike, 0)))
        short_limit = min(hard_limit, int(self.OPTION_SHORT_LIMIT.get(strike, 0)))
        if long_limit <= 0 and short_limit <= 0:
            return

        edge = float(self.OPTION_PASSIVE_EDGE[strike])
        scale = self._clip(scale, 0.05, 1.0)
        lot = max(1, int(self.OPTION_LOT.get(strike, 20) * scale))

        # Inventory skew is the main smoother: high enough to pull inventory
        # back toward zero, but not so high that we stop quoting both sides.
        skew = max(0.04, min(0.55, fair * 0.00105))
        if strike <= 4500:
            skew = max(skew, 0.10)
        elif strike in (5000, 5100, 5200):
            skew = max(skew, 0.18)
        reservation = fair - skew * position
        if reduce_only:
            reservation = fair - 0.65 * skew * position

        bid_price = min(best_bid + 1, math.floor(reservation - edge))
        ask_price = max(best_ask - 1, math.ceil(reservation + edge))
        bid_price = max(1, int(bid_price))
        ask_price = max(1, int(ask_price))

        buy_room = min(hard_limit - position - used_buy, long_limit - position - used_buy)
        sell_room = min(hard_limit + position - used_sell, short_limit + position - used_sell)
        if reduce_only:
            buy_room = min(buy_room, max(0, -position - used_buy))
            sell_room = min(sell_room, max(0, position - used_sell))

        # Keep quotes just inside the visible spread when they still respect the
        # quote fair. With large visible spreads, quoting one tick inside the book
        # is the main way to earn spread consistently. The ±0.10 guard prevents
        # crossing our own quote_fair.
        if buy_room > 0 and bid_price < best_ask and bid_price <= fair - 0.10:
            quantity = min(lot, int(buy_room))
            if quantity > 0:
                orders.append(Order(product, bid_price, quantity))

        if sell_room > 0 and ask_price > best_bid and ask_price >= fair + 0.10:
            quantity = min(lot, int(sell_room))
            if quantity > 0:
                orders.append(Order(product, ask_price, -quantity))


    def _flatten_all(self, state: TradingState) -> Dict[str, List[Order]]:
        result: Dict[str, List[Order]] = {}
        for product, depth in state.order_depths.items():
            pos = int(state.position.get(product, 0))
            if pos == 0:
                continue
            orders: List[Order] = []
            if pos > 0:
                best_bid = self._best_bid(depth)
                if best_bid is not None:
                    qty = min(pos, max(0, int(depth.buy_orders.get(best_bid, 0))))
                    if qty > 0:
                        orders.append(Order(product, int(best_bid), -int(qty)))
            else:
                best_ask = self._best_ask(depth)
                if best_ask is not None:
                    qty = min(-pos, max(0, -int(depth.sell_orders.get(best_ask, 0))))
                    if qty > 0:
                        orders.append(Order(product, int(best_ask), int(qty)))
            if orders:
                result[product] = orders
        return result

    # -------------------------- option model --------------------------

    def _voucher_fair_value(
        self,
        underlying: float,
        strike: int,
        tte_years: float,
        vol_shift: float,
    ) -> Optional[float]:
        if strike in self.DISABLED_OPTION_STRIKES:
            return None
        if strike in (4000, 4500):
            return max(underlying - strike, 0.0)

        moneyness = math.log(strike / underlying) / math.sqrt(tte_years)
        vol = (
            self.SMILE_A * moneyness * moneyness
            + self.SMILE_B * moneyness
            + self.SMILE_C
            + self.STRIKE_VOL_BIAS.get(strike, 0.0)
            + 0.18 * vol_shift
        )
        vol = self._clip(vol, 0.08, 0.45)
        return max(0.0, self._call_price(underlying, strike, tte_years, vol))

    def _surface_shift(
        self,
        depths: Dict[str, OrderDepth],
        underlying: float,
        tte_years: float,
    ) -> float:
        shifts: List[float] = []
        for strike in (5000, 5100, 5200, 5300, 5400, 5500):
            product = "VEV_" + str(strike)
            depth = depths.get(product)
            if depth is None:
                continue
            mid = self._mid_price(depth)
            if mid is None or mid <= 0.5:
                continue
            intrinsic = max(underlying - strike, 0.0)
            if mid <= intrinsic + 0.25:
                continue

            observed = self._implied_vol(underlying, strike, tte_years, mid)
            moneyness = math.log(strike / underlying) / math.sqrt(tte_years)
            base = (
                self.SMILE_A * moneyness * moneyness
                + self.SMILE_B * moneyness
                + self.SMILE_C
                + self.STRIKE_VOL_BIAS.get(strike, 0.0)
            )
            shifts.append(observed - base)

        if not shifts:
            return 0.0
        shifts.sort()
        median = shifts[len(shifts) // 2]
        return self._clip(median, -0.025, 0.025)

    def _time_to_expiry_years(self, timestamp: int) -> float:
        # Round 4 live starts with TTE = 4 Solvenarian days.
        tte_days = 4.0 - timestamp / 1_000_000.0
        return max(0.01, tte_days / 365.0)

    def _call_price(self, spot: float, strike: int, tte: float, vol: float) -> float:
        if tte <= 0 or vol <= 0:
            return max(spot - strike, 0.0)
        sqrt_t = math.sqrt(tte)
        d1 = (math.log(spot / strike) + 0.5 * vol * vol * tte) / (vol * sqrt_t)
        d2 = d1 - vol * sqrt_t
        return spot * self._norm_cdf(d1) - strike * self._norm_cdf(d2)

    def _implied_vol(self, spot: float, strike: int, tte: float, price: float) -> float:
        intrinsic = max(spot - strike, 0.0)
        if price <= intrinsic + 1e-9:
            return 0.000001
        lo = 0.000001
        hi = 2.0
        for _ in range(28):
            mid = (lo + hi) * 0.5
            if self._call_price(spot, strike, tte, mid) > price:
                hi = mid
            else:
                lo = mid
        return (lo + hi) * 0.5

    def _norm_cdf(self, value: float) -> float:
        return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))

    # -------------------------- utilities --------------------------

    def _mid_price(self, depth: OrderDepth) -> Optional[float]:
        best_bid = self._best_bid(depth)
        best_ask = self._best_ask(depth)
        if best_bid is None and best_ask is None:
            return None
        if best_bid is None:
            return float(best_ask)
        if best_ask is None:
            return float(best_bid)
        return (best_bid + best_ask) * 0.5

    def _best_bid(self, depth: OrderDepth) -> Optional[int]:
        if not depth.buy_orders:
            return None
        return max(depth.buy_orders)

    def _best_ask(self, depth: OrderDepth) -> Optional[int]:
        if not depth.sell_orders:
            return None
        return min(depth.sell_orders)

    def _update_cash_from_own_trades(self, memory: Dict, state: TradingState) -> None:
        cash = memory.setdefault("cash", {})
        last_ts = int(memory.get("last_trade_ts", -1))
        max_seen_ts = last_ts
        own_trades = getattr(state, "own_trades", {}) or {}

        for product, trades in own_trades.items():
            for trade in trades:
                trade_ts = int(getattr(trade, "timestamp", -1))
                if trade_ts <= last_ts:
                    continue
                price = float(getattr(trade, "price", 0.0))
                quantity = int(getattr(trade, "quantity", 0))
                buyer = getattr(trade, "buyer", "")
                seller = getattr(trade, "seller", "")

                if buyer == "SUBMISSION":
                    cash[product] = float(cash.get(product, 0.0)) - price * quantity
                elif seller == "SUBMISSION":
                    cash[product] = float(cash.get(product, 0.0)) + price * quantity

                if trade_ts > max_seen_ts:
                    max_seen_ts = trade_ts

        memory["last_trade_ts"] = max_seen_ts

    def _estimate_mtm_pnl(
        self,
        memory: Dict,
        positions: Dict[str, int],
        mids: Dict[str, Optional[float]],
    ) -> float:
        cash = memory.get("cash", {})
        pnl = 0.0
        if isinstance(cash, dict):
            for value in cash.values():
                try:
                    pnl += float(value)
                except Exception:
                    pass
        for product, position in positions.items():
            mid = mids.get(product)
            if mid is not None:
                pnl += int(position) * float(mid)
        return pnl

    def _product_mtm_pnl(self, memory: Dict, product: str, position: int, mid: Optional[float]) -> float:
        cash = memory.get("cash", {})
        product_cash = 0.0
        if isinstance(cash, dict):
            try:
                product_cash = float(cash.get(product, 0.0))
            except Exception:
                product_cash = 0.0
        mark = 0.0 if mid is None else float(position) * float(mid)
        return product_cash + mark

    def _risk_mode(self, memory: Dict, timestamp: int, peak_pnl: float, drawdown: float) -> str:
        current_until = int(memory.get("risk_until", -1))
        current_mode = str(memory.get("risk_mode", "NORMAL"))
        mode = current_mode if timestamp < current_until else "NORMAL"

        if peak_pnl > self.PROFIT_LOCK_MIN_PEAK:
            defensive_trigger = max(self.DEFENSIVE_DRAWDOWN_ABS, self.DEFENSIVE_DRAWDOWN_FRAC * peak_pnl)
            hard_trigger = max(self.HARD_LOCK_DRAWDOWN_ABS, self.HARD_LOCK_DRAWDOWN_FRAC * peak_pnl)

            if drawdown > hard_trigger:
                mode = "LOCK"
                memory["risk_until"] = int(timestamp + self.HARD_LOCK_COOLDOWN)
            elif drawdown > defensive_trigger and mode != "LOCK":
                mode = "DEFENSIVE"
                memory["risk_until"] = int(timestamp + self.DEFENSIVE_COOLDOWN)

        memory["risk_mode"] = mode
        return mode

    def _load_memory(self, trader_data: str) -> Dict:
        if not trader_data:
            return {}
        try:
            value = json.loads(trader_data)
            if isinstance(value, dict):
                return value
        except Exception:
            pass
        return {}

    def _dump_memory(self, memory: Dict) -> str:
        try:
            return json.dumps(memory, separators=(",", ":"))
        except Exception:
            return ""

    def _clip(self, value: float, low: float, high: float) -> float:
        return min(high, max(low, value))
