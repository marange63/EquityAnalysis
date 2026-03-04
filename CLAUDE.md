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
| `app.py` | `App(tk.Tk)`, `ComparisonWindow(tk.Toplevel)`, `_TextRedirector`, `_Tooltip` |
| `chart.py` | `plot_price()`, `plot_volume()`, `plot_scatter()`, `plot_drawdown()`, `plot_rolling_beta()`, `plot_rolling_sharpe()`, `plot_monthly_heatmap()` |
| `metrics.py` | `Metrics` dataclass + `compute_metrics()` — pure analytics |
| `data.py` | `fetch_stock_data()`, `fetch_benchmark()` — yfinance calls |
| `constants.py` | `BENCH_TICKERS`, `PERIODS`, `INTERVALS`, chart color constants |

`data.py` and `metrics.py` have no tkinter/matplotlib imports and are independently usable (e.g. in notebooks).

### UI layout (`App(tk.Tk)`)

```
┌─ top bar ─────────────────────────────────────────────────────────┐
│ Symbol | Period | Interval | Benchmark | Run | Log Scale          │
├─ main_split (horizontal PanedWindow, 65% / 35%) ──────────────────┤
│  ┌─ left: outer (vertical PanedWindow) ───┐  ┌─ right pane ─────┐ │
│  │ top_row: output  │ metrics             │  │ View: [dropdown] │ │
│  │ fundamentals bar (valuations + 52w)    │  │ • Returns Scatter│ │
│  │ chart: ax_price (price line)           │  │ • Drawdown       │ │
│  │        ax_vol   (volume bars)          │  │ • Rolling Beta   │ │
│  └────────────────────────────────────────┘  │ • Rolling Sharpe │ │
│                                              │ • Monthly Heatmap│ │
│                                              └──────────────────┘ │
├─ status bar (BOTTOM) ─────────────────────────────────────────────┤
└───────────────────────────────────────────────────────────────────┘
```

**Metrics pane** default width = half the window width, set via `sash_place()` on `<Map>` with a `nonlocal` one-shot flag. Do not use `unbind(seq, funcid)` on Python 3.13 — throws `TclError` because `<Map>` fires once per child widget.

- `_build_panes()` — delegates to `_build_left_pane(main_split)` (returns `top_row`) and `_build_right_pane(main_split)`; handles sash initialisation only
- `_run()` — splits symbol on commas; if multiple tickers calls `_fetch_comparison()`, otherwise `_fetch()`; clears output pane on every run
- `_fetch()` — fetches stock + benchmark; updates window title and status bar; schedules UI updates via `self.after(0, ...)`; `finally` uses `self.after(0, ...)` for button re-enable (thread-safe)
- `_fetch_comparison()` — iterates symbols, calls `compute_metrics()` per ticker, schedules `_show_comparison()` → opens `ComparisonWindow`
- `_update_metrics()` — calls `compute_metrics()`, iterates `self._metric_vars` with `_METRIC_FORMATS[key](getattr(m, key))`; overrides beta to append bench name
- `_plot()` — saves args to `self._last_plot`; reads `self.log_var` to set `ax_price` y-scale; passes `earnings_dates` to `plot_price()`
- `_toggle_log()` — re-calls `_plot(*self._last_plot)` if data exists; no re-fetch needed
- `_show_chart_menu()` / `_save_chart()` — right-click context menu on either canvas; saves PNG/PDF/SVG via `filedialog.asksaveasfilename()`
- `_TextRedirector` — redirects `sys.stdout` to the ScrolledText output pane (thread-safe via `widget.after`)
- `_Tooltip` — `wm_overrideredirect(True)` Toplevel on `<Enter>`/`<Leave>`; attached to all metric label widgets using `_METRIC_TIPS` dict

**Module-level dicts in `app.py`:** `_METRIC_TIPS` (tooltip text), `_METRIC_FORMATS` (format lambdas). Both are keyed by metric key string. `_METRIC_FORMATS` also covers `trailingPE` and `dividendYield` for `ComparisonWindow`.

### Metrics panel

| Metric | Formula |
|--------|---------|
| Annualized Volatility | `std(daily returns) × √252` |
| Cumulative Return | `last / first − 1` |
| Annualized Return (CAGR) | `(1 + cum)^(252/n) − 1` |
| Sharpe Ratio | `mean(r) / std(r) × √252` (rf = 0) |
| Sortino Ratio | `mean(r) × 252 / (std(downside r) × √252)` |
| Calmar Ratio | `CAGR / |Max Drawdown|` — N/A if drawdown = 0 |
| Max Drawdown | `min((close − rolling_max) / rolling_max)` — displayed red |
| Beta | `Cov(stock, bench) / Var(bench)` — inner-aligned on dates |
| Correlation | `np.corrcoef(stock_r, bench_r)[0,1]` |
| R-Squared | `corr²` |
| Up Capture | `mean(stock r on bench-up days) / mean(bench r on bench-up days)` |
| Down Capture | `mean(stock r on bench-down days) / mean(bench r on bench-down days)` |

