# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Equity analysis desktop app built with Python/tkinter. Fetches stock data via yfinance and displays a summary, return metrics, and a price/volume chart in a single-window GUI.

## Environment

- IDE: PyCharm
- Interpreter: `C:\Users\wamfo\anaconda3\envs\Finance` (Python 3.13, Anaconda)
- Key packages: `pandas==2.2.3`, `numpy`, `yfinance`, `matplotlib`
  - pandas is pinned to 2.2.x — do NOT upgrade to 3.x (breaks PyCharm's DataFrame debugger)

## Running

```bash
python main.py
```

No CLI arguments. The app launches a tkinter window directly.

## Architecture

| File | Responsibility |
|------|---------------|
| `main.py` | Entry point only (4 lines) |
| `app.py` | `App(tk.Tk)` class + `_TextRedirector` |
| `chart.py` | `plot_price()`, `plot_volume()` — pure matplotlib functions |
| `metrics.py` | `compute_metrics()` — pure analytics |
| `data.py` | `fetch_stock_data()`, `fetch_benchmark()` — yfinance calls |
| `constants.py` | `BENCH_TICKERS`, `PERIODS`, `INTERVALS`, chart color constants |

`data.py` and `metrics.py` have no tkinter/matplotlib imports and are independently usable (e.g. in notebooks).

### UI layout (`App(tk.Tk)`)

```
┌─ top bar ─────────────────────────────────────────────────────────┐
│ Symbol | Period | Interval | Benchmark | Run | Log Scale          │
├─ main_split (horizontal PanedWindow, 65% / 35%) ──────────────────┤
│  ┌─ left: outer (vertical PanedWindow) ───┐  ┌─ scatter pane ───┐ │
│  │ top_row: output  │ metrics             │  │ daily returns    │ │
│  │ fundamentals bar (P/E, dividend yield) │  │ scatter vs bench │ │
│  │ chart: ax_price (price line)           │  └──────────────────┘ │
│  │        ax_vol   (volume bars)          │                       │
│  └────────────────────────────────────────┘                       │
└───────────────────────────────────────────────────────────────────┘
```

**Metrics pane** default width = half the window width, set via `sash_place()` on `<Map>` with a `nonlocal` one-shot flag. Do not use `unbind(seq, funcid)` on Python 3.13 — throws `TclError` because `<Map>` fires once per child widget.

- `_run()` — clears output, reads controls, spawns a daemon thread calling `_fetch()`
- `_fetch()` — unpacks `hist, fundamentals = fetch_stock_data(...)`, fetches benchmark, then schedules `_plot()`, `_update_metrics()`, `_plot_scatter()`, and `_update_fundamentals()` via `self.after(0, ...)`
- `_plot()` — saves args to `self._last_plot`; reads `self.log_var` to set `ax_price` y-scale
- `_toggle_log()` — re-calls `_plot(*self._last_plot)` if data exists; no re-fetch needed
- `_TextRedirector` — redirects `sys.stdout` to the ScrolledText output pane (thread-safe via `widget.after`)

### Metrics panel

| Metric | Formula |
|--------|---------|
| Annualized Volatility | `std(daily returns) × √252` |
| Cumulative Return | `last / first − 1` |
| Annualized Return (CAGR) | `(1 + cum)^(252/n) − 1` |
| Sharpe Ratio | `mean(r) / std(r) × √252` (rf = 0) |
| Max Drawdown | `min((close − rolling_max) / rolling_max)` — displayed red |
| Beta | `Cov(stock, bench) / Var(bench)` — inner-aligned on dates |
| Correlation | `np.corrcoef(stock_r, bench_r)[0,1]` |
| R-Squared | `corr²` |

Benchmark dropdown options: S&P 500 (`^GSPC`), NASDAQ 100 (`^NDX`), Dow Jones (`^DJI`), Russell 2000 (`^RUT`).

Metrics rows use `pady=1` (no visible gap between rows). Rows are split into two groups — `return_rows` and `bench_rows` — rendered by a shared `_add_rows(rows, start)` helper. A `ttk.Separator` and "vs Benchmark" sub-header are inserted between the two groups. Each row tuple is `(key, label, fg)` — `fg=None` defaults to black, `fg="red"` used for Max Drawdown.

### Fundamentals bar

Compact horizontal pane (`stretch="never"`) between `top_row` and `chart_frame` in the `outer` vertical PanedWindow. Displays three label/value pairs side by side: **Trailing P/E**, **Forward P/E**, **Dividend Yield**.

`fetch_stock_data()` now returns `(hist, fundamentals)` — a tuple. On empty data returns `(None, {})`. The `fundamentals` dict keys are `trailingPE`, `forwardPE`, `dividendYield` (from `stock.info`).

**yfinance quirk (v1.2.0):** `dividendYield` is returned already as a percentage value (e.g. `0.52` means 0.52%), so format with `f"{dy:.2f}%"` — do NOT use `:.2%` which would multiply by 100 again.