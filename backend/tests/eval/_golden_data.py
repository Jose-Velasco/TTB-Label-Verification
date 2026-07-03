"""Shared helpers for loading golden sample data and rasterizing sample SVGs.

Kept separate from conftest.py because pytest.mark.parametrize needs the sample
list at collection time, before fixtures are available — both conftest fixtures
and test module parametrize decorators import from here to avoid re-reading
data.json in two different ways.
"""

import json
from pathlib import Path
from typing import Any

import cairosvg

SAMPLES_DIR = Path(__file__).resolve().parents[3] / "frontend" / "public" / "samples"
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
