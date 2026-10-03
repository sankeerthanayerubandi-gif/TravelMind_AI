from __future__ import annotations

from collections import Counter
from hashlib import sha1
from urllib.parse import quote_plus

from backend.services.places import Place


def crowd_level(place: Place) -> dict[str, str]:
    score = (place.popularity_score or 0) + int((place.rating or 0) * 4)
    if score >= 85:
        label, color = "Busy", "orange"
    elif score >= 60:
        label, color = "Moderate", "yellow"
    else:
        label, color = "Less crowded", "green"
    return {"label": label, "color": color, "basis": "Catalog popularity estimate; not live crowd data."}


def booking_links(destination: str, place: str) -> dict[str, str]:
    query = quote_plus(f"{place}, {destination}")
    return {
        "Stays": f"https://www.booking.com/searchresults.html?ss={query}",
        "Food": f"https://www.google.com/maps/search/restaurants+near+{query}",
        "Transport": f"https://www.google.com/maps/search/transport+near+{query}",
        "Rental cars": f"https://www.google.com/maps/search/car+rental+near+{query}",
    }


def group_profile(members: list[dict]) -> dict:
    members = [m for m in members if m.get("name", "").strip()]
    interest_lists = [set(m.get("interests", [])) for m in members]
    common = sorted(set.intersection(*interest_lists)) if interest_lists else []
    all_interests = Counter(i for values in interest_lists for i in values)
    conflicts = sorted([name for name, count in all_interests.items() if count == 1])
    must_visit = sorted({p.strip() for m in members for p in m.get("must_visit", "").split(",") if p.strip()})
    avoid = sorted({p.strip() for m in members for p in m.get("avoid", "").split(",") if p.strip()})
    budgets = [float(m.get("budget", 0) or 0) for m in members if float(m.get("budget", 0) or 0) > 0]
    return {"members": len(members), "common": common, "conflicts": conflicts, "must_visit": must_visit, "avoid": avoid, "budget": round(sum(budgets), 2), "votes": {}}


def invite_code(seed: str) -> str:
    return sha1(seed.encode()).hexdigest()[:8].upper()
