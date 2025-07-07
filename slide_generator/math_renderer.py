#!/usr/bin/env python3
"""
Math renderer for converting LaTeX equations to SVG images.
Uses KaTeX for high-quality math rendering.
"""

import hashlib
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Dict, Tuple, Optional
import shutil
import json
from bs4 import BeautifulSoup
import re
import xml.etree.ElementTree as ET


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
        
        # Check if KaTeX CLI is available
        self._check_katex_availability()
        
        if self.debug:
            print(f"📐 Math renderer initialized with cache: {self.cache_dir}")
    
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
                    print(f"✅ KaTeX CLI available via '{cmd}': {result.stdout.strip()}")
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
                print(f"📋 Using cached math: {cache_key}")
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                return str(svg_path), metadata
            except (json.JSONDecodeError, FileNotFoundError):
                # Cache corrupted, re-render
                pass
        
        # Render using KaTeX CLI
        if self.debug:
            print(f"🔧 Rendering math: {latex[:50]}{'...' if len(latex) > 50 else ''}")
        
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
                print(f"✅ Math rendered: {cache_key} ({metadata['width']}x{metadata['height']}px)")
            
            return str(svg_path), metadata
            
        except subprocess.CalledProcessError as e:
            error_msg = f"KaTeX rendering failed for: {latex}\n"
            error_msg += f"Error: {e.stderr}"
            raise RuntimeError(error_msg)
    
    def render_to_png(self, latex: str, display_mode: bool = False) -> Tuple[str, Dict]:
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
                print(f"📋 Using cached math: {cache_key}")
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                return str(png_path), metadata
            except (json.JSONDecodeError, FileNotFoundError):
                # Cache corrupted, re-render
                pass
        
        # Render using KaTeX CLI
        if self.debug:
            print(f"🔧 Rendering math: {latex[:50]}{'...' if len(latex) > 50 else ''}")
        
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
            png_data, dimensions = self._convert_katex_html_to_png(html_content, display_mode)
            
            # Create metadata
            metadata = {
                'width': dimensions['width'],
                'height': dimensions['height'],
                'baseline': dimensions.get('baseline', 0)
            }
            
            # Save PNG to cache
            with open(png_path, 'wb') as f:
                f.write(png_data)
            
            # Save metadata to cache
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f)
            
            if self.debug:
                print(f"✅ Math rendered: {cache_key} ({metadata['width']}x{metadata['height']}px)")
            
            return str(png_path), metadata
            
        except subprocess.CalledProcessError as e:
            error_msg = f"KaTeX rendering failed for: {latex}\n"
            error_msg += f"Error: {e.stderr}"
            raise RuntimeError(error_msg)
    
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
    
    def _convert_katex_html_to_png(self, katex_html: str, display_mode: bool = False) -> Tuple[bytes, Dict]:
        """
        Convert KaTeX HTML output to PNG using Puppeteer with transparent background.
        """
        import asyncio
        import tempfile
        import os
        from pathlib import Path
        
        # Create a temporary HTML file with the KaTeX output
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            # Include KaTeX CSS for proper rendering with transparent background
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
        }}
        .katex {{ 
            font-size: 1.2em;
            background: transparent !important;
        }}
        .katex-display {{ 
            text-align: center; 
            margin: 0.5em 0; 
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
            # Use Puppeteer to render HTML to PNG directly
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # We're in an event loop, create a new thread to run the async function
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self._render_html_to_png(temp_html_path, display_mode))
                    png_data, dimensions = future.result()
            except RuntimeError:
                # No event loop running, safe to use asyncio.run
                png_data, dimensions = asyncio.run(self._render_html_to_png(temp_html_path, display_mode))
            
            return png_data, dimensions
        finally:
            # Clean up temporary file
            os.unlink(temp_html_path)
    
    async def _render_html_to_png(self, html_path: str, display_mode: bool = False) -> Tuple[bytes, Dict]:
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
            
            # Wait for KaTeX to render
            await page.waitForSelector('.katex')
            
            # Get the dimensions and baseline of the rendered math
            dimensions = await page.evaluate('''() => {
                const katexElement = document.querySelector('.katex');
                const rect = katexElement.getBoundingClientRect();
                
                // Calculate baseline offset for inline math
                let baseline = 0;
                if (katexElement.querySelector('.base')) {
                    const baseRect = katexElement.querySelector('.base').getBoundingClientRect();
                    baseline = rect.bottom - baseRect.bottom;
                }
                
                return {
                    width: Math.ceil(rect.width),
                    height: Math.ceil(rect.height),
                    baseline: Math.ceil(baseline)
                };
            }''')
            
            # Take a screenshot of just the math element with transparent background
            element = await page.querySelector('.katex')
            screenshot = await element.screenshot({
                'type': 'png',
                'omitBackground': True  # This ensures transparent background
            })
            
            await browser.close()
            
            return screenshot, dimensions
            
        except Exception as e:
            if self.debug:
                print(f"⚠️ Failed to render with Puppeteer: {e}")
            raise e
    
    def render_math_html(self, html_content: str, temp_dir: str, mode: str = "mixed") -> str:
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
                    png_path, metadata = self.render_to_png(latex, display_mode=is_display)
                    
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
                    print(f"📐 Rendered math ({mode}): {latex[:30]}...")
                    
            except Exception as e:
                if self.debug:
                    print(f"⚠️ Failed to render math: {latex[:50]}... Error: {e}")
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
    
    def copy_math_images_to_temp(self, html_content: str, temp_dir: str) -> str:
        """
        Copy math SVG files referenced in HTML to temp directory.
        
        Args:
            html_content: HTML content with math images
            temp_dir: Destination directory
            
        Returns:
            Updated HTML with corrected file paths
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all math images
        math_images = soup.find_all('img', class_=re.compile(r'math-image'))
        
        for img in math_images:
            src = img.get('src', '')
            if src.startswith('file://'):
                # Extract the original file path
                original_path = Path(src.replace('file://', ''))
                if original_path.exists():
                    # Copy to temp directory
                    temp_path = Path(temp_dir) / original_path.name
                    shutil.copy2(original_path, temp_path)
                    
                    # Update src to point to temp file
                    img['src'] = f'file://{temp_path.absolute()}'
        
        return str(soup)

    # ------------------------------------------------------------------
    # Convenience wrappers expected by LayoutEngine
    # ------------------------------------------------------------------
    def render_to_katex_html(self, html_content: str) -> str:
        """Return HTML where **all** math has been converted to KaTeX HTML markup.

        This is primarily for browser previews / debug output.  Internally a
        temporary directory is used for any intermediate assets that might be
        generated (though for pure HTML none are needed)."""
        import tempfile
        temp_dir = tempfile.mkdtemp()
        return self.render_math_html(html_content, temp_dir, mode="html")

    def render_to_images(self, html_content: str) -> str:
        """Return HTML where *display* maths are replaced by PNGs while inline maths
        remain embedded as KaTeX HTML.  This mixed representation matches the
        expectations of the measurement + PPTX rendering pipeline."""
        import tempfile
        temp_dir = tempfile.mkdtemp()
        return self.render_math_html(html_content, temp_dir, mode="mixed")


# Global math renderer instance
_math_renderer = None

def get_math_renderer(cache_dir: Optional[str] = None, debug: bool = False) -> MathRenderer:
    """Get the global math renderer instance."""
    global _math_renderer
    if _math_renderer is None:
        _math_renderer = MathRenderer(cache_dir=cache_dir, debug=debug)
    return _math_renderer 