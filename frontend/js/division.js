// MM.AI — division.js
// Page d'UNE division : Champion + tous les fighters (rangés par UFC rank puis MM.AI rating)

async function renderDivisionPage() {
    const root = document.getElementById("division-root");
    const wc     = getQueryParam("wc") || "";
    const gender = (getQueryParam("gender") || "M").toUpperCase();

    if (!wc) {
        root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="error-box">No division specified.</div></div>`;
        return;
    }

    setupNavSearch();
    const display = `${wc}${gender === "F" ? " W" : " M"}`;
    document.title = `${display} — MM.AI`;

    try {
        // Tous les fighters de la division : token genre "base|gender" -> le backend
        // matche la division canonique + le genre (gere les "Women's X" en base).
        const data = await api.rankings({ weight_class: `${wc}|${gender}`, sort: "fightmatrix", limit: 200 });
        const all = (data.fighters || []).filter(f => (f.gender || "M").toUpperCase() === gender);

        const champion = all.find(f => f.is_ufc_champion) || null;
        // Ranked = UFC rank 1..15 (exclu champion)
        const ranked = all
            .filter(f => !f.is_ufc_champion && f.ufc_official_rank && f.ufc_official_rank <= 15)
            .sort((a, b) => (a.ufc_official_rank || 999) - (b.ufc_official_rank || 999));
        // Tous les autres
        const others = all
            .filter(f => !f.is_ufc_champion && (!f.ufc_official_rank || f.ufc_official_rank > 15))
            .sort((a, b) => (b.fightmatrix_rating_points || 0) - (a.fightmatrix_rating_points || 0));

        root.innerHTML = renderDivisionDetail(display, wc, gender, champion, ranked, others, all.length);
        if (typeof window._hcPrefill === "function") all.forEach(window._hcPrefill);
    } catch (e) {
        root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="error-box">Error: ${esc(e.message)}</div></div>`;
    }
}

function renderDivisionDetail(displayName, wc, gender, champion, ranked, others, totalCount) {
    const champBlock = champion ? renderChampionCard(champion) : `
        <div class="div-champion-empty">
            <div class="div-champ-label">UFC Champion</div>
            <div class="div-champ-vacant">— Vacant —</div>
        </div>
    `;

    const rankedRows = ranked.map((f, i) => renderDivRow(f, i + 1, "ranked")).join("");
    const othersRows = others.map((f, i) => renderDivRow(f, i + 1, "other")).join("");

    const rankedSection = ranked.length ? `
        <section class="div-section">
            <div class="div-section-header">
                <h2 class="div-section-title">${t("division.top15_title")}</h2>
                <span class="div-section-meta">${ranked.length} ${t("division.ranked_contenders")}</span>
            </div>
            <div class="div-roster-list">${rankedRows}</div>
        </section>
    ` : "";

    const othersSection = others.length ? `
        <section class="div-section">
            <div class="div-section-header">
                <h2 class="div-section-title">${ranked.length ? t("division.other_fighters") : t("division.all_fighters")}</h2>
                <span class="div-section-meta">${others.length} ${t("common.fighters")}</span>
            </div>
            <div class="div-roster-list">${othersRows}</div>
        </section>
    ` : "";

    return `
        <div class="container">
            <a href="divisions.html" class="back-btn" style="margin:24px 0 0;" onclick="if(history.length>1&&document.referrer&&document.referrer.startsWith(location.origin)){event.preventDefault();history.back();}">${t("common.back")}</a>

            <section class="div-hero">
                <div class="div-hero-inner">
                    <div class="div-hero-text">
                        <div class="div-pill">${gender === "F" ? t("division.womens") : t("division.mens")} division</div>
                        <h1 class="div-title">${esc(displayName)}</h1>
                        <p class="div-sub">${totalCount} ${t("division.in_db")}</p>
                    </div>
                </div>
            </section>

            <section class="div-section div-section-champion">
                ${champBlock}
            </section>

            ${rankedSection}
            ${othersSection}

            ${!ranked.length && !others.length ? `
                <div class="empty"><h3>${t("division.no_fighters")}</h3><p>${t("division.no_fighters_sub")}</p></div>
            ` : ""}
        </div>
    `;
}

