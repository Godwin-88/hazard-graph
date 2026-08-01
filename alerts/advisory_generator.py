"""HazardGraph — Groq LLM advisory generation for localised SMS alerts.

Generates 160-character SMS advisories in local languages (Swahili,
Somali, Amharic, Tigrinya, Arabic, French, English) using Groq's
llama-3.3-70b-versatile model. Includes two-stage generation +
tone review.
"""

import json
import logging
from datetime import datetime

from groq import AsyncGroq

from config.settings import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an agricultural extension officer in East Africa.
Generate a SINGLE SMS advisory for farmers/pastoralists.
Rules (STRICT):
  1. Maximum 160 characters total — count carefully
  2. Start with an action verb (plant, harvest, move, sell, store, prepare)
  3. One specific action only — not multiple instructions
  4. No technical terms (no "SPI", "IPC", "anomaly", "regime")
  5. Include timeframe: "this week", "next 2 weeks", "before Friday"
  6. Write in {language} only — no English if language is not English
  7. Never use exclamation marks — keep tone calm and factual
  8. Never say "risk", "crisis", "emergency", "disaster"
Output: the SMS text only. Nothing else. No quotes. No explanation."""


class AdvisoryGenerator:
    """Generates localised SMS advisories using Groq LLM."""

    def __init__(self):
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.model = settings.groq_model

    async def generate(
        self,
        region_id: str,
        region_name: str,
        country: str,
        score: float,
        confidence: float,
        components: dict,
        current_regime: str,
        sde_interpretation: str,
        spi_interpretation: str,
        food_interpretation: str,
        ipc_interpretation: str,
        top_features: list[str] | None = None,
        language: str = "english",
        lang_code: str = "en",
        season_context: str = "",
    ) -> str:
        """Generate a single advisory via Groq with two-stage validation."""
        import json as _json

        with open("config/region_languages.json") as f:
            lang_map = _json.load(f)

        country_key = country.strip().lower().replace(" ", "_")
        lang_info = lang_map.get(country_key, {})
        language_name = lang_info.get("language", language)

        user_prompt = f"""Region: {region_name}, {country}
Language: {language_name}
Season context: {season_context}

Current situation:
- Rainfall: {spi_interpretation}
- Food prices: {food_interpretation}
- Food security: {ipc_interpretation}
- 4-week forecast: {sde_interpretation}

Risk level: {score:.0f}/100 ({confidence} confidence)
{f'Key drivers: {", ".join(top_features)}' if top_features else ''}

