/* 起漲日報 —— 前端。資料全部來自 data/ 底下的靜態 JSON。 */

const view = document.getElementById("view");
const dateline = document.getElementById("dateline");

const state = {
  index: null,
  filter: "both",
  sort: "stars",
  query: "",
  detail: null,
};

const MA_SHORT = 20;
const MA_LONG = 60;

/* ------------------------------------------------------------------ 工具 */

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);

const num = (value, digits = 2) =>
  value === null || value === undefined || Number.isNaN(value)
    ? "—"
    : Number(value).toLocaleString("zh-TW", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });

const stars = (count) => "★".repeat(count) + "☆".repeat(5 - count);

const rocDate = (iso) => {
  const [y, m, d] = iso.split("-").map(Number);
  return `民國 ${y - 1911} 年 ${m} 月 ${d} 日`;
};

/* ------------------------------------------------------------------ 日夜版 */

const applyTheme = (theme) => {
  document.documentElement.dataset.theme = theme;
  document.getElementById("theme-toggle").textContent = theme === "night" ? "日" : "夜";
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === "night" ? "#14130f" : "#f6f2e9";
};

document.getElementById("theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "night" ? "day" : "night";
  applyTheme(next);
  try {
    localStorage.setItem("qzdaily-theme", next);
  } catch (_) {
    /* 無痕模式下忽略 */
  }
  if (state.detail) drawDetailCharts(state.detail);
});

try {
  applyTheme(localStorage.getItem("qzdaily-theme") || "day");
} catch (_) {
  applyTheme("day");
}

/* ------------------------------------------------------------------ 載入 */

async function loadIndex() {
  const res = await fetch("data/index.json", { cache: "no-cache" });
  if (!res.ok) throw new Error(`讀取失敗 ${res.status}`);
  return res.json();
}

async function loadStock(code) {
  const res = await fetch(`data/stocks/${code}.json`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`讀取失敗 ${res.status}`);
  return res.json();
}

/* ------------------------------------------------------------------ 報頭 */

function renderDateline() {
  const { data_date, counts, stale } = state.index;
  dateline.innerHTML = `
    <span>${esc(rocDate(data_date))} 收盤</span>
    <span>掃描 <b>${counts.universe.toLocaleString("zh-TW")}</b> 檔</span>
    <span>入選 <b>${counts.selected}</b> 檔</span>
    ${stale ? '<span class="stale">資料未更新</span>' : ""}
  `;
}

/* ------------------------------------------------------------------ 清單 */

function filteredList() {
  const { universe, selected, thresholds } = state.index;
  const byCode = new Map(selected.map((r) => [r.code, r]));

  let rows;
  if (state.filter === "both") {
    rows = selected;
  } else if (state.filter === "fundamental") {
    rows = universe.filter((r) => r.fundamental_passes >= thresholds.min_fundamental);
  } else if (state.filter === "technical") {
    rows = universe.filter((r) => r.technical_passes >= thresholds.min_technical);
  } else {
    rows = universe;
  }

  if (state.query) {
    const q = state.query.trim().toLowerCase();
    rows = rows.filter(
      (r) => r.code.includes(q) || String(r.name).toLowerCase().includes(q)
    );
  }

  const sorted = [...rows];
  if (state.sort === "stars") {
    sorted.sort((a, b) => b.stars - a.stars || (a.pe_percentile ?? 999) - (b.pe_percentile ?? 999));
  } else if (state.sort === "pe") {
    sorted.sort((a, b) => (a.pe_percentile ?? 999) - (b.pe_percentile ?? 999));
  } else {
    sorted.sort((a, b) => a.code.localeCompare(b.code));
  }

  return sorted.map((r) => byCode.get(r.code) || r);
}

function entryHTML(row) {
  const marketLabel = row.market === "TPEX" ? "上櫃" : "上市";
  const pePos =
    row.pe_percentile === null || row.pe_percentile === undefined
      ? "本益比位階 —"
      : `本益比位階 <b>${num(row.pe_percentile, 0)}%</b>`;

  return `
    <article class="entry">
      <button class="entry__head" data-code="${esc(row.code)}">
        <div>
          <div class="entry__name">
            <span class="entry__code">${esc(row.code)}</span>${esc(row.name)}
          </div>
        </div>
        <div>
          <div class="entry__price">${num(row.close)}</div>
          <div class="entry__stars">${stars(row.stars)}</div>
        </div>
        <div class="entry__meta">
          <span>本益比 <b>${num(row.pe)}</b></span>
          <span>${pePos}</span>
          <span>基本面 <b>${row.fundamental_passes}/${state.index.thresholds.fundamental_total}</b></span>
          <span>技術面 <b>${row.technical_passes}/${state.index.thresholds.technical_total}</b></span>
          <span>${marketLabel}</span>
        </div>
      </button>
    </article>
  `;
}

