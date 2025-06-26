#!/usr/bin/env python3
"""
Main slide generator module that ties together layout engine and PowerPoint renderer.
"""

import os
from .layout_engine import LayoutEngine
from .pptx_renderer import PPTXRenderer


class SlideGenerator:
    """
    Main class for generating PowerPoint slides from markdown.
    """
    
    def __init__(self, debug: bool = False, theme: str = "default"):
        """
        Initialize the slide generator.
        
        Args:
            debug: Enable debug output
            theme: Theme name for styling (default, dark, etc.)
        """
        self.debug = debug
        self.theme = theme
        self.layout_engine = LayoutEngine(debug=debug, theme=theme)
        self.pptx_renderer = PPTXRenderer(theme=theme, debug=debug)
    
    def generate(self, markdown_text: str, output_path: str = "output/demo.pptx"):
        """
        Generate a PowerPoint presentation from markdown text.
        
        Args:
            markdown_text: The markdown content to convert
            output_path: Path where the PPTX file should be saved
            
        Returns:
            str: Path to the generated PPTX file
        """
        import tempfile
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Create a temp directory for this generation session
        temp_dir = tempfile.mkdtemp()
        if self.debug:
            print(f"🗂️ Using temp directory: {temp_dir}")
        
        # Step 1: Layout engine processes markdown and returns paginated blocks
        pages = self.layout_engine.measure_and_paginate(markdown_text, temp_dir=temp_dir)
        
        # Step 2: PPTX renderer converts pages to PowerPoint presentation
        self.pptx_renderer.render(pages, output_path)
        
        if self.debug:
            print(f"Generated presentation saved to: {output_path}")
            print(f"Total pages: {len(pages)}")
            print(f"Theme: {self.theme}")
        
        return output_path


def main():
    """Command-line entry point for the slide generator."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m slide_generator.generator <markdown_file> [output_file] [theme]")
        sys.exit(1)
    
    markdown_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "output/demo.pptx"
    theme = sys.argv[3] if len(sys.argv) > 3 else "default"
    
    # Check if markdown file exists
    if not os.path.exists(markdown_file):
        print(f"Error: Markdown file '{markdown_file}' not found.")
        sys.exit(1)
    
    # Read markdown content
    with open(markdown_file, 'r', encoding='utf-8') as f:
        markdown_content = f.read()
    
    # Generate slides
    generator = SlideGenerator(debug=True, theme=theme)
    output_path = generator.generate(markdown_content, output_file)
    
    print(f"Slides generated successfully: {output_path}")


if __name__ == "__main__":
    main() 