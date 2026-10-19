// MM.AI - Panel admin (page interne /admin.html)
// Securite a 2 couches, 100% serveur-side :
//   1. login normal (email + mot de passe fort)  -> JWT classique
//   2. 2FA TOTP (Google Authenticator)           -> "jeton admin" court (60 min)
// Les endpoints data (/api/admin/*) exigent le JETON ADMIN. Les endpoints 2FA
// (status/setup/enable/login) acceptent le JWT de login. Aucun lien vers cette
// page sur le site public : on y vient en tapant l'URL, puis on passe les 2 portes.
//
// Onglets : Dashboard (stats cachees) · Fighters (edition) · Users/VIP · Reports.
// Regle projet : aucune suppression. On edite, on change le tier, on resout.

const AdminPanel = (() => {
    const root = () => document.getElementById("admin-root");
    const esc = s => String(s == null ? "" : s).replace(/[<>&"']/g, c =>
        ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&#39;" }[c]));

    const ADMIN_TOKEN_KEY = "mmai-admin-token";
    let adminToken = null;
    try { adminToken = localStorage.getItem(ADMIN_TOKEN_KEY); } catch {}
    function setAdminToken(t) { adminToken = t; try { localStorage.setItem(ADMIN_TOKEN_KEY, t); } catch {} }
    function clearAdminToken() { adminToken = null; try { localStorage.removeItem(ADMIN_TOKEN_KEY); } catch {} }

    let drawerWired = false;

    const state = {
        tab: "dashboard",
        fighters: { page: 1, search: "" },
        users: { page: 1, search: "", tier: "" },
        reports: { status: "open" },
        editing: null,
    };

    // ---- Couche API ---------------------------------------------------------

    // Endpoints data : signes avec le JETON ADMIN. Si 401/403 -> session 2FA
    // expiree : on nettoie et on relance le portail (re-demande un code).
    async function apiGet(path) {
        const r = await fetch(path, { headers: { Authorization: "Bearer " + (adminToken || "") } });
        if (r.status === 401 || r.status === 403) { clearAdminToken(); guard(); throw new Error("admin_session"); }
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `HTTP ${r.status}`);
        return r.json();
    }
    async function apiSend(path, method, body) {
        const r = await fetch(path, {
            method, body: JSON.stringify(body || {}),
            headers: { "Content-Type": "application/json", Authorization: "Bearer " + (adminToken || "") },
        });
        if (r.status === 401 || r.status === 403) { clearAdminToken(); guard(); throw new Error("admin_session"); }
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
        return data;
    }
    // Endpoints 2FA : signes avec le JWT de login normal (via MMAIAuth).
    async function apiPre(path, method, body) {
        const opts = { method: method || "GET" };
        if (body) { opts.body = JSON.stringify(body); opts.headers = { "Content-Type": "application/json" }; }
        const r = await window.MMAIAuth.authFetch(path, opts);
        const data = await r.json().catch(() => ({}));
        if (!r.ok) { const e = new Error(data.error || `HTTP ${r.status}`); e.status = r.status; throw e; }
        return data;
    }

    // ---- Portail (gate) -----------------------------------------------------

    function init() { guard(); }

    async function guard() {
        if (!window.MMAIAuth || !window.MMAIAuth.isLoggedIn()) {
            return denied("You must sign in first with your admin account.",
                `<a href="login.html?next=admin.html" class="adm-btn primary">Sign in</a>`);
        }
        let status;
        try {
            status = await apiPre("/api/admin/2fa/status");
        } catch (e) {
            if (e.status === 403) {
                return denied("Access denied — this account is not an administrator.",
                    `<a href="index.html" class="adm-btn">Back to site</a>`);
            }
            return denied("Your session expired. Please sign in again.",
                `<a href="login.html?next=admin.html" class="adm-btn primary">Sign in</a>`);
        }
        if (!status.twofa_available) {
            return denied("2FA libraries are not installed on the server (pyotp / qrcode).",
                `<a href="index.html" class="adm-btn">Back to site</a>`);
        }
        if (!status.totp_enabled) return renderSetup();
        if (adminToken) {
            try { await apiGet("/api/admin/check"); return showPanel(); }
            catch { clearAdminToken(); }
        }
        return renderCode();
    }

    function denied(msg, actions) {
        root().innerHTML = `
            <div class="adm-wrap">
                <div class="adm-head"><h1>Admin</h1><span class="adm-badge">restricted</span></div>
                <div class="adm-error" style="margin-top:18px;">${esc(msg)}</div>
                <div style="margin-top:18px;">${actions || ""}</div>
            </div>`;
    }

    // ---- 2FA : enrolement (QR) ----------------------------------------------

    async function renderSetup() {
        root().innerHTML = `<div class="adm-wrap"><div class="adm-loader">Preparing 2FA setup…</div></div>`;
        let d;
        try { d = await apiPre("/api/admin/2fa/setup", "POST"); }
        catch (e) {
            if (e.error === "already_enabled" || e.message === "already_enabled") return renderCode();
            return denied("Could not start 2FA setup: " + (e.message || e), `<a href="index.html" class="adm-btn">Back</a>`);
        }
        root().innerHTML = `
            <div class="adm-gate">
                <div class="adm-gate-card">
                    <div class="adm-badge" style="margin-bottom:14px;">First-time setup</div>
                    <h2>Enable two-factor authentication</h2>
                    <p class="adm-gate-sub">Scan this QR code with <b>Google Authenticator</b>, Authy, or any TOTP app.
                       Then enter the 6-digit code it shows to finish.</p>
                    <div class="adm-qr">${d.qr_svg}</div>
                    <p class="adm-gate-sub" style="margin-top:6px;">Can't scan? Enter this key manually:</p>
                    <div class="adm-secret">${esc(d.secret)}</div>
                    <form id="adm-2fa-form" autocomplete="off">
                        <input class="adm-code-input" id="adm-2fa-code" inputmode="numeric" maxlength="6"
                               placeholder="000000" autocomplete="one-time-code">
                        <button class="adm-btn primary" type="submit">Activate 2FA</button>
                    </form>
                    <div class="adm-gate-msg" id="adm-2fa-msg"></div>
                </div>
            </div>`;
        wireCodeForm("/api/admin/2fa/enable");
    }

    // ---- 2FA : login (code courant) -----------------------------------------

    function renderCode() {
        root().innerHTML = `
            <div class="adm-gate">
                <div class="adm-gate-card">
                    <div class="adm-badge" style="margin-bottom:14px;">🔒 Admin · 2FA</div>
                    <h2>Two-factor verification</h2>
                    <p class="adm-gate-sub">Enter the 6-digit code from your authenticator app.</p>
                    <form id="adm-2fa-form" autocomplete="off">
                        <input class="adm-code-input" id="adm-2fa-code" inputmode="numeric" maxlength="6"
                               placeholder="000000" autocomplete="one-time-code" autofocus>
                        <button class="adm-btn primary" type="submit">Verify</button>
                    </form>
                    <div class="adm-gate-msg" id="adm-2fa-msg"></div>
                </div>
            </div>`;
        wireCodeForm("/api/admin/2fa/login");
    }

    function wireCodeForm(endpoint) {
        const form = document.getElementById("adm-2fa-form");
        const input = document.getElementById("adm-2fa-code");
        const msg = document.getElementById("adm-2fa-msg");
        input.addEventListener("input", () => { input.value = input.value.replace(/\D/g, "").slice(0, 6); });
        form.addEventListener("submit", async e => {
            e.preventDefault();
            const code = input.value.trim();
            if (code.length !== 6) { msg.className = "adm-gate-msg err"; msg.textContent = "Enter the 6 digits."; return; }
            msg.className = "adm-gate-msg"; msg.textContent = "Checking…";
            try {
                const d = await apiPre(endpoint, "POST", { code });
                setAdminToken(d.admin_token);
                showPanel();
            } catch (err) {
                msg.className = "adm-gate-msg err";
                msg.textContent = (err.message === "invalid_code") ? "Invalid or expired code — try the next one." : ("Error: " + err.message);
                input.value = ""; input.focus();
            }
        });
    }

    // ---- Panel --------------------------------------------------------------

    function showPanel() {
        renderShell();
        if (!drawerWired) { wireDrawer(); drawerWired = true; }
        switchTab("dashboard");
    }

    function renderShell() {
        root().innerHTML = `
            <div class="adm-wrap">
                <div class="adm-head">
                    <h1>Admin panel</h1><span class="adm-badge">MM.AI</span>
                    <button class="adm-btn sm" id="adm-lock" style="margin-left:auto;">🔒 Lock</button>
                </div>
                <p class="adm-sub">Internal control — data, users & reports. 2FA session active.</p>
                <div class="adm-tabs">
                    <button class="adm-tab" data-tab="dashboard">Dashboard</button>
                    <button class="adm-tab" data-tab="fighters">Fighters</button>
                    <button class="adm-tab" data-tab="users">Users &amp; VIP</button>
                    <button class="adm-tab" data-tab="reports">Reports</button>
                </div>
                <div id="adm-content"><div class="adm-loader">Loading…</div></div>
            </div>`;
        root().querySelectorAll(".adm-tab").forEach(b =>
            b.addEventListener("click", () => switchTab(b.dataset.tab)));
        document.getElementById("adm-lock").addEventListener("click", () => { clearAdminToken(); guard(); });
    }

    function switchTab(name) {
        state.tab = name;
        root().querySelectorAll(".adm-tab").forEach(b =>
            b.classList.toggle("active", b.dataset.tab === name));
        if (name === "dashboard") loadDashboard();
        else if (name === "fighters") loadFighters();
        else if (name === "users") loadUsers();
        else if (name === "reports") loadReports();
    }

    const content = () => document.getElementById("adm-content");
    const fail = e => { if (e && e.message === "admin_session") return; if (content()) content().innerHTML = `<div class="adm-error">${esc(e.message || e)}</div>`; };

    // ---- Dashboard ----------------------------------------------------------

    async function loadDashboard() {
        content().innerHTML = `<div class="adm-loader">Loading stats…</div>`;
        try {
            const d = await apiGet("/api/admin/stats");
            const f = d.fighters || {}, u = d.users || {}, r = d.reports || {};
            const card = (v, l, cls = "") =>
                `<div class="adm-card ${cls}"><div class="v">${v ?? "—"}</div><div class="l">${l}</div></div>`;

            const topElo = (d.top_elo || []).map(x => `
                <tr>
                    <td><a href="fighter.html?id=${x.id}" style="color:var(--primary-2)">${esc(x.name)}</a></td>
                    <td>${esc(x.weight_class_current || "")} ${x.gender === "F" ? "♀" : ""}</td>
                    <td><b>${x.base_elo != null ? Math.round(x.base_elo) : "—"}</b></td>
                    <td>${x.scouter_rating != null ? Number(x.scouter_rating).toFixed(1) : "—"}</td>
                    <td>${x.fightmatrix_rating_points != null ? Math.round(x.fightmatrix_rating_points) : "—"}</td>
                </tr>`).join("");

            const recent = (d.recent_users || []).map(x => `
                <tr>
                    <td>${esc(x.pseudo)}</td>
                    <td>${esc(x.email)}</td>
                    <td><span class="adm-pill ${x.tier === "premium" ? "premium" : "free"}">${esc(x.tier || "free")}</span></td>
                    <td>${x.email_verified ? "✓" : "—"}</td>
                    <td style="white-space:nowrap">${fmtDate(x.created_at)}</td>
                </tr>`).join("");

            content().innerHTML = `
                <div class="adm-section-title">Fighters (${f.total ?? "—"})</div>
                <div class="adm-cards">
                    ${card(f.total, "Total")}
                    ${card(f.with_photo, "With photo", "accent")}
                    ${card(f.with_elo, "With Elo")}
                    ${card(f.verified, "Verified")}
                    ${card(f.active, "Active")}
                    ${card(f.women, "Women")}
                    ${card(f.with_league, "With league")}
                    ${card(f.missing_dob, "No birthdate", f.missing_dob ? "warn" : "")}
                    ${card(f.avg_quality, "Avg quality")}
                </div>

                <div class="adm-section-title">Users (${u.total ?? "—"})</div>
                <div class="adm-cards">
                    ${card(u.total, "Accounts")}
                    ${card(u.premium, "VIP / premium", "accent")}
                    ${card(u.free, "Free")}
                    ${card(u.verified, "Email verified")}
                    ${card(u.new_7d, "New (7d)")}
                    ${card(u.new_30d, "New (30d)")}
                    ${card(u.active_7d, "Active (7d)")}
                </div>

                <div class="adm-section-title">Reports</div>
                <div class="adm-cards">
                    ${card(r.open, "Open", r.open ? "warn" : "")}
                    ${card(r.resolved, "Resolved")}
                    ${card(r.total, "Total")}
                </div>

                <div class="adm-section-title">Top Elo (sanity check)</div>
                <div class="adm-table-wrap">
                    <table class="adm-table">
                        <thead><tr><th>Name</th><th>Division</th><th>Elo</th><th>Scouter</th><th>FM pts</th></tr></thead>
                        <tbody>${topElo || `<tr><td colspan="5" class="adm-empty">No Elo computed yet.</td></tr>`}</tbody>
                    </table>
                </div>

                <div class="adm-section-title">Latest signups</div>
                <div class="adm-table-wrap">
                    <table class="adm-table">
                        <thead><tr><th>Pseudo</th><th>Email</th><th>Tier</th><th>Verified</th><th>Joined</th></tr></thead>
                        <tbody>${recent || `<tr><td colspan="5" class="adm-empty">No users yet.</td></tr>`}</tbody>
                    </table>
                </div>`;
        } catch (e) { fail(e); }
    }

    // ---- Fighters -----------------------------------------------------------

    async function loadFighters() {
        const s = state.fighters;
        content().innerHTML = `
            <div class="adm-toolbar">
                <input class="adm-input" id="adm-f-search" placeholder="Search fighter by name or id…" value="${esc(s.search)}">
                <button class="adm-btn primary" id="adm-f-go">Search</button>
            </div>
            <div id="adm-f-results"><div class="adm-loader">Loading…</div></div>`;
        const go = () => { s.search = document.getElementById("adm-f-search").value.trim(); s.page = 1; fetchFighters(); };
        document.getElementById("adm-f-go").addEventListener("click", go);
        document.getElementById("adm-f-search").addEventListener("keydown", e => { if (e.key === "Enter") go(); });
        fetchFighters();
    }

    async function fetchFighters() {
        const s = state.fighters;
        const box = document.getElementById("adm-f-results");
        box.innerHTML = `<div class="adm-loader">Loading…</div>`;
        try {
            const qs = new URLSearchParams({ page: s.page, search: s.search }).toString();
            const d = await apiGet(`/api/admin/fighters?${qs}`);
            if (!d.fighters.length) { box.innerHTML = `<div class="adm-empty">No fighters found.</div>`; return; }
            const rows = d.fighters.map(x => {
                const thumb = x.photo_thumbnail_url
                    ? `<img class="adm-thumb" src="${esc(x.photo_thumbnail_url)}" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'adm-thumb',textContent:'${esc((x.name||'?')[0])}'}))">`
                    : `<span class="adm-thumb">${esc((x.name || "?")[0])}</span>`;
                const w = x.record_total_wins ?? 0, l = x.record_total_losses ?? 0, dr = x.record_total_draws ?? 0;
                return `<tr>
                    <td style="color:var(--text-muted)">#${x.id}</td>
                    <td style="display:flex;align-items:center;gap:10px">${thumb}<b>${esc(x.name)}</b></td>
                    <td>${esc(x.weight_class_current || "")} ${x.gender === "F" ? "♀" : ""}</td>
                    <td style="white-space:nowrap">${w}-${l}${dr ? "-" + dr : ""}</td>
                    <td>${x.base_elo != null ? Math.round(x.base_elo) : "—"}</td>
                    <td>${x.data_quality_score ?? "—"}</td>
                    <td>${x.is_verified ? `<span class="adm-pill yes">verified</span>` : `<span class="adm-pill no">no</span>`}</td>
                    <td><button class="adm-btn sm" data-edit="${x.id}">Edit</button></td>
                </tr>`;
            }).join("");
            box.innerHTML = `
                <div class="adm-table-wrap">
                    <table class="adm-table">
                        <thead><tr><th>ID</th><th>Name</th><th>Division</th><th>Record</th><th>Elo</th><th>Quality</th><th>Verified</th><th></th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
                ${pager(d, "fighters")}`;
            box.querySelectorAll("[data-edit]").forEach(b =>
                b.addEventListener("click", () => openFighterDrawer(b.dataset.edit)));
            wirePager(box, "fighters", fetchFighters);
        } catch (e) { if (e.message !== "admin_session") box.innerHTML = `<div class="adm-error">${esc(e.message)}</div>`; }
    }

    // ---- Drawer edition fighter --------------------------------------------

    const FIELDS = [
        ["Identity", [
            ["name", "Name", "text"], ["nickname", "Nickname", "text"],
            ["gender", "Gender", "gender"], ["date_of_birth", "Date of birth", "date"],
            ["nationality", "Nationality", "text"],
            ["weight_class_current", "Weight class", "text"], ["weight_class_origin", "Origin division", "text"],
            ["height_inches", "Height (in)", "text"], ["reach_inches", "Reach (in)", "text"],
            ["stance", "Stance", "text"], ["first_sport", "First sport", "text"],
            ["current_league", "Current league", "text"],
            ["photo_url", "Photo URL", "text"], ["photo_thumbnail_url", "Thumbnail URL", "text"],
        ]],
        ["Record", [
            ["record_total_wins", "Wins", "number"], ["record_total_losses", "Losses", "number"],
            ["record_total_draws", "Draws", "number"], ["record_total_nc", "No contest", "number"],
            ["record_ufc_wins", "UFC wins", "number"], ["record_ufc_losses", "UFC losses", "number"],
            ["record_ufc_draws", "UFC draws", "number"],
        ]],
        ["Finishes", [
            ["wins_by_ko_tko", "Wins KO/TKO", "number"], ["wins_by_submission", "Wins SUB", "number"],
            ["wins_by_decision", "Wins DEC", "number"], ["losses_by_ko_tko", "Losses KO/TKO", "number"],
            ["losses_by_submission", "Losses SUB", "number"], ["losses_by_decision", "Losses DEC", "number"],
        ]],
        ["Career", [
            ["career_debut_date", "Debut date", "date"], ["last_fight_date", "Last fight date", "date"],
            ["is_active", "Active", "bool"], ["is_ufc_champion", "UFC champion", "bool"],
            ["ufc_title_match_win", "Title match wins", "number"],
            ["current_streak", "Streak", "text"], ["last_5_results", "Last 5 (e.g. WWLWW)", "text"],
            ["ufc_official_rank", "UFC rank", "number"], ["ufc_p4p_rank", "P4P rank", "number"],
        ]],
        ["Ratings", [
            ["base_elo", "Base Elo", "number"], ["scouter_rating", "Scouter", "number"],
            ["fightmatrix_rating_points", "FightMatrix pts", "number"],
            ["fightmatrix_big_league_record", "Big league record", "text"],
        ]],
        ["Meta", [
            ["is_verified", "Verified", "bool"], ["data_quality_score", "Data quality (0-100)", "number"],
            ["data_source", "Data source", "text"], ["notes", "Notes", "textarea"],
        ]],
    ];

    async function openFighterDrawer(id) {
        const body = document.getElementById("adm-drawer-body");
        document.getElementById("adm-save-msg").textContent = "";
        body.innerHTML = `<div class="adm-loader">Loading…</div>`;
        openDrawerEl();
        try {
            const d = await apiGet(`/api/admin/fighters/${id}`);
            state.editing = d.fighter;
            document.getElementById("adm-drawer-title").textContent = `Edit · ${d.fighter.name} (#${d.fighter.id})`;
            body.innerHTML = FIELDS.map(([group, fields]) => `
                <div class="adm-fieldset-title">${group}</div>
                <div class="adm-grid2">
                    ${fields.map(([key, label, type]) => fieldHTML(key, label, type, d.fighter[key])).join("")}
                </div>`).join("")
                + `<div id="adm-history-section"><div class="adm-loader" style="padding:16px 0">Loading fight history…</div></div>`;
            loadFightHistory(id);
        } catch (e) { if (e.message !== "admin_session") body.innerHTML = `<div class="adm-error">${esc(e.message)}</div>`; }
    }

    function fieldHTML(key, label, type, value) {
        const full = (type === "textarea") ? " full" : "";
        let input;
        if (type === "bool") {
            const v = value === true ? "true" : "false";
            input = `<select data-key="${key}" data-orig="${v}">
                <option value="false"${v === "false" ? " selected" : ""}>No</option>
                <option value="true"${v === "true" ? " selected" : ""}>Yes</option></select>`;
        } else if (type === "gender") {
            const v = value === "F" ? "F" : "M";
            input = `<select data-key="${key}" data-orig="${v}">
                <option value="M"${v === "M" ? " selected" : ""}>M</option>
                <option value="F"${v === "F" ? " selected" : ""}>F (women)</option></select>`;
        } else if (type === "textarea") {
            const v = value == null ? "" : String(value);
            input = `<textarea data-key="${key}" data-orig="${esc(v)}">${esc(v)}</textarea>`;
        } else {
            const v = (value == null) ? "" : (type === "date" ? String(value).slice(0, 10) : String(value));
            const it = type === "number" ? "number" : (type === "date" ? "date" : "text");
            input = `<input type="${it}" data-key="${key}" data-orig="${esc(v)}" value="${esc(v)}"${type === "number" ? ' step="any"' : ""}>`;
        }
        return `<div class="adm-field${full}"><label>${esc(label)}</label>${input}</div>`;
    }

    function collectChanges() {
        const payload = {};
        document.querySelectorAll("#adm-drawer-body [data-key]").forEach(el => {
            const key = el.dataset.key;
            const orig = el.dataset.orig ?? "";
            const cur = el.value;
            if (String(cur).trim() === String(orig).trim()) return;
            if (el.tagName === "SELECT" && el.querySelector('option[value="true"]')) {
                payload[key] = (cur === "true");
            } else if (el.type === "number") {
                payload[key] = cur === "" ? "" : Number(cur);
            } else {
                payload[key] = cur;
            }
        });
        return payload;
    }

    async function saveFighter() {
        if (!state.editing) return;
        const msg = document.getElementById("adm-save-msg");
        const btn = document.getElementById("adm-drawer-save");
        const changes = collectChanges();
        if (!Object.keys(changes).length) { msg.className = "adm-save-msg"; msg.textContent = "Nothing changed."; return; }
        btn.disabled = true; msg.className = "adm-save-msg"; msg.textContent = "Saving…";
        try {
            await apiSend(`/api/admin/fighters/${state.editing.id}`, "PATCH", changes);
            msg.className = "adm-save-msg ok"; msg.textContent = "Saved ✓";
            setTimeout(() => { closeDrawerEl(); fetchFighters(); }, 600);
        } catch (e) {
            msg.className = "adm-save-msg err"; msg.textContent = "Error: " + e.message;
        } finally { btn.disabled = false; }
    }

    // ---- Fight history : affichage + ajout --------------------------------

    async function loadFightHistory(fid) {
        const sec = document.getElementById("adm-history-section");
        if (!sec) return;
        try {
            const d = await apiGet(`/api/admin/fighters/${fid}/history`);
            renderFightHistory(sec, fid, d.fights || []);
        } catch (e) {
            if (e.message === "admin_session") return;
            sec.innerHTML = `<div class="adm-fieldset-title" style="margin-top:22px">Fight history</div>
                <div class="adm-error">${esc(e.message)}</div>`;
        }
    }

    function renderFightHistory(sec, fid, fights) {
        const RESULT_CLS = { W: "yes", L: "no", D: "open", NC: "open" };
        const rows = fights.length
            ? fights.map(f => `<tr>
                <td><span class="adm-pill ${RESULT_CLS[f.result] || "free"}">${esc(f.result)}</span></td>
                <td>${esc(f.opponent)}${f.opponent_record ? `<br><span style="color:var(--text-muted);font-size:11px">${esc(f.opponent_record)}</span>` : ""}</td>
                <td style="font-size:12px">${esc(f.event || "")}</td>
                <td style="white-space:nowrap;font-size:12px">${esc(f.event_date || "")}</td>
                <td style="font-size:11px;color:var(--text-muted)">${esc(f.date || "")}</td>
            </tr>`).join("")
            : `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:12px">No fight history recorded.</td></tr>`;

        sec.innerHTML = `
            <div class="adm-fieldset-title" style="margin-top:22px">Fight history (${fights.length})</div>
            <div class="adm-table-wrap" style="margin-bottom:12px">
                <table class="adm-table" style="font-size:12.5px">
                    <thead><tr><th>Res.</th><th>Opponent</th><th>Event</th><th>Date</th><th>Method</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
            <button class="adm-btn sm" id="adm-add-fight-toggle">+ Add missing fight</button>
            <div id="adm-add-fight-form" style="display:none;margin-top:14px"></div>`;

        document.getElementById("adm-add-fight-toggle").addEventListener("click", () => {
            const form = document.getElementById("adm-add-fight-form");
            const visible = form.style.display !== "none";
            form.style.display = visible ? "none" : "block";
            if (!visible) renderAddFightForm(form, fid);
        });
    }

    function renderAddFightForm(form, fid) {
        form.innerHTML = `
            <div class="adm-grid2">
                <div class="adm-field">
                    <label>Result *</label>
                    <select id="af-result">
                        <option value="W">W — Win</option>
                        <option value="L">L — Loss</option>
                        <option value="D">D — Draw</option>
                        <option value="NC">NC — No contest</option>
                    </select>
                </div>
                <div class="adm-field">
                    <label>Opponent *</label>
                    <input id="af-opponent" type="text" placeholder="e.g. Jai Bradney">
                </div>
                <div class="adm-field">
                    <label>Event</label>
                    <input id="af-event" type="text" placeholder="e.g. Roshambo MMA 3">
                </div>
                <div class="adm-field">
                    <label>Date (YYYY-MM-DD)</label>
                    <input id="af-date" type="date">
                </div>
                <div class="adm-field">
                    <label>Method</label>
                    <input id="af-method" type="text" placeholder="e.g. Submission (Rear Naked Choke)">
                </div>
                <div class="adm-field">
                    <label>Round</label>
                    <input id="af-round" type="number" min="1" max="5" placeholder="1">
                </div>
                <div class="adm-field full">
                    <label>Opponent record at fight time</label>
                    <input id="af-oprec" type="text" placeholder="e.g. 6-1">
                </div>
            </div>
            <div style="display:flex;gap:8px;align-items:center;margin-top:10px">
                <button class="adm-btn sm primary" id="af-submit">Save fight</button>
                <span id="af-msg" style="font-size:13px"></span>
            </div>`;

        document.getElementById("af-submit").addEventListener("click", async () => {
            const msg = document.getElementById("af-msg");
            const opponent = document.getElementById("af-opponent").value.trim();
            if (!opponent) { msg.style.color = "#f87171"; msg.textContent = "Opponent is required."; return; }
            const payload = {
                result: document.getElementById("af-result").value,
                opponent,
                event: document.getElementById("af-event").value.trim(),
                event_date: document.getElementById("af-date").value || null,
                method: document.getElementById("af-method").value.trim(),
                round: document.getElementById("af-round").value ? parseInt(document.getElementById("af-round").value) : null,
                opponent_record: document.getElementById("af-oprec").value.trim(),
            };
            msg.style.color = "var(--text-muted)"; msg.textContent = "Saving…";
            try {
                const d = await apiSend(`/api/admin/fighters/${fid}/history/add`, "POST", payload);
                msg.style.color = "#22c55e"; msg.textContent = `Fight added ✓ (${d.count} total)`;
                setTimeout(() => loadFightHistory(fid), 900);
            } catch (e) {
                msg.style.color = "#f87171"; msg.textContent = "Error: " + (e.message || e);
            }
        });
    }

    function wireDrawer() {
        document.getElementById("adm-drawer-close").addEventListener("click", closeDrawerEl);
        document.getElementById("adm-drawer-cancel").addEventListener("click", closeDrawerEl);
        document.getElementById("adm-overlay").addEventListener("click", closeDrawerEl);
        document.getElementById("adm-drawer-save").addEventListener("click", saveFighter);
        document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawerEl(); });
    }
    function openDrawerEl() {
        document.getElementById("adm-overlay").classList.add("show");
        document.getElementById("adm-drawer").classList.add("show");
        document.getElementById("adm-drawer").setAttribute("aria-hidden", "false");
    }
    function closeDrawerEl() {
        document.getElementById("adm-overlay").classList.remove("show");
        document.getElementById("adm-drawer").classList.remove("show");
        document.getElementById("adm-drawer").setAttribute("aria-hidden", "true");
        state.editing = null;
    }

    // ---- Users / VIP --------------------------------------------------------

    async function loadUsers() {
        const s = state.users;
        content().innerHTML = `
            <div class="adm-toolbar">
                <input class="adm-input" id="adm-u-search" placeholder="Search by email, pseudo or name…" value="${esc(s.search)}">
                <select class="adm-select" id="adm-u-tier">
                    <option value="">All tiers</option>
                    <option value="premium"${s.tier === "premium" ? " selected" : ""}>VIP / premium</option>
                    <option value="free"${s.tier === "free" ? " selected" : ""}>Free</option>
                </select>
                <button class="adm-btn primary" id="adm-u-go">Search</button>
            </div>
            <div id="adm-u-results"><div class="adm-loader">Loading…</div></div>`;
        const go = () => {
            s.search = document.getElementById("adm-u-search").value.trim();
            s.tier = document.getElementById("adm-u-tier").value;
            s.page = 1; fetchUsers();
        };
        document.getElementById("adm-u-go").addEventListener("click", go);
        document.getElementById("adm-u-tier").addEventListener("change", go);
        document.getElementById("adm-u-search").addEventListener("keydown", e => { if (e.key === "Enter") go(); });
        fetchUsers();
    }

    async function fetchUsers() {
        const s = state.users;
        const box = document.getElementById("adm-u-results");
        box.innerHTML = `<div class="adm-loader">Loading…</div>`;
        try {
            const qs = new URLSearchParams({ page: s.page, search: s.search, tier: s.tier }).toString();
            const d = await apiGet(`/api/admin/users?${qs}`);
            if (!d.users.length) { box.innerHTML = `<div class="adm-empty">No users found.</div>`; return; }
            const rows = d.users.map(x => {
                const isPrem = x.tier === "premium";
                const adminFlag = x.is_admin ? ` <span class="adm-pill adminflag">admin</span>` : "";
                return `<tr>
                    <td style="color:var(--text-muted)">#${x.id}</td>
                    <td><b>${esc(x.pseudo)}</b>${adminFlag}<br><span style="color:var(--text-muted);font-size:12px">${esc((x.first_name || "") + " " + (x.last_name || ""))}</span></td>
                    <td>${esc(x.email)} ${x.email_verified ? "✓" : `<span style="color:#f59e0b">(unverified)</span>`}</td>
                    <td><span class="adm-pill ${isPrem ? "premium" : "free"}">${esc(x.tier || "free")}</span>
                        ${isPrem && x.premium_until ? `<br><span style="color:var(--text-muted);font-size:11px">until ${fmtDate(x.premium_until)}</span>` : ""}</td>
                    <td>${x.favorites ?? 0}</td>
                    <td style="white-space:nowrap">${fmtDate(x.created_at)}</td>
                    <td style="white-space:nowrap">${x.last_login_at ? fmtDate(x.last_login_at) : "—"}</td>
                    <td>${x.is_admin ? "" : `<button class="adm-btn sm" data-tier="${x.id}" data-to="${isPrem ? "free" : "premium"}">${isPrem ? "Remove VIP" : "Make VIP"}</button>`}</td>
                </tr>`;
            }).join("");
            box.innerHTML = `
                <div class="adm-table-wrap">
                    <table class="adm-table">
                        <thead><tr><th>ID</th><th>User</th><th>Email</th><th>Tier</th><th>Favs</th><th>Joined</th><th>Last login</th><th></th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
                ${pager(d, "users")}`;
            box.querySelectorAll("[data-tier]").forEach(b =>
                b.addEventListener("click", () => toggleTier(b.dataset.tier, b.dataset.to)));
            wirePager(box, "users", fetchUsers);
        } catch (e) { if (e.message !== "admin_session") box.innerHTML = `<div class="adm-error">${esc(e.message)}</div>`; }
    }

    async function toggleTier(userId, to) {
        const label = to === "premium" ? "grant VIP (premium) to" : "remove VIP from";
        if (!confirm(`Confirm: ${label} user #${userId}?`)) return;
        try {
            await apiSend(`/api/admin/users/${userId}/tier`, "PATCH", { tier: to });
            fetchUsers();
        } catch (e) { if (e.message !== "admin_session") alert("Error: " + e.message); }
    }

    // ---- Reports ------------------------------------------------------------

    async function loadReports() {
        const s = state.reports;
        content().innerHTML = `
            <div class="adm-toolbar">
                <select class="adm-select" id="adm-r-status">
                    <option value="open"${s.status === "open" ? " selected" : ""}>Open</option>
                    <option value="resolved"${s.status === "resolved" ? " selected" : ""}>Resolved</option>
                    <option value="all"${s.status === "all" ? " selected" : ""}>All</option>
                </select>
            </div>
            <div id="adm-r-results"><div class="adm-loader">Loading…</div></div>`;
        document.getElementById("adm-r-status").addEventListener("change", e => {
            s.status = e.target.value; fetchReports();
        });
        fetchReports();
    }

    async function fetchReports() {
        const s = state.reports;
        const box = document.getElementById("adm-r-results");
        box.innerHTML = `<div class="adm-loader">Loading…</div>`;
        try {
            const d = await apiGet(`/api/admin/reports?status=${encodeURIComponent(s.status)}`);
            if (!d.reports.length) { box.innerHTML = `<div class="adm-empty">No reports.</div>`; return; }
            const rows = d.reports.map(x => {
                const target = x.fighter_id
                    ? `<a href="fighter.html?id=${x.fighter_id}" style="color:var(--primary-2)">${esc(x.fighter_name || "fighter #" + x.fighter_id)}</a>`
                    : (x.event_id ? `event #${x.event_id}` : "—");
                const open = x.status === "open";
                return `<tr>
                    <td style="color:var(--text-muted)">#${x.id}</td>
                    <td>${target}</td>
                    <td>${esc(x.report_type)}</td>
                    <td style="max-width:320px">${esc(x.message || "")}</td>
                    <td><span class="adm-pill ${open ? "open" : "resolved"}">${esc(x.status)}</span></td>
                    <td style="white-space:nowrap">${fmtDate(x.created_at)}</td>
                    <td><button class="adm-btn sm" data-report="${x.id}" data-to="${open ? "resolved" : "open"}">${open ? "Resolve" : "Reopen"}</button></td>
                </tr>`;
            }).join("");
            box.innerHTML = `
                <div class="adm-table-wrap">
                    <table class="adm-table">
                        <thead><tr><th>ID</th><th>Target</th><th>Type</th><th>Message</th><th>Status</th><th>Date</th><th></th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>`;
            box.querySelectorAll("[data-report]").forEach(b =>
                b.addEventListener("click", () => setReport(b.dataset.report, b.dataset.to)));
        } catch (e) { if (e.message !== "admin_session") box.innerHTML = `<div class="adm-error">${esc(e.message)}</div>`; }
    }

    async function setReport(id, to) {
        try {
            await apiSend(`/api/admin/reports/${id}`, "PATCH", { status: to });
            fetchReports();
        } catch (e) { if (e.message !== "admin_session") alert("Error: " + e.message); }
    }

    // ---- Helpers UI ---------------------------------------------------------

    function pager(d) {
        if (!d.pages || d.pages <= 1) return "";
        return `<div class="adm-pager">
            <button class="adm-btn sm" data-pg="prev" ${d.page <= 1 ? "disabled" : ""}>← Prev</button>
            <span>Page ${d.page} / ${d.pages} · ${d.total} total</span>
            <button class="adm-btn sm" data-pg="next" ${d.page >= d.pages ? "disabled" : ""}>Next →</button>
        </div>`;
    }
    function wirePager(box, kind, reload) {
        box.querySelectorAll("[data-pg]").forEach(b => b.addEventListener("click", () => {
            if (b.dataset.pg === "prev") state[kind].page = Math.max(1, state[kind].page - 1);
            else state[kind].page += 1;
            reload();
        }));
    }
    function fmtDate(iso) {
        if (!iso) return "—";
        try { return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }); }
        catch { return String(iso).slice(0, 10); }
    }

    return { init };
})();
