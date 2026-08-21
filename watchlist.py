"""
Sector Rotation Watchlist Generator
Filters stocks with ADR% (Average Daily Range %) above 4%.
Outputs a dated CSV file and prints results to stdout.
"""

import sys
from datetime import date

import pandas as pd
import yfinance as yf

# Sector rotation universe — expand or modify as needed
UNIVERSE = {
    "XOM":  "Energy",
    "CVX":  "Energy",
    "FCX":  "Materials",
    "NEM":  "Materials",
    "NVDA": "Technology",
    "SMCI": "Technology",
    "AMD":  "Technology",
    "TSLA": "Consumer Discretionary",
    "RIVN": "Consumer Discretionary",
    "F":    "Consumer Discretionary",
    "UAL":  "Industrials",
    "DAL":  "Industrials",
    "AAL":  "Industrials",
    "BAC":  "Financials",
    "JPM":  "Financials",
    "MARA": "Financials",
    "COIN": "Financials",
}

ADR_THRESHOLD = 4.0   # percent
ADR_LOOKBACK  = 20    # trading days


def compute_adr(ticker: str, days: int = ADR_LOOKBACK) -> float | None:
    """Return the average daily range % over the last *days* trading sessions."""
    try:
        df = yf.download(
            ticker,
            period=f"{days + 10}d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if df.empty or len(df) < days:
            return None
        df["ADR"] = (df["High"] - df["Low"]) / df["Low"] * 100
        return round(float(df["ADR"].tail(days).mean()), 2)
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] {ticker}: {exc}", file=sys.stderr)
        return None


def build_watchlist() -> pd.DataFrame:
    rows = []
    for ticker, sector in UNIVERSE.items():
        print(f"  Fetching {ticker} …", flush=True)
        adr = compute_adr(ticker)
        if adr is not None and adr > ADR_THRESHOLD:
            rows.append({"Ticker": ticker, "Sector": sector, "ADR%": adr})

    df = pd.DataFrame(rows, columns=["Ticker", "Sector", "ADR%"])
    return df.sort_values("ADR%", ascending=False).reset_index(drop=True)


def main() -> None:
    today = date.today().isoformat()
    print(f"Building sector rotation watchlist (ADR% > {ADR_THRESHOLD}%) — {today}")

    watchlist = build_watchlist()

    if watchlist.empty:
        print("No stocks met the ADR% threshold today.")
        return

    output_file = f"watchlist_{today}.csv"
    watchlist.to_csv(output_file, index=False)
    print(f"\nSaved → {output_file}\n")
    print(watchlist.to_string(index=False))


if __name__ == "__main__":
    main()
