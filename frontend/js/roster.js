// MM.AI - roster.js : TOUS les combattants d'une division, en vrac, paginés.
// Réutilise /api/fighters (token "base|gender" + sort + limit/offset + total).

const ROSTER_PAGE_SIZE = 50;

async function renderRosterPage() {
    setupNavSearch();
    const root   = document.getElementById("roster-root");
    const wc     = getQueryParam("wc") || "";
    const gender = (getQueryParam("gender") || "M").toUpperCase();
    if (!wc) {
        root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="error-box">No division specified.</div></div>`;
        return;
    }

    const label = formatWeightClassLong(wc, gender === "F" ? "F" : "M");
    document.title = `${label} — MM.AI`;

    const state = {
        page: Math.max(1, parseInt(getQueryParam("page") || "1", 10) || 1),
        sort: getQueryParam("sort") || "name",
    };

    root.innerHTML = `
        <section class="rs-hero">
            <div class="container">
                <button class="back-btn" onclick="location.href='divisions.html'">${t("common.back")}</button>
                <div class="rs-hero-row">
                    <div class="rs-hero-text">
                        <div class="rs-pill">${gender === "F" ? t("division.womens") : t("division.mens")} division</div>
                        <h1 class="rs-title">${esc(label)}</h1>
                        <p class="rs-sub" id="rs-sub">${t("roster.sub")}</p>
                    </div>
                    <div class="rs-controls">
                        <label for="rs-sort">${t("common.sort_by")}</label>
                        <select id="rs-sort">
                            <option value="name">${t("fighters.sort_name")}</option>
                            <option value="wins">${t("fighters.sort_wins")}</option>
                            <option value="rating">${t("fighters.sort_rating")}</option>
                            <option value="recent">${t("fighters.sort_recent")}</option>
                        </select>
                    </div>
                </div>
            </div>
        </section>
        <div class="container">
            <div class="rs-list" id="rs-list"><div class="loader">${t("common.loading")}</div></div>
            <div class="rs-pagination" id="rs-pagination"></div>
        </div>
    `;

    const sortSel = document.getElementById("rs-sort");
    sortSel.value = state.sort;
    sortSel.addEventListener("change", () => { state.sort = sortSel.value; state.page = 1; updateUrl(); load(); });

    function updateUrl() {
        const u = new URL(location.href);
        u.searchParams.set("page", state.page);
        u.searchParams.set("sort", state.sort);
        history.replaceState(null, "", u);
    }

    async function load() {
        const list = document.getElementById("rs-list");
        const pag  = document.getElementById("rs-pagination");
        list.innerHTML = `<div class="loader">${t("common.loading")}</div>`;
        pag.innerHTML = "";
        try {
            const data = await api.fighters({
                weight_class: `${wc}|${gender}`,
                sort: state.sort,
                limit: ROSTER_PAGE_SIZE,
                offset: (state.page - 1) * ROSTER_PAGE_SIZE,
            });
            const total = data.total || 0;
            const totalPages = Math.max(1, Math.ceil(total / ROSTER_PAGE_SIZE));
            if (state.page > totalPages) { state.page = totalPages; return load(); }
            document.getElementById("rs-sub").textContent = `${total} ${t("common.fighters")} · ${t("roster.sub")}`;
            if (!data.fighters.length) {
                list.innerHTML = `<div class="empty"><h3>${t("common.no_results")}</h3></div>`;
                return;
            }
            const startIdx = (state.page - 1) * ROSTER_PAGE_SIZE;
            list.innerHTML = data.fighters.map((f, i) => rosterRow(f, startIdx + i + 1)).join("");
            if (typeof window._hcPrefill === "function") data.fighters.forEach(window._hcPrefill);
            pag.innerHTML = buildPagination(state.page, totalPages);
            pag.querySelectorAll("[data-page]:not([disabled])").forEach(b => {
                b.addEventListener("click", () => {
                    const p = parseInt(b.dataset.page, 10);
                    if (p && p !== state.page) {
                        state.page = p; updateUrl(); load();
                        window.scrollTo({ top: 0, behavior: "smooth" });
                    }
                });
            });
        } catch (e) {
            list.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
        }
    }

    load();
}

function rosterRow(f, pos) {
    const photo = f.photo_thumbnail_url || f.photo_url;
    const av = photo
        ? `<span class="rs-av" data-hc-zone><img src="${esc(photo)}" alt="${esc(f.name)}" loading="lazy" onerror="this.parentNode.classList.add('no-photo');this.parentNode.textContent='${esc(initials(f.name))}'"></span>`
        : `<span class="rs-av no-photo" data-hc-zone>${esc(initials(f.name))}</span>`;
    const flag = nationalityToFlagHTML(f.nationality);
    const w = f.record_total_wins ?? 0, l = f.record_total_losses ?? 0, d = f.record_total_draws ?? 0;
    const rec = `<span class="w">${w}</span>-<span class="l">${l}</span>${d > 0 ? `-<span class="d">${d}</span>` : ""}`;
    const rating = f.fightmatrix_rating_points ?? f.base_elo;
    let tag = "";
    if (f.is_ufc_champion) tag = `<span class="rs-tag champ">C</span>`;
    else if (f.ufc_official_rank) tag = `<span class="rs-tag rank">#${f.ufc_official_rank}</span>`;

    return `
        <a href="fighter.html?id=${f.id}" class="rs-row" data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}" data-hc-restricted>
            <span class="rs-pos">${pos}</span>
            <span data-hc-zone>${av}</span>
            <span class="rs-info">
                <span class="rs-name"><span data-hc-zone>${esc(f.name)}</span>${tag}${!f.is_active ? `<span class="rs-tag off">${t("common.inactive")}</span>` : ""}</span>
                ${f.nickname ? `<span class="rs-nick">"${esc(f.nickname)}"</span>` : ""}
            </span>
            <span class="rs-flag">${flag || ""}</span>
            <span class="rs-rec">${rec}</span>
            <span class="rs-last5">${last5Pills(f.last_5_results)}</span>
            <span class="rs-rating">${rating ? fmtNumber(rating, 0) : '<span class="muted">--</span>'}</span>
        </a>`;
}

function buildPagination(page, totalPages) {
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
