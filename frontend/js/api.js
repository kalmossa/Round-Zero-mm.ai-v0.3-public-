// MM.AI - Client API
// Si on ouvre le front via Flask (http://localhost:5000) -> relative URLs
// Si on l'ouvre via file:// ou autre serveur -> hardcode l'URL ici.
const API_BASE = (() => {
    if (location.protocol === "file:") return "http://localhost:5000";
    return ""; // meme origine
})();

const api = {
    async _fetch(path) {
        const r = await fetch(`${API_BASE}${path}`);
        if (!r.ok) {
            const detail = await r.text().catch(() => "");
            throw new Error(`API ${r.status} - ${detail || r.statusText}`);
        }
        return r.json();
    },
    health()              { return api._fetch("/api/health"); },
    stats()               { return api._fetch("/api/stats"); },
    weightClasses()       { return api._fetch("/api/weight-classes"); },
    // Liste canonique GENREE (page Fighters) : tokens "base|gender" + counts.
    weightClassesGendered() { return api._fetch("/api/weight-classes?gendered=1"); },
    top()                 { return api._fetch("/api/top"); },
    fighters(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return api._fetch(`/api/fighters${qs ? "?" + qs : ""}`);
    },
    fighter(id)           { return api._fetch(`/api/fighters/${id}`); },
    fighterHistory(id)    { return api._fetch(`/api/fighters/${id}/history`); },
    scouter(id)           { return api._fetch(`/api/fighters/${id}/scouter`); },
    rankings(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return api._fetch(`/api/rankings${qs ? "?" + qs : ""}`);
    },
    champions()           { return api._fetch("/api/champions"); },
    rankingsOverview()    { return api._fetch("/api/rankings/overview"); },
    divisionRanking(wc, gender) { return api._fetch(`/api/rankings/division?wc=${encodeURIComponent(wc)}&gender=${gender}`); },
    p4pRankings()         { return api._fetch("/api/rankings/p4p"); },
    divisions()           { return api._fetch("/api/divisions"); },
    analytics()           { return api._fetch("/api/analytics"); },
    async backtest() {
        // 503 = rapport pas encore genere : on retourne le JSON (pas d'exception)
        const r = await fetch(`${API_BASE}/api/backtest`);
        if (!r.ok && r.status !== 503) {
            const detail = await r.text().catch(() => "");
            throw new Error(`API ${r.status} - ${detail || r.statusText}`);
        }
        return r.json();
    },
    countries()           { return api._fetch("/api/countries"); },
    predict(id1, id2)     { return api._fetch(`/api/predict?id1=${id1}&id2=${id2}`); },
    async matchmaking(id1, id2, fightClass = null) {
        // 422 = division_too_far : retourne le JSON (pas d'exception) pour affichage cote front
        let url = `${API_BASE}/api/matchmaking?id1=${id1}&id2=${id2}`;
        if (fightClass) url += `&fight_class=${encodeURIComponent(fightClass)}`;
        const r = await fetch(url);
        if (!r.ok && r.status !== 422) {
            const detail = await r.text().catch(() => "");
            throw new Error(`API ${r.status} - ${detail || r.statusText}`);
        }
        return r.json();
    },
    // Analyse de combat redigee par IA (LLM) + % de fiabilite.
    // Endpoint separe de /matchmaking : la page s'affiche vite, l'analyse se
    // charge ensuite (l'appel LLM prend 1-3s).
    matchmakingAnalysis(id1, id2) {
        const lang = (window.MMAILang && window.MMAILang.get) ? window.MMAILang.get() : "en";
        return api._fetch(`/api/matchmaking/analysis?id1=${id1}&id2=${id2}&lang=${lang}`);
    },
    events(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return api._fetch(`/api/events${qs ? "?" + qs : ""}`);
    },
    event(id)         { return api._fetch(`/api/events/${id}`); },
    eventBySlug(slug) { return api._fetch(`/api/events/slug/${slug}`); },
    upcomingEvent()   { return api.events({ status: "upcoming", promotion: "UFC", sort: "asc", limit: 1 }); },
    lastEvent(promotion = "UFC") { return api._fetch(`/api/events/last?promotion=${encodeURIComponent(promotion)}`); },
};
