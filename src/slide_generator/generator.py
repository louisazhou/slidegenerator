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
    
    def __init__(self, debug: bool = False):
        """
        Initialize the slide generator.
        """
        self.debug = debug
        self.layout_engine = LayoutEngine(debug=debug)
        self.pptx_renderer = PPTXRenderer()
    
    def generate(self, markdown_text: str, output_path: str = "output/demo.pptx"):
        """
        Generate a PowerPoint presentation from markdown text.
        
        Args:
            markdown_text: The markdown content to convert
            output_path: Path where the PPTX file should be saved
            
        Returns:
            str: Path to the generated PPTX file
        """
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Step 1: Layout engine processes markdown and returns paginated blocks
        pages = self.layout_engine.measure_and_paginate(markdown_text)
        
        # Step 2: PPTX renderer converts pages to PowerPoint presentation
        self.pptx_renderer.render(pages, output_path)
        
        if self.debug:
            print(f"Generated presentation saved to: {output_path}")
            print(f"Total pages: {len(pages)}")
        
        return output_path


def main():
    """Command-line entry point for the slide generator."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m slide_generator.generator <markdown_file> [output_file]")
        sys.exit(1)
    
    markdown_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "output/demo.pptx"
    
    # Check if markdown file exists
    if not os.path.exists(markdown_file):
        print(f"Error: Markdown file '{markdown_file}' not found.")
        sys.exit(1)
    
    # Read markdown content
    with open(markdown_file, 'r', encoding='utf-8') as f:
        markdown_content = f.read()
    
    # Generate slides
    generator = SlideGenerator(debug=True)
    output_path = generator.generate(markdown_content, output_file)
    
    print(f"Slides generated successfully: {output_path}")


if __name__ == "__main__":
    main() 