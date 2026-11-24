"use strict";

const api = (path, opts) =>
  fetch(path, opts).then((r) => {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  });

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function platformLabel(p) {
  return (p.platform === "xiaohongshu") ? "小红书" : "B站";
}

/* ---------------- 头像 / 队徽渲染 ----------------
   有图用 <img>，加载失败或无图回退彩色首字母徽章。 */
function abbr(name) {
  const words = String(name || "").split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  if (words.length === 1) return words[0].slice(0, 3).toUpperCase();
  return words.map((w) => w[0]).join("").slice(0, 3).toUpperCase();
}

function imgFallback(img, text, color, cls) {
  const span = document.createElement("span");
  span.className = cls || "avatar-fallback";
  span.style.background = color || "#3a4170";
  span.textContent = text;
  img.replaceWith(span);
}

function onerr(text, color, cls) {
  return "imgFallback(this,'" + escapeHtml(String(text)).replace(/'/g, "\\'") +
    "','" + escapeHtml(String(color || "")) + "','" + (cls || "avatar-fallback") + "')";
}

function avatarHtml(url, text, color) {
  if (!url) {
    return '<span class="avatar-fallback" style="background:' + (color || "#3a4170") + '">' +
      escapeHtml(text) + "</span>";
  }
  return '<img class="avatar" src="' + escapeHtml(url) + '" loading="lazy" alt="" onerror="' +
    onerr(text, color, "avatar-fallback") + '">';
}

function logoHtml(logo, teamName, color) {
  const text = abbr(teamName);
  if (!logo) {
    return '<span class="tlogo-fallback" style="background:' + (color || "#3a4170") + '">' +
      escapeHtml(text) + "</span>";
  }
  return '<img class="tlogo" src="' + escapeHtml(logo) + '" loading="lazy" alt="' +
    escapeHtml(teamName) + '" onerror="' + onerr(text, color, "tlogo-fallback") + '">';
}

/* ---------------- 顶层 Tab 切换 ---------------- */
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "posts") loadPosts();
    if (btn.dataset.tab === "ups") loadUps();
    if (btn.dataset.tab === "calendar") loadCalendar();
    if (btn.dataset.tab === "favs") loadFavs();
  });
});

document.querySelectorAll(".subtab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".subtab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".sub-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("sub-" + btn.dataset.sub).classList.add("active");
    if (btn.dataset.sub === "standings") loadStandings();
    if (btn.dataset.sub === "results") loadResults();
    if (btn.dataset.sub === "trend") loadTrend();
    if (btn.dataset.sub === "compare") loadDrivers();
  });
});

/* ---------------- 积分榜 ---------------- */
let currentStandingType = "drivers";
window._seasons = [];
window._raceLists = {};
window._standingsCache = {};

function loadStandings() {
  const el = document.getElementById("sub-standings");
  if (el.dataset.ready === "1") { renderStandings(); return; }
  el.innerHTML = '<div class="loading">加载中…</div>';
  api("/api/f1/seasons").then((seasons) => {
    window._seasons = seasons.filter((y) => y >= 1950).sort((a, b) => b - a);
    const latest = window._seasons[0];
    el.innerHTML =
      '<div class="toggle">' +
      '<button id="st-drivers" class="on" onclick="setStandingType(\'drivers\')">车手积分榜</button>' +
      '<button id="st-constructors" onclick="setStandingType(\'constructors\')">车队积分榜</button></div>' +
      '<div class="filters">' +
      '<label>赛季 <select id="std-season-select"></select></label>' +
      '<label>分站 <select id="std-round-select"><option value="">当前</option></select></label></div>' +
      '<div id="std-table"></div>';
    const s = document.getElementById("std-season-select");
    window._seasons.forEach((y) => {
      const o = document.createElement("option"); o.value = y; o.textContent = y; s.appendChild(o);
    });
    s.value = latest;
    s.addEventListener("change", () => onStdSeasonChange(s.value));
    document.getElementById("std-round-select").addEventListener("change", () => fetchAndRenderStandings());
    el.dataset.ready = "1";
    fetchAndRenderStandings();
  }).catch((e) => { el.innerHTML = '<div class="error">加载失败: ' + escapeHtml(e) + "</div>"; });
}

function stdQuery() {
  return {
    season: document.getElementById("std-season-select").value,
    round: document.getElementById("std-round-select").value,
  };
}

function onStdSeasonChange(season) {
  const roundSel = document.getElementById("std-round-select");
  roundSel.innerHTML = '<option value="">当前</option>';
  roundSel.value = "";
  const fill = (races) => races.forEach((r) => {
    const o = document.createElement("option");
    o.value = r.round;
    o.textContent = "R" + r.round + " " + r.raceName;
    roundSel.appendChild(o);
  });
  const cached = window._raceLists[season];
  if (cached) { fill(cached); fetchAndRenderStandings(); return; }
  api("/api/f1/season/" + season + "/races").then((races) => {
    window._raceLists[season] = races;
    fill(races);
    fetchAndRenderStandings();
  }).catch(() => { fetchAndRenderStandings(); });
}

function fetchAndRenderStandings() {
  const el = document.getElementById("std-table");
  const { season, round } = stdQuery();
  const key = currentStandingType + "|" + season + "|" + round;
  if (window._standingsCache[key]) { renderStandings(); return; }
  el.innerHTML = '<div class="loading">加载中…</div>';
  const params = new URLSearchParams();
  if (season) params.set("season", season);
  if (round) params.set("round", round);
  const qs = params.toString();
  api("/api/f1/standings/" + currentStandingType + (qs ? "?" + qs : "")).then((data) => {
    window._standingsCache[key] = data;
    renderStandings();
  }).catch((e) => { el.innerHTML = '<div class="error">加载失败: ' + escapeHtml(e) + "</div>"; });
}

function setStandingType(t) {
  currentStandingType = t;
  document.getElementById("st-drivers").className = t === "drivers" ? "on" : "";
  document.getElementById("st-constructors").className = t === "constructors" ? "on" : "";
  fetchAndRenderStandings();
}

function renderStandings() {
  const el = document.getElementById("std-table");
  const { season, round } = stdQuery();
  const data = window._standingsCache[currentStandingType + "|" + season + "|" + round] || [];
  const isDrivers = currentStandingType === "drivers";
  if (!data.length) { el.innerHTML = '<div class="empty">该筛选条件下暂无数据</div>'; return; }
  let html = '<table class="tbl"><thead><tr><th>#</th><th>' + (isDrivers ? "车手" : "车队") + "</th>" +
    (isDrivers ? "<th>车队</th>" : "") + "<th>积分</th><th>胜场</th><th>领奖台</th><th>杆位</th></tr></thead><tbody>";
  data.forEach((r) => {
    if (isDrivers) {
      const avatar = avatarHtml(r.headshot, r.code || abbr(r.name), r.teamColor);
      const logo = logoHtml(r.teamLogo, r.constructor, r.teamColor);
      html += "<tr><td>" + r.position + "</td><td>" + avatar + escapeHtml(r.name) +
        ' <span class="muted">' + escapeHtml(r.code || "") + "</span></td><td>" +
        logo + escapeHtml(r.constructor) + "</td>";
    } else {
      const logo = logoHtml(r.logo, r.name, r.color);
      html += "<tr><td>" + r.position + "</td><td>" + logo + escapeHtml(r.name) + "</td>";
    }
    html += "<td>" + r.points + "</td><td>" + r.wins + "</td><td>" + (r.podiums ?? 0) + "</td><td>" + (r.poles ?? 0) + "</td></tr>";
  });
  html += "</tbody></table>";
  el.innerHTML = html;
}

/* ---------------- 每站结果 ---------------- */
function loadResults() {
  const el = document.getElementById("sub-results");
  if (el.dataset.ready === "1") return;
  el.innerHTML = '<div class="loading">加载中…</div>';
  api("/api/f1/seasons").then((seasons) => {
    const list = seasons.filter((y) => y >= 1950).sort((a, b) => b - a);
    const latest = list[0];
    el.innerHTML = '<div class="filters">' +
      '<label>赛季 <select id="season-select"></select></label>' +
      '<label>分站 <select id="round-select"></select></label></div>' +
      '<div id="race-detail"></div>';
    const s = document.getElementById("season-select");
    list.forEach((y) => { const o = document.createElement("option"); o.value = y; o.textContent = y; s.appendChild(o); });
    s.value = latest;
    s.addEventListener("change", () => loadSeasonRaces(s.value));
    document.getElementById("round-select").addEventListener("change", () => {
      const v = document.getElementById("round-select").value;
      if (v) loadRace(document.getElementById("season-select").value, v);
    });
    el.dataset.ready = "1";
    loadSeasonRaces(latest);
  }).catch((e) => { el.innerHTML = '<div class="error">加载失败: ' + escapeHtml(e) + "</div>"; });
}

