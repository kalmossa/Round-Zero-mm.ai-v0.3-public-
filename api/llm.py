"""
Petit pont vers un LLM (IA generative) pour rediger les analyses de combat.

Objectif : a partir de toutes les donnees qu'on a deja (Elo, Scouter, forme,
record, tale of the tape...), faire ecrire un paragraphe d'analyse + un prono
+ un pourcentage de fiabilite.

Philosophie : ZERO dependance en plus. On utilise "requests" (deja installe).
Marche avec plusieurs fournisseurs, au choix dans le .env :

    LLM_PROVIDER=gemini     -> Google Gemini  (GRATUIT, recommande pour demarrer)
    LLM_PROVIDER=openrouter -> OpenRouter      (1 cle = tous les modeles)
    LLM_PROVIDER=groq       -> Groq            (gratuit, tres rapide)

Cle correspondante dans le .env :
    GEMINI_API_KEY=...        (https://aistudio.google.com/apikey)
    OPENROUTER_API_KEY=...    (https://openrouter.ai/keys)
    GROQ_API_KEY=...          (https://console.groq.com/keys)

Si aucune cle n'est configuree, llm_available() renvoie False et l'appelant
retombe sur une analyse "de secours" generee sans IA (le site marche pareil).
"""

import os
import json
import requests

# ---------------------------------------------------------------------------
# Config : on lit le fournisseur choisi + sa cle dans les variables d'env.
# ---------------------------------------------------------------------------
PROVIDER = (os.getenv("LLM_PROVIDER") or "gemini").strip().lower()

# Modeles par defaut (modifiables via .env si tu veux). Tous gratuits/pas chers.
_DEFAULT_MODELS = {
    "gemini":     "gemini-2.5-flash",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "groq":       "llama-3.3-70b-versatile",
}


def _api_key():
    """Renvoie la cle du fournisseur actif, ou None si pas configuree."""
    return {
        "gemini":     os.getenv("GEMINI_API_KEY"),
        "openrouter": os.getenv("OPENROUTER_API_KEY"),
        "groq":       os.getenv("GROQ_API_KEY"),
    }.get(PROVIDER)


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] DISPONIBILITÉ — pas de clé → False → fallback sans IA, site marche pareil
# ═══════════════════════════════════════════════════════════════════
def llm_available() -> bool:
    """True si une cle est configuree -> on peut appeler l'IA."""
    return bool(_api_key())


def _model():
    return os.getenv("LLM_MODEL") or _DEFAULT_MODELS.get(PROVIDER, "gemini-2.5-flash")


