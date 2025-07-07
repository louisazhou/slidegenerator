#!/usr/bin/env python3
"""
Math equation renderer using KaTeX and Puppeteer.
Converts LaTeX math expressions to SVG/PNG images for PowerPoint compatibility.
"""

import os
import json
import hashlib
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Tuple, Dict, Optional
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class MathRenderer:
    """
    Simple math renderer for LaTeX equations.
    Converts dollarmath plugin output to either KaTeX HTML or PNG images.
    """
    
    def __init__(self, cache_dir: str = "output/math_cache", debug: bool = False):
        """Initialize math renderer with caching."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.debug = debug
        
        if self.debug:
            logger.info(f"Math renderer initialized with cache: {cache_dir}")
    
    def render_to_katex_html(self, html_content: str) -> str:
        """
        Convert math elements to beautiful KaTeX HTML.
        
        Args:
            html_content: HTML with <span class="math inline"> and <div class="math block"> elements
            
        Returns:
            HTML with KaTeX-rendered math
        """
        if 'class="math' not in html_content:
            return html_content
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all math elements
        math_elements = soup.find_all(class_=re.compile(r'math'))
        
        for element in math_elements:
            latex = element.get_text().strip()
            if not latex:
                continue
                
            # Determine if it's display mode
            is_display = 'block' in element.get('class', [])
            
            # Render with KaTeX
            katex_html = self._render_katex(latex, display_mode=is_display)
            if katex_html:
                element.replace_with(BeautifulSoup(katex_html, 'html.parser'))
                
        return str(soup)
    
    def render_to_images(self, html_content: str) -> str:
        """
        Convert math elements to PNG images for PowerPoint.
        
        Args:
            html_content: HTML with <span class="math inline"> and <div class="math block"> elements
            
        Returns:
            HTML with <img> tags for math
        """
        if 'class="math' not in html_content:
            return html_content
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all math elements
        math_elements = soup.find_all(class_=re.compile(r'math'))
        
        for element in math_elements:
            latex = element.get_text().strip()
            if not latex:
                continue
                
            # Determine if it's display mode
            is_display = 'block' in element.get('class', [])
            
            if is_display:
                # Render display math as PNG
                png_path, metadata = self.render_to_png(latex, display_mode=True)
                if os.path.exists(png_path):
                    img_tag = soup.new_tag('img', 
                                         src=png_path, 
                                         alt=latex,
                                         **{'data-latex': latex,
                                            'data-width': str(metadata['width']),
                                            'data-height': str(metadata['height']),
                                            'class': 'math-image display'})
                    element.replace_with(img_tag)
            else:
                # Keep inline math as text for PowerPoint compatibility
                element.replace_with(f"${latex}$")
                
        return str(soup)
    
    def render_to_png(self, latex: str, display_mode: bool = False) -> Tuple[str, Dict]:
        """Render LaTeX to PNG image."""
        # Generate cache key
        cache_key = hashlib.md5(f"{latex}_{display_mode}".encode()).hexdigest()
        png_path = self.cache_dir / f"{cache_key}.png"
        metadata_path = self.cache_dir / f"{cache_key}.json"
        
        # Return cached version if available
        if png_path.exists() and metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            if self.debug:
                logger.info(f"Using cached math: {cache_key}")
            return str(png_path), metadata
        
        # Render new PNG
        try:
            # First render to KaTeX HTML
            katex_html = self._render_katex(latex, display_mode)
            
            # Then convert HTML to PNG using pyppeteer
            png_data, metadata = self._html_to_png(katex_html)
            
            # Save PNG and metadata
            with open(png_path, 'wb') as f:
                f.write(png_data)
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f)
                
            if self.debug:
                logger.info(f"Rendered math: {cache_key} ({metadata['width']}x{metadata['height']}px)")
                
            return str(png_path), metadata
            
        except Exception as e:
            if self.debug:
                logger.warning(f"Failed to render math to PNG: {e}")
            # Return empty path and default metadata
            return "", {"width": 100, "height": 30, "baseline": 24}
    
    def _render_katex(self, latex: str, display_mode: bool = False) -> str:
        """Render LaTeX to KaTeX HTML using Node.js."""
        try:
            import subprocess
            import json
            
            script = f"""
            const katex = require('katex');
            const latex = {json.dumps(latex)};
            const options = {{
                displayMode: {str(display_mode).lower()},
                throwOnError: false,
                output: 'html',
                trust: true
            }};
            
            try {{
                const result = katex.renderToString(latex, options);
                console.log(result);
            }} catch (error) {{
                console.error('KaTeX error:', error.message);
                process.exit(1);
            }}
            """
            
            result = subprocess.run(
                ['node', '-e', script],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                if self.debug:
                    logger.warning(f"KaTeX rendering failed: {result.stderr}")
                return f"${latex}$"  # Fallback
                
        except Exception as e:
            if self.debug:
                logger.warning(f"Failed to render KaTeX: {e}")
            return f"${latex}$"  # Fallback
    
    def _html_to_png(self, html_content: str) -> Tuple[bytes, Dict]:
        """Convert KaTeX HTML to PNG using pyppeteer."""
        try:
            import asyncio
            from pyppeteer import launch
            
            async def render():
                # Create HTML page
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                    html_template = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <style>
                            body {{ margin: 0; padding: 20px; background: transparent; }}
                            .katex {{ font-size: 1.2em; }}
                            .katex-display {{ text-align: center; margin: 0; }}
                        </style>
                    </head>
                    <body>
                        <div id="math">{html_content}</div>
                    </body>
                    </html>
                    """
                    f.write(html_template)
                    html_path = f.name
                
                try:
                    browser = await launch(headless=True, args=['--no-sandbox'])
                    page = await browser.newPage()
                    await page.goto(f'file://{html_path}')
                    await page.waitForSelector('.katex', {'timeout': 5000})
                    
                    # Get dimensions
                    dimensions = await page.evaluate('''() => {
                        const katex = document.querySelector('.katex');
                        const rect = katex.getBoundingClientRect();
                        return {
                            width: Math.ceil(rect.width),
                            height: Math.ceil(rect.height),
                            baseline: Math.ceil(rect.height * 0.8)
                        };
                    }''')
                    
                    # Take screenshot
                    element = await page.querySelector('.katex')
                    png_data = await element.screenshot()
                    
                    await browser.close()
                    return png_data, dimensions
                    
                finally:
                    try:
                        os.unlink(html_path)
                    except:
                        pass
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(render())
            
        except Exception as e:
            if self.debug:
                logger.warning(f"HTML to PNG conversion failed: {e}")
            # Return empty PNG data and default dimensions
            return b'', {"width": 100, "height": 30, "baseline": 24}

# Global instance
_math_renderer = None

def get_math_renderer(debug: bool = False) -> MathRenderer:
    """Get the global math renderer instance."""
    global _math_renderer
    if _math_renderer is None:
        _math_renderer = MathRenderer(debug=debug)
    return _math_renderer 