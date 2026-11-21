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
  vacancy.append(textElement("bdi", "job-title", job.title), textElement("bdi", "company", job.company || "شرکت اعلام نشده"));
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
  $("notice").hidden = true;
  $("result-count").textContent = "";
  $("copy-status").textContent = "";
  $("copy-text").hidden = true;
  renderSummary();
  showState("در حال دریافت آگهی‌ها…");
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
  }
});

loadReport(new URL(location.href).searchParams.get("day"));