function renderList() {
  const { counts, thresholds } = state.index;
  const rows = filteredList();

  const chips = [
    ["both", "雙面俱到"],
    ["fundamental", "只看基本面"],
    ["technical", "只看技術面"],
    ["all", "全市場"],
  ]
    .map(
      ([key, label]) =>
        `<button class="chip" data-filter="${key}" aria-pressed="${state.filter === key}">${label}</button>`
    )
    .join("");

  const sorts = [
    ["stars", "星等"],
    ["pe", "最便宜"],
    ["code", "代號"],
  ]
    .map(
      ([key, label]) =>
        `<button class="chip" data-sort="${key}" aria-pressed="${state.sort === key}">${label}</button>`
    )
    .join("");

  const body = rows.length
    ? rows.map(entryHTML).join("")
    : `<div class="empty"><span class="empty__mark">〇</span>
         今天沒有符合條件的股票。<br>這是常見的結果,條件嚴格時本來就會有空手的日子。
       </div>`;

  view.innerHTML = `
    <div class="fade-in">
      <div class="summary">
        <div class="summary__cell">
          <div class="summary__num">${counts.selected}</div>
          <div class="summary__label">今日入選</div>
        </div>
        <div class="summary__cell">
          <div class="summary__num">${counts.fundamental_only}</div>
          <div class="summary__label">基本面過關</div>
        </div>
        <div class="summary__cell">
          <div class="summary__num">${counts.technical_only}</div>
          <div class="summary__label">技術面起漲</div>
        </div>
      </div>

      <div class="toolbar">${chips}</div>
      <div class="toolbar">
        <span class="figure__note">排序</span>${sorts}
      </div>

      <div class="search">
        <span class="search__icon">⌕</span>
        <input id="search" type="search" inputmode="search" placeholder="輸入股票代號或名稱查詢任一檔"
               value="${esc(state.query)}" autocomplete="off">
      </div>

      <div id="rows">${body}</div>
    </div>
  `;

  view.querySelectorAll("[data-filter]").forEach((el) =>
    el.addEventListener("click", () => {
      state.filter = el.dataset.filter;
      renderList();
    })
  );
  view.querySelectorAll("[data-sort]").forEach((el) =>
    el.addEventListener("click", () => {
      state.sort = el.dataset.sort;
      renderList();
    })
  );
  view.querySelectorAll("[data-code]").forEach((el) =>
    el.addEventListener("click", () => {
      location.hash = `#/${el.dataset.code}`;
    })
  );

  const search = document.getElementById("search");
  search.addEventListener("input", () => {
    state.query = search.value;
    if (state.query && state.filter === "both") state.filter = "all";
    const rowsEl = document.getElementById("rows");
    const next = filteredList();
    rowsEl.innerHTML = next.length
      ? next.slice(0, 60).map(entryHTML).join("")
      : `<div class="empty"><span class="empty__mark">〇</span>查無此股票</div>`;
    rowsEl.querySelectorAll("[data-code]").forEach((el) =>
      el.addEventListener("click", () => {
        location.hash = `#/${el.dataset.code}`;
      })
    );
    view.querySelectorAll("[data-filter]").forEach((chip) => {
      chip.setAttribute("aria-pressed", state.filter === chip.dataset.filter);
    });
  });
}

/* ------------------------------------------------------------------ 個股 */

function checksHTML(title, checks) {
  const items = checks
    .map(
      (c) => `
      <div class="check ${c.passed ? "check--pass" : "check--fail"}">
        <div class="check__mark">${c.passed ? "✓" : "✗"}</div>
        <div>
          <div class="check__label">${esc(c.label)}</div>
          <div class="check__detail">${esc(c.detail)}</div>
        </div>
      </div>`
    )
    .join("");
  return `<h3 class="checks__title">${esc(title)}</h3><div class="checks">${items}</div>`;
}

