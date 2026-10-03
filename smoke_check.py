from pathlib import Path
from backend.services.places import DemoPlaceProvider
from backend.graph.workflow import run_agentic_workflow

provider = DemoPlaceProvider(Path(__file__).parent / "backend" / "data" / "demo_places.csv")
trip = run_agentic_workflow({"country": "Japan", "days": 3, "budget": 1500, "pace": "Balanced", "travelers": 2}, provider)
assert trip["status"] == "verified"
assert len(trip["itinerary"]) == 3
updated = run_agentic_workflow({"country": "Japan", "days": 3, "budget": 1500, "pace": "Balanced", "travelers": 2}, provider, "Heavy rain")
assert updated["status"] == "replanned + verified"
print(f"SMOKE_OK places={len(provider.places)} estimated={trip['estimated_total']} reason={updated['replan_reason']}")
