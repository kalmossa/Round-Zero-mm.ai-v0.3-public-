// MM.AI - Frontend (vanilla JS) - logique partagee

// ---- Theme (light / dark) — appliqué le plus tôt possible -------------------
// On expose window.MMAITheme pour que la page Settings puisse le piloter.
(function bootstrapTheme() {
    const KEY = "mmai-theme";
    const root = document.documentElement;
    const getStored = () => {
        try { return localStorage.getItem(KEY); } catch (e) { return null; }
    };
    const apply = (theme) => {
        if (theme === "light") root.setAttribute("data-theme", "light");
        else root.removeAttribute("data-theme");
    };
    const set = (theme) => {
        try { localStorage.setItem(KEY, theme); } catch (e) {}
        apply(theme);
        window.dispatchEvent(new CustomEvent("mmai:theme-change", { detail: { theme } }));
    };
    const get = () => getStored() === "light" ? "light" : "dark";
    apply(get());
    window.MMAITheme = { get, set };
})();

// ---- Preferences UI (densite, unites, accent, division par defaut) ---------
// Stockees en local (mmai-prefs-ui), totalement separees du compte. On expose
// window.MMAIPrefs pour que la page Settings pilote tout ca. Applique le plus
// tot possible pour limiter le flash (l'accent = juste des variables CSS).
(function bootstrapPrefs() {
    const KEY = "mmai-prefs-ui";
    const root = document.documentElement;

    // Palette d'accents : chaque preset redefinit --primary / --primary-2 et le
    // -dim derive (rgba). "red" = defaut historique UFC -> on n'override rien.
    // Palette ordonnee chaud -> froid pour une rangee de pastilles agreable.
    const ACCENTS = {
        red:     { label: "UFC Red",  p: "#d20a11", p2: "#ff2730", rgb: "210,10,17" },
        crimson: { label: "Crimson",  p: "#e11d48", p2: "#fb7185", rgb: "225,29,72" },
        rose:    { label: "Rose",     p: "#db2777", p2: "#f472b6", rgb: "219,39,119" },
        orange:  { label: "Orange",   p: "#ea580c", p2: "#fb923c", rgb: "234,88,12" },
        gold:    { label: "Gold",     p: "#d98a09", p2: "#f5a623", rgb: "217,138,9" },
        lime:    { label: "Lime",     p: "#65a30d", p2: "#a3e635", rgb: "101,163,13" },
        emerald: { label: "Emerald",  p: "#0f9d6b", p2: "#22c55e", rgb: "15,157,107" },
        teal:    { label: "Teal",     p: "#0d9488", p2: "#2dd4bf", rgb: "13,148,136" },
        cyan:    { label: "Cyan",     p: "#0891b2", p2: "#22d3ee", rgb: "8,145,178" },
        azure:   { label: "Azure",    p: "#2563eb", p2: "#3b82f6", rgb: "37,99,235" },
        indigo:  { label: "Indigo",   p: "#4f46e5", p2: "#818cf8", rgb: "79,70,229" },
        violet:  { label: "Violet",   p: "#7c3aed", p2: "#a78bfa", rgb: "124,58,237" },
    };

    const DEFAULTS = { density: "normal", units: "imperial", accent: "red" };

    const load = () => {
        try { return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(KEY) || "{}")); }
        catch (e) { return Object.assign({}, DEFAULTS); }
    };
    let prefs = load();

    const applyAccent = (key) => {
        const a = ACCENTS[key] || ACCENTS.red;
        if (key === "red") {
            root.style.removeProperty("--primary");
            root.style.removeProperty("--primary-2");
            root.style.removeProperty("--primary-dim");
        } else {
            root.style.setProperty("--primary", a.p);
            root.style.setProperty("--primary-2", a.p2);
            root.style.setProperty("--primary-dim", `rgba(${a.rgb}, 0.15)`);
        }
    };

    const apply = () => {
        if (prefs.density && prefs.density !== "normal") root.setAttribute("data-density", prefs.density);
        else root.removeAttribute("data-density");
        applyAccent(prefs.accent);
    };

    const get = (k) => (k ? prefs[k] : Object.assign({}, prefs));
    const set = (k, v) => {
        prefs[k] = v;
        try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch (e) {}
        apply();
        window.dispatchEvent(new CustomEvent("mmai:prefs-change", { detail: { key: k, value: v } }));
    };

    apply();
    window.MMAIPrefs = { get, set, accents: ACCENTS };
})();

