"""
AI Advisory Layer
-----------------
Uses NVIDIA NIM (llama-3.1-70b-instruct) to generate SOC-style explanations
of vehicle anomalies.

Falls back to a deterministic template response when no API key is configured,
so the system works fully without a paid key.
"""

import json
import requests

from backend.security.env import get_secret

NVIDIA_API_KEY = get_secret("NVIDIA_API_KEY")   # None if not set — no crash

NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"


def _fallback_analysis(vehicle_summary: dict) -> str:
    """
    Deterministic advisory returned when no API key is available.
    Useful for offline demos and CI runs.
    """
    risk = vehicle_summary.get("risk_score", 0)
    anomalies = vehicle_summary.get("anomalies", [])
    ecu_list = ", ".join(a["ecu"] for a in anomalies) if anomalies else "unknown"

    if risk >= 75:
        level = "CRITICAL"
        action = "Immediate vehicle isolation and manual inspection recommended."
    elif risk >= 50:
        level = "HIGH"
        action = "Alert SOC team and flag ECUs for forensic review."
    else:
        level = "MODERATE"
        action = "Monitor closely. Escalate if additional ECUs show anomalies."

    return (
        f"[{level}] Vehicle risk score: {risk}/100. "
        f"Anomalous ECUs: {ecu_list}. "
        f"{action} "
        f"(AI advisory running in offline/fallback mode — set NVIDIA_API_KEY in .env to enable LLM analysis.)"
    )


def explain_vehicle_anomaly(vehicle_summary: dict) -> str:
    """
    Calls NVIDIA NIM API to generate a natural-language SOC advisory.
    Falls back gracefully if the key is missing or the API call fails.
    """
    if not NVIDIA_API_KEY:
        return _fallback_analysis(vehicle_summary)

    prompt = f"""You are an automotive cybersecurity SOC analyst.

A vehicle has triggered semantic anomaly alerts. Analyse the following summary
and respond with:
1. Likely attack type or fault
2. Which ECUs are most critical
3. Recommended immediate action

Vehicle anomaly summary:
{json.dumps(vehicle_summary, indent=2)}

Be concise (3–5 sentences). Use SOC/automotive security language."""

    try:
        response = requests.post(
            NVIDIA_API_URL,
            headers={
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": NVIDIA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.3,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    except Exception as exc:
        return _fallback_analysis(vehicle_summary)
