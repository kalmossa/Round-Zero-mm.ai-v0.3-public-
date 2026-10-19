// MM.AI - Auth client-side (Slice 1B)
// API publique sur `window.MMAIAuth` :
//   getToken()           -> string|null
//   currentUser()        -> {id, pseudo, first_name, ...}|null
//   isLoggedIn()         -> bool
//   setSession(token, user)
//   clearSession()
//   authFetch(url, opts) -> fetch wrapper qui ajoute Authorization: Bearer
//   refreshMe()          -> GET /api/auth/me, met a jour le user cache
//
// Evenement dispatch sur window : "mmai:auth-change" quand login/logout.
// Nav injection : setupAuthNav() (idempotent) — appele depuis app.js::setupNavSearch.

(function () {
    const TOKEN_KEY = "mmai-jwt";
    const USER_KEY  = "mmai-user";

    function _safeGet(k) {
        try { return localStorage.getItem(k); } catch { return null; }
    }
    function _safeSet(k, v) {
        try { localStorage.setItem(k, v); } catch {}
    }
    function _safeDel(k) {
        try { localStorage.removeItem(k); } catch {}
    }

    function getToken() {
        return _safeGet(TOKEN_KEY);
    }

    function currentUser() {
        const raw = _safeGet(USER_KEY);
        if (!raw) return null;
        try { return JSON.parse(raw); } catch { return null; }
    }

    function isLoggedIn() {
        return !!getToken();
    }

    function setSession(token, user) {
        if (token) _safeSet(TOKEN_KEY, token);
        if (user)  _safeSet(USER_KEY, JSON.stringify(user));
        window.dispatchEvent(new CustomEvent("mmai:auth-change", { detail: { loggedIn: true, user } }));
    }

    function clearSession() {
        _safeDel(TOKEN_KEY);
        _safeDel(USER_KEY);
        window.dispatchEvent(new CustomEvent("mmai:auth-change", { detail: { loggedIn: false } }));
    }

    async function authFetch(url, opts = {}) {
        const token = getToken();
        const headers = Object.assign({}, opts.headers || {});
        if (token) headers["Authorization"] = `Bearer ${token}`;
        if (opts.body && !headers["Content-Type"] && typeof opts.body === "string") {
            headers["Content-Type"] = "application/json";
        }
        const resp = await fetch(url, Object.assign({}, opts, { headers }));
        // Token expire / invalide -> on nettoie et on emet l'event
        if (resp.status === 401) {
            clearSession();
        }
        return resp;
    }

    async function refreshMe() {
        if (!isLoggedIn()) return null;
        try {
            const resp = await authFetch("/api/auth/me");
            if (!resp.ok) return null;
            const user = await resp.json();
            _safeSet(USER_KEY, JSON.stringify(user));
            window.dispatchEvent(new CustomEvent("mmai:auth-change", { detail: { loggedIn: true, user } }));
            return user;
        } catch {
            return null;
        }
    }

    // ---- Nav injection -----------------------------------------------------

    function _initials(s) {
        if (!s) return "?";
        return s.trim().slice(0, 1).toUpperCase();
    }

    function _tt(key, fallback) {
        return (typeof t === "function") ? t(key) : fallback;
    }

    function setupAuthNav() {
        const navInner = document.querySelector(".nav-inner");
        if (!navInner || navInner.dataset.authInjected) return;
        navInner.dataset.authInjected = "1";

        const wrap = document.createElement("div");
        wrap.className = "nav-auth";

        // On regroupe dans le rightCluster comme setupSettingsNav
        let rightCluster = navInner.querySelector(".nav-right-cluster");
        if (!rightCluster) {
            const searchWrap = navInner.querySelector(".nav-search");
            if (searchWrap) {
                rightCluster = document.createElement("div");
                rightCluster.className = "nav-right-cluster";
                searchWrap.parentNode.insertBefore(rightCluster, searchWrap);
                rightCluster.appendChild(searchWrap);
            }
        }
        if (rightCluster) {
            // Insere AVANT le bouton settings (le settings gear est ajoute ensuite)
            rightCluster.insertBefore(wrap, rightCluster.firstChild?.nextSibling || null);
        } else {
            navInner.appendChild(wrap);
        }

        const render = () => {
            const user = currentUser();
            if (user) {
                const avatarContent = user.avatar_data
                    ? `<img src="${user.avatar_data.replace(/[<>"]/g, "")}" alt="" class="nav-auth-avatar-img">`
                    : _initials(user.first_name || user.pseudo);
                // Etat connecte : chip avec initiale + menu
                wrap.innerHTML = `
                    <button type="button" class="nav-auth-chip" aria-haspopup="menu" aria-expanded="false">
                        <span class="nav-auth-avatar${user.avatar_data ? " has-img" : ""}">${avatarContent}</span>
                        <span class="nav-auth-name">${(user.first_name || user.pseudo || "").replace(/[<>]/g, "")}</span>
                        <svg class="nav-auth-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                    </button>
                    <div class="nav-auth-panel" role="menu">
                        <div class="nav-auth-user">
                            <div class="nau-name">${(user.first_name || "") + " " + (user.last_name || "")}</div>
                            <div class="nau-email">${(user.email || "").replace(/[<>]/g, "")}</div>
                            <div class="nau-tier ${user.tier === "premium" ? "premium" : "free"}">${(user.tier || "free").toUpperCase()}</div>
                        </div>
                        <a href="profile.html" class="nav-auth-item" data-i18n="nav.my_profile">My profile</a>
                        <a href="favorites.html" class="nav-auth-item" data-i18n="nav.my_favorites">★ My favorite fighters</a>
                        <a href="settings.html" class="nav-auth-item" data-i18n="nav.all_settings">All settings</a>
                        <div class="nav-auth-divider"></div>
                        <button type="button" class="nav-auth-item danger" data-action="logout" data-i18n="nav.sign_out">Sign out</button>
                    </div>
                `;
                if (typeof applyTranslations === "function") applyTranslations();
                wrap.querySelector('[data-action="logout"]').addEventListener("click", async () => {
                    try { await authFetch("/api/auth/logout", { method: "POST" }); } catch {}
                    clearSession();
                    // Reload pour repartir sur un etat propre (au cas ou la page courante
                    // dependait d'un user authentifie).
                    location.href = "index.html";
                });
            } else {
                // Etat invite : bouton "Sign in" + lien "Sign up"
                wrap.innerHTML = `
                    <a href="login.html" class="nav-auth-btn" data-i18n="nav.sign_in_btn">Sign in</a>
                `;
                if (typeof applyTranslations === "function") applyTranslations();
            }
        };

        render();
        window.addEventListener("mmai:auth-change", render);
        window.addEventListener("mmai:lang-change", render);
    }

    // Public API
    window.MMAIAuth = {
        getToken, currentUser, isLoggedIn,
        setSession, clearSession, authFetch, refreshMe,
        setupAuthNav,
    };

    // Auto-inject on DOM ready si une nav existe
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setupAuthNav);
    } else {
        setupAuthNav();
    }
})();
