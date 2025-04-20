from __future__ import annotations
from functools import lru_cache
from typing import TypedDict

from haversine import haversine


class RegionType(TypedDict):
    city: str
    continent: str
    location: tuple[float, float]


REGIONS: dict[str, RegionType] = {
    "lhr": {
        "city": "London",
        "continent": "europe",
        "location": (51.5033466, -0.0793965),
    },
    "ams": {
        "city": "Amsterdam",
        "continent": "europe",
        "location": (52.370216, 4.895168),
    },
    "den": {
        "city": "Denver",
        "continent": "us",
        "location": (39.739235, -104.990250),
    },
    "lax": {
        "city": "Los Angeles",
        "continent": "us",
        "location": (34.052235, -118.243683),
    },
    "ewr": {
        "city": "Secaucus",
        "continent": "us",
        "location": (40.778198, -74.067863),
    },
    "nrt": {
        "city": "Tokyo",
        "continent": "asia",
        "location": (35.6840574, 139.7744912),
    },
    "bom": {
        "city": "Mumbai",
        "continent": "asia",
        "location": (19.0815772, 72.8866275),
    },
}


@lru_cache(maxsize=256)
def get_closest_region(region: str, choices: tuple[str, ...]) -> str | None:
    """Get the closest region from a number of choices.

    Args:
        region: The starting region.
        choices: A list of choices.

    Returns:
        The closest region.
    """
    if not choices:
        # No choices
        return None
    if region in choices:
        # Same region
        return region
    if len(choices) == 1:
        # One region
        return choices[0]

    region_data = REGIONS[region]
    continent = region_data["continent"]
    location = region_data["location"]

    # Find the closest region, but prefer same continent
    region_choices = sorted(
        choices,
        key=lambda region_name: (
            continent != REGIONS[region_name]["continent"],
            haversine(location, REGIONS[region_name]["location"]),
        ),
    )
    closest = region_choices[0]
    return closest


if __name__ == "__main__":
    all_regions = list(REGIONS.keys())
    print(get_closest_region("lhr", ("lhr", "den", "lax")))
    print(get_closest_region("lhr", ("ams", "den", "lax")))
    print(get_closest_region("lhr", ("den", "lax", "ewr")))
    print(get_closest_region("nrt", tuple("lhr,ams,den,lax,ewr,bom".split(","))))
