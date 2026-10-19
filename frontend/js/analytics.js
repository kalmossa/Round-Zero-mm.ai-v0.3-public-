// MM.AI - Page Analytics (SVG vanilla, sans dependances)
// Redesign complet Mai 2026 : hero KPIs + divisions genrees + proportion bar
// + age/stance/nationalite avec drapeaux.

// Ordre du ladder (meme que le serveur) pour trier les divisions proprement.
const ANL_MEN_LADDER   = ["flyweight","bantamweight","featherweight","lightweight","welterweight","middleweight","light heavyweight","heavyweight"];
const ANL_WOMEN_LADDER = ["atomweight","strawweight","flyweight","bantamweight","featherweight","lightweight"];

async function renderAnalyticsPage() {
    setupNavSearch();
    try {
        const [stats, a] = await Promise.all([api.stats(), api.analytics()]);

        // KPI hero
        $$('[data-stat]').forEach(el => {
            const k = el.dataset.stat;
            const v = stats[k];
            el.textContent = (v == null || v === "" || v === "--")
                ? "--"
                : fmtNumber(Number(v));
        });

        // Divisions
        drawDivisions("#anl-divisions", a.by_division || []);

        // Win methods
        drawFinishBar("#anl-finish", a.finish_methods || []);

        // Age
        drawAgeChart("#anl-age", a.age_distribution || []);

        // Stance
        drawStanceChart("#anl-stance", a.by_stance || []);

        // Nationalities
        drawNationalityChart("#anl-nationality", a.by_nationality || []);

        // Finish rate par division
        drawFinishByDivision("#anl-finish-div", a.finish_by_div || []);

        // Fiabilité des données + teaser modele
        drawReliability("#anl-reliability", a.data_quality || {});

    } catch (e) {
        const err = document.getElementById("anl-error");
        if (err) { err.style.display = "block"; err.innerHTML = `<div class="error-box">${esc(e.message)}</div>`; }
        console.error("[Analytics]", e);
    }
}

// les divisions — deux panneaux (hommes / femmes), triés par ladder
function drawDivisions(selector, data) {
    const root = $(selector);
    if (!root) return;
    if (!data.length) { root.innerHTML = `<div class="empty" style="grid-column:1/-1;padding:32px;"><p>${t("common.no_data")}</p></div>`; return; }

    const WC_PROPER = {
        "atomweight":"Atomweight","strawweight":"Strawweight","flyweight":"Flyweight",
        "bantamweight":"Bantamweight","featherweight":"Featherweight","lightweight":"Lightweight",
        "welterweight":"Welterweight","middleweight":"Middleweight",
        "light heavyweight":"Light Heavyweight","heavyweight":"Heavyweight",
    };

    // On filtre chaque genre sur son ladder propre pour exclure les outliers
    // (ex: quelques fighters masculins mal classés en Strawweight/Atomweight).
    const men   = data.filter(d => d.gender === "M" && ANL_MEN_LADDER.includes((d.base||"").toLowerCase()));
    const women = data.filter(d => d.gender === "F" && ANL_WOMEN_LADDER.includes((d.base||"").toLowerCase()));

    const sortByLadder = (arr, ladder) =>
        [...arr].sort((a, b) => {
            const pa = ladder.indexOf((a.base||"").toLowerCase());
            const pb = ladder.indexOf((b.base||"").toLowerCase());
            if (pa < 0 && pb < 0) return b.count - a.count;
            if (pa < 0) return 1; if (pb < 0) return -1;
            return pa - pb;
        });

    const menSorted   = sortByLadder(men,   ANL_MEN_LADDER);
    const womenSorted = sortByLadder(women, ANL_WOMEN_LADDER);

    const maxCountAll = Math.max(1, ...data.map(d => d.count));

    const panelHtml = (rows, color, label) => {
        if (!rows.length) return "";
        const maxInPanel = Math.max(1, ...rows.map(r => r.count));
        const bars = rows.map(r => {
            const pct   = Math.round(100 * r.count / maxInPanel);
            const pctAll= Math.round(100 * r.count / maxCountAll);
            const name  = WC_PROPER[(r.base||"").toLowerCase()] || r.base || "—";
            const actPct= r.count > 0 ? Math.round(100 * r.active / r.count) : 0;
            return `
              <div class="anl-div-row">
                <div class="anl-div-name">${esc(name)}</div>
                <div class="anl-div-bar-wrap">
                  <div class="anl-div-bar" data-w="${pct}" style="width:0%; background:${color};"></div>
                </div>
                <div class="anl-div-meta">
                  <span class="anl-div-count">${fmtNumber(r.count)}</span>
                  <span class="anl-div-active">${actPct}% active</span>
                </div>
              </div>`;
        }).join("");
        return `
          <div class="anl-div-panel">
            <div class="anl-div-panel-head" style="color:${color};">${esc(label)}</div>
            <div class="anl-div-rows">${bars}</div>
          </div>`;
    };

    root.innerHTML =
        panelHtml(menSorted,   "var(--primary-2)", t("analytics.men_divisions")) +
        panelHtml(womenSorted, "var(--gold)",      t("analytics.women_divisions"));

    requestAnimationFrame(() => {
        root.querySelectorAll(".anl-div-bar").forEach(el => {
            el.style.width = el.dataset.w + "%";
        });
    });
}

