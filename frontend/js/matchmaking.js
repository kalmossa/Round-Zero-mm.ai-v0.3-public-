// MM.AI - Page Matchmaking

const mmPicks = { 1: null, 2: null };

async function renderMatchmakingPage() {
    setupNavSearch();

    $$(".mm-search").forEach(input => {
        const side = input.dataset.side;
        input.addEventListener("input", debounce(async () => {
            const q = input.value.trim();
            const box = $(`.mm-results[data-side="${side}"]`);
            if (q.length < 2) { box.innerHTML = ""; box.classList.remove("open"); return; }
            try {
                const data = await api.fighters({ search: q, limit: 8 });
                if (!data.fighters.length) {
                    box.innerHTML = `<div class="vs-result-empty">${t("common.no_results")}</div>`;
                    box.classList.add("open");
                    return;
                }
                box.innerHTML = data.fighters.map(f => `
                    <div class="vs-result" data-id="${f.id}">
                        ${avatar(f)}
                        <div class="info">
                            <div class="name">${esc(f.name)}</div>
                            <div class="sub">${esc(f.weight_class_current || "--")} • ${f.record_total_wins || 0}-${f.record_total_losses || 0}</div>
                        </div>
                    </div>
                `).join("");
                box.classList.add("open");
                box.querySelectorAll(".vs-result").forEach(el => {
                    el.addEventListener("click", () => {
                        mmPick(side, Number(el.dataset.id));
                        box.innerHTML = "";
                        box.classList.remove("open");
                        input.value = "";
                    });
                });
            } catch (e) {
                box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
                box.classList.add("open");
            }
        }, 250));
    });

    $("#run-btn").addEventListener("click", runMatchmaking);
    $("#reset-btn").addEventListener("click", () => {
        mmPicks[1] = null; mmPicks[2] = null;
        renderMmCard(1); renderMmCard(2);
        $("#mm-result").style.display = "none";
        updateRunBtn();
    });
    $("#random-btn").addEventListener("click", randomMatchup);

    const id1 = getQueryParam("id1");
    const id2 = getQueryParam("id2");
    if (id1 && id2) {
        await mmPick(1, Number(id1));
        await mmPick(2, Number(id2));
        runMatchmaking();
    } else {
        if (id1) mmPick(1, Number(id1));
        if (id2) mmPick(2, Number(id2));
    }
}

async function mmPick(side, id) {
    try {
        const f = await api.fighter(id);
        mmPicks[side] = f;
        renderMmCard(side);
        updateRunBtn();
    } catch (e) {
        alert("Error: " + e.message);
    }
}

