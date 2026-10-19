// MM.AI — event.js
// Page detail event — layout inspire Tapology / UFC-FR
// Affiche grand poster en haut · titre centre · sections une fois ·
// abrev poids · favori a gauche · symetrie miroir des bouts

async function renderEventPage() {
    const root = document.getElementById("event-root");
    const id   = getQueryParam("id");
    const slug = getQueryParam("slug");

    if (!id && !slug) {
        root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="error-box">No event specified.</div></div>`;
        return;
    }

    try {
        const ev = id ? await api.event(id) : await api.eventBySlug(slug);
        document.title = `${ev.name} — MM.AI`;
        root.innerHTML = renderEventDetail(ev);
        setupNavSearch();
    } catch (e) {
        root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="error-box">Error: ${esc(e.message)}</div></div>`;
    }
}

// Weight class helpers
// Utilise les helpers globaux d'app.js (formatWeightClassShort/Long, parseWC)
// pour garantir un libelle COHERENT partout (event page, fighter page, etc).
const _LBS_ABBREV = {
    105:"AW", 108:"AW", 112:"SW", 115:"SW", 125:"FLW",
    135:"BW", 145:"FTW", 155:"LW", 165:"SLW", 170:"WW",
    175:"SWW", 185:"MW", 205:"LHW", 225:"CW", 265:"HW",
};

// Detecte le genre depuis le label brut. Wrapper de parseWC pour rester compatible
// avec le code event.js existant.
function detectGender(wc) {
    return parseWC(wc).gender;
}

// Abbrev courte pour le centre du bout (ex: "BW", "BW W" si feminin)
function wcAbbrev(wc, lbs) {
    if (wc) {
        const short = formatWeightClassShort(wc);
        if (short) return short;
        const m = String(wc).match(/\b(\d{3})\b/);
        if (m) return _LBS_ABBREV[parseInt(m[1])] || (parseInt(m[1]) + "#");
    }
    if (lbs) return _LBS_ABBREV[lbs] || (lbs + "#");
    return "?";
}

// Label complet pour la ligne "Championship" — utilise le helper global
// Ex : "Bantamweight" (men) · "Bantamweight (W)" (women)
function wcLabel(wc) {
    return formatWeightClassLong(wc) || wc || "";
}

// les rounds depuis le "3x3" / "3x5" stocké, ou déduit sinon
function roundsDisplay(rounds, isTitleFight, boutLabel) {
    if (rounds) {
        const m = rounds.match(/(\d{1,2})\s*[xX×]\s*(\d{1,2})/);
        if (m) return `${m[1]} × ${m[2]}`;
    }
    if (isTitleFight || boutLabel === "MAIN EVENT") return "5 × 5";
    return "3 × 5";
}

// Favori a gauche : champion > rang plus bas (=meilleur), sinon Tapology
function getOrderedFighters(bout) {
    const f1 = bout.fighter1 || {}, f2 = bout.fighter2 || {};
    if (f2.is_champion && !f1.is_champion) return { left: f2, right: f1, swapped: true };
    if (f1.is_champion)                    return { left: f1, right: f2, swapped: false };
    const r1 = f1.rank ? parseInt(f1.rank) : 9999;
    const r2 = f2.rank ? parseInt(f2.rank) : 9999;
    if (r2 < r1) return { left: f2, right: f1, swapped: true };
    return { left: f1, right: f2, swapped: false };
}

