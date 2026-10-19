// MM.AI - Page Methodology : section "Track record" (validation walk-forward)
// Consomme /api/backtest (rapport pre-calcule par database/run_backtest.py).
// Graphes SVG/CSS maison, aucune dependance. esc()/fmtNumber()/t() viennent
// de app.js / i18n.js (globaux).

async function renderTrackRecord() {
    const body = document.getElementById("tr-body");
    if (!body) return;

    let data;
    try {
        data = await api.backtest();
    } catch (e) {
        body.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
        return;
    }

    if (!data || data.available === false) {
        body.innerHTML = `
            <div class="tr-empty">
                <div class="tr-empty-icon">&#9203;</div>
                <p>${t("track.not_run")}</p>
                <code class="tr-cmd">py database/run_backtest.py</code>
            </div>`;
        return;
    }

    const ov = data.overall || {};
    if (!ov.n) {
        body.innerHTML = `<div class="tr-empty"><p>${t("track.no_data")}</p></div>`;
        return;
    }

    body.innerHTML = `
        ${trMetrics(ov, data.coverage || {})}
        ${trCalibration(data.calibration || [], ov)}
        <div class="tr-grid-2">
            ${trBreakdown(t("track.by_method"), t("track.by_method_sub"), data.by_method || [], "method")}
            ${trBreakdown(t("track.by_experience"), t("track.by_experience_sub"), data.by_experience || [], "bucket")}
        </div>
        ${trYearTrend(data.by_year || [])}
        ${trFootnote(data)}
    `;
}

// Cartes de metriques principales
function trMetrics(ov, cov) {
    const cards = [
        {
            big: ov.accuracy != null ? ov.accuracy + "%" : "--",
            label: t("track.m_accuracy"),
            hint: t("track.m_accuracy_hint"),
            tone: "accent",
        },
        {
            big: ov.lift_vs_baseline != null ? (ov.lift_vs_baseline >= 0 ? "+" : "") + ov.lift_vs_baseline + " pts" : "--",
            label: t("track.m_lift"),
            hint: t("track.m_lift_hint").replace("{base}", ov.baseline_record_accuracy != null ? ov.baseline_record_accuracy + "%" : "?"),
            tone: ov.lift_vs_baseline >= 0 ? "good" : "bad",
        },
        {
            big: ov.brier_skill != null ? ov.brier_skill : "--",
            label: t("track.m_brierskill"),
            hint: t("track.m_brierskill_hint"),
        },
        {
            big: ov.log_loss != null ? ov.log_loss : "--",
            label: t("track.m_logloss"),
            hint: t("track.m_logloss_hint"),
        },
        {
            big: ov.ece != null ? (ov.ece * 100).toFixed(1) + "%" : "--",
            label: t("track.m_ece"),
            hint: t("track.m_ece_hint"),
        },
        {
            big: fmtNumber(ov.n),
            label: t("track.m_n"),
            hint: t("track.m_n_hint"),
        },
    ];
    return `
        <div class="tr-metrics">
            ${cards.map(c => `
                <div class="tr-metric ${c.tone || ""}" title="${esc(c.hint)}">
                    <div class="tr-metric-big">${esc(c.big)}</div>
                    <div class="tr-metric-label">${esc(c.label)}</div>
                    <div class="tr-metric-hint">${esc(c.hint)}</div>
                </div>`).join("")}
        </div>`;
}

// Courbe de calibration (predit vs observe)
function trCalibration(bins, ov) {
    const active = bins.filter(b => b.n > 0);
    if (!active.length) return "";

    const rows = active.map(b => {
        // Hauteurs : on mappe la plage 50–100% sur 0–100% de la barre (zone utile).
        const scale = (v) => Math.max(2, Math.min(100, ((v - 50) / 50) * 100));
        const hp = scale(b.predicted);
        const ho = scale(b.observed);
        const gap = Math.abs(b.observed - b.predicted);
        const gapCls = gap <= 5 ? "spot-on" : gap <= 12 ? "ok" : "off";
        return `
            <div class="cal-col" title="${t("track.cal_tip")
                .replace("{pred}", b.predicted + "%")
                .replace("{obs}", b.observed + "%")
                .replace("{n}", b.n)}">
                <div class="cal-bars">
                    <div class="cal-bar predicted" style="height:0%" data-h="${hp}">
                        <span class="cal-val">${Math.round(b.predicted)}</span>
                    </div>
                    <div class="cal-bar observed ${gapCls}" style="height:0%" data-h="${ho}">
                        <span class="cal-val">${Math.round(b.observed)}</span>
                    </div>
                </div>
                <div class="cal-label">${esc(b.label)}</div>
                <div class="cal-n">n=${fmtNumber(b.n)}</div>
            </div>`;
    }).join("");

    const eceTxt = ov.ece != null ? (ov.ece * 100).toFixed(1) + "%" : "?";

    const html = `
        <div class="tr-card cal-card">
            <div class="tr-card-head">
                <h4>${t("track.cal_title")}</h4>
                <div class="cal-legend">
                    <span><i class="dot predicted"></i>${t("track.cal_predicted")}</span>
                    <span><i class="dot observed"></i>${t("track.cal_observed")}</span>
                </div>
            </div>
            <p class="tr-card-sub">${t("track.cal_sub").replace("{ece}", eceTxt)}</p>
            <div class="cal-chart">${rows}</div>
        </div>`;

    // anime les hauteurs apres insertion
    requestAnimationFrame(() => {
        document.querySelectorAll(".cal-bar").forEach(el => { el.style.height = el.dataset.h + "%"; });
    });
    return html;
}

