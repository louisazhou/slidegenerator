#!/usr/bin/env python3
"""
🎯 Comprehensive Feature Demo - Slide Generator
===============================================

This single file demonstrates ALL implemented features:
• Inline styling (bold, italic, code, highlight)
• Table rendering with HTML auto-width
• Theme support (default & dark)
• Markdown formatting (headers, lists, code blocks)
• Pagination with proper boundary detection
• Professional PowerPoint output

Run this file to generate demonstration slides showcasing every feature.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the project root to the path so we can import our modules
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from slide_generator.generator import SlideGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


async def generate_theme_demos():
    """Generate comprehensive demonstrations for both themes and both parsers."""
    from pathlib import Path

    # Read demo content from file
    demo_content_path = Path(__file__).parent / "demo_content.md"
    if not demo_content_path.exists():
        raise FileNotFoundError(f"Demo content file not found: {demo_content_path}")
    
    demo_content = demo_content_path.read_text(encoding="utf-8")
    
    # Create output directory in current working directory (path-independent)
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    demos_generated = []
    
    # Generate for both themes
    for theme_name in ["default", "dark"]:
        logger.info(f"Generating {theme_name} theme presentation...")
        
        try:
            generator = SlideGenerator(
                output_dir="output", 
                theme=theme_name, 
                debug=True,
                base_dir=Path(__file__).parent  # Point to examples directory where assets are located
            )
            
            # Await the async generate method
            output_filename = f"comprehensive_demo_{theme_name}.pptx"
            pptx_path = await generator.generate(demo_content, f"output/{output_filename}")
            
            logger.info(f"✅ Generated: {pptx_path}")
            demos_generated.append((theme_name, pptx_path))
            
        except Exception:
            logger.error(f"❌ Error generating {theme_name} theme:", exc_info=True)
    
    return demos_generated


def main():
    """Generate comprehensive feature demonstrations."""
    
    logger.info("🚀 COMPREHENSIVE SLIDE GENERATOR DEMO")
    logger.info("=" * 50)
    logger.info("")
    logger.info("This demo showcases ALL implemented features:")
    logger.info("• ✨ Inline styling (bold, italic, code, highlight)")
    logger.info("• 📊 Smart table rendering with HTML auto-width")
    logger.info("• 🎨 Theme support (default & dark)")
    logger.info("• 💻 Code block formatting")
    logger.info("• 📝 List formatting (ordered & unordered)")
    logger.info("• 📏 Intelligent pagination")
    logger.info("• 🔧 Professional PowerPoint output")
    logger.info("")
    
    # Generate demos for both themes
    asyncio.run(generate_theme_demos())
    
    logger.info("")
    logger.info("🎯 GENERATION COMPLETE!")
    logger.info("=" * 30)
    
    print()
    print("🎉 Demo complete! Open the PowerPoint files to explore all features.")


if __name__ == "__main__":
    main() 