// Flag (copie depuis app.js)
const _EV_FLAGS = {
    "united states":"us","usa":"us","american":"us","brazil":"br","brazilian":"br",
    "russia":"ru","russian":"ru","poland":"pl","polish":"pl","mexico":"mx","mexican":"mx",
    "canada":"ca","canadian":"ca","united kingdom":"gb","uk":"gb","england":"gb-eng",
    "british":"gb","scotland":"gb-sct","scottish":"gb-sct","wales":"gb-wls","welsh":"gb-wls",
    "ireland":"ie","irish":"ie","france":"fr","french":"fr",
    "germany":"de","german":"de","japan":"jp","japanese":"jp","south korea":"kr",
    "korean":"kr","china":"cn","chinese":"cn","australia":"au","australian":"au",
    "new zealand":"nz","nigeria":"ng","nigerian":"ng","cameroon":"cm","ghana":"gh",
    "kyrgyzstan":"kg","kyrgyz":"kg","kazakhstan":"kz","uzbekistan":"uz","georgia":"ge",
    "ukraine":"ua","ukrainian":"ua","sweden":"se","swedish":"se","norway":"no","norwegian":"no",
    "netherlands":"nl","dutch":"nl","belgium":"be","belgian":"be","italy":"it","italian":"it",
    "spain":"es","spanish":"es","portugal":"pt","portuguese":"pt","czech republic":"cz","czechia":"cz","turkey":"tr","turkish":"tr",
    "iran":"ir","iranian":"ir","iraq":"iq","egypt":"eg","egyptian":"eg","morocco":"ma","moroccan":"ma","thailand":"th","thai":"th",
    "philippines":"ph","filipino":"ph","indonesia":"id","peru":"pe","peruvian":"pe","colombia":"co","colombian":"co","argentina":"ar","argentine":"ar","argentinian":"ar",
    // ajouts : pays manquants frequents en MMA
    "palestine":"ps","palestinian":"ps","israel":"il","israeli":"il","lebanon":"lb","jordan":"jo",
    "saudi arabia":"sa","united arab emirates":"ae","uae":"ae","syria":"sy","tunisia":"tn","algeria":"dz","algerian":"dz",
    "chile":"cl","chilean":"cl","ecuador":"ec","venezuela":"ve","venezuelan":"ve","uruguay":"uy","bolivia":"bo","paraguay":"py","panama":"pa","cuba":"cu","cuban":"cu","dominican republic":"do",
    "south africa":"za","kenya":"ke","angola":"ao","congo":"cd","senegal":"sn","ivory coast":"ci",
    "armenia":"am","armenian":"am","azerbaijan":"az","tajikistan":"tj","mongolia":"mn","mongolian":"mn","india":"in","indian":"in","pakistan":"pk","bangladesh":"bd","afghanistan":"af","afghan":"af",
    "vietnam":"vn","myanmar":"mm","malaysia":"my","singapore":"sg","cambodia":"kh","taiwan":"tw",
    "finland":"fi","finnish":"fi","denmark":"dk","danish":"dk","iceland":"is","austria":"at","switzerland":"ch","swiss":"ch","greece":"gr","greek":"gr",
    "romania":"ro","romanian":"ro","bulgaria":"bg","hungary":"hu","hungarian":"hu","croatia":"hr","croatian":"hr","serbia":"rs","serbian":"rs","slovakia":"sk","slovenia":"si",
    "lithuania":"lt","lithuanian":"lt","latvia":"lv","estonia":"ee","belarus":"by","moldova":"md",
    "dagestan":"ru","chechnya":"ru","north macedonia":"mk","montenegro":"me","bosnia":"ba","bosnia and herzegovina":"ba","albania":"al","albanian":"al",
    "ph":"ph","th":"th","jp":"jp","ru":"ru","us":"us","br":"br","cn":"cn","ps":"ps",
};
function evFlag(nat) {
    if (!nat) return "";
    const code = _EV_FLAGS[nat.toLowerCase().trim()];
    return code ? `<span class="fi fi-${code}"></span>` : "";
}