Generate one 160-character SMS advisory in {language_name}."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT.format(language=language_name)},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=80,
            )
            advisory = response.choices[0].message.content.strip()
            # Strip surrounding quotes if present
            advisory = advisory.strip("\"'")
        except Exception as exc:
            logger.error("Groq advisory generation failed for %s: %s", region_id, exc)
            return self._fallback(region_name)

        # Truncate to 160 chars
        if len(advisory) > 160:
            advisory = advisory[:157] + "..."

        # Stage 2: tone review
        try:
            review_response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Does this SMS advisory: (a) start with action verb, "
                            "(b) avoid technical jargon, (c) stay under 160 chars, "
                            "(d) sound calm not alarmist? Reply YES or NO only."
                        ),
                    },
                    {"role": "user", "content": advisory},
                ],
                temperature=0.0,
                max_tokens=10,
            )
            review = review_response.choices[0].message.content.strip().upper()
            if review != "YES":
                logger.warning("Tone review failed for %s, regenerating once", region_id)
                # Regenerate once
                response2 = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT.format(language=language_name)},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=80,
                )
                advisory = response2.choices[0].message.content.strip("\"'")
                if len(advisory) > 160:
                    advisory = advisory[:157] + "..."
        except Exception as exc:
            logger.warning("Tone review failed for %s: %s — using generated advisory", region_id, exc)

        return advisory

    async def generate_all_triggered(
        self,
        risk_scores: list,
        bma_results: list,
        postgres_session=None,
        neo4j_session=None,
    ) -> list[str]:
        """Generate advisories for all triggered regions with kelly_priority > 0.10.

        Returns list of created alert IDs (UUIDs) from PostgreSQL.
        """
        import json as _json
        from datetime import datetime, timezone

        from sqlalchemy import text

        with open("config/region_languages.json") as f:
            lang_map = _json.load(f)

        with open("config/farming_calendars.json") as f:
            calendar_map = _json.load(f)

        current_month = str(datetime.now(timezone.utc).month)
        created_ids: list[str] = []

        if not risk_scores:
            logger.info("No risk scores provided for advisory generation")
            return created_ids

        if not bma_results:
            bma_results = [None] * len(risk_scores)

        for idx, score in enumerate(risk_scores):
            if not hasattr(score, "alert_triggered"):
                continue
            if not score.alert_triggered:
                continue

            bma = bma_results[idx] if idx < len(bma_results) else None
            kelly = getattr(bma, "kelly_priority", 0.0) if bma else 0.0
            if kelly <= 0.10:
                continue

            country_key = getattr(score, "country", "").lower().replace(" ", "_")
            lang_info = lang_map.get(country_key, {"language": "english", "lang_code": "en"})
            language_name = lang_info.get("language", "english")
            lang_code = lang_info.get("lang_code", "en")

            calendar = calendar_map.get(country_key, {})
            season_context = calendar.get(current_month, "General farming season")

            components = getattr(score, "components", {})
            spi = components.get("rainfall", 0.5)
            food = components.get("food", 0.5)
            ipc_val = components.get("ipc", 0.5)
            sde_val = components.get("sde", 0.5)

            spi_interpretation = "below normal" if spi > 0.6 else ("above normal" if spi < 0.3 else "normal")
            food_interpretation = "rising sharply" if food > 0.7 else ("rising" if food > 0.4 else "stable")
            ipc_interpretation = "crisis" if ipc_val > 0.6 else ("stressed" if ipc_val > 0.3 else "adequate")
            sde_interpretation = "flooding possible" if sde_val > 0.6 else ("drought likely" if sde_val > 0.3 else "normal expected")

            conf = getattr(bma, "confidence", 0.5) if bma else 0.5
            confidence = f"{conf:.0%}" if isinstance(conf, float) else "moderate"

            comp_scores = components
            sorted_comps = sorted(comp_scores.items(), key=lambda x: x[1], reverse=True)
            top_features = [c[0] for c in sorted_comps[:2]]

            advisory = await self.generate(
                region_id=getattr(score, "region_id", ""),
                region_name=getattr(score, "name", ""),
                country=getattr(score, "country", ""),
                score=getattr(score, "score", 50.0),
                confidence=confidence if isinstance(confidence, float) else 0.5,
                components=components,
                current_regime=getattr(score, "current_regime", "Baseline"),
                sde_interpretation=sde_interpretation,
                spi_interpretation=spi_interpretation,
                food_interpretation=food_interpretation,
                ipc_interpretation=ipc_interpretation,
                top_features=top_features,
                language=language_name,
                lang_code=lang_code,
                season_context=season_context,
            )

            # Insert into PostgreSQL
            try:
                if postgres_session:
                    result = await postgres_session.execute(
                        text(
                            """INSERT INTO alerts
                               (region_id, language, message_text, risk_score_at_trigger,
                                kelly_priority, status, generated_at, created_at, updated_at)
                               VALUES (:rid, :lang, :msg, :score, :kelly, 'pending', :now, :now, :now)
                               RETURNING id"""
                        ),
                        {
                            "rid": getattr(score, "region_id", ""),
                            "lang": lang_code,
                            "msg": advisory,
                            "score": getattr(score, "score", 0.0),
                            "kelly": kelly if isinstance(kelly, (int, float)) else 0.0,
                            "now": datetime.now(timezone.utc),
                        },
                    )
                    await postgres_session.commit()
                    row = result.fetchone()
                    if row:
                        alert_id = str(row[0])
                        created_ids.append(alert_id)
                        logger.info("Created alert %s for region %s", alert_id, getattr(score, "region_id", ""))
            except Exception as exc:
                logger.error("Failed to persist alert for %s: %s", getattr(score, "region_id", ""), exc)
                if postgres_session:
                    await postgres_session.rollback()

        logger.info("Generated %d advisories for triggered regions", len(created_ids))
        return created_ids

    def _fallback(self, region_name: str) -> str:
        """Return English fallback advisory if Groq API fails."""
        msg = f"Alert: {region_name} showing elevated risk. Check with local extension officer for guidance this week."
        return msg[:160]