function loadSeasonRaces(season) {
  const roundSel = document.getElementById("round-select");
  const detail = document.getElementById("race-detail");
  roundSel.innerHTML = "";
  detail.innerHTML = '<div class="loading">加载中…</div>';
  api("/api/f1/season/" + season + "/races").then((races) => {
    races.forEach((r) => {
      const o = document.createElement("option");
      o.value = r.round; o.textContent = "R" + r.round + " " + r.raceName;
      roundSel.appendChild(o);
    });
    if (!races.length) {
      detail.innerHTML = '<div class="empty">该赛季暂无数据</div>';
      return;
    }
    // 默认选中最近一场已开赛的分站（未开赛的分站没有结果数据）
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const run = races.filter((r) => new Date(r.date) <= today);
    const target = run.length ? run[run.length - 1] : races[0];
    roundSel.value = target.round;
    loadRace(season, target.round);
  }).catch((e) => { detail.innerHTML = '<div class="error">加载失败: ' + escapeHtml(e) + "</div>"; });
}

function loadRace(season, round) {
  const detail = document.getElementById("race-detail");
  detail.innerHTML = '<div class="loading">加载中…</div>';
  api("/api/f1/season/" + season + "/race/" + round + "/results").then((race) => {
    renderRace(race);
  }).catch((e) => { detail.innerHTML = '<div class="error">加载失败: ' + escapeHtml(e) + "</div>"; });
}

let currentRaceTab = "race";
window._raceData = null;

function renderRace(race) {
  const detail = document.getElementById("race-detail");
  if (!race) {
    detail.innerHTML = '<div class="empty">该分站暂无数据（可能尚未开赛）</div>';
    return;
  }
  window._raceData = race;
  currentRaceTab = "race";
  const fl = race.fastestLap
    ? escapeHtml(race.fastestLap.driver) + " " + escapeHtml(race.fastestLap.time) + "（第 " + race.fastestLap.lap + " 圈）"
    : "—";
  let html = "<h3>" + race.season + " R" + race.round + " · " + escapeHtml(race.raceName) + "</h3>" +
    '<div class="meta">' + escapeHtml(race.circuit) + " · " + escapeHtml(race.country) + " · " + race.date + "</div>" +
    '<div class="fastestlap">最快圈速：' + fl + "</div>";
  const tabs = [];
  tabs.push("race");
  if (race.qualifying) tabs.push("qualifying");
  if (race.sprint) tabs.push("sprint");
  if (tabs.length > 1) {
    html += '<div class="race-tabs">';
    tabs.forEach((t) => {
      html += '<button id="rt-' + t + '" class="' + (t === "race" ? "on" : "") +
        '" onclick="setRaceTab(\'' + t + '\')">' + ({ race: "正赛", qualifying: "排位赛", sprint: "冲刺赛" })[t] + "</button>";
    });
    html += "</div>";
  }
  html += '<div id="race-table"></div>';
  detail.innerHTML = html;
  renderRaceTable("race");
}

function setRaceTab(t) {
  currentRaceTab = t;
  ["race", "qualifying", "sprint"].forEach((k) => {
    const b = document.getElementById("rt-" + k);
    if (b) b.className = t === k ? "on" : "";
  });
  renderRaceTable(t);
}

function renderRaceTable(type) {
  const box = document.getElementById("race-table");
  const race = window._raceData;
  if (!box || !race) return;
  if (type === "qualifying") {
    let html = '<table class="tbl"><thead><tr><th>#</th><th>车手</th><th>车队</th><th>Q1</th><th>Q2</th><th>Q3</th></tr></thead><tbody>';
    race.qualifying.forEach((r) => {
      const podium = ["1", "2", "3"].includes(r.position) ? " podium-" + r.position : "";
      html += '<tr class="' + podium + '"><td>' + r.position + "</td><td>" +
        avatarHtml(r.headshot, r.code || abbr(r.name), r.color) + escapeHtml(r.name) +
        ' <span class="muted">' + escapeHtml(r.code || "") + "</span></td><td>" +
        logoHtml(r.logo, r.constructor, r.color) + escapeHtml(r.constructor) + "</td><td>" +
        (r.q1 || "—") + "</td><td>" + (r.q2 || "—") + "</td><td>" + (r.q3 || "—") + "</td></tr>";
    });
    box.innerHTML = html + "</tbody></table>";
    return;
  }
  if (type === "sprint") {
    let html = '<table class="tbl"><thead><tr><th>#</th><th>车手</th><th>车队</th><th>发车位</th><th>圈数</th><th>状态</th><th>积分</th></tr></thead><tbody>';
    race.sprint.forEach((r) => {
      const podium = ["1", "2", "3"].includes(r.position) ? " podium-" + r.position : "";
      html += '<tr class="' + podium + '"><td>' + r.position + "</td><td>" +
        avatarHtml(r.headshot, r.code || abbr(r.name), r.color) + escapeHtml(r.name) +
        ' <span class="muted">' + escapeHtml(r.code || "") + "</span></td><td>" +
        logoHtml(r.logo, r.constructor, r.color) + escapeHtml(r.constructor) + "</td><td>" +
        r.grid + "</td><td>" + r.laps + "</td><td>" + escapeHtml(r.status) + "</td><td>" + r.points + "</td></tr>";
    });
    box.innerHTML = html + "</tbody></table>";
    return;
  }
  let html = '<table class="tbl"><thead><tr><th>#</th><th>车手</th><th>车队</th><th>发车位</th><th>圈数</th><th>状态</th><th>积分</th><th>最快圈</th></tr></thead><tbody>';
  race.results.forEach((r) => {
    const isFl = r.flRank === "1";
    const podium = ["1", "2", "3"].includes(r.position) ? " podium-" + r.position : "";
    html += '<tr class="' + (isFl ? "fl-row " : "") + podium + '"><td>' + r.position + "</td><td>" +
      avatarHtml(r.headshot, r.code || abbr(r.name), r.color) + escapeHtml(r.name) +
      ' <span class="muted">' + escapeHtml(r.code || "") + "</span></td><td>" +
      logoHtml(r.logo, r.constructor, r.color) + escapeHtml(r.constructor) + "</td><td>" +
      r.grid + "</td><td>" + r.laps + "</td><td>" + escapeHtml(r.status) + "</td><td>" +
      r.points + "</td><td>" + (r.flTime || "—") + "</td></tr>";
  });
  box.innerHTML = html + "</tbody></table>";
}

/* ---------------- 车手对比 ---------------- */
let driverMap = {};
let driversLoaded = false;

function loadDrivers() {
  const el = document.getElementById("sub-compare");
  if (!el.querySelector(".compare-box")) {
    el.innerHTML = '<div class="compare-box">' +
      '<div class="compare-driver-inputs">' +
      '<input id="driver1" list="drivers-datalist" placeholder="选择车手 1（可输入姓名搜索）">' +
      '<input id="driver2" list="drivers-datalist" placeholder="选择车手 2（可输入姓名搜索）">' +
      "</div>" +
      '<button class="primary" id="btn-compare">对比</button>' +
      '<div id="compare-result" style="margin-top:16px"></div></div>';
    document.getElementById("btn-compare").addEventListener("click", doCompare);
  }
  if (driversLoaded) return;
  api("/api/f1/drivers").then((list) => {
    const dl = document.getElementById("drivers-datalist");
    list.forEach((d) => {
      const code = d.code || d.driverId;
      const display = d.givenName + " " + d.familyName + " (" + code + ")";
      driverMap[display] = d.driverId;
      const opt = document.createElement("option");
      opt.value = display;
      opt.label = d.givenName + " " + d.familyName + " · " + d.nationality;
      dl.appendChild(opt);
    });
    driversLoaded = true;
  }).catch(() => {});
}

function doCompare() {
  const out = document.getElementById("compare-result");
  const id1 = driverMap[document.getElementById("driver1").value.trim()];
  const id2 = driverMap[document.getElementById("driver2").value.trim()];
  if (!id1 || !id2) {
    out.innerHTML = '<div class="error">请从下拉列表中各选择一位车手</div>';
    return;
  }
  out.innerHTML = '<div class="loading">对比中…（首次会拉取完整生涯数据，稍等）</div>';
  api("/api/f1/compare?d1=" + encodeURIComponent(id1) + "&d2=" + encodeURIComponent(id2))
    .then((data) => renderCompare(data, out))
    .catch((e) => { out.innerHTML = '<div class="error">对比失败: ' + escapeHtml(e) + "</div>"; });
}