# ---------------------------------------------------------------------------
# Appel bas niveau : envoie un prompt, recupere le texte de reponse.
# On gere les 2 "dialectes" : Gemini d'un cote, OpenAI-compatible de l'autre
# (OpenRouter et Groq parlent le meme langage que l'API OpenAI).
# ---------------------------------------------------------------------------
# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] APPEL BAS NIVEAU — Gemini (format à part) vs OpenAI-compat (OpenRouter/Groq)
# ═══════════════════════════════════════════════════════════════════
def _raw_complete(system_prompt: str, user_prompt: str, timeout: int = 40) -> str:
    key = _api_key()
    if not key:
        raise RuntimeError("Aucune cle LLM configuree (voir .env).")

    if PROVIDER == "gemini":
        model = _model()
        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model}:generateContent?key={key}"
        )
        gen_cfg = {"temperature": 0.5, "maxOutputTokens": 1024}
        # ═══════════════════════════════════════════════════════════════════
        # 📌 [DÉMO] BUG GEMINI 2.5 — modèle "thinking" → JSON tronqué sans ce fix
        # sans thinkingBudget=0, il dépense tous ses tokens à réfléchir avant d'écrire
        # ═══════════════════════════════════════════════════════════════════
        # Les modeles Gemini 2.5 sont "thinking" : ils depensent des tokens a
        # reflechir AVANT d'ecrire. Pour une sortie JSON courte c'est inutile et
        # ca peut epuiser le budget (-> reponse coupee = JSON invalide). On coupe
        # la reflexion. (Ne s'applique qu'aux modeles 2.5 qui supportent l'option.)
        if "2.5" in model:
            gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": gen_cfg,
        }
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        cand = (r.json().get("candidates") or [{}])[0]
        parts = cand.get("content", {}).get("parts")
        if not parts:
            raise RuntimeError(
                f"Reponse Gemini vide (finishReason={cand.get('finishReason')})."
            )
        return parts[0]["text"]

    # --- OpenRouter / Groq (format OpenAI) ---
    base = {
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "groq":       "https://api.groq.com/openai/v1/chat/completions",
    }[PROVIDER]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 700,
    }
    r = requests.post(base, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Fonction principale utilisee par l'API : rediger l'analyse d'un combat.
# Renvoie toujours un dict : {analysis, reliability, predicted_winner, source}
# ---------------------------------------------------------------------------
# Code langue (du site) -> nom en anglais (pour l'instruction au modele).
_LANG_NAMES = {
    "en": "English", "fr": "French", "es": "Spanish", "zh": "Simplified Chinese",
    "pt": "Portuguese", "de": "German", "ru": "Russian", "ar": "Modern Standard Arabic",
}


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] PROMPT SYSTÈME — impose un JSON strict {predicted_winner, reliability, analysis}
# reliability = confiance auto-évaluée par le LLM (basse si données manquantes/combat serré)
# ═══════════════════════════════════════════════════════════════════
def _system_prompt(lang: str = "en") -> str:
    lang_name = _LANG_NAMES.get((lang or "en").lower(), "English")
    return (
        "You are an MMA analyst for the MM.AI website. You are given the numeric "
        "data of two fighters (internal Elo rating, Scouter score out of 100, recent "
        "form, record, height/reach, style, ranking). Some data may be missing. "
        "You must ALWAYS return a prediction, even with incomplete data. "
        "Respond STRICTLY as valid JSON, no text around it, with this exact format:\n"
        '{"predicted_winner": "<name>", "reliability": <integer 0-100>, '
        '"analysis": "<3 to 5 sentences of analysis>"}\n'
        f"IMPORTANT: write the 'analysis' field in {lang_name}. "
        "The 'reliability' field is your confidence in the prediction: LOWER if data "
        "is missing or the two fighters are very close, HIGHER if data is complete and "
        "the gap is clear."
    )


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] ENTRÉE PRINCIPALE — ne lève JAMAIS d'exception
# erreur/pas de clé → source='error', fallback propre, site marche pareil
# ═══════════════════════════════════════════════════════════════════
def generate_fight_analysis(prompt_data: str, lang: str = "en") -> dict:
    """
    prompt_data : un bloc de texte decrivant les 2 fighters (construit par l'API).
    lang        : code langue du site (en/fr/es/zh/pt/de/ru/ar) -> langue de l'analyse.
    Renvoie un dict {analysis, reliability, predicted_winner, source}.
    Ne leve jamais d'exception : en cas de souci, source='error' et analysis vide.
    """
    try:
        raw = _raw_complete(_system_prompt(lang), prompt_data)
        # Le modele renvoie parfois le JSON entoure de ```json ... ``` -> on nettoie.
        cleaned = raw.strip().lstrip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        # On isole le premier objet JSON { ... }
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end != -1:
            cleaned = cleaned[start:end + 1]
        data = json.loads(cleaned)
        rel = int(data.get("reliability", 50))
        rel = max(0, min(100, rel))
        return {
            "analysis": str(data.get("analysis", "")).strip(),
            "reliability": rel,
            "predicted_winner": str(data.get("predicted_winner", "")).strip(),
            "source": f"{PROVIDER}:{_model()}",
        }
    except Exception as exc:  # noqa: BLE001 - on veut un fallback robuste
        return {
            "analysis": "",
            "reliability": None,
            "predicted_winner": "",
            "source": "error",
            "error": str(exc),
        }
