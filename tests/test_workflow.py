from datetime import date
from pathlib import Path

from backend.graph.workflow import run_agentic_workflow
from backend.services.core import convert_currency
from backend.services.places import DemoPlaceProvider
from backend.services.phase5 import booking_links, crowd_level, group_profile
from backend.services.journey import budget_breakdown, journey_options


PROVIDER = DemoPlaceProvider(Path(__file__).parents[1] / "backend" / "data" / "demo_places.csv", enable_live_search=False)


def test_workflow_plans_and_replans():
    request = {"destination": "All", "days": 3, "budget": 1500, "budget_tier": "Medium", "pace": "Balanced", "travelers": 2, "interests": ["Nature"], "start_date": date.today()}
    trip = run_agentic_workflow(request, PROVIDER)
    assert trip["status"] == "verified"
    assert len(trip["itinerary"]) == 3
    assert all(day["stops"] for day in trip["itinerary"])
    assert all("start_time" in stop and "map_url" in stop for day in trip["itinerary"] for stop in day["stops"])
    updated = run_agentic_workflow({**request, "replan_request": "make it cheaper and add food places"}, PROVIDER, "make it cheaper and add food places")
    assert updated["status"] == "replanned + verified"
    assert updated["replan_reason"]
    assert updated["itinerary"] != trip["itinerary"]


def test_today_and_personalization_change_the_route():
    base = {"destination": "Japan", "days": 2, "travelers": 1, "budget": 500, "budget_tier": "Low", "pace": "Relaxed", "interests": ["Nature"], "start_date": date.today()}
    trip = run_agentic_workflow(base, PROVIDER)
    assert trip["start_date"] == date.today().isoformat()
    assert trip["itinerary"][0]["date"] == date.today().isoformat()
    food_trip = run_agentic_workflow({**base, "destination": "Spain", "interests": ["Food"], "budget_tier": "High"}, PROVIDER)
    assert food_trip["itinerary"] != trip["itinerary"]


def test_utility_fallbacks_are_usable():
    conversion = convert_currency(100, "EUR", "INR")
    assert conversion["converted"] > 0
    assert "INR" == conversion["target"]


def test_phase5_context_group_and_booking_helpers():
    trip = run_agentic_workflow({"destination": "Japan", "origin": "Visakhapatnam", "present_location": "Tokyo", "days": 1, "budget": 500, "budget_tier": "Low", "pace": "Relaxed", "travelers": 1, "interests": ["Nature"], "start_date": date.today()}, PROVIDER)
    assert trip["origin"] == "Visakhapatnam"
    assert trip["present_location"] == "Tokyo"
    profile = group_profile([
        {"name": "A", "budget": 500, "interests": ["Nature", "Food"], "must_visit": "Araku", "avoid": "nightlife"},
        {"name": "B", "budget": 700, "interests": ["Nature", "Culture"], "must_visit": "Araku", "avoid": ""},
    ])
    assert profile["common"] == ["Nature"]
    assert profile["must_visit"] == ["Araku"]
    assert crowd_level(PROVIDER.places[0])["label"] in {"Less crowded", "Moderate", "Busy"}
    links = booking_links("Kyoto, Japan", "Arashiyama")
    assert links["Stays"].startswith("https://www.booking.com/")
    assert links["Food"].startswith("https://www.google.com/maps/")


def test_multimodal_journey_and_cost_breakdown_are_transparent():
    options = journey_options("Mummidivaram", "Hyderabad")
    assert {option["name"] for option in options} == {"Direct bus", "Train + local transfer", "Flight + airport transfer"}
    assert all(option["segments"] and option["source_status"].startswith("Estimated") for option in options)
    assert any(len(option["segments"]) > 1 for option in options)
    costs = budget_breakdown(1200, 2, 900, 4, 3, activities=500)
    assert costs["total"] == costs["transport"] + costs["stay"] + costs["food"] + costs["local_transport"] + costs["activities"] + costs["emergency"]
    assert costs["per_person"] > 0 and costs["group_total"] == costs["total"]
