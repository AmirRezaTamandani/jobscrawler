const $ = (id) => document.getElementById(id);
const roles = { performance: "پرفورمنس", seo: "سئو", social: "شبکه‌های اجتماعی" };
const sources = { jobinja: "جابینجا", jobvision: "جاب‌ویژن" };
const domains = { jobinja: "jobinja.ir", jobvision: "jobvision.ir" };
const pageSize = 20;
const digits = new Intl.NumberFormat("fa-IR");
const dateFormat = new Intl.DateTimeFormat("fa-IR", {
  year: "numeric", month: "long", day: "numeric", timeZone: "Asia/Tehran",
});
const dayFormat = new Intl.DateTimeFormat("fa-IR", {
  weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: "Asia/Tehran",
});
const validDay = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value ?? "");
const roleButtons = [...document.querySelectorAll("[data-role]")];
let report = null;
let filtered = [];
let selectedRole = "";
let page = 1;
let fetching = null;
const selected = new Map();
const jobKey = job => job.source + ":" + job.source_id;
function loading(button, active, label) {
  if (active) button.dataset.idleLabel = button.textContent;
  button.disabled = active;
  button.classList.toggle("is-loading", active);
  button.setAttribute("aria-busy", String(active));
  button.textContent = active ? label : button.dataset.idleLabel;
}

function formatDate(value, full = false) {
  if (!value) return "تاریخ نامشخص";
  const date = new Date(validDay(value) ? value + "T12:00:00+03:30" : value);
  return Number.isNaN(date.valueOf()) ? "تاریخ نامشخص" : (full ? dayFormat : dateFormat).format(date);
}

function sourceUrl(job) {
  try {
    const url = new URL(job.url);
    const domain = domains[job.source];
    if (domain && url.protocol === "https:" && !url.username && !url.password && !url.port &&
        (url.hostname === domain || url.hostname === "www." + domain)) return url.href;
  } catch { /* An unavailable link still leaves a readable listing. */ }
  return null;
}

function textElement(tag, className, value) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (value != null) el.textContent = value;
  return el;
}

function icon(name) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  const use = document.createElementNS(ns, "use");
  svg.setAttribute("class", "ico");
  svg.setAttribute("aria-hidden", "true");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}

function normalize(value) {
  return String(value ?? "").normalize("NFKC").toLocaleLowerCase("fa-IR")
    .replace(/[يى]/g, "ی").replace(/ك/g, "ک").replace(/[\u064b-\u065f\u0670\u0640]/g, "")
    .replace(/[\s\u200c\u200d]+/g, " ").trim();
}

function newRow(job) {
  const row = document.createElement("tr");
  const vacancy = textElement("td", "vacancy");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = selected.has(jobKey(job));
  checkbox.disabled = !sourceUrl(job);
  checkbox.setAttribute("aria-label", "انتخاب «" + job.title + "»");
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) selected.set(jobKey(job), job);
    else selected.delete(jobKey(job));
    renderSelected();
  });
  vacancy.append(checkbox, textElement("bdi", "job-title", job.title), textElement("bdi", "company", job.company || "شرکت اعلام نشده"));
  const chipCell = textElement("td", "chip-cell");
  const chips = textElement("div", "chips");
  for (const role of job.roles || []) {
    if (Object.hasOwn(roles, role)) chips.append(textElement("span", "chip " + role, roles[role]));
  }
  chipCell.append(chips);
  const place = textElement("td", "place");
  const location = textElement("span", "location");
  location.append(icon("pin"), textElement("bdi", "", job.location || "اعلام نشده"));
  place.append(location);
  const source = textElement("td", "source-cell");
  source.append(textElement("span", "source-name", sources[job.source] || job.source),
                textElement("span", "posted", formatDate(job.posted_at)));
  const action = textElement("td", "out-cell");
  const url = sourceUrl(job);
  if (url) {
    const link = textElement("a", "out-link");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.title = "مشاهده آگهی در " + sources[job.source];
    link.setAttribute("aria-label", "مشاهدهٔ «" + job.title + "» در " + sources[job.source]);
    link.append(icon("external"));
    action.append(link);
  }
  row.append(vacancy, chipCell, place, source, action);
  return row;
}

