#!/usr/bin/env python3
"""
Math renderer - simplified to show raw LaTeX text without KaTeX dependencies.
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
    Simplified math renderer that shows raw LaTeX text instead of rendered equations.
    """
    
    def __init__(self, cache_dir: str, debug: bool = False):
        """
        Initialize the simplified math renderer.
        
        Args:
            cache_dir: Directory for compatibility (unused)
            debug: Enable debug output
        """
        self.debug = debug
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Keep the same interface
        self.png_text_color = "#000000"
        
        if self.debug:
            logger.info("Math renderer: showing raw LaTeX text instead of rendered equations")
    
    def render_to_svg(self, latex: str, display_mode: bool = False) -> Tuple[str, Dict]:
        """
        Returns the LaTeX text as-is.
        
        Args:
            latex: LaTeX math expression
            display_mode: Whether to render in display mode
            
        Returns:
            Tuple of (placeholder_path, metadata)
        """
        if self.debug:
            logger.info("Showing raw LaTeX: %s", latex[:50])
        
        # Create a placeholder file with the LaTeX text
        cache_key = hashlib.md5(latex.encode('utf-8')).hexdigest()
        placeholder_path = self.cache_dir / f"{cache_key}.txt"
        
        # Write the LaTeX as plain text
        with open(placeholder_path, 'w', encoding='utf-8') as f:
            f.write(latex)
        
        # Return minimal metadata
        metadata = {
            'width': len(latex) * 8,  # Rough estimate based on text length
            'height': 20,
            'baseline': 10,
            'type': 'text_fallback'
        }
        
        return str(placeholder_path), metadata
    
    async def render_to_png(self, latex: str, display_mode: bool = False) -> Tuple[str, Dict]:
        """
        Returns the LaTeX text as-is.
        
        Args:
            latex: LaTeX math expression
            display_mode: Whether to render in display mode
            
        Returns:
            Tuple of (placeholder_path, metadata)
        """
        return self.render_to_svg(latex, display_mode)
    
    def render_math_html(self, html_content: str, temp_dir: str, mode: str = "mixed") -> str:
        """
        Replaces math elements with their raw LaTeX content.
        
        Args:
            html_content: HTML content with math elements
            temp_dir: Temporary directory (unused)
            mode: Rendering mode (unused)
            
        Returns:
            HTML with math elements replaced by raw LaTeX text
        """
        if self.debug:
            logger.info("Converting math elements to raw LaTeX text")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find math elements and replace with their LaTeX content
        math_elements = soup.find_all(class_=re.compile(r'\bmath\b'))
        
        for element in math_elements:
            # Extract LaTeX content from the element
            latex = element.get_text().strip()
            
            # Create a simple text span with the raw LaTeX
            fallback = soup.new_tag('span', class_='math-text')
            fallback.string = latex
            
            # Replace the math element
            element.replace_with(fallback)
            
            if self.debug:
                logger.info("Replaced math with raw text: %s", latex[:30])
        
        return str(soup)


# Global math renderer instance
_math_renderer = None

def get_math_renderer(cache_dir: str = None, debug: bool = False) -> MathRenderer:
    """
    Get a global math renderer instance.
    
    Args:
        cache_dir: Directory to cache rendered files
        debug: Enable debug output
        
    Returns:
        MathRenderer instance
    """
    global _math_renderer
    
    if _math_renderer is None:
        if cache_dir is None:
            # Use a default cache directory
            cache_dir = Path.cwd() / ".math_cache"
        
        _math_renderer = MathRenderer(str(cache_dir), debug=debug)
    
    return _math_renderer