#!/usr/bin/env python3
"""
Main slide generator module that ties together layout engine and PowerPoint renderer.
"""

from .layout_engine import LayoutEngine
from .pptx_renderer import PPTXRenderer

class SlideGenerator:
    """
    Main class for generating PowerPoint slides from Markdown content.
    """
    
    def __init__(self, debug_dir=None):
        """
        Initialize the slide generator.
        
        Args:
            debug_dir: Directory for debug output (uses temp dir if None)
        """
        self.layout_engine = LayoutEngine(debug_dir)
        self.renderer = PPTXRenderer()
    
    def generate(self, markdown_text, output_path="output.pptx", max_height_px=460):
        """
        Generate PowerPoint slides from markdown text.
        
        Args:
            markdown_text: Markdown content to convert
            output_path: Path to save the PowerPoint file
            max_height_px: Maximum height per slide in pixels
            
        Returns:
            Path to the saved PowerPoint file
        """
        # Get paginated layout
        paginated_blocks = self.layout_engine.get_paginated_layout(
            markdown_text, 
            max_px=max_height_px
        )
        
        # Create PowerPoint presentation
        pptx_path = self.renderer.create_presentation(paginated_blocks, output_path)
        print(f"PowerPoint file created: {pptx_path}")
        
        return pptx_path 