Benchmark dropdown options: S&P 500 (`^GSPC`), NASDAQ 100 (`^NDX`), Dow Jones (`^DJI`), Russell 2000 (`^RUT`).

Metrics rows use `pady=1` (no visible gap between rows). Rows are split into two groups — `return_rows` and `bench_rows` — rendered by a shared `_add_rows(rows, start)` helper. A `ttk.Separator` and "vs Benchmark" sub-header are inserted between the two groups. Each row tuple is `(key, label, fg)` — `fg=None` defaults to black, `fg="red"` used for Max Drawdown.

### Right pane

Controlled by a `View:` combobox at the top of the pane (`self.right_view_var`). Data is saved to `self._right_pane_data = (hist, bench_hist, symbol, bench_name)` on each fetch; `_redraw_right_pane()` is called both after fetch and on dropdown change (no re-fetch needed).

| View | Function | Notes |
|------|----------|-------|
| Returns Scatter | `plot_scatter()` | OLS regression line, β label |
| Drawdown | `plot_drawdown()` | filled area, y-axis as % |
| Rolling Beta | `plot_rolling_beta(window=63)` | β=1 reference line |
| Rolling Sharpe | `plot_rolling_sharpe(window=63)` | Sharpe=1 reference line |
| Monthly Heatmap | `plot_monthly_heatmap()` | `resample("ME")`, custom red/white/green colormap, cell annotations |

`autofmt_xdate(rotation=30)` is applied for Drawdown, Rolling Beta, and Rolling Sharpe (date x-axis). Monthly Heatmap has month-name x-axis — do not apply `autofmt_xdate` to it.

### Fundamentals bar

Compact horizontal pane (`stretch="never"`) between `top_row` and `chart_frame`. Two rows, three columns each:

- **Row 0**: Trailing P/E · Forward P/E · Dividend Yield
- **Row 1**: % from 52w High · % from 52w Low · % from Period High

`fetch_stock_data()` returns `(hist, fundamentals)` — a tuple. On empty data returns `(None, {})`. Fundamentals dict keys: `trailingPE`, `forwardPE`, `dividendYield`, `currentPrice`, `fiftyTwoWeekHigh`, `fiftyTwoWeekLow`, `periodHigh`, `earnings_dates`.

**yfinance quirk (v1.2.0):** `dividendYield` is returned already as a percentage value (e.g. `0.52` means 0.52%), so format with `f"{dy:.2f}%"` — do NOT use `:.2%` which would multiply by 100 again.

### Dynamic metric coloring

`_update_metrics()` calls `.config(fg=...)` on `self._metric_labels[key]` after setting values. Rules:
- `cum_return`, `ann_cum_return`: green if > 0, red if ≤ 0
- `sharpe`, `sortino`, `calmar`: green if > 1, red if < 0, black otherwise
- `up_capture`: green if > 1, red otherwise
- `down_capture`: green if < 1 (loses less than market), red otherwise

### Status bar & window title

`_build_status_bar()` packs a sunken `tk.Label` at `BOTTOM` **before** `_build_panes()` to ensure correct layout. Title updates to `f"Equity Analysis — {symbol}  ${price:.2f}"` after a successful single-ticker fetch.

### Multi-ticker comparison

Enter comma-separated tickers (e.g. `AAPL, MSFT, GOOG`). `_fetch_comparison()` fetches each in sequence, calls `compute_metrics()`, then opens a `ComparisonWindow(tk.Toplevel)`. The window renders 14 rows (all `Metrics` fields + Trailing P/E + Dividend Yield) × N ticker columns using `_METRIC_FORMATS` for formatting and `hasattr(metrics, key)` to distinguish metric fields from fundamentals dict keys.

### Earnings overlay

`plot_price()` accepts `earnings_dates` (list of `datetime.date`). Draws a dotted `axvline` at each date and annotates the next-day % move using `ax.get_xaxis_transform()` for mixed axis/data coordinates.

### Launch script

`launch.bat` — double-click in Windows Explorer to activate the `Finance` conda environment and run `main.py`. Pauses on error.