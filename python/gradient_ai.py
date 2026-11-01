import os
import json
import urllib.request
import urllib.error

# DigitalOcean Gradient Serverless Inference / OpenAI-compatible endpoint
DO_GRADIENT_ENDPOINT = os.environ.get(
    "DO_GRADIENT_ENDPOINT", "https://inference.do-ai.run/v1/chat/completions"
)
DO_GRADIENT_API_KEY = os.environ.get("DO_GRADIENT_API_KEY", "").strip()
MODEL_NAME = os.environ.get("DO_MODEL_NAME", "meta-llama/Meta-Llama-3.1-8B-Instruct")

SYSTEM_PROMPT = """You are the Huush AI Acoustic Moderator running on DigitalOcean Gradient.
Your job is to analyze 30-second aggregated acoustic room telemetry (RMS level, peak levels, active microphone stations, and spike counts).
Provide a concise, encouraging 1-sentence room acoustic status and an adaptive threshold recommendation (e.g. 70-85).
Return valid JSON only with keys:
"status": a concise 1-sentence assessment of room acoustics
"recommendation": a constructive suggestion for participants
"adaptive_threshold": integer between 65 and 85
"""

def analyze_room_telemetry(snapshot: dict, recent_spikes: int = 0) -> dict:
    """Send aggregated acoustic summary to DigitalOcean Gradient open-weight model."""
    if not DO_GRADIENT_API_KEY:
        # Fallback heuristic when API key is not configured locally
        lvl = snapshot.get("level", 0)
        count = snapshot.get("count", 0)
        if lvl >= 75:
            return {
                "status": "High ambient noise detected across the room.",
                "recommendation": "Suggest taking group side-discussions to breakout spaces.",
                "adaptive_threshold": 78,
                "model": "local-heuristic"
            }
        elif lvl >= 45:
            return {
                "status": "Moderate, energetic collaboration cadence.",
                "recommendation": "Acoustics are lively. Great focus across active stations.",
                "adaptive_threshold": 75,
                "model": "local-heuristic"
            }
        else:
            return {
                "status": "Calm, focused sound floor.",
                "recommendation": "Ideal deep-work conditions.",
                "adaptive_threshold": 72,
                "model": "local-heuristic"
            }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Snapshot: current_level={snapshot.get('level')}, active_microphones={snapshot.get('count')}, recent_spikes={recent_spikes}"
            }
        ],
        "temperature": 0.3,
        "max_tokens": 150
    }

    req = urllib.request.Request(
        DO_GRADIENT_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DO_GRADIENT_API_KEY}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            parsed["model"] = MODEL_NAME
            return parsed
    except Exception as exc:
        return {
            "status": "Sound floor monitored.",
            "recommendation": "Keep collaboration balanced.",
            "adaptive_threshold": 75,
            "error": str(exc),
            "model": "fallback"
        }