// ---- Menu mobile (hamburger) — injecté une fois sur chaque page ------------
// Le header est dupliqué dans chaque .html ; plutôt que d'éditer 20 fichiers,
// on injecte le bouton + le comportement ici (app.js est chargé partout).
(function setupMobileNav() {
    function init() {
        document.querySelectorAll(".navbar .nav-inner").forEach(inner => {
            if (inner.querySelector(".nav-toggle")) return;       // idempotent
            const links = inner.querySelector(".nav-links");
            if (!links) return;
            const btn = document.createElement("button");
            btn.className = "nav-toggle";
            btn.type = "button";
            btn.setAttribute("aria-label", "Menu");
            btn.setAttribute("aria-expanded", "false");
            btn.innerHTML = "<span></span><span></span><span></span>";
            const setOpen = (open) => {
                links.classList.toggle("open", open);
                btn.classList.toggle("open", open);
                btn.setAttribute("aria-expanded", open ? "true" : "false");
            };
            btn.addEventListener("click", () => setOpen(!links.classList.contains("open")));
            // Referme quand on clique un lien
            links.addEventListener("click", e => { if (e.target.closest("a")) setOpen(false); });
            // Referme au clic en dehors
            document.addEventListener("click", e => {
                if (!inner.contains(e.target)) setOpen(false);
            });
            inner.appendChild(btn);
        });
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();

// on re-applique les traductions statiques des que la langue active change
window.addEventListener("mmai:lang-change", () => {
    if (typeof applyTranslations === "function") applyTranslations();
    // on rafraichit le texte de la bio du fighter dans la nouvelle langue
    document.querySelectorAll("[data-bio-note]").forEach(el => {
        try {
            const langs = JSON.parse(el.dataset.noteLangs || "{}");
            const lang = window.MMAILang ? window.MMAILang.get() : "en";
            const text = langs[lang] || langs.en || langs.fr || el.dataset.fallback || "";
            if (text) el.textContent = text;
        } catch (e) { /* le parse JSON a foiré, on laisse tel quel */ }
    });
});

// ---- Utils ------------------------------------------------------------------

const $  = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));

const esc = (s) => {
    if (s === null || s === undefined) return "";
    return String(s)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
};

const num = (v, fallback = "--") => (v === null || v === undefined || v === "" ? fallback : v);

const fmtNumber = (v, decimals = 0) => {
    if (v === null || v === undefined || v === "") return "--";
    const n = Number(v);
    if (Number.isNaN(n)) return "--";
    // Locale en-US : separateur de milliers = virgule, decimal = point.
    return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
};

const initials = (name) => {
    if (!name) return "?";
    return name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join("");
};

const debounce = (fn, ms = 250) => {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
};

function getQueryParam(name) {
    return new URLSearchParams(location.search).get(name);
}

function showError(target, msg) {
    target.innerHTML = `<div class="error-box">Error: ${esc(msg)}</div>`;
}

// Weight class formatting (HELPERS GLOBAUX)
// Convention site MM.AI :
//   Long :  "Bantamweight"           (men)  ·  "Bantamweight (W)"        (women)
//   Short : "BW"                     (men)  ·  "BW W"                    (women)
// On nettoie systematiquement les variantes brutes type
//   "Women's Bantamweight W" / "Women Bantamweight" / "Bantamweight W" /
//   "Women's Flyweight" → key = "bantamweight"|"flyweight", gender = "W"
// Resultat : un SEUL libelle coherent partout dans le site.
const WC_ABBREV_MAP = {
    "atomweight": "AW", "strawweight": "SW", "flyweight": "FLW",
    "bantamweight": "BW", "featherweight": "FTW", "lightweight": "LW",
    "welterweight": "WW", "middleweight": "MW", "light heavyweight": "LHW",
    "cruiserweight": "CW", "heavyweight": "HW", "super heavyweight": "SHW",
    "super lightweight": "SLW", "super welterweight": "SWW",
};
const WC_PROPER_MAP = {
    "atomweight": "Atomweight", "strawweight": "Strawweight",
    "flyweight": "Flyweight", "bantamweight": "Bantamweight",
    "featherweight": "Featherweight", "lightweight": "Lightweight",
    "welterweight": "Welterweight", "middleweight": "Middleweight",
    "light heavyweight": "Light Heavyweight",
    "cruiserweight": "Cruiserweight", "heavyweight": "Heavyweight",
    "super heavyweight": "Super Heavyweight",
    "super lightweight": "Super Lightweight",
    "super welterweight": "Super Welterweight",
};

function parseWC(raw, genderHint) {
    if (!raw) return { key: "", gender: (genderHint === "F" ? "W" : "M") };
    let s = String(raw).toLowerCase();
    // Detection genre depuis le label brut
    let gender = "M";
    if (/^women['']?s?\b/.test(s) || /\bwomen['']?s?\s+\w/.test(s) || /\s+w\s*$/.test(s)) {
        gender = "W";
    }
    if (genderHint === "F" || genderHint === "W") gender = "W";
    // Nettoyage : on retire les marqueurs de genre pour avoir la cle pure
    s = s.replace(/women['']?s?\s*/g, "")
         .replace(/\s+\b[wm]\s*$/g, "")
         .trim();
    return { key: s, gender };
}

// "Bantamweight"   (men)  ·  "Bantamweight (W)"   (women)
function formatWeightClassLong(raw, genderHint) {
    const { key, gender } = parseWC(raw, genderHint);
    if (!key) return "";
    const proper = WC_PROPER_MAP[key] || raw;
    return gender === "W" ? `${proper} (W)` : proper;
}

// "BW"   (men)  ·  "BW W"   (women)
function formatWeightClassShort(raw, genderHint) {
    const { key, gender } = parseWC(raw, genderHint);
    if (!key) return "";
    const abbrev = WC_ABBREV_MAP[key] || raw;
    return gender === "W" ? `${abbrev} W` : abbrev;
}

/**
 * Formate "Inactive since" -> "2025-11-15 (6 months)" / "2024-04-12 (1y 7m)".
 * Si pas de date de dernier combat, renvoie "--".
 */
function formatInactiveSince(lastFightDate, daysInactive) {
    if (!lastFightDate) return "--";
    // Pretty duration
    let pretty = "";
    if (daysInactive != null) {
        const d = Number(daysInactive);
        if (!Number.isNaN(d)) {
            if (d < 31)        pretty = `${d} day${d > 1 ? "s" : ""}`;
            else if (d < 365)  pretty = `${Math.round(d / 30)} month${Math.round(d / 30) > 1 ? "s" : ""}`;
            else {
                const y = Math.floor(d / 365);
                const m = Math.round((d % 365) / 30);
                pretty = m > 0 ? `${y}y ${m}m` : `${y}y`;
            }
        }
    }
    return pretty ? `${esc(lastFightDate)} <span class="muted">(${pretty})</span>` : esc(lastFightDate);
}

// le drapeau emoji depuis le nom du pays -------------------------------------------
// Couvre les nationalites les plus frequentes en MMA. ISO 3166-1 alpha-2.
// Accepte FR et EN pour les pays qui ont des noms differents.
const COUNTRY_TO_ISO = {
    "united states": "US", "usa": "US", "etats-unis": "US", "états-unis": "US", "american": "US",
    "brazil": "BR", "bresil": "BR", "brésil": "BR", "brazilian": "BR",
    "russia": "RU", "russie": "RU", "russian": "RU",
    "ireland": "IE", "irlande": "IE", "irish": "IE",
    "england": "GB", "united kingdom": "GB", "uk": "GB", "great britain": "GB", "scotland": "GB", "wales": "GB",
    "france": "FR", "french": "FR",
    "canada": "CA", "canadian": "CA",
    "mexico": "MX", "mexique": "MX", "mexican": "MX",
    "australia": "AU", "australie": "AU", "australian": "AU",
    "new zealand": "NZ", "nouvelle-zelande": "NZ", "nouvelle-zélande": "NZ",
    "japan": "JP", "japon": "JP", "japanese": "JP",
    "china": "CN", "chine": "CN", "chinese": "CN",
    "south korea": "KR", "corée du sud": "KR", "coree du sud": "KR", "korean": "KR",
    "north korea": "KP",
    "kazakhstan": "KZ", "kazakh": "KZ",
    "kyrgyzstan": "KG", "kirghizistan": "KG", "kyrgyz": "KG",
    "uzbekistan": "UZ", "ouzbekistan": "UZ", "ouzbékistan": "UZ",
    "tajikistan": "TJ",
    "georgia": "GE", "géorgie": "GE", "georgie": "GE",
    "armenia": "AM", "armenie": "AM", "arménie": "AM",
    "azerbaijan": "AZ", "azerbaidjan": "AZ", "azerbaïdjan": "AZ",
    "dagestan": "RU", "chechnya": "RU", "tchetchenie": "RU", "tchétchénie": "RU",
    "ukraine": "UA", "ukrainian": "UA",
    "poland": "PL", "pologne": "PL", "polish": "PL",
    "germany": "DE", "allemagne": "DE", "german": "DE",
    "netherlands": "NL", "pays-bas": "NL", "dutch": "NL", "holland": "NL",
    "belgium": "BE", "belgique": "BE", "belgian": "BE",
    "sweden": "SE", "suede": "SE", "suède": "SE", "swedish": "SE",
    "norway": "NO", "norvege": "NO", "norvège": "NO",
    "denmark": "DK", "danemark": "DK",
    "finland": "FI", "finlande": "FI",
    "iceland": "IS", "islande": "IS",
    "spain": "ES", "espagne": "ES", "spanish": "ES",
    "portugal": "PT", "portuguese": "PT",
    "italy": "IT", "italie": "IT", "italian": "IT",
    "switzerland": "CH", "suisse": "CH", "swiss": "CH",
    "austria": "AT", "autriche": "AT",
    "croatia": "HR", "croatie": "HR", "croatian": "HR",
    "serbia": "RS", "serbie": "RS", "serbian": "RS",
    "bulgaria": "BG", "bulgarie": "BG",
    "romania": "RO", "roumanie": "RO",
    "greece": "GR", "grece": "GR", "grèce": "GR",
    "turkey": "TR", "turquie": "TR", "turkish": "TR",
    "iran": "IR", "iranian": "IR",
    "iraq": "IQ", "irak": "IQ", "iraqi": "IQ",
    "israel": "IL", "israël": "IL",
    "lebanon": "LB", "liban": "LB",
    "syria": "SY", "syrie": "SY", "syrian": "SY",
    "jordan": "JO", "jordanie": "JO",
    "saudi arabia": "SA", "arabie saoudite": "SA",
    "united arab emirates": "AE", "uae": "AE", "emirats": "AE", "émirats": "AE", "emirats arabes unis": "AE",
    "qatar": "QA",
    "kuwait": "KW", "koweit": "KW", "koweït": "KW",
    "bahrain": "BH", "bahrein": "BH", "bahreïn": "BH",
    "oman": "OM",
    "yemen": "YE", "yémen": "YE",
    "afghanistan": "AF", "afghan": "AF",
    "morocco": "MA", "maroc": "MA", "moroccan": "MA",
    "tunisia": "TN", "tunisie": "TN",
    "algeria": "DZ", "algerie": "DZ", "algérie": "DZ",
    "egypt": "EG", "egypte": "EG", "égypte": "EG",
    "nigeria": "NG", "nigerian": "NG",
    "south africa": "ZA", "afrique du sud": "ZA",
    "cameroon": "CM", "cameroun": "CM",
    "ghana": "GH",
    "kenya": "KE",
    "ethiopia": "ET",
    "india": "IN", "inde": "IN", "indian": "IN",
    "pakistan": "PK", "pakistani": "PK",
    "bangladesh": "BD",
    "thailand": "TH", "thailande": "TH", "thaïlande": "TH", "thai": "TH",
    "vietnam": "VN", "vietnamese": "VN",
    "philippines": "PH", "filipino": "PH",
    "indonesia": "ID", "indonesie": "ID", "indonésie": "ID",
    "malaysia": "MY", "malaisie": "MY",
    "singapore": "SG", "singapour": "SG",
    "myanmar": "MM", "burma": "MM", "birmanie": "MM", "burmese": "MM",
    "cambodia": "KH", "cambodge": "KH",
    "laos": "LA", "lao": "LA",
    "nepal": "NP", "nepalese": "NP",
    "sri lanka": "LK", "mongolia": "MN", "mongolie": "MN",
    "taiwan": "TW", "taïwan": "TW",
    "hong kong": "HK",
    "argentina": "AR", "argentine": "AR",
    "chile": "CL", "chili": "CL",
    "colombia": "CO", "colombie": "CO",
    "peru": "PE", "perou": "PE", "pérou": "PE",
    "venezuela": "VE",
    "ecuador": "EC", "equateur": "EC", "équateur": "EC",
    "uruguay": "UY",
    "bolivia": "BO", "bolivie": "BO",
    "cuba": "CU", "cuban": "CU",
    "jamaica": "JM", "jamaique": "JM", "jamaïque": "JM",
    "dominican republic": "DO", "republique dominicaine": "DO", "république dominicaine": "DO",
    "puerto rico": "PR",
    "panama": "PA", "panamanian": "PA",
    "costa rica": "CR",
    "guatemala": "GT",
    "honduras": "HN",
    "el salvador": "SV", "salvador": "SV",
    "nicaragua": "NI",
    "haiti": "HT", "haïti": "HT",
    "paraguay": "PY",
    "moldova": "MD", "moldavie": "MD",
    "belarus": "BY", "bielorussie": "BY", "biélorussie": "BY",
    "estonia": "EE", "estonie": "EE",
    "latvia": "LV", "lettonie": "LV",
    "lithuania": "LT", "lituanie": "LT",
    "slovakia": "SK", "slovaquie": "SK",
    "slovenia": "SI", "slovenie": "SI", "slovénie": "SI",
    "czech republic": "CZ", "republique tcheque": "CZ", "république tchèque": "CZ", "czechia": "CZ",
    "hungary": "HU", "hongrie": "HU", "hungarian": "HU",
    "bosnia": "BA", "bosnie": "BA", "bosnia and herzegovina": "BA",
    "albania": "AL", "albanie": "AL",
    "north macedonia": "MK", "macedoine": "MK", "macédoine": "MK",
    "montenegro": "ME",
    "kosovo": "XK",
    "cyprus": "CY", "chypre": "CY",
    "malta": "MT", "malte": "MT",
    "luxembourg": "LU",
    "monaco": "MC",
    "iceland": "IS", "islande": "IS",
    "ireland": "IE",
    "north ireland": "GB", "northern ireland": "GB",
    "guyana": "GY", "guyane": "GY",
    "suriname": "SR",
    "trinidad and tobago": "TT", "trinidad": "TT",
    "barbados": "BB",
    "bahamas": "BS",
    "senegal": "SN", "sénégal": "SN",
    "ivory coast": "CI", "cote d'ivoire": "CI", "côte d'ivoire": "CI",
    "mali": "ML",
    "uganda": "UG", "ouganda": "UG",
    "tanzania": "TZ", "tanzanie": "TZ",
    "zimbabwe": "ZW",
    "angola": "AO",
    "mozambique": "MZ",
    "madagascar": "MG",
    "mauritius": "MU", "maurice": "MU",
    "namibia": "NA", "namibie": "NA",
    "botswana": "BW",
    "rwanda": "RW",
    "libya": "LY", "libye": "LY",
    "sudan": "SD", "soudan": "SD",
    "papua new guinea": "PG", "papouasie": "PG",
    "fiji": "FJ", "fidji": "FJ",
    "samoa": "WS",
    "tonga": "TO",
    "turkmenistan": "TM",
    "abkhazia": "GE", "abkhazie": "GE",
    "samogh": "RU", "ossetia": "RU",
    // Pacific / Oceania
    "guam": "GU", "american samoa": "AS", "samoa americaines": "AS",
    "northern mariana islands": "MP", "palau": "PW", "micronesia": "FM", "micronesie": "FM", "micronésie": "FM",
    "marshall islands": "MH", "iles marshall": "MH", "îles marshall": "MH",
    "kiribati": "KI", "nauru": "NR", "tuvalu": "TV", "vanuatu": "VU",
    "solomon islands": "SB", "iles salomon": "SB", "îles salomon": "SB",
    "new caledonia": "NC", "nouvelle-caledonie": "NC", "nouvelle-calédonie": "NC",
    "french polynesia": "PF", "polynesie francaise": "PF", "polynésie française": "PF",
    // Caribbean
    "cuba": "CU", "cuban": "CU",
    "haiti": "HT", "haïti": "HT",
    "jamaica": "JM", "jamaique": "JM", "jamaïque": "JM",
    "barbados": "BB", "barbade": "BB",
    "trinite-et-tobago": "TT", "trinidad and tobago": "TT", "trinidad": "TT",
    "guadeloupe": "GP", "martinique": "MQ",
    "antigua and barbuda": "AG", "antigua-et-barbuda": "AG",
    "saint lucia": "LC", "sainte-lucie": "LC",
    "saint kitts and nevis": "KN", "saint-kitts-et-nevis": "KN",
    "saint vincent and the grenadines": "VC", "saint-vincent-et-les-grenadines": "VC",
    "grenada": "GD", "grenade": "GD",
    "dominica": "DM", "dominique": "DM",
    "belize": "BZ", "aruba": "AW", "curacao": "CW", "curaçao": "CW",
    "cayman islands": "KY", "iles caimans": "KY", "îles caïmans": "KY",
    "virgin islands": "VI", "british virgin islands": "VG",
    "bermuda": "BM", "bahamas": "BS",
    // Africa — additional
    "democratic republic of congo": "CD", "dr congo": "CD", "drc": "CD",
    "republique democratique du congo": "CD", "rdc": "CD",
    "republic of congo": "CG", "congo": "CG",
    "gabon": "GA", "guinea": "GN", "guinee": "GN", "guinée": "GN",
    "guinea-bissau": "GW", "guinee-bissau": "GW", "guinée-bissau": "GW",
    "equatorial guinea": "GQ", "guinee equatoriale": "GQ", "guinée équatoriale": "GQ",
    "togo": "TG", "benin": "BJ", "bénin": "BJ",
    "burkina faso": "BF", "cape verde": "CV", "cap-vert": "CV",
    "central african republic": "CF", "republique centrafricaine": "CF",
    "chad": "TD", "tchad": "TD",
    "djibouti": "DJ", "eritrea": "ER", "erythree": "ER", "érythrée": "ER",
    "comoros": "KM", "comores": "KM",
    "gambia": "GM", "gambie": "GM",
    "sierra leone": "SL",
    "liberia": "LR",
    "niger": "NE",
    "malawi": "MW",
    "zambia": "ZM", "zambie": "ZM",
    "eswatini": "SZ", "swaziland": "SZ", "lesotho": "LS",
    "seychelles": "SC", "reunion": "RE", "réunion": "RE",
    "sao tome and principe": "ST", "sao tome": "ST",
    "burundi": "BI",
    "south sudan": "SS", "soudan du sud": "SS",
    "somalia": "SO", "somalie": "SO",
    // Middle East / Central Asia additional
    "palestine": "PS", "palestinian territories": "PS",
    "maldives": "MV", "bhutan": "BT", "bhoutan": "BT",
    "timor-leste": "TL", "east timor": "TL", "timor oriental": "TL",
    "brunei": "BN",
    "uzbek": "UZ",
    // Europe additional
    "andorra": "AD", "andorre": "AD",
    "liechtenstein": "LI", "san marino": "SM", "vatican": "VA",
    "faroe islands": "FO", "iles feroe": "FO", "îles féroé": "FO",
    "gibraltar": "GI", "isle of man": "IM",
    "channel islands": "JE", "jersey": "JE", "guernsey": "GG",
    "greenland": "GL", "groenland": "GL",
    // Americas additional
    "french guiana": "GF", "guyane française": "GF", "guyane": "GF",
    "falkland islands": "FK", "iles malouines": "FK", "îles malouines": "FK",
    "saint-barthelemy": "BL", "saint barthelemy": "BL",
    "saint martin": "MF",
    // Aliases / short forms used in MMA databases
    "american": "US",
    "brit": "GB", "british": "GB",
    "kiwi": "NZ",
    "aussie": "AU",
    "scotsman": "GB",
    "welsh": "GB",
    "émirats arabes unis": "AE", "emirats arabes unis": "AE",
};

// Map FR -> EN pour afficher les noms de pays en anglais partout sur le site.
// Seules les clefs FR sont listees (les EN passent through telles quelles).
const FR_TO_EN_COUNTRY = {
    "etats-unis": "United States", "états-unis": "United States",
    "russie": "Russia", "bresil": "Brazil", "brésil": "Brazil",
    "irlande": "Ireland", "espagne": "Spain", "allemagne": "Germany",
    "japon": "Japan", "chine": "China",
    "ouzbekistan": "Uzbekistan", "ouzbékistan": "Uzbekistan",
    "kirghizistan": "Kyrgyzstan", "azerbaidjan": "Azerbaijan", "azerbaïdjan": "Azerbaijan",
    "georgie": "Georgia", "géorgie": "Georgia",
    "armenie": "Armenia", "arménie": "Armenia",
    "norvege": "Norway", "norvège": "Norway",
    "suede": "Sweden", "suède": "Sweden",
    "italie": "Italy", "pologne": "Poland",
    "danemark": "Denmark", "finlande": "Finland", "islande": "Iceland",
    "pays-bas": "Netherlands", "belgique": "Belgium", "autriche": "Austria",
    "suisse": "Switzerland", "hongrie": "Hungary",
    "republique tcheque": "Czech Republic", "république tchèque": "Czech Republic", "tchequie": "Czech Republic",
    "slovaquie": "Slovakia", "slovenie": "Slovenia", "slovénie": "Slovenia",
    "roumanie": "Romania", "bulgarie": "Bulgaria",
    "grece": "Greece", "grèce": "Greece",
    "turquie": "Turkey", "irak": "Iraq", "israël": "Israel",
    "liban": "Lebanon", "syrie": "Syria", "jordanie": "Jordan",
    "arabie saoudite": "Saudi Arabia",
    "emirats arabes unis": "United Arab Emirates", "émirats arabes unis": "United Arab Emirates",
    "koweit": "Kuwait", "koweït": "Kuwait", "bahrein": "Bahrain", "bahreïn": "Bahrain",
    "yemen": "Yemen", "yémen": "Yemen",
    "maroc": "Morocco", "tunisie": "Tunisia",
    "algerie": "Algeria", "algérie": "Algeria",
    "egypte": "Egypt", "égypte": "Egypt",
    "afrique du sud": "South Africa", "cameroun": "Cameroon",
    "inde": "India",
    "thailande": "Thailand", "thaïlande": "Thailand",
    "indonesie": "Indonesia", "indonésie": "Indonesia",
    "malaisie": "Malaysia", "singapour": "Singapore", "cambodge": "Cambodia",
    "népal": "Nepal", "mongolie": "Mongolia",
    "taiwan": "Taiwan", "taïwan": "Taiwan",
    "argentine": "Argentina", "chili": "Chile",
    "colombie": "Colombia",
    "perou": "Peru", "pérou": "Peru",
    "equateur": "Ecuador", "équateur": "Ecuador",
    "bolivie": "Bolivia",
    "jamaique": "Jamaica", "jamaïque": "Jamaica",
    "republique dominicaine": "Dominican Republic", "république dominicaine": "Dominican Republic",
    "haiti": "Haiti", "haïti": "Haiti",
    "mexique": "Mexico",
    "nouvelle-zelande": "New Zealand", "nouvelle-zélande": "New Zealand",
    "moldavie": "Moldova",
    "bielorussie": "Belarus", "biélorussie": "Belarus",
    "estonie": "Estonia", "lettonie": "Latvia", "lituanie": "Lithuania",
    "bosnie": "Bosnia", "albanie": "Albania",
    "macedoine": "North Macedonia", "macédoine": "North Macedonia",
    "chypre": "Cyprus", "malte": "Malta",
    "guyane": "Guyana",
    "sénégal": "Senegal",
    "cote d'ivoire": "Ivory Coast", "côte d'ivoire": "Ivory Coast",
    "ouganda": "Uganda", "tanzanie": "Tanzania",
    "libye": "Libya", "soudan": "Sudan",
    "fidji": "Fiji", "maurice": "Mauritius", "namibie": "Namibia",
    "birmanie": "Myanmar",
    "coree du sud": "South Korea", "corée du sud": "South Korea",
    "tchetchenie": "Russia", "tchétchénie": "Russia",
    "papouasie": "Papua New Guinea",
    // Additional FR names
    "tcheque": "Czech Republic", "tchadien": "Chad", "tchad": "Chad",
    "republique centrafricaine": "Central African Republic",
    "guinee equatoriale": "Equatorial Guinea", "guinée équatoriale": "Equatorial Guinea",
    "cap-vert": "Cape Verde", "burkina faso": "Burkina Faso",
    "benin": "Benin", "bénin": "Benin",
    "djibouti": "Djibouti",
    "erythree": "Eritrea", "érythrée": "Eritrea",
    "somalie": "Somalia",
    "soudan du sud": "South Sudan",
    "comores": "Comoros",
    "gambie": "Gambia",
    "ouganda": "Uganda",
    "andorre": "Andorra",
    "liechtenstein": "Liechtenstein",
    "groenland": "Greenland",
    "polynesie francaise": "French Polynesia", "polynésie française": "French Polynesia",
    "nouvelle-caledonie": "New Caledonia", "nouvelle-calédonie": "New Caledonia",
    "zambie": "Zambia", "mozambique": "Mozambique",
    "bhoutan": "Bhutan",
    "timor oriental": "Timor-Leste",
    "guyane française": "French Guiana", "guyane francaise": "French Guiana",
    "iles malouines": "Falkland Islands", "îles malouines": "Falkland Islands",
    "iles marshall": "Marshall Islands", "îles marshall": "Marshall Islands",
    "micronesie": "Micronesia", "micronésie": "Micronesia",
    "iles salomon": "Solomon Islands", "îles salomon": "Solomon Islands",
};

function nationalityEnglish(name) {
    if (!name) return "";
    const k = String(name).trim().toLowerCase();
    return FR_TO_EN_COUNTRY[k] || name;
}

function nationalityToFlag(name) {
    // Garde l'API pour compat (rare cas ou on veut juste l'emoji).
    if (!name) return "";
    const key = String(name).trim().toLowerCase();
    const code = COUNTRY_TO_ISO[key];
    if (!code) return "";
    return String.fromCodePoint(...[...code.toUpperCase()].map(c => 0x1F1A5 + c.charCodeAt(0)));
}

// HTML d'un drapeau via flag-icons (SVG, fonctionne sur tous les OS / fonts).
// Renvoie un <span class="fi fi-XX"> ou "" si pays inconnu.
function nationalityToFlagHTML(name) {
    if (!name) return "";
    const key = String(name).trim().toLowerCase();
    const code = COUNTRY_TO_ISO[key];
    if (!code) return "";
    return `<span class="fi fi-${code.toLowerCase()}" aria-hidden="true"></span>`;
}

// ---- Renderers reutilisables -----------------------------------------------

function avatar(f, size = "") {
    const src = f.photo_thumbnail_url || f.photo_url;
    if (src) {
        return `<div class="avatar ${size}"><img src="${esc(src)}" alt="${esc(f.name)}" loading="lazy" onerror="this.parentNode.innerHTML='<span class=&quot;initials&quot;>${esc(initials(f.name))}</span>'"></div>`;
    }
    return `<div class="avatar ${size}"><span class="initials">${esc(initials(f.name))}</span></div>`;
}

function recordStr(f) {
    const w = f.record_total_wins ?? 0;
    const l = f.record_total_losses ?? 0;
    const d = f.record_total_draws ?? 0;
    let h = `<span class="record-w">${w}</span><span class="record-sep">-</span><span class="record-l">${l}</span>`;
    if (d > 0) h += `<span class="record-sep">-</span><span class="record-d">${d}</span>`;
    return h;
}

function streakPill(streak) {
    if (!streak || streak === "0") return `<span class="streak-pill neutral">--</span>`;
    // Le format BDD est "16W" / "1L" (nombre puis lettre) -> on detecte la lettre
    // ou qu'elle soit et on extrait le compteur.
    const s = String(streak).toUpperCase();
    const isW = /W/.test(s), isL = /L/.test(s);
    const n = parseInt(s.replace(/[^0-9]/g, ""), 10) || 0;
    // Hot/cold base sur de VRAIS combats : 3 victoires d'affilee = en feu,
    // 2 defaites = en perte de vitesse. En dessous, pill win/loss normale.
    let cls = isW ? "win" : isL ? "loss" : "neutral";
    let ico = "";
    if (isW && n >= 3)      { cls = "hot";  ico = `<span class="trend-ico" aria-hidden="true">▲</span>`; }
    else if (isL && n >= 2) { cls = "cold"; ico = `<span class="trend-ico" aria-hidden="true">▼</span>`; }
    return `<span class="streak-pill ${cls}">${ico}${esc(streak)}</span>`;
}

function last5Pills(last5) {
    if (!last5) return `<span class="muted">--</span>`;
    // last5 : "W,L,W,W,NC" du plus ancien au plus récent → on inverse pour plus récent à gauche.
    const results = String(last5).split(",")
        .map(s => s.trim().toUpperCase())
        .filter(s => s.length > 0)
        .map(s => {
            if (s === "W") return "W";
            if (s === "L") return "L";
            if (s === "D") return "D";
            // NC, N, NO CONTEST, N/C → NC
            if (/^N/.test(s)) return "NC";
            return null;
        })
        .filter(Boolean)
        .reverse();
    if (!results.length) return `<span class="muted">--</span>`;
    return `<span class="last5">${results.map(c => {
        const cls = c === "W" ? "w" : c === "L" ? "l" : c === "NC" ? "nc" : "d";
        return `<span class="res ${cls}">${esc(c)}</span>`;
    }).join("")}</span>`;
}

// ---- Unites (taille / allonge) selon la pref user --------------------------
// Les valeurs scrappees sont des chaines : 5'5"  ·  66.1"  ·  5' 11" ...
function _strToInches(raw) {
    if (raw === null || raw === undefined) return null;
    const s = String(raw).trim();
    let m = s.match(/(\d+)\s*['′]\s*(\d+(?:\.\d+)?)/);   // pieds'pouces"
    if (m) return parseInt(m[1], 10) * 12 + parseFloat(m[2]);
    m = s.match(/(\d+(?:\.\d+)?)/);                        // pouces seuls
    if (m) return parseFloat(m[1]);
    return null;
}
function formatLengthPref(raw) {
    if (!raw) return "--";
    const metric = window.MMAIPrefs && window.MMAIPrefs.get("units") === "metric";
    if (!metric) return String(raw);
    const inch = _strToInches(raw);
    if (inch == null) return String(raw);
    return `${Math.round(inch * 2.54)} cm`;
}

// ---- Bouton "epingler au comparateur" (variants: corner | text) ------------
function pinButtonHTML(f, variant) {
    const photo = f.photo_thumbnail_url || f.photo_url || "";
    const pinned = (window.MMAICompare && window.MMAICompare.has(f.id)) ? " pinned" : "";
    const label  = t("compare.add_btn");
    // Icone "+" ; pivotee en "×" via CSS quand epingle (= clic pour retirer)
    const ico = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
    const attrs = `data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}" data-fighter-photo="${esc(photo)}"`;
    if (variant === "text") {
        return `<button class="mm-pin-text${pinned}" ${attrs} title="${esc(label)}">${ico}<span>${esc(label)}</span></button>`;
    }
    return `<button class="mm-pin${pinned}" ${attrs} title="${esc(label)}" aria-label="${esc(label)}">${ico}</button>`;
}

function fighterCard(f) {
    const photo = f.photo_thumbnail_url || f.photo_url;
    const photoBlock = photo
        ? `<img src="${esc(photo)}" alt="${esc(f.name)}" loading="lazy" onerror="this.parentNode.innerHTML='<div class=&quot;no-photo&quot;>${esc(initials(f.name))}</div>'">`
        : `<div class="no-photo">${esc(initials(f.name))}</div>`;

    const badges = [];
    if (f.is_ufc_champion) badges.push(`<span class="badge champ">${t("common.champion")}</span>`);
    if (f.ufc_official_rank) badges.push(`<span class="badge rank">#${f.ufc_official_rank}</span>`);
    if (!f.is_active) badges.push(`<span class="badge inactive">${t("common.inactive")}</span>`);
    // Weight class : libelle court coherent partout dans le site (BW W / BW M ...)
    const _wc = (f.weight_class_current && f.weight_class_current !== "Unknown")
        ? formatWeightClassShort(f.weight_class_current, f.gender)
        : "";
    if (_wc) badges.push(`<span class="badge weight">${esc(_wc)}</span>`);

    const rating = f.fightmatrix_rating_points ?? f.base_elo;
    // On ne devoile plus la source : toujours afficher "Rating" peu importe d'ou ca vient.
    const ratingLabel = t("common.rating");

    return `
        <a href="fighter.html?id=${f.id}" class="fighter-card" data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}" data-hc-restricted>
            <div class="fighter-photo" data-hc-zone>
                <div class="fighter-badges">
                    <div style="display:flex; gap:6px;">${badges.slice(0, 2).join("")}</div>
                    <div style="display:flex; gap:6px;">${badges.slice(2).join("")}</div>
                </div>
                ${photoBlock}
                ${pinButtonHTML(f, "corner")}
                <div class="fighter-overlay">
                    <div class="fighter-name">${esc(f.name)}</div>
                    ${f.nickname ? `<div class="fighter-nickname">"${esc(f.nickname)}"</div>` : ""}
                </div>
            </div>
            <div class="fighter-body">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div class="fighter-record">${recordStr(f)}</div>
                    ${streakPill(f.current_streak)}
                </div>
                <div class="fighter-meta">
                    <div>
                        <div class="meta-label">${ratingLabel}</div>
                        <div class="meta-value">${rating ? fmtNumber(rating, 0) : '<span class="muted">--</span>'}</div>
                    </div>
                    <div>
                        <div class="meta-label">${t("common.age")}</div>
                        <div class="meta-value">${num(f.age)}</div>
                    </div>
                    <div>
                        <div class="meta-label">${t("common.win_pct")}</div>
                        <div class="meta-value">${f.win_percentage_int != null ? f.win_percentage_int + "%" : '<span class="muted">--</span>'}</div>
                    </div>
                    <div>
                        <div class="meta-label">${t("common.finish_pct")}</div>
                        <div class="meta-value">${f.finish_rate_int != null ? f.finish_rate_int + "%" : '<span class="muted">--</span>'}</div>
                    </div>
                </div>
            </div>
        </a>
    `;
}

function fighterRow(f, rank) {
    const photo = f.photo_thumbnail_url || f.photo_url;
    const av = photo
        ? `<div class="avatar"><img src="${esc(photo)}" alt="${esc(f.name)}" loading="lazy" onerror="this.parentNode.innerHTML='<span class=&quot;initials&quot;>${esc(initials(f.name))}</span>'"></div>`
        : `<div class="avatar"><span class="initials">${esc(initials(f.name))}</span></div>`;

    const rankCls = rank === 1 ? "top-1" : rank <= 3 ? "top-3" : "";
    // base_elo uniquement (jamais les points FightMatrix bruts — cf. CLAUDE.md)
    const rating = f.base_elo ?? null;

    const nameSuffix = f.is_ufc_champion
        ? ` <span class="badge champ" style="margin-left:6px;">C</span>`
        : (f.ufc_official_rank ? ` <span style="color:var(--text-dim); font-size:11px;">#${f.ufc_official_rank}</span>` : "");

    return `
        <tr onclick="location.href='fighter.html?id=${f.id}'" data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}" data-hc-restricted>
            <td class="rank-cell hide-mobile ${rankCls}">${rank}</td>
            <td>
                <div class="fighter-cell" data-hc-zone>
                    ${av}
                    <div class="info">
                        <div class="name">${esc(f.name)}${nameSuffix}</div>
                        ${f.nickname ? `<div class="nickname">"${esc(f.nickname)}"</div>` : ""}
                    </div>
                </div>
            </td>
            <td class="hide-mobile">${esc(f.weight_class_current || "--")}</td>
            <td><div class="fighter-record" style="font-size:16px;">${recordStr(f)}</div></td>
            <td class="hide-mobile">${last5Pills(f.last_5_results)}</td>
            <td class="rating-cell">${rating ? fmtNumber(rating, 0) : '<span class="muted">--</span>'}</td>
        </tr>
    `;
}

// ---- Page : Accueil --------------------------------------------------------

async function renderHomePage() {
    setupNavSearch();
    // Section favoris : charge si connecte, se met a jour au changement d'auth
    renderFavoritesSection();
    window.addEventListener("mmai:auth-change", () => renderFavoritesSection());
    try {
        const [stats, top, champs, nextEventResult, lastEventResult] = await Promise.all([
            api.stats(),
            api.top(),
            api.champions(),
            api.events({ status: "upcoming", promotion: "UFC", sort: "asc", limit: 1 }).catch(() => null),
            api.lastEvent("UFC").catch(() => null),
        ]);
        $("#hero-count").textContent = fmtNumber(stats.total_fighters);
        const heroChamps = $("#hero-stat-champs");
        if (heroChamps) heroChamps.textContent = fmtNumber(stats.champions ?? 0);
        $$('[data-stat]').forEach(el => {
            const key = el.dataset.stat;
            el.textContent = fmtNumber(stats[key] ?? 0);
        });

        // Champions strip
        if (champs && champs.length) {
            $("#champions-section").style.display = "block";
            $("#champions-strip").innerHTML = champs.map(c => {
                // thumbnail UFC-FR d'abord (fiable) ; Tapology souvent mort -> fallback
                const photo = c.photo_thumbnail_url || c.photo_url;
                const photoBlock = photo
                    ? `<img src="${esc(photo)}" alt="${esc(c.name)}" loading="lazy" onerror="this.parentNode.innerHTML='<div class=&quot;no-photo&quot;>${esc(initials(c.name))}</div>'">`
                    : `<div class="no-photo">${esc(initials(c.name))}</div>`;
                return `
                    <a href="fighter.html?id=${c.id}" class="champ-mini-card">
                        <div class="photo">${photoBlock}</div>
                        <div class="body">
                            <div class="div-name">${esc(c.weight_class_current || "")}</div>
                            <div class="name">${esc(c.name)}</div>
                            <div class="rec">${c.record_total_wins || 0}-${c.record_total_losses || 0}${(c.record_total_draws||0)>0?"-"+c.record_total_draws:""}</div>
                        </div>
                    </a>
                `;
            }).join("");
        }

        // Next event card
        const nextEvents = nextEventResult
            ? (nextEventResult.events || nextEventResult)
            : [];
        const nextEvent = Array.isArray(nextEvents) ? nextEvents[0] : null;
        const nextEventSection = $("#next-event-section");
        if (nextEvent && nextEventSection) {
            nextEventSection.style.display = "block";
            const cardRoot = $("#next-event-card-root");
            if (cardRoot) cardRoot.innerHTML = buildNextEventCard(nextEvent);
        }

        // Last event card
        const lastEventSection = $("#last-event-section");
        if (lastEventResult && lastEventResult.id && lastEventSection) {
            lastEventSection.style.display = "block";
            const lastRoot = $("#last-event-card-root");
            if (lastRoot) lastRoot.innerHTML = buildLastEventCard(lastEventResult);
        }

        // Top Challengers grid
        const grid = $("#top-fighters");
        if (!top.length) {
            grid.innerHTML = `<div class="empty" style="grid-column:1/-1;"><h3>${t("home.no_fighter")}</h3><p>${t("home.no_fighter_sub")}</p></div>`;
        } else {
            grid.innerHTML = top.map(fighterCard).join("");
        }
    } catch (e) {
        showError($("#top-fighters"), e.message);
    }
}

function buildNextEventCard(ev) {
    const name = esc(ev.name || "UFC Event");
    const rawDate = ev.date || ev.event_date || "";
    const dateObj = rawDate ? new Date(rawDate) : null;
    const dateStr = dateObj && !isNaN(dateObj)
        ? dateObj.toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" })
        : esc(rawDate);
    const venue = esc(ev.venue || "");
    const location = esc(ev.location || ev.city || "");
    const venueStr = [venue, location].filter(Boolean).join(" · ");
    const poster = ev.poster_url || ev.image_url || "";
    const eventLink = ev.id ? `event.html?id=${ev.id}` : "events.html";

    return `
        <a href="${eventLink}" class="next-event-card">
            ${poster ? `<div class="next-event-poster"><img src="${esc(poster)}" alt="${name}" loading="lazy" onerror="this.parentNode.style.display='none'"></div>` : ""}
            <div class="next-event-body">
                <div class="next-event-badge">UPCOMING</div>
                <div class="next-event-name">${name}</div>
                ${dateStr ? `<div class="next-event-date"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>${dateStr}</div>` : ""}
                ${venueStr ? `<div class="next-event-venue"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>${venueStr}</div>` : ""}
            </div>
        </a>`;
}

function buildLastEventCard(ev) {
    const name = esc(ev.name || "UFC Event");
    const rawDate = ev.date || "";
    const dateObj = rawDate ? new Date(rawDate) : null;
    const dateStr = dateObj && !isNaN(dateObj)
        ? dateObj.toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" })
        : esc(rawDate);
    const venue = esc(ev.venue || "");
    const loc   = esc(ev.city || "");
    const venueStr = [venue, loc].filter(Boolean).join(" · ");
    const poster = ev.poster_url || ev.image_url || "";
    const eventLink = ev.id ? `event.html?id=${ev.id}` : "events.html?type=results&promotion=UFC";

    return `
        <a href="${eventLink}" class="last-event-card">
            ${poster ? `<div class="last-event-poster"><img src="${esc(poster)}" alt="${name}" loading="lazy" onerror="this.parentNode.style.display='none'"></div>` : ""}
            <div class="last-event-header">
                <div class="last-event-badge">PAST EVENT</div>
                <div class="last-event-name">${name}</div>
                ${dateStr ? `<div class="last-event-date"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>${dateStr}</div>` : ""}
                ${venueStr ? `<div class="last-event-venue"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>${venueStr}</div>` : ""}
            </div>
        </a>`;
}

// ---- Page : Rankings -------------------------------------------------------

// ---- Page : Rankings (HUB : P4P + champion/#1/#2 par division) --------------

async function renderRankingsPage() {
    setupNavSearch();
    const root = $("#rankings-root");
    if (!root) return;
    try {
        const o = await api.rankingsOverview();
        root.innerHTML = `
            <section class="rk-hero">
                <div class="container">
                    <div class="rk-hero-pill">${t("rankings.ufc_pill")}</div>
                    <h1 class="rk-hero-title">${t("rankings.title")}</h1>
                    <p class="rk-hero-sub">${t("rankings.hub_sub")}</p>
                </div>
            </section>
            <div class="container rk-body">
                <div class="rk-p4p-grid">
                    ${rkP4PCard(t("rankings.p4p_men"), o.p4p_men, "M")}
                    ${rkP4PCard(t("rankings.p4p_women"), o.p4p_women, "F")}
                </div>
                ${o.men && o.men.length ? `
                <div class="rk-cat-block">
                    <h2 class="rk-cat-heading">${t("common.men")}</h2>
                    <div class="rk-cat-grid">${o.men.map(rkCatCard).join("")}</div>
                </div>` : ""}
                ${o.women && o.women.length ? `
                <div class="rk-cat-block">
                    <h2 class="rk-cat-heading rk-cat-heading-w">${t("common.women")}</h2>
                    <div class="rk-cat-grid">${o.women.map(rkCatCard).join("")}</div>
                </div>` : ""}
            </div>
        `;
        if (typeof window._hcPrefill === "function") {
            [...(o.p4p_men || []), ...(o.p4p_women || [])].forEach(window._hcPrefill);
        }
    } catch (e) {
        root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="error-box">${esc(e.message)}</div></div>`;
    }
}

// Une ligne de classement (badge + avatar + nom + record), cliquable vers le profil.
function rkRankLine(f, badge, badgeCls) {
    const photo = f.photo_thumbnail_url || f.photo_url;
    const av = photo
        ? `<span class="rk-line-av" data-hc-zone><img src="${esc(photo)}" alt="${esc(f.name)}" loading="lazy" onerror="this.parentNode.classList.add('no-photo');this.parentNode.textContent='${esc(initials(f.name))}'"></span>`
        : `<span class="rk-line-av no-photo" data-hc-zone>${esc(initials(f.name))}</span>`;
    const ufcW = f.record_ufc_wins ?? 0, ufcL = f.record_ufc_losses ?? 0, ufcD = f.record_ufc_draws ?? 0;
    const hasUFC = (ufcW + ufcL + ufcD) > 0;
    const w = hasUFC ? ufcW : (f.record_total_wins ?? 0);
    const l = hasUFC ? ufcL : (f.record_total_losses ?? 0);
    const d = hasUFC ? ufcD : (f.record_total_draws ?? 0);
    const rec = `${w}-${l}${d > 0 ? "-" + d : ""}${hasUFC ? " UFC" : ""}`;
    return `
        <a href="fighter.html?id=${f.id}" class="rk-line" data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}" data-hc-restricted>
            <span class="rk-line-badge ${badgeCls}">${badge}</span>
            ${av}
            <span class="rk-line-name"><span data-hc-zone>${esc(f.name)}</span></span>
            <span class="rk-line-rec">${rec}</span>
        </a>`;
}

function rkP4PCard(title, list, gender) {
    if (!list || !list.length) return "";
    // Top 10 affiché sur le hub ; "See more" → nouvelle URL p4p.html
    const top10 = list.slice(0, 10).map(f => rkRankLine(f, "#" + f.ufc_p4p_rank, "p4p")).join("");
    return `
        <div class="rk-p4p-card ${gender === "F" ? "w" : "m"}">
            <div class="rk-p4p-head"><span class="rk-p4p-icon">★</span><span>${esc(title)}</span></div>
            <div class="rk-p4p-list">${top10}</div>
            <a href="p4p.html" class="rk-p4p-more">${t("rankings.see_more")}</a>
        </div>`;
}

function rkCatCard(div) {
    const lines = [];
    if (div.champion) lines.push(rkRankLine(div.champion, "C", "champ"));
    if (div.rank1)    lines.push(rkRankLine(div.rank1, "1", "r1"));
    if (div.rank2)    lines.push(rkRankLine(div.rank2, "2", "r2"));
    if (div.rank3)    lines.push(rkRankLine(div.rank3, "3", "r3"));
    // Lien → ranking.html (classement MM.AI), PAS division.html
    const url = `ranking.html?wc=${encodeURIComponent(div.base)}&gender=${div.gender}`;
    const label = formatWeightClassLong(div.base, div.gender === "F" ? "F" : "M");
    return `
        <div class="rk-cat-card">
            <a href="${url}" class="rk-cat-head">
                <span class="rk-cat-name">${esc(label)}</span>
                <span class="rk-cat-link">${t("divisions.full_ranking")}</span>
            </a>
            <div class="rk-cat-lines">${lines.join("") || `<div class="rk-cat-empty">${t("division.no_fighters")}</div>`}</div>
        </div>`;
}

// page : le classement d'une division (top 15 MM.AI + ceux juste en dessous) -----------------

async function renderRankingPage() {
    setupNavSearch();
    const root = document.getElementById("ranking-root");
    if (!root) return;
    const wc     = getQueryParam("wc") || "";
    const gender = (getQueryParam("gender") || "M").toUpperCase();
    if (!wc) {
        root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="error-box">No division specified.</div></div>`;
        return;
    }
    const label = formatWeightClassLong(wc, gender === "F" ? "F" : "M");
    document.title = `${label} Rankings — MM.AI`;
    root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="loader">${t("common.loading")}</div></div>`;
    try {
        const d = await api.divisionRanking(wc, gender);
        root.innerHTML = buildRankingPage(d, label, wc, gender);
        if (typeof window._hcPrefill === "function") {
            if (d.champion) window._hcPrefill(d.champion);
            (d.fighters || []).forEach(window._hcPrefill);
        }
    } catch (e) {
        root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="error-box">${esc(e.message)}</div></div>`;
    }
}

function buildRankingPage(d, label, wc, gender) {
    const champBlock = d.champion ? `
        <a href="fighter.html?id=${d.champion.id}" class="rkd-champ-card" data-fighter-id="${d.champion.id}" data-fighter-name="${esc(d.champion.name)}" data-hc-restricted>
            <div class="rkd-champ-belt">${t("division.ufc_champion") || "UFC Champion"}</div>
            <div class="rkd-champ-inner">
                ${(() => {
                    // thumbnail UFC-FR d'abord (fiable) ; Tapology souvent mort -> fallback initiales via onerror
                    const p = d.champion.photo_thumbnail_url || d.champion.photo_url;
                    return p ? `<div class="rkd-champ-photo" data-hc-zone><img src="${esc(p)}" alt="${esc(d.champion.name)}" loading="lazy" onerror="this.parentNode.classList.add('rkd-champ-nophoto');this.parentNode.textContent='${esc(initials(d.champion.name))}'"></div>`
                             : `<div class="rkd-champ-photo rkd-champ-nophoto" data-hc-zone>${esc(initials(d.champion.name))}</div>`;
                })()}
                <div class="rkd-champ-info">
                    ${d.champion.nickname ? `<div class="rkd-champ-nick">"${esc(d.champion.nickname)}"</div>` : ""}
                    <div class="rkd-champ-name"><span data-hc-zone>${esc(d.champion.name)}</span></div>
                    <div class="rkd-champ-sub">
                        ${nationalityToFlagHTML(d.champion.nationality) || ""}
                        <span>${esc(nationalityEnglish(d.champion.nationality) || "")}</span>
                    </div>
                    ${(() => {
                        const f = d.champion;
                        const tW = f.record_total_wins ?? 0, tL = f.record_total_losses ?? 0, tD = f.record_total_draws ?? 0;
                        const uW = f.record_ufc_wins ?? 0, uL = f.record_ufc_losses ?? 0, uD = f.record_ufc_draws ?? 0;
                        const hasUFC = (uW + uL + uD) > 0;
                        const flagH = nationalityToFlagHTML(f.nationality);
                        const ufcSmall = hasUFC ? `<span class="rkd-rec-ufc-small">${uW}-${uL}${uD > 0 ? `-${uD}` : ""} <span class="rkd-rec-ufc">UFC</span></span>` : "";
                        return `<div class="rkd-champ-rec">
                            <span class="rkd-rec-total"><span class="w">${tW}</span>-<span class="l">${tL}</span>${tD > 0 ? `-<span class="d">${tD}</span>` : ""}</span>
                            <span class="rkd-rec-flag">${flagH || ""}</span>
                            ${ufcSmall}
                        </div>`;
                    })()}
                </div>
            </div>
        </a>` : "";

    const top15Html = (d.top15 || []).map((f, i) => rkDivRow(f, i + 1, false)).join("");
    const bubbleHtml = (d.bubble || []).map((f, i) => rkDivRow(f, 16 + i, true)).join("");
    const rosterUrl = `roster.html?wc=${encodeURIComponent(wc)}&gender=${gender}`;

    return `
        <section class="rkd-hero">
            <div class="container">
                <a href="rankings.html" class="back-btn">← ${t("common.back")}</a>
                <div class="rkd-hero-row">
                    <div>
                        <div class="rkd-hero-pill">${gender === "F" ? t("division.womens") : t("division.mens")} · MM.AI Rankings</div>
                        <h1 class="rkd-hero-title">${esc(label)}</h1>
                        <p class="rkd-hero-sub">${d.total || "?"} ${t("division.in_db")}</p>
                    </div>
                    <a href="${rosterUrl}" class="btn btn-ghost btn-sm">${t("ranking.full_roster")}</a>
                </div>
            </div>
        </section>
        <div class="container rkd-body">
            ${champBlock ? `<div class="rkd-section">${champBlock}</div>` : ""}
            ${top15Html ? `
            <div class="rkd-section">
                <div class="rkd-section-head">
                    <span class="rkd-section-title">${t("ranking.top15_title")}</span>
                    <span class="rkd-section-meta">${t("ranking.sorted_by_score")}</span>
                </div>
                <div class="rkd-list">${top15Html}</div>
            </div>` : `<div class="empty"><h3>${t("common.no_results")}</h3></div>`}
            ${bubbleHtml ? `
            <div class="rkd-section rkd-section-bubble">
                <div class="rkd-section-head rkd-bubble-head">
                    <span class="rkd-section-title">${t("ranking.on_bubble")}</span>
                    <span class="rkd-section-meta">${t("ranking.bubble_sub")}</span>
                </div>
                <div class="rkd-list rkd-list-bubble">${bubbleHtml}</div>
            </div>` : ""}
        </div>
    `;
}

function rkDivRow(f, pos, isBubble) {
    const photo = f.photo_thumbnail_url || f.photo_url;
    const av = photo
        ? `<span class="rkd-av" data-hc-zone><img src="${esc(photo)}" alt="${esc(f.name)}" loading="lazy" onerror="this.parentNode.classList.add('no-photo');this.parentNode.textContent='${esc(initials(f.name))}'"></span>`
        : `<span class="rkd-av no-photo" data-hc-zone>${esc(initials(f.name))}</span>`;
    const tW = f.record_total_wins ?? 0, tL = f.record_total_losses ?? 0, tD = f.record_total_draws ?? 0;
    const uW = f.record_ufc_wins ?? 0, uL = f.record_ufc_losses ?? 0, uD = f.record_ufc_draws ?? 0;
    const hasUFC = !isBubble && (uW + uL + uD) > 0;
    const ufcSmall = hasUFC ? `<span class="rkd-rec-ufc-small">${uW}-${uL}${uD > 0 ? `-${uD}` : ""} <span class="rkd-rec-ufc">UFC</span></span>` : "";
    const flag = nationalityToFlagHTML(f.nationality);
    const posCls = pos === 1 ? "pos-1" : pos <= 5 ? "pos-top5" : isBubble ? "pos-bubble" : "";
    const champBadge = f.is_ufc_champion ? `<span class="rkd-c-badge">C</span>` : "";
    return `
        <a href="fighter.html?id=${f.id}" class="rkd-row" data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}" data-hc-restricted>
            <span class="rkd-pos ${posCls}">${pos}${champBadge}</span>
            <span data-hc-zone>${av}</span>
            <span class="rkd-info">
                <span class="rkd-name"><span data-hc-zone>${esc(f.name)}</span></span>
                ${f.nickname ? `<span class="rkd-nick">"${esc(f.nickname)}"</span>` : ""}
            </span>
            <span class="rkd-rec">
                <span class="rkd-rec-total"><span class="w">${tW}</span>-<span class="l">${tL}</span>${tD > 0 ? `-${tD}` : ""}</span>
                <span class="rkd-rec-flag">${flag || ""}</span>
                ${ufcSmall || `<span class="rkd-rec-ufc-small"></span>`}
            </span>
        </a>`;
}

// ---- Page : P4P (top 15-20 toutes divisions confondues, H + F) --------------

async function renderP4PPage() {
    setupNavSearch();
    const root = document.getElementById("p4p-root");
    if (!root) return;
    root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="loader">${t("common.loading")}</div></div>`;
    try {
        const d = await api.p4pRankings();
        root.innerHTML = buildP4PPage(d);
    } catch (e) {
        root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="error-box">${esc(e.message)}</div></div>`;
    }
}

