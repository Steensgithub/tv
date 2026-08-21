from __future__ import annotations

from datetime import UTC, datetime, timedelta

from config import PineParams
from models import ExitType, OHLCVBar, SignalType
from signal_engine import SignalEngine


def make_bar(symbol: str, i: int, o: float, h: float, l: float, c: float) -> OHLCVBar:
    return OHLCVBar(
        symbol=symbol,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=1000,
    )


def feed(engine: SignalEngine, bars: list[OHLCVBar]):
    outputs = []
    for bar in bars:
        outputs.append(engine.process_bar(bar))
    return outputs


def test_confirmed_pivot_timing() -> None:
    engine = SignalEngine("AAA", "NYSE", "1m", PineParams(swing_length=2))
    bars = [
        make_bar("AAA", 0, 10, 11, 9, 10),
        make_bar("AAA", 1, 10, 12, 9, 11),
        make_bar("AAA", 2, 11, 15, 10, 12),
        make_bar("AAA", 3, 12, 13, 10, 11),
        make_bar("AAA", 4, 11, 12, 9, 10),
    ]
    out = feed(engine, bars)
    assert engine.state.latest_swing_high is not None
    assert engine.state.latest_swing_high.index == 2
    assert out[3].signals == []


def test_bullish_structure_break_and_confirmation() -> None:
    params = PineParams(swing_length=2, strength_lookback=2, atr_length=2)
    engine = SignalEngine("AAA", "NYSE", "1m", params)
    bars = [
        make_bar("AAA", 0, 10, 11, 9, 10),
        make_bar("AAA", 1, 10, 12, 9.5, 11),
        make_bar("AAA", 2, 11, 13, 10, 12),
        make_bar("AAA", 3, 12, 12.5, 10.5, 11),
        make_bar("AAA", 4, 11, 11.5, 10.2, 10.8),
        make_bar("AAA", 5, 10.8, 13.5, 10.7, 13.2),
        make_bar("AAA", 6, 13.1, 13.3, 12.0, 12.8),
        make_bar("AAA", 7, 12.2, 13.8, 12.1, 13.6),
    ]
    outputs = feed(engine, bars)
    signals = [s for out in outputs for s in out.signals if s.signal_type == SignalType.LONG]
    assert len(signals) == 1
    signal = signals[0]
    assert signal.entry_price == bars[7].close
    assert signal.invalidation_price > 0
    assert signal.target_price > signal.entry_price


def test_bearish_structure_break_exists() -> None:
    params = PineParams(swing_length=2, strength_lookback=2, atr_length=2)
    engine = SignalEngine("AAA", "NYSE", "1m", params)
    bars = [
        make_bar("AAA", 0, 20, 21, 19, 20),
        make_bar("AAA", 1, 20, 20.5, 18, 19),
        make_bar("AAA", 2, 19, 19.5, 16, 17),
        make_bar("AAA", 3, 17, 18, 16.5, 17.5),
        make_bar("AAA", 4, 17.5, 18, 17, 17.6),
        make_bar("AAA", 5, 17.4, 17.6, 15.5, 15.8),
        make_bar("AAA", 6, 15.8, 16.3, 15.6, 16.1),
        make_bar("AAA", 7, 16.0, 16.1, 14.8, 15.0),
    ]
    outputs = feed(engine, bars)
    shorts = [s for out in outputs for s in out.signals if s.signal_type == SignalType.SHORT]
    assert len(shorts) == 1


def test_retest_window_expiration() -> None:
    params = PineParams(swing_length=2, retest_window=1, strength_lookback=2, atr_length=2)
    engine = SignalEngine("AAA", "NYSE", "1m", params)
    bars = [
        make_bar("AAA", 0, 10, 11, 9, 10),
        make_bar("AAA", 1, 10, 12, 9.5, 11),
        make_bar("AAA", 2, 11, 13, 10, 12),
        make_bar("AAA", 3, 12, 12.2, 11, 11.2),
        make_bar("AAA", 4, 11.2, 11.5, 10.7, 10.9),
        make_bar("AAA", 5, 10.9, 13.6, 10.8, 13.4),
        make_bar("AAA", 6, 13.4, 13.6, 13.2, 13.5),
        make_bar("AAA", 7, 13.5, 13.7, 13.3, 13.6),
    ]
    feed(engine, bars)
    assert engine.state.pending_bull is None