// Rendu principal
function renderEventDetail(ev) {
    const dateStr = ev.date ? (() => {
        try {
            const [y, m, d] = ev.date.split("-");
            const days   = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
            const months = ["January","February","March","April","May","June",
                            "July","August","September","October","November","December"];
            const dt = new Date(+y, +m - 1, +d);
            return `${days[dt.getDay()]} ${months[+m-1]} ${parseInt(d)}, ${y}`;
        } catch { return ev.date; }
    })() : "";

    // effective_status = "upcoming" si event a lieu aujourd'hui/demain/...
    // ou hier (chevauchement 1 jour). Sinon "completed".
    const effStatus = ev.effective_status || ev.status || "completed";
    const isUpcoming = effStatus === "upcoming";
    const statusLabel = isUpcoming ? t("events.status_upcoming") : effStatus === "cancelled" ? t("events.status_cancelled") : t("events.status_past");
    const statusClass = isUpcoming ? "upcoming" : effStatus === "cancelled" ? "cancelled" : "completed";

    const locationParts = [ev.venue, ev.city, ev.country].filter(Boolean);
    const locationStr   = locationParts.join(", ");
    const totalBouts    = (ev.card_sections || []).reduce((s, sec) => s + sec.bouts.length, 0);

    // classe de promotion (UFC -> nom coloré + accents spécifiques)
    const promoRaw   = (ev.promotion || "").toUpperCase();
    const promoClass = promoRaw.includes("UFC")     ? "promo-ufc"
                     : promoRaw.includes("PFL")     ? "promo-pfl"
                     : promoRaw.includes("BELLATOR")? "promo-bellator"
                     : promoRaw.includes("ONE")     ? "promo-one"
                     : "";

    // le hero : titre + meta centré, grosse image juste en dessous
    const headerHtml = `
        <div class="ev-header">
            <div class="ev-promo-badge">${esc(ev.promotion || "MMA")}</div>
            <h1 class="ev-main-title">${esc(ev.name)}</h1>
            <div class="ev-hero-meta">
                <span class="ev-status-pill ${statusClass}">${statusLabel}</span>
                ${dateStr ? `<span class="ev-hero-date">${esc(dateStr)}</span>` : ""}
                ${locationStr ? `<span class="ev-hero-loc">${esc(locationStr)}</span>` : ""}
            </div>
        </div>
    `;

    // le poster : grande image style Tapology, juste sous le header.
    // Si pas de poster_url (events historiques importes) -> poster GENERE en CSS
    // (carte UFC stylisee avec nom + date) au lieu d'un trou blanc.
    const dParts = (ev.date || "").split("-");
    const yr = dParts[0] || "";
    const imgHtml = ev.poster_url ? `
        <img src="${esc(ev.poster_url)}" alt="${esc(ev.name)} poster"
             class="ev-poster-img" loading="eager"
             onerror="this.parentElement.classList.add('ev-poster-fallback');this.remove();">
    ` : "";
    // Le nom est toujours present mais cache par CSS ; il n'apparait que si le
    // cadre est en mode .ev-poster-fallback (pas de poster ou image cassee).
    const posterInner = imgHtml + `<div class="ev-poster-fallback-name">${esc(ev.name || "")}</div>`;
    const posterHtml = `
        <div class="ev-poster-block">
            <div class="ev-poster-frame ${ev.poster_url ? "" : "ev-poster-fallback"}"
                 data-promo="${esc(ev.promotion || "UFC")}"
                 data-name="${esc(ev.name || "")}"
                 data-year="${esc(yr)}">
                ${posterInner}
            </div>
        </div>
    `;

    const cardHtml = (ev.card_sections || []).map(sec => renderSection(sec)).join("");

    const awardsHtml = (ev.awards && ev.awards.length > 0) ? `
        <div class="ev-awards">
            <div class="ev-section-divider">${t("events.awards")}</div>
            <div class="ev-awards-list">
                ${ev.awards.map(a => `
                    <div class="ev-award-row">
                        <span class="ev-award-label">${esc(a.award)}</span>
                        <span class="ev-award-val">${esc(a.recipient)}</span>
                    </div>
                `).join("")}
            </div>
        </div>
    ` : "";

    // Infos event en bas
    const metaHtml = (ev.venue || ev.city || totalBouts) ? `
        <div class="ev-bottom-meta">
            <div class="ev-meta-grid">
                ${ev.venue    ? `<div class="ev-meta-row"><span class="ev-meta-k">${t("events.venue")}</span><span class="ev-meta-v">${esc(ev.venue)}</span></div>` : ""}
                ${ev.city || ev.country ? `<div class="ev-meta-row"><span class="ev-meta-k">${t("events.location_label")}</span><span class="ev-meta-v">${esc([ev.city, ev.country].filter(Boolean).join(", "))}</span></div>` : ""}
                ${totalBouts  ? `<div class="ev-meta-row"><span class="ev-meta-k">${t("events.total_bouts")}</span><span class="ev-meta-v">${totalBouts}</span></div>` : ""}
            </div>
        </div>
    ` : "";

    // fond du hero : le poster lui-même, flouté + assombri (effet "ambiance event")
    const backdropHtml = ev.poster_url
        ? `<div class="ev-hero-backdrop" style="background-image:url('${esc(ev.poster_url)}')"></div>`
        : "";

    return `
        <div class="ev-page ${promoClass}">
            <div class="container ev-back-row">
                <a href="events.html" class="back-btn" onclick="if(history.length>1&&document.referrer&&document.referrer.startsWith(location.origin)){event.preventDefault();history.back();}">${t("events.back")}</a>
            </div>

            <div class="ev-hero-wrap">
                ${backdropHtml}
                <div class="container ev-hero-fg">
                    ${headerHtml}
                    ${posterHtml}
                </div>
            </div>

            <div class="container">
                <div class="ev-card-header">
                    <span class="ev-card-label-big">${t("events.fight_card")}</span>
                    <button class="ev-predict-btn" id="ev-predict-btn" onclick="predictFullCard(this)">
                        <span class="ev-predict-btn-spark">⚡</span>
                        <span class="ev-predict-btn-txt">${t("events.predict_card_btn")}</span>
                    </button>
                </div>
                <div id="ev-predict-summary"></div>
                <div class="ev-card-body">
                    ${cardHtml || `<div class="empty"><p>${t("events.no_fights")}</p></div>`}
                </div>
                ${awardsHtml}
                ${metaHtml}
            </div>
        </div>
    `;
}

