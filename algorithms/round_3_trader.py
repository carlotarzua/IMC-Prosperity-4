from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Optional, Tuple
import json
import math


class Trader:
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

    SMILE_A = 0.028259203050341634
    SMILE_B = 0.0024601685462392114
    SMILE_C = 0.23953346206705442
    STRIKE_VOL_BIAS = {
        5000: -0.0007115205147279486,
        5100: -0.0007218007937266071,
        5200: 0.0028175170224307403,
        5300: 0.005119367939774469,
        5400: -0.011719306076002524,
        5500: 0.005215742422253735,
    }

    DELTA_PRODUCTS = {
        "HYDROGEL_PACK": {
            "fair": 10000.0,
            "take_edge": 18.0,
            "passive_edge": 4.0,
            "skew": 0.075,
            "lot": 24,
            "taker_blend": 0.0,
        },
        "VELVETFRUIT_EXTRACT": {
            "fair": 5251.0,
            "take_edge": 15.0,
            "passive_edge": 1.8,
            "skew": 0.050,
            "lot": 42,
            "taker_blend": 0.15,
        },
    }

    OPTION_TAKE_EDGE = {
        4000: 1.75,
        4500: 1.75,
        5000: 0.60,
        5100: 0.65,
        5200: 1.50,
        5300: 2.50,
        5400: 0.75,
        5500: 0.50,
    }
    OPTION_PASSIVE_EDGE = {
        5000: 3.0,
        5100: 2.4,
        5200: 2.0,
        5300: 1.5,
        5400: 1.0,
        5500: 1.0,
    }
    OPTION_LOT = {
        4000: 12,
        4500: 12,
        5000: 24,
        5100: 26,
        5200: 26,
        5300: 26,
        5400: 24,
        5500: 18,
    }

    DISABLED_OPTION_STRIKES = {5500}
    PROFIT_LOCK_MIN_PEAK = 2500.0
    DEFENSIVE_DRAWDOWN_ABS = 2500.0
    DEFENSIVE_DRAWDOWN_FRAC = 0.48
    HARD_LOCK_DRAWDOWN_ABS = 6000.0
    HARD_LOCK_DRAWDOWN_FRAC = 0.70
    DEFENSIVE_COOLDOWN = 6000
    HARD_LOCK_COOLDOWN = 12000

    def bid(self):
        return 0

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        memory = self._load_memory(state.traderData)

        mids = {
            product: self._mid_price(depth)
            for product, depth in state.order_depths.items()
        }

        ema = memory.setdefault("ema", {})
        for product, mid in mids.items():
            if mid is None:
                continue
            previous = float(ema.get(product, mid))
            ema[product] = 0.03 * mid + 0.97 * previous

        self._update_cash_from_own_trades(memory, state)
        current_pnl = self._estimate_mtm_pnl(memory, state.position, mids)
        peak_pnl = max(float(memory.get("peak_pnl", current_pnl)), current_pnl)
        memory["peak_pnl"] = peak_pnl
        drawdown = peak_pnl - current_pnl
        risk_mode = self._risk_mode(memory, state.timestamp, peak_pnl, drawdown)

        if risk_mode == "LOCK":
            delta_scale = 0.45
            option_scale = 0.20
            delta_reduce_only = True
            option_reduce_only = True
        elif risk_mode == "DEFENSIVE":
            delta_scale = 0.80
            option_scale = 0.45
            delta_reduce_only = False
            option_reduce_only = False
        else:
            delta_scale = 1.00
            option_scale = 1.00
            delta_reduce_only = False
            option_reduce_only = False

        for product, config in self.DELTA_PRODUCTS.items():
            depth = state.order_depths.get(product)
            if depth is None:
                continue
            orders: List[Order] = []
            position = state.position.get(product, 0)
            used_buy = 0
            used_sell = 0

            anchor = config["fair"]
            ema_fair = float(ema.get(product, anchor))
            taker_blend = config["taker_blend"]
            taker_fair = (1.0 - taker_blend) * anchor + taker_blend * ema_fair
            passive_fair = 0.85 * anchor + 0.15 * ema_fair
            used_buy, used_sell = self._take_anchor_edges(
                product,
                depth,
                orders,
                position,
                taker_fair,
                config["take_edge"],
                used_buy,
                used_sell,
                delta_scale,
                delta_reduce_only,
            )
            self._make_market(
                product,
                depth,
                orders,
                position,
                passive_fair,
                config["passive_edge"],
                config["skew"],
                config["lot"],
                used_buy,
                used_sell,
                delta_scale,
                delta_reduce_only,
            )
            if orders:
                result[product] = orders

        velvet_mid = mids.get("VELVETFRUIT_EXTRACT")
        if velvet_mid is not None:
            tte_years = self._time_to_expiry_years(state.timestamp)
            vol_shift = self._surface_shift(state.order_depths, velvet_mid, tte_years)
            for product, strike in self.STRIKES.items():
                depth = state.order_depths.get(product)
                if depth is None:
                    continue

                fair = self._voucher_fair_value(velvet_mid, strike, tte_years, vol_shift)
                if fair is None:
                    continue

                orders: List[Order] = []
                position = state.position.get(product, 0)
                used_buy = 0
                used_sell = 0
                used_buy, used_sell = self._take_option_edges(
                    product,
                    strike,
                    depth,
                    orders,
                    position,
                    fair,
                    used_buy,
                    used_sell,
                    option_scale,
                    option_reduce_only,
                )
                self._quote_option(
                    product,
                    strike,
                    depth,
                    orders,
                    position,
                    fair,
                    used_buy,
                    used_sell,
                    option_scale,
                    option_reduce_only,
                )
                if orders:
                    result[product] = orders

        trader_data = self._dump_memory(memory)
        return result, 0, trader_data

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
        scale = min(1.0, max(0.05, scale))

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
            quantity = min(-volume, room)
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
            quantity = min(volume, room)
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
        scale = min(1.0, max(0.05, scale))
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
        if strike in (6000, 6500) or strike in self.DISABLED_OPTION_STRIKES:
            return used_buy, used_sell

        limit = self.LIMITS[product]
        edge = self.OPTION_TAKE_EDGE.get(strike, 1.5)
        max_lot = max(1, int(self.OPTION_LOT.get(strike, 20) * min(1.0, max(0.05, scale))))

        for price, volume in sorted(depth.sell_orders.items()):
            if price > fair - edge:
                break
            if reduce_only and position >= 0:
                break
            room = limit - position - used_buy
            if reduce_only:
                room = min(room, max(0, -position - used_buy))
            if room <= 0:
                break
            quantity = min(-volume, room, max_lot)
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
            if room <= 0:
                break
            quantity = min(volume, room, max_lot)
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

        limit = self.LIMITS[product]
        edge = self.OPTION_PASSIVE_EDGE[strike]
        lot = max(1, int(self.OPTION_LOT.get(strike, 20) * min(1.0, max(0.05, scale))))
        skew = max(0.01, fair * 0.0009)
        reservation = fair - skew * position
        if reduce_only:
            reservation = fair - 0.5 * skew * position

        bid_price = min(best_bid + 1, math.floor(reservation - edge))
        ask_price = max(best_ask - 1, math.ceil(reservation + edge))
        bid_price = max(1, bid_price)
        ask_price = max(1, ask_price)

        buy_room = limit - position - used_buy
        sell_room = limit + position - used_sell
        if reduce_only:
            buy_room = min(buy_room, max(0, -position - used_buy))
            sell_room = min(sell_room, max(0, position - used_sell))

        if buy_room > 0 and bid_price < best_ask and bid_price <= fair - 0.25:
            quantity = min(lot, buy_room)
            orders.append(Order(product, int(bid_price), int(quantity)))

        if sell_room > 0 and ask_price > best_bid and ask_price >= fair + 0.25:
            quantity = min(lot, sell_room)
            orders.append(Order(product, int(ask_price), -int(quantity)))

    def _voucher_fair_value(
        self,
        underlying: float,
        strike: int,
        tte_years: float,
        vol_shift: float,
    ) -> Optional[float]:
        if strike in (6000, 6500):
            return None
        if strike in (4000, 4500):
            return max(underlying - strike, 0.0)

        moneyness = math.log(strike / underlying) / math.sqrt(tte_years)
        vol = (
            self.SMILE_A * moneyness * moneyness
            + self.SMILE_B * moneyness
            + self.SMILE_C
            + self.STRIKE_VOL_BIAS.get(strike, 0.0)
            + 0.35 * vol_shift
        )
        vol = min(0.45, max(0.08, vol))
        return self._call_price(underlying, strike, tte_years, vol)

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
            if mid is None or mid <= 1:
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
        return min(0.03, max(-0.03, median))

    def _time_to_expiry_years(self, timestamp: int) -> float:
        # Live Round 3 starts with 5 Solvenarian days to expiry. This is a
        # model parameter, not a path schedule; it does not depend on product
        # prices or exact timestamps beyond normal expiry decay.
        tte_days = 5.0 - timestamp / 1_000_000.0
        return max(0.02, tte_days / 365.0)

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
        """Update cash from own fills once, using trade timestamps to avoid repeats."""
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

    def _risk_mode(self, memory: Dict, timestamp: int, peak_pnl: float, drawdown: float) -> str:
        current_until = int(memory.get("risk_until", -1))
        current_mode = str(memory.get("risk_mode", "NORMAL"))
        mode = current_mode if timestamp < current_until else "NORMAL"

        if peak_pnl > self.PROFIT_LOCK_MIN_PEAK:
            defensive_trigger = max(
                self.DEFENSIVE_DRAWDOWN_ABS,
                self.DEFENSIVE_DRAWDOWN_FRAC * peak_pnl,
            )
            hard_trigger = max(
                self.HARD_LOCK_DRAWDOWN_ABS,
                self.HARD_LOCK_DRAWDOWN_FRAC * peak_pnl,
            )

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