// Tableau de ventilation (par methode / par experience)
function trBreakdown(title, sub, rows, keyName) {
    if (!rows.length) return "";
    const maxN = Math.max(...rows.map(r => r.n || 0)) || 1;
    const body = rows.map(r => {
        const acc = r.accuracy != null ? r.accuracy + "%" : "--";
        const w = Math.round(100 * (r.n || 0) / maxN);
        return `
            <div class="tr-row">
                <div class="tr-row-key">${esc(r[keyName])}</div>
                <div class="tr-row-bar"><div class="tr-row-fill" style="width:${w}%"></div></div>
                <div class="tr-row-n">${fmtNumber(r.n)}</div>
                <div class="tr-row-acc">${acc}</div>
            </div>`;
    }).join("");
    return `
        <div class="tr-card">
            <div class="tr-card-head"><h4>${esc(title)}</h4></div>
            <p class="tr-card-sub">${esc(sub)}</p>
            <div class="tr-rows">
                <div class="tr-row tr-row-head">
                    <div class="tr-row-key"></div>
                    <div class="tr-row-bar"></div>
                    <div class="tr-row-n">${t("track.col_fights")}</div>
                    <div class="tr-row-acc">${t("track.col_acc")}</div>
                </div>
                ${body}
            </div>
        </div>`;
}

// Mini-tendance accuracy par annee (sparkline SVG)
function trYearTrend(years) {
    const pts = years.filter(y => y.accuracy != null && y.n >= 10);
    if (pts.length < 3) return "";
    const W = 720, H = 140, pad = 28;
    const xs = pts.map((_, i) => pad + i * (W - 2 * pad) / (pts.length - 1));
    const ys = pts.map(p => H - pad - ((p.accuracy - 40) / 60) * (H - 2 * pad)); // echelle 40–100%
    const path = xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
    const dots = xs.map((x, i) =>
        `<circle cx="${x.toFixed(1)}" cy="${ys[i].toFixed(1)}" r="3.5" fill="var(--primary-2)">
            <title>${pts[i].year}: ${pts[i].accuracy}% (n=${pts[i].n})</title>
         </circle>`).join("");
    const labels = pts.map((p, i) =>
        (i === 0 || i === pts.length - 1 || i === Math.floor(pts.length / 2))
            ? `<text x="${xs[i].toFixed(1)}" y="${H - 6}" text-anchor="middle" class="yr-lab">${p.year}</text>` : ""
    ).join("");
    return `
        <div class="tr-card">
            <div class="tr-card-head"><h4>${t("track.year_title")}</h4></div>
            <p class="tr-card-sub">${t("track.year_sub")}</p>
            <svg viewBox="0 0 ${W} ${H}" class="yr-svg" preserveAspectRatio="none">
                <line x1="${pad}" y1="${(H - pad - ((50 - 40) / 60) * (H - 2 * pad)).toFixed(1)}"
                      x2="${W - pad}" y2="${(H - pad - ((50 - 40) / 60) * (H - 2 * pad)).toFixed(1)}"
                      class="yr-base" stroke-dasharray="4 4"/>
                <path d="${path}" fill="none" stroke="var(--primary-2)" stroke-width="2.5"/>
                ${dots}${labels}
            </svg>
            <div class="yr-foot"><span>${t("track.year_baseline")}</span></div>
        </div>`;
}

// Note de bas : couverture + methode + date
function trFootnote(data) {
    const cov = data.coverage || {};
    const gen = data.generated_at ? String(data.generated_at).slice(0, 10) : null;
    return `
        <div class="tr-foot">
            <div class="tr-foot-method">
                <strong>${t("track.method_label")}</strong>
                ${t("track.method_text")}
            </div>
            <div class="tr-foot-cov">
                ${t("track.cov_text")
                    .replace("{fighters}", fmtNumber(cov.fighters_tracked || 0))
                    .replace("{fights}", fmtNumber(cov.fights_in_metrics || 0))
                    .replace("{total}", fmtNumber(cov.fights_backtested_total || 0))}
                ${gen ? ` · ${t("track.generated")} ${esc(gen)}` : ""}
            </div>
        </div>`;
}
