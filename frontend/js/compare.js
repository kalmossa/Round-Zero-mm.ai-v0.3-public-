// MM.AI - Page Compare (face-a-face detaille en onglets, SANS prediction)
// La prediction complete vit dans matchmaking.html
//
// Vue "tale of the tape" enrichie : memes onglets que la fiche fighter
// (Statistics / Ratings / History / Career / Bio), en double colonne, avec
// highlight du meilleur cote. Garde-fou : avertissement si les deux fighters
// sont a plus de 2 categories de poids d'ecart ou de genres differents.

const selectedFighters = { 1: null, 2: null };
const cmpHist = { 1: null, 2: null };   // cache des fight histories (+ elo_timeline)

// Ladders identiques au serveur (api/app.py) pour mesurer l'ecart de division.
const CMP_MEN_LADDER = [
    "flyweight", "bantamweight", "featherweight", "lightweight",
    "welterweight", "middleweight", "light heavyweight", "heavyweight",
];
const CMP_WOMEN_LADDER = [
    "atomweight", "strawweight", "flyweight", "bantamweight",
    "featherweight", "lightweight",
];

// UFC rank : ufc_official_rank = 0 en BDD pour les champions (INT) -> afficher "Champion"
function fmtUFCRank(f) {
    if (f.is_ufc_champion) return t("common.champion");
    if (f.ufc_official_rank === 0) return t("common.champion");
    return f.ufc_official_rank != null ? "#" + f.ufc_official_rank : null;
}

async function renderComparePage() {
    setupNavSearch();

    $$(".vs-search").forEach(input => {
        const side = input.dataset.side;
        input.addEventListener("input", debounce(async () => {
            const q = input.value.trim();
            const resultsBox = $(`.vs-results[data-side="${side}"]`);
            if (q.length < 2) { resultsBox.innerHTML = ""; resultsBox.classList.remove("open"); return; }
            try {
                const data = await api.fighters({ search: q, limit: 8 });
                if (!data.fighters.length) {
                    resultsBox.innerHTML = `<div class="vs-result-empty">No results</div>`;
                    resultsBox.classList.add("open");
                    return;
                }
                resultsBox.innerHTML = data.fighters.map(f => `
                    <div class="vs-result" data-id="${f.id}">
                        ${avatar(f)}
                        <div class="info">
                            <div class="name">${esc(f.name)}</div>
                            <div class="sub">${esc(f.weight_class_current || "--")} • ${f.record_total_wins || 0}-${f.record_total_losses || 0}</div>
                        </div>
                    </div>
                `).join("");
                resultsBox.classList.add("open");
                resultsBox.querySelectorAll(".vs-result").forEach(el => {
                    el.addEventListener("click", () => {
                        selectFighter(side, Number(el.dataset.id));
                        resultsBox.innerHTML = "";
                        resultsBox.classList.remove("open");
                        input.value = "";
                    });
                });
            } catch (e) {
                resultsBox.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
                resultsBox.classList.add("open");
            }
        }, 250));
    });

    const id1 = getQueryParam("id1");
    const id2 = getQueryParam("id2");
    if (id1) selectFighter(1, Number(id1));
    if (id2) selectFighter(2, Number(id2));

    $("#reset-btn").addEventListener("click", () => {
        selectedFighters[1] = null; selectedFighters[2] = null;
        cmpHist[1] = null; cmpHist[2] = null;
        renderSelected(1); renderSelected(2);
        $("#compare-table-wrap").style.display = "none";
    });
}

async function selectFighter(side, id) {
    try {
        const f = await api.fighter(id);
        selectedFighters[side] = f;
        cmpHist[side] = null;   // invalide le cache de ce cote
        renderSelected(side);
        if (selectedFighters[1] && selectedFighters[2]) renderComparison();
        else $("#compare-table-wrap").style.display = "none";
    } catch (e) {
        alert("Error: " + e.message);
    }
}

