"""Load System objects from JSON. CSV loading is not provided at this
schema complexity — JSON's nested structure maps far more directly onto
buses/lines/generators/renewables/storages than flat CSV columns would."""

import json
from pathlib import Path

from ed_model.data.schema import Bus, Line, Generator, CostSegment, Renewable, Storage, System


def load_system_json(path: str | Path) -> System:
    """Expects a JSON object with keys: buses, lines, generators,
    renewables, storages, demand. See data/ieee_case_examples/ for
    example files matching this format."""
    data = json.loads(Path(path).read_text())

    buses = [Bus(**b) for b in data.get("buses", [])]
    lines = [Line(**l) for l in data.get("lines", [])]

    generators = []
    for g in data.get("generators", []):
        g = dict(g)
        if "segments" in g and g["segments"] is not None:
            g["segments"] = tuple(CostSegment(**s) for s in g["segments"])
        generators.append(Generator(**g))

    renewables = [Renewable(**r) for r in data.get("renewables", [])]
    storages = [Storage(**s) for s in data.get("storages", [])]
    demand = data["demand"]

    return System(
        buses=buses, lines=lines, generators=generators,
        renewables=renewables, storages=storages, demand=demand,
    )