function renderCompare(data, out) {
  const [a, b] = data.drivers;
  const stats = [
    ["国籍", "nationality"], ["活跃赛季", "seasons"], ["参赛场次", "starts"],
    ["世界冠军", "championships"], ["分站冠军", "wins"], ["领奖台", "podiums"],
    ["杆位", "poles"], ["最快圈", "fastestLaps"], ["生涯积分", "points"],
  ];
  let html = '<div class="compare-head"><div></div>' +
    '<div class="compare-driver">' + escapeHtml(a.name) + ' <span class="muted">' + escapeHtml(a.code || "") + "</span></div>" +
    '<div class="compare-driver">' + escapeHtml(b.name) + ' <span class="muted">' + escapeHtml(b.code || "") + "</span></div></div>";
  for (const [label, key] of stats) {
    const va = a[key], vb = b[key];
    let ca = "", cb = "";
    if (typeof va === "number" && typeof vb === "number") {
      if (va > vb) ca = "better";
      else if (vb > va) cb = "better";
    }
    html += '<div class="compare-row"><div class="c-label">' + label + "</div>" +
      '<div class="c-val ' + ca + '">' + va + "</div>" +
      '<div class="c-val ' + cb + '">' + vb + "</div></div>";
  }

  const seasons = new Set();
  a.seasonBreakdown.forEach((x) => seasons.add(x.season));
  b.seasonBreakdown.forEach((x) => seasons.add(x.season));
  const sorted = [...seasons].sort();
  const head = (d) => escapeHtml(d.code || d.name);
  html += '<h3 style="margin-top:24px">逐年对比（胜场 / 积分）</h3>' +
    '<table class="tbl"><thead><tr><th>赛季</th><th>' + head(a) + "</th><th>" + head(b) + "</th></tr></thead><tbody>";
  for (const s of sorted) {
    const ra = a.seasonBreakdown.find((x) => x.season === s);
    const rb = b.seasonBreakdown.find((x) => x.season === s);
    html += "<tr><td>" + s + "</td><td>" + (ra ? ra.wins + " 胜 / " + ra.points + " 分" : "—") + "</td><td>" +
      (rb ? rb.wins + " 胜 / " + rb.points + " 分" : "—") + "</td></tr>";
  }
  html += "</tbody></table>";
  out.innerHTML = html;
}

/* ---------------- 帖子分析 ---------------- */
const SEASON_WIDE = "赛季整体";
window._posts = [];

function opStances(p) {
  const s = new Set();
  try {
    const arr = JSON.parse(p.comment_summary || "[]");
    if (Array.isArray(arr)) {
      arr.forEach((c) => { if (c && c.stance) s.add(c.stance); });
    }
  } catch (e) {}
  return s;
}

function loadPosts() {
  const el = document.getElementById("posts-list");
  el.innerHTML = '<div class="loading">加载中…</div>';
  api("/api/posts").then((posts) => {
    window._posts = posts;
    buildPostsFilter(posts);
    renderPosts();
  }).catch((e) => { el.innerHTML = '<div class="error">加载失败: ' + escapeHtml(e) + "</div>"; });
}

function buildPostsFilter(posts) {
  const sel = document.getElementById("posts-race-filter");
  const names = new Set();
  let hasSeasonWide = false;
  posts.forEach((p) => {
    const r = p.race || SEASON_WIDE;
    if (r === SEASON_WIDE) { hasSeasonWide = true; return; }
    names.add(r);
  });
  sel.innerHTML = '<option value="">全部帖子</option>';
  if (hasSeasonWide) {
    const o = document.createElement("option");
    o.value = SEASON_WIDE; o.textContent = SEASON_WIDE;
    sel.appendChild(o);
  }
  [...names].sort().forEach((n) => {
    const o = document.createElement("option");
    o.value = n; o.textContent = n;
    sel.appendChild(o);
  });
  sel.onchange = () => renderPosts();

  // 时间（年月）筛选：按发布时间倒序，方便区分今年与往年（17 年、25 年…）的帖子
  const tsel = document.getElementById("posts-time-filter");
  const months = new Set();
  posts.forEach((p) => {
    const m = String(p.published_at || "").slice(0, 7);
    if (m) months.add(m);
  });
  tsel.innerHTML = '<option value="">全部时间</option>';
  [...months].sort().reverse().forEach((m) => {
    const o = document.createElement("option");
    o.value = m; o.textContent = m;
    tsel.appendChild(o);
  });
  tsel.onchange = () => renderPosts();

  // 立场筛选：筛选「含该立场观点簇」的帖子（无观点汇总的帖子不参与）
  const fsel = document.getElementById("posts-stance-filter");
  fsel.onchange = () => renderPosts();
}

function renderPosts() {
  const el = document.getElementById("posts-list");
  const race = document.getElementById("posts-race-filter").value;
  const ym = document.getElementById("posts-time-filter").value;
  const st = document.getElementById("posts-stance-filter").value;
  // 分站/时间/立场三条件过滤；列表按发布时间倒序（无日期的排最后）
  const posts = window._posts
    .filter((p) => (!race || (p.race || SEASON_WIDE) === race) &&
                  (!ym || String(p.published_at || "").startsWith(ym)) &&
                  (!st || opStances(p).has(st)))
    .sort((a, b) => (b.published_at || "").localeCompare(a.published_at || "") ||
                    ((b.id || 0) - (a.id || 0)));
  if (!window._posts.length) {
    el.innerHTML = '<div class="empty">还没有抓取到帖子，点上方「手动抓取一次」试试。</div>';
    return;
  }
  if (!posts.length) { el.innerHTML = '<div class="empty">该筛选条件下暂无相关帖子</div>'; return; }
  el.innerHTML = posts.map((p) => {
    const hasOp = !!p.comment_summary;
    return (
      '<article class="post-card"' + (hasOp ? ' onclick="openOpModal(' + p.id + ', &quot;posts&quot;)"' : "") + ">" +
      '<div class="post-top"><span class="platform">' + platformLabel(p) + "</span>" +
      '<span class="race">' + escapeHtml(p.race || SEASON_WIDE) + "</span>" +
      '<span class="cat">' + escapeHtml(p.category || "") + "</span>" +
      (hasOp ? '<span class="op-badge">观点</span>' : "") +
      favBtn("post", p.id) + "</div>" +
      '<a class="post-title" href="' + (hasOp ? "javascript:void(0)" : escapeHtml(p.url || "#")) + '"' +
      (hasOp ? "" : ' target="_blank" rel="noopener"') + ">" +
      escapeHtml(p.title || "无标题") + "</a>" +
      '<div class="post-author">' + escapeHtml(p.author || "") + " · " + escapeHtml(p.published_at || "") + "</div>" +
      '<div class="post-summary">' + escapeHtml(p.summary || p.raw_text || "") + "</div>" +
      (hasOp
        ? '<span class="jump">查看评论区观点 →</span>'
        : '<a class="jump" href="' + escapeHtml(p.url || "#") + '" target="_blank" rel="noopener">去原帖 →</a>') +
      "</article>"
    );
  }).join("");
}

async function submitScrape(path, st, runMsg, pollFn) {
  st.textContent = "提交抓取任务…";
  try {
    let res = await fetch(path, {
      method: "POST",
      headers: { "X-Scrape-Token": localStorage.getItem("scrapeToken") || "" },
    });
    if (res.status === 403) {
      const token = prompt("此站点开启了抓取口令，请输入口令：");
      if (token === null) { st.textContent = "已取消"; return; }
      res = await fetch(path, { method: "POST", headers: { "X-Scrape-Token": token } });
      if (res.status === 403) { st.textContent = "口令不正确"; return; }
      localStorage.setItem("scrapeToken", token);
    }
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (data.busy) {
      st.textContent = "已有抓取任务在运行，请稍后再试";
      return;
    }
    st.textContent = runMsg;
    let tries = 0;
    const iv = setInterval(() => {
      tries += 1;
      pollFn();
      if (tries >= 8) clearInterval(iv);
    }, 60000);
  } catch (e) {
    st.textContent = "抓取失败: " + e;
  }
}

document.getElementById("btn-scrape").addEventListener("click", () => {
  submitScrape("/api/scrape", document.getElementById("scrape-status"),
    "抓取任务已启动（逐站扫描约需几分钟），完成后列表会自动更新", loadPosts);
});

document.getElementById("btn-scrape-xhs").addEventListener("click", () => {
  submitScrape("/api/scrape/xhs", document.getElementById("scrape-status"),
    "小红书抓取已启动（约需 1~2 分钟），完成后列表会自动更新", loadPosts);
});

function showSchedulerStatus() {
  api("/api/scheduler/status").then((s) => {
    const el = document.getElementById("scheduler-status");
    if (!s.running) {
      el.textContent = "定时抓取未启用";
      return;
    }
    el.textContent = "帖子抓取：每 " + s.intervalHours + " 小时（下次 " + (s.nextRun || "—") + "）· 小红书每 " + (s.xhsIntervalHours || "—") + " 小时（下次 " + (s.xhsNextRun || "—") + "）";
    const upsEl = document.getElementById("ups-scheduler-status");
    if (upsEl) {
      upsEl.textContent = "UP 订阅检查：每 " + s.upIntervalHours + " 小时（下次 " + (s.upNextRun || "—") + "）";
    }
  }).catch(() => {});
}

