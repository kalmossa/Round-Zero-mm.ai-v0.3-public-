// MM.AI v0.3 - public showcase banner (added when the project was published on GitHub).
// Tells visitors this is NOT the real prediction engine of the final product (RoundZero).
(function () {
    var MSG = {
        en: "MM.AI v0.3 - early public showcase. Predictions and ratings here are simplified and are NOT the algorithms of the final product, RoundZero.",
        fr: "MM.AI v0.3 - premiere version, en vitrine. Les pronostics et notes ici sont simplifies et ne sont PAS les algorithmes du produit final, RoundZero.",
        es: "MM.AI v0.3 - primera version, solo como muestra. Las predicciones y valoraciones son simplificadas y NO son los algoritmos del producto final, RoundZero.",
        zh: "MM.AI v0.3 - 早期公开展示版本。此处的预测与评分经过简化，并非最终产品 RoundZero 所使用的算法。",
        pt: "MM.AI v0.3 - primeira versao, apenas vitrine. As previsoes e notas aqui sao simplificadas e NAO sao os algoritmos do produto final, RoundZero.",
        de: "MM.AI v0.3 - fruhe oeffentliche Showcase-Version. Prognosen und Ratings sind vereinfacht und NICHT die Algorithmen des Endprodukts RoundZero.",
        ru: "MM.AI v0.3 - ранняя публичная витринная версия. Прогнозы и рейтинги упрощены и НЕ являются алгоритмами финального продукта RoundZero.",
        ar: "MM.AI v0.3 - نسخة عرض عامة مبكرة. التوقعات والتقييمات هنا مبسطة وليست خوارزميات المنتج النهائي RoundZero."
    };
    var lang = "en";
    try { lang = localStorage.getItem("mmai-lang") || document.documentElement.lang || "en"; } catch (e) {}
    lang = String(lang).slice(0, 2).toLowerCase();
    var text = MSG[lang] || MSG.en;

    function add() {
        if (document.getElementById("mm-demo-banner")) return;
        var bar = document.createElement("div");
        bar.id = "mm-demo-banner";
        bar.setAttribute("role", "note");
        bar.textContent = text;
        bar.style.cssText = "background:#7c3aed;color:#fff;font:600 13px/1.4 system-ui,sans-serif;" +
            "text-align:center;padding:8px 16px;position:relative;z-index:9999;";
        document.body.insertBefore(bar, document.body.firstChild);

        var foot = document.querySelector(".footer-meta");
        if (foot) {
            var p = document.createElement("div");
            p.textContent = text;
            p.style.cssText = "opacity:.7;font-size:12px;margin-top:6px;";
            foot.appendChild(p);
        }
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", add);
    else add();
})();