function renderSelected() {
  $("selected-count").textContent = digits.format(selected.size);
  $("batch-copy").disabled = !selected.size;
  $("batch-status").textContent = "";
  const eligible = filtered.filter(job => sourceUrl(job));
  const count = eligible.filter(job => selected.has(jobKey(job))).length;
  $("select-all").disabled = !eligible.length;
  $("select-all").checked = Boolean(eligible.length) && count === eligible.length;
  $("select-all").indeterminate = count > 0 && count < eligible.length;
  $("selection-status").textContent = digits.format(count) + " از " + digits.format(eligible.length) + " نتیجه انتخاب شده";
  $("selected-list").replaceChildren(...Array.from(selected.values(), job => {
    const item = document.createElement("li");
    const name = textElement("span", "", job.title + " | " + (job.company || "") + " | " + sources[job.source]);
    const remove = textElement("button", "", "حذف");
    remove.type = "button";
    remove.setAttribute("aria-label", "حذف «" + job.title + "» از فهرست");
    remove.addEventListener("click", () => { selected.delete(jobKey(job)); renderSelected(); if (report) renderPage(); });
    item.append(name, remove);
    return item;
  }));
}
$("select-all").addEventListener("change", event => {
  for (const job of filtered) {
    if (!sourceUrl(job)) continue;
    if (event.target.checked) selected.set(jobKey(job), job);
    else selected.delete(jobKey(job));
  }
  renderSelected();
  renderPage();
});
$("batch-copy").addEventListener("click", async () => {
  loading($("batch-copy"), true, "در حال کپی…");
  const jobs = Array.from(selected.values(), job => ({source: job.source, source_id: job.source_id, title: job.title, company: job.company, url: sourceUrl(job)}));
  const payload = JSON.stringify({version: 1, jobs});
  try { await navigator.clipboard.writeText(payload); $("batch-status").textContent = "فهرست کپی شد. آن را در افزونه وارد کنید."; }
  catch { $("batch-text").value = payload; $("batch-text").hidden = false; $("batch-text").select(); $("batch-status").textContent = "متن انتخاب‌شده را کپی کنید."; }
  finally { loading($("batch-copy"), false); $("batch-copy").disabled = !selected.size; }
});

function showState(message, action, handler) {
  $("state").replaceChildren(textElement("p", "", message));
  if (action && handler) {
    const button = textElement("button", "", action);
    button.type = "button";
    button.addEventListener("click", handler);
    $("state").append(button);
  }
  $("state").hidden = false;
}

function renderSummary() {
  const jobs = report?.jobs;
  $("total").textContent = jobs ? digits.format(jobs.length) : "—";
  const counts = Object.fromEntries(Object.keys(roles).map(role => [
    role, jobs ? jobs.filter(job => job.roles?.includes(role)).length : 0,
  ]));
  const occurrences = Object.values(counts).reduce((sum, count) => sum + count, 0);
  let start = 0;
  for (const [role, count] of Object.entries(counts)) {
    $("total-" + role).textContent = jobs ? digits.format(count) : "—";
    const share = occurrences ? 100 * count / occurrences : 0;
    const arc = $("arc-" + role);
    const length = Math.max(0, share - Math.min(share * .2, .9));
    arc.style.strokeDasharray = length + " " + (100 - length);
    arc.style.strokeDashoffset = -start;
    start += share;
  }
  $("report-date").textContent = report?.day ? formatDate(report.day, true) : "—";
  if (report?.day) $("report-date").dateTime = report.day;
  else $("report-date").removeAttribute("datetime");
}

function renderNotice() {
  const messages = [];
  const incomplete = Object.entries(sources)
    .filter(([key]) => !Object.hasOwn(report.sources, key) || report.sources[key] !== null)
    .map(([, name]) => name);
  if (report.mode === "snapshot") messages.push("این نسخهٔ ذخیره‌شدهٔ گزارش است.");
  if (incomplete.length) messages.push("دریافت کامل نشد (" + incomplete.join(" و ") + ").");
  $("notice").className = "notice " + (incomplete.length ? "warn" : "info");
  $("notice").textContent = messages.join(" ");
  $("notice").hidden = !messages.length;
}

function renderPage() {
  const max = Math.ceil(filtered.length / pageSize);
  page = Math.max(1, Math.min(page, max));
  const start = (page - 1) * pageSize;
  $("rows").replaceChildren(...filtered.slice(start, start + pageSize).map(newRow));
  $("list").hidden = !filtered.length;
  $("state").hidden = Boolean(filtered.length);
  $("pagination").hidden = max <= 1;
  $("prev").disabled = page <= 1;
  $("next").disabled = page >= max;
  $("range").textContent = digits.format(start + 1) + " تا " + digits.format(Math.min(start + pageSize, filtered.length)) + " از " + digits.format(filtered.length) + " فرصت";
  $("page-label").textContent = "صفحهٔ " + digits.format(page) + " از " + digits.format(max);
  $("result-count").textContent = digits.format(filtered.length) + " نتیجه";
  $("copy").disabled = !filtered.some(job => sourceUrl(job));
  $("download").disabled = !filtered.length;
  renderSelected();
  if (!filtered.length) {
    if (report.jobs.length) showState("فرصتی با این جست‌وجو و فیلترها پیدا نشد.", "پاک کردن فیلترها", resetFilters);
    else if (Object.values(sources).length && Object.keys(sources).every(key => report.sources[key] !== null)) {
      showState("نتیجهٔ این روز هنوز مشخص نیست. دریافت از منابع کامل نشد.");
    } else showState("در این گزارش فرصت تازه‌ای ثبت نشده است.");
  }
}