function buildP4PPage(d) {
    const colM = (d.men || []).map(f => p4pRow(f)).join("");
    const colF = (d.women || []).map(f => p4pRow(f)).join("");
    return `
        <section class="p4p-hero">
            <div class="container">
                <a href="rankings.html" class="back-btn">← ${t("common.back")}</a>
                <div class="p4p-hero-pill">★ ${t("p4p.eyebrow")}</div>
                <h1 class="p4p-hero-title">${t("p4p.title")}</h1>
                <p class="p4p-hero-sub">${t("p4p.sub")}</p>
            </div>
        </section>
        <div class="container p4p-body">
            <div class="p4p-grid">
                ${colM ? `<div class="p4p-col"><div class="p4p-col-head m">${t("rankings.p4p_men")}</div>${colM}</div>` : ""}
                ${colF ? `<div class="p4p-col"><div class="p4p-col-head w">${t("rankings.p4p_women")}</div>${colF}</div>` : ""}
            </div>
        </div>
    `;
}

function p4pRow(f) {
    const rank = f.ufc_p4p_rank || 0;
    const photo = f.photo_thumbnail_url || f.photo_url;
    const av = photo
        ? `<span class="p4pr-av"><img src="${esc(photo)}" alt="${esc(f.name)}" loading="lazy" onerror="this.parentNode.classList.add('no-photo');this.parentNode.textContent='${esc(initials(f.name))}'"></span>`
        : `<span class="p4pr-av no-photo">${esc(initials(f.name))}</span>`;
    const w = f.record_total_wins ?? 0, l = f.record_total_losses ?? 0, dw = f.record_total_draws ?? 0;
    const rec = `${w}-${l}${dw > 0 ? `-${dw}` : ""}`;
    const flag = nationalityToFlagHTML(f.nationality);
    const wc = formatWeightClassShort(f.weight_class_current, f.gender);
    const cls = rank === 1 ? "top-1" : rank === 2 ? "top-2" : rank === 3 ? "top-3" : "";
    return `
        <a href="fighter.html?id=${f.id}" class="p4pr ${cls}" data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}" data-hc-restricted>
            <span class="p4pr-pos">${rank || "?"}</span>
            <span data-hc-zone>${av}</span>
            <span class="p4pr-info">
                <span class="p4pr-name" data-hc-zone>${esc(f.name)}</span>
                <span class="p4pr-div">${esc(wc)}</span>
            </span>
            <span class="p4pr-flag">${flag || ""}</span>
            <span class="p4pr-rec">${rec}</span>
            ${f.is_ufc_champion ? `<span class="p4pr-champ">C</span>` : ""}
        </a>`;
}

