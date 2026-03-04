import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap

from constants import (
    COLOR_GREEN, COLOR_RED, COLOR_BLUE, COLOR_ORANGE, COLOR_GRAY, COLOR_DARK
)


def _get_dates(hist):
    return hist.index.tz_localize(None) if hist.index.tzinfo else hist.index


def _auto_date_axis(ax):
    """Apply an adaptive date locator/formatter that avoids label overlap."""
    locator = mdates.AutoDateLocator(minticks=4, maxticks=9)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))


def plot_price(ax, hist, symbol, period, log_scale=False, earnings_info=None, analyst_target=None, ma_windows=None):
    dates = _get_dates(hist)

    roll_ret = hist["Close"] / hist["Close"].shift(21) - 1
    x = mdates.date2num(dates.to_pydatetime())
    y = hist["Close"].values
    pts  = np.array([x, y]).T.reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    seg_colors = [COLOR_GREEN if v >= 0 else COLOR_RED for v in roll_ret.values[1:]]
    lc = LineCollection(segs, colors=seg_colors, linewidth=1.5)
    ax.add_collection(lc)

    ax.fill_between(dates, hist["Close"], alpha=0.08, color=COLOR_GRAY)
    ax.set_xlim(x[0], x[-1])
    ax.set_yscale("log" if log_scale else "linear")
    ax.set_ylim(bottom=hist["Close"].min() * 0.95)
    ax.set_ylabel("Price (USD, log)" if log_scale else "Price (USD)")
    current_price = hist["Close"].iloc[-1]
    ax.set_title(f"{symbol}  ${current_price:.2f}  ({period}) — Close Price & Volume")
    ax.grid(True, linestyle="--", alpha=0.4)
    plt.setp(ax.get_xticklabels(), visible=False)

    # Analyst price target band
    if analyst_target:
        mean = analyst_target.get("mean")
        low  = analyst_target.get("low")
        high = analyst_target.get("high")
        if mean:
            ax.axhline(mean, color=COLOR_BLUE, linewidth=0.9, linestyle="--", alpha=0.8,
                       label=f"Target ${mean:.2f}")
            if low and high:
                ax.axhspan(low, high, alpha=0.06, color=COLOR_BLUE)

    # Moving averages
    _MA_COLORS = {50: COLOR_ORANGE, 200: COLOR_BLUE}
    if ma_windows:
        for w in ma_windows:
            ma = hist["Close"].rolling(w).mean()
            ax.plot(dates, ma, color=_MA_COLORS.get(w, COLOR_GRAY),
                    linewidth=1.0, linestyle="--", label=f"MA{w}", alpha=0.85)

    # Earnings markers — line color shows EPS beat (green) / miss (red) / unknown (gray)
    if earnings_info:
        hist_date_arr = np.array([d.date() for d in hist.index.to_pydatetime()])
        closes = hist["Close"].values
        for ed, info in earnings_info.items():
            pos = np.searchsorted(hist_date_arr, ed)
            if 0 < pos < len(closes):
                move     = closes[pos] / closes[pos - 1] - 1
                surprise = info.get("surprise_pct")
                line_clr = (COLOR_GREEN if surprise > 0 else COLOR_RED) if surprise is not None else COLOR_DARK
                ax.axvline(x[pos], color=line_clr, linewidth=0.8, linestyle=":", alpha=0.7)
                clr = COLOR_GREEN if move >= 0 else COLOR_RED
                ax.text(x[pos], 0.97, f"{move:+.1%}",
                        transform=ax.get_xaxis_transform(),
                        fontsize=6, color=clr, rotation=90, va="top", ha="center")

    # Consolidated legend (analyst target + MAs)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels, fontsize=7, loc="upper left")