function renderMmCard(side) {
    const card = $(`.mm-card[data-side="${side}"]`);
    const f = mmPicks[side];
    if (!f) {
        card.classList.add("empty-card");
        card.innerHTML = `<div class="vs-empty"><div class="vs-empty-icon">?</div><p>${t("common.no_fighter")}</p></div>`;
        return;
    }
    card.classList.remove("empty-card");
    // thumbnail UFC-FR d'abord (fiable) ; Tapology souvent mort
    const photo = f.photo_thumbnail_url || f.photo_url;
    const cornerClass = side === "1" ? "red" : "blue";
    card.innerHTML = `
        <button class="vs-clear" title="${t("common.remove")}" onclick="mmClear(${side})">&times;</button>
        <div class="mm-corner-strip ${cornerClass}"></div>
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
                ${f.ufc_official_rank ? `<span class="profile-tag red">#${f.ufc_official_rank} UFC</span>` : ""}
            </div>
        </div>
    `;
}

function mmClear(side) {
    mmPicks[side] = null;
    renderMmCard(side);
    updateRunBtn();
    $("#mm-result").style.display = "none";
}
window.mmClear = mmClear;

function updateRunBtn() {
    $("#run-btn").disabled = !(mmPicks[1] && mmPicks[2]);
}

async function randomMatchup() {
    try {
        const data = await api.fighters({ limit: 50 });
        if (data.fighters.length < 2) {
            alert("Pas assez de fighters en BDD pour un tirage aleatoire.");
            return;
        }
        const shuffled = data.fighters.slice().sort(() => Math.random() - 0.5);
        await mmPick(1, shuffled[0].id);
        await mmPick(2, shuffled[1].id);
    } catch (e) { alert(e.message); }
}

// le systeme Scouter — DBZ power level reveal

// Vegeta-Scouter.gif = loading only → 6 GIFs distincts pour les résultats
// Densité sur 45–90 (là où sont la plupart des bons combattants)
const SCOUTER_TIERS = [
    { max: 30,  gif: "assets/gifs/Dessin Alien.gif",             label: "POWER LEVEL: LOW",       sublabel: "Earthling",      color: "#90caf9" },
    { max: 45,  gif: "assets/gifs/Dragonball Z.gif",             label: "POWER LEVEL: AVERAGE",   sublabel: "Saiyan",         color: "#aed581" },
    { max: 60,  gif: "assets/gifs/Fond D'écran Goku.gif",        label: "POWER LEVEL: HIGH",      sublabel: "Super Saiyan",   color: "#ffd740" },
    { max: 73,  gif: "assets/gifs/freezer scouut.webp",          label: "POWER LEVEL: DANGEROUS", sublabel: "Frieza Level",   color: "#ce93d8" },
    { max: 88,  gif: "assets/gifs/Végéta pierre volantes.gif",   label: "POWER LEVEL: ELITE",     sublabel: "Super Saiyan 2", color: "#ff9800" },
    { max: 101, gif: "assets/gifs/Vegeta-casse.gif",             label: "POWER LEVEL: LEGENDARY", sublabel: "LEGENDARY",      color: "#ff5252" },
];

function scouterTier(score) {
    if (score === null || score === undefined) return SCOUTER_TIERS[1];
    return SCOUTER_TIERS.find(t => score < t.max) || SCOUTER_TIERS[SCOUTER_TIERS.length - 1];
}

// --- Son (joué au lancement du calcul) ---
let _scAudio = null;
function playScouterSound() {
    try {
        if (!_scAudio) { _scAudio = new Audio("assets/scouter.mp3"); _scAudio.volume = 0.65; }
        _scAudio.currentTime = 0;
        _scAudio.play().catch(() => {});
    } catch (_) {}
}

// --- Compteur animé 0 → target ---
function animateCounter(el, target, duration = 1100) {
    if (target === null || target === undefined) { el.textContent = "???"; return; }
    const start = performance.now();
    const from = 0;
    function step(now) {
        const t = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - t, 3); // ease-out cubic
        const cur = from + (target - from) * ease;
        el.textContent = cur.toFixed(1);
        if (t < 1) requestAnimationFrame(step);
        else el.textContent = target.toFixed(1);
    }
    requestAnimationFrame(step);
}

// --- Overlay de révélation : DUEL des power levels (les 2 persos DBZ se font face) ---
// Le perso de chaque combattant dépend de son scouter (palier). Les 2 power levels
// montent, choc d'énergie au centre, puis le gagnant (prono matchmaking) s'illumine
// et le perdant s'assombrit. Auto-fermeture 10s, ou croix / "Voir l'analyse".
function showScouterReveal(m, onClose) {
    const f1 = m.fighter1, f2 = m.fighter2;
    const winnerIsF1 = m.predicted_winner_id === f1.id;
    const winner = winnerIsF1 ? f1 : f2;
    const sc1 = f1.scouter_rating, sc2 = f2.scouter_rating;
    const t1 = scouterTier(sc1), t2 = scouterTier(sc2);
    const wProb = (winnerIsF1 ? f1.win_prob : f2.win_prob);
    // Δ de power level orienté vers le gagnant (n'affiche "▲" que s'il a réellement plus)
    const scWin = winnerIsF1 ? sc1 : sc2, scLose = winnerIsF1 ? sc2 : sc1;
    const upPower = (scWin != null && scLose != null && scWin > scLose)
        ? "▲ +" + (scWin - scLose).toFixed(1) + " POWER" : "";

    // Un côté du duel = un perso DBZ (selon le scouter) + son power level
    const fighterSide = (f, tier, side, mirror) => `
        <div class="scd-fighter ${side}">
            <div class="scd-char-big">
                <img src="${tier.gif}" alt="${esc(tier.sublabel)}"${mirror ? ' class="mirror"' : ''}
                     onerror="this.closest('.scd-char-big').classList.add('no-img')">
                <div class="scd-char-veil"></div>
                <div class="scd-corner" style="color:${tier.color};border-color:${tier.color}55">${tier.sublabel}</div>
            </div>
            <div class="scd-fname">${esc(f.name)}</div>
            <div class="scd-pl-label">POWER LEVEL</div>
            <div class="scd-pl" data-target="${f.scouter_rating != null ? f.scouter_rating : ''}" style="color:${tier.color};text-shadow:0 0 22px ${tier.color}">${f.scouter_rating != null ? "0.0" : "???"}</div>
            <div class="scd-bar-track"><div class="scd-bar-fill" data-target="${f.scouter_rating != null ? Math.min(f.scouter_rating,100) : 0}" style="background:${tier.color}"></div></div>
            <div class="scd-tier" style="color:${tier.color}">${tier.label}</div>
        </div>`;

    const overlay = document.createElement("div");
    overlay.className = "sc-overlay";
    overlay.innerHTML = `
        <div class="scd-panel-wrap scd-duel-wrap">
            <div class="sc-crt"></div>
            <button class="scd-close-x" id="sc-x-btn" aria-label="Fermer">✕</button>

            <div class="scd-head">
                <span class="scd-dot scd-blink" style="background:#4ade80"></span>
                MM.AI SCOUTER — BATTLE SCAN
            </div>

            <div class="scd-duel">
                ${fighterSide(f1, t1, "red", false)}
                <div class="scd-clash">
                    <div class="scd-vs">VS</div>
                    <div class="scd-clash-orb"></div>
                    <div class="scd-clash-flash"></div>
                </div>
                ${fighterSide(f2, t2, "blue", true)}
            </div>

            <div class="scd-verdict" id="sc-verdict">
                <i>⚡</i> ${esc(winner.name)} ${upPower} · ${wProb != null ? wProb.toFixed(0)+"% WIN" : ""}
            </div>

            <button class="sc-btn-close" id="sc-close-btn">
                <span>▼</span> VOIR L'ANALYSE
            </button>
            <div class="scd-autoclose" id="sc-auto">Fermeture auto dans <span id="sc-cd">10</span>s</div>
        </div>
    `;

    document.body.appendChild(overlay);

    let closed = false;
    let autoTimer = null, cdTimer = null;
    const close = () => {
        if (closed) return;
        closed = true;
        if (autoTimer) clearTimeout(autoTimer);
        if (cdTimer) clearInterval(cdTimer);
        overlay.classList.remove("visible");
        setTimeout(() => { overlay.remove(); onClose(); }, 280);
    };
    overlay.querySelector("#sc-close-btn").addEventListener("click", close);
    overlay.querySelector("#sc-x-btn").addEventListener("click", close);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });

    // Séquence : apparition → montée des 2 power levels → choc → verdict + illumination
    requestAnimationFrame(() => {
        overlay.classList.add("visible");
        setTimeout(() => {
            overlay.querySelectorAll(".scd-pl").forEach((el) => {
                const tgt = el.getAttribute("data-target");
                if (tgt !== "") animateCounter(el, Number(tgt), 1300);
            });
            overlay.querySelectorAll(".scd-bar-fill").forEach((el) => {
                el.style.transition = "width 1.3s cubic-bezier(0.22,1,0.36,1)";
                el.style.width = Number(el.getAttribute("data-target")) + "%";
            });
        }, 350);
        // choc d'énergie une fois les power levels stabilisés
        setTimeout(() => {
            const clash = overlay.querySelector(".scd-clash");
            if (clash) clash.classList.add("clash-go");
        }, 1650);
        // verdict + gagnant illuminé / perdant assombri
        setTimeout(() => {
            const v = overlay.querySelector("#sc-verdict");
            if (v) v.classList.add("show");
            const fr = overlay.querySelector(".scd-fighter.red");
            const fb = overlay.querySelector(".scd-fighter.blue");
            (winnerIsF1 ? fr : fb)?.classList.add("is-winner");
            (winnerIsF1 ? fb : fr)?.classList.add("is-loser");
        }, 1950);
    });

    // Compte à rebours + auto-fermeture 10s
    let cd = 10;
    cdTimer = setInterval(() => {
        cd--;
        const el = overlay.querySelector("#sc-cd");
        if (el) el.textContent = cd;
        if (cd <= 0) clearInterval(cdTimer);
    }, 1000);
    autoTimer = setTimeout(close, 10000);
}

// ---------------------------------------------------------------------------
// Écrans de chargement du matchmaking — COMMUTABLES.
// Mets MM_LOADER sur "gif" (Vegeta historique), "radar", ou "random".
// Chaque loader expose html(name1,name2) + tick(prog 0..100) pour la barre.
// ---------------------------------------------------------------------------
const MM_LOADER = "gif";

// barre de progression linéaire commune (#sc-load-bar)
function _mmBarTick(prog) {
    const b = document.getElementById("sc-load-bar");
    if (b) b.style.width = prog + "%";
}

const MM_LOADERS = {
    // 0 — le GIF Vegeta d'origine (inchangé)
    gif: {
        html: (n1, n2) => `
            <div class="scouter-loading-inner">
                <div class="scouter-loading-gif-wrap">
                    <img src="assets/gifs/Vegeta-Scouter.gif" alt="scanning..." class="scouter-loading-gif">
                    <div class="scouter-loading-scanlines"></div>
                </div>
                <div class="scouter-loading-hud">
                    <div class="scouter-hud-row"><span class="scouter-hud-label">STATUS</span><span class="scouter-hud-val scouter-blink">SCANNING...</span></div>
                    <div class="scouter-hud-row"><span class="scouter-hud-label">TARGET 1</span><span class="scouter-hud-val">${esc(n1)}</span></div>
                    <div class="scouter-hud-row"><span class="scouter-hud-label">TARGET 2</span><span class="scouter-hud-val">${esc(n2)}</span></div>
                    <div class="scouter-hud-row"><span class="scouter-hud-label">ENGINE</span><span class="scouter-hud-val">MM.AI v2</span></div>
                    <div class="scouter-loading-bar-wrap"><div class="scouter-loading-bar" id="sc-load-bar"></div></div>
                    <div class="scouter-dots"><span>█</span><span>█</span><span>█</span><span>█</span><span>█</span><span>█</span></div>
                </div>
            </div>`,
        tick: _mmBarTick,
    },

    // 1 — radar de scouter : balayage + verrouillage de cibles
    radar: {
        html: (n1, n2) => `
            <div class="ml-stage ml-radar-stage">
                <div class="ml-crt"></div>
                <div class="ml-radar-names"><span>${esc(n1)}</span><b>VS</b><span>${esc(n2)}</span></div>
                <div class="ml-radar">
                    <div class="ml-ring"></div><div class="ml-ring2"></div>
                    <div class="ml-cross-h"></div><div class="ml-cross-v"></div>
                    <div class="ml-sweep"></div>
                    <div class="ml-blip"></div><div class="ml-blip ml-blip2"></div>
                </div>
                <div class="ml-pl"><small>TARGET LOCK</small>SCANNING…</div>
                <div class="ml-barwrap"><div class="ml-bar" id="sc-load-bar"></div></div>
            </div>`,
        tick: _mmBarTick,
    },

};
const MM_LOADER_KEYS = Object.keys(MM_LOADERS);

function pickMmLoader() {
    if (MM_LOADER === "random") {
        return MM_LOADER_KEYS[Math.floor(Math.random() * MM_LOADER_KEYS.length)];
    }
    return MM_LOADERS[MM_LOADER] ? MM_LOADER : "gif";
}

// Affiche une overlay pour choisir la division du combat quand les 2 fighters
// viennent de categories differentes. Retourne une Promise<string|null> :
// null si meme division, sinon la weight_class choisie.
function pickFightClass(f1, f2) {
    const wc1 = f1.weight_class_current;
    const wc2 = f2.weight_class_current;
    if (!wc1 || !wc2 || wc1 === wc2) return Promise.resolve(null);

    return new Promise(resolve => {
        const overlay = document.createElement("div");
        overlay.className = "sc-overlay mm-div-pick-overlay";
        overlay.innerHTML = `
            <div class="mm-div-pick-box">
                <div class="mm-div-pick-title">${t("mm.div_select_title")}</div>
                <p class="mm-div-pick-msg">${t("mm.div_select_msg")}</p>
                <div class="mm-div-pick-btns">
                    <button class="mm-div-pick-btn" data-wc="${esc(wc1)}">
                        <span class="mm-div-pick-fighter">${esc(f1.name)}</span>
                        <span class="mm-div-pick-wc">${esc(wc1)}</span>
                    </button>
                    <button class="mm-div-pick-btn" data-wc="${esc(wc2)}">
                        <span class="mm-div-pick-fighter">${esc(f2.name)}</span>
                        <span class="mm-div-pick-wc">${esc(wc2)}</span>
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        requestAnimationFrame(() => overlay.classList.add("visible"));
        overlay.querySelectorAll(".mm-div-pick-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                const picked = btn.dataset.wc;
                overlay.classList.remove("visible");
                setTimeout(() => overlay.remove(), 280);
                resolve(picked);
            });
        });
    });
}