function applyFilters() {
  roleButtons.forEach(b => b.setAttribute("aria-pressed", String(b.dataset.role === selectedRole)));
  $("copy-status").textContent = "";
  $("copy-text").hidden = true;
  if (!report) return;
  const words = normalize($("query").value).split(" ").filter(Boolean);
  const source = $("source").value;
  filtered = report.jobs.filter(job => {
    if (source && job.source !== source) return false;
    if (selectedRole && !job.roles?.includes(selectedRole)) return false;
    if (!words.length) return true;
    const text = normalize([job.title, job.company, job.location].filter(Boolean).join(" "));
    return words.every(word => text.includes(word));
  });
  page = 1;
  renderPage();
}

function resetFilters() {
  $("query").value = "";
  $("source").value = "";
  selectedRole = "";
  applyFilters();
}

function showDay(day, push) {
  const url = new URL(location.href);
  if (day) url.searchParams.set("day", day);
  else url.searchParams.delete("day");
  if (push && url.href !== location.href) history.pushState(null, "", url);
  loadReport(day);
}

async function loadReport(day) {
  fetching?.abort();
  const request = new AbortController();
  fetching = request;
  report = null;
  filtered = [];
  $("list").hidden = true;
  $("pagination").hidden = true;
  $("day").disabled = true;
  $("copy").disabled = true;
  $("download").disabled = true;
  renderSelected();
  $("notice").hidden = true;
  $("result-count").textContent = "";
  $("copy-status").textContent = "";
  $("copy-text").hidden = true;
  renderSummary();
  showState("در حال دریافت آگهی‌ها…");
  $("state").classList.add("is-loading");
  $("results").setAttribute("aria-busy", "true");
  try {
    const endpoint = new URL("/api/dashboard", location.origin);
    if (day) endpoint.searchParams.set("day", day);
    const response = await fetch(endpoint, { signal: request.signal, headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    if (!Array.isArray(data.jobs) || !Array.isArray(data.days) || !data.sources || typeof data.sources !== "object") {
      throw new Error("Invalid report");
    }
    if (request !== fetching) return;
    report = data;
    $("day").replaceChildren(...report.days.map(d => new Option(formatDate(d, true), d, false, d === report.day)));
    $("day").disabled = !report.days.length;
    renderSummary();
    renderNotice();
    applyFilters();
  } catch (err) {
    if (request !== fetching || err.name === "AbortError") return;
    $("day").disabled = !$("day").options.length || !$("day").options[0].value.match(/^\d{4}-/);
    if (day && err.message === "HTTP 404") showState("برای این تاریخ گزارشی در دسترس نیست.", "نمایش آخرین گزارش", () => showDay(null, true));
    else showState("دریافت گزارش انجام نشد. لطفاً دوباره تلاش کنید.", "تلاش دوباره", () => loadReport(day));
  } finally {
    if (request === fetching) {
      $("state").classList.remove("is-loading");
      $("results").setAttribute("aria-busy", "false");
    }
  }
}

$("day").addEventListener("change", () => showDay($("day").value, true));
window.addEventListener("popstate", () => loadReport(new URL(location.href).searchParams.get("day")));
$("query").addEventListener("input", applyFilters);
$("source").addEventListener("change", applyFilters);
roleButtons.forEach(b => b.addEventListener("click", () => { selectedRole = b.dataset.role; applyFilters(); }));
function movePage(delta) {
  page += delta;
  renderPage();
  $("results").scrollIntoView({ block: "start" });
  $("list-heading").setAttribute("tabindex", "-1");
  $("list-heading").focus({ preventScroll: true });
}
$("prev").addEventListener("click", () => movePage(-1));
$("next").addEventListener("click", () => movePage(1));
$("copy").addEventListener("click", async () => {
  if (!report) return;
  loading($("copy"), true, "در حال کپی…");
  const lines = filtered.flatMap(job => {
    const url = sourceUrl(job);
    return url ? [job.title + (job.company ? " | " + job.company : "") + "\n" + url] : [];
  });
  const value = "فرصت‌های شغلی فلووین | " + formatDate(report.day) + "\n\n" + lines.join("\n\n");
  try {
    await navigator.clipboard.writeText(value);
    $("copy-status").textContent = "فهرست و لینک فرصت‌ها کپی شد.";
  } catch {
    $("copy-text").value = value;
    $("copy-text").hidden = false;
    $("copy-text").select();
    $("copy-status").textContent = "متن انتخاب‌شده را کپی کنید.";
  } finally {
    loading($("copy"), false);
    $("copy").disabled = !filtered.some(job => sourceUrl(job));
  }
});

function csvCell(value) {
  let text = String(value ?? "");
  // Prevent spreadsheet software interpreting untrusted cell values as formulas.
  if (/^[\s\u0000-\u001f]*[=+@\-\t\r]/u.test(text)) text = "'" + text;
  return '"' + text.replace(/"/g, '""') + '"';
}

$("download").addEventListener("click", async () => {
  if (!report || !filtered.length) return;
  loading($("download"), true, "در حال آماده‌سازی…");
  await new Promise(resolve => requestAnimationFrame(() => setTimeout(resolve, 0)));
  try {
  const rows = [["عنوان", "شرکت", "موقعیت", "حوزه", "منبع", "تاریخ درج", "تاریخ اولین مشاهده", "لینک"]];
  for (const job of filtered) {
    rows.push([job.title, job.company, job.location,
      (job.roles || []).map(role => roles[role] || role).join("، "),
      sources[job.source] || job.source, job.posted_at, job.first_seen, sourceUrl(job)]);
  }
  const csv = "\ufeff" + rows.map(row => row.map(csvCell).join(",")).join("\r\n");
  const href = URL.createObjectURL(new Blob([csv], {type: "text/csv;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = href;
  link.download = "felowin-jobs-" + report.day + ".csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
  } finally {
    loading($("download"), false);
    $("download").disabled = !filtered.length;
  }
});

$("crawl-form").addEventListener("submit", async event => {
  event.preventDefault();
  const secret = $("crawl-secret").value;
  if (!secret) return;
  $("crawl-secret").value = "";
  loading($("crawl-start"), true, "در حال دریافت…");
  $("crawl-status").textContent = "دریافت آگهی‌ها در حال انجام است. این مرحله ممکن است چند دقیقه طول بکشد.";
  try {
    const response = await fetch("/api/crawl", {
      method: "POST", headers: {Authorization: "Bearer " + secret, Accept: "application/json"},
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) throw new Error("کلید دسترسی معتبر نیست.");
    if (response.status === 503) throw new Error("ذخیره‌سازی یا تنظیمات سرور آماده نیست.");
    if (!response.ok && response.status !== 502) throw new Error("اجرای کراولر با خطا مواجه شد.");
    if (data.status === "complete") $("crawl-status").textContent = "دریافت آگهی‌ها کامل شد.";
    else if (data.status === "partial") $("crawl-status").textContent = "دریافت کامل نشد. وضعیت منابع را در گزارش بررسی کنید.";
    else if (data.status === "failed") $("crawl-status").textContent = "دریافت از منابع ناموفق بود. وضعیت منابع را در گزارش بررسی کنید.";
    else throw new Error("پاسخ سرور قابل بررسی نیست.");
    showDay(data.day || null, true);
  } catch (error) {
    $("crawl-status").textContent = error instanceof TypeError
      ? "ارتباط با سرور قطع شد. پیش از اجرای مجدد، گزارش و وضعیت منابع را بررسی کنید."
      : error.message;
  } finally {
    loading($("crawl-start"), false);
  }
});

loadReport(new URL(location.href).searchParams.get("day"));

window.addEventListener("felowin-session-status", event => {
  const detail = event.detail;
  if (!detail || !["logged_in", "logged_out", "unknown"].includes(detail.jobinja) || !["logged_in", "logged_out", "unknown"].includes(detail.jobvision)) return;
  const labels = {logged_in: "وارد شده", logged_out: "وارد نشده", unknown: "نامشخص"};
  const checked = new Date(detail.checkedAt);
  if (Number.isNaN(checked.valueOf())) return;
  $("session-status").textContent = "آخرین بررسی " + checked.toLocaleTimeString("fa-IR") + " — جابینجا: " + labels[detail.jobinja] + "، جاب‌ویژن: " + labels[detail.jobvision];
});