// Section (Main Card / Prelims / …)
function renderSection(sec) {
    const bouts = sec.bouts || [];
    if (!bouts.length) return "";

    const sName = (sec.name || "Main Card");
    const boutRows = bouts.map((b, idx) => renderBout(b, sName, idx)).join("");

    const divider = `<div class="ev-section-divider">${esc(sName.toUpperCase())}</div>`;
    return `${divider}${boutRows}`;
}

// Un bout
function renderBout(b, sectionName, idxInSection) {
    const { left, right } = getOrderedFighters(b);

    const sLow = (sectionName || "").toLowerCase();
    const isMainCard   = !sLow.includes("prelim");
    const isCancelled  = b.status === "cancelled";
    const isUpcoming   = b.status === "upcoming";
    const isCompleted  = !isUpcoming && !isCancelled;

    let labelHtml = "";
    if (isMainCard) {
        if (idxInSection === 0) {
            labelHtml = `<div class="ev-bout-label lbl-main-event">MAIN EVENT</div>`;
        } else if (idxInSection === 1) {
            labelHtml = `<div class="ev-bout-label lbl-co-main">CO-MAIN</div>`;
        }
    }

    // Détection du genre du bout : via weight_class label OU via gender des fighters
    const isFemaleWC = (wc_raw) => detectGender(wc_raw) === "W";
    const isFemale = (f) => f.gender === "F" || isFemaleWC(f.weight_class || "");
    const boutIsFemale = isFemaleWC(b.weight_class || "")
        || (isFemale(left) && isFemale(right));

    // Normalise la weight_class du bout en ajoutant "Women's" si besoin
    function ensureWomenPrefix(wc_str) {
        if (!wc_str) return wc_str;
        if (boutIsFemale && !/^Women['']?s?\s/i.test(wc_str)) {
            return "Women's " + wc_str.replace(/^Women['']?s?\s*/i, "");
        }
        return wc_str;
    }

    const abbrevWc = ensureWomenPrefix(b.weight_class || "");
    const wc     = wcAbbrev(abbrevWc, b.weight_lbs);
    const rounds = roundsDisplay(b.rounds, b.is_title_fight, (isMainCard && idxInSection === 0) ? "MAIN EVENT" : "");

    // Bouts annulés : pas affichés du tout
    if (isCancelled) return "";

    const isNC = (b.method || "").toUpperCase() === "NC";

    // NC = No Contest : personne ne gagne ni ne perd
    const leftWins  = isCompleted && !isNC && b.winner_name &&
                      b.winner_name.toLowerCase() === (left.name  || "").toLowerCase();
    const rightWins = isCompleted && !isNC && b.winner_name &&
                      b.winner_name.toLowerCase() === (right.name || "").toLowerCase();

    // Titre du bout : "Interim Heavyweight Championship" ou "Women's Bantamweight Championship"
    const titleWc = ensureWomenPrefix(b.weight_class || "");
    const interimPrefix = b.is_interim_title ? "Interim " : "";
    const titleLineClass = b.is_interim_title ? "ev-title-line interim" : "ev-title-line";
    const titleLine = b.is_title_fight && titleWc
        ? `<div class="${titleLineClass}">${esc(interimPrefix + wcLabel(titleWc))} ${t("events.championship")}</div>`
        : "";

    const methodHtml = (() => {
        if (isUpcoming)  return "";
        if (!b.method)   return "";
        let s = b.method;
        if (b.method_detail) s += ` · ${b.method_detail}`;
        if (b.round_num)     s += ` R${b.round_num}`;
        if (b.time_str)      s += ` ${b.time_str}`;
        return `<div class="ev-bout-method-text${isNC ? " ev-bout-nc" : ""}">${esc(s)}</div>`;
    })();

    return `
        <div class="ev-bout ${isCancelled ? "cancelled" : ""}" data-f1id="${left.id || ''}" data-f2id="${right.id || ''}">
            ${titleLine}
            <div class="ev-bout-row">
                ${renderFighterSide(left,  "left",  isCompleted && leftWins,  isCompleted && rightWins)}
                <div class="ev-bout-center">
                    ${labelHtml}
                    <div class="ev-bout-wc">${wc}</div>
                    <div class="ev-bout-rounds">${rounds}</div>
                </div>
                ${renderFighterSide(right, "right", isCompleted && rightWins, isCompleted && leftWins)}
            </div>
            ${methodHtml}
            <div class="ev-predict-slot"></div>
        </div>
    `;
}