async function runMatchmaking() {
    if (!(mmPicks[1] && mmPicks[2])) return;

    // Si divisions differentes, demander dans laquelle se fait le combat
    const fightClass = await pickFightClass(mmPicks[1], mmPicks[2]);

    const btn = $("#run-btn");
    btn.disabled = true;
    btn.textContent = t("mm.calculating");

    // le son dès le clic
    playScouterSound();

    const id1 = mmPicks[1].id, id2 = mmPicks[2].id;
    const out = $("#mm-result");

    // Loader en OVERLAY plein écran centré (pour bien voir l'animation choisie,
    // au lieu d'un petit bloc en bas de page).
    const variant = pickMmLoader();
    const loader = MM_LOADERS[variant];
    const loadOverlay = document.createElement("div");
    loadOverlay.className = "sc-overlay mm-load-overlay";
    loadOverlay.innerHTML = `<div class="scouter-loading ml-${variant} mm-load-card" style="width:640px;max-width:94vw">${loader.html(mmPicks[1].name, mmPicks[2].name)}</div>`;
    document.body.appendChild(loadOverlay);
    requestAnimationFrame(() => loadOverlay.classList.add("visible"));
    const removeLoader = () => { loadOverlay.classList.remove("visible"); setTimeout(() => loadOverlay.remove(), 280); };

    // Durée mini d'affichage du loader (sinon l'API répond trop vite et on ne voit
    // pas l'animation). La barre monte progressivement jusqu'à ~92% pendant ce temps.
    const loadStart = performance.now();
    const MIN_LOADER_MS = 2800;
    let prog = 0;
    const progInterval = setInterval(() => {
        prog = Math.min(prog + Math.random() * 4 + 1.5, 92);
        loader.tick(prog);
    }, 180);

    try {
        // matchmaking + scouter des 2 fighters EN PARALLÈLE. Le scouter n'est pas
        // stocké en BDD (calcul à la demande), sinon les power levels du duel
        // restent "???" et les 2 persos tombent sur le même palier par défaut.
        const [m, s1, s2] = await Promise.all([
            api.matchmaking(id1, id2, fightClass),
            api.scouter(id1).catch(() => null),
            api.scouter(id2).catch(() => null),
        ]);

        // injecte les scouters calculés dans les fighters du résultat (mappé par id)
        const scById = {};
        scById[id1] = (s1 && s1.scouter_rating != null) ? Number(s1.scouter_rating) : null;
        scById[id2] = (s2 && s2.scouter_rating != null) ? Number(s2.scouter_rating) : null;
        if (m.fighter1 && m.fighter1.id in scById) m.fighter1.scouter_rating = scById[m.fighter1.id];
        if (m.fighter2 && m.fighter2.id in scById) m.fighter2.scouter_rating = scById[m.fighter2.id];

        // laisse le temps de voir l'animation avant de révéler
        await new Promise(r => setTimeout(r, Math.max(MIN_LOADER_MS - (performance.now() - loadStart), 0)));
        clearInterval(progInterval);
        loader.tick(100);

        if (m.error === "division_too_far") {
            removeLoader();
            out.style.display = "block";
            renderDivisionWarning(m);
            out.scrollIntoView({ behavior: "smooth", block: "start" });
        } else {
            setTimeout(() => {
                removeLoader();
                showScouterReveal(m, () => {
                    renderMatchmakingResult(m);
                    out.style.display = "block";
                    out.scrollIntoView({ behavior: "smooth", block: "start" });
                });
            }, 350);
        }
    } catch (e) {
        clearInterval(progInterval);
        removeLoader();
        out.style.display = "block";
        out.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
    } finally {
        btn.disabled = false;
        btn.textContent = t("mm.run_analysis");
    }
}