function renderChampionCard(f) {
    const photo = f.photo_thumbnail_url || f.photo_url;
    const photoBlock = photo
        ? `<img src="${esc(photo)}" alt="${esc(f.name)}" loading="lazy">`
        : `<div class="no-photo champ-no-photo">${esc(initials(f.name))}</div>`;
    const flag = nationalityToFlagHTML(f.nationality);
    const w = f.record_total_wins ?? 0, l = f.record_total_losses ?? 0, d = f.record_total_draws ?? 0;
    const nat = nationalityEnglish(f.nationality);

    return `
        <a href="fighter.html?id=${f.id}" class="div-champion-card" data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}" data-hc-restricted>
            <div class="div-champion-belt">${t("division.ufc_champion")}</div>
            <div class="div-champion-grid">
                <div class="div-champion-photo" data-hc-zone>${photoBlock}</div>
                <div class="div-champion-info">
                    ${f.nickname ? `<div class="div-champion-nick">"${esc(f.nickname)}"</div>` : ""}
                    <div class="div-champion-name"><span data-hc-zone>${esc(f.name)}</span></div>
                    <div class="div-champion-sub">
                        ${flag ? `<span class="div-champion-flag">${flag}</span>` : ""}
                        <span class="div-champion-nat">${esc(nat)}</span>
                    </div>
                    <div class="div-champion-record">
                        <span class="w">${w}</span>-<span class="l">${l}</span>${d > 0 ? `-<span class="d">${d}</span>` : ""}
                        <span class="div-champion-record-lbl">${t("division.pro_record")}</span>
                    </div>
                </div>
            </div>
        </a>
    `;
}

function renderDivRow(f, posInSection, kind) {
    const photo = f.photo_thumbnail_url || f.photo_url;
    const photoBlock = photo
        ? `<img src="${esc(photo)}" alt="${esc(f.name)}" loading="lazy" class="dr-photo">`
        : `<div class="dr-photo dr-no-photo">${esc(initials(f.name))}</div>`;
    const flag = nationalityToFlagHTML(f.nationality);
    const w = f.record_total_wins ?? 0, l = f.record_total_losses ?? 0, d = f.record_total_draws ?? 0;
    const nat = nationalityEnglish(f.nationality);

    // UFC rank badge si dispo (kind=ranked), sinon position numerique pour kind=other
    const rankBadge = kind === "ranked" && f.ufc_official_rank
        ? `<div class="dr-rank ufc">#${f.ufc_official_rank}</div>`
        : `<div class="dr-rank pos">${posInSection}</div>`;

    const last5 = (typeof last5Pills === "function" && f.last_5_results)
        ? last5Pills(f.last_5_results)
        : "";

    return `
        <a href="fighter.html?id=${f.id}" class="div-ranked-row" data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}" data-hc-restricted>
            ${rankBadge}
            <div class="dr-photo-wrap" data-hc-zone>${photoBlock}</div>
            <div class="dr-info">
                <div class="dr-name"><span data-hc-zone>${esc(f.name)}</span></div>
                <div class="dr-sub">
                    ${flag ? `<span class="dr-flag">${flag}</span>` : ""}
                    <span class="dr-nat">${esc(nat)}</span>
                </div>
            </div>
            <div class="dr-record">
                <span class="dr-rec-val"><span class="w">${w}</span>-<span class="l">${l}</span>${d > 0 ? `-<span class="d">${d}</span>` : ""}</span>
                <span class="dr-rec-lbl">Record</span>
            </div>
            <div class="dr-last5">${last5 || '<span class="muted">--</span>'}</div>
        </a>
    `;
}
