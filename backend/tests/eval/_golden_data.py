"""Re-exports the golden-sample loader/rasterizer for the eval suite.

The canonical implementation lives in app.services.golden_samples — it moved
there (out of tests/) because the stress-test batch generator needs it at
production runtime too, and the production Docker image only ships app/, not
tests/. Kept as a shim (not just updating call sites) so this stays a single
import path for every test module already using it.
"""

from app.services.golden_samples import (
    RASTER_HEIGHT,
    RASTER_WIDTH,
    SAMPLES_DIR,
    load_golden_samples,
    rasterize_sample_svg,
)

__all__ = [
    "RASTER_HEIGHT",
    "RASTER_WIDTH",
    "SAMPLES_DIR",
    "load_golden_samples",
    "rasterize_sample_svg",
]