function renderMatchmakingResult(m) {
    const f1 = m.fighter1, f2 = m.fighter2;
    const w1 = f1.win_prob, w2 = f2.win_prob;
    const winnerName = m.predicted_winner_name;
    const winnerSide = m.predicted_winner_id === f1.id ? "red" : "blue";
    const out = $("#mm-result");
    out.style.display = "block";

    out.innerHTML = `
        <!-- Bandeau prediction principal -->
        <div class="mm-banner ${winnerSide}-winner">
            <div class="mm-banner-inner">
                <div class="mm-banner-side red ${winnerSide === 'red' ? 'is-winner' : ''}">
                    <div class="mm-banner-photo">
                        ${(f1.photo_thumbnail_url || f1.photo_url)
                            ? `<img src="${esc(f1.photo_thumbnail_url || f1.photo_url)}" alt="${esc(f1.name)}" onerror="this.parentNode.innerHTML='<div class=&quot;no-photo&quot;>${esc(initials(f1.name))}</div>'">`
                            : `<div class="no-photo">${esc(initials(f1.name))}</div>`}
                    </div>
                    <div class="mm-banner-name">${esc(f1.name)}</div>
                    ${winnerSide === 'red' ? `<div class="mm-winner-tag">${t("mm.predicted_winner")}</div>` : ""}
                    ${f1.fighting_away ? `<div class="mm-away-badge">↑ ${t("mm.div_cross_pen")}</div>` : ""}
                    <div class="mm-banner-prob">${w1.toFixed(1)}<small>%</small></div>
                </div>

                <div class="mm-banner-center">
                    <div class="mm-banner-vs">VS</div>
                    <div class="mm-banner-meta">
                        <div class="mm-confidence ${m.confidence > 25 ? 'high' : 'low'}">${esc(m.confidence_label)}</div>
                        <div class="mm-method-hint">${t("mm.likely_method")} : <strong>${esc(m.method_hint)}</strong></div>
                        <div class="mm-round-hint">${esc(m.round_hint)}</div>
                        ${m.fight_class ? `<div class="mm-fight-class-tag">⚖ ${esc(m.fight_class)}</div>` : ""}
                    </div>
                </div>

                <div class="mm-banner-side blue ${winnerSide === 'blue' ? 'is-winner' : ''}">
                    <div class="mm-banner-photo">
                        ${(f2.photo_thumbnail_url || f2.photo_url)
                            ? `<img src="${esc(f2.photo_thumbnail_url || f2.photo_url)}" alt="${esc(f2.name)}" onerror="this.parentNode.innerHTML='<div class=&quot;no-photo&quot;>${esc(initials(f2.name))}</div>'">`
                            : `<div class="no-photo">${esc(initials(f2.name))}</div>`}
                    </div>
                    <div class="mm-banner-name">${esc(f2.name)}</div>
                    ${winnerSide === 'blue' ? `<div class="mm-winner-tag">${t("mm.predicted_winner")}</div>` : ""}
                    ${f2.fighting_away ? `<div class="mm-away-badge">↑ ${t("mm.div_cross_pen")}</div>` : ""}
                    <div class="mm-banner-prob">${w2.toFixed(1)}<small>%</small></div>
                </div>
            </div>

            <!-- Barre de probabilite (animation choc d'energies) -->
            <div class="mm-prob-bar-wrap">
                <div class="mm-prob-bar">
                    <div class="mm-prob-fill-1" id="mm-pf1" style="width:50%">
                        <span class="lbl" id="mm-pl1">50.0%</span>
                    </div>
                    <div class="mm-prob-seam" id="mm-pseam"></div>
                    <div class="mm-prob-fill-2" id="mm-pf2" style="width:50%">
                        <span class="lbl" id="mm-pl2">50.0%</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Analyse IA (chargee en asynchrone) -->
        <div class="mm-ai" id="mm-ai-block">
            <div class="mm-ai-glow"></div>
            <div class="mm-ai-head">
                <div class="mm-ai-badge">
                    <span class="mm-ai-spark">◆</span>
                    <span class="mm-ai-title">${t("mm.ai_title")}</span>
                </div>
                <div class="mm-ai-status" id="mm-ai-status">${t("mm.ai_thinking")}</div>
            </div>
            <div class="mm-ai-body">
                <div class="mm-ai-text" id="mm-ai-text">
                    <span class="mm-ai-cursor">▍</span>
                </div>
                <div class="mm-ai-gauge-wrap">
                    <div class="mm-ai-gauge" id="mm-ai-gauge" style="--val:0">
                        <svg viewBox="0 0 120 120">
                            <circle class="g-track" cx="60" cy="60" r="52"></circle>
                            <circle class="g-fill"  cx="60" cy="60" r="52"></circle>
                        </svg>
                        <div class="mm-ai-gauge-num"><span id="mm-ai-gauge-num">--</span><small>%</small></div>
                    </div>
                    <div class="mm-ai-gauge-label">${t("mm.ai_reliability")}</div>
                    <div class="mm-ai-completeness" id="mm-ai-completeness"></div>
                </div>
            </div>
        </div>

        <!-- Tale of the tape -->
        <div class="mm-block">
            <h3 class="mm-block-title">${t("mm.tale_of_tape")}</h3>
            <div class="mm-tape">
                ${tapeRow(t("common.division"),     f1.tape.weight_class, f2.tape.weight_class, "text")}
                ${tapeRow(t("common.nationality"),  f1.tape.nationality,  f2.tape.nationality,  "text")}
                ${tapeRow(t("common.age"),          f1.tape.age,          f2.tape.age,          "lowerBetter")}
                ${tapeRow(t("common.height"),       f1.tape.height_inches ? f1.tape.height_inches+' in' : null, f2.tape.height_inches ? f2.tape.height_inches+' in' : null)}
                ${tapeRow(t("common.reach"),        f1.tape.reach_inches  ? f1.tape.reach_inches +' in' : null, f2.tape.reach_inches  ? f2.tape.reach_inches +' in' : null)}
                ${tapeRow(t("common.stance"),       f1.tape.stance,       f2.tape.stance,       "text")}
                ${tapeRow(t("common.record"),       `${f1.record[0]}-${f1.record[1]}${f1.record[2]?'-'+f1.record[2]:''}`, `${f2.record[0]}-${f2.record[1]}${f2.record[2]?'-'+f2.record[2]:''}`, "text")}
                ${tapeRow(t("common.streak"),       f1.current_streak,    f2.current_streak,    "streak")}
                ${tapeRow(t("common.ufc_rank"),     (f1.ufc_rank && Number(f1.ufc_rank) <= 15) ? '#'+f1.ufc_rank : null, (f2.ufc_rank && Number(f2.ufc_rank) <= 15) ? '#'+f2.ufc_rank : null, "lowerBetter")}
                ${tapeRow(t("mm.base_elo"),         fmtNumber(f1.base_elo, 0), fmtNumber(f2.base_elo, 0))}
                ${tapeRow(t("mm.scouter"),          fmtNumber(f1.scouter_rating, 1), fmtNumber(f2.scouter_rating, 1))}
            </div>
        </div>

        <!-- Style matchup -->
        <div class="mm-block">
            <h3 class="mm-block-title">${t("mm.style_matchup")}</h3>
            <div class="mm-style-grid">
                ${styleCard(f1, "red")}
                ${styleCard(f2, "blue")}
            </div>
        </div>

        <!-- Breakdown des facteurs -->
        <div class="mm-block">
            <h3 class="mm-block-title">${t("mm.factor_breakdown")}</h3>
            <p class="mm-block-sub">${t("mm.breakdown_sub")}</p>
            <div class="mm-breakdown">
                ${breakdownTable(f1, f2)}
            </div>
        </div>

        <!-- Actions -->
        <div class="mm-footer">
            <div class="mm-actions">
                <a href="compare.html?id1=${f1.id}&id2=${f2.id}" class="btn btn-ghost">${t("mm.see_compare")}</a>
                <a href="fighter.html?id=${f1.id}" class="btn btn-ghost">${t("mm.profile_link")} ${esc(f1.name)}</a>
                <a href="fighter.html?id=${f2.id}" class="btn btn-ghost">${t("mm.profile_link")} ${esc(f2.name)}</a>
            </div>
        </div>
    `;

    // Animation barre de probabilite : part de 50/50 et se stabilise sur le verdict.
    requestAnimationFrame(() => requestAnimationFrame(() => {
        const pf1 = document.getElementById("mm-pf1"), pf2 = document.getElementById("mm-pf2");
        const seam = document.getElementById("mm-pseam");
        if (pf1) pf1.style.width = w1 + "%";
        if (pf2) pf2.style.width = w2 + "%";
        if (seam) seam.style.left = w1 + "%";
        const l1 = document.getElementById("mm-pl1"), l2 = document.getElementById("mm-pl2");
        if (l1) animateCounter2(l1, w1);
        if (l2) animateCounter2(l2, w2);
    }));

    // L'analyse IA se charge apres coup (l'appel LLM prend 1-3s).
    loadAiAnalysis(f1.id, f2.id);
}

