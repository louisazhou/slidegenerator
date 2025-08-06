#!/usr/bin/env python3
"""
Math renderer stub - KaTeX functionality disabled for company server compatibility.
Full math rendering capabilities are available in the feature/katex-math branch.
"""

import hashlib
from pathlib import Path
from typing import Dict, Tuple, Optional
import json
from bs4 import BeautifulSoup
import re

import logging
logger = logging.getLogger(__name__)

class MathRenderer:
    """
    No-op math renderer for company server compatibility.
    
    This stub version provides the same interface as the full math renderer
    but simply returns fallback text instead of rendered equations.
    
    For full KaTeX math rendering, use the feature/katex-math branch.
    """
    
    def __init__(self, cache_dir: str, debug: bool = False):
        """
        Initialize the no-op math renderer.
        
        Args:
            cache_dir: Directory that would cache rendered SVG files (unused in stub)
            debug: Enable debug output
        """
        self.debug = debug
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Keep the same interface
        self.png_text_color = "#000000"
        
        if self.debug:
            logger.info("Math renderer STUB active - equations will show as text (cache dir: %s)", self.cache_dir)
            logger.info("For full math rendering, use the feature/katex-math branch")
    
    def render_to_svg(self, latex: str, display_mode: bool = False) -> Tuple[str, Dict]:
        """
        Stub method - returns fallback text instead of SVG.
        
        Args:
            latex: LaTeX math expression
            display_mode: Whether to render in display mode
            
        Returns:
            Tuple of (placeholder_path, metadata)
        """
        if self.debug:
            logger.info("Math rendering disabled - showing text fallback for: %s", latex[:50])
        
        # Create a placeholder file with the LaTeX text
        cache_key = hashlib.md5(latex.encode('utf-8')).hexdigest()
        placeholder_path = self.cache_dir / f"{cache_key}.txt"
        
        # Write the LaTeX as plain text
        with open(placeholder_path, 'w', encoding='utf-8') as f:
            f.write(latex)
        
        # Return minimal metadata
        metadata = {
            'width': 100,
            'height': 20,
            'baseline': 10,
            'type': 'text_fallback'
        }
        
        return str(placeholder_path), metadata
    
    async def render_to_png(self, latex: str, display_mode: bool = False) -> Tuple[str, Dict]:
        """
        Stub method - returns fallback text instead of PNG.
        
        Args:
            latex: LaTeX math expression
            display_mode: Whether to render in display mode
            
        Returns:
            Tuple of (placeholder_path, metadata)
        """
        if self.debug:
            logger.info("Math rendering disabled - PNG fallback for: %s", latex[:50])
        
        # Just return the SVG path (text file) as a fallback
        return self.render_to_svg(latex, display_mode)
    
    def render_math_html(self, html_content: str, temp_dir: str, mode: str = "mixed") -> str:
        """
        Stub method - replaces math elements with text fallbacks.
        
        Args:
            html_content: HTML content with math elements
            temp_dir: Temporary directory (unused in stub)
            mode: Rendering mode (unused in stub)
            
        Returns:
            HTML with math elements replaced by text
        """
        if self.debug:
            logger.info("Processing HTML with math fallbacks (mode: %s)", mode)
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find math elements and replace with text
        math_elements = soup.find_all(class_=re.compile(r'\bmath\b'))
        
        for element in math_elements:
            # Extract LaTeX content from the element
            latex = element.get_text()
            
            # Create a simple text fallback
            fallback = soup.new_tag('span', class_='math-fallback')
            fallback.string = f"[Math: {latex}]"
            
            # Replace the math element
            element.replace_with(fallback)
            
            if self.debug:
                logger.info("Replaced math element with text: %s", latex[:30])
        
        return str(soup)


# Global math renderer instance
_math_renderer = None

def get_math_renderer(cache_dir: str = None, debug: bool = False) -> MathRenderer:
    """
    Get a global math renderer instance (stub version).
    
    Args:
        cache_dir: Directory to cache rendered files
        debug: Enable debug output
        
    Returns:
        MathRenderer stub instance
    """
    global _math_renderer
    
    if _math_renderer is None:
        if cache_dir is None:
            # Use a default cache directory
            cache_dir = Path.cwd() / ".math_cache"
        
        _math_renderer = MathRenderer(str(cache_dir), debug=debug)
    
    return _math_renderer