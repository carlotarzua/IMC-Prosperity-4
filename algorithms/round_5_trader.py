from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Optional, Tuple
import json
import math

"""
Round 5 strategy summary.

This trading strategy is based on QAPCA, which uses PCA relationships between
the Round 5 products to estimate fair values from the live market.

The PCA parameters below were calibrated offline using the public Round 5 data.
During the actual run, the strategy only uses the current order book, current
positions, and its own saved state.

In practice, the strategy:
- estimates a fair value for each product from live mid-prices,
- checks whether a product looks cheap or expensive versus that fair value,
- places market-making quotes around the fair value,
- adjusts quotes and size based on inventory and product risk.

The session profile is a broad liquidity/risk adjustment for different parts
of the round. It is not designed to replay historical prices or follow exact
timestamp-by-timestamp trading instructions.
"""

class Trader:

    QAPCA_PRODUCTS = ["GALAXY_SOUNDS_BLACK_HOLES", "GALAXY_SOUNDS_DARK_MATTER", "GALAXY_SOUNDS_PLANETARY_RINGS", "GALAXY_SOUNDS_SOLAR_FLAMES", "GALAXY_SOUNDS_SOLAR_WINDS", "MICROCHIP_CIRCLE", "MICROCHIP_OVAL", "MICROCHIP_RECTANGLE", "MICROCHIP_SQUARE", "MICROCHIP_TRIANGLE", "OXYGEN_SHAKE_CHOCOLATE", "OXYGEN_SHAKE_EVENING_BREATH", "OXYGEN_SHAKE_GARLIC", "OXYGEN_SHAKE_MINT", "OXYGEN_SHAKE_MORNING_BREATH", "PANEL_1X2", "PANEL_1X4", "PANEL_2X2", "PANEL_2X4", "PANEL_4X4", "PEBBLES_L", "PEBBLES_M", "PEBBLES_S", "PEBBLES_XL", "PEBBLES_XS", "ROBOT_DISHES", "ROBOT_IRONING", "ROBOT_LAUNDRY", "ROBOT_MOPPING", "ROBOT_VACUUMING", "SLEEP_POD_COTTON", "SLEEP_POD_LAMB_WOOL", "SLEEP_POD_NYLON", "SLEEP_POD_POLYESTER", "SLEEP_POD_SUEDE", "SNACKPACK_CHOCOLATE", "SNACKPACK_PISTACHIO", "SNACKPACK_RASPBERRY", "SNACKPACK_STRAWBERRY", "SNACKPACK_VANILLA", "TRANSLATOR_ASTRO_BLACK", "TRANSLATOR_ECLIPSE_CHARCOAL", "TRANSLATOR_GRAPHITE_MIST", "TRANSLATOR_SPACE_GRAY", "TRANSLATOR_VOID_BLUE", "UV_VISOR_AMBER", "UV_VISOR_MAGENTA", "UV_VISOR_ORANGE", "UV_VISOR_RED", "UV_VISOR_YELLOW"]
    QAPCA_MU = [9.34379056, 9.23223636, 9.2816563, 9.31320993, 9.25181358, 9.12696278, 8.98991933, 9.07113403, 9.50780359, 9.17460845, 9.16336756, 9.13380596, 9.38323295, 9.19266637, 9.20825464, 9.09415767, 9.14428071, 9.16456733, 9.32793615, 9.19708291, 9.22571352, 9.23402677, 9.09290172, 9.48054877, 8.89110549, 9.21063065, 9.06730129, 9.19046237, 9.31231669, 9.12164949, 9.34957621, 9.27739282, 9.17192889, 9.37577367, 9.33789489, 9.19434459, 9.15841509, 9.21794962, 9.27803165, 9.21986735, 9.14553018, 9.19088065, 9.21758459, 9.15040579, 9.29125312, 8.96837614, 9.31419611, 9.25071502, 9.30999337, 9.29980488]
    QAPCA_SD = [0.08243265, 0.03207538, 0.07166546, 0.04049873, 0.0520579, 0.05631486, 0.20135985, 0.08540336, 0.14101292, 0.08894654, 0.05682802, 0.04338677, 0.0803479, 0.05303714, 0.06530101, 0.06644409, 0.08857017, 0.07106386, 0.05576392, 0.04578731, 0.0616089, 0.06819263, 0.09627666, 0.1383494, 0.19276342, 0.05546628, 0.08915325, 0.06348872, 0.06943281, 0.05804912, 0.07623737, 0.03844322, 0.05246644, 0.08447585, 0.0814202, 0.0204715, 0.01970653, 0.01683959, 0.0343245, 0.0176761, 0.052176, 0.03631093, 0.04824596, 0.05406311, 0.05432557, 0.12343556, 0.05635449, 0.05273329, 0.05266589, 0.06307176]
    QAPCA_PCS = [[0.178375, 0.0161987, 0.0663818, -0.0376016, 0.1526777, 0.0641961, -0.1981525, -0.1483717, 0.1705202, -0.170211, 0.1224062, 0.041849, 0.1746251, -0.0944715, -0.1619338, 0.0320707, -0.1701636, -0.1423999, 0.1800224, 0.0027621, 0.0647232, 0.1563037, -0.1815595, 0.1566213, -0.1944853, 0.1715967, -0.1858626, -0.1778021, 0.164554, -0.1871503, 0.177916, 0.0461946, 0.1290581, 0.1827432, 0.1640296, -0.1495656, -0.1571383, 0.0002271, 0.1673026, 0.1003006, -0.1314037, 0.0115059, 0.1129181, -0.1209247, 0.1490161, -0.1957663, 0.1633579, 0.1342615, 0.1491783, -0.022683], [0.0279411, -0.2253188, -0.2680508, -0.100911, 0.0943872, 0.2122952, -0.0667023, 0.1788948, -0.1750392, -0.1479017, 0.1824011, 0.1361035, -0.0121797, -0.1456936, 0.0240424, 0.3294355, -0.0665095, -0.1756954, -0.0205903, 0.1000164, -0.0447212, 0.0461286, -0.0606552, -0.0866438, 0.081561, -0.0176814, -0.0476551, -0.1060539, 0.003385, 0.0143419, -0.0463563, 0.2216461, 0.2404141, -0.1251146, -0.1784145, -0.0693755, 0.0267689, 0.0140176, -0.1213693, 0.1124883, 0.1668794, -0.2295795, 0.0113595, -0.0762119, -0.1670208, 0.090435, -0.1628486, -0.089656, 0.1720473, -0.2882138], [0.1064526, -0.1612543, -0.0203224, 0.2316392, -0.1555791, 0.2927161, -0.0278293, 0.0657805, -0.0444357, -0.0632976, 0.1924594, -0.2220731, 0.1613726, 0.1576177, 0.1349742, -0.0206178, 0.1712477, 0.0798171, 0.1307394, -0.2959185, -0.3033657, -0.1484569, -0.1124752, 0.239418, -0.0438087, 0.1275667, 0.0381652, 0.0845876, -0.1681749, 0.0682846, -0.1020042, -0.0378531, -0.006191, -0.02812, -0.014267, -0.0367537, -0.0364264, 0.0483496, 0.062105, 0.072618, -0.0277335, 0.0927875, -0.3120478, -0.2706127, 0.1522273, -0.0173356, 0.0227221, -0.0644339, 0.0199894, -0.1097747], [0.1345469, 0.00503, -0.1438043, 0.0904172, -0.1411388, -0.0362613, 0.0056536, 0.1646683, -0.0590705, -0.0819793, -0.0074927, -0.075185, 0.041112, -0.2979251, 0.1958404, -0.048539, 0.0670747, -0.2298447, -0.004628, 0.2318792, 0.1366658, -0.1873848, -0.0490049, 0.0106427, 0.0706464, 0.0865496, 0.0529411, -0.1053149, -0.0960783, 0.0993691, 0.1499172, -0.1961395, -0.0910011, 0.1075633, -0.0549907, 0.002127, 0.2085539, -0.4194249, 0.1656455, -0.0464893, 0.2605893, 0.2549264, 0.1007424, -0.1622649, 0.0373657, -0.0362564, 0.0335742, 0.0774698, 0.1208078, 0.1341963], [0.1109176, 0.3360579, -0.2190023, 0.1321148, -0.0629558, -0.0912211, 0.0345518, -0.0687744, -0.0099202, 0.0270969, -0.049689, -0.4067499, 0.139222, -0.0400679, -0.0260102, 0.0492779, -0.0351273, -0.0520232, 0.086578, 0.1927331, -0.1875512, 0.0486299, -0.0385283, 0.067254, 0.0314882, -0.0823235, -0.1887919, 0.0758332, 0.1772667, 0.098658, 0.0900958, 0.0161314, -0.0417196, 0.0231076, -0.1188884, -0.0771197, -0.2282522, 0.090457, -0.0736353, 0.1597675, 0.1361008, -0.1852682, 0.0263223, 0.0023898, -0.1182057, 0.0357569, 0.0209516, -0.3846728, -0.0231905, 0.2759315], [-0.0319682, 0.0535964, 0.1662675, -0.0924217, -0.111085, 0.0270405, 0.0585017, 0.1076982, -0.026209, 0.0845631, 0.105383, 0.0479472, -0.1071602, -0.0342415, -0.0279545, 0.130583, -0.083574, 0.0319457, 0.0737587, -0.0330782, 0.0119585, -0.1315299, 0.134364, -0.0234031, 0.0013563, -0.1052728, 0.030448, 0.0012151, 0.1684007, -0.0079458, 0.04616, 0.0091634, -0.056366, -0.0281613, 0.0355166, -0.4909872, 0.1814562, -0.1259453, 0.0138362, 0.5895945, 0.063994, 0.0593672, -0.1319579, 0.1418843, 0.1621177, 0.0413806, 0.0637714, 0.0492713, -0.253584, 0.0014447], [-0.1232934, -0.0669136, -0.05834, 0.514724, 0.1102409, -0.0987876, 0.0156491, -0.0396904, 0.0979984, 0.1014592, -0.1157506, 0.0388502, 0.1219306, -0.029607, -0.0932223, -0.0756901, -0.108472, 0.0485767, -0.0116148, -0.2842462, 0.1229765, 0.1175091, 0.052429, -0.0414543, -0.0748843, -0.202268, -0.1527319, 0.1521172, 0.0059745, 0.0437773, 0.0356213, 0.136855, -0.04037, -0.0193151, -0.1172929, -0.0790431, 0.0966238, -0.3630863, 0.2008023, 0.0315507, 0.0286153, -0.3160103, -0.0604521, -0.0664885, -0.0398061, -0.0381616, -0.1861562, 0.133428, 0.098438, -0.0380296], [-0.1037795, 0.1504063, -0.1516874, -0.0877235, 0.1094353, 0.0980567, -0.0060264, -0.1638076, -0.0499962, -0.0069306, 0.0649438, 0.1884486, -0.0852437, 0.1937162, -0.2154743, 0.1118998, 0.011336, 0.0835873, 0.0914384, -0.009302, -0.290435, 0.094859, 0.0813455, -0.0033087, 0.0037185, 0.130157, -0.0268873, 0.0142241, 0.0719748, -0.0350315, -0.0874052, -0.4710358, 0.2461349, -0.0461249, -0.0664122, 0.0773195, 0.1901725, -0.3935387, 0.1312599, -0.0037319, -0.1284308, 0.002763, 0.0646935, -0.0998593, -0.1189886, 0.028227, 0.0368689, -0.1778886, -0.0967698, 0.0521093]]
    QAPCA_INDEX = {p: i for i, p in enumerate(QAPCA_PRODUCTS)}

    LIMIT = 10
    FORCE_FLAT_TS = 100_000

    PEBBLES_ALL = ["PEBBLES_XS", "PEBBLES_S", "PEBBLES_M", "PEBBLES_L", "PEBBLES_XL"]
    PEBBLES_TRADE = {"PEBBLES_L", "PEBBLES_M", "PEBBLES_XL"}

    ACTIVE = {
        "ROBOT_DISHES",
        "ROBOT_IRONING",
        "OXYGEN_SHAKE_CHOCOLATE",
        "OXYGEN_SHAKE_EVENING_BREATH",
        "PEBBLES_XL",
        "TRANSLATOR_ASTRO_BLACK",
        "UV_VISOR_AMBER",
        "SNACKPACK_CHOCOLATE",
        "SNACKPACK_VANILLA",
        "SNACKPACK_PISTACHIO",
        "SNACKPACK_STRAWBERRY",
    }


    BLACKLIST = set()

    SESSION_OPPORTUNITY = {
        0: {
            "PEBBLES_XL", "PEBBLES_M", "PEBBLES_L", "PANEL_4X4",
            "OXYGEN_SHAKE_CHOCOLATE", "SNACKPACK_RASPBERRY",
            "TRANSLATOR_VOID_BLUE", "PANEL_2X4", "SNACKPACK_CHOCOLATE",
            "SNACKPACK_PISTACHIO",
        },
        1: {
            "SLEEP_POD_COTTON", "ROBOT_IRONING", "PANEL_1X4",
            "PEBBLES_XS", "OXYGEN_SHAKE_GARLIC", "SLEEP_POD_POLYESTER",
            "ROBOT_LAUNDRY", "UV_VISOR_ORANGE", "PANEL_4X4",
            "OXYGEN_SHAKE_MINT",
        },
        2: {
            "GALAXY_SOUNDS_PLANETARY_RINGS", "MICROCHIP_TRIANGLE",
            "TRANSLATOR_ECLIPSE_CHARCOAL", "ROBOT_DISHES",
            "PANEL_4X4", "SLEEP_POD_LAMB_WOOL", "TRANSLATOR_SPACE_GRAY",
            "MICROCHIP_RECTANGLE", "SLEEP_POD_COTTON", "PEBBLES_L",
        },
        3: {
            "SLEEP_POD_POLYESTER", "PEBBLES_XL", "TRANSLATOR_SPACE_GRAY",
            "PANEL_1X4", "UV_VISOR_ORANGE", "OXYGEN_SHAKE_MORNING_BREATH",
            "OXYGEN_SHAKE_GARLIC", "SLEEP_POD_LAMB_WOOL",
            "UV_VISOR_YELLOW", "SLEEP_POD_COTTON",
        },
        4: {
            "MICROCHIP_SQUARE", "PEBBLES_XL", "OXYGEN_SHAKE_GARLIC",
            "GALAXY_SOUNDS_DARK_MATTER", "SLEEP_POD_COTTON",
            "PEBBLES_M", "PANEL_2X4", "GALAXY_SOUNDS_SOLAR_WINDS",
            "PANEL_4X4", "GALAXY_SOUNDS_PLANETARY_RINGS",
        },
    }

    SESSION_REDUCTION = {
        0: {
            "GALAXY_SOUNDS_DARK_MATTER", "OXYGEN_SHAKE_GARLIC",
            "OXYGEN_SHAKE_MINT", "GALAXY_SOUNDS_SOLAR_WINDS",
            "OXYGEN_SHAKE_MORNING_BREATH", "SNACKPACK_VANILLA",
            "ROBOT_MOPPING",
        },
        1: {
            "PEBBLES_XL", "ROBOT_DISHES", "TRANSLATOR_ECLIPSE_CHARCOAL",
            "GALAXY_SOUNDS_SOLAR_WINDS", "OXYGEN_SHAKE_CHOCOLATE",
            "TRANSLATOR_GRAPHITE_MIST",
        },
        2: {
            "SLEEP_POD_POLYESTER", "OXYGEN_SHAKE_GARLIC",
            "OXYGEN_SHAKE_CHOCOLATE", "UV_VISOR_AMBER",
            "PEBBLES_XL", "SNACKPACK_CHOCOLATE",
        },
        3: {
            "PEBBLES_XS", "MICROCHIP_SQUARE",
            "OXYGEN_SHAKE_EVENING_BREATH", "GALAXY_SOUNDS_SOLAR_WINDS",
            "PANEL_2X4",
        },
        4: {
            "TRANSLATOR_SPACE_GRAY", "SLEEP_POD_LAMB_WOOL",
            "ROBOT_LAUNDRY", "PEBBLES_XS", "TRANSLATOR_GRAPHITE_MIST",
        },
    }

    ALWAYS_LIGHT = {
        "TRANSLATOR_GRAPHITE_MIST", "UV_VISOR_RED", "PANEL_2X2",
        "ROBOT_MOPPING", "SLEEP_POD_NYLON", "UV_VISOR_MAGENTA",
        "SLEEP_POD_SUEDE", "TRANSLATOR_ASTRO_BLACK", "PANEL_1X2",
        "MICROCHIP_OVAL",
    }




    QAPCA_SKIP = {
        "ROBOT_LAUNDRY",
        "MICROCHIP_RECTANGLE",
        "UV_VISOR_RED",
        "PANEL_2X2",
        "SLEEP_POD_NYLON",
        "UV_VISOR_MAGENTA",
        "SLEEP_POD_SUEDE",
        "TRANSLATOR_ASTRO_BLACK",
        "PANEL_1X2",
    }


    CORE_PRODUCTS = {
        "GALAXY_SOUNDS_PLANETARY_RINGS", "SLEEP_POD_COTTON", "PANEL_4X4",
        "PEBBLES_XS", "MICROCHIP_SQUARE", "UV_VISOR_ORANGE",
        "OXYGEN_SHAKE_GARLIC", "TRANSLATOR_SPACE_GRAY", "PANEL_1X4",
        "ROBOT_IRONING", "PEBBLES_L", "PEBBLES_M",
        "GALAXY_SOUNDS_DARK_MATTER", "MICROCHIP_TRIANGLE",
        "TRANSLATOR_VOID_BLUE", "TRANSLATOR_ECLIPSE_CHARCOAL",
        "SLEEP_POD_POLYESTER", "OXYGEN_SHAKE_MINT",
        "GALAXY_SOUNDS_BLACK_HOLES", "PEBBLES_XL",
        "OXYGEN_SHAKE_MORNING_BREATH", "MICROCHIP_CIRCLE",
        "OXYGEN_SHAKE_CHOCOLATE", "SLEEP_POD_LAMB_WOOL",
    }

    SECONDARY_PRODUCTS = {
        "SNACKPACK_VANILLA", "MICROCHIP_RECTANGLE", "PANEL_2X4",
        "UV_VISOR_YELLOW", "ROBOT_VACUUMING", "GALAXY_SOUNDS_SOLAR_FLAMES",
        "SNACKPACK_CHOCOLATE", "SNACKPACK_PISTACHIO", "UV_VISOR_AMBER",
        "OXYGEN_SHAKE_EVENING_BREATH", "ROBOT_LAUNDRY",
        "SNACKPACK_RASPBERRY", "GALAXY_SOUNDS_SOLAR_WINDS",
    }

    REDUCED_PRODUCTS = {
        "PEBBLES_S", "SNACKPACK_STRAWBERRY", "UV_VISOR_MAGENTA",
        "ROBOT_MOPPING", "SLEEP_POD_NYLON", "MICROCHIP_OVAL",
        "PANEL_1X2", "SLEEP_POD_SUEDE", "TRANSLATOR_ASTRO_BLACK",
        "PANEL_2X2", "UV_VISOR_RED", "TRANSLATOR_GRAPHITE_MIST",
    }


    JUMP_PRODUCTS = {}


    MAKERS = {}

    SNACKS = [
        "SNACKPACK_CHOCOLATE", "SNACKPACK_VANILLA", "SNACKPACK_PISTACHIO",
        "SNACKPACK_STRAWBERRY", "SNACKPACK_RASPBERRY",
    ]
    SNACK_TRADE = {"SNACKPACK_CHOCOLATE", "SNACKPACK_VANILLA", "SNACKPACK_PISTACHIO", "SNACKPACK_STRAWBERRY"}
    SNACK_RELATIONS = [
        ("SNACKPACK_CHOCOLATE", "SNACKPACK_VANILLA", 1, 45.0, 0.90),
        ("SNACKPACK_STRAWBERRY", "SNACKPACK_RASPBERRY", 1, 88.0, 0.45),
        ("SNACKPACK_PISTACHIO", "SNACKPACK_STRAWBERRY", -1, 98.0, 0.45),
        ("SNACKPACK_PISTACHIO", "SNACKPACK_RASPBERRY", 1, 74.0, 0.45),
    ]


    def _session_profile(self, timestamp: int) -> int:
        if timestamp < 20_000:
            return 0
        if timestamp < 40_000:
            return 1
        if timestamp < 60_000:
            return 2
        if timestamp < 80_000:
            return 3
        return 4

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        mem = self._load(state.traderData)
        mids = {p: self._mid(d) for p, d in state.order_depths.items()}

        ema = mem.setdefault("ema", {})
        for p, m in mids.items():
            if m is None:
                continue
            old = float(ema.get(p, m))

            ema[p] = 0.06 * float(m) + 0.94 * old

        if state.timestamp >= self.FORCE_FLAT_TS:
            for p, depth in state.order_depths.items():
                pos = int(state.position.get(p, 0))
                if pos:
                    orders = self._flatten_orders(p, depth, pos)
                    if orders:
                        result[p] = orders
            return result, 0, self._dump(mem)


        regime = "balanced"
        mem["regime"] = regime
        mem["session"] = self._session_profile(state.timestamp)

        self._trade_pebbles_xs_xl(state, mids, mem, regime, result)
        self._trade_jump_fades(state, mids, mem, regime, result)
        self._trade_oxygen_microfade(state, mids, mem, result)
        self._trade_qapca_all(state, mids, mem, regime, result)
        self._trade_makers(state, mids, mem, result)


        for p in self.BLACKLIST:
            result.pop(p, None)
            pos = int(state.position.get(p, 0))
            if pos and p in state.order_depths:
                flat = self._flatten_orders(p, state.order_depths[p], pos)
                if flat:
                    result[p] = flat

        mem["last_mid"] = {p: m for p, m in mids.items() if m is not None}
        return result, 0, self._dump(mem)



    def _trade_pebbles_xs_xl(self, state: TradingState, mids: Dict[str, Optional[float]], mem: Dict, regime: str, result: Dict[str, List[Order]]) -> None:

        if any(mids.get(p) is None or p not in state.order_depths for p in self.PEBBLES_ALL):
            return
        total = sum(float(mids[p]) for p in self.PEBBLES_ALL)


        session = self._session_profile(state.timestamp)
        trade_set = set(self.PEBBLES_TRADE)
        if session == 1:
            trade_set.add("PEBBLES_XS")
            trade_set.discard("PEBBLES_XL")
        elif session in (0, 3, 4):
            trade_set.discard("PEBBLES_XS")
        elif session == 2:
            trade_set = {"PEBBLES_L", "PEBBLES_M"}
        candidates = []
        for p in trade_set:
            depth = state.order_depths[p]
            bid, ask = self._best_bid_ask(depth)
            if bid is None or ask is None:
                continue
            fair = 50000.0 - (total - float(mids[p]))
            spread = ask - bid
            buy_edge = fair - ask
            sell_edge = bid - fair
            best_edge = max(buy_edge, sell_edge)
            candidates.append((best_edge, p, fair, bid, ask, spread, buy_edge, sell_edge))

        candidates.sort(reverse=True)
        for best_edge, p, fair, bid, ask, spread, buy_edge, sell_edge in candidates[:2]:
            depth = state.order_depths[p]
            pos = int(state.position.get(p, 0))
            orders = result.setdefault(p, [])
            if regime == "conservative":
                take_edge = max(10.0, 0.55 * spread + 2.5)
                max_abs_pos = 8
                cross_divisor = 3
                passive = max(2.5, min(6.0, 0.16 * spread + 1.0))
                skew = 0.45 * pos
                passive_lot = 3
            else:
                take_edge = max(7.0, 0.42 * spread + 1.3)
                max_abs_pos = 10
                cross_divisor = 2
                passive = max(1.8, min(4.5, 0.10 * spread + 0.8))
                skew = 0.34 * pos
                passive_lot = 4

            if buy_edge > take_edge and pos < max_abs_pos:
                qty = min(max_abs_pos - pos, abs(depth.sell_orders[ask]), max(1, int(buy_edge // cross_divisor)))
                if qty > 0:
                    orders.append(Order(p, ask, qty))
                    pos += qty
            elif sell_edge > take_edge and pos > -max_abs_pos:
                qty = min(max_abs_pos + pos, depth.buy_orders[bid], max(1, int(sell_edge // cross_divisor)))
                if qty > 0:
                    orders.append(Order(p, bid, -qty))
                    pos -= qty

            buy_px = min(bid + 1, int(math.floor(fair - passive - skew)))
            sell_px = max(ask - 1, int(math.ceil(fair + passive - skew)))
            if buy_px < ask and pos < max_abs_pos and buy_px < sell_px:
                orders.append(Order(p, buy_px, min(passive_lot, max_abs_pos - pos)))
            if sell_px > bid and pos > -max_abs_pos and buy_px < sell_px:
                orders.append(Order(p, sell_px, -min(passive_lot, max_abs_pos + pos)))

            if not orders:
                result.pop(p, None)

    def _trade_jump_fades(self, state: TradingState, mids: Dict[str, Optional[float]], mem: Dict, regime: str, result: Dict[str, List[Order]]) -> None:
        last_mid = mem.get("last_mid", {}) if isinstance(mem.get("last_mid"), dict) else {}
        jump_mem = mem.setdefault("jump", {})

        for p, cfg in self.JUMP_PRODUCTS.items():
            if p not in state.order_depths or mids.get(p) is None:
                continue
            cfg = dict(cfg)
            if regime == "aggressive" and p == "ROBOT_IRONING":
                cfg["min"] = 96; cfg["max"] = 106; cfg["target"] = 2; cfg["hold"] = 1
            if regime == "aggressive" and p == "ROBOT_DISHES":
                cfg["min"] = 74; cfg["max"] = 126; cfg["target"] = 10; cfg["hold"] = 2
            if p.startswith("OXYGEN_SHAKE"):
                cfg["min"] = 74; cfg["max"] = 126; cfg["target"] = 6; cfg["hold"] = 2

            depth = state.order_depths[p]
            pos = int(state.position.get(p, 0))
            m = float(mids[p])
            prev = last_mid.get(p)
            target = None

            if prev is not None:
                jump = m - float(prev)
                if cfg["min"] <= abs(jump) <= cfg["max"]:
                    target = -int(math.copysign(int(cfg["target"]), jump))
                    jump_mem[p] = {"target": target, "ttl": int(cfg["hold"])}

            active = jump_mem.get(p)
            if target is None and isinstance(active, dict):
                ttl = int(active.get("ttl", 0))
                if ttl > 0:
                    target = int(active.get("target", 0))
                    active["ttl"] = ttl - 1
                else:
                    target = 0 if abs(pos) <= 4 else int(math.copysign(4, pos))
                    jump_mem[p] = {"target": 0, "ttl": 0}

            if target is not None:
                orders = result.setdefault(p, [])
                self._move_to_target_aggressive(p, depth, pos, target, orders)
                if not orders:
                    result.pop(p, None)

    def _trade_snacks(self, state: TradingState, mids: Dict[str, Optional[float]], mem: Dict, result: Dict[str, List[Order]]) -> None:
        if any(mids.get(p) is None for p in self.SNACKS):
            return
        rel_ema = mem.setdefault("rel", {})
        raw_signal: Dict[str, float] = {p: 0.0 for p in self.SNACKS}

        for a, b, sign, threshold, weight in self.SNACK_RELATIONS:
            combo = float(mids[a]) + sign * float(mids[b])
            key = f"{a}|{sign}|{b}"
            base = float(rel_ema.get(key, combo))
            rel_ema[key] = 0.012 * combo + 0.988 * base
            dev = combo - base
            if abs(dev) < threshold:
                continue
            z = max(-1.75, min(1.75, dev / threshold))
            raw_signal[a] += -weight * z
            raw_signal[b] += (-sign) * weight * z

        for p, sig in raw_signal.items():
            if p not in self.SNACK_TRADE or abs(sig) < 0.75 or p not in state.order_depths:
                continue
            depth = state.order_depths[p]
            bid, ask = self._best_bid_ask(depth)
            if bid is None or ask is None:
                continue
            spread = ask - bid
            if spread > 22:
                continue
            pos = int(state.position.get(p, 0))
            max_abs_pos = 5
            fair = float(mids[p]) + 4.2 * sig - 0.55 * pos
            orders = result.setdefault(p, [])

            if sig > 1.25 and fair - ask > max(14.0, 0.75 * spread) and pos < max_abs_pos:
                qty = min(2, max_abs_pos - pos, abs(depth.sell_orders[ask]))
                if qty > 0:
                    orders.append(Order(p, ask, qty)); pos += qty
            elif sig < -1.25 and bid - fair > max(14.0, 0.75 * spread) and pos > -max_abs_pos:
                qty = min(2, max_abs_pos + pos, depth.buy_orders[bid])
                if qty > 0:
                    orders.append(Order(p, bid, -qty)); pos -= qty

            buy_px = min(bid + 1, int(math.floor(fair - 3.5)))
            sell_px = max(ask - 1, int(math.ceil(fair + 3.5)))
            if buy_px < ask and buy_px < sell_px and sig > 0 and pos < max_abs_pos:
                orders.append(Order(p, buy_px, min(1, max_abs_pos - pos)))
            if sell_px > bid and buy_px < sell_px and sig < 0 and pos > -max_abs_pos:
                orders.append(Order(p, sell_px, -min(1, max_abs_pos + pos)))

            if not orders:
                result.pop(p, None)


    def _trade_oxygen_microfade(self, state: TradingState, mids: Dict[str, Optional[float]], mem: Dict, result: Dict[str, List[Order]]) -> None:

        last_mid = mem.get("last_mid", {}) if isinstance(mem.get("last_mid"), dict) else {}
        for p in ():
            if p in result or p not in state.order_depths or mids.get(p) is None or p not in last_mid:
                continue
            move = float(mids[p]) - float(last_mid[p])
            if abs(move) < 24 or abs(move) > 74:
                continue
            depth = state.order_depths[p]
            bid, ask = self._best_bid_ask(depth)
            if bid is None or ask is None:
                continue
            pos = int(state.position.get(p, 0))
            orders = result.setdefault(p, [])
            if move > 0 and pos > -6:
                qty = min(2, 6 + pos, depth.buy_orders[bid])
                if qty > 0:
                    orders.append(Order(p, bid, -qty))
            elif move < 0 and pos < 6:
                qty = min(2, 6 - pos, abs(depth.sell_orders[ask]))
                if qty > 0:
                    orders.append(Order(p, ask, qty))
            if not orders:
                result.pop(p, None)


    def _trade_qapca_all(self, state: TradingState, mids: Dict[str, Optional[float]], mem: Dict, regime: str, result: Dict[str, List[Order]]) -> None:

        if any(mids.get(p) is None or p not in state.order_depths for p in self.QAPCA_PRODUCTS):
            return

        session = self._session_profile(state.timestamp)
        boost_set = self.SESSION_OPPORTUNITY.get(session, set())
        block_set = self.SESSION_REDUCTION.get(session, set())

        z = []
        for p, mu, sd in zip(self.QAPCA_PRODUCTS, self.QAPCA_MU, self.QAPCA_SD):
            m = max(1.0, float(mids[p]))
            z.append((math.log(m) - mu) / max(sd, 1e-9))

        recon = [0.0 for _ in z]
        for pc in self.QAPCA_PCS:
            score = sum(zi * pci for zi, pci in zip(z, pc))
            for i, pci in enumerate(pc):
                recon[i] += score * pci

        fair_by_product = {}
        residual_by_product = {}
        for i, p in enumerate(self.QAPCA_PRODUCTS):
            fair_log = self.QAPCA_MU[i] + self.QAPCA_SD[i] * recon[i]
            pca_fair = math.exp(fair_log)
            mid = float(mids[p])

            fair = 0.42 * pca_fair + 0.58 * mid
            fair_by_product[p] = fair
            residual_by_product[p] = pca_fair - mid

        def max_abs_for(product: str, spread: int) -> int:
            if product in self.CORE_PRODUCTS:
                return 10
            if product in self.SECONDARY_PRODUCTS:
                return 8
            if product in self.REDUCED_PRODUCTS:
                return 2
            return 6

        for p in self.QAPCA_PRODUCTS:
            if p in self.QAPCA_SKIP or p in result:
                continue
            depth = state.order_depths[p]
            bid, ask = self._best_bid_ask(depth)
            if bid is None or ask is None:
                continue
            spread = ask - bid
            if spread <= 3 or spread > 70:
                continue

            pos = int(state.position.get(p, 0))
            boost = p in boost_set
            blocked = p in block_set

            if blocked:
                if pos != 0:
                    orders = []
                    if pos > 0 and ask - 1 > bid:
                        orders.append(Order(p, ask - 1, -min(2, pos)))
                    elif pos < 0 and bid + 1 < ask:
                        orders.append(Order(p, bid + 1, min(2, -pos)))
                    if orders:
                        result[p] = orders
                continue

            max_abs = max_abs_for(p, spread)
            if p in self.ALWAYS_LIGHT and not boost:
                max_abs = min(max_abs, 2)
            if boost:
                max_abs = min(10, max(max_abs, 7 if p in self.ALWAYS_LIGHT else 9))
            if abs(pos) > max_abs:

                orders = result.setdefault(p, [])
                if pos > max_abs:
                    orders.append(Order(p, bid, -min(pos - max_abs, depth.buy_orders[bid])))
                elif pos < -max_abs:
                    orders.append(Order(p, ask, min(-max_abs - pos, abs(depth.sell_orders[ask]))))
                continue

            mid = float(mids[p])
            fair = fair_by_product[p]
            residual = residual_by_product[p]


            bid_vol = sum(max(0, int(v)) for v in depth.buy_orders.values())
            ask_vol = sum(max(0, -int(v)) for v in depth.sell_orders.values())
            imbalance = 0.0
            if bid_vol + ask_vol > 0:
                imbalance = (bid_vol - ask_vol) / float(bid_vol + ask_vol)

            edge = max(0.5, min(3.0, 0.055 * spread + 0.45))
            if boost:
                edge = max(0.3, edge * 0.65)
            elif p in self.ALWAYS_LIGHT:
                edge = min(4.5, edge * 1.35 + 0.25)
            skew = 0.24 * pos if boost else (0.30 * pos if p in self.CORE_PRODUCTS else 0.42 * pos)
            residual_ticks = residual / max(1.0, 0.18 * spread + 6.0)
            directional_skew = max(-3.5, min(3.5, residual_ticks))
            micro_skew = max(-2.5, min(2.5, 0.16 * spread * imbalance))
            quote_fair = fair + directional_skew + micro_skew - skew

            buy_px = min(bid + 1, int(math.floor(quote_fair - edge)))
            sell_px = max(ask - 1, int(math.ceil(quote_fair + edge)))
            if buy_px >= ask:
                buy_px = ask - 1
            if sell_px <= bid:
                sell_px = bid + 1

            orders: List[Order] = []

            if p in self.CORE_PRODUCTS:
                base_lot = 4 if spread >= 8 else 3
            elif p in self.SECONDARY_PRODUCTS:
                base_lot = 3 if spread >= 8 else 2
            elif p in self.REDUCED_PRODUCTS:
                base_lot = 1
            else:
                base_lot = 2 if spread >= 8 else 1

            if boost:
                base_lot = min(6, max(base_lot + 2, 4 if spread >= 8 else 3))
            elif p in self.ALWAYS_LIGHT:
                base_lot = 1

            buy_ok = pos < max_abs and (residual > -0.65 * spread or pos < 0 or p in self.CORE_PRODUCTS)
            sell_ok = pos > -max_abs and (residual < 0.65 * spread or pos > 0 or p in self.CORE_PRODUCTS)

            if boost:
                take_threshold = max(7.0, 0.70 * spread)
                if residual > take_threshold and pos < max_abs:
                    qty = min(2, max_abs - pos, abs(depth.sell_orders[ask]))
                    if qty > 0:
                        orders.append(Order(p, ask, qty))
                        pos += qty
                elif residual < -take_threshold and pos > -max_abs:
                    qty = min(2, max_abs + pos, depth.buy_orders[bid])
                    if qty > 0:
                        orders.append(Order(p, bid, -qty))
                        pos -= qty

            if buy_ok and buy_px < ask and buy_px < sell_px:
                qty = min(base_lot, max_abs - pos)
                if qty > 0:
                    orders.append(Order(p, buy_px, qty))
            if sell_ok and sell_px > bid and buy_px < sell_px:
                qty = min(base_lot, max_abs + pos)
                if qty > 0:
                    orders.append(Order(p, sell_px, -qty))

            if orders:
                result[p] = orders

    def _trade_makers(self, state: TradingState, mids: Dict[str, Optional[float]], mem: Dict, result: Dict[str, List[Order]]) -> None:
        ema = mem.get("ema", {}) if isinstance(mem.get("ema"), dict) else {}
        for p, cfg in self.MAKERS.items():
            if p in result or p not in state.order_depths or mids.get(p) is None:
                continue
            depth = state.order_depths[p]
            bid, ask = self._best_bid_ask(depth)
            if bid is None or ask is None:
                continue
            spread = ask - bid
            if spread > cfg["max_spread"]:
                continue

            pos = int(state.position.get(p, 0))

            max_abs_pos = 8 if p not in {"ROBOT_DISHES"} else 10
            if abs(pos) >= max_abs_pos:

                orders: List[Order] = []
                if pos > 0:
                    orders.append(Order(p, max(ask - 1, bid + 1), -min(cfg["lot"], pos)))
                elif pos < 0:
                    orders.append(Order(p, min(bid + 1, ask - 1), min(cfg["lot"], -pos)))
                if orders:
                    result[p] = orders
                continue

            fair = 0.65 * float(mids[p]) + 0.35 * float(ema.get(p, mids[p]))
            fair -= float(cfg["skew"]) * pos
            edge = float(cfg["edge"])
            lot = int(cfg["lot"])

            buy_px = min(bid + 1, int(math.floor(fair - edge)))
            sell_px = max(ask - 1, int(math.ceil(fair + edge)))
            orders = []
            if buy_px < ask and buy_px < sell_px and pos < max_abs_pos:
                orders.append(Order(p, buy_px, min(lot, max_abs_pos - pos)))
            if sell_px > bid and buy_px < sell_px and pos > -max_abs_pos:
                orders.append(Order(p, sell_px, -min(lot, max_abs_pos + pos)))
            if orders:
                result[p] = orders


    def _move_to_target_aggressive(self, p: str, depth: OrderDepth, pos: int, target: int, orders: List[Order]) -> None:
        target = max(-self.LIMIT, min(self.LIMIT, target))
        need = target - pos
        if need > 0:
            remaining = min(need, self.LIMIT - pos)
            for ask in sorted(depth.sell_orders.keys()):
                if remaining <= 0:
                    break
                qty = min(remaining, abs(depth.sell_orders[ask]))
                if qty > 0:
                    orders.append(Order(p, ask, qty))
                    remaining -= qty
        elif need < 0:
            remaining = min(-need, self.LIMIT + pos)
            for bid in sorted(depth.buy_orders.keys(), reverse=True):
                if remaining <= 0:
                    break
                qty = min(remaining, depth.buy_orders[bid])
                if qty > 0:
                    orders.append(Order(p, bid, -qty))
                    remaining -= qty

    def _flatten_orders(self, p: str, depth: OrderDepth, pos: int) -> List[Order]:
        orders: List[Order] = []
        if pos > 0:
            remaining = pos
            for bid in sorted(depth.buy_orders.keys(), reverse=True):
                qty = min(remaining, depth.buy_orders[bid])
                if qty > 0:
                    orders.append(Order(p, bid, -qty))
                    remaining -= qty
                if remaining <= 0:
                    break
        elif pos < 0:
            remaining = -pos
            for ask in sorted(depth.sell_orders.keys()):
                qty = min(remaining, abs(depth.sell_orders[ask]))
                if qty > 0:
                    orders.append(Order(p, ask, qty))
                    remaining -= qty
                if remaining <= 0:
                    break
        return orders

    def _best_bid_ask(self, depth: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
        bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
        ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
        return bid, ask

    def _mid(self, depth: OrderDepth) -> Optional[float]:
        bid, ask = self._best_bid_ask(depth)
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2.0

    def _load(self, s: str) -> Dict:
        if not s:
            return {}
        try:
            x = json.loads(s)
            return x if isinstance(x, dict) else {}
        except Exception:
            return {}

    def _dump(self, d: Dict) -> str:
        try:
            return json.dumps(d, separators=(",", ":"))
        except Exception:
            return ""