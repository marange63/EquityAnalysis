import math

import numpy as np
import yfinance as yf


def fetch_stock_data(ticker: str, period: str = "1y", interval: str = "1d"):
    stock = yf.Ticker(ticker)

    hist = stock.history(period=period, interval=interval)
    if hist.empty:
        print(f"No data found for ticker '{ticker}'")
        return None, {}

    info = stock.info

    print(f"\n{'='*50}")
    print(f"  {info.get('longName', ticker)} ({ticker.upper()})")
    print(f"{'='*50}")
    print(f"Sector:        {info.get('sector', 'N/A')}")
    print(f"Industry:      {info.get('industry', 'N/A')}")
    print(f"Market Cap:    ${info.get('marketCap', 0):,.0f}")
    print(f"52w High:      ${info.get('fiftyTwoWeekHigh', 0):.2f}")
    print(f"52w Low:       ${info.get('fiftyTwoWeekLow', 0):.2f}")
    print(f"Avg Volume:    {info.get('averageVolume', 0):,.0f}")

    current_price = float(hist["Close"].iloc[-1])

    # --- Earnings info (dates + EPS surprise) ---
    try:
        ed_df = stock.earnings_dates
        if ed_df is not None and not ed_df.empty:
            h_start = hist.index[0].date()
            h_end   = hist.index[-1].date()
            earnings_info = {}
            for idx_dt, row in ed_df.iterrows():
                dt = idx_dt.date() if hasattr(idx_dt, "date") else idx_dt
                if h_start <= dt <= h_end:
                    try:
                        v = float(row["Surprise(%)"])
                        surprise_val = v if not math.isnan(v) else None
                    except (KeyError, ValueError, TypeError):
                        surprise_val = None
                    earnings_info[dt] = {"surprise_pct": surprise_val}
            earnings_info = dict(sorted(earnings_info.items()))
        else:
            earnings_info = {}
    except Exception:
        earnings_info = {}

    # --- Options: ATM IV, IV/HV, Put/Call OI ratio ---
    hv = float(hist["Close"].pct_change().dropna().std() * np.sqrt(252))
    try:
        expiries = stock.options
        if expiries:
            chain       = stock.option_chain(expiries[0])
            calls, puts = chain.calls, chain.puts
            atm_call    = calls.iloc[(calls["strike"] - current_price).abs().argsort()[:1]]
            atm_put     = puts.iloc[(puts["strike"] - current_price).abs().argsort()[:1]]
            call_iv     = float(atm_call["impliedVolatility"].values[0]) if not atm_call.empty else None
            put_iv      = float(atm_put["impliedVolatility"].values[0])  if not atm_put.empty  else None
            if call_iv is not None and put_iv is not None:
                atm_iv = (call_iv + put_iv) / 2
            else:
                atm_iv = call_iv or put_iv
            total_call_oi = int(calls["openInterest"].fillna(0).sum())
            total_put_oi  = int(puts["openInterest"].fillna(0).sum())
            pc_ratio      = total_put_oi / total_call_oi if total_call_oi > 0 else None
            nearest_expiry = expiries[0]
        else:
            atm_iv = pc_ratio = nearest_expiry = None
    except Exception:
        atm_iv = pc_ratio = nearest_expiry = None

    fundamentals = {
        # Valuation
        "trailingPE":    info.get("trailingPE"),
        "forwardPE":     info.get("forwardPE"),
        "dividendYield": info.get("dividendYield"),
        # Price context
        "currentPrice":     current_price,
        "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
        "fiftyTwoWeekLow":  info.get("fiftyTwoWeekLow"),
        "periodHigh":       float(hist["Close"].max()),
        # Earnings
        "earnings_info": earnings_info,
        # Analyst targets
        "targetMeanPrice":         info.get("targetMeanPrice"),
        "targetHighPrice":         info.get("targetHighPrice"),
        "targetLowPrice":          info.get("targetLowPrice"),
        "numberOfAnalystOpinions": info.get("numberOfAnalystOpinions"),
        "recommendationKey":       info.get("recommendationKey"),
        # Options
        "atm_iv":         atm_iv,
        "iv_hv_ratio":    atm_iv / hv if (atm_iv and hv > 0) else None,
        "pc_oi_ratio":    pc_ratio,
        "nearest_expiry": nearest_expiry,
    }

    return hist, fundamentals


def fetch_benchmark(ticker: str, period: str = "1y", interval: str = "1d"):
    return yf.Ticker(ticker).history(period=period, interval=interval)