// ---- Page : Fighters (grille avec recherche) -------------------------------

async function renderFightersPage() {
    setupNavSearch();
    const weightSel = $("#filter-weight");
    const statusSel = $("#filter-status");
    const sortSel   = $("#filter-sort");
    const search    = $("#search-input");
    const grid      = $("#fighters-grid");
    const count      = $("#fighters-count");

    const presetSearch = getQueryParam("q");
    const presetWeight = getQueryParam("weight_class");
    const presetStatus = getQueryParam("status");
    if (presetSearch) search.value = presetSearch;

    try {
        // Divisions GENREES : 1 entree par (division, genre), tokens "base|gender".
        // Le genre est porte par la division -> plus de filtre Gender separe.
        const wcs = await api.weightClassesGendered();
        for (const w of wcs) {
            const opt = document.createElement("option");
            opt.value = w.value;  // ex "Flyweight|F"
            const suffix = w.gender === "F" ? "(W)" : "(M)";
            opt.textContent = `${w.base} ${suffix} · ${w.count}`;
            weightSel.appendChild(opt);
        }
        if (presetWeight) {
            weightSel.value = presetWeight;
            // Compat deep-link non genre (?weight_class=Heavyweight) -> token homme.
            if (weightSel.value !== presetWeight && !presetWeight.includes("|")) {
                weightSel.value = `${presetWeight}|M`;
            }
        }
        if (presetStatus) statusSel.value = presetStatus;
    } catch {}

    async function reload() {
        grid.innerHTML = `<div class="loader" style="grid-column:1/-1;">${t("common.loading")}</div>`;
        try {
            const data = await api.fighters({
                search:       search.value.trim(),
                weight_class: weightSel.value,
                status:       statusSel ? statusSel.value : "all",
                sort:         sortSel.value,
                limit:        60,
            });
            count.textContent = `${data.total} ${t("common.fighters")}`;
            if (!data.fighters.length) {
                grid.innerHTML = `<div class="empty" style="grid-column:1/-1;"><h3>${t("common.no_results")}</h3><p>${t("fighters.no_results")}</p></div>`;
                return;
            }
            grid.innerHTML = data.fighters.map(fighterCard).join("");
        } catch (e) {
            showError(grid, e.message);
        }
    }

    [weightSel, statusSel, sortSel]
        .filter(Boolean)
        .forEach(el => el.addEventListener("change", reload));
    search.addEventListener("input", debounce(reload, 250));
    reload();
}

// ---- Page : Fighter profile ------------------------------------------------

