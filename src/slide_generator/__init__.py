"""
Slide Generator Package

A package for converting Markdown to PowerPoint slides with precise layout.
"""

from .generator import SlideGenerator
from .layout_engine import LayoutEngine
from .pptx_renderer import PPTXRenderer
from .models import Block

__all__ = ['SlideGenerator', 'LayoutEngine', 'PPTXRenderer', 'Block'] 