// les méthodes de victoire — grande barre proportionnelle
function drawFinishBar(selector, data) {
    const root = $(selector);
    if (!root) return;
    const clean = data.filter(d => Number(d.count) > 0);
    if (!clean.length) { root.innerHTML = `<div class="empty" style="padding:32px;"><p>${t("common.no_data")}</p></div>`; return; }

    const colors = { "KO/TKO": "var(--primary-2)", "Submission": "var(--info)", "Decision": "var(--text-dim)" };
    const icons  = { "KO/TKO": "⚡", "Submission": "🔒", "Decision": "📋" };
    const total  = clean.reduce((s, d) => s + Number(d.count), 0);

    const segs = clean.map(d => {
        const pct  = (100 * Number(d.count) / total).toFixed(1);
        const col  = colors[d.name] || "var(--text-dim)";
        return `
          <div class="anl-finish-seg" style="flex:${pct}; background:${col};"
               title="${esc(d.name)} — ${pct}%">
            <span class="anl-finish-pct">${pct}%</span>
          </div>`;
    }).join("");

    const legend = clean.map(d => {
        const pct = (100 * Number(d.count) / total).toFixed(1);
        const col = colors[d.name] || "var(--text-dim)";
        const ico = icons[d.name] || "";
        return `
          <div class="anl-finish-leg-item">
            <span class="anl-finish-leg-dot" style="background:${col};"></span>
            <span class="anl-finish-leg-name">${ico} ${esc(d.name)}</span>
            <span class="anl-finish-leg-val">${fmtNumber(d.count)}</span>
            <span class="anl-finish-leg-pct" style="color:${col};">${pct}%</span>
          </div>`;
    }).join("");

    root.innerHTML = `
      <div class="anl-finish-wrap">
        <div class="anl-finish-bar-row">
          <div class="anl-finish-total">${fmtNumber(total)}<small>total wins</small></div>
          <div class="anl-finish-bar">${segs}</div>
        </div>
        <div class="anl-finish-legend">${legend}</div>
      </div>`;
}

