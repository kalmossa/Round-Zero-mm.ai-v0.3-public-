// MM.AI - login.js (Slice 1B)
// Soumet le form a /api/auth/login, stocke le JWT, redirige vers l'accueil.

(function () {
    function $(sel) { return document.querySelector(sel); }

    function showError(msg) {
        const box = $("#login-error");
        if (!box) return;
        box.textContent = msg;
        box.hidden = false;
    }
    function clearError() {
        const box = $("#login-error");
        if (box) { box.hidden = true; box.textContent = ""; }
    }

    function _tt(key, fallback) {
        return (typeof t === "function") ? t(key) : fallback;
    }

    document.addEventListener("DOMContentLoaded", () => {
        const form = $("#login-form");
        if (!form) return;

        // Deja connecte ? redirection vers home
        if (window.MMAIAuth && window.MMAIAuth.isLoggedIn()) {
            location.href = "index.html";
            return;
        }

        // Banniere "email verifie" si on arrive depuis le lien email (?verified=1)
        const params = new URLSearchParams(location.search);
        if (params.get("verified") === "1") {
            const banner = $("#login-banner-verified");
            if (banner) banner.hidden = false;
        }

        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            clearError();

            const email = $("#login-id").value.trim();
            const password = $("#login-password").value;
            if (!email || !password) {
                showError(_tt("auth.err.required", "Both fields are required"));
                return;
            }

            const btn = $("#login-submit");
            const originalLabel = btn.textContent;
            btn.disabled = true;
            btn.textContent = _tt("auth.submitting", "Signing in...");

            try {
                const resp = await fetch("/api/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ identifier: email, password }),
                });
                const body = await resp.json().catch(() => ({}));

                if (resp.ok && body.ok && body.token) {
                    window.MMAIAuth.setSession(body.token, body.user);
                    // Redirect : on prefere ?next= si fourni, sinon home
                    const next = params.get("next");
                    location.href = next && /^[a-z0-9_.\-]+\.html(?:\?.*)?$/i.test(next)
                        ? next
                        : "index.html";
                    return;
                }

                if (body.error === "email_not_verified") {
                    showError(_tt("auth.err.email_not_verified", "Please verify your email before signing in."));
                } else if (body.error === "invalid_credentials") {
                    showError(_tt("auth.err.invalid_credentials", "Invalid email/username or password."));
                } else if (body.error === "missing_credentials") {
                    showError(_tt("auth.err.required", "Both fields are required"));
                } else {
                    showError(_tt("auth.err.server", "Server error. Please try again later."));
                }
            } catch (err) {
                showError(_tt("auth.err.network", "Network error. Please try again."));
            } finally {
                btn.disabled = false;
                btn.textContent = originalLabel;
            }
        });
    });
})();