def test_failed_retest_cancellation() -> None:
    params = PineParams(swing_length=2, strength_lookback=2, atr_length=2, failure_buffer_atr=0.1)
    engine = SignalEngine("AAA", "NYSE", "1m", params)
    bars = [
        make_bar("AAA", 0, 10, 11, 9, 10),
        make_bar("AAA", 1, 10, 12, 9.5, 11),
        make_bar("AAA", 2, 11, 13, 10, 12),
        make_bar("AAA", 3, 12, 12.5, 11, 11.2),
        make_bar("AAA", 4, 11.1, 11.4, 10.5, 10.8),
        make_bar("AAA", 5, 10.8, 13.5, 10.7, 13.3),
        make_bar("AAA", 6, 13.2, 13.3, 10.0, 10.1),
    ]
    feed(engine, bars)
    assert engine.state.pending_bull is None


def test_confirmation_candle_filters() -> None:
    params = PineParams(swing_length=2, strength_lookback=2, atr_length=2, body_ratio_minimum=0.9)
    engine = SignalEngine("AAA", "NYSE", "1m", params)
    bars = [
        make_bar("AAA", 0, 10, 11, 9, 10),
        make_bar("AAA", 1, 10, 12, 9.5, 11),
        make_bar("AAA", 2, 11, 13, 10, 12),
        make_bar("AAA", 3, 12, 12.4, 11, 11.2),
        make_bar("AAA", 4, 11.2, 11.4, 10.7, 10.8),
        make_bar("AAA", 5, 10.8, 13.5, 10.7, 13.4),
        make_bar("AAA", 6, 13.2, 13.5, 12.0, 12.6),
        make_bar("AAA", 7, 12.6, 13.0, 12.2, 12.8),
    ]
    outputs = feed(engine, bars)
    assert not [s for out in outputs for s in out.signals]


def test_long_trade_exit_priority() -> None:
    params = PineParams(swing_length=2, strength_lookback=2, atr_length=2)
    engine = SignalEngine("AAA", "NYSE", "1m", params)
    bars = [
        make_bar("AAA", 0, 10, 11, 9, 10),
        make_bar("AAA", 1, 10, 12, 9.5, 11),
        make_bar("AAA", 2, 11, 13, 10, 12),
        make_bar("AAA", 3, 12, 12.4, 11, 11.2),
        make_bar("AAA", 4, 11.2, 11.4, 10.7, 10.8),
        make_bar("AAA", 5, 10.8, 13.5, 10.7, 13.4),
        make_bar("AAA", 6, 13.2, 13.5, 12.0, 12.8),
        make_bar("AAA", 7, 12.2, 13.9, 12.1, 13.7),
    ]
    feed(engine, bars)
    assert engine.state.trade.active
    exit_bar = make_bar("AAA", 8, 13.7, 20.0, 1.0, 0.5)
    output = engine.process_bar(exit_bar)
    assert output.exits
    assert output.exits[0].exit_type == ExitType.STOP


def test_long_levels_calculation() -> None:
    params = PineParams(swing_length=2, strength_lookback=2, atr_length=2, target_risk_multiple=2.0)
    engine = SignalEngine("AAA", "NYSE", "1m", params)
    bars = [
        make_bar("AAA", 0, 10, 11, 9, 10),
        make_bar("AAA", 1, 10, 12, 9.5, 11),
        make_bar("AAA", 2, 11, 13, 10, 12),
        make_bar("AAA", 3, 12, 12.4, 11, 11.2),
        make_bar("AAA", 4, 11.2, 11.4, 10.7, 10.8),
        make_bar("AAA", 5, 10.8, 13.5, 10.7, 13.4),
        make_bar("AAA", 6, 13.2, 13.5, 12.0, 12.8),
        make_bar("AAA", 7, 12.2, 13.9, 12.1, 13.7),
    ]
    outputs = feed(engine, bars)
    long_signal = [s for out in outputs for s in out.signals if s.signal_type == SignalType.LONG][0]
    assert long_signal.stop_price < long_signal.entry_price
    assert long_signal.target_price == long_signal.entry_price + long_signal.risk_per_share * 2.0