function renderSelected(side) {
    const card = $(`.vs-card[data-side="${side}"]`);
    const f = selectedFighters[side];
    if (!f) {
        card.classList.add("empty-card");
        card.innerHTML = `
            <div class="vs-empty">
                <div class="vs-empty-icon">?</div>
                <p>${t("common.select_fighter")}</p>
            </div>
        `;
        return;
    }
    card.classList.remove("empty-card");
    const photo = f.photo_thumbnail_url || f.photo_url;
    card.innerHTML = `
        <button class="vs-clear" title="${t("common.remove")}" onclick="clearSide(${side})">&times;</button>
        <div class="vs-photo">
            ${photo
                ? `<img src="${esc(photo)}" alt="${esc(f.name)}" onerror="this.parentNode.innerHTML='<div class=&quot;no-photo&quot;>${esc(initials(f.name))}</div>'">`
                : `<div class="no-photo">${esc(initials(f.name))}</div>`}
        </div>
        <div class="vs-info">
            ${f.is_ufc_champion ? `<div class="vs-champ-tag">Champion ${esc(f.weight_class_current || "")}</div>` : ""}
            <h3 class="vs-name">${esc(f.name)}</h3>
            ${f.nickname ? `<div class="vs-nickname">"${esc(f.nickname)}"</div>` : ""}
            <div class="vs-record">
                <span class="rec">${f.record_total_wins || 0}-${f.record_total_losses || 0}${(f.record_total_draws||0)>0?"-"+f.record_total_draws:""}</span>
                <span class="rec-label">${t("common.record")}</span>
            </div>
            <div class="vs-tags">
                ${f.weight_class_current ? `<span class="profile-tag">${esc(f.weight_class_current)}</span>` : ""}
                ${f.nationality ? `<span class="profile-tag">${esc(f.nationality)}</span>` : ""}
                ${f.stance ? `<span class="profile-tag">${esc(f.stance)}</span>` : ""}
            </div>
            <div style="margin-top:14px;">
                <a href="matchmaking.html?id1=${selectedFighters[1]?.id || ''}&id2=${selectedFighters[2]?.id || ''}" class="btn btn-primary" style="width:100%; justify-content:center;${(selectedFighters[1] && selectedFighters[2]) ? '' : 'opacity:0.5; pointer-events:none;'}">${t("compare.launch_predict")}</a>
            </div>
        </div>
    `;
}

function clearSide(side) {
    selectedFighters[side] = null;
    cmpHist[side] = null;
    renderSelected(side);
    $("#compare-table-wrap").style.display = "none";
}
window.clearSide = clearSide;

// Garde-fou : ecart de division / genre
// Retourne { status, message, gap } avec status ∈ "ok" | "warn" | "block".
//   - cross-gender                     -> warn (comparaison indicative)
//   - ecart >= 3 categories            -> block (on refuse : les pools d'Elo sont
//                                         relatifs a la division, ca ne rime a rien)
//   - ecart == 2 categories            -> warn
//   - categorie inconnue / hors ladder -> ok (on laisse faire)
function divisionCompat(f1, f2) {
    const g1 = String(f1.gender || "M").toUpperCase()[0];
    const g2 = String(f2.gender || "M").toUpperCase()[0];
    if (g1 !== g2) return { status: "warn", message: t("compare.warn_cross_gender"), gap: null };

    const w1 = parseWC(f1.weight_class_current, f1.gender).key;
    const w2 = parseWC(f2.weight_class_current, f2.gender).key;
    if (!w1 || !w2 || w1 === "unknown" || w2 === "unknown") return { status: "ok", gap: null };

    const ladder = g1 === "F" ? CMP_WOMEN_LADDER : CMP_MEN_LADDER;
    const p1 = ladder.indexOf(w1), p2 = ladder.indexOf(w2);
    if (p1 < 0 || p2 < 0) return { status: "ok", gap: null };   // hors ladder -> on laisse passer

    const gap = Math.abs(p1 - p2);
    if (gap >= 3) return { status: "block", message: t("compare.block_weight_gap", { gap }), gap };
    if (gap === 2) return { status: "warn", message: t("compare.warn_weight_gap"), gap };
    return { status: "ok", gap };
}

// base_elo / Elo : comparable seulement A L'INTERIEUR d'une meme division (les
// pools convergent par categorie). Si les deux fighters ne sont pas dans la meme
// division (ou cross-gender), on AFFICHE l'Elo mais on ne le compte pas comme
// critere (pas de "vainqueur" sur cette ligne). Categorie inconnue -> on laisse.
function isCrossDivision(f1, f2) {
    const g1 = String(f1.gender || "M").toUpperCase()[0];
    const g2 = String(f2.gender || "M").toUpperCase()[0];
    if (g1 !== g2) return true;
    const w1 = parseWC(f1.weight_class_current, f1.gender).key;
    const w2 = parseWC(f2.weight_class_current, f2.gender).key;
    if (!w1 || !w2 || w1 === "unknown" || w2 === "unknown") return false;
    return w1 !== w2;
}