// Compteur 0→target avec suffixe % (pour la barre de proba)
function animateCounter2(el, target, duration = 1000) {
    const start = performance.now(), from = 50;
    function step(now) {
        const p = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - p, 3);
        el.textContent = (from + (target - from) * ease).toFixed(1) + "%";
        if (p < 1) requestAnimationFrame(step);
        else el.textContent = target.toFixed(1) + "%";
    }
    requestAnimationFrame(step);
}

// ---------------------------------------------------------------------------
// Analyse IA : appelle /api/matchmaking/analysis, anime la jauge de fiabilite
// et "tape" le texte facon terminal.
// ---------------------------------------------------------------------------
async function loadAiAnalysis(id1, id2) {
    const block  = document.getElementById("mm-ai-block");
    const status = document.getElementById("mm-ai-status");
    const textEl = document.getElementById("mm-ai-text");
    if (!block) return;

    try {
        const a = await api.matchmakingAnalysis(id1, id2);

        // Statut : IA reelle ou mode secours (pas de cle configuree)
        const isAi = a.ai_enabled && a.source && a.source.indexOf("error") === -1
                     && a.source !== "no_key";
        status.textContent = isAi ? (a.source || t("mm.ai_done")) : t("mm.ai_fallback");
        status.classList.toggle("is-fallback", !isAi);

        // Jauge de fiabilite (anneau conique)
        const rel = (a.reliability === null || a.reliability === undefined) ? null : a.reliability;
        animateGauge(rel);

        // Completude des donnees (le "data_score" du prono)
        const comp = document.getElementById("mm-ai-completeness");
        if (comp && a.data_completeness !== undefined) {
            comp.innerHTML = `${t("mm.ai_data_coverage")} : <strong>${a.data_completeness}%</strong>`;
        }

        // Effet machine a ecrire
        typewriter(textEl, a.analysis || "—");
        block.classList.add("is-ready");
    } catch (e) {
        status.textContent = t("mm.ai_error");
        status.classList.add("is-fallback");
        textEl.innerHTML = `<span class="muted">${esc(e.message)}</span>`;
    }
}

