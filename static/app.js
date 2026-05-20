/* ==========================================================================
   MT5 LIVE TERMINAL — websocket client + chart + DOM updates
   ========================================================================== */

(() => {
  const MAX_CURVE_POINTS = 600;

  // -------- DOM refs ------------------------------------------------------
  const $ = (id) => document.getElementById(id);

  const els = {
    connStatus:   $("conn-status"),
    acctLogin:    $("acct-login"),
    acctServer:   $("acct-server"),
    balance:      $("stat-balance"),
    balanceCcy:   $("stat-balance-ccy"),
    equity:       $("stat-equity"),
    equityCcy:    $("stat-equity-ccy"),
    today:        $("stat-today"),
    open:         $("stat-open"),
    margin:       $("stat-margin"),
    freeMargin:   $("stat-free-margin"),
    leverage:     $("stat-leverage"),
    marginLevel:  $("stat-margin-level"),
    posBody:      $("positions-body"),
    posCount:     $("pos-count"),
    footerClock:  $("footer-clock"),
    footerTick:   $("footer-tick"),
  };

  // -------- Formatting helpers -------------------------------------------
  const fmtMoney = (n) => {
    if (n === null || n === undefined || Number.isNaN(n)) return "0.00";
    return Number(n).toLocaleString(undefined, {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
  };
  const fmtSigned = (n) => {
    const s = fmtMoney(Math.abs(n));
    return (n >= 0 ? "+" : "−") + s;
  };
  const fmtPrice = (n, digits = 5) => Number(n).toFixed(digits);
  const fmtVolume = (n) => Number(n).toFixed(2);
  const fmtPct = (n) => `${Number(n).toFixed(1)}%`;

  const applyPnlClass = (el, value) => {
    el.classList.remove("profit", "loss");
    if (value > 0) el.classList.add("profit");
    else if (value < 0) el.classList.add("loss");
  };

  // -------- Chart --------------------------------------------------------
  // Uses a linear x-axis with unix-seconds values and a tick-callback that
  // formats them as dates. This avoids needing a Chart.js date adapter.
  let chart = null;

  const buildChart = (points) => {
    const canvas = document.getElementById("equityChart");
    if (!canvas) {
      console.error("[chart] #equityChart canvas not found");
      return;
    }
    console.log(
      "[chart] buildChart points=%d canvas=%dx%d",
      points.length,
      canvas.clientWidth,
      canvas.clientHeight,
    );

    const ctx = canvas.getContext("2d");
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.clientHeight || 300);
    gradient.addColorStop(0, "rgba(0, 217, 255, 0.45)");
    gradient.addColorStop(1, "rgba(0, 217, 255, 0.00)");

    if (chart) {
      chart.destroy();
      chart = null;
    }

    chart = new Chart(ctx, {
      type: "line",
      data: {
        datasets: [{
          label: "Equity",
          data: points.map(p => ({ x: p.t, y: p.v })),
          borderColor: "#00D9FF",
          borderWidth: 2,
          backgroundColor: gradient,
          fill: true,
          tension: 0.32,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: "#00D9FF",
          pointHoverBorderColor: "#05060D",
          pointHoverBorderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        animation: { duration: 0 },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(5, 6, 13, 0.92)",
            borderColor: "rgba(0, 217, 255, 0.4)",
            borderWidth: 1,
            titleColor: "#00D9FF",
            titleFont: { family: "Orbitron", size: 10, weight: "700" },
            bodyColor: "#F4FBFF",
            bodyFont: { family: "JetBrains Mono", size: 12 },
            padding: 10,
            displayColors: false,
            callbacks: {
              title: (items) => new Date(items[0].parsed.x * 1000).toLocaleString(),
              label: (item) => `Equity  ${fmtMoney(item.parsed.y)}`,
            },
          },
        },
        scales: {
          x: {
            type: "linear",
            grid: { color: "rgba(0, 217, 255, 0.05)", drawBorder: false },
            ticks: {
              color: "#6E7A95",
              font: { family: "JetBrains Mono", size: 10 },
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 8,
              callback: function (v) {
                const d = new Date(v * 1000);
                // Show day for long ranges, hour:min for short.
                const span = this.chart.scales.x.max - this.chart.scales.x.min;
                if (span > 86400 * 2) {
                  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
                }
                return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
              },
            },
          },
          y: {
            grid: { color: "rgba(0, 217, 255, 0.05)", drawBorder: false },
            ticks: {
              color: "#6E7A95",
              font: { family: "JetBrains Mono", size: 10 },
              callback: (v) => fmtMoney(v),
            },
          },
        },
      },
    });
  };

  const pushEquityPoint = (pt) => {
    if (!chart) return;
    const data = chart.data.datasets[0].data;
    data.push({ x: pt.t, y: pt.v });
    if (data.length > MAX_CURVE_POINTS) data.shift();
    chart.update("none");
  };

  // -------- DOM updaters -------------------------------------------------
  const updateAccount = (acct) => {
    els.acctLogin.textContent = acct.login || "—";
    els.acctServer.textContent = acct.server || "—";

    els.balance.textContent = fmtMoney(acct.balance);
    els.balanceCcy.textContent = acct.currency || "USD";
    els.equity.textContent = fmtMoney(acct.equity);
    els.equityCcy.textContent = acct.currency || "USD";

    els.open.textContent = fmtSigned(acct.open_pnl);
    applyPnlClass(els.open, acct.open_pnl);

    els.margin.textContent = fmtMoney(acct.margin);
    els.freeMargin.textContent = fmtMoney(acct.free_margin);
    els.leverage.textContent = `1:${acct.leverage}`;
    els.marginLevel.textContent = acct.margin_level ? fmtPct(acct.margin_level) : "—";
  };

  const updateTodayPnl = (v) => {
    els.today.textContent = fmtSigned(v);
    applyPnlClass(els.today, v);
  };

  const updatePositions = (positions) => {
    els.posCount.textContent = positions.length;

    if (!positions.length) {
      els.posBody.innerHTML = `<tr class="empty-row"><td colspan="6">— NO OPEN POSITIONS —</td></tr>`;
      return;
    }

    const rows = positions.map(p => {
      const pnlCls = p.profit > 0 ? "profit" : p.profit < 0 ? "loss" : "";
      const sideCls = p.side === "BUY" ? "buy" : "sell";
      return `
        <tr>
          <td class="symbol">${p.symbol}</td>
          <td><span class="side-pill ${sideCls}">${p.side}</span></td>
          <td class="num">${fmtVolume(p.volume)}</td>
          <td class="num">${fmtPrice(p.price_open)}</td>
          <td class="num">${fmtPrice(p.price_current)}</td>
          <td class="num pnl-cell ${pnlCls}">${fmtSigned(p.profit)}</td>
        </tr>
      `;
    }).join("");

    els.posBody.innerHTML = rows;
  };

  // -------- Stats panel --------------------------------------------------
  const safe = (fn, label) => {
    try { fn(); } catch (e) { console.error(`[render:${label}]`, e); }
  };

  const STAT_KEYS = [
    "total_trades", "win_rate", "profit_factor", "total_profit",
    "avg_win", "avg_loss", "largest_win", "largest_loss",
    "max_win_streak", "max_loss_streak", "avg_duration_minutes", "most_traded_symbol",
  ];

  // Static color rule per Part 5. total_profit is handled dynamically by sign.
  const STAT_COLOR_CLASS = {
    win_rate:          "pos",
    avg_win:           "pos",
    largest_win:       "pos",
    max_win_streak:    "pos",
    avg_loss:          "neg",
    largest_loss:      "neg",
    max_loss_streak:   "neg",
    most_traded_symbol: "accent",
    // total_trades, profit_factor, avg_duration_minutes → no class (plain white)
  };

  const MONEY_KEYS = new Set([
    "total_profit", "avg_win", "avg_loss", "largest_win", "largest_loss",
  ]);

  const fmtStat = (key, value) => {
    if (value === null || value === undefined) return "—";
    if (key === "win_rate")              return `${Number(value).toFixed(2)}%`;
    if (key === "avg_duration_minutes")  return `${Math.round(Number(value))}m`;
    if (key === "most_traded_symbol")    return String(value || "N/A");
    if (key === "profit_factor")         return Number(value).toFixed(2);
    if (key === "total_trades" || key === "max_win_streak" || key === "max_loss_streak") {
      return String(Number(value));
    }
    if (MONEY_KEYS.has(key)) return fmtSigned(Number(value));
    return String(value);
  };

  const renderStats = (stats) => {
    if (!stats) return;
    for (const key of STAT_KEYS) {
      const el = document.getElementById(`stat-${key}`);
      if (!el) continue;
      el.textContent = fmtStat(key, stats[key]);
      el.classList.remove("pos", "neg", "accent");

      if (key === "total_profit") {
        const v = Number(stats[key]);
        if (v > 0)      el.classList.add("pos");
        else if (v < 0) el.classList.add("neg");
        // exactly 0: leave plain white
      } else {
        const cls = STAT_COLOR_CLASS[key];
        if (cls) el.classList.add(cls);
      }
    }
  };

  // -------- Drawdown -----------------------------------------------------
  const renderDrawdown = (dd, _account) => {
    if (!dd) return;
    const cur = $("dd-current");
    const mx  = $("dd-max");
    const pk  = $("dd-peak");
    const bar = $("dd-bar-fill");
    const st  = $("dd-status");
    if (!cur || !mx || !pk || !bar || !st) return;

    const pct = Math.max(0, Math.min(100, Number(dd.current_dd_pct) || 0));
    cur.textContent = `-${fmtMoney(Math.abs(dd.current_dd))} (${pct.toFixed(2)}%)`;
    mx.textContent  = `-${fmtMoney(Math.abs(dd.max_dd))}`;
    pk.textContent  = fmtMoney(dd.peak);
    bar.style.width = `${pct}%`;

    st.classList.remove("dd-status-safe", "dd-status-caution", "dd-status-danger");
    if (pct < 3) {
      st.textContent = "SAFE";
      st.classList.add("dd-status-safe");
    } else if (pct < 7) {
      st.textContent = "CAUTION";
      st.classList.add("dd-status-caution");
    } else {
      st.textContent = "DANGER";
      st.classList.add("dd-status-danger");
    }
  };

  // -------- Per-symbol breakdown ----------------------------------------
  const renderPerSymbol = (rows) => {
    const tbody = $("per-symbol-body");
    if (!tbody) return;
    if (!rows || !rows.length) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="4">— NO CLOSED TRADES YET —</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map(r => {
      const cls = r.net_pnl > 0 ? "profit" : r.net_pnl < 0 ? "loss" : "";
      return `
        <tr>
          <td class="symbol">${r.symbol}</td>
          <td class="num">${r.trades}</td>
          <td class="num">${Number(r.win_rate).toFixed(2)}%</td>
          <td class="num pnl-cell ${cls}">${fmtSigned(r.net_pnl)}</td>
        </tr>
      `;
    }).join("");
  };

  // -------- Heatmap color helper ----------------------------------------
  const heatmapColor = (value, maxAbs) => {
    if (!value || !maxAbs) {
      return { bg: "rgba(255,255,255,0.03)", border: "rgba(255,255,255,0.05)" };
    }
    const intensity = Math.min(1, Math.abs(value) / maxAbs);
    if (value > 0) {
      return {
        bg:     `rgba(0, 255, 156, ${0.08 + intensity * 0.40})`,
        border: `rgba(0, 255, 156, ${0.20 + intensity * 0.50})`,
      };
    }
    return {
      bg:     `rgba(255, 61, 110, ${0.08 + intensity * 0.40})`,
      border: `rgba(255, 61, 110, ${0.20 + intensity * 0.50})`,
    };
  };

  // -------- Hourly heatmap ----------------------------------------------
  const renderHourlyHeatmap = (hourly) => {
    const container = $("hourly-heatmap");
    if (!container) return;
    if (!hourly || !hourly.length) {
      container.innerHTML = "";
      return;
    }
    const maxAbs = Math.max(...hourly.map(h => Math.abs(h.pnl || 0)), 0);
    container.innerHTML = hourly.map(h => {
      const c = heatmapColor(h.pnl, maxAbs);
      const label = String(h.hour).padStart(2, "0") + "h";
      const pnlDisplay = h.trades === 0
        ? "—"
        : (h.pnl > 0 ? "+" : h.pnl < 0 ? "-" : "") + Math.round(Math.abs(h.pnl));
      const title = `${label} · ${h.trades} trades · ${Number(h.win_rate).toFixed(1)}% win · ${fmtSigned(h.pnl)}`;
      return `
        <div class="hm-cell" style="background:${c.bg};border-color:${c.border}" title="${title}">
          <div class="hm-hour">${label}</div>
          <div class="hm-pnl">${pnlDisplay}</div>
        </div>
      `;
    }).join("");
  };

  // -------- Weekday breakdown -------------------------------------------
  const WEEKDAY_ABBR = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];

  const renderWeekday = (weekday) => {
    const container = $("weekday-grid");
    if (!container) return;
    if (!weekday || !weekday.length) {
      container.innerHTML = "";
      return;
    }
    const maxAbs = Math.max(...weekday.map(d => Math.abs(d.pnl || 0)), 0);
    container.innerHTML = weekday.map(d => {
      const c = heatmapColor(d.pnl, maxAbs);
      const day = WEEKDAY_ABBR[d.weekday] || "?";
      const pnlDisplay = d.trades === 0 ? "—" : fmtSigned(d.pnl);
      const title = `${day} · ${d.trades} trades · ${Number(d.win_rate).toFixed(1)}% win`;
      return `
        <div class="weekday-cell" style="background:${c.bg};border-color:${c.border}" title="${title}">
          <div class="wd-day">${day}</div>
          <div class="wd-pnl">${pnlDisplay}</div>
          <div class="wd-count">${d.trades} trades</div>
        </div>
      `;
    }).join("");
  };

  // -------- Live ticks ---------------------------------------------------
  const renderTicks = (ticks) => {
    const container = $("ticks-grid");
    if (!container) return;
    if (!ticks || !ticks.length) {
      container.innerHTML = `<div class="empty-cell">— NO TICK DATA · SYMBOLS NOT SUBSCRIBED —</div>`;
      return;
    }
    container.innerHTML = ticks.map(t => {
      const digits = Number.isInteger(t.digits) ? t.digits : 5;
      const bid = Number(t.bid).toFixed(digits);
      const ask = Number(t.ask).toFixed(digits);
      const spr = Number(t.spread).toFixed(digits);
      return `
        <div class="tick-card">
          <div class="tick-symbol">${t.symbol}</div>
          <div class="tick-spread">SPREAD ${spr}</div>
          <div class="tick-bid">${bid}</div>
          <div class="tick-ask">${ask}</div>
        </div>
      `;
    }).join("");
  };

  // -------- Connection status -------------------------------------------
  const setConnStatus = (state) => {
    els.connStatus.classList.remove("connected", "disconnected");
    const text = els.connStatus.querySelector(".status-text");
    if (state === "connected") {
      els.connStatus.classList.add("connected");
      text.textContent = "LIVE";
    } else if (state === "disconnected") {
      els.connStatus.classList.add("disconnected");
      text.textContent = "OFFLINE";
    } else {
      text.textContent = "CONNECTING";
    }
  };

  // -------- Clock --------------------------------------------------------
  let tickCount = 0;
  setInterval(() => {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    els.footerClock.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }, 1000);

  // -------- Websocket ----------------------------------------------------
  let ws = null;
  let reconnectDelay = 1000;

  const connect = () => {
    setConnStatus("connecting");
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.addEventListener("open", () => {
      setConnStatus("connected");
      reconnectDelay = 1000;
    });

    ws.addEventListener("message", (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }

      if (msg.type === "init") {
        const curve = msg.equity_curve || [];
        console.log(
          "[ws] init: equity_curve len=%d, first=%o, last=%o, stats=%o",
          curve.length,
          curve[0],
          curve[curve.length - 1],
          msg.stats,
        );
        updateAccount(msg.account);
        updateTodayPnl(msg.today_pnl);
        updatePositions(msg.positions);
        buildChart(curve);
        safe(() => renderStats(msg.stats), "stats");
        safe(() => renderDrawdown(msg.drawdown, msg.account), "drawdown");
        safe(() => renderPerSymbol(msg.per_symbol), "per_symbol");
        safe(() => renderHourlyHeatmap(msg.hourly), "hourly");
        safe(() => renderWeekday(msg.weekday), "weekday");
        safe(() => renderTicks(msg.ticks), "ticks");
      } else if (msg.type === "tick") {
        updateAccount(msg.account);
        updateTodayPnl(msg.today_pnl);
        updatePositions(msg.positions);
        if (msg.equity_point) pushEquityPoint(msg.equity_point);
        safe(() => renderStats(msg.stats), "stats");
        safe(() => renderDrawdown(msg.drawdown, msg.account), "drawdown");
        safe(() => renderPerSymbol(msg.per_symbol), "per_symbol");
        safe(() => renderHourlyHeatmap(msg.hourly), "hourly");
        safe(() => renderWeekday(msg.weekday), "weekday");
        safe(() => renderTicks(msg.ticks), "ticks");
        tickCount += 1;
        els.footerTick.textContent = tickCount;
      } else if (msg.type === "error") {
        console.error("Server error:", msg.message);
      }
    });

    ws.addEventListener("close", () => {
      setConnStatus("disconnected");
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 1.5, 8000);
    });

    ws.addEventListener("error", () => {
      try { ws.close(); } catch {}
    });
  };

  connect();
})();