async function renderFighterPage() {
    setupNavSearch();
    const root = $("#profile-root");
    const id = getQueryParam("id");
    if (!id) {
        root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="error-box">Missing ID.</div></div>`;
        return;
    }
    try {
        const f = await api.fighter(id);
        document.title = `${f.name} - MM.AI`;
        if (window.MMAIRecent) window.MMAIRecent.push(f);   // memorise "recemment consulte"
        root.innerHTML = renderFighterDetail(f);
        wireProfileTabs();
        const btn = root.querySelector('[data-action="open-scouter"]');
        if (btn) btn.addEventListener("click", () => openScouter(f));
        setupFavoriteStar(root, id);
        loadAndRenderHistory(id);
        const reportBtn = root.querySelector('[data-action="open-report"]');
        if (reportBtn) reportBtn.addEventListener("click", () => openReportModal({
            fighter_id: id, fighter_name: f.name
        }));
    } catch (e) {
        root.innerHTML = `<div class="container" style="padding-top:40px;"><div class="error-box">${esc(e.message)}</div></div>`;
    }
}

// ---- Favoris : étoile sur la page fighter -----------------------------------

async function setupFavoriteStar(root, fighterId) {
    const btn = root.querySelector('[data-action="toggle-favorite"]');
    if (!btn) return;

    if (!window.MMAIAuth || !window.MMAIAuth.isLoggedIn()) {
        btn.addEventListener("click", () => {
            location.href = `login.html?next=${encodeURIComponent("fighter.html?id=" + fighterId)}`;
        });
        btn.title = "Sign in to add to favorites";
        return;
    }

    let isFav = false;
    try {
        const resp = await window.MMAIAuth.authFetch("/api/auth/favorites/ids");
        if (resp.ok) {
            const data = await resp.json();
            isFav = (data.ids || []).includes(Number(fighterId));
        }
    } catch {}
    _updateStarBtn(btn, isFav);

    btn.addEventListener("click", async () => {
        const method = isFav ? "DELETE" : "POST";
        btn.disabled = true;
        try {
            const resp = await window.MMAIAuth.authFetch(
                `/api/auth/favorites/${fighterId}`, { method }
            );
            if (resp.ok) { isFav = !isFav; _updateStarBtn(btn, isFav); }
        } catch {}
        btn.disabled = false;
    });
}

function _updateStarBtn(btn, isFav) {
    btn.textContent = isFav ? "★" : "☆";
    btn.title = isFav ? "Remove from favorites" : "Add to favorites";
    btn.setAttribute("aria-label", isFav ? "Remove from favorites" : "Add to favorites");
    btn.classList.toggle("favorited", isFav);
}

// ---- Favoris : section accueil ----------------------------------------------

async function renderFavoritesSection() {
    const container = document.querySelector(".container");
    if (!container) return;
    const statsBar = document.getElementById("stats-bar");
    if (!statsBar) return;

    // Insere la section juste apres la stats bar
    let section = document.getElementById("favorites-section");
    if (!section) {
        section = document.createElement("section");
        section.id = "favorites-section";
        section.className = "section";
        section.style.display = "none";
        statsBar.parentNode.insertBefore(section, statsBar.nextSibling);
    }

    if (!window.MMAIAuth || !window.MMAIAuth.isLoggedIn()) {
        section.style.display = "none";
        return;
    }

    try {
        const resp = await window.MMAIAuth.authFetch("/api/auth/favorites");
        if (!resp.ok) return;
        const data = await resp.json();
        const favs = data.favorites || [];

        if (!favs.length) {
            section.style.display = "none";
            return;
        }

        section.style.display = "block";
        section.innerHTML = `
            <div class="section-head">
                <h2>★ My favorites</h2>
                <a href="favorites.html" class="section-head-link">View all →</a>
            </div>
            <div class="fav-list-container" id="favorites-strip">
                ${favs.slice(0, 5).map(f => {
                    const photo = f.photo_thumbnail_url;
                    const initial = esc((f.name || "?")[0].toUpperCase());
                    const photoContent = photo
                        ? `<img src="${esc(photo)}" alt="" loading="lazy" onerror="this.style.display='none'">`
                        : `<span class="fav-list-initial">${initial}</span>`;
                    const w = f.record_total_wins || 0, l = f.record_total_losses || 0;
                    const flagHTML = nationalityToFlagHTML(f.nationality || "");
                    const wc = esc(formatWeightClassLong(f.weight_class_current, f.gender) || "");
                    return `
                        <a href="fighter.html?id=${f.id}" class="fav-list-row">
                            <div class="fav-list-photo">${photoContent}</div>
                            <div class="fav-list-info">
                                <div class="fav-list-name-row">
                                    <span class="fav-list-name">${esc(f.name)}</span>
                                    ${flagHTML ? `<span class="fav-flag-inline">${flagHTML}</span>` : ""}
                                </div>
                                <div class="fav-list-cat">${wc}</div>
                            </div>
                            <div class="fav-list-record">${w}-${l}</div>
                        </a>`;
                }).join("")}
            </div>`;
    } catch {}
}

async function loadAndRenderHistory(fighterId) {
    const pane = document.querySelector('.tab-content[data-pane="history"]');
    if (!pane) return;
    pane.innerHTML = `<div class="loader" style="padding:40px;">${t("common.loading_history")}</div>`;
    try {
        const data = await api.fighterHistory(fighterId);
        pane.innerHTML = renderFightHistory(data);
        // Injecte la courbe d'evolution de l'Elo dans l'onglet Ratings (memes
        // donnees : le endpoint history renvoie aussi `elo_timeline`).
        renderEloTimeline(data.elo_timeline);
    } catch (e) {
        pane.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
    }
}

// ---- Courbe d'evolution de l'Elo (SVG vanilla, sans librairie) -------------

// Construit une carte avec un line chart SVG du base_elo combat par combat.
// timeline : [{date, elo, result, opponent_name, method, delta}, ...] (oldest->newest)
// Reutilise par la fiche fighter ET par le comparateur (window.buildEloChart).
function buildEloChart(timeline, opts = {}) {
    const pts = (timeline || []).filter(p => p && typeof p.elo === "number" && !Number.isNaN(p.elo));
    const title = esc(opts.title || t("profile.elo_evolution"));
    if (pts.length < 2) {
        return `
          <div class="elo-chart-head"><div class="elo-chart-title">${title}</div></div>
          <div class="elo-chart-empty">${t("profile.elo_not_enough")}</div>`;
    }

    const W = 760, H = 250, padL = 46, padR = 16, padT = 16, padB = 30;
    const innerW = W - padL - padR, innerH = H - padT - padB;

    const elos = pts.map(p => p.elo);
    let lo = Math.min(...elos), hi = Math.max(...elos);
    const span = Math.max(hi - lo, 40), mid = (hi + lo) / 2;
    lo = mid - span / 2 - span * 0.14;
    hi = mid + span / 2 + span * 0.14;

    const n = pts.length;
    const X = (i) => padL + (i / (n - 1)) * innerW;
    const Y = (v) => padT + innerH - ((v - lo) / (hi - lo)) * innerH;

    const grid = [0, 0.5, 1].map(frac => {
        const gy = padT + innerH * frac;
        const val = Math.round(hi - (hi - lo) * frac);
        return `<line class="elo-grid" x1="${padL}" y1="${gy.toFixed(1)}" x2="${W - padR}" y2="${gy.toFixed(1)}"/>`
             + `<text class="elo-axis-y" x="${padL - 8}" y="${(gy + 4).toFixed(1)}">${val}</text>`;
    }).join("");

    const linePts = pts.map((p, i) => `${X(i).toFixed(1)},${Y(p.elo).toFixed(1)}`).join(" ");
    const areaPts = `${X(0).toFixed(1)},${(padT + innerH).toFixed(1)} ${linePts} ${X(n - 1).toFixed(1)},${(padT + innerH).toFixed(1)}`;

    const dots = pts.map((p, i) => {
        const cls = p.result === "W" ? "w" : p.result === "L" ? "l" : "d";
        const sign = (p.delta > 0 ? "+" : "");
        const tip = `${p.date || ""} · ${p.result} vs ${p.opponent_name || "?"}`
                  + ` (${p.method || "?"}) · ${Math.round(p.elo)} (${sign}${p.delta})`;
        return `<circle class="elo-dot ${cls}" cx="${X(i).toFixed(1)}" cy="${Y(p.elo).toFixed(1)}" r="3.4"><title>${esc(tip)}</title></circle>`;
    }).join("");

    const yearOf = (d) => (d && d.length >= 4) ? d.slice(0, 4) : esc(d || "");
    const finalElo = Math.round(pts[n - 1].elo);
    const trend = finalElo - Math.round(pts[0].elo);
    const trendCls = trend > 0 ? "up" : trend < 0 ? "down" : "flat";
    const trendSign = trend > 0 ? "+" : "";

    return `
      <div class="elo-chart-head">
        <div>
          <div class="elo-chart-title">${title}</div>
          <div class="elo-chart-sub">${t("profile.elo_evolution_sub")}</div>
        </div>
        <div class="elo-chart-final">
          <span class="elo-final-val">${finalElo}</span>
          <span class="elo-final-trend ${trendCls}">${trendSign}${trend}</span>
        </div>
      </div>
      <div class="elo-chart-wrap">
        <svg viewBox="0 0 ${W} ${H}" class="elo-chart-svg" role="img" aria-label="Elo timeline">
          ${grid}
          <polygon class="elo-area" points="${areaPts}"/>
          <polyline class="elo-line" points="${linePts}"/>
          ${dots}
          <text class="elo-axis-x" x="${padL}" y="${H - 8}">${yearOf(pts[0].date)}</text>
          <text class="elo-axis-x end" x="${W - padR}" y="${H - 8}">${yearOf(pts[n - 1].date)}</text>
        </svg>
      </div>
      <div class="elo-chart-legend">
        <span><i class="elo-leg w"></i>${t("common.win")}</span>
        <span><i class="elo-leg l"></i>${t("common.loss")}</span>
        <span><i class="elo-leg d"></i>${t("common.draw")}</span>
      </div>`;
}
window.buildEloChart = buildEloChart;

// Injecte la courbe dans l'onglet Ratings de la fiche fighter (au-dessus des
// cartes de notes). Ne fait rien si moins de 2 points exploitables.
function renderEloTimeline(timeline) {
    if (!timeline || timeline.length < 2) return;
    const pane = document.querySelector('.tab-content[data-pane="ratings"]');
    if (!pane) return;
    const cardHtml = `<div class="stat-card elo-chart-card" id="elo-timeline-card" style="grid-column:1/-1;">${buildEloChart(timeline)}</div>`;
    const existing = pane.querySelector("#elo-timeline-card");
    if (existing) { existing.outerHTML = cardHtml; return; }
    const grid = pane.querySelector(".stat-grid");
    if (grid) grid.insertAdjacentHTML("afterbegin", cardHtml);
    else pane.insertAdjacentHTML("afterbegin", cardHtml);
}

// Rendu de l'historique : style proche Tapology/FightMatrix, cliquable si
// l'adversaire est dans notre BDD (sinon le row reste visible mais non clickable).
function renderFightHistory(data) {
    const fights = data && data.fights ? data.fights : [];
    if (!fights.length) {
        return `<div class="empty"><h3>${t("profile.no_history_title")}</h3><p>${t("profile.no_history_sub")}</p></div>`;
    }

    const rows = fights.map(f => renderFightRow(f)).join("");
    const matchedCount = fights.filter(f => f.opponent_id != null).length;

    return `
        <div class="history-header">
            <span class="history-count">${fights.length} ${t("common.fights")}</span>
            <span class="history-meta">${matchedCount} ${t("profile.history_linked_db")}</span>
        </div>
        <div class="fight-history-list">
            <div class="fight-row fight-row-header">
                <div class="th">${t("common.result")}</div>
                <div class="th">${t("common.opponent")}</div>
                <div class="th">${t("common.method")}</div>
                <div class="th">${t("common.event")}</div>
            </div>
            ${rows}
        </div>
    `;
}

function renderFightRow(f) {
    const result = (f.result || "").toUpperCase();
    const resultCls = result === "W" ? "win"
                    : result === "L" ? "loss"
                    : (result === "NC" || result === "N") ? "nc"
                    : "draw";
    const methodCls = (f.method || "").toLowerCase().replace(/\W/g, "");
    // Avatar adversaire encadre selon le resultat (W vert / L rouge / NC-D gris).
    const avatarCls = `opp-avatar res-${resultCls}`;

    // Format date "May 9, 2026" depuis ISO YYYY-MM-DD
    let dateStr = "";
    if (f.event_date) {
        try {
            const [y, m, d] = f.event_date.split("-");
            const monthName = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][parseInt(m,10)-1];
            dateStr = `${monthName} ${parseInt(d,10)}, ${y}`;
        } catch { dateStr = f.event_date; }
    }

    // Affichage du rank :
    //   - si opponent_rank_current dispo (en BDD) -> on l'affiche (rang actuel a jour)
    //   - sinon on affiche opponent_rank historique avec tooltip "at fight time"
    //   - sinon rien
    let rankBlock = "";
    if (f.opponent_rank_current) {
        rankBlock = `<div class="opp-rank current" title="Current rank">${esc(f.opponent_rank_current)}</div>`;
    }
    // On n'affiche PLUS le rang historique "#N at fight time" : il vient de
    // FightMatrix (embarque dans le nom de l'adversaire). On le garde en donnee
    // mais on ne l'expose pas tant qu'on n'a pas notre propre rang historique.

    const opponentBlock = f.opponent_id
        ? `<a class="opp-link" href="fighter.html?id=${f.opponent_id}" data-fighter-id="${f.opponent_id}" data-fighter-name="${esc(f.opponent_name)}" data-hc-restricted>
             ${f.opponent_photo
                ? `<div class="${avatarCls}" data-hc-zone><img src="${esc(f.opponent_photo)}" alt="${esc(f.opponent_name)}" loading="lazy" onerror="this.parentNode.classList.add('no-photo');this.parentNode.innerHTML='${esc(initials(f.opponent_name))}'"></div>`
                : `<div class="${avatarCls} no-photo" data-hc-zone>${esc(initials(f.opponent_name))}</div>`}
             <div class="opp-info">
                 <div class="opp-name" data-hc-zone>${esc(f.opponent_name)}</div>
                 ${rankBlock}
             </div>
           </a>`
        : `<div class="opp-link disabled" title="${t("profile.not_in_db")}">
             <div class="${avatarCls} no-photo">${esc(initials(f.opponent_name))}</div>
             <div class="opp-info">
                 <div class="opp-name">${esc(f.opponent_name)}</div>
                 ${rankBlock}
             </div>
           </div>`;

    const methodLine = [
        f.method_detail ? `${esc(f.method)} <span class="dim">·</span> ${esc(f.method_detail)}` : esc(f.method || "--"),
        f.round ? `Round ${f.round}` : "",
    ].filter(Boolean).join(`  <span class="dim">·</span>  `);

    return `
        <div class="fight-row">
            <div class="fight-result ${resultCls}">
                <div class="rcode">${esc(result || "?")}</div>
                ${f.method ? `<div class="mcode mcode-${methodCls}">${esc(f.method)}</div>` : ""}
            </div>
            <div class="fight-opponent">${opponentBlock}</div>
            <div class="fight-method">${methodLine}</div>
            <div class="fight-event">
                ${f.event_id
                    ? `<a class="event-name event-link" href="event.html?id=${f.event_id}">${esc(f.event_name || "--")}</a>`
                    : `<div class="event-name">${esc(f.event_name || "--")}</div>`}
                ${dateStr ? `<div class="event-date">${esc(dateStr)}</div>` : ""}
            </div>
        </div>
    `;
}

// ---- Scouter modal DBZ -------------------------------------------------------

// Vegeta-Scouter.gif = loading only → 6 GIFs distincts pour les résultats
// Densité sur 45–90 (là où sont la plupart des bons combattants)
const _SC_TIERS = [
    { max: 30,  gif: "/assets/gifs/Dessin Alien.gif",            label: "POWER LEVEL: LOW",       sub: "Earthling",      color: "#90caf9" },
    { max: 45,  gif: "/assets/gifs/Dragonball Z.gif",            label: "POWER LEVEL: AVERAGE",   sub: "Saiyan",         color: "#aed581" },
    { max: 60,  gif: "/assets/gifs/Fond D'écran Goku.gif",       label: "POWER LEVEL: HIGH",      sub: "Super Saiyan",   color: "#ffd740" },
    { max: 73,  gif: "/assets/gifs/freezer scouut.webp",         label: "POWER LEVEL: DANGEROUS", sub: "Frieza Level",   color: "#ce93d8" },
    { max: 88,  gif: "/assets/gifs/Végéta pierre volantes.gif",  label: "POWER LEVEL: ELITE",     sub: "Super Saiyan 2", color: "#ff9800" },
    { max: 101, gif: "/assets/gifs/Vegeta-casse.gif",            label: "POWER LEVEL: LEGENDARY", sub: "LEGENDARY",      color: "#ff5252" },
];
function _scTier(score) {
    if (score == null) return _SC_TIERS[1];
    return _SC_TIERS.find(t => score < t.max) || _SC_TIERS[_SC_TIERS.length - 1];
}

let _scAudioProfile = null;
function _playScSound() {
    try {
        if (!_scAudioProfile) { _scAudioProfile = new Audio("/assets/scouter.mp3"); _scAudioProfile.volume = 0.65; }
        _scAudioProfile.currentTime = 0;
        _scAudioProfile.play().catch(() => {});
    } catch (_) {}
}

function _animCount(el, target, dur = 1100) {
    if (target == null) { el.textContent = "--"; return; }
    const t0 = performance.now();
    (function step(now) {
        const p = Math.min((now - t0) / dur, 1);
        const e = 1 - Math.pow(1 - p, 3);
        el.textContent = (target * e).toFixed(1);
        if (p < 1) requestAnimationFrame(step);
        else el.textContent = target.toFixed(1);
    })(t0);
}

function openScouter(f) {
    const modal = document.createElement("div");
    modal.className = "scouter-modal";

    // Phase 1 : scan (Vegeta-Scouter.gif)
    modal.innerHTML = `
        <div class="scouter-backdrop"></div>
        <div class="scouter-window sc-dbz-window">
            <button class="scouter-close" aria-label="Close">&times;</button>

            <!-- Phase scan -->
            <div class="sc-dbz-scan-phase" id="sc-phase-scan">
                <div class="sc-dbz-gif-wrap">
                    <img src="/assets/gifs/Vegeta-Scouter.gif" class="sc-dbz-gif" alt="scanning">
                    <div class="sc-dbz-scanlines"></div>
                </div>
                <div class="sc-dbz-hud">
                    <div class="sc-dbz-hud-label">// SCOUTER READING //</div>
                    <div class="sc-dbz-target">TARGET : <strong>${esc(f.name)}</strong></div>
                    <div class="sc-dbz-status" id="sc-status">
                        SCANNING<span class="sc-dbz-blink">_</span>
                    </div>
                    <div class="sc-dbz-step" id="sc-step">Initializing...</div>
                    <div class="sc-dbz-progress-wrap">
                        <div class="sc-dbz-progress" id="sc-prog"></div>
                    </div>
                </div>
            </div>

            <!-- Phase révélation (remplie dynamiquement après appel API) -->
            <div class="sc-dbz-reveal-phase" id="sc-phase-reveal" style="display:none"></div>
        </div>
    `;

    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add("open"), 20);

    // le son dès l'ouverture de la modale
    _playScSound();

    const close = () => { modal.classList.remove("open"); setTimeout(() => modal.remove(), 250); };
    modal.querySelector(".scouter-close").addEventListener("click", close);
    modal.querySelector(".scouter-backdrop").addEventListener("click", close);
    document.addEventListener("keydown", function onEsc(e) {
        if (e.key === "Escape") { close(); document.removeEventListener("keydown", onEsc); }
    });

    // Appel API en parallèle pendant le scan
    const apiPromise = fetch(`/api/fighters/${f.id}/scouter`)
        .then(r => r.ok ? r.json() : Promise.reject(r.status))
        .catch(() => null);

    // Animation de scan (étapes)
    const stepEl = modal.querySelector("#sc-step");
    const progEl = modal.querySelector("#sc-prog");
    const steps = [
        "Reading career rating...",
        "Analyzing recent form...",
        "Evaluating opposition quality...",
        "Cross-checking external ratings...",
        "Computing technical skills...",
    ];
    let i = 0;
    const STEP_MS = 480;
    const interval = setInterval(() => {
        if (!document.body.contains(modal)) { clearInterval(interval); return; } // guard
        if (i < steps.length) {
            stepEl.textContent = steps[i];
            progEl.style.width = ((i + 1) / steps.length * 100) + "%";
            i++;
        } else {
            clearInterval(interval);
            // Attendre la réponse API avant de révéler
            apiPromise.then(data => {
                if (!document.body.contains(modal)) return;
                const score = data && data.scouter_rating != null ? Number(data.scouter_rating) : null;
                const tier = _scTier(score);

                const revealPhase = modal.querySelector("#sc-phase-reveal");
                revealPhase.innerHTML = `
                    <div class="sc-crt"></div>
                    <div class="sc-scan-line"></div>
                    <div class="sc-corner-tag" style="color:${tier.color};border-color:${tier.color}40">${tier.sub}</div>
                    <div class="sc-dbz-result-gif-wrap">
                        <img src="${tier.gif}" class="sc-dbz-result-gif" alt="${tier.sub}">
                        <div class="sc-gif-vignette"></div>
                    </div>
                    <div class="sc-readout">
                        <div class="sc-readout-header">
                            <span class="sc-dot" style="background:${tier.color}"></span>
                            <span class="sc-readout-title">MM.AI SCOUTER</span>
                            <span class="sc-dot" style="background:${tier.color}"></span>
                        </div>
                        <div class="sc-fighter-name">${esc(f.name)}</div>
                        <div class="sc-score-block">
                            <div class="sc-score-label">POWER LEVEL</div>
                            <div class="sc-score" id="sc-num" style="color:${tier.color};text-shadow:0 0 24px ${tier.color}">
                                ${score != null ? "0.0" : "--"}
                            </div>
                            <div class="sc-score-bar-wrap">
                                <div class="sc-score-bar-track">
                                    <div class="sc-score-bar-fill" id="sc-bar" style="background:${tier.color}"></div>
                                </div>
                            </div>
                        </div>
                        <div class="sc-tier-label" style="color:${tier.color};text-shadow:0 0 14px ${tier.color}60">${score != null ? tier.label : "NOT COMPUTED"}</div>
                        <div class="sc-dbz-formula">${score != null ? "35% Elo · 30% carrière · 20% ratings ext. · 15% skills" : "Pas assez de données"}</div>
                    </div>
                `;

                const scanPhase = modal.querySelector("#sc-phase-scan");
                scanPhase.style.opacity = "0";
                setTimeout(() => {
                    scanPhase.style.display = "none";
                    revealPhase.style.display = "flex";
                    setTimeout(() => revealPhase.classList.add("reveal-in"), 20);
                    if (score != null) {
                        setTimeout(() => {
                            _animCount(modal.querySelector("#sc-num"), score, 1200);
                            const bar = modal.querySelector("#sc-bar");
                            bar.style.transition = "width 1.2s cubic-bezier(0.22,1,0.36,1)";
                            bar.style.width = Math.min(score, 100) + "%";
                            // Mettre à jour la carte du profil
                            const cardVal = document.getElementById("fighter-scouter-card-val");
                            if (cardVal) cardVal.textContent = fmtNumber(score, 1);
                        }, 200);
                    }
                }, 300);
            });
        }
    }, STEP_MS);
}
window.openScouter = openScouter;

// ---- Report an issue modal --------------------------------------------------
const REPORT_TYPES = [
    { value: "wrong_record",  label: "Wrong record / results" },
    { value: "wrong_stats",   label: "Wrong stats or physical info" },
    { value: "wrong_photo",   label: "Wrong or missing photo" },
    { value: "outdated",      label: "Outdated information" },
    { value: "other",         label: "Other" },
];

function openReportModal({ fighter_id, fighter_name, event_id, event_name }) {
    if (document.getElementById("report-modal")) return;
    const title = fighter_name ? `Report an issue – ${fighter_name}`
                               : `Report an issue – ${event_name || "this event"}`;
    const modal = document.createElement("div");
    modal.id = "report-modal";
    modal.className = "report-modal";
    modal.innerHTML = `
        <div class="report-modal-box">
            <div class="report-modal-head">
                <h3>${esc(title)}</h3>
                <button type="button" class="report-modal-close" aria-label="Close">✕</button>
            </div>
            <form id="report-form">
                <div class="report-field">
                    <label class="report-label">Issue type</label>
                    <div class="report-types">
                        ${REPORT_TYPES.map((rt, i) => `
                            <label class="report-type-opt">
                                <input type="radio" name="report_type" value="${rt.value}"${i === 0 ? " checked" : ""}>
                                <span>${esc(rt.label)}</span>
                            </label>`).join("")}
                    </div>
                </div>
                <div class="report-field">
                    <label class="report-label" for="report-message">Details <span class="report-counter" id="report-counter">0/500</span></label>
                    <textarea id="report-message" class="report-textarea" placeholder="Describe the issue… (optional)" maxlength="500" rows="4"></textarea>
                </div>
                <div id="report-status" style="display:none;margin-bottom:10px;font-size:13px;"></div>
                <div class="report-actions">
                    <button type="submit" class="btn btn-primary" id="report-submit">Send report</button>
                    <button type="button" class="btn btn-ghost" id="report-cancel">Cancel</button>
                </div>
            </form>
        </div>`;
    document.body.appendChild(modal);

    const close = () => modal.remove();
    modal.querySelector(".report-modal-close").addEventListener("click", close);
    document.getElementById("report-cancel").addEventListener("click", close);
    modal.addEventListener("click", e => { if (e.target === modal) close(); });

    const ta = document.getElementById("report-message");
    const counter = document.getElementById("report-counter");
    ta.addEventListener("input", () => { counter.textContent = `${ta.value.length}/500`; });

    document.getElementById("report-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const type = modal.querySelector('input[name="report_type"]:checked')?.value || "other";
        const message = ta.value.trim();
        const submitBtn = document.getElementById("report-submit");
        const statusEl = document.getElementById("report-status");
        submitBtn.disabled = true; submitBtn.textContent = "Sending…";
        try {
            const resp = await fetch("/api/auth/reports", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ fighter_id: fighter_id ? Number(fighter_id) : null, event_id: event_id || null, report_type: type, message }),
            });
            if (resp.ok) {
                statusEl.style.color = "var(--success)";
                statusEl.textContent = "Report sent. Thank you!";
                statusEl.style.display = "block";
                setTimeout(close, 2000);
            } else {
                statusEl.style.color = "var(--primary-2)";
                statusEl.textContent = "Error sending report. Please try again.";
                statusEl.style.display = "block";
                submitBtn.disabled = false; submitBtn.textContent = "Send report";
            }
        } catch {
            statusEl.style.color = "var(--primary-2)";
            statusEl.textContent = "Network error. Please try again.";
            statusEl.style.display = "block";
            submitBtn.disabled = false; submitBtn.textContent = "Send report";
        }
    });
}
window.openReportModal = openReportModal;

/**
 * Retourne le texte des notes dans la langue active du site.
 * Chaine de fallback : langue courante → EN → FR → notes brutes.
 */
function getNote(f) {
    const nt = f.notes_translations;
    const lang = window.MMAILang ? window.MMAILang.get() : "en";
    if (nt && typeof nt === "object") {
        return nt[lang] || nt.en || nt.fr || f.notes || "";
    }
    return f.notes || "";
}

function renderFighterDetail(f) {
    // Banniere : photo_url Tapology (grande) en priorite ; thumbnail UFC-FR en fallback
    const photo = f.photo_url || f.photo_thumbnail_url;
    const photoBlock = photo
        ? `<img src="${esc(photo)}" alt="${esc(f.name)}" onerror="this.parentNode.innerHTML='<div class=&quot;no-photo&quot;>${esc(initials(f.name))}</div>'">`
        : `<div class="no-photo">${esc(initials(f.name))}</div>`;

    // Weight class : libelle long coherent partout dans le site
    // ("Bantamweight" pour les hommes, "Bantamweight (W)" pour les femmes).
    const weightDisplay = (f.weight_class_current && f.weight_class_current !== "Unknown")
        ? formatWeightClassLong(f.weight_class_current, f.gender)
        : "";

    // Drapeau via flag-icons (SVG, render correctement sur Windows/Edge contrairement aux emoji-flags).
    const flagHTML = nationalityToFlagHTML(f.nationality);

    // is_ufc_champion : ufc_official_rank = 0 par convention -> 0 est falsy en JS, faut tester is_ufc_champion d'ABORD.
    const tags = [];
    const isWoman = f.gender === "F";
    if (f.is_ufc_champion) tags.push(`<span class="profile-tag champ">${t("profile.ufc_champion")}</span>`);
    if (!f.is_ufc_champion && f.ufc_official_rank) tags.push(`<span class="profile-tag red">#${f.ufc_official_rank} UFC ${esc(weightDisplay)}</span>`);
    if (f.ufc_p4p_rank) tags.push(`<span class="profile-tag red">#${f.ufc_p4p_rank} P4P${isWoman ? " W" : ""}</span>`);
    if (f.mmai_rank) tags.push(`<span class="profile-tag mmai-rank">#${f.mmai_rank} MM.AI</span>`);
    if (weightDisplay && f.weight_class_current && f.weight_class_current !== "Unknown") {
        // Lien vers la page de la division (dédiée : champion + top 15 + tous les fighters)
        tags.push(`<a href="division.html?wc=${encodeURIComponent(f.weight_class_current)}&gender=${encodeURIComponent(f.gender || "M")}" class="profile-tag clickable">${esc(weightDisplay)}</a>`);
    } else if (weightDisplay) {
        tags.push(`<span class="profile-tag">${esc(weightDisplay)}</span>`);
    }
    if (f.current_league) tags.push(`<span class="profile-tag league">${esc(f.current_league)}</span>`);
    if (f.nationality) {
        tags.push(`<span class="profile-tag">${flagHTML}${flagHTML ? " " : ""}${esc(nationalityEnglish(f.nationality))}</span>`);
    }
    if (f.stance) tags.push(`<span class="profile-tag">${esc(f.stance)}</span>`);
    if (!f.is_active) tags.push(`<span class="profile-tag">${t("common.inactive")}</span>`);

    const w = f.record_total_wins ?? 0, l = f.record_total_losses ?? 0, d = f.record_total_draws ?? 0, nc = f.record_total_nc ?? 0;
    const totalWins = w || 1;
    const ko = f.wins_by_ko_tko ?? 0, sub = f.wins_by_submission ?? 0, dec = f.wins_by_decision ?? 0;
    const koPct  = Math.round(100 * ko / totalWins);
    const subPct = Math.round(100 * sub / totalWins);
    const decPct = Math.round(100 * dec / totalWins);
    const totalLosses = l || 1;
    const lko = f.losses_by_ko_tko ?? 0, lsub = f.losses_by_submission ?? 0, ldec = f.losses_by_decision ?? 0;
    const lkoPct  = Math.round(100 * lko / totalLosses);
    const lsubPct = Math.round(100 * lsub / totalLosses);
    const ldecPct = Math.round(100 * ldec / totalLosses);

    // Hauteur/allonge : on retire le " in" en suffixe. La valeur scrappée
    // contient deja les guillemets (ex: 5'5" / 66.1") -> on n'ajoute plus rien.
    const heightStr = formatLengthPref(f.height_inches);
    const reachStr  = formatLengthPref(f.reach_inches);

    return `
        <section class="profile-hero">
            <div class="container">
                <a href="fighters.html" class="back-link" onclick="if(history.length>1){event.preventDefault();history.back();}">${t("common.back")}</a>
                <div class="profile-grid">
                    <div class="profile-photo">${photoBlock}</div>
                    <div>
                        <div class="profile-name-row">
                            <h1 class="profile-name">${esc(f.name)}</h1>
                            <button class="btn btn-ghost profile-fav-btn profile-fav-name" data-action="toggle-favorite" data-fighter-id="${f.id}" title="Add to favorites" aria-label="Add to favorites">☆</button>
                        </div>
                        ${f.nickname ? `<div class="profile-nickname">"${esc(f.nickname)}"</div>` : ""}
                        <div class="profile-tags">${tags.join("")}</div>
                        <div class="profile-record-big">
                            <div class="rec"><span class="w">${w}</span>-<span class="l">${l}</span>${d>0?`-<span class="d">${d}</span>`:""}${nc>0?`<span class="record-nc"> (${nc} NC)</span>`:""}</div>
                            <div>
                                <div class="label">${t("profile.pro_record")}</div>
                            </div>
                        </div>
                        <div class="profile-quick">
                            <div class="quick-card"><div class="lbl">${t("common.win_pct")}</div><div class="val">${f.win_percentage_int != null ? f.win_percentage_int + "%" : "--"}</div></div>
                            <div class="quick-card"><div class="lbl">${t("common.finish_pct")}</div><div class="val">${f.finish_rate_int != null ? f.finish_rate_int + "%" : "--"}</div></div>
                            <div class="quick-card"><div class="lbl">${t("common.age")}</div><div class="val">${num(f.age)}</div></div>
                            <div class="quick-card"><div class="lbl">${t("common.height")}</div><div class="val" style="font-size:18px;">${esc(heightStr)}</div></div>
                            <div class="quick-card"><div class="lbl">${t("common.reach")}</div><div class="val" style="font-size:18px;">${esc(reachStr)}</div></div>
                        </div>
                        <div class="profile-last5-inline">
                            <span class="profile-last5-label">${t("profile.lbl_last5")}</span>
                            <span class="profile-last5-pills">${last5Pills(f.last_5_results) || '<span class="muted">--</span>'}</span>
                        </div>
                        <div class="profile-actions">
                            <a href="matchmaking.html?id1=${f.id}" class="btn btn-primary">${t("profile.matchmake_btn")}</a>
                            <button class="btn btn-ghost" data-action="open-scouter" data-id="${f.id}">${t("profile.calculate_scouter")}</button>
                            ${pinButtonHTML(f, "text")}
                        </div>
                    </div>
                </div>
            </div>
        </section>

        ${(() => {
            const noteText = getNote(f);
            if (!noteText) return "";
            // on stocke toutes les traductions dans un data-attribute pour que le
            // paragraphe change direct quand l'user switch de langue (sans recharger)
            const noteLangsAttr = esc(JSON.stringify(f.notes_translations || {}));
            return `
        <div class="container">
            <div class="fighter-bio-section">
                <p class="fighter-bio-text" data-bio-note data-note-langs="${noteLangsAttr}" data-fallback="${esc(f.notes || "")}">${esc(noteText)}</p>
            </div>
        </div>`;
        })()}

        <div class="container">
            <div class="profile-tabs">
                <button class="tab-btn" data-tab="stats">${t("profile.tab_stats")}</button>
                <button class="tab-btn" data-tab="ratings">${t("profile.tab_ratings")}</button>
                <button class="tab-btn active" data-tab="history">${t("profile.tab_history")}</button>
                <button class="tab-btn" data-tab="career">${t("profile.tab_career")}</button>
                <button class="tab-btn" data-tab="bio">${t("profile.tab_bio")}</button>
            </div>

            <div class="tab-content" data-pane="stats">
                <div class="stat-grid">
                    <div class="stat-card">
                        <h3>${t("profile.win_methods")}</h3>
                        <div class="methods-viz">
                            <div class="method-bar"><span class="name">KO/TKO</span><span class="track"><span class="fill" data-w="${koPct}" style="width:0%"></span></span><span class="pct">${ko} (${koPct}%)</span></div>
                            <div class="method-bar"><span class="name">Submission</span><span class="track"><span class="fill" data-w="${subPct}" style="width:0%"></span></span><span class="pct">${sub} (${subPct}%)</span></div>
                            <div class="method-bar"><span class="name">Decision</span><span class="track"><span class="fill" data-w="${decPct}" style="width:0%"></span></span><span class="pct">${dec} (${decPct}%)</span></div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <h3>${t("profile.loss_methods")}</h3>
                        <div class="methods-viz">
                            <div class="method-bar loss"><span class="name">KO/TKO</span><span class="track"><span class="fill" data-w="${lkoPct}" style="width:0%"></span></span><span class="pct">${lko} (${lkoPct}%)</span></div>
                            <div class="method-bar loss"><span class="name">Submission</span><span class="track"><span class="fill" data-w="${lsubPct}" style="width:0%"></span></span><span class="pct">${lsub} (${lsubPct}%)</span></div>
                            <div class="method-bar loss"><span class="name">Decision</span><span class="track"><span class="fill" data-w="${ldecPct}" style="width:0%"></span></span><span class="pct">${ldec} (${ldecPct}%)</span></div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <h3>${t("profile.detailed_record")}</h3>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_total")}</span><span class="val">${w}-${l}${d>0?"-"+d:""}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_ufc_record")}</span><span class="val">${num(f.record_ufc_wins,0)}-${num(f.record_ufc_losses,0)}${(f.record_ufc_draws||0)>0?"-"+f.record_ufc_draws:""}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_non_ufc")}</span><span class="val">${num(f.record_other_wins,0)}-${num(f.record_other_losses,0)}${(f.record_other_draws||0)>0?"-"+f.record_other_draws:""}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_nc")}</span><span class="val">${num(f.record_total_nc,0)}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_title_wins")}</span><span class="val">${num(f.ufc_title_match_win,0)}</span></div>
                    </div>
                    <div class="stat-card">
                        <h3>${t("profile.recent_form_section")}</h3>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_last5")}</span><span class="val">${last5Pills(f.last_5_results)}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_streak")}</span><span class="val">${streakPill(f.current_streak)}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_form_score")}</span><span class="val">${f.recent_form_score != null ? fmtNumber(f.recent_form_score, 3) : '<span class="muted">--</span>'}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_days_inactive")}</span><span class="val">${num(f.days_inactive)}</span></div>
                    </div>
                </div>
            </div>

            <div class="tab-content" data-pane="ratings">
                <div class="stat-grid">
                    <div class="stat-card">
                        <h3>${t("profile.mmai_ratings")}</h3>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_base_elo")}</span><span class="val" style="color:var(--primary-2)">${f.base_elo != null ? fmtNumber(f.base_elo, 1) : `<span class="muted">${t("profile.not_computed")}</span>`}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_scouter")}</span><span class="val" style="color:var(--gold)" id="fighter-scouter-card-val"><span class="muted">${t("profile.not_computed")}</span></span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_form_score")}</span><span class="val">${f.recent_form_score != null ? fmtNumber(f.recent_form_score, 3) : '<span class="muted">--</span>'}</span></div>
                    </div>
                    <div class="stat-card">
                        <h3>${t("profile.career_highlights")}</h3>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_big_league")}</span><span class="val">${esc(f.fightmatrix_big_league_record || "--")}</span></div>
                    </div>
                    <div class="stat-card">
                        <h3>${t("profile.ufc_rankings_section")}</h3>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_ufc_div")}</span><span class="val">${
                            f.is_ufc_champion
                                ? `<span style="color:var(--gold); font-weight:700;">${t("common.champion")}</span>`
                                : (f.ufc_official_rank ? "#" + f.ufc_official_rank : `<span class="muted">${t("common.unranked")}</span>`)
                        }</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_p4p")}</span><span class="val">${f.ufc_p4p_rank ? "#" + f.ufc_p4p_rank + (isWoman ? " W" : "") : `<span class="muted">${t("common.unranked")}</span>`}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_champion_status")}</span><span class="val">${f.is_ufc_champion ? `<span style="color:var(--gold)">${t("common.yes")}</span>` : t("common.no")}</span></div>
                    </div>
                    ${f.mmai_rank ? `
                    <div class="stat-card">
                        <h3>${t("profile.mmai_ranking_section")}</h3>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_mmai_div_rank")}</span><span class="val" style="color:var(--primary-2); font-weight:700;">#${f.mmai_rank} <span style="font-size:12px; color:var(--text-muted);">${esc(weightDisplay)}</span></span></div>
                    </div>` : ""}
                </div>
            </div>

            <div class="tab-content active" data-pane="history">
                <div class="loader" style="padding:40px;">${t("common.loading_history")}</div>
            </div>

            <div class="tab-content" data-pane="career">
                <div class="stat-grid">
                    <div class="stat-card">
                        <h3>${t("profile.personal_info")}</h3>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_fullname")}</span><span class="val">${esc(f.name)}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_nickname")}</span><span class="val">${esc(f.nickname || "--")}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_gender")}</span><span class="val">${f.gender === "F" ? t("common.female") : t("common.male")}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_dob")}</span><span class="val">${f.date_of_birth ? f.date_of_birth : "--"}</span></div>
                        <div class="stat-row"><span class="lbl">${t("common.age")}</span><span class="val">${num(f.age)}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_nationality")}</span><span class="val">${f.nationality ? `${flagHTML}${flagHTML ? " " : ""}${esc(nationalityEnglish(f.nationality))}` : "--"}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_first_sport")}</span><span class="val">${esc(f.first_sport || "--")}</span></div>
                    </div>
                    <div class="stat-card">
                        <h3>${t("profile.physical_profile")}</h3>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_current_div")}</span><span class="val">${esc(weightDisplay || "--")}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_origin_div")}</span><span class="val">${esc(f.weight_class_origin || "--")}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_current_league")}</span><span class="val">${esc(f.current_league || "--")}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_height")}</span><span class="val">${heightStr}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_reach")}</span><span class="val">${reachStr}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_stance")}</span><span class="val">${esc(f.stance || "--")}</span></div>
                    </div>
                    <div class="stat-card">
                        <h3>${t("profile.career_section")}</h3>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_debut")}</span><span class="val">${f.career_debut_date || "--"}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_last_fight")}</span><span class="val">${f.last_fight_date || "--"}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_inactive_since")}</span><span class="val">${formatInactiveSince(f.last_fight_date, f.days_inactive)}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_total_fights")}</span><span class="val">${num(f.total_fights, 0)}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_is_active")}</span><span class="val">${f.is_active ? t("common.yes") : t("common.no")}</span></div>
                    </div>
                </div>
            </div>

            <div class="tab-content" data-pane="bio">
                <div class="stat-grid">
                    <div class="stat-card">
                        <h3>${t("profile.physical_profile")}</h3>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_height")}</span><span class="val">${esc(heightStr)}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_reach")}</span><span class="val">${esc(reachStr)}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_stance")}</span><span class="val">${esc(f.stance || "--")}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_current_div")}</span><span class="val">${esc(weightDisplay || "--")}</span></div>
                        <div class="stat-row"><span class="lbl">${t("common.age")}</span><span class="val">${num(f.age)}</span></div>
                        <div class="stat-row"><span class="lbl">${t("profile.lbl_nationality")}</span><span class="val">${f.nationality ? `${flagHTML}${flagHTML ? " " : ""}${esc(nationalityEnglish(f.nationality))}` : "--"}</span></div>
                    </div>
                </div>
            </div>
        </div>

        <div class="container">
            <div class="report-issue-bar">
                <button type="button" class="report-issue-link" data-action="open-report" data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-2px;margin-right:6px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                    Report an issue with this fighter
                </button>
            </div>
        </div>
    `;
}

function wireProfileTabs() {
    $$(".tab-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const tab = btn.dataset.tab;
            $$(".tab-btn").forEach(b => b.classList.toggle("active", b === btn));
            $$(".tab-content").forEach(c => c.classList.toggle("active", c.dataset.pane === tab));
            if (tab === "stats") animateBars();
        });
    });
}