function animateGauge(value) {
    const gauge = document.getElementById("mm-ai-gauge");
    const numEl = document.getElementById("mm-ai-gauge-num");
    if (!gauge) return;
    if (value === null) {
        gauge.style.setProperty("--val", 0);
        if (numEl) numEl.textContent = "??";
        return;
    }
    // Couleur selon le niveau de confiance
    const color = value >= 70 ? "#37d67a" : value >= 45 ? "#ffb020" : "#ff5470";
    gauge.style.setProperty("--gauge-color", color);
    const start = performance.now();
    function step(now) {
        const p = Math.min((now - start) / 1000, 1);
        const ease = 1 - Math.pow(1 - p, 3);
        const cur = value * ease;
        gauge.style.setProperty("--val", cur);
        if (numEl) numEl.textContent = Math.round(cur);
        if (p < 1) requestAnimationFrame(step);
        else if (numEl) numEl.textContent = value;
    }
    requestAnimationFrame(step);
}

function typewriter(el, text) {
    if (!el) return;
    el.innerHTML = `<span class="mm-ai-typed"></span><span class="mm-ai-cursor">▍</span>`;
    const span = el.querySelector(".mm-ai-typed");
    let i = 0;
    const speed = 12; // ms par caractere
    function step() {
        span.textContent = text.slice(0, i);
        i++;
        if (i <= text.length) setTimeout(step, speed);
        else el.querySelector(".mm-ai-cursor").classList.add("done");
    }
    step();
}