function verdictText(result) {
  if (result.excluded_reason) {
    return `這檔未納入篩選:<b>${esc(result.excluded_reason)}</b>。`;
  }
  if (result.selected) {
    return `<b>今日入選。</b>基本面通過 ${result.fundamental_passes} 項、技術面通過 ${result.technical_passes} 項,估值偏低且價量出現轉強跡象。`;
  }
  return `<b>今日未入選。</b>基本面通過 ${result.fundamental_passes} 項、技術面通過 ${result.technical_passes} 項,未同時滿足兩邊門檻。`;
}

function renderDetail(payload) {
  const r = payload.result;
  const marketLabel = payload.market === "TPEX" ? "上櫃" : "上市";

  view.innerHTML = `
    <div class="fade-in">
      <a class="back" href="#/">← 回今日精選</a>
      <div class="detail__head">
        <h2 class="detail__name">
          <span class="detail__code">${esc(payload.code)} · ${marketLabel}</span>
          ${esc(payload.name)}
        </h2>
        <div class="detail__stats">
          <div><div class="stat__label">收盤</div><div class="stat__value">${num(r.close)}</div></div>
          <div><div class="stat__label">本益比</div><div class="stat__value">${num(r.pe)}</div></div>
          <div><div class="stat__label">位階</div><div class="stat__value">${num(r.pe_percentile, 0)}%</div></div>
          <div><div class="stat__label">股價淨值比</div><div class="stat__value">${num(r.pb)}</div></div>
          <div><div class="stat__label">殖利率</div><div class="stat__value">${num(r.yield_pct)}%</div></div>
          <div><div class="stat__label">評等</div><div class="stat__value" style="color:var(--gold)">${stars(r.stars)}</div></div>
        </div>
        <div class="verdict">${verdictText(r)}</div>
      </div>

      <section class="figure">
        <div class="figure__caption">
          <span class="figure__title">日線走勢</span>
          <span class="figure__note">近六個月</span>
        </div>
        <svg class="chart" id="candles" role="img" aria-label="日K線圖"></svg>
        <div class="readout" id="candle-readout"></div>
        <div class="legend">
          <span><i style="background:var(--gold)"></i>${MA_SHORT} 日均線</span>
          <span><i style="background:var(--ink-faint)"></i>${MA_LONG} 日均線</span>
          <span><i style="background:var(--rise)"></i>收紅</span>
          <span><i style="background:var(--fall)"></i>收綠</span>
        </div>
      </section>

      <section class="figure">
        <div class="figure__caption">
          <span class="figure__title">本益比位階</span>
          <span class="figure__note">近三年</span>
        </div>
        <svg class="chart" id="pe" role="img" aria-label="本益比走勢圖"></svg>
        <div class="readout" id="pe-readout"></div>
      </section>

      ${checksHTML("基本面條件", r.fundamental)}
      ${checksHTML("技術面條件", r.technical)}
    </div>
  `;

  state.detail = payload;
  drawDetailCharts(payload);
}

/* ------------------------------------------------------------------ 圖表 */

const movingAverage = (values, window) =>
  values.map((_, i) => {
    if (i + 1 < window) return null;
    let sum = 0;
    for (let k = i + 1 - window; k <= i; k += 1) sum += values[k];
    return sum / window;
  });

function svgEl(tag, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  return el;
}

