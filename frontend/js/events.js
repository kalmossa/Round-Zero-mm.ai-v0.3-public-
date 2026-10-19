// MM.AI — events.js
// Page liste des events. URL params : ?type=upcoming|results|all&promotion=UFC|all&page=N
//   - type=upcoming  : tri ASC (le plus proche en premier)
//   - type=results   : tri DESC (le plus recent en premier)
//   - type=all       : tri DESC global
// Pagination : l'API renvoie { events, total, page, limit }. On pagine en place
// (sans recharger la page) comme roster.js, avec les memes classes .rs-page-btn.

const EVENTS_PAGE_SIZE = 50;

const _PROMOS_LIST = [
    { code: "",           label: "All MMA", i18n: "events.promo_all" },
    { code: "UFC",        label: "UFC" },
    { code: "PFL",        label: "PFL" },
    { code: "ONE",        label: "ONE" },
    { code: "BELLATOR",   label: "Bellator" },
    { code: "KSW",        label: "KSW" },
    { code: "RIZIN",      label: "Rizin" },
    { code: "BKFC",       label: "BKFC" },
    { code: "LFA",        label: "LFA" },
    { code: "Invicta",    label: "Invicta" },
    { code: "ACA",        label: "ACA" },
    { code: "Cage Warriors", label: "Cage Warriors" },
    { code: "Road FC",    label: "Road FC" },
    { code: "BRAVE CF",   label: "BRAVE CF" },
];

async function renderEventsPage() {
    setupNavSearch();
    const root = document.getElementById("events-root");

    const type      = (getQueryParam("type") || "upcoming").toLowerCase();
    const promotion = (getQueryParam("promotion") || "").trim();

    // Titre : generique (sans promo) -> cle i18n dediee ; avec promo -> "PROMO — Onglet"
    const titleMap = {
        "upcoming": promotion ? `${promotion} — ${t("events.upcoming")}` : t("events.hub_upcoming"),
        "results":  promotion ? `${promotion} — ${t("events.results")}`  : t("events.hub_results"),
        "all":      promotion ? `${promotion} — ${t("events.all")}`      : t("events.hub_all"),
    };
    document.title = `${titleMap[type] || "Events"} — MM.AI`;

    root.innerHTML = `
        <div class="container">
            <div class="events-header">
                <div>
                    <h1 class="events-title">${esc(titleMap[type] || "Events")}</h1>
                    <p class="events-sub">${
                        type === "upcoming" ? t("events.sorted_asc") :
                        type === "results"  ? t("events.sorted_desc") :
                                              t("events.all_desc")
                    }</p>
                </div>
            </div>

            <div class="events-tabs-row">
                <div class="events-tabs">
                    ${renderTab(t("events.upcoming"), "upcoming", type, promotion)}
                    ${renderTab(t("events.results"),  "results",  type, promotion)}
                    ${renderTab(t("events.all"),      "all",      type, promotion)}
                </div>
                <div class="events-search-wrap">
                    <input type="search" id="events-search" class="events-search-input"
                           placeholder="${esc(t("events.search_placeholder"))}" autocomplete="off">
                    <div class="events-search-results" id="events-search-results"></div>
                </div>
            </div>

            <div class="events-filter-bar">
                <span class="events-filter-label">${t("events.promotion_label")}:</span>
                ${_PROMOS_LIST.map(p => {
                    const active = (p.code || "") === (promotion || "");
                    const label = p.i18n ? t(p.i18n) : p.label;
                    return `<a href="events.html?type=${type}&promotion=${encodeURIComponent(p.code)}"
                              class="events-filter-pill ${active ? "active" : ""}">${esc(label)}</a>`;
                }).join("")}
            </div>

            <div id="events-list" class="events-list">
                <div class="loader">${t("events.loading")}</div>
            </div>
            <div class="rs-pagination" id="events-pagination"></div>
        </div>
    `;

    setupEventsSearchBox();

    const startPage = Math.max(1, parseInt(getQueryParam("page") || "1", 10) || 1);
    loadEventsList(type, promotion, startPage);
}

