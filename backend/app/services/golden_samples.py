"""Loads the golden label samples and rasterizes their SVGs to PNG bytes.

Canonical implementation — used both by the eval test suite (via
tests/eval/_golden_data.py, a thin re-export shim) and, at production runtime,
by the stress-test batch generator (app/services/stress_test_generator.py).
Lives under app/ (not tests/) specifically so it and its data ship in the
production Docker image, which only COPYs app/.
"""

import json
from pathlib import Path
from typing import Any

import cairosvg

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"
RASTER_WIDTH = 800
RASTER_HEIGHT = 1200


def load_golden_samples() -> list[dict[str, Any]]:
    data_path = SAMPLES_DIR / "data.json"
    return json.loads(data_path.read_text(encoding="utf-8"))


def rasterize_sample_svg(filename: str) -> bytes:
    """Rasterize a sample SVG to PNG bytes — Pillow cannot read SVG directly."""
    svg_path = SAMPLES_DIR / filename
    return cairosvg.svg2png(
        url=str(svg_path),
        output_width=RASTER_WIDTH,
        output_height=RASTER_HEIGHT,
    )