// Convertit une streak ("2W", "W2", "1L", "L1", "0"...) en valeur signée
// (victoires = positif, défaites = négatif). Tolère l'ordre lettre/chiffre.
function streakSigned(s) {
    if (s === null || s === undefined || s === "") return null;
    const str = String(s).trim();
    const num = str.match(/\d+/);
    if (!num) return null;
    const n = Number(num[0]);
    return /l/i.test(str) ? -n : n;
}

function tapeRow(label, a, b, mode = "default") {
    const fmt = (v) => (v === null || v === undefined || v === "") ? '<span class="muted">--</span>' : esc(v);
    let highA = "", highB = "";
    if (mode === "streak") {
        const sa = streakSigned(a), sb = streakSigned(b);
        if (sa !== null && sb !== null && sa !== sb) {
            if (sa > sb) highA = "advantage"; else highB = "advantage";
        }
        return `
        <div class="mm-tape-row">
            <div class="mm-tape-val left ${highA}">${fmt(a)}</div>
            <div class="mm-tape-label">${esc(label)}</div>
            <div class="mm-tape-val right ${highB}">${fmt(b)}</div>
        </div>
    `;
    }
    const ax = a !== null && a !== undefined && a !== "" ? Number(String(a).replace(/[^\d.-]/g, "")) : null;
    const bx = b !== null && b !== undefined && b !== "" ? Number(String(b).replace(/[^\d.-]/g, "")) : null;
    if (ax !== null && bx !== null && !Number.isNaN(ax) && !Number.isNaN(bx) && ax !== bx) {
        if (mode === "lowerBetter") {
            if (ax < bx) highA = "advantage"; else highB = "advantage";
        } else if (mode !== "text") {
            if (ax > bx) highA = "advantage"; else highB = "advantage";
        }
    }
    return `
        <div class="mm-tape-row">
            <div class="mm-tape-val left ${highA}">${fmt(a)}</div>
            <div class="mm-tape-label">${esc(label)}</div>
            <div class="mm-tape-val right ${highB}">${fmt(b)}</div>
        </div>
    `;
}