// le profil d'âge — barres verticales avec le pic mis en valeur
function drawAgeChart(selector, data) {
    const root = $(selector);
    if (!root) return;
    // Ordre logique croissant
    const ORDER = ["< 25","25-29","30-34","35-39","40+"];
    const sorted = [...data].sort((a, b) => ORDER.indexOf(a.name) - ORDER.indexOf(b.name));
    if (!sorted.length) { root.innerHTML = `<div class="empty" style="padding:32px;"><p>${t("common.no_data")}</p></div>`; return; }

    const max  = Math.max(...sorted.map(d => Number(d.count)));
    const peak = sorted.reduce((p, c) => Number(c.count) > Number(p.count) ? c : p, sorted[0]);

    root.innerHTML = `
      <div class="anl-age-chart">
        ${sorted.map(d => {
            const h   = Math.round(100 * Number(d.count) / max);
            const isPeak = d.name === peak.name;
            return `
              <div class="anl-age-col">
                <div class="anl-age-val">${fmtNumber(d.count)}</div>
                <div class="anl-age-track">
                  <div class="anl-age-fill${isPeak ? " peak" : ""}" data-h="${h}" style="height:0%;"></div>
                </div>
                <div class="anl-age-lbl${isPeak ? " peak" : ""}">${esc(d.name)}</div>
              </div>`;
        }).join("")}
      </div>
      <div class="anl-age-caption">${t("analytics.age_peak_label")} <strong>${esc(peak.name)}</strong></div>`;

    requestAnimationFrame(() => {
        root.querySelectorAll(".anl-age-fill").forEach(el => { el.style.height = el.dataset.h + "%"; });
    });
}

// la stance — barres horizontales avec %
function drawStanceChart(selector, data) {
    const root = $(selector);
    if (!root) return;
    const clean = data.filter(d => d.name && Number(d.count) > 0).slice(0, 6);
    if (!clean.length) { root.innerHTML = `<div class="empty" style="padding:32px;"><p>${t("common.no_data")}</p></div>`; return; }

    const total = clean.reduce((s, d) => s + Number(d.count), 0);
    const max   = Number(clean[0].count);
    const COLORS = ["var(--success)","var(--info)","var(--gold)","var(--primary-2)","var(--text-muted)","var(--text-dim)"];

    root.innerHTML = `
      <div class="anl-stance-list">
        ${clean.map((d, i) => {
            const w   = Math.round(100 * Number(d.count) / max);
            const pct = ((100 * Number(d.count) / total)).toFixed(1);
            return `
              <div class="anl-stance-row">
                <div class="anl-stance-name">${esc(d.name)}</div>
                <div class="anl-stance-bar-wrap">
                  <div class="anl-stance-bar" data-w="${w}" style="width:0%; background:${COLORS[i]};"></div>
                </div>
                <div class="anl-stance-pct" style="color:${COLORS[i]};">${pct}%</div>
              </div>`;
        }).join("")}
      </div>`;

    requestAnimationFrame(() => {
        root.querySelectorAll(".anl-stance-bar").forEach(el => { el.style.width = el.dataset.w + "%"; });
    });
}

// les nationalités — barres horizontales avec drapeaux
function drawNationalityChart(selector, data) {
    const root = $(selector);
    if (!root) return;
    const clean = data.filter(d => d.name && Number(d.count) > 0).slice(0, 15);
    if (!clean.length) { root.innerHTML = `<div class="empty" style="padding:32px;"><p>${t("common.no_data")}</p></div>`; return; }

    const max = Number(clean[0].count);

    root.innerHTML = `
      <div class="anl-nat-list">
        ${clean.map(d => {
            const w    = Math.round(100 * Number(d.count) / max);
            const flag = nationalityToFlagHTML(d.name);
            const name = nationalityEnglish(d.name);
            return `
              <div class="anl-nat-row">
                <div class="anl-nat-flag">${flag || '<span class="anl-nat-flag-ph"></span>'}</div>
                <div class="anl-nat-name" title="${esc(name)}">${esc(name)}</div>
                <div class="anl-nat-bar-wrap">
                  <div class="anl-nat-bar" data-w="${w}" style="width:0%;"></div>
                </div>
                <div class="anl-nat-count">${fmtNumber(d.count)}</div>
              </div>`;
        }).join("")}
      </div>`;

    requestAnimationFrame(() => {
        root.querySelectorAll(".anl-nat-bar").forEach(el => { el.style.width = el.dataset.w + "%"; });
    });
}