// Charge (et recharge) la liste paginee dans #events-list, sans recharger la page.
async function loadEventsList(type, promotion, page) {
    const listEl = document.getElementById("events-list");
    const pagEl  = document.getElementById("events-pagination");
    if (!listEl) return;
    listEl.innerHTML = `<div class="loader">${t("events.loading")}</div>`;
    if (pagEl) pagEl.innerHTML = "";

    try {
        const params = {
            limit: EVENTS_PAGE_SIZE,
            page,
            sort: type === "results" ? "desc" : (type === "upcoming" ? "asc" : "desc"),
        };
        if (type === "upcoming") params.status = "upcoming";
        if (type === "results")  params.status = "completed";
        if (promotion)           params.promotion = promotion;

        const data   = await api.events(params);
        const events = data.events || [];
        const total  = data.total || 0;
        const totalPages = Math.max(1, Math.ceil(total / EVENTS_PAGE_SIZE));

        // page hors borne (ex: filtre qui reduit le total) -> on recadre
        if (page > totalPages) { return loadEventsList(type, promotion, totalPages); }

        if (!events.length) {
            listEl.innerHTML = `
                <div class="empty">
                    <h3>${t("events.no_events_filter")}</h3>
                    <p>${t("events.empty_sub")}</p>
                </div>`;
            return;
        }

        listEl.innerHTML = events.map(ev => renderEventCard(ev)).join("");

        // pagination (memes classes que roster.js)
        if (pagEl) {
            pagEl.innerHTML = buildEventsPagination(page, totalPages);
            pagEl.querySelectorAll("[data-page]:not([disabled])").forEach(b => {
                b.addEventListener("click", () => {
                    const p = parseInt(b.dataset.page, 10);
                    if (p && p !== page) {
                        const u = new URL(location.href);
                        u.searchParams.set("type", type);
                        if (promotion) u.searchParams.set("promotion", promotion);
                        else u.searchParams.delete("promotion");
                        u.searchParams.set("page", p);
                        history.replaceState(null, "", u);
                        loadEventsList(type, promotion, p);
                        window.scrollTo({ top: 0, behavior: "smooth" });
                    }
                });
            });
        }
    } catch (e) {
        listEl.innerHTML = `<div class="error-box">Error: ${esc(e.message)}</div>`;
    }
}

// Pagination numerotee (1 … prev page next … last) — reprend la logique de roster.js
function buildEventsPagination(page, totalPages) {
    if (totalPages <= 1) return "";
    const btn = (p, label, cls = "") =>
        `<button type="button" class="rs-page-btn ${cls}" data-page="${p}"${p === page ? ' aria-current="page"' : ""}>${label}</button>`;
    const dots = `<span class="rs-page-dots">…</span>`;
    let html = `<button type="button" class="rs-page-btn nav" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>‹ ${t("pagination.prev")}</button>`;
    const wanted = new Set([1, totalPages, page, page - 1, page + 1, page - 2, page + 2]);
    const sorted = [...wanted].filter(p => p >= 1 && p <= totalPages).sort((a, b) => a - b);
    let prev = 0;
    for (const p of sorted) {
        if (p - prev > 1) html += dots;
        html += btn(p, p, p === page ? "current" : "");
        prev = p;
    }
    html += `<button type="button" class="rs-page-btn nav" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""}>${t("pagination.next")} ›</button>`;
    return html;
}

// Event search box (à coté des tabs)
function setupEventsSearchBox() {
    const input = document.getElementById("events-search");
    const panel = document.getElementById("events-search-results");
    if (!input || !panel) return;

    const close = () => { panel.classList.remove("open"); panel.innerHTML = ""; };

    document.addEventListener("click", (e) => {
        if (!input.parentElement.contains(e.target)) close();
    });

    input.addEventListener("keydown", (e) => {
        if (e.key === "Escape") { close(); input.blur(); }
    });

    const render = (events) => {
        if (!events || !events.length) {
            panel.innerHTML = `<div class="es-empty">${t("events.no_event_found")}</div>`;
            panel.classList.add("open");
            return;
        }
        panel.innerHTML = events.map(ev => {
            const dt = ev.date ? new Date(ev.date) : null;
            const dateStr = dt
                ? dt.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
                : "";
            const loc = [ev.city, ev.country].filter(Boolean).join(", ");
            return `
              <a class="es-row" href="event.html?id=${ev.id}">
                <span class="es-info">
                  <span class="es-name">${esc(ev.name)}</span>
                  <span class="es-sub">
                    ${ev.promotion ? `<span class="es-promo">${esc(ev.promotion)}</span>` : ""}
                    ${dateStr ? `<span class="es-date">${esc(dateStr)}</span>` : ""}
                    ${loc ? `<span class="es-loc">${esc(loc)}</span>` : ""}
                  </span>
                </span>
                <span class="es-status es-status-${esc(ev.effective_status || ev.status || "completed")}">${esc(ev.effective_status || ev.status || "")}</span>
              </a>
            `;
        }).join("");
        panel.classList.add("open");
    };

    const doSearch = debounce(async () => {
        const q = input.value.trim();
        if (q.length < 2) { close(); return; }
        try {
            const data = await api.events({ search: q, limit: 8 });
            render(data.events || []);
        } catch (e) {
            panel.innerHTML = `<div class="es-empty">Error: ${esc(e.message)}</div>`;
            panel.classList.add("open");
        }
    }, 220);

    input.addEventListener("input", doSearch);
    input.addEventListener("focus", () => {
        if (input.value.trim().length >= 2) doSearch();
    });
}

