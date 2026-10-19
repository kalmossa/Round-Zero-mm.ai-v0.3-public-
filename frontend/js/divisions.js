// MM.AI — Page Divisions (redesign 2026)
// Utilise /api/divisions (champion + top fighters + count par division)
// Carte visuelle par division : couleur unique, champion photo, contenders.

// Couleur accent par division de base (léger → lourd = bleu → rouge).
const DIV_COLOR = {
    "Atomweight":        { h: "#a78bfa", glow: "rgba(167,139,250,0.18)", bg: "rgba(139,92,246,0.07)"  },
    "Strawweight":       { h: "#8b5cf6", glow: "rgba(139,92,246,0.18)",  bg: "rgba(109,40,217,0.07)"  },
    "Flyweight":         { h: "#3b82f6", glow: "rgba(59,130,246,0.18)",  bg: "rgba(37,99,235,0.07)"   },
    "Bantamweight":      { h: "#06b6d4", glow: "rgba(6,182,212,0.18)",   bg: "rgba(8,145,178,0.07)"   },
    "Featherweight":     { h: "#10b981", glow: "rgba(16,185,129,0.18)",  bg: "rgba(5,150,105,0.07)"   },
    "Lightweight":       { h: "#f59e0b", glow: "rgba(245,158,11,0.18)",  bg: "rgba(217,119,6,0.07)"   },
    "Welterweight":      { h: "#f97316", glow: "rgba(249,115,22,0.18)",  bg: "rgba(234,88,12,0.07)"   },
    "Middleweight":      { h: "#ef4444", glow: "rgba(239,68,68,0.18)",   bg: "rgba(220,38,38,0.07)"   },
    "Light Heavyweight": { h: "#dc2626", glow: "rgba(220,38,38,0.20)",   bg: "rgba(185,28,28,0.08)"   },
    "Heavyweight":       { h: "#b91c1c", glow: "rgba(185,28,28,0.22)",   bg: "rgba(153,27,27,0.10)"   },
};
// Femmes : couleur de base + nuance violet
const DIV_COLOR_W = {
    "Atomweight":  { h: "#c084fc", glow: "rgba(192,132,252,0.20)", bg: "rgba(168,85,247,0.08)" },
    "Strawweight": { h: "#a855f7", glow: "rgba(168,85,247,0.20)",  bg: "rgba(126,34,206,0.08)" },
    "Flyweight":   { h: "#818cf8", glow: "rgba(129,140,248,0.20)", bg: "rgba(99,102,241,0.08)" },
    "Bantamweight":{ h: "#e879f9", glow: "rgba(232,121,249,0.20)", bg: "rgba(192,38,211,0.08)" },
    "Featherweight":{ h: "#c026d3", glow: "rgba(192,38,211,0.20)", bg: "rgba(162,28,175,0.08)" },
};

const WEIGHT_LIMITS = {
    "Atomweight":        "105 lbs / 48 kg",
    "Strawweight":       "115 lbs / 52 kg",
    "Flyweight":         "125 lbs / 57 kg",
    "Bantamweight":      "135 lbs / 61 kg",
    "Featherweight":     "145 lbs / 66 kg",
    "Lightweight":       "155 lbs / 70 kg",
    "Welterweight":      "170 lbs / 77 kg",
    "Middleweight":      "185 lbs / 84 kg",
    "Light Heavyweight": "205 lbs / 93 kg",
    "Heavyweight":       "265 lbs / 120 kg",
};

const MEN_ORDER = [
    "Flyweight","Bantamweight","Featherweight","Lightweight",
    "Welterweight","Middleweight","Light Heavyweight","Heavyweight",
];
const WOMEN_ORDER = [
    "Atomweight","Strawweight","Flyweight","Bantamweight","Featherweight",
];