function drawCandles(svg, candles, readout) {
  const width = svg.clientWidth || svg.parentElement.clientWidth;
  if (!width || !candles.length) return;

  const height = Math.min(360, Math.max(240, Math.round(width * 0.62)));
  const padRight = 44;
  const padBottom = 18;
  const padTop = 9; // 留給最上方的價格刻度,否則文字會被裁掉
  const priceH = Math.round((height - padBottom) * 0.76);
  const volTop = priceH + 12;
  const volH = height - padBottom - volTop;
  const plotW = width - padRight;

  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("height", height);
  svg.textContent = "";

  const closes = candles.map((c) => c[4]);
  const maShort = movingAverage(closes, MA_SHORT);
  const maLong = movingAverage(closes, MA_LONG);

  const lows = candles.map((c) => c[3]);
  const highs = candles.map((c) => c[2]);
  let min = Math.min(...lows);
  let max = Math.max(...highs);
  const pad = (max - min) * 0.06 || 1;
  min -= pad;
  max += pad;

  const maxVol = Math.max(...candles.map((c) => c[5] || 0)) || 1;
  const step = plotW / candles.length;
  const bodyW = Math.max(1.4, step * 0.62);
  const x = (i) => i * step + step / 2;
  const y = (price) => padTop + ((max - price) / (max - min)) * (priceH - padTop);

  for (let t = 0; t <= 4; t += 1) {
    const price = min + ((max - min) * t) / 4;
    const yy = y(price);
    svg.appendChild(svgEl("line", { class: "grid-line", x1: 0, x2: plotW, y1: yy, y2: yy }));
    const label = svgEl("text", { x: plotW + 6, y: yy + 3.5 });
    label.textContent = price.toFixed(price < 50 ? 1 : 0);
    svg.appendChild(label);
  }

  candles.forEach((c, i) => {
    const [, open, high, low, close, volume] = c;
    const cls = close >= open ? "candle-up" : "candle-down";
    svg.appendChild(
      svgEl("line", { class: cls, x1: x(i), x2: x(i), y1: y(high), y2: y(low), "stroke-width": 1 })
    );
    const top = y(Math.max(open, close));
    const bodyH = Math.max(1, Math.abs(y(open) - y(close)));
    svg.appendChild(
      svgEl("rect", { class: cls, x: x(i) - bodyW / 2, y: top, width: bodyW, height: bodyH })
    );
    const vh = ((volume || 0) / maxVol) * volH;
    svg.appendChild(
      svgEl("rect", {
        class: cls,
        x: x(i) - bodyW / 2,
        y: volTop + volH - vh,
        width: bodyW,
        height: vh,
        opacity: 0.45,
      })
    );
  });

  const polyline = (series, cls) => {
    const points = series
      .map((v, i) => (v === null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`))
      .filter(Boolean)
      .join(" ");
    if (points) svg.appendChild(svgEl("polyline", { class: cls, points }));
  };
  polyline(maLong, "ma-long");
  polyline(maShort, "ma-short");

  svg.appendChild(
    svgEl("line", { class: "axis-line", x1: 0, x2: plotW, y1: priceH, y2: priceH })
  );
  svg.appendChild(
    svgEl("line", { class: "axis-line", x1: 0, x2: plotW, y1: height - padBottom, y2: height - padBottom })
  );

  [0, Math.floor(candles.length / 2), candles.length - 1].forEach((i) => {
    const label = svgEl("text", {
      x: Math.min(Math.max(x(i), 14), plotW - 14),
      y: height - 5,
      "text-anchor": "middle",
    });
    label.textContent = candles[i][0].slice(5);
    svg.appendChild(label);
  });

  const cursor = svgEl("line", { class: "cursor-line", y1: 0, y2: height - padBottom, opacity: 0 });
  svg.appendChild(cursor);

  const describe = (i) => {
    const [d, o, h, l, c, v] = candles[i];
    const change = i > 0 ? ((c / candles[i - 1][4] - 1) * 100).toFixed(2) : "0.00";
    readout.textContent =
      `${d}　開 ${num(o)}　高 ${num(h)}　低 ${num(l)}　收 ${num(c)}　` +
      `${change >= 0 ? "+" : ""}${change}%　量 ${num(v, 0)} 張`;
  };

  const handle = (event) => {
    const rect = svg.getBoundingClientRect();
    const px = ((event.touches ? event.touches[0].clientX : event.clientX) - rect.left) *
      (width / rect.width);
    const i = Math.min(candles.length - 1, Math.max(0, Math.round((px - step / 2) / step)));
    cursor.setAttribute("x1", x(i));
    cursor.setAttribute("x2", x(i));
    cursor.setAttribute("opacity", 0.55);
    describe(i);
  };

  svg.addEventListener("pointermove", handle);
  svg.addEventListener("touchmove", handle, { passive: true });
  svg.addEventListener("pointerleave", () => {
    cursor.setAttribute("opacity", 0);
    describe(candles.length - 1);
  });
  describe(candles.length - 1);
}

function drawPe(svg, series, readout) {
  const points = series.filter((row) => row[1] !== null && row[1] > 0);
  const width = svg.clientWidth || svg.parentElement.clientWidth;
  if (!width || points.length < 10) {
    svg.setAttribute("height", 0);
    readout.textContent = "歷史本益比資料不足,無法計算位階。";
    return;
  }

  const height = Math.min(240, Math.max(170, Math.round(width * 0.42)));
  const padRight = 44;
  const padBottom = 18;
  const plotW = width - padRight;
  const plotH = height - padBottom;

  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("height", height);
  svg.textContent = "";

  const values = points.map((p) => p[1]);
  const sorted = [...values].sort((a, b) => a - b);
  const quantile = (q) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))];
  const p40 = quantile(0.4);
  const p80 = quantile(0.8);

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i) => (i / (points.length - 1)) * plotW;
  const y = (v) => ((max - v) / span) * plotH;

  // 便宜區:歷史最低到第 40 百分位
  svg.appendChild(
    svgEl("rect", { class: "band", x: 0, y: y(p40), width: plotW, height: Math.max(0, plotH - y(p40)) })
  );
  [[p40, "第 40 百分位"], [p80, "第 80 百分位"]].forEach(([value, text]) => {
    svg.appendChild(svgEl("line", { class: "band-line", x1: 0, x2: plotW, y1: y(value), y2: y(value) }));
    const label = svgEl("text", { x: plotW + 6, y: y(value) + 3.5 });
    label.textContent = value.toFixed(1);
    label.setAttribute("aria-label", text);
    svg.appendChild(label);
  });

  // 三年日線約 700 點,畫面只有數百像素寬。抽稀後線條才看得出趨勢,
  // 位階計算仍使用完整序列,不受影響。
  const stride = Math.max(1, Math.ceil(points.length / 200));
  const drawn = [];
  points.forEach((p, i) => {
    if (i % stride === 0 || i === points.length - 1) {
      drawn.push(`${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`);
    }
  });
  svg.appendChild(svgEl("polyline", { class: "pe-line", points: drawn.join(" ") }));

  const last = points.length - 1;
  svg.appendChild(svgEl("circle", { class: "marker", cx: x(last), cy: y(points[last][1]), r: 3.5 }));
  svg.appendChild(
    svgEl("line", { class: "axis-line", x1: 0, x2: plotW, y1: plotH, y2: plotH })
  );

  [0, Math.floor(last / 2), last].forEach((i) => {
    const label = svgEl("text", {
      x: Math.min(Math.max(x(i), 26), plotW - 26),
      y: height - 5,
      "text-anchor": "middle",
    });
    label.textContent = points[i][0].slice(0, 7);
    svg.appendChild(label);
  });

  const current = points[last][1];
  const rank = (values.filter((v) => v < current).length / values.length) * 100;
  readout.textContent =
    `目前本益比 ${num(current)},在近三年 ${values.length} 個交易日中位於第 ${rank.toFixed(0)} 百分位` +
    `(區間 ${num(min)} ～ ${num(max)})。`;
}

function drawDetailCharts(payload) {
  const candlesSvg = document.getElementById("candles");
  const peSvg = document.getElementById("pe");
  if (!candlesSvg || !peSvg) return;
  drawCandles(candlesSvg, payload.candles, document.getElementById("candle-readout"));
  drawPe(peSvg, payload.valuation, document.getElementById("pe-readout"));
}

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (state.detail) drawDetailCharts(state.detail);
  }, 180);
});

/* ------------------------------------------------------------------ 路由 */

async function route() {
  const code = location.hash.replace(/^#\/?/, "").trim();
  if (!state.index) return;

  if (!code) {
    state.detail = null;
    renderList();
    window.scrollTo(0, 0);
    return;
  }

  view.innerHTML = '<div class="empty">載入中……</div>';
  try {
    const payload = await loadStock(code);
    renderDetail(payload);
  } catch (_) {
    view.innerHTML = `
      <a class="back" href="#/">← 回今日精選</a>
      <div class="empty"><span class="empty__mark">〇</span>
        找不到 ${esc(code)} 的資料。<br>可能不是上市櫃個股,或當日無交易。
      </div>`;
  }
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", route);

(async () => {
  try {
    state.index = await loadIndex();
    renderDateline();
    route();
  } catch (error) {
    dateline.textContent = "資料載入失敗";
    view.innerHTML = `<div class="notice">無法載入選股資料(${esc(error.message)})。請稍後重新整理。</div>`;
  }
})();