function renderTab(label, slug, currentType, currentPromo) {
    const active = slug === currentType;
    const promoQ = currentPromo ? `&promotion=${encodeURIComponent(currentPromo)}` : "";
    return `<a href="events.html?type=${slug}${promoQ}" class="events-tab ${active ? "active" : ""}">${esc(label)}</a>`;
}

// Couleur de marque par promotion (sinon couleur stable dérivée du nom)
function promoColor(promo) {
    const key = (promo || "").toUpperCase();
    const brand = {
        "UFC":"#e02a31", "PFL":"#2f7bf0", "ONE":"#d4a02a", "BELLATOR":"#e23a2e",
        "BKFC":"#c84030", "RIZIN":"#e0408f", "KSW":"#e8b21e", "LFA":"#3aa0e0",
        "ACA":"#8b6cd6", "CAGE WARRIORS":"#2bb673", "ROAD FC":"#e05a2b",
        "BRAVE":"#d4a02a", "INVICTA":"#d04a8f", "COMBATE":"#e0a52a", "EFC":"#3bb0a0",
    };
    for (const k in brand) { if (key.includes(k)) return brand[k]; }
    // fallback : hash → palette (couleur stable par promo, jamais juste gris)
    const pal = ["#5b8def","#2bb673","#d4863c","#9b6cd0","#cf5b8a","#3bb0b0","#c0894a","#d05b5b"];
    let h = 0;
    for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
    return pal[h % pal.length];
}

function renderEventCard(ev) {
    const dt = ev.date ? new Date(ev.date) : null;
    const month = dt ? dt.toLocaleDateString("en-US", { month: "short" }).toUpperCase() : "—";
    const day   = dt ? dt.getDate() : "?";
    const dow   = dt ? dt.toLocaleDateString("en-US", { weekday: "short" }).toUpperCase() : "";
    const year  = dt ? dt.getFullYear() : "";

    const locParts = [ev.venue, ev.city, ev.country].filter(Boolean);
    const location = locParts.length ? locParts.join(" · ") : t("events.location_tba");

    // On utilise effective_status (calcule dynamiquement par l'API depuis la date)
    // plutot que status (fige au scrape). Permet l'overlap 1 jour upcoming↔results.
    const effStatus = ev.effective_status || ev.status;
    const statusPill = effStatus === "upcoming"
        ? `<span class="ev-status-pill upcoming">${t("events.status_upcoming")}</span>`
        : effStatus === "cancelled"
        ? `<span class="ev-status-pill cancelled">${t("events.status_cancelled")}</span>`
        : `<span class="ev-status-pill completed">${t("events.status_completed")}</span>`;

    const color = promoColor(ev.promotion);
    const promoChip = ev.promotion
        ? `<span class="event-card-promo">${esc(ev.promotion)}</span>` : "";

    return `
        <a href="event.html?id=${ev.id}" class="event-card" style="--promo:${color}">
            <div class="event-date-tile">
                <span class="edt-month">${esc(month)}</span>
                <span class="edt-day">${esc(String(day))}</span>
                <span class="edt-dow">${esc(dow)}</span>
            </div>
            <div class="event-card-body">
                <div class="event-card-head">
                    ${promoChip}
                    ${statusPill}
                </div>
                <div class="event-card-title">${esc(ev.name || "—")}</div>
                <div class="event-card-meta">
                    <span class="event-card-meta-item ec-loc">${esc(location)}</span>
                </div>
            </div>
            <div class="event-card-right">
                ${ev.fight_count ? `<span class="event-bouts"><b>${ev.fight_count}</b> ${t("events.bouts")}</span>` : ""}
                ${year ? `<span class="event-year">${esc(String(year))}</span>` : ""}
                <span class="event-card-cta">${t("events.view")}</span>
            </div>
        </a>
    `;
}
