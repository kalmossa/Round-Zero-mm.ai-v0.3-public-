// MM.AI - register.js (Slice 1B)
// Soumet le form a /api/auth/register, redirige vers verify-email.html en cas
// de succes (avec ?email=xxx pour afficher l'adresse).

(function () {
    function $(sel) { return document.querySelector(sel); }

    function showError(msg) {
        const box = $("#register-error");
        if (!box) return;
        box.textContent = msg;
        box.hidden = false;
    }

    function clearError() {
        const box = $("#register-error");
        if (box) { box.hidden = true; box.textContent = ""; }
    }

    function _tt(key, fallback) {
        return (typeof t === "function") ? t(key) : fallback;
    }

    function validateClientSide(data) {
        if (!data.first_name) return _tt("auth.err.required", "First name is required");
        if (!data.last_name)  return _tt("auth.err.required", "Last name is required");
        if (!/^[a-zA-Z0-9_]{3,20}$/.test(data.pseudo || "")) {
            return _tt("auth.err.pseudo_invalid", "Username must be 3-20 chars (letters, digits, underscore)");
        }
        const age = parseInt(data.age, 10);
        if (Number.isNaN(age) || age < 13 || age > 120) {
            return _tt("auth.err.age_invalid", "Age must be between 13 and 120");
        }
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email || "")) {
            return _tt("auth.err.email_invalid", "Invalid email format");
        }
        if ((data.password || "").length < 8) {
            return _tt("auth.err.password_too_short", "Password must be at least 8 characters");
        }
        if (data.password !== data.password2) {
            return _tt("auth.err.passwords_mismatch", "Passwords don't match");
        }
        return null;
    }

    document.addEventListener("DOMContentLoaded", () => {
        const form = $("#register-form");
        if (!form) return;

        // Si l'utilisateur est deja connecte, on le redirige vers l'accueil
        if (window.MMAIAuth && window.MMAIAuth.isLoggedIn()) {
            location.href = "index.html";
            return;
        }

        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            clearError();

            const data = {
                first_name: $("#reg-first").value.trim(),
                last_name:  $("#reg-last").value.trim(),
                pseudo:     $("#reg-pseudo").value.trim(),
                age:        $("#reg-age").value.trim(),
                email:      $("#reg-email").value.trim().toLowerCase(),
                password:   $("#reg-password").value,
                password2:  $("#reg-password2").value,
            };

            const clientErr = validateClientSide(data);
            if (clientErr) { showError(clientErr); return; }

            const btn = $("#register-submit");
            const originalLabel = btn.textContent;
            btn.disabled = true;
            btn.textContent = _tt("auth.submitting", "Submitting...");

            try {
                const payload = { ...data };
                delete payload.password2;
                payload.age = parseInt(payload.age, 10);

                const resp = await fetch("/api/auth/register", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });
                const body = await resp.json().catch(() => ({}));

                if (resp.status === 201 && body.ok) {
                    location.href = `verify-email.html?email=${encodeURIComponent(data.email)}`;
                    return;
                }

                // Erreurs metier
                if (body.error === "email_taken") {
                    showError(_tt("auth.err.email_taken", "This email is already registered."));
                } else if (body.error === "pseudo_taken") {
                    showError(_tt("auth.err.pseudo_taken", "This username is already taken."));
                } else if (body.error === "validation") {
                    showError(body.detail || _tt("auth.err.validation", "Validation error."));
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