/* ---------------- UP 订阅 ---------------- */
window._ups = [];
window._myUps = [];
window._upPosts = [];
window._me = null;

function upsStatus(text) {
  const el = document.getElementById("ups-status");
  if (el) el.textContent = text;
}

function upToken() {
  return localStorage.getItem("upToken") || "";
}

async function apiAuth(path, opts) {
  const headers = Object.assign(
    { Authorization: "Bearer " + upToken(), "Content-Type": "application/json" },
    (opts && opts.headers) || {}
  );
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  if (res.status === 401) {
    window._me = null;
    localStorage.removeItem("upToken");
    renderNavAuth();
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || "登录已过期，请重新登录");
  }
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || ("HTTP " + res.status));
  }
  return res.json();
}

function renderNavAuth() {
  const guest = document.getElementById("nav-auth-guest");
  const user = document.getElementById("nav-auth-user");
  const nameEl = document.getElementById("nav-auth-name");
  if (window._me) {
    guest.style.display = "none";
    user.style.display = "";
    nameEl.textContent = window._me;
  } else {
    guest.style.display = "";
    user.style.display = "none";
  }
}

/* ---------------- 我的收藏 ---------------- */
window._favs = { post: [], up: [] };

async function loadFavIds() {
  if (!window._me) {
    window._favs = { post: [], up: [] };
    return;
  }
  try {
    const ids = await apiAuth("/api/favs/ids");
    window._favs = { post: ids.post || [], up: ids.up || [] };
  } catch (e) {
    window._favs = { post: [], up: [] };
  }
}

function isFav(type, id) {
  const key = type === "post" ? "post" : "up";
  return (window._favs[key] || []).includes(id);
}

function favBtn(type, id) {
  return '<button class="fav-btn' + (isFav(type, id) ? " on" : "") +
    '" title="' + (isFav(type, id) ? "取消收藏" : "收藏") +
    '" onclick="toggleFav(event, \'' + type + "', " + id + ')">' +
    (isFav(type, id) ? "♥" : "♡") + "</button>";
}

async function toggleFav(ev, type, id) {
  ev.stopPropagation();
  ev.preventDefault();
  if (!window._me) {
    openAuthModal("login");
    authError("登录后才能使用收藏功能");
    return;
  }
  const key = type === "post" ? "post" : "up";
  const has = isFav(type, id);
  try {
    await apiAuth("/api/favs/" + type + "/" + id, { method: has ? "DELETE" : "POST" });
    window._favs[key] = has
      ? window._favs[key].filter((x) => x !== id)
      : window._favs[key].concat([id]);
    rerenderFavState();
  } catch (e) {
    upsStatus("收藏操作失败: " + e);
  }
}

function rerenderFavState() {
  const activeTab = document.querySelector(".tab.active");
  if (!activeTab) return;
  const t = activeTab.dataset.tab;
  if (t === "posts" && window._posts) renderPosts();
  if (t === "ups" && window._upPosts) renderUps();
  if (t === "favs") loadFavs();
}

function favsStatus(text) {
  const el = document.getElementById("favs-status");
  if (el) el.textContent = text;
}

async function loadFavs() {
  const el = document.getElementById("favs-list");
  const btn = document.getElementById("btn-favs-refresh");
  if (!window._me) {
    el.innerHTML =
      '<div class="empty">登录后才能收藏帖子与 UP 内容。<br><br>' +
      '<button class="primary" onclick="openAuthModal(\'login\')">立即登录 / 注册</button></div>';
    favsStatus("");
    if (btn) btn.style.display = "none";
    return;
  }
  if (btn) btn.style.display = "";
  el.innerHTML = '<div class="loading">加载中…</div>';
  try {
    const data = await apiAuth("/api/favs");
    renderFavs(data.items || []);
  } catch (e) {
    el.innerHTML = '<div class="error">加载失败: ' + escapeHtml(e) + "</div>";
  }
}

function renderFavs(items) {
  const el = document.getElementById("favs-list");
  favsStatus("共 " + items.length + " 条收藏");
  if (!items.length) {
    el.innerHTML =
      '<div class="empty">还没有收藏。在「帖子分析」或「UP 订阅」页点卡片右上角的 ♡ 即可收藏。</div>';
    return;
  }
  el.innerHTML = items.map((p) => {
    const type = p.item_type;
    const label = type === "post" ? platformLabel(p) : (p.source_type === "video" ? "视频" : "专栏");
    return (
      '<article class="post-card">' +
      '<div class="post-top"><span class="platform">' + label + "</span>" +
      (p.race ? '<span class="race">' + escapeHtml(p.race) + "</span>" : "") +
      '<button class="fav-btn on" title="取消收藏" onclick="toggleFav(event, \'' + type + "', " + p.id + ')">♥</button></div>' +
      '<a class="post-title" href="' + escapeHtml(p.url || "#") + '" target="_blank" rel="noopener">' +
      escapeHtml(p.title || "无标题") + "</a>" +
      '<div class="post-author">' + escapeHtml(p.author || "") + " · " + escapeHtml(p.published_at || "") +
      " · 收藏于 " + escapeHtml(p.fav_at || "") + "</div>" +
      '<div class="post-summary">' + escapeHtml(p.summary || "") + "</div>" +
      "</article>"
    );
  }).join("");
}

let _authTab = "login";

function switchAuthTab(tab) {
  _authTab = tab;
  document.getElementById("auth-tab-login").classList.toggle("active", tab === "login");
  document.getElementById("auth-tab-register").classList.toggle("active", tab === "register");
  document.getElementById("auth-pass2").style.display = tab === "register" ? "" : "none";
  document.getElementById("btn-auth-submit").textContent = tab === "login" ? "登录" : "注册";
  document.getElementById("auth-error").textContent = "";
}

function openAuthModal(tab) {
  switchAuthTab(tab || "login");
  document.getElementById("auth-modal").classList.add("show");
  document.body.style.overflow = "hidden";
  document.getElementById("auth-nick").focus();
}

function closeAuthModal() {
  document.getElementById("auth-modal").classList.remove("show");
  document.body.style.overflow = "";
}

function authError(text) {
  document.getElementById("auth-error").textContent = text;
}

async function authSubmit() {
  const nick = document.getElementById("auth-nick").value.trim();
  const pass = document.getElementById("auth-pass").value;
  authError("");
  if (!nick) { authError("请输入昵称"); return; }
  if (pass.length < 6) { authError("密码至少 6 位"); return; }
  if (_authTab === "register") {
    const pass2 = document.getElementById("auth-pass2").value;
    if (pass !== pass2) { authError("两次输入的密码不一致"); return; }
  }
  try {
    const res = await fetch("/api/auth/" + _authTab, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nickname: nick, password: pass }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
    localStorage.setItem("upToken", data.token);
    window._me = data.nickname;
    document.getElementById("auth-pass").value = "";
    document.getElementById("auth-pass2").value = "";
    closeAuthModal();
    renderNavAuth();
    upsStatus((_authTab === "login" ? "登录成功" : "注册成功，已自动登录") + "：" + data.nickname);
    loadUps();
    loadFavIds().then(rerenderFavState);
  } catch (e) {
    authError(String(e));
  }
}

function openAccountModal() {
  document.getElementById("account-nick").textContent = "当前账号：" + (window._me || "");
  document.getElementById("acct-status").textContent = "";
  document.getElementById("acct-old").value = "";
  document.getElementById("acct-new").value = "";
  document.getElementById("account-modal").classList.add("show");
  document.body.style.overflow = "hidden";
}

function closeAccountModal() {
  document.getElementById("account-modal").classList.remove("show");
  document.body.style.overflow = "";
}

async function changePassword() {
  const oldPw = document.getElementById("acct-old").value;
  const newPw = document.getElementById("acct-new").value;
  const st = document.getElementById("acct-status");
  if (!oldPw) { st.textContent = "请输入当前密码"; return; }
  if (newPw.length < 6) { st.textContent = "新密码至少 6 位"; return; }
  st.textContent = "提交中…";
  try {
    await apiAuth("/api/auth/password", {
      method: "POST",
      body: JSON.stringify({ old_password: oldPw, new_password: newPw }),
    });
    st.textContent = "密码已修改";
    document.getElementById("acct-old").value = "";
    document.getElementById("acct-new").value = "";
  } catch (e) {
    st.textContent = "修改失败: " + e;
  }
}

async function deleteAccount() {
  if (!confirm("确定注销账号「" + (window._me || "") + "」？账号、登录状态和全部个人订阅将被删除，内容汇总保留。此操作不可恢复。")) return;
  try {
    await apiAuth("/api/auth/delete", { method: "POST" });
  } catch (e) {
    document.getElementById("acct-status").textContent = "注销失败: " + e;
    return;
  }
  localStorage.removeItem("upToken");
  window._me = null;
  closeAccountModal();
  renderNavAuth();
  upsStatus("账号已注销");
  loadUps();
  window._favs = { post: [], up: [] };
  if (document.querySelector(".tab.active") && document.querySelector(".tab.active").dataset.tab === "favs") loadFavs();
}

