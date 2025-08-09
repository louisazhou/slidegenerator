#!/usr/bin/env python3
"""Minimal end-to-end demo that renders a small Markdown deck directly to
Google Slides using the new GSlideRenderer pathway.

Prerequisites
-------------
1. `google-api-python-client`, `google-auth` and friends installed.
2. Either
   • *Service-account JSON* – set env var `GOOGLE_SLIDES_CREDENTIALS` to the
     JSON file **or** place a `credentials.json` file in the project root, **or**
   • *OAuth token* – first-time run will open a browser window, afterwards the
     cached `token.json` is reused.

The script is intentionally self-contained: it builds a very small Markdown
string with a heading, paragraph, image and coloured speaker note, then calls
:pyclass:`slide_generator.SlideGenerator` with `format="gslides"`.

Upon success its stdout prints the resulting *presentation ID* and a direct
link.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import sys

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from slide_generator.generator import SlideGenerator
import json

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

# Image creation functionality removed - now using comprehensive demo content with web-accessible images

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NOTEPAD = PROJECT_ROOT / "gslides_notepad.json"

# If the user dropped a service-account file in the repo root we export the env
cred_file = PROJECT_ROOT / "credentials.json"
if cred_file.exists():
    os.environ.setdefault("GOOGLE_SLIDES_CREDENTIALS", str(cred_file))

# ---------------------------------------------------------------------------
# Minimal Markdown deck
# ---------------------------------------------------------------------------

# Read the full demo_content.md file to use as our comprehensive test
DEMO_CONTENT_PATH = PROJECT_ROOT / "examples" / "demo_content.md"

def prepare_web_accessible_images():
    """Copy assets to output directory and provide web-accessible URLs."""
    import shutil
    
    assets_dir = PROJECT_ROOT / "examples" / "assets"
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    
    # Map of local files to web URLs (for now, using placeholder service)
    # In production, these would be uploaded to a CDN or file hosting service
    image_mappings = {}
    
    # Use the actual chart images from the GitHub repository
    # These are the real assets from examples/assets/ made publicly accessible via GitHub
    image_mappings = {
        "assets/chart_bar.png": "https://raw.githubusercontent.com/louisazhou/slidegenerator/main/examples/assets/chart_bar.png",
        "assets/chart_pie.png": "https://raw.githubusercontent.com/louisazhou/slidegenerator/main/examples/assets/chart_pie.png"
    }
    
    print("📊 Using web-accessible chart images:")
    for local_path, web_url in image_mappings.items():
        print(f"  {local_path} → {web_url}")
    
    return image_mappings

def load_demo_content():
    """Load the comprehensive demo content from demo_content.md and update image URLs"""
    try:
        content = DEMO_CONTENT_PATH.read_text(encoding='utf-8')
        
        # Replace local asset paths with web-accessible URLs
        image_mappings = prepare_web_accessible_images()
        
        for local_path, web_url in image_mappings.items():
            content = content.replace(local_path, web_url)
            
        return content
    except FileNotFoundError:
        print(f"Warning: {DEMO_CONTENT_PATH} not found, using fallback content")
        return """# 🍀 Google Slides Demo
        
Welcome to *Slide Generator* → **Google Slides** pipeline!

## Sample Table

| Feature | Status | Notes |
|---------|--------|-------|
| Text boxes | ✅ | With scaling |
| Images | ✅ | Aspect ratio preserved |
| Tables | ✅ | Basic support |

??? [Speaker note]{.red}: demo generated at runtime with **enhanced** features.
"""

MARKDOWN_DECK = load_demo_content()

# ---------------------------------------------------------------------------
# Async driver
# ---------------------------------------------------------------------------

def _load_last_id():
    if NOTEPAD.exists():
        try:
            return json.loads(NOTEPAD.read_text()).get("presentation_id")
        except Exception:
            return None
    return None

def _save_last_id(pid: str):
    try:
        NOTEPAD.write_text(json.dumps({"presentation_id": pid}))
    except Exception:
        pass

async def _run_demo():
    print("🚀 Starting comprehensive Google Slides demo with full demo_content.md...")
    print(f"📄 Loading content from: {DEMO_CONTENT_PATH}")
    
    gen = SlideGenerator(output_dir="output", debug=True)
    last_id = _load_last_id()
    presentation_id = await gen.generate(
        MARKDOWN_DECK,
        output_path="demo",  # ignored for gslides
        format="gslides",
        presentation_id=last_id,
    )
    _save_last_id(presentation_id)
    print("✅ Google Slides ready:")
    print(f"   https://docs.google.com/presentation/d/{presentation_id}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    try:
        asyncio.run(_run_demo())
    except Exception as exc:
        print("❌ Demo failed:", exc)
        raise

