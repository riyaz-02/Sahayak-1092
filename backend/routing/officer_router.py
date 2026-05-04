"""Officer scoring and selection logic."""

from __future__ import annotations

from typing import Any


def _normalized_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value.lower()]
    return [str(item).lower() for item in value]


def score_agent(
    agent: dict[str, Any],
    call_language: str,
    category: str,
    dialect: str = "",
    urgency: float = 0.5,
) -> float:
    """Score an officer for the current call.

    Formula:
      50% specialty/category fit + 40% language/dialect fit + 10% wait time,
      with a small load penalty for heavily occupied agents.
    """

    return score_agent_with_breakdown(
        agent=agent,
        call_language=call_language,
        category=category,
        dialect=dialect,
        urgency=urgency,
    )["score"]


def score_agent_with_breakdown(
    agent: dict[str, Any],
    call_language: str,
    category: str,
    dialect: str = "",
    urgency: float = 0.5,
) -> dict[str, Any]:
    """Return an auditable routing score and component breakdown."""

    language = (call_language or "").lower()
    category = (category or "general").lower()
    dialect = (dialect or "").lower()
    urgency = max(0.0, min(float(urgency or 0.5), 1.0))

    agent_langs = _normalized_list(agent.get("languages", []))
    agent_dialects = _normalized_list(agent.get("dialects", []))
    agent_specs = _normalized_list(agent.get("specialties", []))

    if category in agent_specs:
        specialty_score = 1.0
        specialty_reason = f"specialty match for {category}"
    elif "general" in agent_specs:
        specialty_score = 0.55
        specialty_reason = "general specialist fallback"
    elif urgency >= 0.9:
        specialty_score = 0.35
        specialty_reason = "critical urgency fallback"
    else:
        specialty_score = 0.15
        specialty_reason = "no direct specialty match"

    urgency_readiness = 1.0 if urgency >= 0.9 and category in agent_specs else max(0.35, urgency)
    urgency_specialty_raw = max(specialty_score, 0.65 * specialty_score + 0.35 * urgency_readiness)

    if language and language in agent_langs:
        if dialect:
            language_raw = 1.0 if dialect in agent_dialects else 0.88
            language_reason = "language and dialect match" if dialect in agent_dialects else "language match"
        else:
            language_raw = 1.0
            language_reason = "language match"
    elif any(lang in agent_langs for lang in ["english", "hindi"]):
        language_raw = 0.38
        language_reason = "bridge language fallback"
    else:
        language_raw = 0.12
        language_reason = "weak language fit"

    avg_wait = agent.get("avg_wait_sec", 60) or 60
    wait_raw = max(0.0, 1.0 - (float(avg_wait) / 120.0))

    current_load = int(agent.get("current_load", 0) or 0)
    load_penalty = 0.0
    if current_load > 2:
        load_penalty = min(0.25, 0.05 * (current_load - 2) + 0.10)

    weighted = {
        "urgency_specialty": round(0.50 * urgency_specialty_raw, 4),
        "language_dialect": round(0.40 * language_raw, 4),
        "wait_time": round(0.10 * wait_raw, 4),
        "load_penalty": round(load_penalty, 4),
    }
    score = max(
        min(
            weighted["urgency_specialty"]
            + weighted["language_dialect"]
            + weighted["wait_time"]
            - weighted["load_penalty"],
            1.0,
        ),
        0.0,
    )
    return {
        "agent_id": agent.get("id"),
        "score": round(score, 3),
        "weights": {
            "urgency_specialty": 0.50,
            "language_dialect": 0.40,
            "wait_time": 0.10,
            "load_penalty": "subtractive",
        },
        "raw": {
            "urgency": urgency,
            "specialty_fit": round(specialty_score, 3),
            "urgency_specialty_fit": round(urgency_specialty_raw, 3),
            "language_dialect_fit": round(language_raw, 3),
            "wait_time_fit": round(wait_raw, 3),
            "current_load": current_load,
            "avg_wait_sec": avg_wait,
        },
        "weighted": weighted,
        "reason": (
            f"{specialty_reason}; {language_reason}; "
            f"avg wait {avg_wait}s; current load {current_load}"
        ),
    }


def select_best_agent(
    agents: list[dict[str, Any]],
    call_language: str,
    category: str,
    dialect: str = "",
    urgency: float = 0.5,
) -> dict[str, Any] | None:
    """Return the best officer and score from a list of candidates."""

    if not agents:
        return None

    scored = []
    for agent in agents:
        breakdown = score_agent_with_breakdown(
            agent=agent,
            call_language=call_language,
            category=category,
            dialect=dialect,
            urgency=urgency,
        )
        scored.append(
            {
                "agent": agent,
                "score": breakdown["score"],
                "score_breakdown": breakdown,
                "reason": breakdown["reason"],
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    best = scored[0]
    best["ranked_agents"] = [
        {
            "agent_id": item["agent"].get("id"),
            "name": item["agent"].get("name"),
            "score": item["score"],
            "score_breakdown": item["score_breakdown"],
        }
        for item in scored[:5]
    ]
    return best
