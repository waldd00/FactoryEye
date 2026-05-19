# ─────────────────────────────────────────────
#  SmartQualityControl — agent.py
#  LLM-based intelligent decision support
#  Powered by Google Gemini (google-genai SDK)
# ─────────────────────────────────────────────

import os
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import LLM_MAX_TOKENS, LLM_MODEL, AGENT_TRIGGER_RATE

GEMINI_MODEL = LLM_MODEL

SYSTEM_PROMPT = (
    "You are an industrial quality control assistant monitoring a production line. "
    "You receive real-time statistics and provide short, actionable recommendations. "
    "Always respond in JSON with this exact format:\n"
    '{"severity": "ok"|"warning"|"critical", '
    '"recommendation": "<one short sentence>", '
    '"action": "none"|"slow_belt"|"stop_line"|"maintenance_check"}\n'
    "Do not include any text outside the JSON."
)


class QualityAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("[Agent] GEMINI_API_KEY not set — agent disabled")
            self._enabled = False
            self._client  = None
            return

        try:
            from google import genai
            from google.genai import types
            self._client = genai.Client(api_key=api_key)
            self._types  = types
            self._history: list = []
            self._enabled = True
            print(f"[Agent] Gemini agent ready (model={GEMINI_MODEL})")
        except Exception as e:
            print(f"[Agent] Init failed: {e}")
            self._enabled = False
            self._client  = None

    # ── Main Entry Point ──────────────────────
    def analyze(
        self,
        total: int,
        defects: int,
        rate: float,
        last_defect_label: str = "unknown",
    ) -> dict | None:
        if not self._enabled:
            return None
        if rate < AGENT_TRIGGER_RATE:
            return None

        user_message = (
            f"Production stats — "
            f"Total: {total}, Defects: {defects}, "
            f"Defect rate: {rate:.1f}%, "
            f"Last defect type: {last_defect_label}"
        )

        try:
            from google.genai import types
            self._history.append(
                types.Content(role="user", parts=[types.Part(text=user_message)])
            )

            response = self._client.models.generate_content(
                model=GEMINI_MODEL,
                contents=self._history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    max_output_tokens=LLM_MAX_TOKENS,
                ),
            )
            reply = response.text.strip()

            self._history.append(
                types.Content(role="model", parts=[types.Part(text=reply)])
            )

            if reply.startswith("```"):
                reply = reply.split("```")[1]
                if reply.startswith("json"):
                    reply = reply[4:]
                reply = reply.strip()

            parsed = json.loads(reply)
            self._log(parsed, rate)
            return parsed

        except json.JSONDecodeError:
            print(f"[Agent] Could not parse Gemini response: {reply}")
            return None
        except Exception as e:
            print(f"[Agent] Gemini API error: {e}")
            return None

    # ── Natural Language Control ──────────────
    def ask(self, question: str) -> str:
        if not self._enabled:
            return "Agent is disabled (no API key)."
        try:
            from google.genai import types
            response = self._client.models.generate_content(
                model=GEMINI_MODEL,
                contents=question,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "You are an industrial quality control assistant. "
                        "Answer concisely in 1-2 sentences."
                    ),
                    max_output_tokens=256,
                ),
            )
            return response.text.strip()
        except Exception as e:
            return f"Agent error: {e}"

    # ── Reset Conversation ────────────────────
    def reset(self):
        self._history = []
        print("[Agent] Conversation history cleared")

    # ── Internal ──────────────────────────────
    def _log(self, parsed: dict, rate: float):
        severity = parsed.get("severity", "?")
        rec      = parsed.get("recommendation", "")
        action   = parsed.get("action", "none")
        icons    = {"ok": "[OK]", "warning": "[WARN]", "critical": "[CRIT]"}
        icon     = icons.get(severity, "[?]")
        print(f"[Agent] {icon} rate={rate:.1f}% | {rec} | action={action}")