async function doLogout() {
  try { await apiAuth("/api/auth/logout", { method: "POST" }); } catch (e) { /* 忽略 */ }
  localStorage.removeItem("upToken");
  window._me = null;
  renderNavAuth();
  upsStatus("已退出登录");
  loadUps();
  window._favs = { post: [], up: [] };
  if (document.querySelector(".tab.active") && document.querySelector(".tab.active").dataset.tab === "favs") loadFavs();
}

async function initAuth() {
  if (!upToken()) { renderNavAuth(); return; }
  try {
    const me = await apiAuth("/api/auth/me");
    window._me = me.nickname;
  } catch (e) {
    window._me = null;
  }
  renderNavAuth();
  loadFavIds();
}

async function upsAuthed(path, opts) {
  const headers = Object.assign(
    { "X-Scrape-Token": localStorage.getItem("scrapeToken") || "" },
    (opts && opts.headers) || {}
  );
  let res = await fetch(path, Object.assign({}, opts, { headers }));
  if (res.status === 403) {
    const token = prompt("此操作需要抓取口令，请输入：");
    if (token === null) throw new Error("已取消");
    headers["X-Scrape-Token"] = token;
    res = await fetch(path, Object.assign({}, opts, { headers }));
    if (res.status === 403) throw new Error("口令不正确");
    localStorage.setItem("scrapeToken", token);
  }
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || ("HTTP " + res.status));
  }
  return res.json();
}

function loadUps() {
  const subsEl = document.getElementById("ups-subs");
  const listEl = document.getElementById("ups-list");
  subsEl.innerHTML = '<div class="loading">加载中…</div>';
  listEl.innerHTML = '<div class="loading">加载中…</div>';
  const headers = upToken() ? { Authorization: "Bearer " + upToken() } : {};
  const jobs = [
    api("/api/ups"),
    fetch("/api/ups/posts", { headers }).then((r) => r.json()),
  ];
  if (upToken()) {
    jobs.push(
      apiAuth("/api/ups/mine").catch((e) => {
        if (!upToken()) return []; // 401 已清除 token，按游客继续
        throw e;
      })
    );
  }
  Promise.all(jobs)
    .then(([subs, posts, mine]) => {
      window._ups = subs;
      window._upPosts = posts;
      window._myUps = mine || [];
      renderUps();
    })
    .catch((e) => {
      subsEl.innerHTML = '<div class="error">加载失败: ' + escapeHtml(e) + "</div>";
      listEl.innerHTML = "";
    });
}

function subCard(u, mine) {
  const toggle = mine ? "toggleMyUp" : "toggleUp";
  const del = mine ? "delMyUp" : "delUp";
  return (
    '<div class="up-sub-card">' +
    avatarHtml(u.avatar, abbr(u.name), "#fb7299") +
    '<div class="up-sub-info"><div class="up-sub-name up-sub-name-link" onclick="jumpToUp(' + u.mid + ')" title="跳转到该 UP 的汇总">' + escapeHtml(u.name) + "</div>" +
    '<div class="muted">mid: ' + u.mid + " · " + (u.enabled ? "已启用" : "已停用") + "</div></div>" +
    '<button class="btn-sm" onclick="' + toggle + "(" + u.mid + ')">' + (u.enabled ? "停用" : "启用") + "</button>" +
    '<button class="btn-sm danger" onclick="' + del + "(" + u.mid + ')">删除</button>' +
    "</div>"
  );
}

function subCardReadOnly(u) {
  return (
    '<div class="up-sub-card">' +
    avatarHtml(u.avatar, abbr(u.name), "#fb7299") +
    '<div class="up-sub-info"><div class="up-sub-name up-sub-name-link" onclick="jumpToUp(' + u.mid + ')" title="跳转到该 UP 的汇总">' + escapeHtml(u.name) + "</div>" +
    '<div class="muted">mid: ' + u.mid + " · " + (u.enabled ? "已启用" : "已停用") + "</div></div>" +
    "</div>"
  );
}

function renderUps() {
  const subsEl = document.getElementById("ups-subs");
  const parts = [];
  const isAdmin = !!localStorage.getItem("scrapeToken");
  parts.push(
    '<div class="up-group-head"><span class="up-group-name">公共订阅</span>' +
    '<span class="up-group-count">' + window._ups.length + " 个 · 全员可见</span></div>"
  );
  if (!window._ups.length) {
    parts.push('<div class="empty">暂无公共订阅。</div>');
  } else {
    parts.push(window._ups.map((u) => (isAdmin ? subCard(u, false) : subCardReadOnly(u))).join(""));
  }
  if (window._me) {
    parts.push(
      '<div class="up-group-head"><span class="up-group-name">我的订阅</span>' +
      '<span class="up-group-count">' + (window._myUps.length || 0) + " 个 · 上限 10 个</span></div>"
    );
    if (!window._myUps.length) {
      parts.push('<div class="empty">还没有自己的订阅。在上方粘贴 UP 主页链接或名称，点「添加订阅」。</div>');
    } else {
      parts.push(window._myUps.map((u) => subCard(u, true)).join(""));
    }
  }
  subsEl.innerHTML = parts.join("");

  const listEl = document.getElementById("ups-list");
  const st = document.getElementById("ups-stance-filter").value;
  const upPosts = st ? window._upPosts.filter((p) => opStances(p).has(st)) : window._upPosts;
  if (!upPosts.length) {
    listEl.innerHTML = st
      ? '<div class="empty">该立场下暂无相关内容。</div>'
      : (window._me
        ? '<div class="empty">还没有汇总内容。添加订阅后会立即开始拉取该 UP 的最新内容，稍等几分钟再刷新。</div>'
        : '<div class="empty">公共订阅暂无汇总内容。</div>');
    return;
  }
  const byMid = {};
  upPosts.forEach((p) => {
    (byMid[p.mid] = byMid[p.mid] || []).push(p);
  });
  const groups = [];
  const seen = new Set();
  const subs = [];
  (window._ups || []).concat(window._myUps || []).forEach((u) => {
    if (!seen.has(Number(u.mid))) {
      seen.add(Number(u.mid));
      subs.push(u);
    }
  });
  subs.forEach((u) => {
    if (byMid[u.mid]) {
      groups.push({ sub: u, posts: byMid[u.mid] });
    }
  });
  const others = Object.keys(byMid)
    .filter((mid) => !seen.has(Number(mid)))
    .map((mid) => ({
      sub: { mid: Number(mid), name: byMid[mid][0].author || "已删除的订阅", avatar: "" },
      posts: byMid[mid],
    }));
  groups.push(...others);
  const newest = (g) => g.posts[0].published_at || "";
  groups.sort((a, b) => (newest(a) < newest(b) ? 1 : -1));
  listEl.innerHTML = groups.map((g) => {
    const mid = g.sub.mid;
    const collapsed = window._collapsedUps.has(mid);
    return (
      '<section class="up-group" id="up-group-' + mid + '">' +
      '<div class="up-group-head up-group-toggle" onclick="toggleUpGroup(' + mid + ')" title="点击收缩 / 展开">' +
      avatarHtml(g.sub.avatar, abbr(g.sub.name), "#fb7299") +
      '<span class="up-group-name">' + escapeHtml(g.sub.name) + "</span>" +
      '<span class="up-group-count">' + g.posts.length + " 条</span>" +
      '<span class="up-group-arrow" id="up-group-arrow-' + mid + '">' + (collapsed ? "▶" : "▼") + "</span>" +
      "</div>" +
      '<div class="up-group-body" id="up-group-body-' + mid + '"' + (collapsed ? ' style="display:none"' : "") + ">" +
      g.posts.map(upPostCard).join("") +
      "</div></section>"
    );
  }).join("");
}

document.getElementById("ups-stance-filter").onchange = renderUps;

window._collapsedUps = new Set(JSON.parse(localStorage.getItem("collapsedUps") || "[]"));

function toggleUpGroup(mid) {
  if (window._collapsedUps.has(mid)) window._collapsedUps.delete(mid);
  else window._collapsedUps.add(mid);
  localStorage.setItem("collapsedUps", JSON.stringify(Array.from(window._collapsedUps)));
  const body = document.getElementById("up-group-body-" + mid);
  const arrow = document.getElementById("up-group-arrow-" + mid);
  if (body) body.style.display = window._collapsedUps.has(mid) ? "none" : "";
  if (arrow) arrow.textContent = window._collapsedUps.has(mid) ? "▶" : "▼";
}

