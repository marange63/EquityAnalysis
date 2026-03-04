import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.collections import LineCollection

from constants import (
    COLOR_GREEN, COLOR_RED, COLOR_BLUE, COLOR_ORANGE, COLOR_GRAY, COLOR_DARK
)


def _get_dates(hist):
    return hist.index.tz_localize(None) if hist.index.tzinfo else hist.index


def plot_price(ax, hist, symbol, period, log_scale=False):
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
    ax.set_title(f"{symbol} ({period}) — Close Price & Volume")
    ax.grid(True, linestyle="--", alpha=0.4)
    plt.setp(ax.get_xticklabels(), visible=False)


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
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.grid(True, linestyle="--", alpha=0.4)


def plot_rolling_beta(ax, hist, bench_hist, symbol, bench_name, window=21):
    stock_ret = hist["Close"].pct_change()
    bench_ret = bench_hist["Close"].pct_change()
    s, b = stock_ret.align(bench_ret, join="inner")
    rolling_beta = (s.rolling(window).cov(b) / b.rolling(window).var()).dropna()
    dates = rolling_beta.index.tz_localize(None) if rolling_beta.index.tzinfo else rolling_beta.index
    ax.plot(dates, rolling_beta.values, color=COLOR_BLUE, linewidth=1.2)
    ax.axhline(1, color=COLOR_GRAY, linewidth=0.8, linestyle="--", label="β = 1")
    ax.axhline(0, color="#aaaaaa", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Beta")
    ax.set_title(f"{symbol} — {window}d Rolling Beta vs {bench_name}")
    ax.legend(fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.grid(True, linestyle="--", alpha=0.4)


def plot_monthly_heatmap(ax, hist, symbol):
    MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_ret = hist["Close"].resample("ME").last().pct_change().dropna()
    years = sorted(monthly_ret.index.year.unique())
    data = np.full((len(years), 12), np.nan)
    for dt, val in monthly_ret.items():
        data[years.index(dt.year), dt.month - 1] = val

    vmax = np.nanmax(np.abs(data))
    ax.imshow(data, cmap="RdYlGn", aspect="auto", vmin=-vmax, vmax=vmax)
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

    med_vol = hist["Volume"].median()
    vol_colors = [COLOR_BLUE if v >= med_vol else COLOR_ORANGE for v in hist["Volume"]]
    ax.bar(dates, hist["Volume"], color=vol_colors, width=1.5)
    ax.axhline(med_vol, color=COLOR_DARK, linewidth=0.8, linestyle="--")
    ax.set_ylabel("Volume")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    figure.autofmt_xdate(rotation=30, ha="right")