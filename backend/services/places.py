from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote
import math

import pandas as pd
import requests


@dataclass
class Place:
    id: str
    name: str
    description: str
    country: str
    region: str
    city: str
    locality: str
    latitude: float
    longitude: float
    category: str
    subcategory: str
    rating: float | None = None
    review_count: int | None = None
    popularity_score: int | None = None
    estimated_visit_duration: int | None = None
    entry_fee: float | None = None
    currency: str = "Not available"
    opening_hours: str = "Not available"
    best_time_to_visit: str = "Not available"
    family_friendly: bool | None = None
    wheelchair_accessible: bool | None = None
    indoor_outdoor: str = "Not available"
    estimated_cost: float | None = None
    images: list[str] = field(default_factory=list)
    source: str = "Demo dataset"
    source_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def map_url(self) -> str:
        return f"https://www.openstreetmap.org/?mlat={self.latitude}&mlon={self.longitude}#map=15/{self.latitude}/{self.longitude}"


class PlaceProvider(Protocol):
    def search(self, query: str = "", category: str = "All", country: str = "All") -> list[Place]: ...
    def nearby(self, latitude: float, longitude: float, limit: int = 10) -> list[Place]: ...


class DemoPlaceProvider:
    def __init__(self, csv_path: str | Path, enable_live_search: bool = True):
        self.csv_path = Path(csv_path)
        self.enable_live_search = enable_live_search
        self._places = self._load()

    def _load(self) -> list[Place]:
        df = pd.read_csv(self.csv_path).fillna("")
        places: list[Place] = []
        for row in df.to_dict("records"):
            def maybe_float(value):
                return float(value) if value != "" else None

            def maybe_int(value):
                return int(float(value)) if value != "" else None

            def maybe_bool(value):
                return str(value).strip().lower() in {"true", "1", "yes"}

            places.append(Place(
                id=str(row["id"]), name=str(row["name"]), description=str(row["description"]),
                country=str(row["country"]), region=str(row["region"]), city=str(row["city"]), locality=str(row["locality"]),
                latitude=float(row["latitude"]), longitude=float(row["longitude"]), category=str(row["category"]),
                subcategory=str(row["subcategory"]), rating=maybe_float(row["rating"]), review_count=maybe_int(row["review_count"]),
                popularity_score=maybe_int(row["popularity_score"]), estimated_visit_duration=maybe_int(row["estimated_visit_duration"]),
                entry_fee=maybe_float(row["entry_fee"]), currency=str(row["currency"] or "Not available"),
                opening_hours=str(row["opening_hours"] or "Not available"), best_time_to_visit=str(row["best_time_to_visit"] or "Not available"),
                family_friendly=maybe_bool(row["family_friendly"]), wheelchair_accessible=maybe_bool(row["wheelchair_accessible"]),
                indoor_outdoor=str(row["indoor_outdoor"] or "Not available"), estimated_cost=maybe_float(row["estimated_cost"]),
                source=str(row["source"] or "Demo dataset"), source_url=str(row["source_url"] or ""),
            ))
        return places

    @property
    def places(self) -> list[Place]:
        return self._places

    def search(self, query: str = "", category: str = "All", country: str = "All") -> list[Place]:
        q = query.lower().strip()
        results = [p for p in self._places if (category == "All" or p.category == category) and (country == "All" or p.country == country)]
        if q:
            tokens = [token for token in q.replace(",", " ").split() if token]
            results = [p for p in results if all(token in " ".join([p.name, p.description, p.city, p.country, p.region, p.category]).lower() for token in tokens)]
            if self.enable_live_search and len(results) < 3:
                live_results = self._nominatim_search(query)
                known = {(p.name.lower(), round(p.latitude, 3), round(p.longitude, 3)) for p in results}
                results.extend(p for p in live_results if (p.name.lower(), round(p.latitude, 3), round(p.longitude, 3)) not in known)
        return sorted(results, key=lambda p: (p.popularity_score or 0, p.rating or 0), reverse=True)

    def _nominatim_search(self, query: str, limit: int = 8) -> list[Place]:
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "jsonv2", "limit": limit, "addressdetails": 1},
                headers={"User-Agent": "TravelMind3D/1.0 (educational project)"}, timeout=6,
            )
            response.raise_for_status()
            results: list[Place] = []
            for index, item in enumerate(response.json()):
                address = item.get("address", {})
                display = item.get("display_name", query).split(",")
                name = item.get("name") or display[0].strip()
                city = address.get("city") or address.get("town") or address.get("village") or address.get("state") or name
                country = address.get("country", "Unknown")
                results.append(Place(
                    id=f"osm-{item.get('osm_type', 'place')}-{item.get('osm_id', index)}", name=name,
                    description=f"OpenStreetMap result for {item.get('display_name', query)}.", country=country,
                    region=address.get("state", "Not available"), city=city, locality=address.get("suburb", "Not available"),
                    latitude=float(item["lat"]), longitude=float(item["lon"]), category="Place", subcategory=item.get("type", "location"),
                    source="OpenStreetMap", source_url=f"https://www.openstreetmap.org/{item.get('osm_type', 'node')}/{item.get('osm_id', '')}",
                ))
            return results
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return []

    def nearby(self, latitude: float, longitude: float, limit: int = 10) -> list[Place]:
        def distance(place: Place) -> float:
            lat = math.radians(place.latitude - latitude)
            lon = math.radians(place.longitude - longitude)
            return lat * lat + lon * lon * math.cos(math.radians(latitude)) ** 2
        return sorted(self._places, key=distance)[:limit]


def wikipedia_image(place_name: str) -> str | None:
    """Return a real Wikipedia thumbnail when available; never invent an image URL."""
    try:
        response = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(place_name.replace(' ', '_'))}",
            headers={"User-Agent": "TravelMind3D/1.0 (educational project)"}, timeout=5,
        )
        if response.ok:
            return response.json().get("thumbnail", {}).get("source")
    except (requests.RequestException, ValueError, TypeError):
        pass
    return None
