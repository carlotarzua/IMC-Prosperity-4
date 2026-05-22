from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List, Optional, Tuple
import json


class Trader:

    LIMIT = {
        "ASH_COATED_OSMIUM": 80,
        "INTARIAN_PEPPER_ROOT": 80,
    }

    # Blind-auction bid for extra 25% flow.
    # Without knowing the field's median bid, this is a compromise:
    # high enough to have a decent chance of clearing, low enough to avoid
    # burning too much one-time PnL.
    def bid(self):
        return 12000

    # ------------------------- state helpers -------------------------

    def _load_data(self, trader_data: str) -> Dict:
        if not trader_data:
            return {}
        try:
            return json.loads(trader_data)
        except Exception:
            return {}

    def _dump_data(self, data: Dict) -> str:
        try:
            encoded = json.dumps(data, separators=(",", ":"))
        except Exception:
            return ""
        return encoded[:49000]

    def _best_bid(self, od: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
        if od.buy_orders:
            p = max(od.buy_orders.keys())
            return p, od.buy_orders[p]
        return None, None

    def _best_ask(self, od: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
        if od.sell_orders:
            p = min(od.sell_orders.keys())
            return p, od.sell_orders[p]
        return None, None

    def _mid_price(self, od: OrderDepth, fallback: Optional[float] = None) -> Optional[float]:
        bb, _ = self._best_bid(od)
        ba, _ = self._best_ask(od)
        if bb is not None and ba is not None:
            return (bb + ba) / 2.0
        if fallback is not None:
            return fallback
        if bb is not None:
            return bb + 8.0
        if ba is not None:
            return ba - 8.0
        return None

    def _microprice(self, od: OrderDepth, fallback: Optional[float]) -> Optional[float]:
        bb, bbv = self._best_bid(od)
        ba, bav = self._best_ask(od)
        if bb is None or ba is None or bbv is None or bav is None:
            return fallback
        buy_v = max(0, bbv)
        sell_v = abs(min(0, bav))
        total = buy_v + sell_v
        if total == 0:
            return fallback
        # Standard top-of-book microprice weighting.
        return (ba * buy_v + bb * sell_v) / total

    def _update_history(self, data: Dict, product: str, price: Optional[float], max_len: int = 200) -> None:
        if product not in data:
            data[product] = {"mid_history": []}
        hist = data[product].setdefault("mid_history", [])
        if price is not None:
            hist.append(price)
        if len(hist) > max_len:
            data[product]["mid_history"] = hist[-max_len:]

    def _linreg_forecast(self, values: List[float], lookback: int, horizon_steps: int = 1) -> Optional[float]:
        vals = [v for v in values if v is not None]
        if len(vals) < max(8, lookback // 3):
            return None
        y = vals[-lookback:]
        n = len(y)
        if n < 2:
            return None
        mean_x = (n - 1) / 2.0
        mean_y = sum(y) / n
        cov = 0.0
        var = 0.0
        for i, yi in enumerate(y):
            dx = i - mean_x
            cov += dx * (yi - mean_y)
            var += dx * dx
        if var == 0:
            return y[-1]
        slope = cov / var
        intercept = mean_y - slope * mean_x
        x_pred = n - 1 + horizon_steps
        return intercept + slope * x_pred

    def _ema(self, values: List[float], alpha: float) -> Optional[float]:
        vals = [v for v in values if v is not None]
        if not vals:
            return None
        out = vals[0]
        for v in vals[1:]:
            out = alpha * v + (1 - alpha) * out
        return out

    def _clamp_buy(self, product: str, pos: int, pending_buy: int, qty: int) -> int:
        return max(0, min(qty, self.LIMIT[product] - pos - pending_buy))

    def _clamp_sell(self, product: str, pos: int, pending_sell: int, qty: int) -> int:
        return max(0, min(qty, self.LIMIT[product] + pos - pending_sell))

    # ------------------------- execution primitives -------------------------

    def _take_best(
        self,
        product: str,
        od: OrderDepth,
        fair: float,
        take_width: float,
        pos: int,
        pending_buy: int,
        pending_sell: int,
        orders: List[Order],
        max_take_per_side: int,
    ) -> Tuple[int, int]:
        # Buy cheap asks.
        bought = 0
        for ask in sorted(od.sell_orders.keys()):
            if ask > fair - take_width:
                break
            ask_qty = abs(od.sell_orders[ask])
            qty = min(ask_qty, max_take_per_side - bought)
            qty = self._clamp_buy(product, pos, pending_buy, qty)
            if qty <= 0:
                break
            orders.append(Order(product, int(ask), int(qty)))
            pending_buy += qty
            bought += qty
            if bought >= max_take_per_side:
                break

        # Sell rich bids.
        sold = 0
        for bid in sorted(od.buy_orders.keys(), reverse=True):
            if bid < fair + take_width:
                break
            bid_qty = od.buy_orders[bid]
            qty = min(bid_qty, max_take_per_side - sold)
            qty = self._clamp_sell(product, pos, pending_sell, qty)
            if qty <= 0:
                break
            orders.append(Order(product, int(bid), int(-qty)))
            pending_sell += qty
            sold += qty
            if sold >= max_take_per_side:
                break

        return pending_buy, pending_sell

    def _clear_near_fair(
        self,
        product: str,
        od: OrderDepth,
        fair: float,
        clear_width: float,
        pos: int,
        pending_buy: int,
        pending_sell: int,
        orders: List[Order],
    ) -> Tuple[int, int]:
        net_after_take = pos + pending_buy - pending_sell
        if net_after_take > 0:
            # Long -> clear into reasonably good bids.
            clearable = 0
            for bid, bid_qty in od.buy_orders.items():
                if bid >= fair + clear_width:
                    clearable += bid_qty
            qty = min(net_after_take, clearable)
            qty = self._clamp_sell(product, pos, pending_sell, qty)
            if qty > 0:
                orders.append(Order(product, int(round(fair + clear_width)), int(-qty)))
                pending_sell += qty
        elif net_after_take < 0:
            # Short -> clear into reasonably good asks.
            clearable = 0
            for ask, ask_qty in od.sell_orders.items():
                if ask <= fair - clear_width:
                    clearable += abs(ask_qty)
            qty = min(abs(net_after_take), clearable)
            qty = self._clamp_buy(product, pos, pending_buy, qty)
            if qty > 0:
                orders.append(Order(product, int(round(fair - clear_width)), int(qty)))
                pending_buy += qty
        return pending_buy, pending_sell

    def _passive_quotes(
        self,
        product: str,
        od: OrderDepth,
        fair: float,
        pos: int,
        pending_buy: int,
        pending_sell: int,
        base_edge: int,
        join_edge: int,
        soft_limit: int,
        base_size: int,
        min_cross_gap: int = 2,
    ) -> None:
        orders = []
        bb, _ = self._best_bid(od)
        ba, _ = self._best_ask(od)

    # ------------------------- product logic -------------------------

    def _trade_ipr(self, state: TradingState, data: Dict) -> List[Order]:
        product = "INTARIAN_PEPPER_ROOT"
        od = state.order_depths.get(product)
        if od is None:
            return []

        last_mid = None
        if product in data and data[product].get("mid_history"):
            last_mid = data[product]["mid_history"][-1]

        mid = self._mid_price(od, fallback=last_mid)
        self._update_history(data, product, mid, max_len=160)
        hist = data.get(product, {}).get("mid_history", [])

        # Main model: rolling linear-regression fair. If we do not have enough
        # history yet, fall back to a small positive-drift estimate.
        fair = self._linreg_forecast(hist, lookback=min(120, len(hist)), horizon_steps=3)
        if fair is None and mid is not None:
            fair = mid + 0.3
        if fair is None:
            return []

        pos = state.position.get(product, 0)
        orders: List[Order] = []
        bb, _ = self._best_bid(od)
        ba, _ = self._best_ask(od)

        # Target inventory: get long quickly because the product is strongly
        # upward trending in the round-1 data and the round notes say buy/hold
        # is close to ideal.
        # We still avoid obviously bad prices and we stop aggressively buying
        # once we are close to the limit.
        pending_buy = 0
        target = 80
        capacity = max(0, target - pos)

        if capacity > 0:
            for ask in sorted(od.sell_orders.keys()):
                if capacity <= 0:
                    break
                # Buy asks that are not too far above fair.
                if ask > fair + 8:
                    break
                ask_qty = abs(od.sell_orders[ask])
                qty = min(ask_qty, capacity)
                qty = self._clamp_buy(product, pos, pending_buy, qty)
                if qty <= 0:
                    continue
                orders.append(Order(product, int(ask), int(qty)))
                pending_buy += qty
                capacity -= qty

        # Once long, do not market-make on both sides. Only leave a passive ask
        # above fair so we do not accidentally bleed out inventory.
        if pos + pending_buy >= 65:
            offer_qty = min(8, pos + pending_buy)
            if offer_qty > 0:
                ask_px = int(round(fair + 10))
                if bb is not None:
                    ask_px = max(ask_px, bb + 2)
                orders.append(Order(product, ask_px, -offer_qty))

        return orders

    def _trade_ash(self, state: TradingState, data: Dict) -> List[Order]:
        product = "ASH_COATED_OSMIUM"
        od = state.order_depths.get(product)
        if od is None:
            return []

        last_mid = None
        if product in data and data[product].get("mid_history"):
            last_mid = data[product]["mid_history"][-1]

        raw_mid = self._mid_price(od, fallback=last_mid)
        micro = self._microprice(od, fallback=raw_mid)
        obs = micro if micro is not None else raw_mid
        self._update_history(data, product, obs, max_len=220)
        hist = data.get(product, {}).get("mid_history", [])

        # ASH behaved like a stable/mean-reverting asset around ~10000 in the
        # round-1 files, with a wide spread. Use a denoised fair and trade both
        # spread capture and deviations from fair.
        ema_fast = self._ema(hist[-30:], 0.25) if hist else None
        ema_slow = self._ema(hist[-120:], 0.08) if hist else None
        if ema_fast is None and ema_slow is None:
            fair = 10000.0
        elif ema_fast is None:
            fair = ema_slow
        elif ema_slow is None:
            fair = ema_fast
        else:
            fair = 0.6 * ema_fast + 0.4 * ema_slow

        # Gentle anchor toward the known central level from round-1 data.
        fair = 0.8 * fair + 0.2 * 10000.0

        pos = state.position.get(product, 0)
        orders: List[Order] = []
        pending_buy = 0
        pending_sell = 0

        bb, _ = self._best_bid(od)
        ba, _ = self._best_ask(od)
        spread = (ba - bb) if bb is not None and ba is not None else 16

        # 1) TAKE: exploit obvious mispricings.
        take_width = max(4.0, spread / 3.0)
        pending_buy, pending_sell = self._take_best(
            product,
            od,
            fair,
            take_width,
            pos,
            pending_buy,
            pending_sell,
            orders,
            max_take_per_side=24,
        )

        # 2) CLEAR: if we already carry inventory, flatten opportunistically near fair.
        pending_buy, pending_sell = self._clear_near_fair(
            product,
            od,
            fair,
            clear_width=1.0,
            pos=pos,
            pending_buy=pending_buy,
            pending_sell=pending_sell,
            orders=orders,
        )

        # 3) MAKE: quote inside the spread with inventory skew.
        net_pos = pos + pending_buy - pending_sell
        inv_ratio = net_pos / self.LIMIT[product]
        skew = int(round(inv_ratio * 4))  # up to ~4 ticks of skew.

        if bb is not None:
            bid_px = bb + 1
        else:
            bid_px = int(round(fair - 6))

        if ba is not None:
            ask_px = ba - 1
        else:
            ask_px = int(round(fair + 6))

        bid_px -= skew
        ask_px -= skew

        bid_px = min(bid_px, int(round(fair - 2)))
        ask_px = max(ask_px, int(round(fair + 2)))

        if bid_px >= ask_px:
            bid_px = int(round(fair - 3))
            ask_px = int(round(fair + 3))

        base_size = 16
        if net_pos > 0:
            buy_size = max(4, base_size - net_pos // 6)
            sell_size = min(28, base_size + net_pos // 6)
        elif net_pos < 0:
            buy_size = min(28, base_size + abs(net_pos) // 6)
            sell_size = max(4, base_size - abs(net_pos) // 6)
        else:
            buy_size = base_size
            sell_size = base_size

        buy_qty = self._clamp_buy(product, pos, pending_buy, buy_size)
        sell_qty = self._clamp_sell(product, pos, pending_sell, sell_size)

        if buy_qty > 0:
            orders.append(Order(product, int(bid_px), int(buy_qty)))
        if sell_qty > 0:
            orders.append(Order(product, int(ask_px), int(-sell_qty)))

        return orders

    # ------------------------- main -------------------------

    def run(self, state: TradingState):
        data = self._load_data(state.traderData)

        result: Dict[str, List[Order]] = {}

        ash_orders = self._trade_ash(state, data)
        if ash_orders:
            result["ASH_COATED_OSMIUM"] = ash_orders

        ipr_orders = self._trade_ipr(state, data)
        if ipr_orders:
            result["INTARIAN_PEPPER_ROOT"] = ipr_orders

        trader_data = self._dump_data(data)
        conversions = 0
        return result, conversions, trader_data