function jumpToUp(mid) {
  if (window._collapsedUps.has(mid)) toggleUpGroup(mid);
  const el = document.getElementById("up-group-" + mid);
  if (!el) { upsStatus("该 UP 暂无汇总内容"); return; }
  const y = Math.max(0, el.getBoundingClientRect().top + window.scrollY - 90);
  window.scrollTo({ top: y, behavior: "smooth" });
  el.classList.remove("flash");
  void el.offsetWidth;
  el.classList.add("flash");
  // 滚动期间懒加载图片可能改变布局，动画结束后按最新位置校正一次
  setTimeout(() => {
    const el2 = document.getElementById("up-group-" + mid);
    if (!el2) return;
    const y2 = Math.max(0, el2.getBoundingClientRect().top + window.scrollY - 90);
    if (Math.abs(y2 - window.scrollY) > 4) window.scrollTo({ top: y2, behavior: "smooth" });
  }, 900);
}

function upPostCard(p) {
  const hasSub = !!(p.source_type === "video" && p.subtitle_text);
  const hasOp = !!(p.source_type === "video" && p.comment_summary);
  const cardClick = hasSub
    ? ' onclick="openSubModal(' + p.id + ')"'
    : hasOp
      ? ' onclick="openOpModal(' + p.id + ', &quot;ups&quot;)"'
      : "";
  const opBadge = hasOp
    ? '<span class="op-badge"' +
      (hasSub ? ' onclick="event.stopPropagation(); openOpModal(' + p.id + ', &quot;ups&quot;)"' : "") +
      ">观点</span>"
    : "";
  return (
    '<article class="post-card up-post' + (hasSub ? " has-sub" : "") + '"' + cardClick + ">" +
    (p.cover
      ? '<img class="up-cover" src="' + escapeHtml(p.cover) + '" loading="lazy" alt="" onerror="this.remove()">'
      : "") +
    '<div class="post-top"><span class="platform">' + (p.source_type === "video" ? "视频" : "专栏") + "</span>" +
    '<span class="race">' + escapeHtml(p.summary_type || "—") + "</span>" + opBadge +
    favBtn("up", p.id) + "</div>" +
    '<a class="post-title" href="' + (hasSub || hasOp ? "javascript:void(0)" : escapeHtml(p.url || "#")) + '"' +
    (hasSub || hasOp ? "" : ' target="_blank" rel="noopener"') + ">" +
    escapeHtml(p.title || "无标题") + "</a>" +
    '<div class="post-author">' + escapeHtml(p.published_at || "") + "</div>" +
    '<div class="post-summary">' + escapeHtml(p.summary || "（暂无摘要，点标题去原视频）") + "</div>" +
    (hasSub
      ? '<span class="jump">查看字幕总结 →</span>'
      : hasOp
        ? '<span class="jump">查看评论区观点 →</span>'
        : '<a class="jump" href="' + escapeHtml(p.url || "#") + '" target="_blank" rel="noopener">去 B站 →</a>') +
    "</article>"
  );
}

function stanceClass(s) {
  const m = { "支持": "sup", "质疑": "doubt", "调侃": "joke", "中立": "mid", "争议": "argue" };
  return m[s] || "mid";
}

function fmtTime(t) {
  if (!t) return "";
  const diff = Math.max(0, Date.now() - new Date(t * 1000).getTime());
  if (diff < 60e3) return "刚刚";
  if (diff < 3600e3) return Math.floor(diff / 60e3) + " 分钟前";
  if (diff < 86400e3) return Math.floor(diff / 3600e3) + " 小时前";
  if (diff < 7 * 86400e3) return Math.floor(diff / 86400e3) + " 天前";
  const d = new Date(t * 1000);
  const pad = (n) => (n < 10 ? "0" + n : n);
  return (d.getMonth() + 1) + "-" + pad(d.getDate());
}

function samplesHtml(samples) {
  const rows = samples.slice().sort((a, b) => (b.t || 0) - (a.t || 0));
  return '<div class="op-tl">' + rows.map((s) =>
    '<div class="tl-item' + (s.sub ? " tl-sub" : "") + '">' +
    '<div class="tl-meta">' + escapeHtml(fmtTime(s.t)) +
    " · 赞 " + (s.like || 0) + " · 回 " + (s.rcount || 0) + "</div>" +
    '<div class="tl-text">' + escapeHtml(s.text || "") + "</div>" +
    "</div>"
  ).join("") + "</div>";
}

function openOpModal(postId, src) {
  const arr = src === "posts" ? (window._posts || []) : (window._upPosts || []);
  const p = arr.find((x) => x.id === postId);
  if (!p) return;
  let clusters = [];
  try { clusters = JSON.parse(p.comment_summary || "[]"); } catch (e) { clusters = []; }
  if (!clusters.length) return;
  let samples = [];
  try { samples = JSON.parse(p.comment_samples || "[]"); } catch (e) { samples = []; }
  let m = document.getElementById("op-modal");
  if (m) m.remove();
  m = document.createElement("div");
  m.id = "op-modal";
  m.className = "sub-modal op-modal";
  m.innerHTML =
    '<div class="sub-modal-mask" onclick="closeOpModal()"></div>' +
    '<div class="sub-modal-box">' +
    '<button class="sub-modal-close" onclick="closeOpModal()">×</button>' +
    '<div class="sub-modal-title"></div>' +
    '<div class="sub-modal-meta"></div>' +
    '<div class="op-tabs"><button class="op-tab active" data-tab="op">观点</button>' +
    '<button class="op-tab" data-tab="tl">时间线</button></div>' +
    '<div class="sub-modal-body"></div>' +
    '<div class="sub-modal-foot"><a class="btn" target="_blank" rel="noopener">去 B站 看原评论</a></div>' +
    "</div>";
  document.body.appendChild(m);
  m.querySelector(".sub-modal-title").textContent = p.title || "无标题";
  m.querySelector(".sub-modal-meta").textContent = "评论区观点 · " + (p.comment_at || "");
  const body = m.querySelector(".sub-modal-body");
  const opHtml = clusters.map((c) => {
    const quotes = (c.quotes || []).map((q) => '<div class="op-quote">“' + escapeHtml(q) + "”</div>").join("");
    return (
      '<div class="op-cluster">' +
      '<div class="op-cluster-head">' +
      '<span class="op-label">' + escapeHtml(c.label || "") + "</span>" +
      '<span class="op-stance op-stance-' + stanceClass(c.stance) + '">' + escapeHtml(c.stance || "中立") + "</span>" +
      '<span class="op-size">' + escapeHtml(c.size || "") + "</span>" +
      "</div>" + quotes +
      "</div>"
    );
  }).join("");
  const tlHtml = samples.length
    ? samplesHtml(samples)
    : '<div class="empty">暂无时间线样本（等定时任务刷新回填）</div>';
  const renderBody = (mode) => { body.innerHTML = mode === "tl" ? tlHtml : opHtml; };
  m.querySelectorAll(".op-tab").forEach((b) => {
    b.addEventListener("click", () => {
      m.querySelectorAll(".op-tab").forEach((x) => x.classList.toggle("active", x === b));
      renderBody(b.dataset.tab);
    });
  });
  body.innerHTML = opHtml;
  m.classList.add("show");
  document.body.style.overflow = "hidden";
}

function closeOpModal() {
  const m = document.getElementById("op-modal");
  if (m) m.classList.remove("show");
  document.body.style.overflow = "";
}

function openSubModal(postId) {
  const p = (window._upPosts || []).find((x) => x.id === postId);
  if (!p) return;
  let m = document.getElementById("sub-modal");
  if (!m) {
    m = document.createElement("div");
    m.id = "sub-modal";
    m.className = "sub-modal";
    m.innerHTML =
      '<div class="sub-modal-mask" onclick="closeSubModal()"></div>' +
      '<div class="sub-modal-box">' +
      '<button class="sub-modal-close" onclick="closeSubModal()">×</button>' +
      '<div class="sub-modal-title"></div>' +
      '<div class="sub-modal-meta"></div>' +
      '<div class="sub-modal-summary"></div>' +
      '<div class="sub-modal-body"></div>' +
      '<div class="sub-modal-foot"><a class="btn" target="_blank" rel="noopener">去 B站 看原视频</a></div>' +
      "</div>";
    document.body.appendChild(m);
  }
  m.querySelector(".sub-modal-title").textContent = p.title || "无标题";
  m.querySelector(".sub-modal-meta").textContent =
    (p.author || "") + " · " + (p.published_at || "") + " · " + (p.summary_type || "");
  m.querySelector(".sub-modal-summary").textContent = p.summary || "";
  m.querySelector(".sub-modal-body").textContent = p.subtitle_text || "";
  m.querySelector(".sub-modal-foot a").href = p.url || "#";
  m.classList.add("show");
  document.body.style.overflow = "hidden";
}

function closeSubModal() {
  const m = document.getElementById("sub-modal");
  if (m) m.classList.remove("show");
  document.body.style.overflow = "";
}