// Normalise le nom de division vers la clé de base (retire le préfixe Women's).
function _baseDiv(name) {
    return name.replace(/^Women'?s?\s+/i, "").trim();
}
function _isWomen(name) {
    return /^Women'?s?\s/i.test(name) || name.includes("Women");
}

// l'affichage principal de la page
async function renderDivisionsPage() {
    setupNavSearch();
    const root = $("#divisions-list");
    try {
        const divs = await api.divisions();
        // Indexer par clé "base|gender"
        const byKey = {};
        divs.forEach(d => {
            const base   = _baseDiv(d.name);
            const gender = _isWomen(d.name) ? "F" : "M";
            byKey[`${base}|${gender}`] = d;
        });

        const section = (labelKey, order, gender, headCls) => {
            const cards = order.map(base => {
                const d = byKey[`${base}|${gender}`];
                return d ? divCard(base, gender, d) : "";
            }).filter(Boolean).join("");
            if (!cards) return "";
            return `
                <div class="dv-section">
                    <h2 class="dv-heading ${headCls}">
                        <span>${t(labelKey)}</span>
                    </h2>
                    <div class="dv-card-grid">${cards}</div>
                </div>`;
        };

        const html =
            section("common.men",   MEN_ORDER,   "M", "") +
            section("common.women", WOMEN_ORDER, "F", "dv-heading-w");

        root.innerHTML = html || `<div class="empty"><h3>${t("divisions.no_division")}</h3></div>`;
    } catch (e) {
        showError(root, e.message);
    }
}

// Carte individuelle
function divCard(base, gender, data) {
    const col  = (gender === "F" ? DIV_COLOR_W[base] : DIV_COLOR[base])
               || { h: "var(--primary-2)", glow: "rgba(255,39,48,0.15)", bg: "rgba(210,10,17,0.06)" };
    const lim  = WEIGHT_LIMITS[base] || "";
    const lbs  = lim ? lim.split(" ")[0] : "";
    const name = formatWeightClassLong(base, gender);
    const abbr = formatWeightClassShort(base, gender);
    const urlR = `ranking.html?wc=${encodeURIComponent(base)}&gender=${gender}`;
    const urlS = `roster.html?wc=${encodeURIComponent(base)}&gender=${gender}`;

    const champ  = data.champion;
    const top    = (data.top || []).filter(f => !f.is_ufc_champion).slice(0, 3);
    const count  = data.count || 0;

    // Blocs HTML internes
    const champBlock = champ
        ? `<div class="dv-card-champ" data-fighter-id="${champ.id}" data-fighter-name="${esc(champ.name)}" data-hc-restricted>
               ${champPhoto(champ, col.h)}
               <div class="dv-card-champ-info">
                   <div class="dv-card-champ-belt">
                       <svg width="12" height="12" viewBox="0 0 24 24" fill="${col.h}" aria-hidden="true"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
                       Champion
                   </div>
                   <a href="fighter.html?id=${champ.id}" class="dv-card-champ-name" style="color:${col.h};" data-fighter-id="${champ.id}" data-fighter-name="${esc(champ.name)}">${esc(champ.name)}</a>
                   <div class="dv-card-champ-rec">${champ.record_total_wins || 0}-${champ.record_total_losses || 0}${(champ.record_total_draws||0)>0?"-"+champ.record_total_draws:""}</div>
               </div>
           </div>`
        : `<div class="dv-card-champ dv-card-champ-vacant">
               <div class="dv-card-champ-vacant-icon" style="border-color:${col.h};">?</div>
               <div class="dv-card-champ-info">
                   <div class="dv-card-champ-belt" style="color:var(--text-dim);">Champion</div>
                   <div class="dv-card-champ-name" style="color:var(--text-muted);">Vacant</div>
               </div>
           </div>`;

    const contendersBlock = top.length
        ? `<div class="dv-card-contenders">
               <div class="dv-card-cont-label">Top contenders</div>
               <div class="dv-card-cont-row">
                   ${top.map((f, i) => contenderAvatar(f, i + 1, col.h)).join("")}
               </div>
           </div>`
        : "";

    return `
        <div class="dv-card" style="--div-color:${col.h}; --div-glow:${col.glow}; --div-bg:${col.bg};">
            <div class="dv-card-top-bar" style="background:linear-gradient(90deg,${col.h},${col.h}99);"></div>

            <div class="dv-card-header">
                <div class="dv-card-abbr" style="color:${col.h}; background:${col.bg}; border-color:${col.h}44;">${esc(abbr)}</div>
                <div class="dv-card-meta">
                    <div class="dv-card-name">${esc(name)}</div>
                    <div class="dv-card-meta-row">
                        ${lim ? `<span class="dv-card-lbs-chip" style="color:${col.h}; border-color:${col.h}44;">${esc(lim.replace(" / ", " · "))}</span>` : ""}
                        <span class="dv-card-count-info"><b style="color:${col.h};">${count}</b> ${t("common.fighters")}</span>
                    </div>
                </div>
            </div>

            <div class="dv-card-body">
                ${champBlock}
                ${contendersBlock}
            </div>

            <div class="dv-card-actions">
                <a href="${urlR}" class="dv-card-btn dv-card-btn-primary" style="--btn-color:${col.h};">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M8 6l4-4 4 4"/><path d="M12 2v10.5"/><rect x="2" y="14" width="20" height="8" rx="2"/></svg>
                    Rankings
                </a>
                <a href="${urlS}" class="dv-card-btn dv-card-btn-secondary">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                    Roster
                </a>
            </div>
        </div>`;
}

// Photo du champion avec fallback initiales
function champPhoto(f, color) {
    const photo = f.photo_thumbnail_url || f.photo_url;
    const init  = initials(f.name);
    return `
        <a href="fighter.html?id=${f.id}" class="dv-card-champ-photo" style="border-color:${color}cc;" data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}">
            ${photo
                ? `<img src="${esc(photo)}" alt="${esc(f.name)}" loading="lazy"
                       onerror="this.parentNode.innerHTML='<div class=\\'dv-champ-init\\'>${esc(init)}</div>'">`
                : `<div class="dv-champ-init" style="color:${color};">${esc(init)}</div>`}
        </a>`;
}

// Avatar de contender (#N)
function contenderAvatar(f, rank, color) {
    const photo = f.photo_thumbnail_url || f.photo_url;
    const init  = initials(f.name);
    return `
        <a href="fighter.html?id=${f.id}" class="dv-cont-av" title="${esc(f.name)} • #${rank}" data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}">
            <div class="dv-cont-av-img">
                ${photo
                    ? `<img src="${esc(photo)}" alt="${esc(f.name)}" loading="lazy"
                           onerror="this.parentNode.innerHTML='<span>${esc(init)}</span>'">`
                    : `<span>${esc(init)}</span>`}
            </div>
            <div class="dv-cont-av-rank" style="background:${color};">#${rank}</div>
        </a>`;
}