// le finish rate par division — barres empilées (KO / Sub / Dec)
function drawFinishByDivision(selector, data) {
    const root = $(selector);
    if (!root) return;
    const men = data.filter(d => d.gender === "M");
    if (!men.length) { root.innerHTML = `<div class="empty" style="padding:32px;"><p>${t("common.no_data")}</p></div>`; return; }

    const rows = men.map(d => {
        const abbr = {
            "Flyweight":"FLY","Bantamweight":"BAN","Featherweight":"FEA",
            "Lightweight":"LW","Welterweight":"WW","Middleweight":"MW",
            "Light Heavyweight":"LHW","Heavyweight":"HW",
        }[d.division] || d.division.slice(0,3).toUpperCase();

        return `
          <div class="anl-fbd-row">
            <div class="anl-fbd-div" title="${esc(d.division)}">${esc(abbr)}</div>
            <div class="anl-fbd-bars">
              <div class="anl-fbd-seg anl-fbd-ko"  data-w="${d.ko_pct}"  style="width:0%;" title="KO/TKO ${d.ko_pct}%"></div>
              <div class="anl-fbd-seg anl-fbd-sub" data-w="${d.sub_pct}" style="width:0%;" title="Sub ${d.sub_pct}%"></div>
              <div class="anl-fbd-seg anl-fbd-dec" data-w="${d.dec_pct}" style="width:0%;" title="Dec ${d.dec_pct}%"></div>
            </div>
            <div class="anl-fbd-pcts">
              <span class="anl-fbd-p ko">${d.ko_pct}%</span>
              <span class="anl-fbd-p sub">${d.sub_pct}%</span>
              <span class="anl-fbd-p dec">${d.dec_pct}%</span>
            </div>
          </div>`;
    }).join("");

    root.innerHTML = `
      <div class="anl-fbd-legend">
        <span><i style="background:var(--primary-2);"></i>KO / TKO</span>
        <span><i style="background:var(--info);"></i>Submission</span>
        <span><i style="background:var(--bg-elev-3); border:1px solid var(--border);"></i>Decision</span>
      </div>
      <div class="anl-fbd-list">${rows}</div>
      <p class="anl-fbd-note">${t("analytics.finish_div_note")}</p>`;

    requestAnimationFrame(() => {
        root.querySelectorAll(".anl-fbd-seg").forEach(el => { el.style.width = el.dataset.w + "%"; });
    });
}

// le win rate par nationalité — barres horizontales avec drapeau + %
function drawNationWinRate(selector, data) {
    const root = $(selector);
    if (!root) return;
    if (!data.length) { root.innerHTML = `<div class="empty" style="padding:32px;"><p>${t("common.no_data")}</p></div>`; return; }

    const max = Math.max(...data.map(d => d.avg_win_rate));

    root.innerHTML = `
      <div class="anl-nwr-list">
        ${data.map((d, i) => {
            const flag = nationalityToFlagHTML(d.name);
            const name = nationalityEnglish(d.name);
            const w    = Math.round(100 * d.avg_win_rate / max);
            // Dégradé vert→rouge selon performance
            const hue  = Math.round(120 * d.avg_win_rate / 100);
            const col  = `hsl(${hue},70%,50%)`;
            return `
              <div class="anl-nwr-row">
                <div class="anl-nwr-rank">#${i+1}</div>
                <div class="anl-nwr-flag">${flag || '<span class="anl-nat-flag-ph"></span>'}</div>
                <div class="anl-nwr-name">${esc(name)}</div>
                <div class="anl-nwr-bar-wrap">
                  <div class="anl-nwr-bar" data-w="${w}" style="width:0%; background:${col};"></div>
                </div>
                <div class="anl-nwr-pct" style="color:${col};">${d.avg_win_rate}%</div>
                <div class="anl-nwr-n">${fmtNumber(d.fighters)} fighters</div>
              </div>`;
        }).join("")}
      </div>
      <p class="anl-fbd-note">${t("analytics.nation_perf_note")}</p>`;

    requestAnimationFrame(() => {
        root.querySelectorAll(".anl-nwr-bar").forEach(el => { el.style.width = el.dataset.w + "%"; });
    });
}

