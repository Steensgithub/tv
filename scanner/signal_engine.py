"""
Signal engine.

Evaluates all conditions for a LONG signal on each confirmed signal-timeframe
candle, using only confirmed HTF data.

All condition logic matches the Pine Script strategy described in the spec.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from .config import AppConfig
from .indicators import (
    pine_ema,
    pine_sma,
    pine_atr,
    window_cvd,
    ma_expansion_condition,
)
from .models import Candle, SignalRecord, BullishZone
from .order_blocks import BullishZone as OBZone, OrderBlockTracker
from .session import to_ny

log = logging.getLogger(__name__)


@dataclass
class HTFState:
    """Snapshot of the last confirmed HTF candle's MA values."""
    ema8: float = float("nan")
    ema21: float = float("nan")
    ema34: float = float("nan")
    sma50: float = float("nan")
    sma200: float = float("nan")
    atr14: float = float("nan")
    regime_bullish: bool = False
    bandwidth_atr: float = float("nan")
    candle_timestamp: Optional[datetime] = None


@dataclass
class BarArrays:
    timestamps: list[datetime] = field(default_factory=list)
    opens: list[float] = field(default_factory=list)
    highs: list[float] = field(default_factory=list)
    lows: list[float] = field(default_factory=list)
    closes: list[float] = field(default_factory=list)
    volumes: list[float] = field(default_factory=list)

    def append(self, candle: Candle) -> None:
        self.timestamps.append(candle.timestamp)
        self.opens.append(candle.open)
        self.highs.append(candle.high)
        self.lows.append(candle.low)
        self.closes.append(candle.close)
        self.volumes.append(candle.volume if candle.volume is not None else float("nan"))

    def as_arrays(self) -> tuple[np.ndarray, ...]:
        return (
            np.array(self.timestamps),
            np.array(self.opens),
            np.array(self.highs),
            np.array(self.lows),
            np.array(self.closes),
            np.array(self.volumes),
        )

    def __len__(self) -> int:
        return len(self.closes)


