import numpy as np


def compute_metrics(hist, bench_hist):
    close = hist["Close"]
    returns = close.pct_change().dropna()
    n = len(close)

    ann_vol        = returns.std() * np.sqrt(252)
    cum_return     = close.iloc[-1] / close.iloc[0] - 1
    ann_cum_return = (1 + cum_return) ** (252 / n) - 1
    sharpe         = (returns.mean() / returns.std()) * np.sqrt(252)
    rolling_max    = close.cummax()
    max_drawdown   = ((close - rolling_max) / rolling_max).min()

    downside       = returns[returns < 0]
    sortino        = (returns.mean() * 252) / (downside.std() * np.sqrt(252))
    calmar         = ann_cum_return / abs(max_drawdown) if max_drawdown != 0 else np.nan

    bench_returns = bench_hist["Close"].pct_change().dropna()
    aligned       = returns.align(bench_returns, join="inner")
    cov           = np.cov(aligned[0], aligned[1])
    beta          = cov[0, 1] / cov[1, 1]
    corr          = np.corrcoef(aligned[0], aligned[1])[0, 1]
    r_squared     = corr ** 2

    up_mask        = aligned[1] > 0
    down_mask      = aligned[1] < 0
    up_bench_mean  = aligned[1][up_mask].mean()
    down_bench_mean = aligned[1][down_mask].mean()
    up_capture     = aligned[0][up_mask].mean()  / up_bench_mean   if up_bench_mean   != 0 else np.nan
    down_capture   = aligned[0][down_mask].mean() / down_bench_mean if down_bench_mean != 0 else np.nan

    return (ann_vol, cum_return, ann_cum_return, sharpe, sortino, calmar,
            max_drawdown, beta, corr, r_squared, up_capture, down_capture)