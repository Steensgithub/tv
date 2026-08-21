"""
Confirmed bullish order-block construction.

Algorithm
---------
With pivotLeft=L and pivotRight=R, a pivot low at index ``p`` is confirmed
only after ``R`` bars have printed to its right, i.e., at bar index ``p + R``.

At confirmation time:
  - pivot_index  = current_index - R
  - zone bottom  = low[pivot_index]
  - zone top     = max(open[pivot_index], close[pivot_index])  if use_body
                   high[pivot_index]                           otherwise

A zone is ELIGIBLE for a LONG entry when the current candle's CLOSE is
strictly between zone_bottom and zone_top (inclusive of edges).

IMPORTANT: the Pine logic checks zone eligibility BEFORE removing first-touch
zones.  A candle that closes inside the zone both triggers a signal AND marks
the zone for removal.

A candle that only wicks into the zone (close outside) does NOT trigger a
signal but DOES remove the zone when remove_on_first_touch is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np


@dataclass
class BullishZone:
    bottom: float
    top: float
    pivot_timestamp: datetime
    confirmed_at_timestamp: datetime
    touched: bool = False
    active: bool = True


class OrderBlockTracker:
    """
    Maintains a list of active bullish zones and processes each confirmed bar.

    Parameters
    ----------
    left_bars, right_bars : pivot parameters
    use_body : if True, zone top = max(open, close); else zone top = high
    max_bullish_zones : max number of bullish zones to keep
    remove_on_first_touch : remove zone when candle wicks or closes into it
    remove_mitigated : remove zone when close fully passes through it
    """

    def __init__(
        self,
        left_bars: int = 5,
        right_bars: int = 5,
        use_body: bool = True,
        max_bullish_zones: int = 10,
        remove_on_first_touch: bool = True,
        remove_mitigated: bool = False,
    ) -> None:
        self.left_bars = left_bars
        self.right_bars = right_bars
        self.use_body = use_body
        self.max_bullish_zones = max_bullish_zones
        self.remove_on_first_touch = remove_on_first_touch
        self.remove_mitigated = remove_mitigated
        self.zones: list[BullishZone] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_bar(
        self,
        timestamps: np.ndarray,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        current_idx: int,
    ) -> Optional[BullishZone]:
        """
        Process bar at ``current_idx``.

        1. Check whether a pivot low is confirmed at this index.
        2. Update existing zones (touch / mitigation checks).
        3. Return the matched zone if the current close is inside one, or None.

        NOTE: eligibility is checked BEFORE removal to match Pine behaviour.
        """
        self._try_confirm_pivot(timestamps, opens, highs, lows, closes, current_idx)

        close = closes[current_idx]
        high = highs[current_idx]
        low = lows[current_idx]

        # --- Check eligibility BEFORE any removal ---
        matched: Optional[BullishZone] = None
        for zone in self.zones:
            if not zone.active:
                continue
            if zone.bottom <= close <= zone.top:
                matched = zone
                break  # return the first (oldest) matching zone

        # --- Now update zones based on wick or close interaction ---
        for zone in self.zones:
            if not zone.active:
                continue
            # Wick touch: low wicks into zone but close is outside
            wick_touch = low <= zone.top and close > zone.top
            close_touch = zone.bottom <= close <= zone.top
            mitigation = close < zone.bottom  # price closed below zone bottom

            if close_touch or wick_touch:
                zone.touched = True
                if self.remove_on_first_touch:
                    zone.active = False

            if self.remove_mitigated and mitigation:
                zone.active = False

        # Prune inactive zones
        self.zones = [z for z in self.zones if z.active]

        return matched

    def active_zones(self) -> list[BullishZone]:
        return [z for z in self.zones if z.active]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_pivot_low(
        self,
        lows: np.ndarray,
        idx: int,
    ) -> bool:
        """
        Return True if lows[idx] is a pivot low with ``left_bars`` bars to its
        left and ``right_bars`` bars to its right all having higher lows.
        """
        L = self.left_bars
        R = self.right_bars
        if idx - L < 0 or idx + R >= len(lows):
            return False
        pivot_low = lows[idx]
        left_ok = all(lows[idx - i] > pivot_low for i in range(1, L + 1))
        right_ok = all(lows[idx + i] > pivot_low for i in range(1, R + 1))
        return left_ok and right_ok

    def _try_confirm_pivot(
        self,
        timestamps: np.ndarray,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        current_idx: int,
    ) -> None:
        """
        A pivot low at (current_idx - right_bars) becomes confirmed NOW.
        Add it as a new zone if it qualifies.
        """
        R = self.right_bars
        pivot_idx = current_idx - R
        if pivot_idx < 0:
            return

        if not self._is_pivot_low(lows, pivot_idx):
            return

        # Build zone
        bottom = float(lows[pivot_idx])
        if self.use_body:
            top = float(max(opens[pivot_idx], closes[pivot_idx]))
        else:
            top = float(highs[pivot_idx])

        pivot_ts = timestamps[pivot_idx]
        confirmed_ts = timestamps[current_idx]

        # Avoid duplicate zones for the same pivot
        for existing in self.zones:
            if (
                abs(existing.bottom - bottom) < 1e-9
                and existing.pivot_timestamp == pivot_ts
            ):
                return

        zone = BullishZone(
            bottom=bottom,
            top=top,
            pivot_timestamp=pivot_ts,
            confirmed_at_timestamp=confirmed_ts,
        )
        self.zones.append(zone)

        # Enforce max zones (keep most recent)
        self.zones = sorted(self.zones, key=lambda z: z.pivot_timestamp)
        self.zones = self.zones[-self.max_bullish_zones :]