// Rendu principal : onglets
function renderComparison() {
    const f1 = selectedFighters[1], f2 = selectedFighters[2];
    if (!f1 || !f2) return;

    const wrap = $("#compare-table-wrap");
    wrap.style.display = "block";

    const compat = divisionCompat(f1, f2);

    // Ecart >= 3 categories : on BLOQUE la comparaison (elle n'aurait pas de sens).
    if (compat.status === "block") {
        wrap.innerHTML = `
            <div class="cmp-blocked">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="10"/><line x1="4.9" y1="4.9" x2="19.1" y2="19.1"/></svg>
                <h3>${t("compare.blocked_title")}</h3>
                <p>${esc(compat.message)}</p>
            </div>`;
        return;
    }

    const warnHtml = compat.status === "warn" ? `
        <div class="cmp-warning">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <span>${esc(compat.message)}</span>
        </div>` : "";

    wrap.innerHTML = `
        ${warnHtml}
        <div class="cmp-tabs profile-tabs">
            <button class="tab-btn active" data-ctab="stats">${t("profile.tab_stats")}</button>
            <button class="tab-btn" data-ctab="ratings">${t("profile.tab_ratings")}</button>
            <button class="tab-btn" data-ctab="history">${t("profile.tab_history")}</button>
            <button class="tab-btn" data-ctab="career">${t("profile.tab_career")}</button>
            <button class="tab-btn" data-ctab="bio">${t("profile.tab_bio")}</button>
        </div>
        <div class="cmp-pane active" data-cpane="stats">${cmpStatsPane(f1, f2)}</div>
        <div class="cmp-pane" data-cpane="ratings">${cmpRatingsPane(f1, f2)}</div>
        <div class="cmp-pane" data-cpane="history"><div class="loader" style="padding:40px;">${t("common.loading")}</div></div>
        <div class="cmp-pane" data-cpane="career">${cmpCareerPane(f1, f2)}</div>
        <div class="cmp-pane" data-cpane="bio">${cmpBioPane(f1, f2)}</div>
    `;
    wireCmpTabs();
    loadCmpHistories();
}

function wireCmpTabs() {
    const wrap = $("#compare-table-wrap");
    wrap.querySelectorAll(".cmp-tabs .tab-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const tab = btn.dataset.ctab;
            wrap.querySelectorAll(".cmp-tabs .tab-btn").forEach(b => b.classList.toggle("active", b === btn));
            wrap.querySelectorAll(".cmp-pane").forEach(p => p.classList.toggle("active", p.dataset.cpane === tab));
        });
    });
}

// Tableau comparatif generique (3 colonnes : val1 | label | val2).
// rows : [label, valA, valB, mode, suffix?]
//   mode : "num" (haut = mieux), "numLow" (bas = mieux), "text" (neutre)
//   ["__section__", "Titre"] -> ligne de sous-titre pleine largeur
function cmpTable(rows) {
    const f1 = selectedFighters[1], f2 = selectedFighters[2];
    const body = rows.map(row => {
        if (row[0] === "__section__") {
            return `<tr class="cmp-section-row"><td colspan="3">${esc(row[1])}</td></tr>`;
        }
        const [label, a, b, mode = "text", suffix = ""] = row;
        let highA = "", highB = "";
        const ax = (a === null || a === undefined || a === "") ? null : Number(a);
        const bx = (b === null || b === undefined || b === "") ? null : Number(b);
        if (ax !== null && bx !== null && !Number.isNaN(ax) && !Number.isNaN(bx) && ax !== bx) {
            if (mode === "num")        { if (ax > bx) highA = "winner"; else highB = "winner"; }
            else if (mode === "numLow"){ if (ax < bx) highA = "winner"; else highB = "winner"; }
        }
        const fmt = (v) => (v === null || v === undefined || v === "") ? '<span class="muted">--</span>' : esc(v) + (suffix || "");
        return `
            <tr>
                <td class="cmp-val right ${highA}">${fmt(a)}</td>
                <td class="cmp-label">${esc(label)}</td>
                <td class="cmp-val ${highB}">${fmt(b)}</td>
            </tr>`;
    }).join("");

    return `
        <div class="ranking-table-wrap">
            <table class="ranking compare-table">
                <thead>
                    <tr>
                        <th style="text-align:right;">${esc(f1.name)}</th>
                        <th style="text-align:center;">vs</th>
                        <th>${esc(f2.name)}</th>
                    </tr>
                </thead>
                <tbody>${body}</tbody>
            </table>
        </div>`;
}