def plot_scatter(ax, hist, bench_hist, symbol, bench_name):
    stock_ret = hist["Close"].pct_change().dropna()
    bench_ret = bench_hist["Close"].pct_change().dropna()
    s, b = stock_ret.align(bench_ret, join="inner")

    ax.scatter(b.values, s.values, alpha=0.4, s=8, color=COLOR_BLUE)

    # OLS regression line (slope = beta)
    m, c = np.polyfit(b.values, s.values, 1)
    x_line = np.linspace(b.min(), b.max(), 100)
    ax.plot(x_line, m * x_line + c, color=COLOR_RED, linewidth=1.2, label=f"β = {m:.2f}")

    # Zero reference lines
    ax.axhline(0, color="#aaaaaa", linewidth=0.5, linestyle="--")
    ax.axvline(0, color="#aaaaaa", linewidth=0.5, linestyle="--")

    pct_fmt = mticker.FuncFormatter(lambda v, _: f"{v:.1%}")
    ax.xaxis.set_major_formatter(pct_fmt)
    ax.yaxis.set_major_formatter(pct_fmt)
    ax.set_xlabel(f"{bench_name} Daily Return")
    ax.set_ylabel(f"{symbol} Daily Return")
    ax.set_title(f"{symbol} vs {bench_name}")
    ax.legend(fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.4)


def plot_drawdown(ax, hist, symbol):
    close = hist["Close"]
    drawdown = (close - close.cummax()) / close.cummax()
    dates = _get_dates(hist)
    ax.fill_between(dates, drawdown.values, 0, alpha=0.35, color=COLOR_RED)
    ax.plot(dates, drawdown.values, color=COLOR_RED, linewidth=0.8)
    ax.axhline(0, color="#aaaaaa", linewidth=0.5)
    ax.set_ylabel("Drawdown")
    ax.set_title(f"{symbol} — Drawdown from Peak")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0%}"))
    _auto_date_axis(ax)
    ax.grid(True, linestyle="--", alpha=0.4)


def plot_rolling_beta(ax, hist, bench_hist, symbol, bench_name, window=63):
    stock_ret = hist["Close"].pct_change()
    bench_ret = bench_hist["Close"].pct_change()
    s, b = stock_ret.align(bench_ret, join="inner")
    rolling_beta = (s.rolling(window).cov(b) / b.rolling(window).var()).dropna()
    dates = rolling_beta.index.tz_localize(None) if rolling_beta.index.tzinfo else rolling_beta.index

    x = mdates.date2num(dates.to_pydatetime())
    y = rolling_beta.values
    pts  = np.array([x, y]).T.reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    lc = LineCollection(segs, colors=[COLOR_GREEN if v >= 0 else COLOR_RED for v in y[1:]], linewidth=1.2)
    ax.add_collection(lc)
    ax.set_xlim(x[0], x[-1])
    y_pad = max((y.max() - y.min()) * 0.05, 0.1)
    ax.set_ylim(y.min() - y_pad, y.max() + y_pad)

    ax.axhline(1, color=COLOR_GRAY, linewidth=0.8, linestyle="--", label="β = 1")
    ax.axhline(0, color="#aaaaaa", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Beta")
    ax.set_title(f"{symbol} — {window}d Rolling Beta vs {bench_name}")
    ax.legend(fontsize=8)
    _auto_date_axis(ax)
    ax.grid(True, linestyle="--", alpha=0.4)


def plot_rolling_sharpe(ax, hist, symbol, window=63):
    returns = hist["Close"].pct_change()
    rolling_sharpe = (
        returns.rolling(window).mean() / returns.rolling(window).std() * np.sqrt(252)
    ).dropna()
    dates = rolling_sharpe.index.tz_localize(None) if rolling_sharpe.index.tzinfo else rolling_sharpe.index

    x = mdates.date2num(dates.to_pydatetime())
    y = rolling_sharpe.values
    pts  = np.array([x, y]).T.reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    lc = LineCollection(segs, colors=[COLOR_GREEN if v >= 0 else COLOR_RED for v in y[1:]], linewidth=1.2)
    ax.add_collection(lc)
    ax.set_xlim(x[0], x[-1])
    y_pad = max((y.max() - y.min()) * 0.05, 0.1)
    ax.set_ylim(y.min() - y_pad, y.max() + y_pad)

    ax.axhline(1, color=COLOR_GRAY, linewidth=0.8, linestyle="--", label="Sharpe = 1")
    ax.axhline(0, color="#aaaaaa", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Sharpe Ratio")
    ax.set_title(f"{symbol} — {window}d Rolling Sharpe")
    ax.legend(fontsize=8)
    _auto_date_axis(ax)
    ax.grid(True, linestyle="--", alpha=0.4)


def plot_monthly_heatmap(ax, hist, symbol):
    MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_ret = hist["Close"].resample("ME").last().pct_change().dropna()
    years = sorted(monthly_ret.index.year.unique())
    data = np.full((len(years), 12), np.nan)
    for dt, val in monthly_ret.items():
        data[years.index(dt.year), dt.month - 1] = val

    cmap = LinearSegmentedColormap.from_list("rg", [COLOR_RED, "white", COLOR_GREEN])
    vmax = np.nanmax(np.abs(data))
    ax.imshow(data, cmap=cmap, aspect="auto", vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(12))
    ax.set_xticklabels(MONTH_LABELS, fontsize=8)
    ax.set_yticks(range(len(years)))
    ax.set_yticklabels(years, fontsize=8)
    ax.set_xticks(np.arange(-0.5, 12, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(years), 1), minor=True)
    ax.grid(which="minor", color="black", linewidth=0.5)
    ax.tick_params(which="minor", bottom=False, left=False)
    for i in range(len(years)):
        for j in range(12):
            val = data[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.1%}", ha="center", va="center", fontsize=7, fontweight="bold")
    ax.set_title(f"{symbol} — Monthly Returns")


def plot_volume(ax, hist, figure):
    dates = _get_dates(hist)

    dollar_vol = hist["Volume"] * hist["Close"]
    med_vol = dollar_vol.median()
    vol_colors = [COLOR_BLUE if v >= med_vol else COLOR_ORANGE for v in dollar_vol]
    ax.bar(dates, dollar_vol, color=vol_colors, width=1.5)
    ax.axhline(med_vol, color=COLOR_DARK, linewidth=0.8, linestyle="--")
    max_val = dollar_vol.max()
    ax.set_ylim(0, max_val * 1.10)
    if max_val >= 1e9:
        scale, suffix = 1e9, "B"
    elif max_val >= 1e6:
        scale, suffix = 1e6, "M"
    else:
        scale, suffix = 1e5, "00K"
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _, s=scale, sfx=suffix: f"${v/s:.0f}{sfx}"))
    ax.set_ylabel("Dollar Volume")
    ax.grid(True, linestyle="--", alpha=0.4)
    _auto_date_axis(ax)
    figure.autofmt_xdate(rotation=30, ha="right")