function animateBars() {
    requestAnimationFrame(() => {
        $$(".method-bar .fill").forEach(el => {
            const w = el.dataset.w;
            if (w !== undefined) {
                const pct = parseFloat(w) || 0;
                el.style.width   = pct + "%";
                // Si 0% : on masque complètement la barre (même les 6px min-width CSS)
                el.style.opacity = pct === 0 ? "0" : "1";
            }
        });
    });
}

// ---- Nav: Events dropdown (injecté dans .nav-links sur chaque page) --------

const _MMA_PROMOTIONS = [
    { code: "UFC",     label: "UFC" },
    { code: "PFL",     label: "PFL" },
    { code: "ONE",     label: "ONE Championship" },
    { code: "BELLATOR",label: "Bellator" },
    { code: "KSW",     label: "KSW" },
    { code: "RIZIN",   label: "Rizin FF" },
    { code: "BKFC",    label: "BKFC" },
    { code: "LFA",     label: "LFA" },
    { code: "CAGE WARRIORS", label: "Cage Warriors" },
    { code: "INVICTA", label: "Invicta FC" },
];

async function setupEventsNav() {
    const navLinks = document.querySelector(".nav-links");
    if (!navLinks || navLinks.dataset.eventsInjected) return;
    navLinks.dataset.eventsInjected = "1";

    // Reperer l'ancre courante pour mettre .active sur "Events" si on est sur events/event
    const path = location.pathname.split("/").pop();
    const isActive = ["events.html", "event.html"].includes(path);

    // Le dropdown
    const wrap = document.createElement("div");
    wrap.className = "nav-events-dropdown";
    wrap.innerHTML = `
        <a href="events.html?type=upcoming" class="nav-events-trigger ${isActive ? "active" : ""}" data-i18n="nav.events">
            ${t("nav.events")} <span class="nav-caret">&#9662;</span>
        </a>
        <div class="nav-events-panel">
            <div class="nav-events-cols">
                <div class="nav-events-col">
                    <div class="nav-events-col-head">${t("nav.ufc_events")}</div>
                    <a href="events.html?type=upcoming&promotion=UFC">${t("nav.ufc_upcoming")}</a>
                    <a href="events.html?type=results&promotion=UFC">${t("nav.ufc_recent")}</a>
                    <a href="events.html?type=all&promotion=UFC">${t("nav.ufc_all")}</a>
                </div>
                <div class="nav-events-col">
                    <div class="nav-events-col-head">${t("nav.all_mma")}</div>
                    <a href="events.html?type=upcoming">${t("nav.mma_upcoming")}</a>
                    <a href="events.html?type=results">${t("nav.mma_recent")}</a>
                    <a href="events.html?type=all">${t("nav.mma_all")}</a>
                </div>
                <div class="nav-events-col">
                    <div class="nav-events-col-head">${t("nav.promotions")}</div>
                    ${_MMA_PROMOTIONS.map(p =>
                        `<a href="events.html?type=all&promotion=${encodeURIComponent(p.code)}">${esc(p.label)}</a>`
                    ).join("")}
                </div>
                <div class="nav-events-col nav-events-col-list">
                    <div class="nav-events-col-head">${t("nav.coming_up")}</div>
                    <div class="nav-events-list" id="nav-events-list"><span class="muted">${t("common.loading")}...</span></div>
                </div>
            </div>
        </div>
    `;

    // Inserer le dropdown apres "Matchmaking" (juste avant "Analytics") pour rester thematique
    const matchmakingLink = Array.from(navLinks.querySelectorAll("a"))
        .find(a => /matchmaking\.html$/i.test(a.getAttribute("href") || ""));
    if (matchmakingLink && matchmakingLink.nextSibling) {
        navLinks.insertBefore(wrap, matchmakingLink.nextSibling);
    } else {
        navLinks.appendChild(wrap);
    }

    // Charge les 5 prochains events pour la colonne "Coming up next"
    try {
        const data = await api.events({ status: "upcoming", sort: "asc", limit: 5 });
        const list = $("#nav-events-list");
        if (data && data.events && data.events.length) {
            list.innerHTML = data.events.map(ev => {
                const dt = ev.date ? new Date(ev.date) : null;
                const dateStr = dt
                    ? dt.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
                    : "";
                return `
                    <a href="event.html?id=${ev.id}" class="nav-events-item">
                        <div class="nav-events-item-name">${esc(ev.name || "—")}</div>
                        <div class="nav-events-item-meta">
                            ${ev.promotion ? `<span class="nav-events-item-promo">${esc(ev.promotion)}</span>` : ""}
                            ${dateStr ? `<span class="nav-events-item-date">${esc(dateStr)}</span>` : ""}
                        </div>
                    </a>`;
            }).join("");
        } else {
            list.innerHTML = `<span class="muted" style="font-size:12px;">No upcoming events in database yet.</span>`;
        }
    } catch (e) {
        const list = $("#nav-events-list");
        if (list) list.innerHTML = `<span class="muted" style="font-size:12px;">—</span>`;
    }
}