// Prédit toute la carte (endpoint matchmaking — meilleurs % + décisions) et injecte les résultats inline.
window.predictFullCard = async function(btn) {
    btn = btn || document.getElementById("ev-predict-btn");
    if (!btn || btn.dataset.loading) return;
    btn.dataset.loading = "1";
    btn.disabled = true;
    const btnTxt = btn.querySelector(".ev-predict-btn-txt") || btn;
    btnTxt.textContent = t("events.predict_loading");

    const bouts = [...document.querySelectorAll(".ev-bout:not(.cancelled)[data-f1id]")];
    let linked = 0;

    const tasks = bouts.map(async (el) => {
        const f1id = el.dataset.f1id;
        const f2id = el.dataset.f2id;
        const slot = el.querySelector(".ev-predict-slot");
        if (!slot) return;

        if (!f1id || !f2id) {
            slot.innerHTML = `<div class="ev-pred-card ev-pred-unlinked"><span class="ev-pred-pick-lbl">${t("events.predict_picks")}</span><span>${t("events.predict_not_linked")}</span></div>`;
            slot.classList.add("active");
            return;
        }

        linked++;
        slot.innerHTML = `<div class="ev-pred-card ev-pred-loading"><span class="ev-pred-loading-dots">···</span></div>`;
        slot.classList.add("active");

        try {
            const res = await api.matchmaking(Number(f1id), Number(f2id));
            const winnerId     = res.predicted_winner_id;
            const winnerIsLeft = winnerId === Number(f1id);
            const winnerName   = res.predicted_winner_name || (winnerIsLeft ? res.fighter1.name : res.fighter2.name);
            const winnerProb   = winnerIsLeft ? res.fighter1.win_prob : res.fighter2.win_prob;
            const conf         = Math.round(Number(winnerProb) || 0);
            const meth         = res.method_hint || "";
            const confCls      = conf >= 65 ? "high" : conf >= 55 ? "mid" : "low";

            // Highlight predicted winner / dim predicted loser on the bout card
            const leftSide  = el.querySelector(".ev-f-side.left");
            const rightSide = el.querySelector(".ev-f-side.right");
            if (winnerIsLeft) { leftSide?.classList.add("pred-winner"); rightSide?.classList.add("pred-loser"); }
            else              { rightSide?.classList.add("pred-winner"); leftSide?.classList.add("pred-loser"); }
            el.classList.add("predicted");

            slot.innerHTML = `
                <div class="ev-pred-card">
                    <div class="ev-pred-top">
                        <span class="ev-pred-pick-lbl">${t("events.predict_picks")}</span>
                        <a href="fighter.html?id=${winnerId}" class="ev-pred-winner-name">${esc(winnerName)}</a>
                        ${meth ? `<span class="ev-pred-meth ev-pred-meth-${confCls}">${esc(meth)}</span>` : ""}
                        <span class="ev-pred-pct ev-pred-pct-${confCls}">${conf}%</span>
                    </div>
                    <div class="ev-pred-bar-wrap">
                        <div class="ev-pred-bar-fill ev-pred-bar-${confCls}" style="width:0%" data-target="${conf}%"></div>
                    </div>
                    <div class="ev-pred-footer">
                        <a href="matchmaking.html?id1=${f1id}&id2=${f2id}" class="ev-pred-link">${t("events.predict_analysis_link")} →</a>
                    </div>
                </div>`;

            // Animate the bar after the DOM paints width:0
            requestAnimationFrame(() => requestAnimationFrame(() => {
                const fill = slot.querySelector(".ev-pred-bar-fill");
                if (fill) fill.style.width = fill.dataset.target;
            }));
        } catch {
            slot.innerHTML = `<div class="ev-pred-card ev-pred-unlinked"><span>${t("events.predict_not_linked")}</span></div>`;
        }
    });

    await Promise.all(tasks);

    const summary = document.getElementById("ev-predict-summary");
    if (summary && linked > 0) {
        summary.innerHTML = `<div class="ev-pred-summary"><span class="ev-pred-sum-ico">⚡</span><span class="ev-pred-sum-txt">MM.AI — <strong>${linked}</strong> ${t("events.predict_summary_done")}</span></div>`;
    }

    btnTxt.textContent = t("events.predict_done").replace("{n}", linked).replace("{total}", bouts.length);
    btn.disabled = false;
    delete btn.dataset.loading;
};