// Panes
function cmpStatsPane(f1, f2) {
    return cmpTable([
        ["__section__", t("profile.detailed_record")],
        [t("common.total_fights"), f1.total_fights, f2.total_fights, "num"],
        [t("common.wins"), f1.record_total_wins, f2.record_total_wins, "num"],
        [t("common.losses"), f1.record_total_losses, f2.record_total_losses, "numLow"],
        [t("profile.lbl_nc"), f1.record_total_nc, f2.record_total_nc, "text"],
        [t("common.win_pct"), f1.win_percentage_int, f2.win_percentage_int, "num", "%"],
        ["__section__", t("profile.win_methods")],
        ["KO/TKO", f1.wins_by_ko_tko, f2.wins_by_ko_tko, "num"],
        ["Submissions", f1.wins_by_submission, f2.wins_by_submission, "num"],
        ["Decisions", f1.wins_by_decision, f2.wins_by_decision, "num"],
        [t("common.finish_pct"), f1.finish_rate_int, f2.finish_rate_int, "num", "%"],
        ["__section__", t("profile.recent_form_section")],
        [t("profile.lbl_streak"), f1.current_streak, f2.current_streak, "text"],
        [t("profile.lbl_form_score"), f1.recent_form_score, f2.recent_form_score, "num"],
        [t("profile.lbl_days_inactive"), f1.days_inactive, f2.days_inactive, "numLow"],
    ]);
}

function cmpRatingsPane(f1, f2) {
    // base_elo comparable seulement a division egale. Cross-division -> on
    // l'affiche mais en mode neutre (pas de "vainqueur" sur cette ligne).
    const crossDiv = isCrossDivision(f1, f2);
    const eloMode = crossDiv ? "text" : "num";
    const eloLabel = t("profile.lbl_base_elo") + (crossDiv ? " *" : "");

    const table = cmpTable([
        ["__section__", t("profile.mmai_ratings")],
        [eloLabel, f1.base_elo, f2.base_elo, eloMode],
        [t("profile.lbl_scouter"), f1.scouter_rating, f2.scouter_rating, "num"],
        [t("profile.lbl_form_score"), f1.recent_form_score, f2.recent_form_score, "num"],
        ["MM.AI Rating", f1.fightmatrix_rating_points, f2.fightmatrix_rating_points, "num"],
        ["__section__", t("profile.ufc_rankings_section")],
        ["UFC Rank", fmtUFCRank(f1), fmtUFCRank(f2), "text"],
        [t("profile.lbl_p4p"), f1.ufc_p4p_rank ? "#" + f1.ufc_p4p_rank : null, f2.ufc_p4p_rank ? "#" + f2.ufc_p4p_rank : null, "text"],
    ]);
    const eloNote = crossDiv ? `<p class="cmp-note">* ${esc(t("compare.elo_cross_div_note"))}</p>` : "";
    // Radar de profil (synchrone : nourri par les champs deja charges) puis deux
    // courbes d'Elo cote a cote (remplies apres chargement des historiques).
    return `
        ${table}
        ${eloNote}
        <div class="stat-card elo-chart-card cmp-radar-card">${buildRadarChart(f1, f2)}</div>
        <div class="cmp-elo-charts">
            <div class="stat-card elo-chart-card" id="cmp-elo-1"><div class="loader" style="padding:30px;">${t("common.loading")}</div></div>
            <div class="stat-card elo-chart-card" id="cmp-elo-2"><div class="loader" style="padding:30px;">${t("common.loading")}</div></div>
        </div>`;
}

