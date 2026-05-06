"""Resolved-case seed dataset for Smart Similarity Detection.

These are demo-safe, synthetic cases. They give the vector/RAG path enough
language, dialect, urgency, and issue diversity to behave like a real helpline
knowledge base during local demos and judging.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


CATEGORY_ALIASES = {
    "cyber_fraud": "cyber",
    "domestic_violence": "domestic",
    "road_accident": "accident",
}


BASE_RESOLVED_CASE_SEEDS: list[dict[str, Any]] = [
    {
        "summary": "Caller reported mobile phone theft at Majestic bus stand. Stolen while boarding BMTC bus.",
        "category": "theft",
        "language": "kannada",
        "dialect": "bengaluru",
        "urgency_band": "medium",
        "resolution": "FIR registered online. Advised to block SIM via telecom provider. Shared nearest police station details. Phone tracked via IMEI within 48 hours.",
        "tags": ["mobile_theft", "public_transport", "bangalore"],
    },
    {
        "summary": "Woman reported domestic violence by husband. Afraid for safety of children.",
        "category": "domestic",
        "language": "kannada",
        "dialect": "",
        "urgency_band": "high",
        "resolution": "Immediate dispatch of nearest PCR van. Connected with Women Helpline 181. Temporary shelter arranged. FIR registered under IPC 498A.",
        "tags": ["domestic_violence", "women_safety", "urgent"],
    },
    {
        "summary": "Road accident reported on NH-44 near Tumkur toll. Two-wheeler hit by truck. Rider injured.",
        "category": "accident",
        "language": "hindi",
        "dialect": "",
        "urgency_band": "high",
        "resolution": "Ambulance dispatched (108). Nearest hospital alerted. Traffic police diverted traffic. FIR registered against truck driver.",
        "tags": ["road_accident", "highway", "medical_emergency"],
    },
    {
        "summary": "Neighbour playing loud music late at night causing disturbance. Repeated complaints ignored.",
        "category": "noise",
        "language": "english",
        "dialect": "",
        "urgency_band": "low",
        "resolution": "Local beat constable dispatched to address the issue. Warning issued under Noise Pollution Rules. Follow-up scheduled for next 3 days.",
        "tags": ["noise_complaint", "neighbourhood", "non_urgent"],
    },
    {
        "summary": "Suspicious person loitering near school premises during school hours. Parents concerned.",
        "category": "suspicious_activity",
        "language": "kannada",
        "dialect": "",
        "urgency_band": "medium",
        "resolution": "PCR van dispatched for verification. Person identified and warned. School principal informed. Increased patrol scheduled near school.",
        "tags": ["suspicious_activity", "school_safety", "patrol"],
    },
]


COMPETITION_RESOLVED_CASE_SEEDS: list[dict[str, Any]] = [
    {
        "summary": "Caller reported mobile phone theft near Howrah railway station while boarding a crowded train.",
        "category": "theft",
        "language": "english",
        "dialect": "kolkata-urban",
        "urgency_band": "medium",
        "resolution": "Advised caller to block SIM, note IMEI, register e-FIR, and visit GRP police station.",
        "tags": ["mobile_theft", "railway", "crowd"],
    },
    {
        "summary": "Mera phone bus stand pe chori ho gaya.",
        "category": "theft",
        "language": "hindi",
        "dialect": "north-india",
        "urgency_band": "medium",
        "resolution": "SIM block karne, IMEI note karne aur FIR register karne ki salah di gayi.",
        "tags": ["mobile_theft", "bus_stand"],
    },
    {
        "summary": "ನನ್ನ ಮೊಬೈಲ್ ಮಜಸ್ಟಿಕ್ ನಲ್ಲಿ ಕಳ್ಳತನವಾಗಿದೆ.",
        "category": "theft",
        "language": "kannada",
        "dialect": "bengaluru",
        "urgency_band": "medium",
        "resolution": "SIM ಬ್ಲಾಕ್ ಮಾಡಿ, IMEI ದಾಖಲಿಸಿ FIR ಮಾಡಲು ಸಲಹೆ ನೀಡಲಾಗಿದೆ.",
        "tags": ["mobile_theft", "majestic"],
    },
    {
        "summary": "Caller reported wallet stolen in crowded market.",
        "category": "theft",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "low",
        "resolution": "Advised to block cards, file complaint, and monitor transactions.",
        "tags": ["wallet_theft", "market"],
    },
    {
        "summary": "Unauthorized UPI transaction reported after clicking unknown link.",
        "category": "cyber_fraud",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "high",
        "resolution": "Advised immediate bank contact, account freeze, and report on cybercrime portal.",
        "tags": ["upi_fraud", "phishing"],
    },
    {
        "summary": "Mujhe fake call aaya aur paise kat gaye account se.",
        "category": "cyber_fraud",
        "language": "hindi",
        "dialect": "north-india",
        "urgency_band": "high",
        "resolution": "Bank ko turant contact karne aur cyber complaint file karne ko bola gaya.",
        "tags": ["fraud_call", "bank"],
    },
    {
        "summary": "Caller reports continuous abusive behavior by spouse at home.",
        "category": "domestic_violence",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "high",
        "resolution": "Escalated to police, advised safe location, connected to women helpline.",
        "tags": ["domestic_violence", "abuse"],
    },
    {
        "summary": "Mera pati mujhe maar raha hai abhi.",
        "category": "domestic_violence",
        "language": "hindi",
        "dialect": "north-india",
        "urgency_band": "high",
        "resolution": "Emergency escalation ki gayi aur police support arrange kiya gaya.",
        "tags": ["violence", "urgent"],
    },
    {
        "summary": "Caller saw suspicious person loitering repeatedly near apartment at night.",
        "category": "suspicious_activity",
        "language": "english",
        "dialect": "bengaluru",
        "urgency_band": "medium",
        "resolution": "Advised no confrontation and informed patrol unit.",
        "tags": ["suspicious", "night"],
    },
    {
        "summary": "Caller later realized suspicious person was known neighbor.",
        "category": "suspicious_activity",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "low",
        "resolution": "No action needed, reassured caller.",
        "tags": ["false_positive"],
    },
    {
        "summary": "Child missing from park since evening.",
        "category": "missing_person",
        "language": "english",
        "dialect": "mumbai",
        "urgency_band": "high",
        "resolution": "Immediate FIR advised and alert sent to nearby stations.",
        "tags": ["missing_child", "urgent"],
    },
    {
        "summary": "Mera beta subah se ghar nahi aaya.",
        "category": "missing_person",
        "language": "hindi",
        "dialect": "north-india",
        "urgency_band": "high",
        "resolution": "Police complaint register karne aur last location share karne ko bola gaya.",
        "tags": ["missing", "family"],
    },
    {
        "summary": "Bike accident with injured rider on highway.",
        "category": "road_accident",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "high",
        "resolution": "Ambulance call advised and avoid moving victim.",
        "tags": ["accident", "injury"],
    },
    {
        "summary": "Caller reports minor car collision, no injuries.",
        "category": "road_accident",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "low",
        "resolution": "Advised to exchange details and report if needed.",
        "tags": ["minor_accident"],
    },
    {
        "summary": "Smoke seen from apartment kitchen.",
        "category": "fire",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "high",
        "resolution": "Evacuation advised and fire services contacted.",
        "tags": ["fire", "smoke"],
    },
    {
        "summary": "Caller smelled gas leak in house.",
        "category": "fire",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "high",
        "resolution": "Advised ventilation, no electrical use, and gas service contact.",
        "tags": ["gas_leak"],
    },
    {
        "summary": "Elderly person unconscious at home.",
        "category": "medical",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "high",
        "resolution": "Ambulance and CPR guidance provided.",
        "tags": ["medical_emergency"],
    },
    {
        "summary": "Caller feeling chest pain and dizziness.",
        "category": "medical",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "high",
        "resolution": "Advised immediate hospital visit and ambulance.",
        "tags": ["heart_risk"],
    },
    {
        "summary": "Caller harassed in crowded bus.",
        "category": "harassment",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "medium",
        "resolution": "Advised to inform conductor and file complaint.",
        "tags": ["harassment", "bus"],
    },
    {
        "summary": "Loud music complaint at night.",
        "category": "civic",
        "language": "english",
        "dialect": "urban",
        "urgency_band": "low",
        "resolution": "Advised complaint via local police.",
        "tags": ["noise"],
    },
    {
        "summary": "Waterlogging reported after heavy rain.",
        "category": "civic",
        "language": "english",
        "dialect": "kolkata",
        "urgency_band": "medium",
        "resolution": "Escalated to municipal authority.",
        "tags": ["waterlogging"],
    },
    {
        "summary": "Street light not working in area.",
        "category": "civic",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "low",
        "resolution": "Advised municipal complaint.",
        "tags": ["infrastructure"],
    },
    {
        "summary": "Caller reports suspicious bag unattended in station.",
        "category": "suspicious_activity",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "high",
        "resolution": "Area secured and bomb squad alerted.",
        "tags": ["security", "bag"],
    },
    {
        "summary": "Caller panicked but no real threat found.",
        "category": "suspicious_activity",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "low",
        "resolution": "Reassurance provided.",
        "tags": ["false_alarm"],
    },
    {
        "summary": "Phone snatched by bike riders on road.",
        "category": "theft",
        "language": "english",
        "dialect": "delhi",
        "urgency_band": "medium",
        "resolution": "FIR registration and IMEI tracking advised.",
        "tags": ["snatching"],
    },
    {
        "summary": "Fraud SMS asking for OTP shared accidentally.",
        "category": "cyber_fraud",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "high",
        "resolution": "Account block and complaint filing advised.",
        "tags": ["otp_fraud"],
    },
    {
        "summary": "Caller reports neighbor violent argument escalating.",
        "category": "domestic_violence",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "high",
        "resolution": "Police welfare check initiated.",
        "tags": ["neighbor", "violence"],
    },
    {
        "summary": "Missing elderly person with memory issues.",
        "category": "missing_person",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "high",
        "resolution": "Alert issued and search initiated.",
        "tags": ["elderly", "missing"],
    },
    {
        "summary": "Caller stuck in flooded street.",
        "category": "civic",
        "language": "english",
        "dialect": "mumbai",
        "urgency_band": "high",
        "resolution": "Rescue team alerted.",
        "tags": ["flood"],
    },
    {
        "summary": "Dog bite incident reported.",
        "category": "medical",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "medium",
        "resolution": "Advised vaccination and hospital visit.",
        "tags": ["animal_bite"],
    },
    {
        "summary": "Caller reports online job scam.",
        "category": "cyber_fraud",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "medium",
        "resolution": "Cyber complaint advised.",
        "tags": ["job_scam"],
    },
    {
        "summary": "Caller locked out of house safely.",
        "category": "civic",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "low",
        "resolution": "Suggested locksmith service.",
        "tags": ["lockout"],
    },
    {
        "summary": "Caller hears loud fight but no confirmation.",
        "category": "suspicious_activity",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "medium",
        "resolution": "Patrol sent for verification.",
        "tags": ["disturbance"],
    },
    {
        "summary": "Caller fainted due to dehydration.",
        "category": "medical",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "medium",
        "resolution": "Hydration and medical check advised.",
        "tags": ["fainting"],
    },
    {
        "summary": "Street harassment by unknown group.",
        "category": "harassment",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "medium",
        "resolution": "Complaint filing advised.",
        "tags": ["eve_teasing"],
    },
    {
        "summary": "Caller reporting loud construction noise early morning.",
        "category": "civic",
        "language": "english",
        "dialect": "urban",
        "urgency_band": "low",
        "resolution": "Municipal complaint advised.",
        "tags": ["noise"],
    },
    {
        "summary": "Caller suspects online shopping fraud.",
        "category": "cyber_fraud",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "medium",
        "resolution": "Refund dispute and complaint advised.",
        "tags": ["ecommerce"],
    },
    {
        "summary": "Caller reports minor fire extinguished already.",
        "category": "fire",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "low",
        "resolution": "Inspection advised.",
        "tags": ["minor_fire"],
    },
    {
        "summary": "Caller stressed thinking someone is following but no evidence.",
        "category": "suspicious_activity",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "low",
        "resolution": "Reassurance and awareness advice.",
        "tags": ["false_alarm"],
    },
    {
        "summary": "Caller injured in minor fall at home.",
        "category": "medical",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "low",
        "resolution": "Basic first aid advised.",
        "tags": ["injury"],
    },
    {
        "summary": "Caller reports stolen bicycle.",
        "category": "theft",
        "language": "english",
        "dialect": "generic",
        "urgency_band": "low",
        "resolution": "Complaint registration advised.",
        "tags": ["cycle"],
    },
    {
        "summary": "Caller reports lost bag in taxi.",
        "category": "theft",
        "language": "english",
        "dialect": "mumbai",
        "urgency_band": "low",
        "resolution": "Taxi details tracking advised.",
        "tags": ["lost_property"],
    },
]


def _normalise_category(value: str) -> str:
    label = str(value or "general").strip().lower().replace("-", "_").replace(" ", "_")
    return CATEGORY_ALIASES.get(label, label)


def _normalise_case(case: dict[str, Any]) -> dict[str, Any]:
    row = deepcopy(case)
    original_category = str(row.get("category") or "general").strip().lower()
    category = _normalise_category(original_category)
    tags = [str(tag) for tag in row.get("tags") or []]
    if original_category and original_category != category and original_category not in tags:
        tags.append(original_category)
    row["category"] = category
    row["language"] = str(row.get("language") or "english").strip().lower()
    row["dialect"] = str(row.get("dialect") or "").strip().lower()
    row["urgency_band"] = str(row.get("urgency_band") or "medium").strip().lower()
    row["tags"] = tags
    return row


def resolved_case_seed_data() -> list[dict[str, Any]]:
    """Return normalized seed cases without sharing mutable state."""

    seen: set[str] = set()
    cases: list[dict[str, Any]] = []
    for case in BASE_RESOLVED_CASE_SEEDS + COMPETITION_RESOLVED_CASE_SEEDS:
        row = _normalise_case(case)
        key = " ".join(str(row.get("summary") or "").lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        cases.append(row)
    return cases
