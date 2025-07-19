#!/usr/bin/env python3
"""
Math renderer for converting LaTeX equations to SVG images.
Uses KaTeX for high-quality math rendering.
"""

import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Tuple, Optional
import shutil
import json
from bs4 import BeautifulSoup
import re
import xml.etree.ElementTree as ET

import logging
logger = logging.getLogger(__name__)

class MathRenderer:
    """
    Renders LaTeX math expressions to SVG images using KaTeX.
    Provides caching to avoid re-rendering identical equations.
    """
    
    def __init__(self, cache_dir: Optional[str] = None, debug: bool = False):
        """
        Initialize the math renderer.
        
        Args:
            cache_dir: Directory to cache rendered SVG files (default: temp dir)
            debug: Enable debug output
        """
        self.debug = debug
        self.cache_dir = Path(cache_dir) if cache_dir else Path.cwd() / "output" / "math_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Text colour for rendering PNGs (hex string like '#ffffff') – can be
        # overridden by the layout engine depending on light/dark theme.
        self.png_text_color = "#000000"
        
        # Check if KaTeX CLI is available
        self._check_katex_availability()
        
        if self.debug:
            logger.info("Math renderer cache directory: %s", self.cache_dir)
    
    def _check_katex_availability(self):
        """Check if KaTeX CLI is available on the system."""
        # Try different possible locations for KaTeX
        katex_commands = [
            'katex',  # Global installation
            './node_modules/.bin/katex',  # Local installation
            'npx katex'  # Via npx
        ]
        
        for cmd in katex_commands:
            try:
                cmd_parts = cmd.split()
                result = subprocess.run(cmd_parts + ['--version'], 
                                      capture_output=True, text=True, check=True)
                self.katex_cmd = cmd_parts
                if self.debug:
                    logger.info("KaTeX CLI available via '%s': %s", cmd, result.stdout.strip())
                return
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        
        raise RuntimeError(
            "❌ KaTeX CLI not found. Please install it with:\n"
            "npm install katex\n"
            "or\n"
            "npm install -g katex"
        )
    
    def _get_cache_key(self, latex: str, display_mode: bool = False) -> str:
        """Generate a cache key for the LaTeX expression."""
        # Include display mode in the hash to differentiate inline vs block
        content = f"{latex}|display={display_mode}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _get_cached_svg_path(self, cache_key: str) -> Path:
        """Get the path to the cached SVG file."""
        return self.cache_dir / f"{cache_key}.svg"
    
    def _get_cached_png_path(self, cache_key: str) -> Path:
        """Get the path to the cached PNG file."""
        return self.cache_dir / f"{cache_key}.png"
    
    def _get_cached_metadata_path(self, cache_key: str) -> Path:
        """Get the path to the cached metadata file."""
        return self.cache_dir / f"{cache_key}.json"
    
    def render_to_svg(self, latex: str, display_mode: bool = False) -> Tuple[str, Dict]:
        """
        Render LaTeX to SVG and return the file path and metadata.
        
        Args:
            latex: LaTeX expression to render
            display_mode: True for block math ($$), False for inline math ($)
            
        Returns:
            Tuple of (svg_file_path, metadata_dict)
            metadata contains: width, height, baseline (all in pixels)
        """
        # Clean up the LaTeX expression
        latex = latex.strip()
        if not latex:
            raise ValueError("Empty LaTeX expression")
        
        # Generate cache key
        cache_key = self._get_cache_key(latex, display_mode)
        svg_path = self._get_cached_svg_path(cache_key)
        metadata_path = self._get_cached_metadata_path(cache_key)
        
        # Check if already cached
        if svg_path.exists() and metadata_path.exists():
            if self.debug:
                logger.info("Using cached math: %s", cache_key)
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                return str(svg_path), metadata
            except (json.JSONDecodeError, FileNotFoundError):
                # Cache corrupted, re-render
                pass
        
        # Render using KaTeX CLI
        if self.debug:
            logger.info("Rendering math: %s", latex[:50])
        
        try:
            # Prepare KaTeX command using the detected command
            katex_cmd = self.katex_cmd + [
                '--no-throw-on-error',  # Don't throw on errors, output error message instead
            ]
            
            if display_mode:
                katex_cmd.append('--display-mode')
            
            if self.debug:
                logger.debug("KaTeX command: %s", ' '.join(katex_cmd))
                logger.debug("LaTeX input: %s", repr(latex))
                logger.debug("LaTeX content preview: %s...", latex[:100])
            
            # Run KaTeX with LaTeX as stdin
            result = subprocess.run(katex_cmd, input=latex, capture_output=True, text=True, check=True)
            html_content = result.stdout
            
            if self.debug:
                if result.stderr:
                    logger.debug("KaTeX stderr: %s", result.stderr)
                logger.debug("KaTeX output length: %s", len(html_content))
            
            if not html_content.strip():
                raise RuntimeError(f"KaTeX produced empty output for: {latex}")
            
            # Convert HTML to SVG using a headless browser approach
            svg_content = self._convert_katex_html_to_svg(html_content, display_mode)
            
            # Parse SVG to extract dimensions
            metadata = self._extract_svg_metadata(svg_content)
            
            # Save to cache
            with open(svg_path, 'w', encoding='utf-8') as f:
                f.write(svg_content)
            
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f)
            
            if self.debug:
                logger.info("Math rendered: %s (%sx%s px)", cache_key, metadata['width'], metadata['height'])
            
            return str(svg_path), metadata
            
        except subprocess.CalledProcessError as e:
            if self.debug:
                logger.error("KaTeX failed with exit code %s", e.returncode)
                logger.error("KaTeX stdout: %s", e.stdout)
                logger.error("KaTeX stderr: %s", e.stderr)
                logger.error("Failed LaTeX: %s", repr(latex))
            raise RuntimeError(f"KaTeX failed: {e.stderr or e.stdout}")
        except Exception as e:
            if self.debug:
                logger.error("Unexpected error running KaTeX: %s", e)
                logger.error("Failed LaTeX: %s", repr(latex))
            raise
    
    async def render_to_png(self, latex: str, display_mode: bool = False) -> Tuple[str, Dict]:
        """
        Render LaTeX math to PNG format with transparent background.
        
        Args:
            latex: LaTeX math expression
            display_mode: Whether to render in display mode (block) or inline
            
        Returns:
            Tuple of (png_file_path, metadata_dict)
        """
        # Clean up the LaTeX expression
        latex = latex.strip()
        if not latex:
            raise ValueError("Empty LaTeX expression")
        
        # Generate cache key
        cache_key = self._get_cache_key(latex, display_mode)
        png_path = self._get_cached_png_path(cache_key)
        metadata_path = self._get_cached_metadata_path(cache_key)
        
        # Check if already cached
        if png_path.exists() and metadata_path.exists():
            if self.debug:
                logger.info("Using cached math: %s", cache_key)
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                return str(png_path), metadata
            except (json.JSONDecodeError, FileNotFoundError):
                # Cache corrupted, re-render
                pass
        
        # Render using KaTeX CLI
        if self.debug:
            logger.info("Rendering math: %s", latex[:50])
        
        try:
            # Prepare KaTeX command using the detected command
            katex_cmd = self.katex_cmd + [
                '--no-throw-on-error',  # Don't throw on errors, output error message instead
            ]
            
            if display_mode:
                katex_cmd.append('--display-mode')
            
            # Run KaTeX with LaTeX as stdin
            result = subprocess.run(katex_cmd, input=latex, capture_output=True, text=True, check=True)
            html_content = result.stdout
            
            if not html_content.strip():
                raise RuntimeError(f"KaTeX produced empty output for: {latex}")
            
            # Convert HTML to PNG using Puppeteer
            png_data, dimensions = await self._convert_katex_html_to_png(html_content, display_mode)
            
            if self.debug:
                logger.debug("Got PNG data: %s bytes, dimensions: %s", len(png_data), dimensions)
            
            # Create metadata
            metadata = {
                'width': dimensions['width'],
                'height': dimensions['height'],
                'baseline': dimensions.get('baseline', 0)
            }
            
            # Save PNG to cache
            if self.debug:
                logger.debug("Saving PNG to: %s", png_path)
            with open(png_path, 'wb') as f:
                f.write(png_data)
            
            if self.debug:
                logger.debug("PNG file size after save: %s bytes", png_path.stat().st_size)
            
            # Save metadata to cache
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f)
            
            if self.debug:
                logger.info("Math rendered: %s (%sx%s px)", cache_key, metadata['width'], metadata['height'])
            
            return str(png_path), metadata
            
        except subprocess.CalledProcessError as e:
            if self.debug:
                logger.error("KaTeX subprocess failed: %s", e)
            error_msg = f"KaTeX rendering failed for: {latex}\n"
            error_msg += f"Error: {e.stderr}"
            raise RuntimeError(error_msg)
        except Exception as e:
            if self.debug:
                logger.error("PNG rendering failed: %s", e)
                import traceback
                traceback.print_exc()
            raise RuntimeError(f"PNG rendering failed: {e}")
    
    def _extract_svg_metadata(self, svg_content: str) -> Dict:
        """
        Extract width, height, and baseline from SVG content.
        
        Args:
            svg_content: SVG XML content
            
        Returns:
            Dictionary with width, height, baseline in pixels
        """
        try:
            # Parse SVG
            root = ET.fromstring(svg_content)
            
            # Extract dimensions from SVG root element
            width_str = root.get('width', '0')
            height_str = root.get('height', '0')
            
            # Parse dimensions (KaTeX outputs in 'ex' units typically)
            width_px = self._parse_dimension(width_str)
            height_px = self._parse_dimension(height_str)
            
            # For baseline, we'll use a heuristic based on the SVG viewBox
            # KaTeX typically centers math vertically, so baseline is roughly at height/2
            viewbox = root.get('viewBox', '0 0 0 0')
            viewbox_parts = viewbox.split()
            if len(viewbox_parts) >= 4:
                viewbox_height = float(viewbox_parts[3])
                # Baseline is typically at about 20% from the bottom for most math
                baseline_px = height_px * 0.2
            else:
                baseline_px = height_px * 0.2
            
            return {
                'width': width_px,
                'height': height_px,
                'baseline': baseline_px
            }
            
        except ET.ParseError as e:
            # Fallback to regex parsing if XML parsing fails
            width_match = re.search(r'width="([^"]+)"', svg_content)
            height_match = re.search(r'height="([^"]+)"', svg_content)
            
            width_px = self._parse_dimension(width_match.group(1)) if width_match else 20
            height_px = self._parse_dimension(height_match.group(1)) if height_match else 20
            
            return {
                'width': width_px,
                'height': height_px,
                'baseline': height_px * 0.2
            }
    
    def _parse_dimension(self, dim_str: str) -> float:
        """
        Parse a dimension string (e.g., '1.2ex', '24px') to pixels.
        
        Args:
            dim_str: Dimension string
            
        Returns:
            Dimension in pixels
        """
        # Remove whitespace
        dim_str = dim_str.strip()
        
        # Parse number and unit
        match = re.match(r'([0-9.]+)([a-z]*)', dim_str)
        if not match:
            return 20.0  # Fallback
        
        value = float(match.group(1))
        unit = match.group(2).lower()
        
        # Convert to pixels
        if unit == 'px' or unit == '':
            return value
        elif unit == 'ex':
            # 1ex ≈ 8px for typical math fonts
            return value * 8
        elif unit == 'em':
            # 1em ≈ 16px for typical fonts
            return value * 16
        elif unit == 'pt':
            # 1pt = 4/3 px
            return value * 4/3
        else:
            # Unknown unit, assume pixels
            return value
    
    async def _convert_katex_html_to_png(self, katex_html: str, display_mode: bool = False) -> Tuple[bytes, Dict]:
        """
        Convert KaTeX HTML output to PNG using Puppeteer with transparent background.
        """
        import tempfile
        import os
        
        # Create a temporary HTML file with the KaTeX output
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            # Include KaTeX CSS for proper rendering with transparent background
            text_color = self.png_text_color

            html_template = f'''<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css">
    <style>
        body {{ 
            margin: 0; 
            padding: 8px; 
            font-family: serif; 
            background: transparent !important;
            color: {text_color};
        }}
        .katex {{ 
            font-size: 1.2em;
            background: transparent !important;
            color: {text_color};
        }}
        .katex-display {{ 
            text-align: center; 
            margin: 0.5em 0; 
            color: {text_color};
        }}
    </style>
</head>
<body>
    <div class="{'katex-display' if display_mode else ''}">{katex_html}</div>
</body>
</html>'''
            f.write(html_template)
            temp_html_path = f.name
        
        try:
            # Render the HTML file to PNG
            png_data, dimensions = await self._render_html_to_png(temp_html_path)
        finally:
            # Clean up the temporary file
            os.unlink(temp_html_path)
            
        return png_data, dimensions
    
    async def _render_html_to_png(self, html_path: str) -> Tuple[bytes, Dict]:
        """Use Puppeteer to render HTML directly to PNG with transparent background."""
        try:
            from pyppeteer import launch

            browser = await launch({'headless': True})
            page = await browser.newPage()
            
            # Set transparent background
            await page.evaluateOnNewDocument('''() => {
                const style = document.createElement('style');
                style.textContent = `
                    body { 
                        background: transparent !important; 
                        margin: 0; 
                        padding: 8px; 
                    }
                    .katex { 
                        background: transparent !important; 
                    }
                `;
                document.head.appendChild(style);
            }''')
            
            # Load the HTML file
            await page.goto(f'file://{html_path}')
            
            # Wait for KaTeX to render with a reasonable timeout
            try:
                await page.waitForSelector('.katex', {'timeout': 5000})  # 5 second timeout
            except Exception as e:
                if self.debug:
                    logger.warning("KaTeX selector timeout or not found: %s", e)
                # Try to get page content for debugging
                try:
                    content = await page.content()
                    if self.debug:
                        logger.debug("Page content length: %s", len(content))
                        if 'katex' not in content.lower():
                            logger.warning("No KaTeX content found in page")
                        if 'error' in content.lower():
                            logger.warning("Error found in page content: %s...", content[:500])
                except:
                    pass
                await browser.close()
                raise RuntimeError(f"KaTeX rendering failed: {e}")
            
            # Embed colour via injected style so KaTeX SVG/text picks it up
            css_colour = self.png_text_color
            style_rules = (
                f"body, .katex, .katex-display {{ color:{css_colour} !important; }}"
                f" .katex svg * {{ fill:{css_colour} !important; stroke:{css_colour} !important; }}"
            )
            await page.addStyleTag({'content': style_rules})

            # Compute dimensions & baseline
            dims_js = """() => {
                const el = document.querySelector('.katex-display') || document.querySelector('.katex');
                const rect = el.getBoundingClientRect();
                let baseline = 0;
                const base = el.querySelector('.base');
                if (base) {
                    const br = base.getBoundingClientRect();
                    baseline = rect.bottom - br.bottom;
                }
                return { width: Math.ceil(rect.width), height: Math.ceil(rect.height), baseline: Math.ceil(baseline) };
            }"""
            dimensions = await page.evaluate(dims_js)

            # grab wrapper first, else inner
            try:
                let_el = await page.querySelector('.katex-display')
                if let_el is None:
                    let_el = await page.querySelector('.katex')
                if let_el is None:
                    raise RuntimeError('KaTeX element not found for screenshot')

                screenshot = await let_el.screenshot({
                  'type': 'png',
                  'omitBackground': True  # This ensures transparent background
              })
            except Exception as e:
                if self.debug:
                    logger.error("math PNG render failed: %s", e)
                raise
            
            await browser.close()
            
            return screenshot, dimensions
            
        except Exception as e:
            if self.debug:
                logger.warning("Failed to render with Puppeteer: %s", e)
            raise e
    
    async def render_math_html(self, html_content: str, temp_dir: str, mode: str = "mixed") -> str:
        """
        Process HTML content and handle math elements.
        
        Args:
            html_content: HTML content containing math elements
            temp_dir: Temporary directory for copying files
            mode: "html" for HTML math, "images" for PNG images, "mixed" for HTML inline + PNG display
            
        Returns:
            HTML content with math processed according to mode
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all math elements (inline or display). The dollarmath plugin can emit either
        #   <span class="math math-inline"> ...
        #   <span class="math math-display"> ...
        #   <div  class="math math-display"> ...
        # or legacy variants such as "math inline" / "math block".
        # We therefore look for any element whose *class list* contains the token "math".
        math_elements = [
            el for el in soup.find_all(['span', 'div'])
            if any('math' in cls for cls in (el.get('class') or []))
        ]
        
        for element in math_elements:
            latex = element.get_text().strip()
            if not latex:
                continue
            
            # Determine if it's display mode (block math)
            classes = element.get('class', [])
            # The dollarmath plugin uses "math-display" token for block equations. Legacy
            # versions used "block". Support both as well as a plain "display" token.
            is_display = (
                'block' in classes or
                'display' in classes or
                'math-display' in classes or
                'math-block' in classes or
                'math_block' in classes
            )
            
            try:
                if mode == "html" or (mode == "mixed" and not is_display):
                    if mode == "html":
                        # Render as HTML math using KaTeX for nice preview
                        katex_html = self._render_latex_to_html(latex, display_mode=is_display)
                        wrapper = soup.new_tag('span' if not is_display else 'div')
                        wrapper['class'] = f'math-html {"display" if is_display else "inline"}'
                        wrapper['data-latex'] = latex
                        wrapper.append(BeautifulSoup(katex_html, 'html.parser'))
                        element.replace_with(wrapper)
                    else:
                        # Keep original inline math in plain LaTeX form with delimiters for PPTX
                        plain_span = soup.new_tag('span')
                        plain_span.string = f"${latex}$"
                        element.replace_with(plain_span)
                else:
                    # Render to PNG (for display math or when mode="images")
                    png_path, metadata = await self.render_to_png(latex, display_mode=is_display)
                    
                    # Copy PNG to temp directory for browser access
                    png_filename = Path(png_path).name
                    temp_png_path = Path(temp_dir) / png_filename
                    
                    # Only copy if source and destination are different
                    if str(png_path) != str(temp_png_path):
                        shutil.copy2(png_path, temp_png_path)
                    else:
                        temp_png_path = Path(png_path)  # Use the original path
                    
                    # Create img tag
                    img_tag = soup.new_tag('img')
                    img_tag['src'] = f'file://{temp_png_path.absolute()}'
                    img_tag['alt'] = latex  # For accessibility
                    img_tag['class'] = f'math-image {"display" if is_display else "inline"}'
                    img_tag['data-latex'] = latex
                    img_tag['data-math-width'] = str(metadata['width'])
                    img_tag['data-math-height'] = str(metadata['height'])
                    img_tag['data-math-baseline'] = str(metadata['baseline'])
                    
                    # Set display style for block math
                    if is_display:
                        img_tag['style'] = 'display: block; margin: 0.5em auto;'
                    else:
                        img_tag['style'] = f'vertical-align: -{metadata["baseline"]}px;'
                    
                    # Replace the math element with the img tag
                    element.replace_with(img_tag)
                
                if self.debug:
                    logger.info("Rendered math (%s): %s...", mode, latex[:30])
                    
            except Exception as e:
                if self.debug:
                    logger.warning("Failed to render math: %s... Error: %s", latex[:50], e)
                # Leave the original element if rendering fails
                continue
        
        return str(soup)
    
    def _render_latex_to_html(self, latex: str, display_mode: bool = False) -> str:
        """
        Render LaTeX to HTML using KaTeX.
        
        Args:
            latex: LaTeX math expression
            display_mode: Whether to render in display mode
            
        Returns:
            HTML string with rendered math
        """
        try:
            # Prepare KaTeX command
            katex_cmd = self.katex_cmd + [
                '--no-throw-on-error',  # Don't throw on errors
            ]
            
            if display_mode:
                katex_cmd.append('--display-mode')
            
            # Run KaTeX with LaTeX as stdin
            result = subprocess.run(katex_cmd, input=latex, capture_output=True, text=True, check=True)
            html_content = result.stdout.strip()
            
            if not html_content:
                raise RuntimeError(f"KaTeX produced empty output for: {latex}")
            
            return html_content
            
        except subprocess.CalledProcessError as e:
            error_msg = f"KaTeX HTML rendering failed for: {latex}\n"
            error_msg += f"Error: {e.stderr}"
            raise RuntimeError(error_msg)


# Global math renderer instance
_math_renderer = None

def get_math_renderer(cache_dir: Optional[str] = None, debug: bool = False) -> MathRenderer:
    """Get the global math renderer instance."""
    global _math_renderer
    if _math_renderer is None:
        _math_renderer = MathRenderer(cache_dir=cache_dir, debug=debug)
    return _math_renderer 