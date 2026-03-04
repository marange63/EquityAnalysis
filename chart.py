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