function styleCard(f, corner) {
    const s = f.style;
    return `
        <div class="mm-style-card ${corner}">
            <div class="mm-style-corner">${corner === "red" ? t("mm.red_corner") : t("mm.blue_corner")}</div>
            <div class="mm-style-label">${esc(s.label)}</div>
            <div class="mm-style-name">${esc(f.name)}</div>
            <div class="mm-style-bars">
                <div class="mm-style-bar">
                    <span class="lbl">${t("mm.m_ko")}</span>
                    <span class="bar"><span class="fill ko" style="width:${s.ko_pct}%"></span></span>
                    <span class="pct">${s.ko_pct}%</span>
                </div>
                <div class="mm-style-bar">
                    <span class="lbl">${t("mm.m_sub")}</span>
                    <span class="bar"><span class="fill sub" style="width:${s.sub_pct}%"></span></span>
                    <span class="pct">${s.sub_pct}%</span>
                </div>
                <div class="mm-style-bar">
                    <span class="lbl">${t("mm.m_dec")}</span>
                    <span class="bar"><span class="fill dec" style="width:${s.dec_pct}%"></span></span>
                    <span class="pct">${s.dec_pct}%</span>
                </div>
            </div>
            <div class="mm-style-finish">
                <span class="lbl">${t("mm.finish_rate")}</span>
                <span class="val">${s.finish_rate}%</span>
            </div>
        </div>
    `;
}

function renderDivisionWarning(m) {
    const f1 = m.fighter1 || mmPicks[1] || {};
    const f2 = m.fighter2 || mmPicks[2] || {};
    const wc1 = f1.weight_class || f1.weight_class_current || "?";
    const wc2 = f2.weight_class || f2.weight_class_current || "?";
    $("#mm-result").innerHTML = `
        <div class="mm-division-warning">
            <div class="mm-division-warning-icon">&#9878;</div>
            <h3 class="mm-division-warning-title">${t("mm.div_too_far")}</h3>
            <p class="mm-division-warning-msg">${esc(m.message || t("mm.div_too_far"))}</p>
            <div class="mm-division-fighters">
                <div class="mm-division-fighter">
                    <strong>${esc(f1.name || "Fighter 1")}</strong>
                    <span class="mm-division-wc">${esc(wc1)}</span>
                </div>
                <div class="mm-division-vs">vs</div>
                <div class="mm-division-fighter">
                    <strong>${esc(f2.name || "Fighter 2")}</strong>
                    <span class="mm-division-wc">${esc(wc2)}</span>
                </div>
            </div>
            <p class="mm-division-hint">${t("mm.div_hint")}</p>
        </div>
    `;
}

function breakdownTable(f1, f2) {
    const labels = {
        rating:             t("mm.base_elo"),
        wins_bonus:         t("mm.bd_wins"),
        losses_pen:         t("mm.bd_losses"),
        ufc_rank:           t("mm.bd_ufc_rank"),
        champion:           t("mm.bd_champion"),
        form:               t("mm.bd_form"),
        inactivity:         t("mm.bd_inactivity"),
        age_pen:            t("mm.bd_age"),
        h2h:                t("mm.bd_h2h"),
        cross_division_pen: t("mm.div_cross_pen"),
    };
    // On masque les lignes où les deux valeurs sont 0 (ex: cross_division_pen absent)
    const keys = Object.keys(labels).filter(k =>
        (f1.breakdown[k] || 0) !== 0 || (f2.breakdown[k] || 0) !== 0
    );
    const max = Math.max(
        ...keys.flatMap(k => [Math.abs(f1.breakdown[k] || 0), Math.abs(f2.breakdown[k] || 0)]),
        1,
    );
    const rows = keys.map(k => {
        const v1 = f1.breakdown[k] || 0;
        const v2 = f2.breakdown[k] || 0;
        const w1 = Math.abs(v1) / max * 100;
        const w2 = Math.abs(v2) / max * 100;
        const sign1 = v1 < 0 ? "neg" : "pos";
        const sign2 = v2 < 0 ? "neg" : "pos";
        return `
            <div class="bd-row">
                <div class="bd-side left">
                    <span class="bd-val ${sign1}">${v1 >= 0 ? "+" : ""}${v1.toFixed(1)}</span>
                    <span class="bd-bar"><span class="fill ${sign1}" style="width:${w1}%"></span></span>
                </div>
                <div class="bd-label">${esc(labels[k])}</div>
                <div class="bd-side right">
                    <span class="bd-bar"><span class="fill ${sign2}" style="width:${w2}%"></span></span>
                    <span class="bd-val ${sign2}">${v2 >= 0 ? "+" : ""}${v2.toFixed(1)}</span>
                </div>
            </div>
        `;
    }).join("");
    const total1 = f1.score_total, total2 = f2.score_total;
    return rows + `
        <div class="bd-row total-row">
            <div class="bd-side left"><span class="bd-val total">${total1.toFixed(1)}</span></div>
            <div class="bd-label">${t("mm.total_score")}</div>
            <div class="bd-side right"><span class="bd-val total">${total2.toFixed(1)}</span></div>
        </div>
        <div class="bd-total-note">${t("mm.total_score_note")}</div>
    `;
}
