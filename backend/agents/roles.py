"""Named agent roles used by the workflow. Kept small and composable for Cloud deployment."""

ROLES = {
    "supervisor": "Decomposes the travel brief and coordinates specialists.",
    "planner": "Builds a day-by-day itinerary from normalized places.",
    "verifier": "Checks budget, timing, and destination fit.",
    "replanner": "Finds alternatives after a monitored change.",
    "specialists": ["transportation", "food", "accommodation", "attractions", "weather", "location", "currency", "hospital", "app_recommender"],
}