async function addUp() {
  const input = document.getElementById("ups-add-input");
  const text = input.value.trim();
  if (!text) { upsStatus("请输入主页链接或 UP 名称"); return; }
  const isAdmin = !!localStorage.getItem("scrapeToken");
  if (!window._me && !isAdmin) {
    upsStatus("请先点右上角「登录 / 注册」，才能添加自己的订阅");
    return;
  }
  upsStatus("解析中…");
  const path = window._me ? "/api/ups/mine" : "/api/ups";
  const fn = window._me ? apiAuth : upsAuthed;
  try {
    const data = await fn(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    upsStatus("已添加订阅：" + data.subscription.name + "（正在拉取该 UP 的最新内容…）");
    input.value = "";
    loadUps();
    setTimeout(loadUps, 60000);
  } catch (e) {
    upsStatus("添加失败: " + e);
  }
}

async function toggleUp(mid) {
  upsStatus("操作中…");
  try {
    await upsAuthed("/api/ups/" + mid + "/toggle", { method: "POST" });
    loadUps();
  } catch (e) {
    upsStatus("操作失败: " + e);
  }
}

async function delUp(mid) {
  if (!confirm("确定删除该公共订阅？已生成的内容汇总会保留。")) return;
  upsStatus("删除中…");
  try {
    await upsAuthed("/api/ups/" + mid, { method: "DELETE" });
    loadUps();
  } catch (e) {
    upsStatus("操作失败: " + e);
  }
}

async function toggleMyUp(mid) {
  upsStatus("操作中…");
  try {
    await apiAuth("/api/ups/mine/" + mid + "/toggle", { method: "POST" });
    loadUps();
  } catch (e) {
    upsStatus("操作失败: " + e);
  }
}

async function delMyUp(mid) {
  if (!confirm("确定删除该订阅？")) return;
  upsStatus("删除中…");
  try {
    await apiAuth("/api/ups/mine/" + mid, { method: "DELETE" });
    loadUps();
  } catch (e) {
    upsStatus("操作失败: " + e);
  }
}

document.getElementById("btn-nav-login").addEventListener("click", () => openAuthModal("login"));
document.getElementById("btn-nav-account").addEventListener("click", openAccountModal);
document.getElementById("btn-nav-logout").addEventListener("click", doLogout);
document.getElementById("auth-tab-login").addEventListener("click", () => switchAuthTab("login"));
document.getElementById("auth-tab-register").addEventListener("click", () => switchAuthTab("register"));
document.getElementById("btn-acct-pw").addEventListener("click", changePassword);
document.getElementById("btn-acct-delete").addEventListener("click", deleteAccount);
document.getElementById("btn-ups-add").addEventListener("click", addUp);
document.getElementById("btn-favs-refresh").addEventListener("click", loadFavs);
document.getElementById("btn-ups-check").addEventListener("click", async () => {
  upsStatus("提交检查任务…");
  try {
    const data = await upsAuthed("/api/ups/check", { method: "POST" });
    if (data.busy) {
      upsStatus("已有检查任务在运行，请稍后再试");
      return;
    }
    upsStatus("检查已启动（约需几分钟），完成后列表会自动更新");
    let tries = 0;
    const iv = setInterval(() => {
      tries += 1;
      loadUps();
      if (tries >= 8) clearInterval(iv);
    }, 60000);
  } catch (e) {
    upsStatus("检查失败: " + e);
  }
});

/* ---------------- 积分走势 ---------------- */
window._trendCache = {};
let trendType = "drivers";
let trendTop = 6;

function loadTrend() {
  const el = document.getElementById("sub-trend");
  if (el.dataset.ready === "1") return;
  el.innerHTML = '<div class="loading">加载中…</div>';
  api("/api/f1/seasons").then((seasons) => {
    const list = seasons.filter((y) => y >= 1950).sort((a, b) => b - a);
    const latest = list[0];
    el.innerHTML =
      '<div class="filters">' +
      '<label>赛季 <select id="trend-season"></select></label>' +
      '<label>类型 <select id="trend-type"><option value="drivers">车手</option><option value="constructors">车队</option></select></label>' +
      '<label>显示 <select id="trend-top"><option value="6">前 6</option><option value="3">前 3</option><option value="10">前 10</option><option value="0">全部</option></select></label>' +
      "</div>" +
      '<div id="trend-legend"></div>' +
      '<div id="trend-chart"></div>';
    const s = document.getElementById("trend-season");
    list.forEach((y) => {
      const o = document.createElement("option"); o.value = y; o.textContent = y; s.appendChild(o);
    });
    s.value = latest;
    s.addEventListener("change", fetchTrend);
    document.getElementById("trend-type").addEventListener("change", (e) => {
      trendType = e.target.value;
      renderTrend();
    });
    document.getElementById("trend-top").addEventListener("change", (e) => {
      trendTop = parseInt(e.target.value, 10);
      renderTrend();
    });
    el.dataset.ready = "1";
    fetchTrend();
  }).catch((e) => { el.innerHTML = '<div class="error">加载失败: ' + escapeHtml(e) + "</div>"; });
}

function fetchTrend() {
  const el = document.getElementById("trend-chart");
  const season = document.getElementById("trend-season").value;
  const key = "trend|" + season;
  if (window._trendCache[key]) { renderTrend(); return; }
  document.getElementById("trend-legend").innerHTML = "";
  el.innerHTML = '<div class="loading">加载中…（首次加载该赛季需逐站汇总，约 30 秒）</div>';
  api("/api/f1/trend?season=" + season).then((data) => {
    window._trendCache[key] = data;
    renderTrend();
  }).catch((e) => { el.innerHTML = '<div class="error">加载失败: ' + escapeHtml(e) + "</div>"; });
}

function trendSeries() {
  const season = document.getElementById("trend-season").value;
  const data = window._trendCache["trend|" + season] ||
    { rounds: [], drivers: [], constructors: [] };
  const all = trendType === "drivers" ? data.drivers : data.constructors;
  const arr = trendTop > 0 ? all.slice(0, trendTop) : all;
  return { data, arr };
}

function niceMax(v) {
  if (v <= 0) return 10;
  const pow = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / pow;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow;
}

function renderTrend() {
  const { data, arr } = trendSeries();
  const chartEl = document.getElementById("trend-chart");
  const legendEl = document.getElementById("trend-legend");
  if (!data.rounds.length || !arr.length) {
    legendEl.innerHTML = "";
    chartEl.innerHTML = '<div class="empty">该赛季暂无走势数据（可能尚未开赛）</div>';
    return;
  }
  legendEl.innerHTML = arr.map((s) =>
    '<span class="trend-legend-item"><span class="trend-dot" style="background:' +
    escapeHtml(s.color) + '"></span>' + escapeHtml(s.name) +
    ' <span class="muted">' + s.points[s.points.length - 1] + "</span></span>").join("");

  const W = 900, H = 400, L = 50, R = 12, T = 12, B = 28;
  const n = data.rounds.length;
  const maxPts = Math.max(...arr.map((s) => Math.max(...s.points)));
  const yMax = niceMax(maxPts);
  const x = (i) => (n === 1 ? (L + W - R) / 2 : L + ((W - L - R) * i) / (n - 1));
  const y = (p) => T + (H - T - B) * (1 - p / yMax);

  let g = "";
  for (let k = 0; k <= 5; k++) {
    const p = (yMax * k) / 5;
    const yy = y(p);
    g += '<line x1="' + L + '" y1="' + yy + '" x2="' + (W - R) + '" y2="' + yy + '" class="trend-grid"/>' +
      '<text x="' + (L - 6) + '" y="' + (yy + 4) + '" class="trend-axis" text-anchor="end">' +
      Math.round(p) + "</text>";
  }
  const stepX = Math.max(1, Math.ceil(n / 12));
  data.rounds.forEach((r, i) => {
    if (i % stepX !== 0 && i !== n - 1) return;
    g += '<text x="' + x(i) + '" y="' + (H - 8) + '" class="trend-axis" text-anchor="middle">R' +
      r.round + "</text>";
  });
  const paths = arr.map((s) => {
    const pts = s.points.map((p, i) => x(i).toFixed(1) + "," + y(p).toFixed(1)).join(" ");
    return '<polyline points="' + pts + '" class="trend-line" style="stroke:' +
      escapeHtml(s.color) + '"/>';
  }).join("");

  chartEl.innerHTML =
    '<div class="trend-chart-wrap">' +
    '<svg viewBox="0 0 ' + W + " " + H + '" class="trend-svg" preserveAspectRatio="xMidYMid meet">' +
    g + paths +
    '<g id="trend-hover"></g>' +
    '<rect x="' + L + '" y="' + T + '" width="' + (W - L - R) + '" height="' + (H - T - B) +
    '" fill="transparent" id="trend-hover-area"></rect>' +
    "</svg>" +
    '<div class="trend-tip" id="trend-tip" style="display:none"></div>' +
    "</div>";

  window._trendData = { arr, data, x, y };
  const area = document.getElementById("trend-hover-area");
  const svg = chartEl.querySelector("svg");
  area.addEventListener("mousemove", (ev) => trendHover(ev, svg));
  area.addEventListener("click", (ev) => trendHover(ev, svg));
  area.addEventListener("mouseleave", () => {
    document.getElementById("trend-hover").innerHTML = "";
    document.getElementById("trend-tip").style.display = "none";
  });
}

function trendHover(ev, svg) {
  const { arr, data, x, y } = window._trendData || {};
  if (!arr) return;
  const rect = svg.getBoundingClientRect();
  const px = ((ev.clientX - rect.left) / rect.width) * 900;
  const n = data.rounds.length;
  const i = n === 1 ? 0 : Math.max(0, Math.min(n - 1,
    Math.round((px - 50) / ((900 - 50 - 12) / (n - 1)))));
  const g = document.getElementById("trend-hover");
  const tip = document.getElementById("trend-tip");
  const vals = arr.map((s) => ({ s, v: s.points[i] })).sort((a, b) => b.v - a.v);
  const hx = x(i);
  g.innerHTML = '<line x1="' + hx.toFixed(1) + '" y1="12" x2="' + hx.toFixed(1) +
    '" y2="372" class="trend-guide"/>' +
    vals.map((o) => '<circle cx="' + hx.toFixed(1) + '" cy="' + y(o.v).toFixed(1) +
      '" r="3.5" style="fill:' + escapeHtml(o.s.color) + ';stroke:#fff;stroke-width:1"/>').join("");
  const r = data.rounds[i];
  tip.innerHTML = '<div class="trend-tip-title">R' + r.round + " · " + escapeHtml(r.raceName) + "</div>" +
    vals.map((o) => '<div class="trend-tip-row"><span><span class="trend-dot" style="background:' +
      escapeHtml(o.s.color) + '"></span>' + escapeHtml(o.s.name) + "</span><b>" + o.v + "</b></div>").join("");
  tip.style.display = "block";
  const wrap = tip.parentElement.getBoundingClientRect();
  let left = ev.clientX - wrap.left + 14;
  if (left + 180 > wrap.width) left = ev.clientX - wrap.left - 194;
  let top = ev.clientY - wrap.top + 12;
  if (top + 130 > wrap.height) top = wrap.height - 140;
  tip.style.left = left + "px";
  tip.style.top = top + "px";
}

/* ---------------- 2027 赛历 ---------------- */
let _calTimer = null;

function loadCalendar() {
  const el = document.getElementById("calendar-list");
  if (el.dataset.ready === "1") return;
  el.innerHTML = '<div class="loading">加载中…</div>';
  api("/api/f1/calendar/2027").then((data) => {
    window._cal = data;
    el.innerHTML = '<div id="cal-banner"></div><div class="cal-note" id="cal-note"></div><div id="cal-rows"></div>';
    if (data.note) document.getElementById("cal-note").textContent = data.note;
    el.dataset.ready = "1";
    tickCalendar();
    if (!_calTimer) _calTimer = setInterval(tickCalendar, 1000);
  }).catch((e) => { el.innerHTML = '<div class="error">加载失败: ' + escapeHtml(e) + "</div>"; });
}

function pad2(n) { return String(n).padStart(2, "0"); }

function tickCalendar() {
  const el = document.getElementById("calendar-list");
  if (!el || !window._cal) return;
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const races = window._cal.races || [];
  const next = races.find((r) => new Date(r.date + "T00:00:00") >= today);
  const banner = document.getElementById("cal-banner");
  if (next) {
    const target = new Date(next.date + "T00:00:00");
    const diff = Math.max(0, target - now);
    const d = Math.floor(diff / 86400000);
    const h = Math.floor((diff % 86400000) / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    banner.innerHTML =
      '<div class="cal-banner-title">下一站 · R' + next.round + " " + escapeHtml(next.raceName) + "</div>" +
      '<div class="cal-banner-date">' + next.date + " · " + escapeHtml(next.circuit) +
      " · " + escapeHtml(next.country) + "</div>" +
      '<div class="cal-count">' + d + "<i>天</i> " + pad2(h) + ":" + pad2(m) + ":" + pad2(s) + "</div>";
  } else {
    banner.innerHTML = '<div class="cal-banner-title">2027 赛季已结束</div>';
  }
  renderCalRows(races, today);
}

function renderCalRows(races, today) {
  const el = document.getElementById("cal-rows");
  if (!el) return;
  const dows = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  el.innerHTML = races.map((r) => {
    const d = new Date(r.date + "T00:00:00");
    let status;
    let rowCls = "";
    if (d < today) {
      status = '<span class="cal-status done">已结束</span>';
    } else if (d.getTime() === today.getTime()) {
      status = '<span class="cal-status today">今天正赛</span>';
      rowCls = " cal-row-today";
    } else {
      status = '<span class="cal-status soon">还有 ' + Math.round((d - today) / 86400000) + " 天</span>";
    }
    return '<div class="cal-row' + rowCls + '">' +
      '<span class="cal-round">R' + r.round + "</span>" +
      '<div class="cal-info"><div class="cal-name">' + escapeHtml(r.raceName) + "</div>" +
      '<div class="cal-meta">' + escapeHtml(r.circuit) + " · " + escapeHtml(r.country) + "</div></div>" +
      '<div class="cal-date">' + r.date + ' <span class="muted">' + dows[d.getDay()] + "</span></div>" +
      status + "</div>";
  }).join("");
}

/* ---------------- 站内搜索 ---------------- */
function hl(text, q) {
  let esc = escapeHtml(text || "");
  const qe = String(q || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if (!qe) return esc;
  try {
    esc = esc.replace(new RegExp(qe, "gi"), (m) => "<mark>" + m + "</mark>");
  } catch (e) { /* 非法正则兜底 */ }
  return esc;
}

function truncate(text, n) {
  text = String(text || "");
  return text.length <= n ? text : text.slice(0, n) + "…";
}

function doSearch() {
  const q = document.getElementById("search-input").value.trim();
  if (!q) return;
  const modal = document.getElementById("search-modal");
  document.getElementById("search-modal-input").value = q;
  modal.classList.add("show");
  document.body.style.overflow = "hidden";
  runSearch();
  setTimeout(() => document.getElementById("search-modal-input").focus(), 50);
}

function runSearch() {
  const q = document.getElementById("search-modal-input").value.trim();
  const body = document.getElementById("search-body");
  const meta = document.getElementById("search-meta");
  if (!q) { body.innerHTML = ""; meta.textContent = ""; return; }
  meta.textContent = "搜索中…";
  api("/api/search?q=" + encodeURIComponent(q)).then((data) => {
    const posts = data.posts || [];
    const ups = data.upPosts || [];
    meta.textContent = "「" + q + "」共 " + (posts.length + ups.length) +
      " 条结果（帖子 " + posts.length + " · UP 内容 " + ups.length + "）";
    if (!posts.length && !ups.length) {
      body.innerHTML = '<div class="search-empty">没有找到相关内容</div>';
      return;
    }
    let html = "";
    if (posts.length) {
      html += '<div class="search-sec-title">帖子分析</div>';
      html += posts.map((p) =>
        '<a class="search-item" href="' + escapeHtml(p.url || "#") + '" target="_blank" rel="noopener">' +
        '<div class="search-item-title">' + hl(truncate(p.title, 80), q) + "</div>" +
        (p.summary ? '<div class="search-item-sum">' + hl(truncate(p.summary, 130), q) + "</div>" : "") +
        '<div class="search-item-meta">' + escapeHtml(p.author || "") + " · " +
        escapeHtml(p.published_at || "") + (p.race ? " · " + escapeHtml(p.race) : "") +
        " · " + platformLabel(p) + "</div></a>"
      ).join("");
    }
    if (ups.length) {
      html += '<div class="search-sec-title">UP 内容</div>';
      html += ups.map((p) =>
        '<a class="search-item" href="' + escapeHtml(p.url || "#") + '" target="_blank" rel="noopener">' +
        '<div class="search-item-title">' + hl(truncate(p.title, 80), q) + "</div>" +
        (p.summary ? '<div class="search-item-sum">' + hl(truncate(p.summary, 130), q) + "</div>" : "") +
        '<div class="search-item-meta">' + escapeHtml(p.author || "") + " · " +
        escapeHtml(p.published_at || "") + " · " +
        (p.source_type === "video" ? "视频" : "专栏") + "</div></a>"
      ).join("");
    }
    body.innerHTML = html;
  }).catch((e) => {
    meta.textContent = "搜索失败: " + e;
    body.innerHTML = "";
  });
}

function closeSearchModal() {
  const m = document.getElementById("search-modal");
  if (m) m.classList.remove("show");
  document.body.style.overflow = "";
}

document.getElementById("btn-search").addEventListener("click", doSearch);
document.getElementById("search-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") doSearch();
});
document.getElementById("btn-search-go").addEventListener("click", runSearch);
document.getElementById("search-modal-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") runSearch();
});

/* 初始加载 */
loadStandings();
showSchedulerStatus();
initAuth();
