from datamodel import Order, OrderDepth, TradingState, Symbol
from typing import Dict, List
import json


class Trader:
    
    POSITION_LIMITS = {
        'ASH_COATED_OSMIUM': 80,
        'INTARIAN_PEPPER_ROOT': 80,
    }
    
   
    ASH_FAIR = 10000
    ASH_MM_EDGE = 3          
    ASH_TAKE_THRESH = 7      
    ASH_MM_QTY = 15          
    ASH_TAKE_QTY = 30        
    IPR_BASE = 9998.5
    IPR_DAY_STEP = 1000
    IPR_TICK_SLOPE = 0.001
    IPR_BID_EDGE = 4         
    IPR_ASK_EDGE = 6         
    IPR_TAKE_THRESH = 9      
    IPR_MM_QTY = 15
    IPR_TAKE_QTY = 30

    def _clamp(self, qty: int, pos: int, product: str) -> int:
        """Clamp quantity so position stays within limits."""
        limit = self.POSITION_LIMITS[product]
        if qty > 0:
            return min(qty, limit - pos)
        else:
            return max(qty, -limit - pos)

    def _best_bid(self, od: OrderDepth):
        if od.buy_orders:
            p = max(od.buy_orders)
            return p, od.buy_orders[p]
        return None, None

    def _best_ask(self, od: OrderDepth):
        if od.sell_orders:
            p = min(od.sell_orders)
            return p, od.sell_orders[p]
        return None, None

    def _ipr_fair(self, state: TradingState) -> float:
        od = state.order_depths.get('INTARIAN_PEPPER_ROOT')
        if od is None:
            return None
        
        bb, _ = self._best_bid(od)
        ba, _ = self._best_ask(od)
        
        if bb and ba:
            mid = (bb + ba) / 2
        elif bb:
            mid = bb + 8   
        elif ba:
            mid = ba - 8
        else:
            return None
        
        day_est = round((mid - self.IPR_BASE) / self.IPR_DAY_STEP) - 2
        day_est = max(-2, min(5, day_est))
        
        fair = self.IPR_BASE + self.IPR_DAY_STEP * (day_est + 2) + state.timestamp * self.IPR_TICK_SLOPE
        return round(fair, 1)

    def _trade_ash(self, state: TradingState) -> List[Order]:
        symbol = 'ASH_COATED_OSMIUM'
        if symbol not in state.order_depths:
            return []
        
        od = state.order_depths[symbol]
        pos = state.position.get(symbol, 0)
        orders = []
        
        fair = self.ASH_FAIR
        bb_price, _ = self._best_bid(od)
        ba_price, _ = self._best_ask(od)
        
        if ba_price is not None and ba_price < fair - self.ASH_TAKE_THRESH:
            qty = self._clamp(self.ASH_TAKE_QTY, pos, symbol)
            if qty > 0:
                orders.append(Order(symbol, ba_price, qty))
                pos += qty

        if bb_price is not None and bb_price > fair + self.ASH_TAKE_THRESH:
            qty = self._clamp(-self.ASH_TAKE_QTY, pos, symbol)
            if qty < 0:
                orders.append(Order(symbol, bb_price, qty))
                pos += qty

        inv_ratio = pos / self.POSITION_LIMITS[symbol]  
        skew = round(inv_ratio * 2)  

        our_bid = fair - self.ASH_MM_EDGE - skew
        our_ask = fair + self.ASH_MM_EDGE - skew  

        buy_qty = self._clamp(self.ASH_MM_QTY, pos, symbol)
        if buy_qty > 0:
            orders.append(Order(symbol, int(our_bid), buy_qty))

        sell_qty = self._clamp(-self.ASH_MM_QTY, pos, symbol)
        if sell_qty < 0:
            orders.append(Order(symbol, int(our_ask), sell_qty))

        return orders

    def _trade_ipr(self, state: TradingState) -> List[Order]:
        symbol = 'INTARIAN_PEPPER_ROOT'
        if symbol not in state.order_depths:
            return []
        
        od = state.order_depths[symbol]
        pos = state.position.get(symbol, 0)
        orders = []
        
        fair = self._ipr_fair(state)
        if fair is None:
            return []
        
        bb_price, _ = self._best_bid(od)
        ba_price, _ = self._best_ask(od)

        
        if ba_price is not None and ba_price < fair - self.IPR_TAKE_THRESH:
            qty = self._clamp(self.IPR_TAKE_QTY, pos, symbol)
            if qty > 0:
                orders.append(Order(symbol, ba_price, qty))
                pos += qty

        if bb_price is not None and bb_price > fair + self.IPR_TAKE_THRESH:
            qty = self._clamp(-self.IPR_TAKE_QTY, pos, symbol)
            if qty < 0:
                orders.append(Order(symbol, bb_price, qty))
                pos += qty

        
        inv_ratio = pos / self.POSITION_LIMITS[symbol]
        skew = round(inv_ratio * 3)  

        our_bid = int(fair - self.IPR_BID_EDGE - skew)
        our_ask = int(fair + self.IPR_ASK_EDGE - skew)

        if our_bid >= our_ask:
            our_bid = int(fair) - 1
            our_ask = int(fair) + 1

        buy_qty = self._clamp(self.IPR_MM_QTY, pos, symbol)
        if buy_qty > 0:
            orders.append(Order(symbol, our_bid, buy_qty))

        sell_qty = self._clamp(-self.IPR_MM_QTY, pos, symbol)
        if sell_qty < 0:
            orders.append(Order(symbol, our_ask, sell_qty))

        return orders

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        conversions = 0
        trader_data = ""

        ash_orders = self._trade_ash(state)
        if ash_orders:
            result['ASH_COATED_OSMIUM'] = ash_orders

        ipr_orders = self._trade_ipr(state)
        if ipr_orders:
            result['INTARIAN_PEPPER_ROOT'] = ipr_orders

        return result, conversions, trader_data
