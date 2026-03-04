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

    fundamentals = {
        "trailingPE":  info.get("trailingPE"),
        "forwardPE":   info.get("forwardPE"),
        "dividendYield": info.get("dividendYield"),
    }

    return hist, fundamentals


def fetch_benchmark(ticker: str, period: str = "1y", interval: str = "1d"):
    return yf.Ticker(ticker).history(period=period, interval=interval)