// Radar de profil comparatif (2 fighters). Axes derives des champs deja presents
// sur l'objet fighter -> AUCUNE requete supplementaire, AUCUN calcul serveur.
// 6 axes normalises 0..100. f1 = rouge (--primary), f2 = bleu (--info).
function radarAxes(f) {
    const clamp = (v) => Math.max(0, Math.min(100, Math.round(v)));
    const wins = Math.max(Number(f.record_total_wins) || 0, 1);
    // scouter_rating est deja 0..100 (calcule a la volee par l'API) ; fallback
    // sur base_elo remappe (1000..2500 -> 0..100) si absent.
    const level = (f.scouter_rating != null && f.scouter_rating !== "")
        ? Number(f.scouter_rating)
        : ((Number(f.base_elo) || 1300) - 1000) / 15;
    return [
        { key: t("compare.radar_ko"),       val: clamp((Number(f.wins_by_ko_tko)     || 0) / wins * 100) },
        { key: t("compare.radar_sub"),      val: clamp((Number(f.wins_by_submission) || 0) / wins * 100) },
        { key: t("common.win_pct"),         val: clamp(Number(f.win_percentage_int)  || 0) },
        { key: t("compare.radar_form"),     val: clamp((Number(f.recent_form_score)  || 0) * 100) },
        { key: t("compare.radar_exp"),      val: clamp(Math.min(Number(f.total_fights) || 0, 50) / 50 * 100) },
        { key: t("common.rating"),          val: clamp(level) },
    ];
}

function buildRadarChart(f1, f2) {
    const a1 = radarAxes(f1), a2 = radarAxes(f2);
    const N = a1.length;
    const W = 360, H = 320, cx = W / 2, cy = H / 2 + 4, R = 104;
    const ang = (i) => (-Math.PI / 2) + (i * 2 * Math.PI / N);
    const pt = (i, frac) => [
        +(cx + Math.cos(ang(i)) * R * frac).toFixed(1),
        +(cy + Math.sin(ang(i)) * R * frac).toFixed(1),
    ];

    const rings = [0.25, 0.5, 0.75, 1].map(fr =>
        `<polygon class="radar-ring" points="${a1.map((_, i) => pt(i, fr).join(",")).join(" ")}"/>`
    ).join("");

    const spokes = a1.map((ax, i) => {
        const [x, y] = pt(i, 1);
        const [lx, ly] = pt(i, 1.17);
        const anchor = Math.abs(lx - cx) < 8 ? "middle" : (lx > cx ? "start" : "end");
        return `<line class="radar-spoke" x1="${cx}" y1="${cy}" x2="${x}" y2="${y}"/>`
             + `<text class="radar-axis-label" x="${lx}" y="${(ly + 4).toFixed(1)}" text-anchor="${anchor}">${esc(ax.key)}</text>`;
    }).join("");

    const poly = (axes, cls) =>
        `<polygon class="radar-poly ${cls}" points="${axes.map((ax, i) => pt(i, ax.val / 100).join(",")).join(" ")}"/>`;
    const dots = (axes, cls) => axes.map((ax, i) => {
        const [x, y] = pt(i, ax.val / 100);
        return `<circle class="radar-dot ${cls}" cx="${x}" cy="${y}" r="2.6"><title>${esc(ax.key)}: ${ax.val}</title></circle>`;
    }).join("");

    return `
      <div class="elo-chart-head">
        <div class="elo-chart-title">${t("compare.radar_title")}</div>
        <div class="radar-legend">
          <span><i class="radar-leg f1"></i>${esc(f1.name)}</span>
          <span><i class="radar-leg f2"></i>${esc(f2.name)}</span>
        </div>
      </div>
      <div class="radar-wrap">
        <svg viewBox="0 0 ${W} ${H}" class="radar-svg" role="img" aria-label="Skill radar">
          ${rings}${spokes}
          ${poly(a2, "f2")}${poly(a1, "f1")}
          ${dots(a2, "f2")}${dots(a1, "f1")}
        </svg>
      </div>`;
}