// ---- Nav: Rankings dropdown (injecté dans .nav-links sur chaque page) -------

function setupRankingsNav() {
    const navLinks = document.querySelector(".nav-links");
    if (!navLinks || navLinks.dataset.rankingsInjected) return;
    navLinks.dataset.rankingsInjected = "1";

    // Trouver le lien Rankings existant
    const rankingsLink = Array.from(navLinks.querySelectorAll("a"))
        .find(a => /rankings\.html$/i.test(a.getAttribute("href") || ""));
    if (!rankingsLink) return;

    const path = location.pathname.split("/").pop();
    const isActive = ["rankings.html", "ranking.html", "p4p.html"].includes(path);

    const MEN_CLASSES = [
        "Flyweight", "Bantamweight", "Featherweight", "Lightweight",
        "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight"
    ];
    const WOMEN_CLASSES = [
        "Atomweight", "Strawweight", "Flyweight",
        "Bantamweight", "Featherweight", "Lightweight"
    ];

    const wrap = document.createElement("div");
    wrap.className = "nav-rankings-dropdown";
    wrap.innerHTML = `
        <a href="rankings.html" class="nav-rankings-trigger ${isActive ? "active" : ""}" data-i18n="nav.rankings">
            ${t("nav.rankings")} <span class="nav-caret">&#9662;</span>
        </a>
        <div class="nav-rankings-panel">
            <div class="nav-rankings-cols">
                <div class="nav-rankings-col">
                    <div class="nav-rankings-col-head" data-i18n="common.men">${t("common.men")}</div>
                    ${MEN_CLASSES.map(wc =>
                        `<a href="ranking.html?wc=${encodeURIComponent(wc)}&gender=M">${esc(wc)}</a>`
                    ).join("")}
                </div>
                <div class="nav-rankings-col">
                    <div class="nav-rankings-col-head" data-i18n="common.women">${t("common.women")}</div>
                    ${WOMEN_CLASSES.map(wc =>
                        `<a href="ranking.html?wc=${encodeURIComponent(wc)}&gender=F">${esc(wc)}</a>`
                    ).join("")}
                </div>
            </div>
        </div>
    `;

    // Remplacer le lien Rankings par le dropdown
    rankingsLink.parentElement.replaceChild(wrap, rankingsLink);
}

// ---- Nav: Settings dropdown (gear icon top-right) --------------------------

function setupSettingsNav() {
    const navInner = document.querySelector(".nav-inner");
    if (!navInner || navInner.dataset.settingsInjected) return;
    navInner.dataset.settingsInjected = "1";

    const isActive = /settings\.html$/i.test(location.pathname);

    const wrap = document.createElement("div");
    wrap.className = "nav-settings";
    wrap.innerHTML = `
        <a href="settings.html" class="nav-settings-trigger ${isActive ? "active" : ""}" aria-label="Settings" title="Settings">
            <svg class="nav-settings-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
            </svg>
        </a>
        <div class="nav-settings-panel" role="menu">
            <div class="nav-settings-section" data-i18n="nav.account_section">Account</div>
            <a href="settings.html#account" class="nav-settings-item" data-auth-visibility="logged-in">
                <svg class="nsi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                    <circle cx="12" cy="7" r="4"></circle>
                </svg>
                <span data-i18n="nav.my_account">My account</span>
            </a>
            <a href="register.html" class="nav-settings-item" data-auth-visibility="logged-out">
                <svg class="nsi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path>
                    <circle cx="9" cy="7" r="4"></circle>
                    <line x1="19" y1="8" x2="19" y2="14"></line>
                    <line x1="22" y1="11" x2="16" y2="11"></line>
                </svg>
                <span data-i18n="nav.sign_up">Sign up</span>
            </a>
            <a href="login.html" class="nav-settings-item" data-auth-visibility="logged-out">
                <svg class="nsi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path>
                    <polyline points="10 17 15 12 10 7"></polyline>
                    <line x1="15" y1="12" x2="3" y2="12"></line>
                </svg>
                <span data-i18n="nav.log_in">Log in</span>
            </a>
            <div class="nav-settings-divider"></div>
            <div class="nav-settings-section" data-i18n="nav.prefs_section">Preferences</div>
            <button type="button" class="nav-settings-item" data-action="toggle-theme">
                <svg class="nsi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                </svg>
                <span data-theme-label>Switch theme</span>
            </button>
            <a href="settings.html" class="nav-settings-item">
                <svg class="nsi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="3"></circle>
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                </svg>
                <span data-i18n="nav.all_settings">All settings</span>
            </a>
            <div class="nav-settings-divider"></div>
            <button type="button" class="nav-settings-item danger" data-action="settings-logout" data-auth-visibility="logged-in">
                <svg class="nsi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                    <polyline points="16 17 21 12 16 7"></polyline>
                    <line x1="21" y1="12" x2="9" y2="12"></line>
                </svg>
                <span data-i18n="nav.log_out">Log out</span>
            </button>
        </div>
    `;

    // On regroupe la nav-search et le bouton settings dans un wrapper flex
    // (sinon `justify-content: space-between` du parent disperse trop les items).
    const searchWrap = navInner.querySelector(".nav-search");
    if (searchWrap) {
        let rightCluster = navInner.querySelector(".nav-right-cluster");
        if (!rightCluster) {
            rightCluster = document.createElement("div");
            rightCluster.className = "nav-right-cluster";
            searchWrap.parentNode.insertBefore(rightCluster, searchWrap);
            rightCluster.appendChild(searchWrap);
        }
        rightCluster.appendChild(wrap);
    } else {
        navInner.appendChild(wrap);
    }

    // Sync auth-dependent items visibility
    function syncSettingsAuth() {
        const loggedIn = !!(window.MMAIAuth && window.MMAIAuth.isLoggedIn());
        wrap.querySelectorAll("[data-auth-visibility]").forEach(el => {
            const v = el.dataset.authVisibility;
            el.style.display = (v === "logged-in" && !loggedIn) || (v === "logged-out" && loggedIn) ? "none" : "";
        });
    }
    syncSettingsAuth();
    window.addEventListener("mmai:auth-change", syncSettingsAuth);

    // on met a jour le label du theme dans le menu
    const themeLabel = wrap.querySelector("[data-theme-label]");
    const updateThemeLabel = () => {
        if (!themeLabel) return;
        const cur = window.MMAITheme ? window.MMAITheme.get() : "dark";
        themeLabel.textContent = typeof t === "function"
            ? (cur === "light" ? t("nav.switch_dark") : t("nav.switch_light"))
            : (cur === "light" ? "Switch to dark" : "Switch to light");
    };
    updateThemeLabel();
    window.addEventListener("mmai:theme-change", updateThemeLabel);
    window.addEventListener("mmai:lang-change", updateThemeLabel);

    // petit toggle rapide depuis le menu
    const toggleBtn = wrap.querySelector('[data-action="toggle-theme"]');
    if (toggleBtn) {
        toggleBtn.addEventListener("click", (e) => {
            e.preventDefault();
            const cur = window.MMAITheme ? window.MMAITheme.get() : "dark";
            window.MMAITheme.set(cur === "light" ? "dark" : "light");
        });
    }

    // Logout depuis le settings dropdown (delegue a MMAIAuth si dispo)
    const logoutBtn = wrap.querySelector('[data-action="settings-logout"]');
    if (logoutBtn) {
        logoutBtn.addEventListener("click", async () => {
            if (!window.MMAIAuth || !window.MMAIAuth.isLoggedIn()) {
                location.href = "login.html";
                return;
            }
            try { await window.MMAIAuth.authFetch("/api/auth/logout", { method: "POST" }); } catch {}
            window.MMAIAuth.clearSession();
            location.href = "index.html";
        });
    }
}

// ---- Nav search ------------------------------------------------------------

function setupNavSearch() {
    // Injecte aussi le dropdown Events/Rankings + le bouton auth (idempotents grace aux flags).
    // Ordre voulu dans le rightCluster : search → auth-button/chip → settings-gear.
    setupEventsNav();
    setupRankingsNav();
    if (window.MMAIAuth && typeof window.MMAIAuth.setupAuthNav === "function") {
        window.MMAIAuth.setupAuthNav();
    }
    setupSettingsNav();

    const input = $("#nav-search");
    if (!input) return;

    // Cree le panneau de resultats s'il n'existe pas deja (frere de l'input dans .nav-search).
    let panel = input.parentElement.querySelector(".nav-search-results");
    if (!panel) {
        panel = document.createElement("div");
        panel.className = "nav-search-results";
        input.parentElement.appendChild(panel);
    }

    const close = () => { panel.classList.remove("open"); panel.innerHTML = ""; };

    // Fermeture quand on clique ailleurs
    document.addEventListener("click", (e) => {
        if (!input.parentElement.contains(e.target)) close();
    });

    // Enter -> page Fighters avec le query (fallback recherche complete)
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            const q = input.value.trim();
            if (!q) return;
            location.href = `fighters.html?q=${encodeURIComponent(q)}`;
        } else if (e.key === "Escape") {
            close(); input.blur();
        }
    });

    const render = (fighters) => {
        if (!fighters || !fighters.length) {
            panel.innerHTML = `<div class="ns-empty">${t("common.no_fighter_db")}</div>`;
            panel.classList.add("open");
            return;
        }
        panel.innerHTML = fighters.map(f => {
            const photo = f.photo_thumbnail_url || f.photo_url;
            const avatarHtml = photo
                ? `<img src="${esc(photo)}" alt="" onerror="this.parentNode.innerHTML='<span class=&quot;ns-initials&quot;>${esc(initials(f.name))}</span>'">`
                : `<span class="ns-initials">${esc(initials(f.name))}</span>`;
            const w = f.record_total_wins ?? 0;
            const l = f.record_total_losses ?? 0;
            const d = f.record_total_draws ?? 0;
            const recStr = d > 0 ? `${w}-${l}-${d}` : `${w}-${l}`;
            const flag = nationalityToFlagHTML(f.nationality);
            const sub = f.weight_class_current && f.weight_class_current !== "Unknown" ? f.weight_class_current : "MMA";
            return `
              <a class="ns-row" href="fighter.html?id=${f.id}">
                <span class="ns-photo">${avatarHtml}</span>
                <span class="ns-info">
                  ${f.nickname ? `<span class="ns-nick">${esc(f.nickname)}</span>` : ""}
                  <span class="ns-name">${esc(f.name)}</span>
                  <span class="ns-sub">${esc(sub)}</span>
                </span>
                <span class="ns-record">${recStr}</span>
                <span class="ns-flag">${flag || '<span class="ns-flag-blank"></span>'}</span>
              </a>
            `;
        }).join("") + `
          <a class="ns-row ns-row-all" href="fighters.html?q=${encodeURIComponent(input.value.trim())}">
            <span>${t("common.view_all_results")} &raquo;</span>
          </a>
        `;
        panel.classList.add("open");
    };

    const search = debounce(async () => {
        const q = input.value.trim();
        if (q.length < 2) { close(); return; }
        try {
            const data = await api.fighters({ search: q, limit: 8 });
            render(data.fighters || []);
        } catch (e) {
            panel.innerHTML = `<div class="ns-empty">Error: ${esc(e.message)}</div>`;
            panel.classList.add("open");
        }
    }, 220);

    input.addEventListener("input", search);
    input.addEventListener("focus", () => {
        if (input.value.trim().length >= 2) search();
    });
    if (typeof applyTranslations === "function") applyTranslations();
}

/* ===========================================================================
   UX++  —  comparateur rapide, recemment consultes, hover-card fighter
   Tout en local (localStorage), zero appel base. Charge sur toutes les pages.
   =========================================================================== */

// ---- Store : comparateur rapide (max 2) ------------------------------------
window.MMAICompare = (function () {
    const KEY = "mmai-compare", CAP = 2;
    function fire() { window.dispatchEvent(new CustomEvent("mmai:compare-change")); }
    function list() { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; } }
    function save(a) { try { localStorage.setItem(KEY, JSON.stringify(a)); } catch (e) {} fire(); }
    function has(id) { return list().some(x => Number(x.id) === Number(id)); }
    function toggle(f) {
        if (!f || !f.id) return;
        let a = list();
        if (has(f.id)) a = a.filter(x => Number(x.id) !== Number(f.id));
        else { a.push({ id: Number(f.id), name: f.name, photo: f.photo || "" }); if (a.length > CAP) a = a.slice(a.length - CAP); }
        save(a);
    }
    function remove(id) { save(list().filter(x => Number(x.id) !== Number(id))); }
    function clear() { save([]); }
    return { list, has, toggle, remove, clear };
})();

