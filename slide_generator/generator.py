#!/usr/bin/env python3
"""
Main slide generator module that ties together layout engine and PowerPoint renderer.
"""

import os
import logging
from pathlib import Path

from .paths import prepare_workspace
from .layout_engine import LayoutEngine
from .pptx_renderer import PPTXRenderer

logger = logging.getLogger(__name__)


class SlideGenerator:
    """
    Main class for generating PowerPoint slides from markdown.
    """
    
    def __init__(
        self,
        *,
        output_dir,
        base_dir: str = None,
        keep_tmp: bool = False,
        debug: bool = False,
        theme: str = "default",
    ):
        """Create a new :class:`SlideGenerator`.

        Parameters
        ----------
        output_dir
            Directory where the final PPTX (and optional *preview.html*) will
            be written.  *Required*.
        base_dir
            Base directory for resolving relative image paths in markdown.
            If None, defaults to current working directory.
        keep_tmp
            If ``True`` the working directory ``.sg_tmp`` inside *output_dir*
            will be left on disk for inspection.  Ignored (always deleted) if
            we had to fall back to a system temporary directory.
        debug
            Enable verbose logging & HTML preview generation.
        theme
            Name of the CSS theme to apply (``default`` / ``dark`` / …).
        """

        self.debug = debug
        self.theme = theme
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()

        self.paths = prepare_workspace(output_dir, keep_tmp=keep_tmp)

        # Inject tmp_dir into sub-components
        self.layout_engine = LayoutEngine(
            debug=debug, theme=theme, tmp_dir=self.paths["tmp_dir"], base_dir=self.base_dir
        )
        self.pptx_renderer = PPTXRenderer(theme=theme, debug=debug)
    
    async def generate(self, markdown_text: str, output_path: str = "output/demo.pptx"):
        """
        Generate a PowerPoint presentation from markdown text.
        
        Args:
            markdown_text: The markdown content to convert
            output_path: Path where the PPTX file should be saved
            
        Returns:
            str: Path to the generated PPTX file
        """
        
        # Ensure output_path has .pptx extension and is in output_dir if no path specified
        if not output_path.endswith('.pptx'):
            output_path = f"{output_path}.pptx"
        
        output_path = Path(output_path)
        if not output_path.is_absolute() and len(output_path.parts) == 1:
            # If it's just a filename, put it in the output directory
            output_path = Path(self.paths["output_dir"]) / output_path
        
        output_path = str(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        temp_dir = str(self.paths["tmp_dir"])
        if self.debug:
            logger.info(f"Using temp directory: {temp_dir}")
        
        # Step 1: Layout engine processes markdown and returns paginated blocks
        pages = await self.layout_engine.measure_and_paginate(
            markdown_text,
        )
        
        # Step 2: PPTX renderer converts pages to PowerPoint presentation
        self.pptx_renderer.render(pages, output_path)
        
        if self.debug:
            logger.info(f"Generated presentation saved to: {output_path}")
            logger.info(f"Total pages: {len(pages)}")
            logger.info(f"Theme: {self.theme}")
        
        return output_path


def main():
    """Command-line entry point for the slide generator."""
    import argparse
    import asyncio
    import sys
    
    def _build_parser() -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(prog="slidegen", description="Convert Markdown to a themed PPTX presentation.")
        p.add_argument("markdown", type=Path, help="Markdown file to convert")
        p.add_argument("--output", "-o", type=Path, default=Path("output/presentation.pptx"), help="Destination PPTX path")
        p.add_argument("--theme", "-t", default="default", help="CSS theme to use (default, dark, …)")
        p.add_argument("--debug", action="store_true", help="Enable verbose logging & HTML preview generation")
        p.add_argument("--asset-base", type=Path, help="Base directory for resolving relative asset paths (default: parent of markdown file)")
        p.add_argument("--keep-tmp", action="store_true", help="Keep .sg_tmp directory after run")
        return p

    async def _generate_async(args):
        """Async wrapper for slide generation."""
        md_path: Path = args.markdown
        if not md_path.exists():
            logger.error(f"Markdown file '{md_path}' not found")
            sys.exit(1)

        asset_base = args.asset_base if args.asset_base else md_path.parent
        markdown_text = md_path.read_text(encoding="utf-8")

        generator = SlideGenerator(
            output_dir=args.output.parent,
            theme=args.theme,
            debug=args.debug,
            keep_tmp=args.keep_tmp,
            base_dir=asset_base,
        )
        
        output_path = await generator.generate(markdown_text, args.output)
        logger.info("✅ Presentation written to %s", output_path)
    
    # Set up logging
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    
    # Parse arguments
    parser = _build_parser()
    args = parser.parse_args()
    
    # Run async generation
    asyncio.run(_generate_async(args))


if __name__ == "__main__":
    main() 