function cmpCareerPane(f1, f2) {
    const g = (f) => f.gender === "F" ? t("common.female") : t("common.male");
    return cmpTable([
        ["__section__", t("profile.personal_info")],
        [t("profile.lbl_gender"), g(f1), g(f2), "text"],
        [t("profile.lbl_nationality"), nationalityEnglish(f1.nationality), nationalityEnglish(f2.nationality), "text"],
        [t("profile.lbl_dob"), f1.date_of_birth, f2.date_of_birth, "text"],
        [t("common.age"), f1.age, f2.age, "text"],
        [t("profile.lbl_first_sport"), f1.first_sport, f2.first_sport, "text"],
        ["__section__", t("profile.physical_profile")],
        [t("profile.lbl_current_div"), formatWeightClassLong(f1.weight_class_current, f1.gender), formatWeightClassLong(f2.weight_class_current, f2.gender), "text"],
        [t("profile.lbl_origin_div"), f1.weight_class_origin, f2.weight_class_origin, "text"],
        [t("profile.lbl_current_league"), f1.current_league, f2.current_league, "text"],
        [t("common.height"), f1.height_inches, f2.height_inches, "num"],
        [t("common.reach"), f1.reach_inches, f2.reach_inches, "num"],
        [t("profile.lbl_stance"), f1.stance, f2.stance, "text"],
        ["__section__", t("profile.career_section")],
        [t("profile.lbl_debut"), f1.career_debut_date, f2.career_debut_date, "text"],
        [t("profile.lbl_last_fight"), f1.last_fight_date, f2.last_fight_date, "text"],
        [t("profile.lbl_is_active"), f1.is_active ? t("common.yes") : t("common.no"), f2.is_active ? t("common.yes") : t("common.no"), "text"],
    ]);
}

function cmpBioPane(f1, f2) {
    const noteCol = (f) => {
        const note = (typeof getNote === "function") ? getNote(f) : (f.notes || "");
        return `
            <div class="cmp-bio-col">
                <h3>${esc(f.name)}</h3>
                ${note ? `<p class="cmp-bio-text">${esc(note)}</p>` : `<p class="muted">${t("profile.no_history_sub")}</p>`}
            </div>`;
    };
    return `<div class="cmp-bio-grid">${noteCol(f1)}${noteCol(f2)}</div>`;
}

// Historiques (lazy) : remplit l'onglet History + les courbes d'Elo
async function loadCmpHistories() {
    const f1 = selectedFighters[1], f2 = selectedFighters[2];
    if (!f1 || !f2) return;
    try {
        const [h1, h2] = await Promise.all([
            cmpHist[1] || api.fighterHistory(f1.id).catch(() => null),
            cmpHist[2] || api.fighterHistory(f2.id).catch(() => null),
        ]);
        cmpHist[1] = h1; cmpHist[2] = h2;

        const hp = document.querySelector('.cmp-pane[data-cpane="history"]');
        if (hp) hp.innerHTML = cmpHistoryPane(h1, h2);

        const c1 = document.getElementById("cmp-elo-1");
        const c2 = document.getElementById("cmp-elo-2");
        if (c1) c1.innerHTML = buildEloChart(h1 && h1.elo_timeline, { title: f1.name });
        if (c2) c2.innerHTML = buildEloChart(h2 && h2.elo_timeline, { title: f2.name });
    } catch (e) {
        const hp = document.querySelector('.cmp-pane[data-cpane="history"]');
        if (hp) hp.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
    }
}

function cmpHistoryPane(h1, h2) {
    const f1 = selectedFighters[1], f2 = selectedFighters[2];
    return `
        <div class="cmp-history-grid">
            <div class="cmp-history-col">
                <h3>${esc(f1.name)}</h3>
                ${cmpFightList(h1)}
            </div>
            <div class="cmp-history-col">
                <h3>${esc(f2.name)}</h3>
                ${cmpFightList(h2)}
            </div>
        </div>`;
}

function cmpFightList(hist) {
    const fights = (hist && hist.fights) ? hist.fights : [];
    if (!fights.length) return `<div class="empty" style="padding:24px;"><p>${t("profile.no_history_title")}</p></div>`;
    return `<div class="cmp-fl">` + fights.map(f => {
        const res = (f.result || "").toUpperCase();
        const cls = res === "W" ? "win" : res === "L" ? "loss" : (res === "NC" || res === "N") ? "nc" : "draw";
        const year = f.event_date ? String(f.event_date).slice(0, 4) : "";
        const opp = f.opponent_id
            ? `<a href="fighter.html?id=${f.opponent_id}">${esc(f.opponent_name || "?")}</a>`
            : esc(f.opponent_name || "?");
        const method = [esc(f.method || ""), f.round ? `R${f.round}` : ""].filter(Boolean).join(" ");
        return `
            <div class="cmp-fl-row">
                <span class="cmp-fl-res ${cls}">${esc(res || "?")}</span>
                <span class="cmp-fl-opp">${opp}</span>
                <span class="cmp-fl-method">${method}</span>
                <span class="cmp-fl-date">${esc(year)}</span>
            </div>`;
    }).join("") + `</div>`;
}
