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

    try:
        ed_df = stock.earnings_dates
        if ed_df is not None and not ed_df.empty:
            h_start = hist.index[0].date()
            h_end   = hist.index[-1].date()
            earnings_dates = sorted([
                d.date() for d in ed_df.index
                if h_start <= d.date() <= h_end
            ])
        else:
            earnings_dates = []
    except Exception:
        earnings_dates = []

    fundamentals = {
        "trailingPE":    info.get("trailingPE"),
        "forwardPE":     info.get("forwardPE"),
        "dividendYield": info.get("dividendYield"),
        "currentPrice":  current_price,
        "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
        "fiftyTwoWeekLow":  info.get("fiftyTwoWeekLow"),
        "periodHigh":    float(hist["Close"].max()),
        "earnings_dates": earnings_dates,
    }

    return hist, fundamentals


def fetch_benchmark(ticker: str, period: str = "1y", interval: str = "1d"):
    return yf.Ticker(ticker).history(period=period, interval=interval)