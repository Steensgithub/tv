from __future__ import annotations

from dataclasses import dataclass

from config import PineParams
from models import ExitType, OHLCVBar, PendingSetup, PivotLevel, Signal, SignalType, SymbolEngineState, TradeExit


@dataclass(slots=True)
class EngineOutput:
    signals: list[Signal]
    exits: list[TradeExit]


class SignalEngine:
    def __init__(self, symbol: str, exchange: str, timeframe: str, params: PineParams) -> None:
        self.symbol = symbol
        self.exchange = exchange
        self.timeframe = timeframe
        self.params = params
        self.state = SymbolEngineState()

    def load_state(self, state: SymbolEngineState) -> None:
        self.state = state

    def process_bar(self, bar: OHLCVBar) -> EngineOutput:
        st = self.state
        st.bars.append(bar)
        idx = len(st.bars) - 1
        signals: list[Signal] = []
        exits: list[TradeExit] = []

        atr = self._update_atr(idx)
        avg_range = self._update_avg_range(idx)
        self._confirm_pivots(idx)
        self._handle_structure_breaks(idx)

        if st.trade.active:
            exit_event = self._process_trade_exits(idx)
            if exit_event:
                exits.append(exit_event)

        long_signal = self._process_bull_setup(idx, atr, avg_range)
        if long_signal is not None:
            signals.append(long_signal)

        short_signal = self._process_bear_setup(idx, atr, avg_range)
        if short_signal is not None:
            signals.append(short_signal)

        return EngineOutput(signals=signals, exits=exits)

    def _update_atr(self, idx: int) -> float | None:
        st = self.state
        bar = st.bars[idx]
        prev_close = st.bars[idx - 1].close if idx > 0 else bar.close
        tr = max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))
        st.tr_values.append(tr)
        if len(st.tr_values) < self.params.atr_length:
            return None
        if st.prev_atr is None:
            st.prev_atr = sum(st.tr_values[-self.params.atr_length :]) / self.params.atr_length
            return st.prev_atr
        st.prev_atr = st.prev_atr + ((tr - st.prev_atr) / self.params.atr_length)
        return st.prev_atr

    def _update_avg_range(self, idx: int) -> float | None:
        st = self.state
        bar = st.bars[idx]
        st.range_values.append(bar.high - bar.low)
        if len(st.range_values) < self.params.strength_lookback:
            return None
        return sum(st.range_values[-self.params.strength_lookback :]) / self.params.strength_lookback

    def _confirm_pivots(self, idx: int) -> None:
        st = self.state
        s = self.params.swing_length
        pivot_idx = idx - s
        if pivot_idx < s:
            return
        window = st.bars[pivot_idx - s : pivot_idx + s + 1]
        pivot = st.bars[pivot_idx]
        highs = [b.high for b in window]
        lows = [b.low for b in window]
        center = s
        if highs[center] == max(highs) and all(highs[center] > value for i, value in enumerate(highs) if i != center):
            st.latest_swing_high = PivotLevel(index=pivot_idx, timestamp=pivot.timestamp, price=pivot.high)
        if lows[center] == min(lows) and all(lows[center] < value for i, value in enumerate(lows) if i != center):
            st.latest_swing_low = PivotLevel(index=pivot_idx, timestamp=pivot.timestamp, price=pivot.low)

    def _handle_structure_breaks(self, idx: int) -> None:
        st = self.state
        if idx == 0:
            return
        curr = st.bars[idx]
        prev = st.bars[idx - 1]
        swing_high = st.latest_swing_high
        if swing_high and not swing_high.broken:
            if curr.close > swing_high.price and prev.close <= swing_high.price:
                st.pending_bull = PendingSetup(
                    direction=SignalType.LONG,
                    broken_level=swing_high.price,
                    break_index=idx,
                    break_timestamp=curr.timestamp,
                )
                swing_high.broken = True
        swing_low = st.latest_swing_low
        if swing_low and not swing_low.broken:
            if curr.close < swing_low.price and prev.close >= swing_low.price:
                st.pending_bear = PendingSetup(
                    direction=SignalType.SHORT,
                    broken_level=swing_low.price,
                    break_index=idx,
                    break_timestamp=curr.timestamp,
                )
                swing_low.broken = True

    def _process_bull_setup(self, idx: int, atr: float | None, avg_range: float | None) -> Signal | None:
        st = self.state
        setup = st.pending_bull
        if setup is None or atr is None or avg_range is None:
            return None
        bar = st.bars[idx]
        if idx - setup.break_index > self.params.retest_window:
            st.pending_bull = None
            return None
        if bar.close < setup.broken_level - (atr * self.params.failure_buffer_atr):
            st.pending_bull = None
            return None
        if idx > setup.break_index and setup.retest_index is None and bar.low <= setup.broken_level:
            setup.retest_index = idx
            setup.retest_timestamp = bar.timestamp
            setup.lowest_retest_low = bar.low
            return None
        if setup.retest_index is not None:
            setup.lowest_retest_low = (
                bar.low
                if setup.lowest_retest_low is None
                else min(setup.lowest_retest_low, bar.low)
            )
            if idx <= setup.retest_index:
                return None
            candle_range = bar.high - bar.low
            if candle_range <= 0:
                return None
            body = abs(bar.close - bar.open)
            if (
                bar.close > setup.broken_level
                and bar.close > bar.open
                and (body / candle_range) >= self.params.body_ratio_minimum
                and candle_range >= avg_range * self.params.range_multiplier
                and not st.trade.active
            ):
                entry = bar.close
                stop = (setup.lowest_retest_low or bar.low) - atr * self.params.stop_buffer_atr
                risk = entry - stop
                if risk <= 0:
                    st.pending_bull = None
                    return None
                target = entry + risk * self.params.target_risk_multiple
                signal = Signal(
                    symbol=self.symbol,
                    exchange=self.exchange,
                    timeframe=self.timeframe,
                    signal_type=SignalType.LONG,
                    signal_timestamp=bar.timestamp,
                    entry_price=entry,
                    stop_price=stop,
                    invalidation_price=setup.broken_level,
                    target_price=target,
                    risk_per_share=risk,
                    broken_structure_level=setup.broken_level,
                    retest_timestamp=setup.retest_timestamp or bar.timestamp,
                    confirmation_timestamp=bar.timestamp,
                    latest_confirmed_swing_high=st.latest_swing_high.price if st.latest_swing_high else None,
                    latest_confirmed_swing_low=st.latest_swing_low.price if st.latest_swing_low else None,
                    reason="Bullish break, retest, and confirmation candle validated",
                )
                st.trade.active = True
                st.trade.entry_price = entry
                st.trade.stop_price = stop
                st.trade.target_price = target
                st.trade.invalidation_price = setup.broken_level
                st.trade.broken_level = setup.broken_level
                st.trade.opened_at = bar.timestamp
                st.trade.structural_exit_level = st.latest_swing_low.price if st.latest_swing_low else None
                st.pending_bull = None
                return signal
        return None

    def _process_bear_setup(self, idx: int, atr: float | None, avg_range: float | None) -> Signal | None:
        st = self.state
        setup = st.pending_bear
        if setup is None or atr is None or avg_range is None:
            return None
        bar = st.bars[idx]
        if idx - setup.break_index > self.params.retest_window:
            st.pending_bear = None
            return None
        if bar.close > setup.broken_level + (atr * self.params.failure_buffer_atr):
            st.pending_bear = None
            return None
        if idx > setup.break_index and setup.retest_index is None and bar.high >= setup.broken_level:
            setup.retest_index = idx
            setup.retest_timestamp = bar.timestamp
            setup.highest_retest_high = bar.high
            return None
        if setup.retest_index is not None:
            setup.highest_retest_high = (
                bar.high
                if setup.highest_retest_high is None
                else max(setup.highest_retest_high, bar.high)
            )
            if idx <= setup.retest_index:
                return None
            candle_range = bar.high - bar.low
            if candle_range <= 0:
                return None
            body = abs(bar.close - bar.open)
            if (
                bar.close < setup.broken_level
                and bar.close < bar.open
                and (body / candle_range) >= self.params.body_ratio_minimum
                and candle_range >= avg_range * self.params.range_multiplier
            ):
                signal = Signal(
                    symbol=self.symbol,
                    exchange=self.exchange,
                    timeframe=self.timeframe,
                    signal_type=SignalType.SHORT,
                    signal_timestamp=bar.timestamp,
                    entry_price=bar.close,
                    stop_price=(setup.highest_retest_high or bar.high) + atr * self.params.stop_buffer_atr,
                    invalidation_price=setup.broken_level,
                    target_price=bar.close,
                    risk_per_share=0,
                    broken_structure_level=setup.broken_level,
                    retest_timestamp=setup.retest_timestamp or bar.timestamp,
                    confirmation_timestamp=bar.timestamp,
                    latest_confirmed_swing_high=st.latest_swing_high.price if st.latest_swing_high else None,
                    latest_confirmed_swing_low=st.latest_swing_low.price if st.latest_swing_low else None,
                    reason="Bearish break, retest, and confirmation candle validated",
                )
                st.pending_bear = None
                return signal
        return None

    def _process_trade_exits(self, idx: int) -> TradeExit | None:
        st = self.state
        bar = st.bars[idx]
        if not st.trade.active:
            return None
        if st.trade.stop_price is not None and bar.low <= st.trade.stop_price:
            reason = "Stop loss hit"
            exit_type = ExitType.STOP
        elif st.trade.broken_level is not None and bar.close < st.trade.broken_level:
            reason = "Structure invalidation close below broken level"
            exit_type = ExitType.STRUCTURE_INVALIDATION
        elif st.trade.target_price is not None and bar.high >= st.trade.target_price:
            reason = "Profit target hit"
            exit_type = ExitType.TARGET
        elif st.trade.structural_exit_level is not None and bar.close < st.trade.structural_exit_level:
            reason = "Structural exit close below latest confirmed swing low"
            exit_type = ExitType.STRUCTURAL_EXIT
        else:
            return None

        st.trade = st.trade.__class__()
        return TradeExit(
            symbol=self.symbol,
            timeframe=self.timeframe,
            exit_type=exit_type,
            timestamp=bar.timestamp,
            reason=reason,
        )
