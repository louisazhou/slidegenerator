"""Slide Generator – top-level package

Exposes the public API (`SlideGenerator`, etc.) **and** sets up a minimal
logging configuration so that every sub-module can call

```python
import logging
logger = logging.getLogger(__name__)
```

and honour a single environment variable `SLIDEGEN_LOG_LEVEL`.
"""

from __future__ import annotations

import logging
import os

# ------------------------------------------------------------------
# Default logging – honour env var, otherwise INFO.
# ------------------------------------------------------------------
LOG_LEVEL = os.getenv("SLIDEGEN_LOG_LEVEL", "INFO").upper()
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

# Public API re-exports ------------------------------------------------
from .generator import SlideGenerator  # noqa: E402  (import after logger)
from .layout_engine import LayoutEngine  # noqa: E402
from .pptx_renderer import PPTXRenderer  # noqa: E402
from .models import Block  # noqa: E402

__all__ = [
    "SlideGenerator",
    "LayoutEngine",
    "PPTXRenderer",
    "Block",
] 