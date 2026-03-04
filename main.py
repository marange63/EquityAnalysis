import sys
import tkinter as tk
from tkinter import scrolledtext, ttk
import threading

import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection


def fetch_stock_data(ticker: str, period: str = "1y", interval: str = "1d"):
    stock = yf.Ticker(ticker)

    hist = stock.history(period=period, interval=interval)
    if hist.empty:
        print(f"No data found for ticker '{ticker}'")
        return None

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

    return hist


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

    bench_returns = bench_hist["Close"].pct_change().dropna()
    aligned       = returns.align(bench_returns, join="inner")
    cov           = np.cov(aligned[0], aligned[1])
    beta          = cov[0, 1] / cov[1, 1]
    corr          = np.corrcoef(aligned[0], aligned[1])[0, 1]
    r_squared     = corr ** 2

    return ann_vol, cum_return, ann_cum_return, sharpe, max_drawdown, beta, corr, r_squared


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Equity Analysis")
        self.resizable(True, True)
        self.minsize(800, 650)

        # --- Top bar: symbol entry + run button ---
        top = tk.Frame(self, padx=10, pady=10)
        top.pack(fill=tk.X)

        tk.Label(top, text="Symbol:").pack(side=tk.LEFT)

        self.symbol_var = tk.StringVar(value="AAPL")
        self.entry = tk.Entry(top, textvariable=self.symbol_var, width=12, font=("Courier", 12))
        self.entry.pack(side=tk.LEFT, padx=(4, 16))
        self.entry.bind("<Return>", lambda _: self._run())

        tk.Label(top, text="Period:").pack(side=tk.LEFT)
        self.period_var = tk.StringVar(value="1y")
        ttk.Combobox(top, textvariable=self.period_var, width=6, state="readonly",
                     values=["1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
                     ).pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(top, text="Interval:").pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value="1d")
        ttk.Combobox(top, textvariable=self.interval_var, width=6, state="readonly",
                     values=["1d", "5d", "1wk", "1mo", "3mo"]
                     ).pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(top, text="Benchmark:").pack(side=tk.LEFT)
        self.bench_var = tk.StringVar(value="S&P 500")
        self._bench_tickers = {
            "S&P 500":    "^GSPC",
            "NASDAQ 100": "^NDX",
            "Dow Jones":  "^DJI",
            "Russell 2000": "^RUT",
        }
        ttk.Combobox(top, textvariable=self.bench_var, width=12, state="readonly",
                     values=list(self._bench_tickers)
                     ).pack(side=tk.LEFT, padx=(4, 16))

        self.run_btn = tk.Button(top, text="Run", width=8, command=self._run)
        self.run_btn.pack(side=tk.LEFT)

        self.log_var = tk.BooleanVar(value=False)
        tk.Checkbutton(top, text="Log Scale", variable=self.log_var,
                       command=self._toggle_log).pack(side=tk.LEFT, padx=(16, 0))

        # --- Outer vertical split: top row | charts ---
        outer = tk.PanedWindow(self, orient=tk.VERTICAL, sashrelief=tk.RAISED, sashwidth=6)
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # --- Top row: horizontal split: output | metrics ---
        top_row = tk.PanedWindow(outer, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=6)
        outer.add(top_row, stretch="always")

        # Scrollable output pane (left)
        self.output = scrolledtext.ScrolledText(
            top_row, font=("Courier", 10), state=tk.DISABLED,
            wrap=tk.NONE, padx=6, pady=6, height=10
        )
        top_row.add(self.output, stretch="always")

        # Metrics pane (right)
        metrics_frame = tk.Frame(top_row, padx=14, pady=14, relief=tk.SUNKEN, bd=1)
        top_row.add(metrics_frame, stretch="never", minsize=200)

        _sash_set = False

        def _set_sash(event=None):
            nonlocal _sash_set
            if _sash_set:
                return
            _sash_set = True
            self.update_idletasks()
            top_row.sash_place(0, self.winfo_width() // 2, 0)

        self.bind("<Map>", _set_sash)

        tk.Label(metrics_frame, text="Return Metrics", font=("Helvetica", 11, "bold"),
                 anchor=tk.W).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        self._metric_vars = {}
        return_rows = [
            ("ann_vol",        "Annualized Volatility",   None),
            ("cum_return",     "Cumulative Return",       None),
            ("ann_cum_return", "Annualized Return (CAGR)", None),
            ("sharpe",         "Sharpe Ratio",            None),
            ("max_drawdown",   "Max Drawdown",            "red"),
        ]
        bench_rows = [
            ("beta",           "Beta",                   None),
            ("corr",           "Correlation",            None),
            ("r_squared",      "R-Squared",              None),
        ]

        def _add_rows(rows, start):
            for i, (key, label, fg) in enumerate(rows, start=start):
                tk.Label(metrics_frame, text=label, anchor=tk.W, fg="#555555").grid(
                    row=i, column=0, sticky=tk.W, pady=1, padx=(0, 16))
                var = tk.StringVar(value="—")
                self._metric_vars[key] = var
                tk.Label(metrics_frame, textvariable=var, anchor=tk.E,
                         font=("Courier", 11, "bold"), fg=fg or "black").grid(row=i, column=1, sticky=tk.E)
            return start + len(rows)

        next_row = _add_rows(return_rows, start=1)

        ttk.Separator(metrics_frame, orient=tk.HORIZONTAL).grid(
            row=next_row, column=0, columnspan=2, sticky=tk.EW, pady=6)
        tk.Label(metrics_frame, text=f"vs Benchmark", font=("Helvetica", 9, "bold"),
                 fg="#555555", anchor=tk.W).grid(row=next_row + 1, column=0, columnspan=2, sticky=tk.W)

        _add_rows(bench_rows, start=next_row + 2)

        metrics_frame.columnconfigure(1, weight=1)

        # --- Chart pane (bottom) ---
        chart_frame = tk.Frame(outer)
        outer.add(chart_frame, stretch="always")

        self.figure = Figure(figsize=(8, 3), tight_layout=True)
        self.ax_price = self.figure.add_subplot(211)
        self.ax_vol   = self.figure.add_subplot(212, sharex=self.ax_price)

        self.canvas = FigureCanvasTkAgg(self.figure, master=chart_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Redirect stdout to the output pane
        sys.stdout = _TextRedirector(self.output)

    def _run(self):
        symbol = self.symbol_var.get().strip().upper()
        if not symbol:
            return
        self.output.config(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        self.output.config(state=tk.DISABLED)
        self.run_btn.config(state=tk.DISABLED)
        period    = self.period_var.get()
        interval  = self.interval_var.get()
        bench     = self._bench_tickers[self.bench_var.get()]
        threading.Thread(target=self._fetch, args=(symbol, period, interval, bench), daemon=True).start()

    def _fetch(self, symbol, period, interval, bench):
        try:
            hist = fetch_stock_data(symbol, period, interval)
            bench_hist = yf.Ticker(bench).history(period=period, interval=interval)
            if hist is not None:
                self.after(0, self._plot, hist, symbol, period)
                self.after(0, self._update_metrics, hist, bench_hist, self.bench_var.get())
        except Exception as e:
            print(f"\nError: {e}")
        finally:
            self.run_btn.config(state=tk.NORMAL)

    def _update_metrics(self, hist, bench_hist, bench_name):
        ann_vol, cum_return, ann_cum_return, sharpe, max_drawdown, beta, corr, r_squared = compute_metrics(hist, bench_hist)
        self._metric_vars["ann_vol"].set(f"{ann_vol:.2%}")
        self._metric_vars["cum_return"].set(f"{cum_return:+.2%}")
        self._metric_vars["ann_cum_return"].set(f"{ann_cum_return:+.2%}")
        self._metric_vars["sharpe"].set(f"{sharpe:.2f}")
        self._metric_vars["max_drawdown"].set(f"{max_drawdown:.2%}")
        self._metric_vars["beta"].set(f"{beta:.2f}  vs {bench_name}")
        self._metric_vars["corr"].set(f"{corr:.4f}")
        self._metric_vars["r_squared"].set(f"{r_squared:.4f}")

    def _toggle_log(self):
        if hasattr(self, "_last_plot"):
            self._plot(*self._last_plot)

    def _plot(self, hist, symbol, period):
        self._last_plot = (hist, symbol, period)
        dates = hist.index.tz_localize(None) if hist.index.tzinfo else hist.index

        self.ax_price.cla()
        self.ax_vol.cla()

        # Close price line colored by rolling 21-day return: green >= 0, red < 0
        roll_ret = hist["Close"] / hist["Close"].shift(21) - 1
        x = mdates.date2num(dates.to_pydatetime())
        y = hist["Close"].values
        pts  = np.array([x, y]).T.reshape(-1, 1, 2)
        segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
        seg_colors = ["#4CAF50" if v >= 0 else "#F44336" for v in roll_ret.values[1:]]
        lc = LineCollection(segs, colors=seg_colors, linewidth=1.5)
        self.ax_price.add_collection(lc)
        self.ax_price.fill_between(dates, hist["Close"], alpha=0.08, color="#888888")
        self.ax_price.set_xlim(x[0], x[-1])
        if self.log_var.get():
            self.ax_price.set_yscale("log")
            self.ax_price.set_ylim(bottom=hist["Close"].min() * 0.95)
        else:
            self.ax_price.set_yscale("linear")
            self.ax_price.set_ylim(bottom=hist["Close"].min() * 0.95)
        self.ax_price.set_ylabel("Price (USD, log)" if self.log_var.get() else "Price (USD)")
        self.ax_price.set_title(f"{symbol} ({period}) — Close Price & Volume")
        self.ax_price.grid(True, linestyle="--", alpha=0.4)
        plt.setp(self.ax_price.get_xticklabels(), visible=False)

        # Volume bars — blue above median, orange below
        med_vol = hist["Volume"].median()
        vol_colors = ["#2196F3" if v >= med_vol else "#FF9800" for v in hist["Volume"]]
        self.ax_vol.bar(dates, hist["Volume"], color=vol_colors, width=1.5)
        self.ax_vol.axhline(med_vol, color="#555555", linewidth=0.8, linestyle="--")
        self.ax_vol.set_ylabel("Volume")
        self.ax_vol.grid(True, linestyle="--", alpha=0.4)
        self.ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        self.ax_vol.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        self.figure.autofmt_xdate(rotation=30, ha="right")

        self.canvas.draw()

    def _write(self, text):
        self.output.config(state=tk.NORMAL)
        self.output.insert(tk.END, text)
        self.output.see(tk.END)
        self.output.config(state=tk.DISABLED)


class _TextRedirector:
    def __init__(self, widget: scrolledtext.ScrolledText):
        self.widget = widget

    def write(self, text):
        self.widget.after(0, self._append, text)

    def _append(self, text):
        self.widget.config(state=tk.NORMAL)
        self.widget.insert(tk.END, text)
        self.widget.see(tk.END)
        self.widget.config(state=tk.DISABLED)

    def flush(self):
        pass


if __name__ == "__main__":
    app = App()
    app.mainloop()