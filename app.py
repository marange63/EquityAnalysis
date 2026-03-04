import sys
import tkinter as tk
from tkinter import scrolledtext, ttk, filedialog
import threading
import numpy as np

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from constants import BENCH_TICKERS, PERIODS, INTERVALS, COLOR_GREEN, COLOR_RED
from data import fetch_stock_data, fetch_benchmark
from metrics import compute_metrics
from chart import plot_price, plot_volume, plot_scatter, plot_drawdown, plot_rolling_beta, plot_rolling_sharpe, plot_monthly_heatmap


_METRIC_TIPS = {
    "ann_vol":        "Annualized Volatility\nstd(daily r) × √252\nHigher = more volatile",
    "cum_return":     "Cumulative Return\nlast / first − 1",
    "ann_cum_return": "CAGR\n(1 + cum)^(252/n) − 1",
    "sharpe":         "Sharpe Ratio\nmean(r) / std(r) × √252  (rf = 0)\n>1 good  >2 excellent  <0 poor",
    "sortino":        "Sortino Ratio\nmean(r) × 252 / downside_std\nLike Sharpe — only penalises losses",
    "calmar":         "Calmar Ratio\nCAGR / |Max Drawdown|\nReturn per unit of peak-to-trough risk",
    "max_drawdown":   "Max Drawdown\nmin((price − peak) / peak)\nWorst peak-to-trough decline",
    "beta":           "Beta\nCov(stock, bench) / Var(bench)\n>1 amplifies market moves  1 = market",
    "corr":           "Pearson Correlation of daily returns\n1 = perfect co-movement with benchmark",
    "r_squared":      "R-Squared  (corr²)\n% of stock variance explained by benchmark",
    "up_capture":     "Up Capture\nStock mean return on bench-up days / bench mean\n>100% = outperforms in rallies",
    "down_capture":   "Down Capture\nStock mean return on bench-down days / bench mean\n<100% = loses less in sell-offs",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Equity Analysis")
        self.resizable(True, True)
        self.minsize(800, 650)

        self._build_toolbar()
        self._build_status_bar()   # pack at BOTTOM before panes fill the rest
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
        self.period_var = tk.StringVar(value="2y")
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
        self.canvas.get_tk_widget().bind(
            "<Button-3>", lambda e: self._show_chart_menu(e, self.figure))

        # --- Right side: chart pane ---
        scatter_frame = tk.Frame(main_split)
        main_split.add(scatter_frame, stretch="always")

        ctrl_bar = tk.Frame(scatter_frame, padx=6, pady=4)
        ctrl_bar.pack(fill=tk.X)
        tk.Label(ctrl_bar, text="View:").pack(side=tk.LEFT)
        self.right_view_var = tk.StringVar(value="Returns Scatter")
        right_cb = ttk.Combobox(ctrl_bar, textvariable=self.right_view_var, width=16,
                                state="readonly",
                                values=["Returns Scatter", "Drawdown", "Rolling Beta",
                                        "Rolling Sharpe", "Monthly Heatmap"])
        right_cb.pack(side=tk.LEFT, padx=(4, 0))
        right_cb.bind("<<ComboboxSelected>>", lambda _: self._redraw_right_pane())

        self._right_pane_data = None
        self.scatter_fig = Figure(tight_layout=True)
        self.ax_scatter  = self.scatter_fig.add_subplot(111)
        self.scatter_canvas = FigureCanvasTkAgg(self.scatter_fig, master=scatter_frame)
        self.scatter_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.scatter_canvas.get_tk_widget().bind(
            "<Button-3>", lambda e: self._show_chart_menu(e, self.scatter_fig))

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

    def _build_status_bar(self):
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self._status_var, anchor=tk.W, relief=tk.SUNKEN,
                 bd=1, padx=6, font=("Helvetica", 9), fg="#555555"
                 ).pack(side=tk.BOTTOM, fill=tk.X)

    def _build_metrics_pane(self, frame):
        tk.Label(frame, text="Return Metrics", font=("Helvetica", 11, "bold"),
                 anchor=tk.W).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        self._metric_vars  = {}
        self._metric_labels = {}

        return_rows = [
            ("ann_vol",        "Annualized Volatility",    None),
            ("cum_return",     "Cumulative Return",        None),
            ("ann_cum_return", "Annualized Return (CAGR)", None),
            ("sharpe",         "Sharpe Ratio",             None),
            ("sortino",        "Sortino Ratio",            None),
            ("calmar",         "Calmar Ratio",             None),
            ("max_drawdown",   "Max Drawdown",             "red"),
        ]
        bench_rows = [
            ("beta",         "Beta",           None),
            ("corr",         "Correlation",    None),
            ("r_squared",    "R-Squared",      None),
            ("up_capture",   "Up Capture",     None),
            ("down_capture", "Down Capture",   None),
        ]

        def _add_rows(rows, start):
            for i, (key, label, fg) in enumerate(rows, start=start):
                lbl_text = tk.Label(frame, text=label, anchor=tk.W, fg="#555555")
                lbl_text.grid(row=i, column=0, sticky=tk.W, pady=1, padx=(0, 16))
                if key in _METRIC_TIPS:
                    _Tooltip(lbl_text, _METRIC_TIPS[key])
                var = tk.StringVar(value="—")
                self._metric_vars[key] = var
                lbl_val = tk.Label(frame, textvariable=var, anchor=tk.E,
                                   font=("Courier", 11, "bold"), fg=fg or "black")
                lbl_val.grid(row=i, column=1, sticky=tk.E)
                self._metric_labels[key] = lbl_val
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
        val_items = [
            ("trailingPE",    "Trailing P/E"),
            ("forwardPE",     "Forward P/E"),
            ("dividendYield", "Dividend Yield"),
        ]
        prox_items = [
            ("from52wHigh",   "% from 52w High"),
            ("from52wLow",    "% from 52w Low"),
            ("fromPeriodHigh","% from Period High"),
        ]
        for row_idx, items in enumerate((val_items, prox_items)):
            pady = (0, 0) if row_idx == 0 else (4, 0)
            for col, (key, label) in enumerate(items):
                padx = (0, 4) if col == 0 else (28, 4)
                tk.Label(frame, text=label, fg="#555555").grid(
                    row=row_idx, column=col * 2, sticky=tk.W, padx=padx, pady=pady)
                var = tk.StringVar(value="—")
                self._fundamental_vars[key] = var
                tk.Label(frame, textvariable=var, font=("Courier", 11, "bold")).grid(
                    row=row_idx, column=col * 2 + 1, sticky=tk.W, pady=pady)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _run(self):
        raw     = self.symbol_var.get().strip().upper()
        symbols = [s.strip() for s in raw.split(",") if s.strip()]
        if not symbols:
            return
        self.run_btn.config(state=tk.DISABLED)
        self.title("Equity Analysis")
        self._status_var.set(f"Fetching {', '.join(symbols)}…")
        self.output.config(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        self.output.config(state=tk.DISABLED)
        period   = self.period_var.get()
        interval = self.interval_var.get()
        bench    = BENCH_TICKERS[self.bench_var.get()]
        if len(symbols) > 1:
            threading.Thread(
                target=self._fetch_comparison,
                args=(symbols, period, interval, bench, self.bench_var.get()), daemon=True
            ).start()
            return
        threading.Thread(
            target=self._fetch, args=(symbols[0], period, interval, bench), daemon=True
        ).start()

    def _fetch(self, symbol, period, interval, bench):
        try:
            hist, fundamentals = fetch_stock_data(symbol, period, interval)
            bench_hist         = fetch_benchmark(bench, period, interval)
            if hist is not None:
                price = hist["Close"].iloc[-1]
                self.after(0, lambda: self.title(f"Equity Analysis — {symbol}  ${price:.2f}"))
                self.after(0, self._status_var.set,
                           f"{symbol}  ·  ${price:.2f}  ·  {len(hist):,} bars")
                ed = fundamentals.get("earnings_dates", [])
                self.after(0, self._plot, hist, symbol, period, ed)
                self.after(0, self._update_metrics, hist, bench_hist, self.bench_var.get())
                self.after(0, self._plot_scatter, hist, bench_hist, symbol, self.bench_var.get())
                self.after(0, self._update_fundamentals, fundamentals)
        except Exception as e:
            self.after(0, self._status_var.set, f"Error: {e}")
            print(f"\nError: {e}")
        finally:
            self.run_btn.config(state=tk.NORMAL)

    def _fetch_comparison(self, symbols, period, interval, bench, bench_name):
        try:
            bench_hist = fetch_benchmark(bench, period, interval)
            results = []
            for sym in symbols:
                hist, fundamentals = fetch_stock_data(sym, period, interval)
                if hist is not None:
                    results.append((sym, compute_metrics(hist, bench_hist), fundamentals))
            if results:
                self.after(0, self._show_comparison, results, bench_name)
                self.after(0, self._status_var.set,
                           f"Comparison: {', '.join(r[0] for r in results)}")
        except Exception as e:
            self.after(0, self._status_var.set, f"Error: {e}")
            print(f"\nError: {e}")
        finally:
            self.after(0, lambda: self.run_btn.config(state=tk.NORMAL))

    def _show_comparison(self, results, bench_name):
        win = tk.Toplevel(self)
        win.title(f"Comparison — {', '.join(r[0] for r in results)}")
        win.minsize(520, 420)

        frame = tk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tickers = [r[0] for r in results]
        cols    = ["Metric"] + tickers
        tree    = ttk.Treeview(frame, columns=cols, show="headings")
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=180 if col == "Metric" else 95,
                        anchor=tk.W if col == "Metric" else tk.E)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        KEYS = ["ann_vol", "cum_return", "ann_cum_return", "sharpe", "sortino",
                "calmar", "max_drawdown", "beta", "corr", "r_squared",
                "up_capture", "down_capture"]
        rows = [
            ("Annualized Volatility",  "ann_vol",        lambda v: f"{v:.2%}"),
            ("Cumulative Return",      "cum_return",     lambda v: f"{v:+.2%}"),
            ("CAGR",                   "ann_cum_return", lambda v: f"{v:+.2%}"),
            ("Sharpe Ratio",           "sharpe",         lambda v: f"{v:.2f}"),
            ("Sortino Ratio",          "sortino",        lambda v: f"{v:.2f}"),
            ("Calmar Ratio",           "calmar",         lambda v: f"{v:.2f}" if not np.isnan(v) else "N/A"),
            ("Max Drawdown",           "max_drawdown",   lambda v: f"{v:.2%}"),
            ("Beta",                   "beta",           lambda v: f"{v:.2f}"),
            ("Correlation",            "corr",           lambda v: f"{v:.4f}"),
            ("R-Squared",              "r_squared",      lambda v: f"{v:.4f}"),
            ("Up Capture",             "up_capture",     lambda v: f"{v:.1%}" if not np.isnan(v) else "N/A"),
            ("Down Capture",           "down_capture",   lambda v: f"{v:.1%}" if not np.isnan(v) else "N/A"),
            ("Trailing P/E",           "trailingPE",     lambda v: f"{v:.2f}" if v else "N/A"),
            ("Dividend Yield",         "dividendYield",  lambda v: f"{v:.2f}%" if v else "N/A"),
        ]
        for label, key, fmt in rows:
            row_vals = [label]
            for _sym, metrics_tuple, fundamentals in results:
                if key in KEYS:
                    row_vals.append(fmt(metrics_tuple[KEYS.index(key)]))
                else:
                    row_vals.append(fmt(fundamentals.get(key)))
            tree.insert("", tk.END, values=row_vals)

    def _plot_scatter(self, hist, bench_hist, symbol, bench_name):
        self._right_pane_data = (hist, bench_hist, symbol, bench_name)
        self._redraw_right_pane()

    def _redraw_right_pane(self):
        if self._right_pane_data is None:
            return
        hist, bench_hist, symbol, bench_name = self._right_pane_data
        self.ax_scatter.cla()
        view = self.right_view_var.get()
        if view == "Returns Scatter":
            plot_scatter(self.ax_scatter, hist, bench_hist, symbol, bench_name)
        elif view == "Drawdown":
            plot_drawdown(self.ax_scatter, hist, symbol)
            self.scatter_fig.autofmt_xdate(rotation=30, ha="right")
        elif view == "Rolling Beta":
            plot_rolling_beta(self.ax_scatter, hist, bench_hist, symbol, bench_name)
            self.scatter_fig.autofmt_xdate(rotation=30, ha="right")
        elif view == "Rolling Sharpe":
            plot_rolling_sharpe(self.ax_scatter, hist, symbol)
            self.scatter_fig.autofmt_xdate(rotation=30, ha="right")
        elif view == "Monthly Heatmap":
            plot_monthly_heatmap(self.ax_scatter, hist, symbol)
        self.scatter_fig.tight_layout()
        self.scatter_canvas.draw()

    def _toggle_log(self):
        if hasattr(self, "_last_plot"):
            self._plot(*self._last_plot)

    def _plot(self, hist, symbol, period, earnings_dates=None):
        self._last_plot = (hist, symbol, period, earnings_dates)
        self.ax_price.cla()
        self.ax_vol.cla()
        plot_price(self.ax_price, hist, symbol, period, self.log_var.get(), earnings_dates)
        plot_volume(self.ax_vol, hist, self.figure)
        self.canvas.draw()

    def _update_metrics(self, hist, bench_hist, bench_name):
        ann_vol, cum_return, ann_cum_return, sharpe, sortino, calmar, \
            max_drawdown, beta, corr, r_squared, up_capture, down_capture = \
            compute_metrics(hist, bench_hist)
        self._metric_vars["ann_vol"].set(f"{ann_vol:.2%}")
        self._metric_vars["cum_return"].set(f"{cum_return:+.2%}")
        self._metric_vars["ann_cum_return"].set(f"{ann_cum_return:+.2%}")
        self._metric_vars["sharpe"].set(f"{sharpe:.2f}")
        self._metric_vars["sortino"].set(f"{sortino:.2f}")
        self._metric_vars["calmar"].set(f"{calmar:.2f}" if not np.isnan(calmar) else "N/A")
        self._metric_vars["max_drawdown"].set(f"{max_drawdown:.2%}")
        self._metric_vars["beta"].set(f"{beta:.2f}  vs {bench_name}")
        self._metric_vars["corr"].set(f"{corr:.4f}")
        self._metric_vars["r_squared"].set(f"{r_squared:.4f}")
        self._metric_vars["up_capture"].set(f"{up_capture:.1%}" if not np.isnan(up_capture) else "N/A")
        self._metric_vars["down_capture"].set(f"{down_capture:.1%}" if not np.isnan(down_capture) else "N/A")

        # Dynamic value coloring
        self._metric_labels["cum_return"].config(
            fg=COLOR_GREEN if cum_return > 0 else COLOR_RED)
        self._metric_labels["ann_cum_return"].config(
            fg=COLOR_GREEN if ann_cum_return > 0 else COLOR_RED)
        self._metric_labels["sharpe"].config(
            fg=COLOR_GREEN if sharpe > 1 else (COLOR_RED if sharpe < 0 else "black"))
        self._metric_labels["sortino"].config(
            fg=COLOR_GREEN if sortino > 1 else (COLOR_RED if sortino < 0 else "black"))
        if not np.isnan(calmar):
            self._metric_labels["calmar"].config(
                fg=COLOR_GREEN if calmar > 1 else (COLOR_RED if calmar < 0 else "black"))
        if not np.isnan(up_capture):
            self._metric_labels["up_capture"].config(
                fg=COLOR_GREEN if up_capture > 1 else COLOR_RED)
        if not np.isnan(down_capture):
            self._metric_labels["down_capture"].config(
                fg=COLOR_GREEN if down_capture < 1 else COLOR_RED)

    def _update_fundamentals(self, fundamentals):
        pe_t = fundamentals.get("trailingPE")
        pe_f = fundamentals.get("forwardPE")
        dy   = fundamentals.get("dividendYield")
        self._fundamental_vars["trailingPE"].set(f"{pe_t:.2f}" if pe_t else "N/A")
        self._fundamental_vars["forwardPE"].set(f"{pe_f:.2f}" if pe_f else "N/A")
        self._fundamental_vars["dividendYield"].set(f"{dy:.2f}%" if dy else "N/A")

        cur = fundamentals.get("currentPrice")
        h52 = fundamentals.get("fiftyTwoWeekHigh")
        l52 = fundamentals.get("fiftyTwoWeekLow")
        ph  = fundamentals.get("periodHigh")
        self._fundamental_vars["from52wHigh"].set(
            f"{cur / h52 - 1:+.1%}" if cur and h52 else "N/A")
        self._fundamental_vars["from52wLow"].set(
            f"{cur / l52 - 1:+.1%}" if cur and l52 else "N/A")
        self._fundamental_vars["fromPeriodHigh"].set(
            f"{cur / ph - 1:+.1%}" if cur and ph else "N/A")


    def _show_chart_menu(self, event, figure):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Save as PNG…", command=lambda: self._save_chart(figure))
        menu.tk_popup(event.x_root, event.y_root)

    def _save_chart(self, figure):
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("PDF document", "*.pdf"), ("SVG image", "*.svg")],
            title="Save chart",
        )
        if path:
            figure.savefig(path, dpi=150, bbox_inches="tight")


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


class _Tooltip:
    def __init__(self, widget, text):
        self._widget = widget
        self._text   = text
        self._tip    = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 2
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=self._text, justify=tk.LEFT, background="#ffffcc",
                 relief=tk.SOLID, borderwidth=1, font=("Helvetica", 9),
                 padx=5, pady=3, wraplength=300).pack()

    def _hide(self, _event=None):
        if self._tip:
            self._tip.destroy()
            self._tip = None