// Cote fighter (left ou right) — SYMETRIE MIROIR
// côté gauche : [badge V/D] [infos: nom+record+rang+drapeau] [photo]
// côté droit (miroir) : [photo] [infos: nom+record+rang+drapeau] [badge V/D]
function renderFighterSide(f, side, isWinner, isLoser) {
    const photo = f.photo
        ? `<img src="${esc(f.photo)}" alt="${esc(f.name)}" loading="lazy" class="ev-f-photo" onerror="this.outerHTML='<div class=&quot;ev-f-photo ev-f-initials&quot;>${esc(initials(f.name || "?"))}</div>'">`
        : `<div class="ev-f-photo ev-f-initials">${esc(initials(f.name || "?"))}</div>`;

    const hasRecord = f.record && (f.record[0] || f.record[1]);
    const record = hasRecord
        ? `<span class="ev-f-record">${f.record[0]}-${f.record[1]}${f.record[2] ? `-${f.record[2]}` : ""}</span>`
        : "";

    const rankHtml = f.is_champion
        ? `<span class="ev-f-rank champ" title="Champion">C</span>`
        : f.rank
        ? `<span class="ev-f-rank">#${f.rank}</span>`
        : "";

    const resultHtml = isWinner
        ? `<div class="ev-f-result win">W</div>`
        : isLoser
        ? `<div class="ev-f-result loss">L</div>`
        : `<div class="ev-f-result placeholder"></div>`;

    const nameHtml = f.id
        ? `<a class="ev-f-name" href="fighter.html?id=${f.id}" data-hc-zone>${esc(f.name || "TBA")}</a>`
        : `<span class="ev-f-name no-link" data-hc-zone>${esc(f.name || "TBA")}</span>`;

    const flag = evFlag(f.nationality);
    const subRow = (flag || record || rankHtml)
        ? `<div class="ev-f-sub">${flag ? `<span class="ev-f-flag">${flag}</span>` : ""}${record}${rankHtml}</div>`
        : "";

    const infoBlock = `
        <div class="ev-f-info">
            ${nameHtml}
            ${subRow}
        </div>
    `;

    const hcAttrs = f.id
        ? `data-fighter-id="${f.id}" data-fighter-name="${esc(f.name || "")}" data-hc-restricted data-hc-side="${side}"`
        : "";

    // symétrie miroir
    // Le combattant de gauche regarde vers la droite (centre du bout).
    // Sa photo est donc a DROITE de sa case, et son badge W/L tout a GAUCHE.
    // Inversement pour le combattant de droite.
    if (side === "left") {
        return `
            <div class="ev-f-side left ${isWinner?"winner":""} ${isLoser?"loser":""}" ${hcAttrs}>
                ${resultHtml}
                ${infoBlock}
                <div class="ev-f-photo-wrap" data-hc-zone>${photo}</div>
            </div>
        `;
    } else {
        return `
            <div class="ev-f-side right ${isWinner?"winner":""} ${isLoser?"loser":""}" ${hcAttrs}>
                <div class="ev-f-photo-wrap" data-hc-zone>${photo}</div>
                ${infoBlock}
                ${resultHtml}
            </div>
        `;
    }
}
