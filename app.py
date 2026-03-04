import sys
import tkinter as tk
from tkinter import scrolledtext, ttk
import threading

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from constants import BENCH_TICKERS, PERIODS, INTERVALS
from data import fetch_stock_data, fetch_benchmark
from metrics import compute_metrics
from chart import plot_price, plot_volume, plot_scatter


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Equity Analysis")
        self.resizable(True, True)
        self.minsize(800, 650)

        self._build_toolbar()
        self._build_panes()

        sys.stdout = _TextRedirector(self.output)

    # ------------------------------------------------------------------
    # Layout builders
    # ------------------------------------------------------------------

    def _build_toolbar(self):
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
                     values=PERIODS).pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(top, text="Interval:").pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value="1d")
        ttk.Combobox(top, textvariable=self.interval_var, width=6, state="readonly",
                     values=INTERVALS).pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(top, text="Benchmark:").pack(side=tk.LEFT)
        self.bench_var = tk.StringVar(value="S&P 500")
        ttk.Combobox(top, textvariable=self.bench_var, width=12, state="readonly",
                     values=list(BENCH_TICKERS)).pack(side=tk.LEFT, padx=(4, 16))

        self.run_btn = tk.Button(top, text="Run", width=8, command=self._run)
        self.run_btn.pack(side=tk.LEFT)

        self.log_var = tk.BooleanVar(value=False)
        tk.Checkbutton(top, text="Log Scale", variable=self.log_var,
                       command=self._toggle_log).pack(side=tk.LEFT, padx=(16, 0))

    def _build_panes(self):
        # Outer horizontal split: left (output+metrics+charts) | right (scatter)
        main_split = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=6)
        main_split.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # --- Left side ---
        left_frame = tk.Frame(main_split)
        main_split.add(left_frame, stretch="always")

        outer = tk.PanedWindow(left_frame, orient=tk.VERTICAL, sashrelief=tk.RAISED, sashwidth=6)
        outer.pack(fill=tk.BOTH, expand=True)

        top_row = tk.PanedWindow(outer, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=6)
        outer.add(top_row, stretch="always")

        # Output pane
        self.output = scrolledtext.ScrolledText(
            top_row, font=("Courier", 10), state=tk.DISABLED,
            wrap=tk.NONE, padx=6, pady=6, height=10
        )
        top_row.add(self.output, stretch="always")

        # Metrics pane
        metrics_frame = tk.Frame(top_row, padx=14, pady=14, relief=tk.SUNKEN, bd=1)
        top_row.add(metrics_frame, stretch="never", minsize=200)
        self._build_metrics_pane(metrics_frame)

        # Fundamentals bar
        fundamentals_frame = tk.Frame(outer, padx=14, pady=6, relief=tk.SUNKEN, bd=1)
        outer.add(fundamentals_frame, stretch="never")
        self._build_fundamentals_pane(fundamentals_frame)

        # Price + volume charts
        chart_frame = tk.Frame(outer)
        outer.add(chart_frame, stretch="always")

        self.figure = Figure(figsize=(8, 3), tight_layout=True)
        self.ax_price = self.figure.add_subplot(211)
        self.ax_vol   = self.figure.add_subplot(212, sharex=self.ax_price)

        self.canvas = FigureCanvasTkAgg(self.figure, master=chart_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # --- Right side: scatter pane ---
        scatter_frame = tk.Frame(main_split)
        main_split.add(scatter_frame, stretch="always")

        self.scatter_fig = Figure(tight_layout=True)
        self.ax_scatter  = self.scatter_fig.add_subplot(111)
        self.scatter_canvas = FigureCanvasTkAgg(self.scatter_fig, master=scatter_frame)
        self.scatter_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Set initial sash positions once window is rendered
        _sash_set = False

        def _set_sash(_event=None):
            nonlocal _sash_set
            if _sash_set:
                return
            _sash_set = True
            self.update_idletasks()
            main_split.sash_place(0, int(self.winfo_width() * 0.65), 0)
            top_row.sash_place(0, top_row.winfo_width() // 2, 0)

        self.bind("<Map>", _set_sash)

    def _build_metrics_pane(self, frame):
        tk.Label(frame, text="Return Metrics", font=("Helvetica", 11, "bold"),
                 anchor=tk.W).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        self._metric_vars = {}

        return_rows = [
            ("ann_vol",        "Annualized Volatility",    None),
            ("cum_return",     "Cumulative Return",        None),
            ("ann_cum_return", "Annualized Return (CAGR)", None),
            ("sharpe",         "Sharpe Ratio",             None),
            ("max_drawdown",   "Max Drawdown",             "red"),
        ]
        bench_rows = [
            ("beta",      "Beta",          None),
            ("corr",      "Correlation",   None),
            ("r_squared", "R-Squared",     None),
        ]

        def _add_rows(rows, start):
            for i, (key, label, fg) in enumerate(rows, start=start):
                tk.Label(frame, text=label, anchor=tk.W, fg="#555555").grid(
                    row=i, column=0, sticky=tk.W, pady=1, padx=(0, 16))
                var = tk.StringVar(value="—")
                self._metric_vars[key] = var
                tk.Label(frame, textvariable=var, anchor=tk.E,
                         font=("Courier", 11, "bold"), fg=fg or "black").grid(
                    row=i, column=1, sticky=tk.E)
            return start + len(rows)

        next_row = _add_rows(return_rows, start=1)

        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(
            row=next_row, column=0, columnspan=2, sticky=tk.EW, pady=6)
        tk.Label(frame, text="vs Benchmark", font=("Helvetica", 9, "bold"),
                 fg="#555555", anchor=tk.W).grid(
            row=next_row + 1, column=0, columnspan=2, sticky=tk.W)

        _add_rows(bench_rows, start=next_row + 2)
        frame.columnconfigure(1, weight=1)

    def _build_fundamentals_pane(self, frame):
        self._fundamental_vars = {}
        items = [
            ("trailingPE",    "Trailing P/E"),
            ("forwardPE",     "Forward P/E"),
            ("dividendYield", "Dividend Yield"),
        ]
        for col, (key, label) in enumerate(items):
            padx = (0, 4) if col == 0 else (28, 4)
            tk.Label(frame, text=label, fg="#555555").grid(row=0, column=col * 2, sticky=tk.W, padx=padx)
            var = tk.StringVar(value="—")
            self._fundamental_vars[key] = var
            tk.Label(frame, textvariable=var, font=("Courier", 11, "bold")).grid(
                row=0, column=col * 2 + 1, sticky=tk.W)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _run(self):
        symbol = self.symbol_var.get().strip().upper()
        if not symbol:
            return
        self.output.config(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        self.output.config(state=tk.DISABLED)
        self.run_btn.config(state=tk.DISABLED)
        period   = self.period_var.get()
        interval = self.interval_var.get()
        bench    = BENCH_TICKERS[self.bench_var.get()]
        threading.Thread(
            target=self._fetch, args=(symbol, period, interval, bench), daemon=True
        ).start()

    def _fetch(self, symbol, period, interval, bench):
        try:
            hist, fundamentals = fetch_stock_data(symbol, period, interval)
            bench_hist         = fetch_benchmark(bench, period, interval)
            if hist is not None:
                self.after(0, self._plot, hist, symbol, period)
                self.after(0, self._update_metrics, hist, bench_hist, self.bench_var.get())
                self.after(0, self._plot_scatter, hist, bench_hist, symbol, self.bench_var.get())
                self.after(0, self._update_fundamentals, fundamentals)
        except Exception as e:
            print(f"\nError: {e}")
        finally:
            self.run_btn.config(state=tk.NORMAL)

    def _plot_scatter(self, hist, bench_hist, symbol, bench_name):
        self.ax_scatter.cla()
        plot_scatter(self.ax_scatter, hist, bench_hist, symbol, bench_name)
        self.scatter_canvas.draw()

    def _toggle_log(self):
        if hasattr(self, "_last_plot"):
            self._plot(*self._last_plot)

    def _plot(self, hist, symbol, period):
        self._last_plot = (hist, symbol, period)
        self.ax_price.cla()
        self.ax_vol.cla()
        plot_price(self.ax_price, hist, symbol, period, self.log_var.get())
        plot_volume(self.ax_vol, hist, self.figure)
        self.canvas.draw()

    def _update_metrics(self, hist, bench_hist, bench_name):
        ann_vol, cum_return, ann_cum_return, sharpe, max_drawdown, beta, corr, r_squared = \
            compute_metrics(hist, bench_hist)
        self._metric_vars["ann_vol"].set(f"{ann_vol:.2%}")
        self._metric_vars["cum_return"].set(f"{cum_return:+.2%}")
        self._metric_vars["ann_cum_return"].set(f"{ann_cum_return:+.2%}")
        self._metric_vars["sharpe"].set(f"{sharpe:.2f}")
        self._metric_vars["max_drawdown"].set(f"{max_drawdown:.2%}")
        self._metric_vars["beta"].set(f"{beta:.2f}  vs {bench_name}")
        self._metric_vars["corr"].set(f"{corr:.4f}")
        self._metric_vars["r_squared"].set(f"{r_squared:.4f}")

    def _update_fundamentals(self, fundamentals):
        pe_t = fundamentals.get("trailingPE")
        pe_f = fundamentals.get("forwardPE")
        dy   = fundamentals.get("dividendYield")
        self._fundamental_vars["trailingPE"].set(f"{pe_t:.2f}" if pe_t else "N/A")
        self._fundamental_vars["forwardPE"].set(f"{pe_f:.2f}" if pe_f else "N/A")
        self._fundamental_vars["dividendYield"].set(f"{dy:.2f}%" if dy else "N/A")


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