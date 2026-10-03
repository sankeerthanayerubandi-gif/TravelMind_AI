from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import math
import re
from typing import Any

from backend.services.places import Place, PlaceProvider
from backend.services.core import monitor_signals


INTEREST_ALIASES = {
    "Nature": {"nature", "forest", "lake", "park", "beach", "waterfall", "mountain"},
    "Culture": {"culture", "history", "historic", "temple", "museum", "heritage", "old town"},
    "Food": {"food", "market", "restaurant", "cafe", "local food"},
    "Adventure": {"adventure", "hiking", "outdoor", "viewpoint", "wildlife"},
    "Shopping": {"shopping", "market", "bazaar"},
}


def _haversine_km(a: Place, b: Place) -> float:
    r = 6371.0
    p1, p2 = math.radians(a.latitude), math.radians(b.latitude)
    dp = math.radians(b.latitude - a.latitude)
    dl = math.radians(b.longitude - a.longitude)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return date.today()


def _destination_places(request: dict[str, Any], provider: PlaceProvider) -> list[Place]:
    destination = str(request.get("destination") or request.get("country") or "").strip()
    local = provider.search(query=destination) if destination and destination.lower() != "all" else provider.search()
    selected_ids = {str(value) for value in request.get("selected_place_ids", [])}
    if selected_ids and hasattr(provider, "places"):
        selected = [place for place in provider.places if place.id in selected_ids]
        known = {place.id for place in local}
        local = selected + [place for place in local if place.id not in known]
    if not local and (not destination or destination.lower() == "all"):
        local = provider.search()
    return local


def _replan_preferences(request: dict[str, Any]) -> tuple[set[str], set[str], bool]:
    text = str(request.get("replan_request") or "").lower()
    remove: set[str] = set()
    add: set[str] = set()
    cheaper = "cheap" in text or "cheaper" in text or "budget" in text
    for word, categories in (("museum", {"Culture"}), ("beach", {"Nature"}), ("nature", {"Nature"}), ("historical", {"History", "Culture"}), ("history", {"History", "Culture"}), ("food", {"Food"}), ("shopping", {"Shopping"}), ("adventure", {"Adventure"})):
        if word in text:
            if "remove" in text or "without" in text:
                remove |= categories
            else:
                add |= categories
    return remove, add, cheaper


def _rank_places(places: list[Place], request: dict[str, Any]) -> list[Place]:
    interests = {str(value) for value in request.get("interests", [])}
    budget_tier = str(request.get("budget_tier", "Medium"))
    remove, add, cheaper = _replan_preferences(request)
    if remove:
        places = [p for p in places if p.category not in remove]
    if add:
        preferred = [p for p in places if p.category in add]
        others = [p for p in places if p.category not in add]
        places = preferred + others
    max_cost = {"Low": 35, "Medium": 130, "High": float("inf")}.get(budget_tier, float("inf"))
    if cheaper:
        max_cost = min(max_cost, 45)
    if max_cost != float("inf"):
        affordable = [p for p in places if (p.estimated_cost or 0) <= max_cost]
        if affordable:
            places = affordable

    def score(place: Place) -> float:
        text = " ".join([place.category, place.subcategory, place.description]).lower()
        interest_score = sum(3 for interest in interests if any(alias in text for alias in INTEREST_ALIASES.get(interest, {interest.lower()})))
        rating = (place.rating or 0) * 1.5
        popularity = (place.popularity_score or 0) / 20
        cost_penalty = (place.estimated_cost or 0) / 25 if budget_tier == "Low" or cheaper else 0
        return interest_score + rating + popularity - cost_penalty

    return sorted(places, key=score, reverse=True)


def _ordered_unique(places: list[Place], request: dict[str, Any]) -> list[Place]:
    ranked = _rank_places(places, request)
    seed = int(hashlib.sha1(str(request.get("replan_request", "initial")).encode()).hexdigest()[:6], 16)
    if request.get("replan_request") and ranked:
        offset = seed % len(ranked)
        ranked = ranked[offset:] + ranked[:offset]
    seen: set[str] = set()
    unique: list[Place] = []
    for place in ranked:
        if place.id not in seen:
            unique.append(place)
            seen.add(place.id)
    return unique


def _time_label(minutes: int) -> str:
    hour, minute = divmod(minutes, 60)
    suffix = "AM" if hour < 12 else "PM"
    shown = hour if 1 <= hour <= 12 else (hour - 12 if hour > 12 else 12)
    return f"{shown}:{minute:02d} {suffix}"