def plot_volatility_cone(ax, hist, symbol, atm_iv=None):
    WINDOWS = [10, 21, 63, 126, 252]
    returns = hist["Close"].pct_change().dropna()

    pct_25, pct_50, pct_75, current_rv = [], [], [], []
    for w in WINDOWS:
        if len(returns) < w:
            pct_25.append(np.nan)
            pct_50.append(np.nan)
            pct_75.append(np.nan)
            current_rv.append(np.nan)
            continue
        rv_series = returns.rolling(w).std().dropna() * np.sqrt(252)
        pct_25.append(float(np.nanpercentile(rv_series, 25)))
        pct_50.append(float(np.nanpercentile(rv_series, 50)))
        pct_75.append(float(np.nanpercentile(rv_series, 75)))
        current_rv.append(float(rv_series.iloc[-1]))

    ax.fill_between(WINDOWS, pct_25, pct_75, alpha=0.18, color=COLOR_BLUE, label="IQR (25–75th pctl)")
    ax.plot(WINDOWS, pct_50, color=COLOR_BLUE, linewidth=1.5, linestyle="--", label="Median RV")
    ax.plot(WINDOWS, current_rv, color=COLOR_ORANGE, linewidth=1.5,
            marker="o", markersize=5, label="Current RV")

    if atm_iv is not None:
        ax.axhline(atm_iv, color=COLOR_RED, linewidth=1.0, linestyle=":",
                   alpha=0.9, label=f"ATM IV {atm_iv:.1%}")

    ax.set_xticks(WINDOWS)
    ax.set_xticklabels([f"{w}d" for w in WINDOWS])
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_xlabel("Lookback Window")
    ax.set_ylabel("Annualized Volatility")
    ax.set_title(f"{symbol} — Volatility Cone")
    ax.legend(fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.4)