// ---- Store : recemment consultes (max 10) ----------------------------------
window.MMAIRecent = (function () {
    const KEY = "mmai-recent", MAX = 7;
    function list() { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; } }
    function save(a) { try { localStorage.setItem(KEY, JSON.stringify(a)); } catch (e) {} }
    function push(f) {
        if (!f || !f.id) return;
        let a = list().filter(x => Number(x.id) !== Number(f.id));
        a.unshift({ id: Number(f.id), name: f.name,
                    photo: f.photo_thumbnail_url || f.photo_url || "",
                    wc: f.weight_class_current || "", gender: f.gender || "" });
        if (a.length > MAX) a = a.slice(0, MAX);
        save(a);
    }
    function clear() { save([]); }
    return { list, push, clear };
})();

(function uxEnhancements() {

    // --- Tray flottant du comparateur ---
    function renderCompareTray() {
        let tray = document.getElementById("mm-cmp-tray");
        const items = window.MMAICompare.list();
        if (!tray) {
            tray = document.createElement("div");
            tray.id = "mm-cmp-tray";
            tray.className = "mm-cmp-tray";
            document.body.appendChild(tray);
        }
        if (!items.length) { tray.classList.remove("open"); tray.innerHTML = ""; return; }

        const slot = (f) => {
            const ph = f.photo
                ? `<img src="${esc(f.photo)}" alt="" loading="lazy">`
                : `<span class="ph">${esc(initials(f.name))}</span>`;
            return `<div class="mm-cmp-slot">${ph}<span class="nm">${esc(f.name)}</span>
                    <span class="x" data-cmp-remove="${f.id}" title="${esc(t("common.remove"))}">×</span></div>`;
        };
        const empty = `<div class="mm-cmp-slot empty">${t("compare.add_slot")}</div>`;
        const ready = items.length >= 2;
        const url = ready ? `compare.html?id1=${items[0].id}&id2=${items[1].id}` : "#";
        tray.innerHTML = `
            <span class="mm-cmp-title">${t("compare.tray_title")}</span>
            <div class="mm-cmp-slots">
                ${items[0] ? slot(items[0]) : empty}
                <span class="mm-cmp-vs">VS</span>
                ${items[1] ? slot(items[1]) : empty}
            </div>
            <a class="mm-cmp-go${ready ? "" : " disabled"}" href="${url}">${t("compare.go_btn")}</a>
            <span class="mm-cmp-clear" data-cmp-clear>${t("common.reset")}</span>`;
        tray.classList.add("open");
        tray.querySelectorAll("[data-cmp-remove]").forEach(b =>
            b.addEventListener("click", () => window.MMAICompare.remove(b.dataset.cmpRemove)));
        const clr = tray.querySelector("[data-cmp-clear]");
        if (clr) clr.addEventListener("click", () => window.MMAICompare.clear());
    }

    // --- Reflete l'etat epingle sur tous les boutons presents ---
    function refreshPinStates() {
        document.querySelectorAll(".mm-pin, .mm-pin-text").forEach(p => {
            const on = window.MMAICompare.has(p.dataset.fighterId);
            p.classList.toggle("pinned", on);
            p.title = on ? t("compare.remove_btn") : t("compare.add_btn");
        });
    }

    // --- Clic sur une epingle (capture : on bat la navigation de la card) ---
    document.addEventListener("click", (e) => {
        const pin = e.target.closest(".mm-pin, .mm-pin-text");
        if (!pin) return;
        e.preventDefault();
        e.stopPropagation();
        window.MMAICompare.toggle({
            id: pin.dataset.fighterId,
            name: pin.dataset.fighterName,
            photo: pin.dataset.fighterPhoto || "",
        });
    }, true);

    // --- Strip "recemment consultes" (home + page fighters) ---
    function recentCard(f) {
        const ph = f.photo
            ? `<img src="${esc(f.photo)}" alt="" loading="lazy" onerror="this.style.display='none'">`
            : esc(initials(f.name));
        const wc = f.wc ? esc(formatWeightClassShort(f.wc, f.gender)) : "";
        return `<a href="fighter.html?id=${f.id}" class="mm-recent-card" data-fighter-id="${f.id}" data-fighter-name="${esc(f.name)}" data-hc-restricted>
            <div class="mm-recent-photo" data-hc-zone>${ph}</div>
            <div class="mm-recent-name" data-hc-zone>${esc(f.name)}</div>
            <div class="mm-recent-cat">${wc}</div></a>`;
    }
    function renderRecentStrip() {
        const isHome = !!document.getElementById("top-fighters");
        const isFighters = !!document.getElementById("fighters-grid");
        if (!isHome && !isFighters) return;
        const items = window.MMAIRecent.list();
        let sec = document.getElementById("mm-recent-section");
        if (!items.length) { if (sec) sec.remove(); return; }
        if (!sec) {
            sec = document.createElement("section");
            sec.id = "mm-recent-section";
            sec.className = "section";
            if (isHome) {
                const fav = document.getElementById("favorites-section");
                const stats = document.getElementById("stats-bar");
                const anchor = fav || stats;
                if (anchor) anchor.parentNode.insertBefore(sec, anchor.nextSibling);
                else { const s = document.getElementById("top-fighters").closest("section"); s.parentNode.insertBefore(sec, s); }
            } else {
                const grid = document.getElementById("fighters-grid");
                const s = grid.closest("section") || grid.parentNode;
                s.parentNode.insertBefore(sec, s);
            }
        }
        sec.innerHTML = `
            <div class="section-head">
                <h2>${t("recent.title")}</h2>
                <span class="mm-recent-clear section-head-link" style="cursor:pointer;">${t("recent.clear")}</span>
            </div>
            <div class="mm-recent-strip">${items.map(recentCard).join("")}</div>`;
        const clr = sec.querySelector(".mm-recent-clear");
        if (clr) clr.addEventListener("click", () => { window.MMAIRecent.clear(); renderRecentStrip(); });
    }

    // --- Hover-card fighter (desktop uniquement, informatif, sans Elo) ---
    (function hoverCard() {
        if (!window.matchMedia || !window.matchMedia("(hover: hover)").matches) return;
        let card = null, timer = null, pendingHide = null, curId = null, mouseX = 0, mouseY = 0;
        const cache = {};

        function ensure() {
            if (!card) {
                card = document.createElement("div"); card.className = "mm-hovercard"; document.body.appendChild(card);
                card.addEventListener("mouseenter", () => { clearTimeout(pendingHide); pendingHide = null; });
                card.addEventListener("mouseleave", (e) => {
                    if (e.relatedTarget && e.relatedTarget.closest("[data-fighter-id]")) return;
                    clearTimeout(pendingHide);
                    pendingHide = setTimeout(hide, 500);
                });
            }
            return card;
        }
        function build(f) {
            const photo = f.photo_thumbnail_url || f.photo_url;
            const ph = photo ? `<img src="${esc(photo)}" alt="" loading="lazy">` : esc(initials(f.name));
            const badges = [];
            if (f.is_ufc_champion) badges.push(`<span class="badge champ">${t("common.champion")}</span>`);
            else if (f.ufc_official_rank) badges.push(`<span class="badge rank">#${f.ufc_official_rank}</span>`);
            const wc = (f.weight_class_current && f.weight_class_current !== "Unknown")
                ? formatWeightClassShort(f.weight_class_current, f.gender) : "";
            if (wc) badges.push(`<span class="badge weight">${esc(wc)}</span>`);
            if (!f.is_active) badges.push(`<span class="badge inactive">${t("common.inactive")}</span>`);
            const w = f.record_total_wins ?? 0, l = f.record_total_losses ?? 0, d = f.record_total_draws ?? 0;
            const rec = `<span class="w">${w}</span><span class="sep">-</span><span class="l">${l}</span>${d > 0 ? `<span class="sep">-</span>${d}` : ""}`;
            const heightDisp = (f.height_inches || f.height) ? formatLengthPref(f.height_inches || f.height) : null;
            const league = f.current_league || null;
            const leagueHTML = league
                ? `<span class="mm-hc-league ${league === "UFC" ? "ufc" : "other"}">${esc(league)}</span>`
                : "";
            return `
                <div class="mm-hc-top">
                    <div class="mm-hc-photo">${ph}</div>
                    <div style="min-width:0;">
                        <div class="mm-hc-name">${
                            (nationalityToFlagHTML(f.nationality) ? `<span class="mm-hc-flag">${nationalityToFlagHTML(f.nationality)}</span> ` : "")
                            + esc(f.name)
                        }</div>
                        ${f.nickname ? `<div class="mm-hc-nick">"${esc(f.nickname)}"</div>` : ""}
                        <div class="mm-hc-badges">${badges.join("")}</div>
                    </div>
                </div>
                <div class="mm-hc-rec">${rec}${leagueHTML ? `<span class="mm-hc-rec-league">${leagueHTML}</span>` : ""}</div>
                <div class="mm-hc-grid">
                    <div class="mm-hc-cell"><div class="v">${num(f.age)}</div><div class="l">${t("common.age")}</div></div>
                    ${heightDisp ? `<div class="mm-hc-cell"><div class="v">${esc(heightDisp)}</div><div class="l">${t("common.height")}</div></div>` : ""}
                </div>
                <div class="mm-hc-foot">
                    <span class="mm-hc-last5">${last5Pills(f.last_5_results)}</span>
                    <span class="mm-hc-foot-right">
                        ${streakPill(f.current_streak)}
                        ${pinButtonHTML(f, "icon")}
                    </span>
                </div>`;
        }
        function position(anchor) {
            const cw = card.offsetWidth || 280, ch = card.offsetHeight || 220;
            let left, top;
            if (anchor && anchor.getBoundingClientRect) {
                const row = anchor.closest("[data-fighter-id]") || anchor;
                const hcSide = row.dataset.hcSide;
                if (hcSide === "left" || hcSide === "right") {
                    // event page : ancré sur le nom (1er zone = nom côté gauche, dernier = nom côté droit)
                    const evZones = row.querySelectorAll("[data-hc-zone]");
                    if (evZones.length) {
                        if (hcSide === "left") {
                            const r = evZones[0].getBoundingClientRect();
                            left = r.left - cw - 16;
                            if (left < 8) left = r.right + 16;
                            top = r.top + r.height / 2 - ch / 2;
                        } else {
                            const r = evZones[evZones.length - 1].getBoundingClientRect();
                            left = r.right + 16;
                            if (left + cw > window.innerWidth - 8) left = r.left - cw - 16;
                            top = r.top + r.height / 2 - ch / 2;
                        }
                    } else {
                        left = hcSide === "left" ? mouseX - cw - 16 : mouseX + 16;
                        if (left < 8) left = mouseX + 16;
                        top = mouseY - ch / 2;
                    }
                    if (left < 8) left = 8;
                } else {
                    // défaut : card juste à droite du texte du nom (dernier [data-hc-zone] inline)
                    const zones = row.querySelectorAll("[data-hc-zone]");
                    const nameEl = zones.length ? zones[zones.length - 1] : row;
                    const rect = nameEl.getBoundingClientRect();
                    left = rect.right + 16;
                    if (left + cw > window.innerWidth - 8) left = rect.left - cw - 16;
                    if (left < 8) left = 8;
                    top = rect.top + (rect.height / 2) - (ch / 2);
                }
            } else {
                left = mouseX + 16;
                if (left + cw > window.innerWidth - 8) left = mouseX - cw - 16;
                if (left < 8) left = 8;
                top = mouseY - 40;
            }
            if (top + ch > window.innerHeight - 8) top = window.innerHeight - ch - 8;
            if (top < 8) top = 8;
            card.style.left = left + "px";
            card.style.top = top + "px";
        }
        async function showFor(el, id, zoneEl) {
            timer = null;
            ensure();
            curId = id;
            let f = cache[id];
            if (!f) { try { f = await api.fighter(id); cache[id] = f; } catch (e) { return; } }
            if (curId !== id) return;       // la souris est deja partie ailleurs
            card.innerHTML = build(f);
            card.style.left = "-9999px"; card.style.top = "0";
            card.classList.add("show");
            requestAnimationFrame(() => { if (curId === id) position(zoneEl || el); });
        }
        function hide() {
            clearTimeout(pendingHide); pendingHide = null;
            if (card) card.classList.remove("show"); curId = null;
            clearTimeout(timer); timer = null;
        }

        document.addEventListener("mousemove", (e) => { mouseX = e.clientX; mouseY = e.clientY; });
        document.addEventListener("mouseover", (e) => {
            if (e.target.closest(".mm-pin, .mm-pin-text, .mm-cmp-tray, .mm-hovercard, [data-action]")) return;
            const trg = e.target.closest("[data-fighter-id]");
            if (!trg || !trg.dataset.fighterId) return;
            if (trg.hasAttribute("data-action")) return;

            const inZone = !trg.hasAttribute("data-hc-restricted") || !!e.target.closest("[data-hc-zone]");
            if (!inZone) {
                // Zone non-hover (record, stats...) : annule le timer de show en cours
                // et planifie un hide doux si la card est visible.
                clearTimeout(timer); timer = null;
                if (curId === trg.dataset.fighterId && card && card.classList.contains("show")) {
                    clearTimeout(pendingHide);
                    pendingHide = setTimeout(hide, 80);
                }
                return;
            }

            // Zone valide (photo ou nom)
            clearTimeout(pendingHide); pendingHide = null;
            const id = trg.dataset.fighterId;
            const zoneEl = e.target.closest("[data-hc-zone]") || trg;

            if (id === curId) {
                // Meme fighter : jitter CSS ou retour depuis zone non-hover.
                // Si le timer a ete annule et la card n'est pas visible, redemarrer.
                if (!timer && !(card && card.classList.contains("show"))) {
                    timer = setTimeout(() => showFor(trg, id, zoneEl), 150);
                }
                return;
            }

            clearTimeout(timer); timer = null;
            curId = id;
            // prefetch immediat
            if (!cache[id]) { api.fighter(id).then(f => { cache[id] = f; }).catch(() => {}); }
            timer = setTimeout(() => showFor(trg, id, zoneEl), 150);
        });
        document.addEventListener("mouseout", (e) => {
            const trg = e.target.closest("[data-fighter-id]");
            if (!trg) return;
            // ne pas cacher si on glisse vers l'interieur du fighter ou vers la hover-card
            if (e.relatedTarget && (trg.contains(e.relatedTarget) || (card && card.contains(e.relatedTarget)))) return;
            // on NE tue PAS le timer de show ici : si c'est un jitter CSS (translateY),
            // le mouseover suivant annulera ce pendingHide et le timer continuera tranquillement.
            // Si c'est un vrai depart, le pendingHide finira par appeler hide() qui tue le timer.
            clearTimeout(pendingHide);
            pendingHide = setTimeout(hide, 500);
        });
        // cacher quand on quitte la hover-card (via un mouseover sur fond neutre)
        document.addEventListener("mouseover", (e) => {
            if (!card || !card.classList.contains("show")) return;
            if (card.contains(e.target) || e.target.closest("[data-fighter-id]")) {
                clearTimeout(pendingHide); pendingHide = null;
            } else if (!pendingHide) {
                pendingHide = setTimeout(hide, 500);
            }
        }, true);
        window.addEventListener("scroll", hide, true);
        window.addEventListener("mmai:compare-change", () => {});  // no-op : la card est informative

        // --- prefetch des fighters visibles (IntersectionObserver) ---
        // quand un [data-fighter-id] entre dans le viewport (marge 400px),
        // on lance l'API en avance avec max 2 requetes en parallele.
        // resultat stocke dans cache -> hover quasi-instantane.
        const prefetchQ = [], prefetchSeen = new Set();
        let prefetchRunning = 0;
        const PREFETCH_MAX = 4;

        // expose un prefill global : les pages qui ont deja charge les fighters
        // (roster, division, rankings) remplissent le cache directement
        // -> hover instantane sans aucun appel API supplementaire
        window._hcPrefill = (f) => { if (f && f.id) { cache[f.id] = f; prefetchSeen.add(String(f.id)); } };

        function prefetchDrain() {
            while (prefetchRunning < PREFETCH_MAX && prefetchQ.length) {
                const id = prefetchQ.shift();
                prefetchRunning++;
                api.fighter(id)
                    .then(f => { cache[id] = f; })
                    .catch(() => {})
                    .finally(() => { prefetchRunning--; prefetchDrain(); });
            }
        }
        function prefetchFighter(id) {
            if (!id || cache[id] || prefetchSeen.has(id)) return;
            prefetchSeen.add(id);
            prefetchQ.push(id);
            prefetchDrain();
        }

        // observe tous les [data-fighter-id] dans la zone elargie du viewport
        const hcObserver = new IntersectionObserver(entries => {
            entries.forEach(e => { if (e.isIntersecting) prefetchFighter(e.target.dataset.fighterId); });
        }, { rootMargin: "400px 0px" });

        function observeAll(root) {
            (root || document).querySelectorAll("[data-fighter-id]").forEach(el => hcObserver.observe(el));
        }
        observeAll();  // fighters deja dans le DOM au chargement

        // ecoute les ajouts dynamiques (pagination, render async des pages)
        new MutationObserver(muts => muts.forEach(m => m.addedNodes.forEach(n => {
            if (n.nodeType !== 1) return;
            if (n.dataset && n.dataset.fighterId) hcObserver.observe(n);
            if (n.querySelectorAll) n.querySelectorAll("[data-fighter-id]").forEach(el => hcObserver.observe(el));
        }))).observe(document.body, { childList: true, subtree: true });
    })();

    function initUX() { renderCompareTray(); renderRecentStrip(); refreshPinStates(); }
    window.addEventListener("mmai:compare-change", () => { renderCompareTray(); refreshPinStates(); });
    window.addEventListener("mmai:lang-change", () => { renderCompareTray(); renderRecentStrip(); refreshPinStates(); });
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initUX);
    else initUX();

    // Quand une page (home/fighters) finit de peindre ses cards, on re-synchronise
    // l'etat des epingles + on (re)pose le strip recent au-dessus.
    window.addEventListener("load", () => { renderRecentStrip(); refreshPinStates(); });
})();