class SignalEngine:
    """
    Evaluates signal conditions for a single symbol.

    Usage
    -----
    engine = SignalEngine(symbol, config)
    engine.load_history(signal_bars, htf_bars)
    result = engine.evaluate(new_signal_bar, htf_state)
    """

    def __init__(self, symbol: str, config: AppConfig) -> None:
        self.symbol = symbol
        self.cfg = config
        self.bars = BarArrays()
        self.htf_state = HTFState()
        self.ob_tracker = OrderBlockTracker(
            left_bars=config.pivot.left_bars,
            right_bars=config.pivot.right_bars,
            use_body=config.filters.order_block_use_body,
            max_bullish_zones=config.order_blocks.max_bullish_zones,
            remove_on_first_touch=config.order_blocks.remove_on_first_touch,
            remove_mitigated=config.order_blocks.remove_mitigated,
        )
        self._last_signal_ts: Optional[datetime] = None
        self._last_long_condition: bool = False

    # ------------------------------------------------------------------
    # History loading
    # ------------------------------------------------------------------

    def load_history(
        self, signal_candles: list[Candle], htf_candles: list[Candle]
    ) -> None:
        """
        Seed the engine with historical bars for warmup.
        Only confirmed candles are accepted.
        """
        # Reset state
        self.bars = BarArrays()
        self.ob_tracker = OrderBlockTracker(
            left_bars=self.cfg.pivot.left_bars,
            right_bars=self.cfg.pivot.right_bars,
            use_body=self.cfg.filters.order_block_use_body,
            max_bullish_zones=self.cfg.order_blocks.max_bullish_zones,
            remove_on_first_touch=self.cfg.order_blocks.remove_on_first_touch,
            remove_mitigated=self.cfg.order_blocks.remove_mitigated,
        )

        for c in signal_candles:
            if not c.confirmed:
                continue
            self.bars.append(c)

        # Build order blocks from warmup bars
        self._replay_order_blocks()

        # Update HTF state from historical HTF bars
        if htf_candles:
            confirmed_htf = [c for c in htf_candles if c.confirmed]
            if confirmed_htf:
                self._update_htf_state(confirmed_htf)

    def _replay_order_blocks(self) -> None:
        """Replay order-block detection on all loaded history bars."""
        self.ob_tracker = OrderBlockTracker(
            left_bars=self.cfg.pivot.left_bars,
            right_bars=self.cfg.pivot.right_bars,
            use_body=self.cfg.filters.order_block_use_body,
            max_bullish_zones=self.cfg.order_blocks.max_bullish_zones,
            remove_on_first_touch=self.cfg.order_blocks.remove_on_first_touch,
            remove_mitigated=self.cfg.order_blocks.remove_mitigated,
        )
        ts, o, h, l, c, v = self.bars.as_arrays()
        for i in range(len(c)):
            self.ob_tracker.process_bar(ts, o, h, l, c, i)

    def _update_htf_state(self, htf_candles: list[Candle]) -> None:
        """Compute HTF indicators from the last confirmed HTF candle."""
        # Only use confirmed bars – never use the current incomplete HTF candle
        confirmed = [c for c in htf_candles if c.confirmed]
        if not confirmed:
            return
        n = len(confirmed)
        ml = self.cfg.indicators.ma_lengths
        atr_len = self.cfg.indicators.atr_length
        bw_min = self.cfg.filters.min_htf_ma_bandwidth_atr

        opens = np.array([c.open for c in confirmed])
        highs = np.array([c.high for c in confirmed])
        lows = np.array([c.low for c in confirmed])
        closes = np.array([c.close for c in confirmed])

        ema8 = pine_ema(closes, ml[0])
        ema21 = pine_ema(closes, ml[1])
        ema34 = pine_ema(closes, ml[2])
        sma50 = pine_sma(closes, ml[3])
        sma200 = pine_sma(closes, ml[4])
        atr14 = pine_atr(highs, lows, closes, atr_len)

        # Use the LAST value (most recently confirmed HTF bar)
        self.htf_state = HTFState(
            ema8=float(ema8[-1]),
            ema21=float(ema21[-1]),
            ema34=float(ema34[-1]),
            sma50=float(sma50[-1]),
            sma200=float(sma200[-1]),
            atr14=float(atr14[-1]),
            candle_timestamp=confirmed[-1].timestamp,
        )
        h = self.htf_state
        h.regime_bullish = (
            not any(np.isnan([h.ema8, h.ema21, h.ema34, h.sma50, h.sma200]))
            and h.ema8 > h.ema21
            and h.ema21 > h.ema34
            and h.ema34 > h.sma50
            and h.sma50 > h.sma200
        )
        if not np.isnan(h.atr14) and h.atr14 != 0:
            h.bandwidth_atr = abs(h.ema8 - h.sma50) / h.atr14
        else:
            h.bandwidth_atr = float("nan")

    # ------------------------------------------------------------------
    # Main evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        candle: Candle,
        htf_candles: Optional[list[Candle]] = None,
    ) -> Optional[SignalRecord]:
        """
        Evaluate the signal conditions for *candle*.

        *candle* must be a confirmed, closed signal-timeframe bar.
        *htf_candles* is the full list of confirmed HTF bars (if updated).

        Returns a SignalRecord if a NEW LONG signal is triggered, else None.
        """
        if not candle.confirmed:
            log.debug("%s: candle not confirmed, skipping", self.symbol)
            return None

        # Update HTF state with latest confirmed HTF bars if provided
        if htf_candles:
            self._update_htf_state(htf_candles)

        # Append new bar
        self.bars.append(candle)

        ts, opens, highs, lows, closes, volumes = self.bars.as_arrays()
        n = len(closes)
        idx = n - 1  # current bar index

        ml = self.cfg.indicators.ma_lengths
        atr_len = self.cfg.indicators.atr_length
        vol_len = self.cfg.indicators.volume_baseline_length
        filt = self.cfg.filters

        # Compute indicators
        ema8_arr = pine_ema(closes, ml[0])
        ema21_arr = pine_ema(closes, ml[1])
        ema34_arr = pine_ema(closes, ml[2])
        sma50_arr = pine_sma(closes, ml[3])
        sma200_arr = pine_sma(closes, ml[4])
        atr_arr = pine_atr(highs, lows, closes, atr_len)
        expansion_arr = ma_expansion_condition(ema21_arr, ema34_arr, sma50_arr, sma200_arr)
        vol_sma_arr = pine_sma(volumes, vol_len)

        cur = dict(
            ema8=float(ema8_arr[idx]),
            ema21=float(ema21_arr[idx]),
            ema34=float(ema34_arr[idx]),
            sma50=float(sma50_arr[idx]),
            sma200=float(sma200_arr[idx]),
            atr=float(atr_arr[idx]),
            expansion=bool(expansion_arr[idx]),
            vol_sma=float(vol_sma_arr[idx]),
            close=float(closes[idx]),
        )

        # Volume validity
        if np.isnan(volumes[idx]):
            log.warning("%s: volume unavailable – signal invalidated", self.symbol)
            return None

        # --- Condition checks ---

        reasons: list[str] = []

        # 1. MA expansion
        if not cur["expansion"]:
            reasons.append("NO_MA_EXPANSION")

        # 2. Bullish MA alignment (signal TF)
        ma_aligned = (
            not any(np.isnan([cur["ema8"], cur["ema21"], cur["ema34"], cur["sma50"]]))
            and cur["ema8"] > cur["ema21"]
            and cur["ema21"] > cur["ema34"]
            and cur["ema34"] > cur["sma50"]
        )
        if not ma_aligned:
            reasons.append("NO_MA_ALIGNMENT")

        # 3. MA ribbon distance
        ma_ribbon_dist = (
            abs(cur["ema8"] - cur["sma50"]) / abs(cur["sma50"]) * 100
            if cur["sma50"] != 0 and not np.isnan(cur["sma50"])
            else float("nan")
        )
        if np.isnan(ma_ribbon_dist) or ma_ribbon_dist < filt.min_ma_distance_pct:
            reasons.append("MA_DISTANCE_TOO_SMALL")

        # 4. CVD proxy
        cvd_window_size = self.cfg.pivot.right_bars + 1  # pivotRight + 1 = 6
        cvd_val = cvd_total = bull_ratio = bear_ratio = float("nan")
        if filt.cvd_alignment_filter:
            if n >= cvd_window_size:
                try:
                    cvd_val, cvd_total, bull_ratio, bear_ratio = window_cvd(
                        closes, opens, volumes, cvd_window_size
                    )
                    if not (cvd_val > 0 and bull_ratio > bear_ratio):
                        reasons.append("CVD_NOT_BULLISH")
                except ValueError as exc:
                    log.warning("%s: CVD error: %s", self.symbol, exc)
                    reasons.append("CVD_VOLUME_MISSING")
            else:
                reasons.append("CVD_INSUFFICIENT_DATA")
        else:
            cvd_val = cvd_total = bull_ratio = bear_ratio = 0.0

        # 5. Relative volume
        six_bar_avg = float(np.nan)
        rel_vol_ratio = float(np.nan)
        if filt.relative_volume_filter:
            if n >= cvd_window_size:
                window_vol = volumes[-cvd_window_size:]
                if not np.any(np.isnan(window_vol)):
                    six_bar_avg = float(window_vol.mean())
                    if not np.isnan(cur["vol_sma"]) and cur["vol_sma"] != 0:
                        rel_vol_ratio = six_bar_avg / cur["vol_sma"] * 100.0
                        if rel_vol_ratio < filt.min_entry_volume_ratio:
                            reasons.append("LOW_REL_VOLUME")
                    else:
                        reasons.append("VOL_BASELINE_MISSING")
                else:
                    reasons.append("VOLUME_MISSING")
        else:
            six_bar_avg = rel_vol_ratio = 0.0

        # 6. Price-side condition
        close = cur["close"]
        if filt.price_side_mode == "or":
            price_ok = (
                (not np.isnan(cur["sma50"]) and close > cur["sma50"])
                or (not np.isnan(cur["sma200"]) and close > cur["sma200"])
            )
        else:  # "and"
            price_ok = (
                not any(np.isnan([cur["sma50"], cur["sma200"]]))
                and close > cur["sma50"]
                and close > cur["sma200"]
            )
        if not price_ok:
            reasons.append("PRICE_BELOW_MA")

        # 7. Extension filter
        ext_ok = True
        if not np.isnan(cur["atr"]) and cur["atr"] != 0 and not np.isnan(cur["sma50"]):
            ext = abs(close - cur["sma50"]) / cur["atr"]
            if ext > filt.max_entry_extension_atr:
                ext_ok = False
                reasons.append(f"EXTENSION_TOO_FAR({ext:.2f}ATR)")

        # 8. HTF regime
        htf = self.htf_state
        if not htf.regime_bullish:
            reasons.append("HTF_NOT_BULLISH")
        if np.isnan(htf.bandwidth_atr) or htf.bandwidth_atr < filt.min_htf_ma_bandwidth_atr:
            reasons.append("HTF_BANDWIDTH_TOO_NARROW")

        # 9. Order-block filter
        matched_zone: Optional[OBZone] = self.ob_tracker.process_bar(
            ts, opens, highs, lows, closes, idx
        )
        if filt.order_block_filter and matched_zone is None:
            reasons.append("NO_OB_MATCH")

        # --- Long condition ---
        long_condition = len(reasons) == 0
        new_long_signal = long_condition and not self._last_long_condition

        prev_long = self._last_long_condition
        self._last_long_condition = long_condition

        cfg_signal = self.cfg.signal
        if cfg_signal.alert_mode == "new_signal" and not new_long_signal:
            return None
        if cfg_signal.alert_mode == "per_candle" and not long_condition:
            return None

        if not long_condition:
            return None

        # Deduplication: avoid re-alerting the same candle
        if (
            self._last_signal_ts is not None
            and candle.timestamp == self._last_signal_ts
        ):
            return None

        self._last_signal_ts = candle.timestamp

        # Build record
        atr_v = cur["atr"] if not np.isnan(cur["atr"]) else 0.0
        ny_ts = to_ny(candle.timestamp)
        reason_str = "LONG_SIGNAL" if not reasons else "; ".join(reasons)

        ob_bottom = matched_zone.bottom if matched_zone else None
        ob_top = matched_zone.top if matched_zone else None

        return SignalRecord(
            symbol=self.symbol,
            signal_timestamp_utc=candle.timestamp,
            signal_timestamp_ny=ny_ts.isoformat(),
            signal_timeframe=self.cfg.scanner.signal_timeframe,
            htf_timeframe=self.cfg.scanner.htf_timeframe,
            close_price=close,
            ema_8=cur["ema8"],
            ema_21=cur["ema21"],
            ema_34=cur["ema34"],
            sma_50=cur["sma50"],
            sma_200=cur["sma200"] if not np.isnan(cur["sma200"]) else float("nan"),
            htf_regime="bullish" if htf.regime_bullish else "not_bullish",
            htf_bandwidth_atr=htf.bandwidth_atr if not np.isnan(htf.bandwidth_atr) else 0.0,
            ma_expansion=cur["expansion"],
            ma_ribbon_distance_pct=ma_ribbon_dist if not np.isnan(ma_ribbon_dist) else 0.0,
            cvd_window=cvd_val if not np.isnan(cvd_val) else 0.0,
            bullish_cvd_ratio=bull_ratio if not np.isnan(bull_ratio) else 0.0,
            six_bar_avg_volume=six_bar_avg if not np.isnan(six_bar_avg) else 0.0,
            relative_volume_ratio=rel_vol_ratio if not np.isnan(rel_vol_ratio) else 0.0,
            order_block_bottom=ob_bottom,
            order_block_top=ob_top,
            atr=atr_v,
            initial_stop=close - 1.5 * atr_v,
            tp1=close + 1.0 * atr_v,
            tp2=close + 2.0 * atr_v,
            signal_reason="LONG_SIGNAL",
            bar_confirmed=True,
        )
