(function () {
  "use strict";
  var D = JSON.parse(document.getElementById("chart-data").textContent);
  var charts = {};
  var state = { flowCum: true, market: "KOSPI" };

  function tok(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function signed(v, digits) {
    var s = Number(v).toLocaleString("ko-KR", { minimumFractionDigits: digits || 0, maximumFractionDigits: digits || 0 });
    return (v > 0 ? "+" : "") + s;
  }
  function pct(v) { return signed(v, 2) + "%"; }
  function md(iso) { var p = iso.split("-"); return +p[1] + "/" + +p[2]; }
  function signColor(v, T) { return v >= 0 ? T.upFill : T.downFill; }
  function endRadius(v, horizontal) {
    if (horizontal) return v >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4];
    return v >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4];
  }

  function theme() {
    return {
      ink: tok("--ink"), ink2: tok("--ink-2"), muted: tok("--muted"), line: tok("--line"),
      surface: tok("--surface"), upFill: tok("--up-fill"), downFill: tok("--down-fill"),
      up: tok("--up"), down: tok("--down"),
      foreign: tok("--s-foreign"), inst: tok("--s-inst"), kospi: tok("--s-kospi"), kosdaq: tok("--s-kosdaq"),
      v: { together: tok("--v-together"), leader: tok("--v-leader"), solo: tok("--v-solo"), mixed: tok("--v-mixed") },
      font: tok("--font-sans"), mono: tok("--font-mono"),
    };
  }

  function base(T) {
    return {
      animationDuration: 400,
      textStyle: { fontFamily: T.font, color: T.ink2 },
      tooltip: {
        backgroundColor: T.surface, borderColor: T.line, borderWidth: 1, padding: [8, 10],
        textStyle: { color: T.ink, fontSize: 12.5, fontFamily: T.font },
        extraCssText: "box-shadow:0 4px 14px rgba(0,0,0,.12);border-radius:8px;",
        confine: true,
      },
    };
  }
  function valueAxis(T, fmt) {
    return {
      type: "value",
      axisLabel: { color: T.muted, fontSize: 11, fontFamily: T.mono, formatter: fmt },
      splitLine: { lineStyle: { color: T.line } },
      axisLine: { show: false },
    };
  }
  // 막대 끝 숫자 라벨이 들어갈 여유를 양쪽에 둡니다
  function paddedAxis(T, rows, c) {
    var vals = rows.map(function (r) { return r.change_pct; });
    var lo = Math.min(0, Math.min.apply(null, vals)), hi = Math.max(0, Math.max.apply(null, vals));
    // 숫자 라벨(약 56px)이 들어갈 만큼, 그래프 실제 폭에 맞춰 여백 계산
    var plotW = Math.max(c.getWidth() - 110, 120), label = 56;
    var sides = (lo < 0 ? 1 : 0) + (hi > 0 ? 1 : 0);
    var pad = (hi - lo) * label / Math.max(plotW - sides * label, 40) || 1;
    return Object.assign(valueAxis(T, function (v) { return v + "%"; }), {
      min: lo < 0 ? +(lo - pad).toFixed(1) : 0, max: hi > 0 ? +(hi + pad).toFixed(1) : 0,
      axisLabel: { show: false }, splitLine: { show: false },
    });
  }
  function catAxis(T, data, extra) {
    return Object.assign({
      type: "category", data: data,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: T.line } },
      axisLabel: { color: T.ink2, fontSize: 12 },
    }, extra || {});
  }
  function row(color, label, value) {
    return '<div style="display:flex;gap:14px;justify-content:space-between;align-items:center">' +
      '<span><i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:' + color + ';margin-right:6px"></i>' +
      label + "</span><b style=\"font-family:" + tok("--font-mono") + '">' + value + "</b></div>";
  }

  function mount(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    if (charts[id]) charts[id].dispose();
    charts[id] = echarts.init(el, null, { renderer: "svg" });
    return charts[id];
  }

  // 1. 주요 지수 — 가로 막대 (설정 파일 순서 고정)
  function drawIndices(T) {
    var c = mount("c-indices"); if (!c) return;
    var rows = D.indices;
    c.setOption(Object.assign(base(T), {
      grid: { left: 8, right: 8, top: 8, bottom: 8, containLabel: true },
      xAxis: paddedAxis(T, rows, c),
      yAxis: catAxis(T, rows.map(function (r) { return r.name; }), { inverse: true, axisLine: { show: false } }),
      tooltip: Object.assign(base(T).tooltip, {
        trigger: "item",
        formatter: function (p) {
          var r = rows[p.dataIndex];
          return "<b>" + r.name + "</b><br>" +
            row(signColor(r.change_pct, T), "등락률", pct(r.change_pct)) +
            row(T.line, "종가", Number(r.close).toLocaleString("ko-KR", { minimumFractionDigits: 2 })) +
            row(T.line, "비교 구간", md(r.base_date) + " → " + md(r.end_date));
        },
      }),
      series: [{
        type: "bar", barWidth: 14,
        data: rows.map(function (r) {
          return { value: r.change_pct, itemStyle: { color: signColor(r.change_pct, T), borderRadius: endRadius(r.change_pct, true) } };
        }),
        label: {
          show: true, fontFamily: T.mono, fontSize: 11.5,
          formatter: function (p) { return pct(p.value); },
          color: T.ink,
          position: "right",
        },
        labelLayout: function (p) {
          var v = rows[p.dataIndex].change_pct;
          return v < 0 ? { x: p.rect.x - 4, align: "right" } : {};
        },
      }],
    }));
  }

  // 2-a. 순매수 막대 (시장 × 투자자)
  function drawFlows(T) {
    var c = mount("c-flows"); if (!c) return;
    var mk = Object.keys(D.flows.current);
    var who = [["외국인", T.foreign], ["기관", T.inst]];
    c.setOption(Object.assign(base(T), {
      legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10, textStyle: { color: T.ink2 } },
      grid: { left: 8, right: 8, top: 34, bottom: 4, containLabel: true },
      xAxis: catAxis(T, mk),
      // 막대 끝 숫자가 축 글씨와 겹치지 않게 위아래로 여유
      yAxis: Object.assign(valueAxis(T, function (v) { return v.toLocaleString("ko-KR"); }), {
        min: function (v) { return v.min < 0 ? Math.round(v.min * 1.25) : 0; },
        max: function (v) { return v.max > 0 ? Math.round(v.max * 1.25) : 0; },
      }),
      tooltip: Object.assign(base(T).tooltip, {
        trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: "rgba(127,127,127,.08)" } },
        formatter: function (ps) {
          return "<b>" + ps[0].name + "</b> 순매수<br>" + ps.map(function (p) {
            return row(p.color, p.seriesName, signed(p.value) + "억");
          }).join("");
        },
      }),
      series: who.map(function (w) {
        return {
          name: w[0], type: "bar", barWidth: 22, barGap: "30%", color: w[1],
          data: mk.map(function (m) {
            var v = D.flows.current[m][w[0]];
            return { value: v, itemStyle: { borderRadius: endRadius(v, false) } };
          }),
          label: { show: true, position: "outside", fontFamily: T.mono, fontSize: 11, color: T.ink2,
                   formatter: function (p) { return signed(p.value); } },
        };
      }),
    }));
  }

  // 2-b. 수급 추이 선그래프 (누적 / 기간별)
  function drawFlowTrend(T, id, market) {
    var c = mount(id); if (!c) return;
    var tr = D.flows.trend, labels = tr.labels;
    function series(arr) {
      if (!state.flowCum) return arr;
      var s = 0; return arr.map(function (v) { s += v; return s; });
    }
    var who = [["외국인", T.foreign], ["기관", T.inst]];
    var big = who.some(function (w) { return series(tr[market][w[0]]).some(function (v) { return Math.abs(v) >= 10000; }); });
    c.setOption(Object.assign(base(T), {
      title: { text: market, left: 0, top: 0, textStyle: { fontSize: 13, fontWeight: 700, color: T.ink, fontFamily: T.font } },
      legend: { top: 1, right: 0, icon: "roundRect", itemWidth: 10, itemHeight: 3, textStyle: { color: T.ink2, fontSize: 12 } },
      grid: { left: 8, right: 12, top: 32, bottom: 4, containLabel: true },
      xAxis: catAxis(T, labels, { boundaryGap: false, axisLabel: { color: T.muted, fontSize: 11, fontFamily: T.mono, hideOverlap: true } }),
      yAxis: valueAxis(T, function (v) { return big ? (v / 10000).toFixed(1) + "조" : v.toLocaleString("ko-KR"); }),
      tooltip: Object.assign(base(T).tooltip, {
        trigger: "axis", axisPointer: { type: "line", lineStyle: { color: T.muted, type: "dashed" } },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return "<b>" + market + " · " + ps[0].name + "</b>" + (state.flowCum ? " (누적)" : "") + "<br>" + ps.map(function (p) {
            var raw = tr[market][p.seriesName][i];
            var txt = signed(p.value) + "억" + (state.flowCum ? ' <span style="color:' + T.muted + '">(' + D.unit + " " + signed(raw) + ")</span>" : "");
            return row(p.color, p.seriesName, txt);
          }).join("");
        },
      }),
      series: who.map(function (w) {
        var data = series(tr[market][w[0]]);
        return {
          name: w[0], type: "line", color: w[1], data: data, symbol: "circle", symbolSize: 5, showSymbol: false,
          lineStyle: { width: 2 },
          emphasis: { focus: "series" },
          markPoint: {
            symbol: "circle", symbolSize: 8, itemStyle: { color: w[1], borderColor: T.surface, borderWidth: 2 },
            data: [{ coord: [labels.length - 1, data[data.length - 1]] }], label: { show: false },
          },
          markLine: w[0] === "외국인" ? { silent: true, symbol: "none", label: { show: false },
                                           lineStyle: { color: T.muted, width: 1, type: "solid", opacity: .5 }, data: [{ yAxis: 0 }] } : undefined,
        };
      }),
    }));
  }

  // 3. 업종 전체 — 등락률 순 가로 막대
  function drawSectors(T) {
    var c = mount("c-sectors"); if (!c) return;
    var rows = D.sectors[state.market];
    c.setOption(Object.assign(base(T), {
      grid: { left: 8, right: 8, top: 4, bottom: 4, containLabel: true },
      xAxis: paddedAxis(T, rows, c),
      yAxis: catAxis(T, rows.map(function (r) { return r.name; }), { inverse: true, axisLine: { show: false }, axisLabel: { color: T.ink2, fontSize: 11.5, interval: 0 } }),
      tooltip: Object.assign(base(T).tooltip, {
        trigger: "item",
        formatter: function (p) { return "<b>" + p.name + "</b> · " + state.market + "<br>" + row(p.color, "등락률", pct(p.value)) + row(T.line, "순위", (p.dataIndex + 1) + " / " + rows.length); },
      }),
      series: [{
        type: "bar", barWidth: 12,
        data: rows.map(function (r) {
          return { value: r.change_pct, itemStyle: { color: signColor(r.change_pct, T), borderRadius: endRadius(r.change_pct, true) } };
        }),
        label: { show: true, position: "right", fontFamily: T.mono, fontSize: 10.5, color: T.ink2, formatter: function (p) { return pct(p.value); } },
        labelLayout: function (p) { return rows[p.dataIndex].change_pct < 0 ? { x: p.rect.x - 4, align: "right" } : {}; },
      }],
    }));
  }

  // 4. 섹터별 신고가/신저가 종목 수 — 판정별 누적 가로 막대
  function drawHL(T, id, groups, verdicts) {
    var c = mount(id); if (!c) return;
    if (!groups.length) { c.dispose(); delete charts[id]; return; }
    var kinds = Object.keys(verdicts);
    var totals = groups.map(function (g) { return kinds.reduce(function (s, k) { return s + g.counts[k]; }, 0); });
    var series = kinds.map(function (k) {
      return {
        name: verdicts[k], type: "bar", stack: "n", barWidth: 14, color: T.v[k],
        itemStyle: { borderColor: T.surface, borderWidth: 1 },
        data: groups.map(function (g) { return g.counts[k] || null; }),
      };
    });
    series.push({
      name: "합계", type: "bar", stack: "n", data: totals.map(function () { return 0; }), silent: true,
      label: { show: true, position: "right", fontFamily: T.mono, fontSize: 11.5, color: T.ink,
               formatter: function (p) { return totals[p.dataIndex]; } },
      itemStyle: { color: "transparent" },
    });
    c.setOption(Object.assign(base(T), {
      grid: { left: 8, right: 30, top: 4, bottom: 4, containLabel: true },
      xAxis: Object.assign(valueAxis(T), { minInterval: 1 }),
      yAxis: catAxis(T, groups.map(function (g) { return g.sector; }), { inverse: true, axisLine: { show: false }, axisLabel: { color: T.ink2, fontSize: 12, interval: 0 } }),
      tooltip: Object.assign(base(T).tooltip, {
        trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: "rgba(127,127,127,.08)" } },
        formatter: function (ps) {
          var i = ps[0].dataIndex;
          return "<b>" + ps[0].name + "</b> · " + totals[i] + "종목<br>" + ps.filter(function (p) { return p.value && p.seriesName !== "합계"; })
            .map(function (p) { return row(p.color, p.seriesName, p.value + "종목"); }).join("");
        },
      }),
      series: series,
    }));
  }

  // 9. 시장 전체 신용융자 잔고
  function drawCredit(T) {
    var c = mount("c-credit"); if (!c) return;
    var ct = D.creditTrend;
    if (!ct) { c.dispose(); delete charts["c-credit"]; return; }
    var mk = [["KOSPI", T.kospi], ["KOSDAQ", T.kosdaq]];
    c.setOption(Object.assign(base(T), {
      legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 10, itemHeight: 3, textStyle: { color: T.ink2 } },
      grid: { left: 8, right: 44, top: 30, bottom: 4, containLabel: true },
      xAxis: catAxis(T, ct.labels, { boundaryGap: false, axisLabel: { color: T.muted, fontSize: 11, fontFamily: T.mono, hideOverlap: true } }),
      yAxis: Object.assign(valueAxis(T, function (v) { return v + "조"; }), { scale: true }),
      tooltip: Object.assign(base(T).tooltip, {
        trigger: "axis", axisPointer: { type: "line", lineStyle: { color: T.muted, type: "dashed" } },
        formatter: function (ps) {
          return "<b>" + ps[0].name + "</b> 신용융자 잔고<br>" + ps.map(function (p) { return row(p.color, p.seriesName, p.value.toFixed(2) + "조"); }).join("");
        },
      }),
      series: mk.map(function (m) {
        var data = ct[m[0]];
        return {
          name: m[0], type: "line", color: m[1], data: data, showSymbol: false, symbolSize: 5, lineStyle: { width: 2 },
          endLabel: { show: true, fontFamily: T.mono, fontSize: 11, color: T.ink2, formatter: function (p) { return p.value.toFixed(1); } },
        };
      }),
    }));
  }

  // 나스닥 급등 상위 — 가로 막대
  function drawUsGainers(T) {
    var c = mount("c-us-gainers"); if (!c) return;
    var rows = D.usGainers;
    c.setOption(Object.assign(base(T), {
      grid: { left: 8, right: 8, top: 4, bottom: 4, containLabel: true },
      xAxis: paddedAxis(T, rows.map(function (r) { return { change_pct: r.pct }; }), c),
      yAxis: catAxis(T, rows.map(function (r) { return r.ticker; }), { inverse: true, axisLine: { show: false },
                     axisLabel: { color: T.ink, fontSize: 11.5, fontFamily: T.mono, interval: 0 } }),
      tooltip: Object.assign(base(T).tooltip, {
        trigger: "item",
        formatter: function (p) {
          var r = rows[p.dataIndex];
          return "<b>" + r.ticker + "</b> " + r.name + (r.high ? " · 52주 신고가" : "") + "<br>" + row(p.color, "등락률", pct(r.pct));
        },
      }),
      series: [{
        type: "bar", barWidth: 12,
        data: rows.map(function (r) { return { value: r.pct, itemStyle: { color: signColor(r.pct, T), borderRadius: endRadius(r.pct, true) } }; }),
        label: { show: true, position: "right", fontFamily: T.mono, fontSize: 11, color: T.ink2, formatter: function (p) { return pct(p.value); } },
      }],
    }));
  }

  // 나스닥 신고가 — 섹터별 종목 수
  function drawUsHighs(T) {
    var c = mount("c-us-highs"); if (!c) return;
    var rows = D.usHighSectors;
    c.setOption(Object.assign(base(T), {
      grid: { left: 8, right: 30, top: 4, bottom: 4, containLabel: true },
      xAxis: Object.assign(valueAxis(T), { minInterval: 1 }),
      yAxis: catAxis(T, rows.map(function (r) { return r[0]; }), { inverse: true, axisLine: { show: false }, axisLabel: { color: T.ink2, fontSize: 12, interval: 0 } }),
      tooltip: Object.assign(base(T).tooltip, {
        trigger: "item", formatter: function (p) { return "<b>" + p.name + "</b><br>" + row(p.color, "신고가", p.value + "종목"); },
      }),
      series: [{
        type: "bar", barWidth: 12, color: T.upFill,
        itemStyle: { borderRadius: [0, 4, 4, 0] },
        data: rows.map(function (r) { return r[1]; }),
        label: { show: true, position: "right", fontFamily: T.mono, fontSize: 11.5, color: T.ink },
      }],
    }));
  }

  function drawAll() {
    if (typeof echarts === "undefined") return;
    var T = theme();
    drawIndices(T);
    drawFlows(T);
    drawFlowTrend(T, "c-flow-kospi", "KOSPI");
    drawFlowTrend(T, "c-flow-kosdaq", "KOSDAQ");
    drawSectors(T);
    drawHL(T, "c-highs", D.highGroups, D.highVerdicts);
    drawHL(T, "c-lows", D.lowGroups, D.lowVerdicts);
    drawCredit(T);
    drawUsGainers(T);
    drawUsHighs(T);
  }

  // ── 버튼 ──
  function press(group, btn) {
    group.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", String(b === btn)); });
  }
  var cum = document.getElementById("flow-cum"), each = document.getElementById("flow-each");
  [cum, each].forEach(function (b) {
    b && b.addEventListener("click", function () {
      state.flowCum = b === cum; press(b.parentNode, b);
      var T = theme(); drawFlowTrend(T, "c-flow-kospi", "KOSPI"); drawFlowTrend(T, "c-flow-kosdaq", "KOSDAQ");
    });
  });
  document.querySelectorAll("[data-market]").forEach(function (b) {
    b.addEventListener("click", function () {
      state.market = b.dataset.market; press(b.parentNode, b);
      document.querySelectorAll("[data-sector-market]").forEach(function (el) { el.hidden = el.dataset.sectorMarket !== state.market; });
      drawSectors(theme());
    });
  });
  document.querySelectorAll("[data-hl]").forEach(function (b) {
    b.addEventListener("click", function () {
      press(b.parentNode, b);
      document.querySelectorAll("[data-hl-panel]").forEach(function (el) { el.hidden = el.dataset.hlPanel !== b.dataset.hl; });
    });
  });

  // ── 크기·테마 변화에 맞춰 다시 그리기 ──
  if (window.ResizeObserver) {
    var ro = new ResizeObserver(function (entries) {
      entries.forEach(function (e) { var c = charts[e.target.id]; if (c) c.resize(); });
    });
    document.querySelectorAll(".chart").forEach(function (el) { ro.observe(el); });
  }
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    (mq.addEventListener ? mq.addEventListener.bind(mq, "change") : mq.addListener.bind(mq))(drawAll);
  }
  new MutationObserver(drawAll).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  drawAll();
})();
