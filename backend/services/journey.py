from __future__ import annotations

from dataclasses import dataclass, asdict
from urllib.parse import quote_plus


@dataclass(frozen=True)
class JourneyOption:
    name: str
    segments: list[dict]
    duration_hours: float
    estimated_cost: float
    changes: int
    convenience: str
    source_status: str = "Estimated planning model; check provider before travel."


def _cost(origin: str, destination: str, base: float) -> float:
    # A transparent local estimate; never presented as live fare or availability.
    distance_factor = max(1.0, min(2.4, (len(origin) + len(destination)) / 18))
    return round(base * distance_factor, 0)


def journey_options(origin: str, destination: str, currency: str = "INR") -> list[dict]:
    origin = origin.strip() or "Your origin"
    destination = destination.strip() or "Your destination"
    options = [
        JourneyOption("Direct bus", [{"from": origin, "board": f"Nearest bus terminal in {origin}", "vehicle": "Bus", "to": destination, "drop": f"Main bus terminal in {destination}", "duration": "10–14 h", "cost": _cost(origin, destination, 650), "transfer": "0 h", "action": "Search bus"}], 12, _cost(origin, destination, 650), 0, "Good"),
        JourneyOption("Train + local transfer", [{"from": origin, "board": f"Nearest practical railway station to {origin}", "vehicle": "Local bus/auto", "to": "Interchange railway station", "drop": "Railway station", "duration": "1–2 h", "cost": _cost(origin, destination, 120), "transfer": "0.5 h", "action": "Find station"}, {"from": "Interchange railway station", "board": "Railway station", "vehicle": "Train", "to": destination, "drop": f"Main railway station in {destination}", "duration": "8–12 h", "cost": _cost(origin, destination, 520), "transfer": "1 h", "action": "Search trains"}, {"from": f"Main railway station in {destination}", "board": "Station exit", "vehicle": "Metro/cab", "to": destination, "drop": "Stay or itinerary base", "duration": "0.5–1 h", "cost": 180, "transfer": "—", "action": "Open directions"}], 11.5, _cost(origin, destination, 820), 2, "Balanced"),
        JourneyOption("Flight + airport transfer", [{"from": origin, "board": "Nearest practical airport", "vehicle": "Local transfer", "to": "Departure airport", "drop": "Airport terminal", "duration": "1–3 h", "cost": 500, "transfer": "1 h", "action": "Open airport map"}, {"from": "Departure airport", "board": "Airport terminal", "vehicle": "Flight", "to": destination, "drop": f"Nearest airport to {destination}", "duration": "1–3 h", "cost": _cost(origin, destination, 3200), "transfer": "1.5 h", "action": "Check flights"}, {"from": f"Nearest airport to {destination}", "board": "Airport exit", "vehicle": "Cab/transfer", "to": destination, "drop": "Stay or itinerary base", "duration": "0.5–1 h", "cost": 650, "transfer": "—", "action": "Open directions"}], 6, _cost(origin, destination, 4350), 2, "Fastest"),
    ]
    return [asdict(option) for option in options]


def budget_breakdown(transport: float, nights: int, nightly_stay: float, travelers: int, days: int, activities: float = 500) -> dict:
    stay = nights * nightly_stay
    local = days * 300
    food = days * travelers * 250
    emergency = 500
    total = transport + stay + local + food + activities + emergency
    return {"transport": round(transport), "stay": round(stay), "food": round(food), "local_transport": round(local), "activities": round(activities), "emergency": emergency, "total": round(total), "per_person": round(total / max(1, travelers)), "group_total": round(total)}


def provider_search_url(kind: str, destination: str) -> str:
    q = quote_plus(destination)
    if kind == "stay":
        return f"https://www.booking.com/searchresults.html?ss={q}"
    if kind == "train":
        return f"https://www.google.com/search?q=trains+to+{q}"
    if kind == "bus":
        return f"https://www.google.com/search?q=bus+to+{q}"
    if kind == "flight":
        return f"https://www.google.com/search?q=flights+to+{q}"
    return f"https://www.google.com/maps/search/{q}"