// la fiabilité / trust — jauges de couverture + teaser modèle
function drawReliability(selector, dq) {
    const root = $(selector);
    if (!root) return;
    const total = dq.total || 1;

    const metrics = [
        { label: t("analytics.rel_history"),    n: dq.has_history,     icon: "📊" },
        { label: t("analytics.rel_photo"),      n: dq.has_photo,       icon: "🖼️"  },
        { label: t("analytics.rel_dob"),        n: dq.has_dob,         icon: "📅" },
        { label: t("analytics.rel_nationality"),n: dq.has_nationality,  icon: "🌍" },
        { label: t("analytics.rel_elo"),        n: dq.has_elo,         icon: "📈" },
    ];

    const gauges = metrics.map(m => {
        const pct = Math.round(100 * (m.n || 0) / total);
        const col = pct >= 80 ? "var(--success)" : pct >= 50 ? "var(--gold)" : "var(--primary-2)";
        return `
          <div class="anl-rel-gauge">
            <div class="anl-rel-gauge-icon">${m.icon}</div>
            <div class="anl-rel-gauge-ring">
              <svg viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--bg-elev-3)" stroke-width="3.2"/>
                <circle cx="18" cy="18" r="15.9" fill="none" stroke="${col}" stroke-width="3.2"
                  stroke-dasharray="${pct} ${100 - pct}" stroke-dashoffset="25"
                  stroke-linecap="round" transform="rotate(-90 18 18)"
                  style="transition:stroke-dasharray 1s ease;"/>
                <text x="18" y="21" text-anchor="middle" font-family="Oswald,sans-serif"
                  font-size="9" font-weight="700" fill="${col}">${pct}%</text>
              </svg>
            </div>
            <div class="anl-rel-gauge-label">${esc(m.label)}</div>
            <div class="anl-rel-gauge-n">${fmtNumber(m.n || 0)}</div>
          </div>`;
    }).join("");

    // Teaser modele
    const teaserHtml = `
      <a href="methodology.html#track-record" class="anl-rel-teaser">
        <div class="anl-rel-teaser-left">
          <div class="anl-rel-teaser-eyebrow">${t("analytics.rel_model_eyebrow")}</div>
          <div class="anl-rel-teaser-title">${t("analytics.rel_model_title")}</div>
          <div class="anl-rel-teaser-sub">${t("analytics.rel_model_sub")}</div>
        </div>
        <div class="anl-rel-teaser-stat">
          <div class="anl-rel-teaser-big">58.98<span>%</span></div>
          <div class="anl-rel-teaser-lbl">${t("analytics.rel_model_lbl")}</div>
          <div class="anl-rel-teaser-cta">${t("analytics.rel_model_cta")} →</div>
        </div>
      </a>`;

    root.innerHTML = `
      <div class="anl-rel-wrap">
        <div class="anl-rel-gauges">${gauges}</div>
        <div class="anl-rel-facts">
          <div class="anl-rel-fact">
            <span class="anl-rel-fact-num">${fmtNumber(dq.avg_fights || 0)}</span>
            <span class="anl-rel-fact-lbl">${t("analytics.rel_avg_fights")}</span>
          </div>
          <div class="anl-rel-fact">
            <span class="anl-rel-fact-num">${fmtNumber(dq.country_count || 0)}</span>
            <span class="anl-rel-fact-lbl">${t("analytics.rel_countries")}</span>
          </div>
          <div class="anl-rel-fact">
            <span class="anl-rel-fact-num">${fmtNumber(dq.division_count || 0)}</span>
            <span class="anl-rel-fact-lbl">${t("analytics.rel_divisions")}</span>
          </div>
          <div class="anl-rel-fact">
            <span class="anl-rel-fact-num">${fmtNumber(dq.max_fights || 0)}</span>
            <span class="anl-rel-fact-lbl">${t("analytics.rel_max_fights")}</span>
          </div>
        </div>
      </div>
      ${teaserHtml}`;
}