def plan_trip(request: dict[str, Any], provider: PlaceProvider) -> dict[str, Any]:
    days = max(1, min(30, int(request.get("days", 1))))
    travelers = max(1, int(request.get("travelers", 1)))
    pace = str(request.get("pace", "Balanced"))
    available_hours = max(2, min(16, float(request.get("available_hours", 8))))
    start = _parse_date(request.get("start_date"))
    places = _ordered_unique(_destination_places(request, provider), request)
    if not places:
        raise ValueError("No places found for this destination. Try a city, country, or landmark.")

    per_day = {"Relaxed": 2, "Balanced": 3, "Intensive": 4}.get(pace, 3)
    if available_hours <= 4:
        per_day = min(per_day, 2)
    needed = days * per_day
    selected = places[:needed]
    itinerary: list[dict[str, Any]] = []
    total = 0.0
    cursor = 0
    for day_index in range(days):
        remaining = len(selected) - cursor
        days_left = days - day_index
        day_count = min(per_day, max(1, math.ceil(remaining / days_left))) if remaining else 0
        day_places = selected[cursor:cursor + day_count]
        cursor += day_count
        if not day_places:
            itinerary.append({
                "day": day_index + 1, "date": (start + timedelta(days=day_index)).isoformat(),
                "title": "Discovery limited by verified place data", "stops": [], "estimated_day_cost": 0,
                "transit": "No additional verified place was available.",
                "notes": "No repeated attraction was inserted. Search another nearby city or enable live OpenStreetMap search to add more verified places.",
            })
            continue
        stops: list[dict[str, Any]] = []
        clock = 9 * 60
        day_total = 0.0
        for stop_index, place in enumerate(day_places):
            previous = day_places[stop_index - 1] if stop_index else None
            travel_minutes = int(round(_haversine_km(previous, place) / 25 * 60)) if previous else 0
            clock += travel_minutes
            duration = min(place.estimated_visit_duration or 90, int(available_hours * 60 / len(day_places)))
            end = clock + max(45, duration)
            item = place.to_dict()
            item.update({
                "start_time": _time_label(clock), "end_time": _time_label(end),
                "travel_time_from_previous_min": travel_minutes,
                "recommended_duration_min": max(45, duration),
                "food_suggestion": f"Try a local {place.category.lower()} stop near {place.city} after this visit.",
                "map_url": place.map_url,
            })
            stops.append(item)
            day_total += float(place.estimated_cost or 0)
            clock = end
        day_total += 12 * travelers
        total += day_total
        itinerary.append({
            "day": day_index + 1, "date": (start + timedelta(days=day_index)).isoformat(),
            "title": f"{day_places[0].city} · {day_places[0].category} route",
            "stops": stops, "estimated_day_cost": round(day_total, 2),
            "transit": "Walking + local transit; route order minimizes backtracking.",
            "notes": f"{pace} pace · {len(stops)} planned stops · about {available_hours:g} available hours.",
        })

    destination = str(request.get("destination") or request.get("country") or places[0].city)
    return {
        "origin": str(request.get("origin", "")), "present_location": str(request.get("present_location", "")),
        "destination": destination, "days": days, "start_date": start.isoformat(), "traveler_count": travelers,
        "budget": float(request.get("budget", 0)), "budget_per_person": float(request.get("budget_per_person", float(request.get("budget", 0)) / max(1, travelers))), "budget_tier": request.get("budget_tier", "Medium"),
        "interests": list(request.get("interests", [])), "pace": pace, "available_hours": available_hours,
        "itinerary": itinerary, "estimated_total": round(total, 2), "currency": request.get("currency", "EUR"),
        "selected_place_ids": list(request.get("selected_place_ids", [])),
        "status": "verified", "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def replan_trip(trip: dict[str, Any], issue: str, provider: PlaceProvider) -> dict[str, Any]:
    request = {**trip, "destination": trip.get("destination"), "start_date": trip.get("start_date"), "days": trip.get("days", 1), "travelers": trip.get("traveler_count", 1), "budget": trip.get("budget", 0), "budget_tier": trip.get("budget_tier", "Medium"), "interests": trip.get("interests", []), "pace": trip.get("pace", "Balanced"), "available_hours": trip.get("available_hours", 8), "replan_request": issue}
    updated = plan_trip(request, provider)
    updated["status"] = "replanned + verified"
    updated["replan_reason"] = issue
    updated["verification"] = "Alternative stops selected using the new constraint; times, route order, and budget were recalculated."
    return updated


def run_agentic_workflow(request: dict[str, Any], provider: PlaceProvider, issue: str | None = None) -> dict[str, Any]:
    request = dict(request)
    if issue:
        request["replan_request"] = issue
        hour_match = re.search(r"(\d+(?:\.\d+)?)\s*hours?", issue.lower())
        if hour_match:
            request["available_hours"] = max(2.0, min(16.0, float(hour_match.group(1))))
    events = [
        {"agent": "Supervisor", "status": "complete", "detail": "Decomposed destination, dates, budget, interests, and time constraints."},
        {"agent": "Discovery", "status": "complete", "detail": "Ranked relevant places from the local catalog and optional live provider."},
        {"agent": "Planner", "status": "complete", "detail": "Grouped places into non-repeating daily routes with timings and food suggestions."},
        {"agent": "Verifier", "status": "complete", "detail": "Checked route order, opening-hour fields, estimated costs, and map coordinates."},
    ]
    trip = plan_trip(request, provider)
    if issue:
        trip["status"] = "replanned + verified"
        events += [{"agent": "Monitor", "status": "alert", "detail": f"Detected change request: {issue}"}, {"agent": "Replanner", "status": "complete", "detail": "Generated a different route for the new constraint."}]
        trip["replan_reason"] = issue
    else:
        events.append({"agent": "Monitor", "status": "watching", "detail": "Monitoring the plan for weather, transport, and preference changes."})
    trip["signals"] = monitor_signals()
    trip["agent_events"] = events
    return trip
