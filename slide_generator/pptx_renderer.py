#!/usr/bin/env python3
"""
PowerPoint renderer for converting layout blocks to PowerPoint slides.
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from .models import Block
from .theme_loader import get_css
from typing import List, Dict, Optional
import re
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls, qn

# Helper function to convert pixels to inches
def px(pixels):
    return Inches(pixels / 96)

class PPTXRenderer:
    """
    Renderer for converting layout blocks to PowerPoint slides.
    """
    
    def __init__(self, theme: str = "default", debug: bool = False):
        """Initialize the PowerPoint renderer with theme support."""
        self.theme = theme
        self.debug = debug
        self.theme_config = self._parse_theme_config()
    
    def _parse_theme_config(self) -> Dict:
        """Parse CSS theme to extract font sizes and styling configuration."""
        css_content = get_css(self.theme)
        
        # NO FALLBACKS - Extract font sizes from CSS or fail
        config = {
            'font_sizes': {},
            'line_height': None,
            'colors': {},
            'slide_dimensions': {},
            'css_content': css_content
        }
        
        # Parse font sizes from CSS - REQUIRED, no defaults
        font_size_patterns = {
            'h1': r'h1\s*{[^}]*font-size:\s*(\d+)px',
            'h2': r'h2\s*{[^}]*font-size:\s*(\d+)px',
            'h3': r'h3\s*{[^}]*font-size:\s*(\d+)px',
            'p': r'p\s*{[^}]*font-size:\s*(\d+)px',
            'ul, ol': r'ul,\s*ol\s*{[^}]*font-size:\s*(\d+)px',
            'pre': r'pre\s*{[^}]*font-size:\s*(\d+)px'  # Look for separate pre rule
        }
        
        # Parse margin-bottoms in px (defaults to 0)
        margin_patterns = {
            'h1': r'h1\s*{[^}]*margin-bottom:\s*(\d+)px',
            'h2': r'h2\s*{[^}]*margin-bottom:\s*(\d+)px',
            'h3': r'h3\s*{[^}]*margin-bottom:\s*(\d+)px',
            'p': r'p\s*{[^}]*margin-bottom:\s*(\d+)px',
            'li': r'li\s*{[^}]*margin-bottom:\s*(\d+)px'
        }
        
        for element, pattern in font_size_patterns.items():
            match = re.search(pattern, css_content, re.IGNORECASE | re.DOTALL)
            if match:
                px_size = int(match.group(1))
                pt_size = max(10, int(px_size * 0.75))  # Convert px to pt, minimum 10pt
                
                if element == 'ul, ol':
                    config['font_sizes']['li'] = pt_size
                elif element == 'pre':
                    config['font_sizes']['code'] = pt_size
                else:
                    config['font_sizes'][element] = pt_size
            else:
                raise ValueError(f"❌ CSS theme '{self.theme}' missing required font-size for {element}. "
                               f"Add 'font-size: XXpx' to {element} rule in themes/{self.theme}.css")
        
        # Parse line height - REQUIRED
        line_height_match = re.search(r'line-height:\s*([\d.]+)', css_content)
        if line_height_match:
            config['line_height'] = float(line_height_match.group(1))
        else:
            raise ValueError(f"❌ CSS theme '{self.theme}' missing required line-height. "
                           f"Add 'line-height: X.X' to CSS rules in themes/{self.theme}.css")
        
        # Parse slide dimensions from CSS variables - REQUIRED
        width_match = re.search(r'--slide-width:\s*(\d+)px', css_content)
        height_match = re.search(r'--slide-height:\s*(\d+)px', css_content)
        padding_match = re.search(r'--slide-padding:\s*(\d+)px', css_content)
        font_family_match = re.search(r'--slide-font-family:\s*[\'"]([^\'\"]+)[\'"]', css_content)
        
        if not width_match or not height_match:
            raise ValueError(f"❌ CSS theme '{self.theme}' missing required slide dimensions. "
                           f"Add '--slide-width: XXXpx' and '--slide-height: XXXpx' to :root in themes/{self.theme}.css")
        
        if not padding_match:
            raise ValueError(f"❌ CSS theme '{self.theme}' missing required --slide-padding variable. "
                           f"Add '--slide-padding: XXpx' to :root in themes/{self.theme}.css")
                           
        if not font_family_match:
            raise ValueError(f"❌ CSS theme '{self.theme}' missing required --slide-font-family variable. "
                           f"Add '--slide-font-family: \"FontName\"' to :root in themes/{self.theme}.css")
        
        config['slide_dimensions'] = {
            'width_px': int(width_match.group(1)),
            'height_px': int(height_match.group(1)),
            'padding_px': int(padding_match.group(1)),
        }
        
        config['font_family'] = font_family_match.group(1)
        
        # Parse table border width (required) and optional font delta (deprecated)
        border_width_match = re.search(r'--table-border-width:\s*([\d.]+)pt', css_content)
        font_delta_match = re.search(r'--table-font-delta:\s*(-?\d+)pt', css_content)

        if not border_width_match:
            raise ValueError(f"❌ CSS theme '{self.theme}' missing required --table-border-width variable. "
                           f"Add '--table-border-width: X.Xpt' to :root in themes/{self.theme}.css")

        font_delta_val = int(font_delta_match.group(1)) if font_delta_match else 0

        config['table_deltas'] = {
            'font_delta': font_delta_val,
            'border_width_pt': float(border_width_match.group(1))
        }
            
        # Calculate inches from pixels (96 DPI standard)
        config['slide_dimensions']['width_inches'] = config['slide_dimensions']['width_px'] / 96
        config['slide_dimensions']['height_inches'] = config['slide_dimensions']['height_px'] / 96
        
        # Extract colors from CSS theme - REQUIRED
        config['colors'] = self._extract_colors_from_css(css_content)
        
        # Margins
        config['margins'] = {}
        for element, pattern in margin_patterns.items():
            match = re.search(pattern, css_content, re.IGNORECASE | re.DOTALL)
            px_val = int(match.group(1)) if match else 0
            config['margins'][element] = px_val
        
        return config
    
    def _extract_colors_from_css(self, css_content: str) -> Dict:
        """Extract all colors from CSS theme file."""
        
        colors = {}  # NO FALLBACKS - extract from CSS or fail
        
        # Required color types that MUST be defined in CSS
        required_colors = ['text', 'background', 'table_border', 'table_text', 'code_text', 'heading_text']
        
        # Extract colors from CSS rules
        color_patterns = {
            'text': [
                r'body\s*{[^}]*color:\s*([^;}\s]+)',
                r'p\s*{[^}]*color:\s*([^;}\s]+)'
            ],
            'background': [
                r'body\s*{[^}]*background-color:\s*([^;}\s]+)',
                r'\.slide\s*{[^}]*background-color:\s*([^;}\s]+)'
            ],
            'table_border': [
                r'th,?\s*td\s*{[^}]*border:[^}]*solid\s+([^;}\s]+)',
                r'table\s*{[^}]*border-color:\s*([^;}\s]+)'
            ],
            'table_text': [
                r'th,?\s*td\s*{[^}]*color:\s*([^;}\s]+)',
                r'th\s*{[^}]*color:\s*([^;}\s]+)'
            ],
            'code_text': [
                r'pre\s*{[^}]*color:\s*([^;}\s]+)',  # Look for separate pre rule
                r'code\s*{[^}]*color:\s*([^;}\s]+)',
                r'pre,?\s*code\s*{[^}]*color:\s*([^;}\s]+)'  # Keep for backwards compatibility
            ],
            'heading_text': [
                r'h[1-6]\s*{[^}]*color:\s*([^;}\s]+)',
                r'h1\s*{[^}]*color:\s*([^;}\s]+)'
            ]
        }
        
        for color_type, patterns in color_patterns.items():
            color_found = False
            for pattern in patterns:
                match = re.search(pattern, css_content, re.IGNORECASE | re.DOTALL)
                if match:
                    color_value = match.group(1).strip()
                    # Normalize color format
                    if color_value.startswith('#'):
                        colors[color_type] = color_value
                        color_found = True
                        break
                    elif color_value in ['transparent', 'inherit']:
                        continue  # Skip these values
                    else:
                        # Try to convert named colors or other formats
                        colors[color_type] = color_value
                        color_found = True
                        break
            
            # Require all colors to be explicitly defined
            if not color_found and color_type in required_colors:
                raise ValueError(f"❌ CSS theme '{self.theme}' missing required color for {color_type}. "
                               f"Add appropriate color definition to themes/{self.theme}.css")
        
        return colors
    
    def _match_table_to_html_dimensions(self, table, block: Block, rows: int, cols: int):
        """Match PowerPoint table dimensions exactly to HTML measurements."""
        
        # Extract CSS styling values for precise matching
        css_content = self.theme_config.get('css_content', '')
        
        # Parse CSS cell padding (default 8px from our CSS)
        padding_match = re.search(r'th,?\s*td\s*{[^}]*padding:\s*(\d+)px', css_content)
        css_cell_padding = int(padding_match.group(1)) if padding_match else 8
        
        # Parse CSS border width (default 1px) - handle "1px solid #000" format
        border_match = re.search(r'th,?\s*td\s*{[^}]*border:\s*(\d+)px\s+solid', css_content)
        css_border_width = int(border_match.group(1)) if border_match else 1
        
        # Calculate precise row height based on HTML measurement
        html_table_height = block.height
        
        # Account for borders: total border height = (rows + 1) * border_width
        total_border_height = (rows + 1) * css_border_width
        content_height = html_table_height - total_border_height
        
        # Distribute content height evenly across rows
        target_row_height = px(content_height / rows)
        
        # Debug output for precision matching
        if hasattr(self, 'debug') and self.debug:
            print(f"🎯 Precision table matching:")
            print(f"  HTML table height: {html_table_height}px")
            print(f"  CSS padding: {css_cell_padding}px, border: {css_border_width}px")
            print(f"  Calculated row height: {content_height / rows:.1f}px")
            print(f"  PowerPoint row height: {target_row_height}")
            if hasattr(block, 'table_column_widths'):
                print(f"  Column widths: {block.table_column_widths}")
        
        # Set row heights precisely
        for row in table.rows:
            try:
                row.height = target_row_height
            except:
                pass  # Fallback for older python-pptx versions
        
        # Set cell padding to match CSS exactly
        for row in table.rows:
            for cell in row.cells:
                try:
                    # Convert CSS padding to PowerPoint margin
                    ppt_margin = px(css_cell_padding)
                    cell.text_frame.margin_left = ppt_margin
                    cell.text_frame.margin_right = ppt_margin
                    cell.text_frame.margin_top = ppt_margin
                    cell.text_frame.margin_bottom = ppt_margin
                except:
                    pass  # Fallback if margin setting fails
    
    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            return (0, 0, 0)  # Default to black
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def render(self, pages: List[List[Block]], output_path: str):
        """
        Render pages of Block objects to a PowerPoint presentation.
        
        Args:
            pages: List of pages, where each page is a list of Block objects
            output_path: Path where the PPTX file should be saved
        """
        # Create a new presentation
        prs = Presentation()
        
        # Set slide dimensions from CSS configuration
        slide_width_inches = self.theme_config['slide_dimensions']['width_inches']
        slide_height_inches = self.theme_config['slide_dimensions']['height_inches']
        prs.slide_width = Inches(slide_width_inches)
        prs.slide_height = Inches(slide_height_inches)
        
        MIN_TEXTBOX_HEIGHT_PX = 28  # PPT minimum intrinsic textbox height

        for page_idx, page in enumerate(pages):
            # Add a new slide
            slide_layout = prs.slide_layouts[6]  # Blank layout
            slide = prs.slides.add_slide(slide_layout)
            
            # Apply theme background color (if not white)
            bg_hex = self.theme_config['colors'].get('background', '#ffffff')
            if bg_hex.lower() not in ['#ffffff', '#fff']:
                # Convert hex to RGB
                rgb = self._hex_to_rgb(bg_hex)
                background = slide.background
                fill = background.fill
                fill.solid()
                fill.fore_color.rgb = RGBColor(*rgb)

            # Track cumulative vertical offset (in px) required to compensate for min-height adjustments
            self._page_offset_px = 0

            # Add each block to the slide with dynamic offset adjustment
            for block in page:
                # Adjust top position by current cumulative offset
                block._adjusted_top_px = block.y + self._page_offset_px  # stash for use in _add_element_to_slide

                # Apply 28-px intrinsic textbox height compensation to every block that
                # eventually becomes a textbox (ie, not images or raw page-breaks)
                is_visual_box = not block.is_image() and not block.is_table() and not block.is_page_break()

                extra_height_px = 0
                if is_visual_box and block.height < MIN_TEXTBOX_HEIGHT_PX:
                    extra_height_px = MIN_TEXTBOX_HEIGHT_PX - block.height

                # Render the block with the calculated extra padding
                self._add_element_to_slide(
                    slide,
                    block,
                    adjusted_top_px=block._adjusted_top_px,
                    extra_padding_px=extra_height_px,
                )

                # Shift subsequent blocks exactly once
                if extra_height_px:
                    self._page_offset_px += extra_height_px
        
        # Handle the case where no pages were generated
        if not pages:
            # Create a single blank slide
            slide_layout = prs.slide_layouts[6]  # Blank layout
            slide = prs.slides.add_slide(slide_layout)
            
            # Set slide background color based on theme
            if self.theme == "dark":
                background = slide.background
                fill = background.fill
                fill.solid()
                fill.fore_color.rgb = RGBColor(26, 26, 26)  # #1a1a1a from CSS
        
        # Save the presentation
        prs.save(output_path)
    
    def _add_formatted_text(self, paragraph, block: Block):
        """Add formatted text to a paragraph, handling HTML inline formatting."""
        
        # Get the raw content
        raw_content = block.content
        
        # Convert HTML line breaks to newlines (will be used if we don't split into separate paragraphs)
        content_with_newlines = re.sub(r'<br\s*/?>', '\n', raw_content, flags=re.IGNORECASE)
        
        # Preprocess ==highlight== syntax (convert to HTML)
        content_with_newlines = re.sub(r'==(.*?)==', r'<mark>\1</mark>', content_with_newlines)

        # Clear the paragraph ready for new runs/paragraphs
        paragraph.clear()
        
        # Check for nested list metadata BEFORE any splitting
        level_match = re.search(r'data-list-levels="([^"]*)"', raw_content)
        list_type_match = re.search(r'data-list-type="([^"]*)"', raw_content)
        
        # If the raw HTML contains <br> tags and this isn't a nested list, split on <br>
        if ('<br' in raw_content.lower()) and not level_match and not list_type_match:
            # Split the RAW content so we keep inline tags per line intact
            line_parts = re.split(r'<br\s*/?>', raw_content, flags=re.IGNORECASE)
            first = True
            for part in line_parts:
                # After splitting, process highlight syntax inside each part
                part_processed = re.sub(r'==(.*?)==', r'<mark>\1</mark>', part)
                if first:
                    para = paragraph
                else:
                    para = paragraph._parent.add_paragraph()

                # Remove any leading/trailing whitespace
                part_processed = part_processed.strip()
                self._parse_html_to_runs(para, part_processed)
                first = False

        elif level_match and list_type_match:
            # Nested list handling – extract the inner content
            content_match = re.search(r'<p[^>]*>(.*?)</p>', raw_content, re.DOTALL)
            list_content = content_match.group(1) if content_match else raw_content
            self._add_nested_list_paragraphs(paragraph, list_content, level_match.group(1), list_type_match.group(1))
        elif block.tag in ['ul', 'ol']:
            # Fallback list detection where engine didn't convert <ul>/<ol> properly
            if self.debug:
                print(f"⚠️ Processing unconverted {block.tag} block - converting to nested list format")
            items = re.findall(r'<li[^>]*>(.*?)</li>', raw_content, re.DOTALL | re.IGNORECASE)
            if items:
                cleaned_items = [re.sub(r'<[^>]*>', '', item).strip() for item in items]
                list_content = '<br>'.join(cleaned_items)
                level_data = ','.join('0' for _ in items)
                self._add_nested_list_paragraphs(paragraph, list_content, level_data, block.tag)
            else:
                self._parse_html_to_runs(paragraph, content_with_newlines)
        else:
            # Regular paragraph – process content_with_newlines which already has \n converted
            self._parse_html_to_runs(paragraph, content_with_newlines)
        
        # Apply theme-aware line spacing directly from CSS (same as before)
        if hasattr(paragraph, 'line_spacing'):
            css_line_height = self.theme_config['line_height']
            if isinstance(css_line_height, str):
                if css_line_height.endswith('px'):
                    px_value = float(css_line_height.replace('px', ''))
                    base_font_size = self.theme_config['font_sizes']['p']
                    paragraph.line_spacing = px_value / base_font_size
                elif css_line_height.endswith('%'):
                    paragraph.line_spacing = float(css_line_height.replace('%', '')) / 100.0
                else:
                    paragraph.line_spacing = float(css_line_height)
            else:
                paragraph.line_spacing = float(css_line_height)

            if self.debug:
                print(f"📏 Applied CSS line-height: {css_line_height} -> {paragraph.line_spacing}")

        # End function early so we don't fall through to old logic below (we replaced it)
        return
    
    def _add_nested_list_paragraphs(self, first_paragraph, content, level_data, list_type):
        """Add additional paragraphs to handle nested lists within a text frame."""
        
        # Split content by <br> tags to get individual list items
        items = content.split('<br>')
        levels = [int(x) for x in level_data.split(',')]
        
        if len(items) != len(levels):
            print(f"⚠️ Mismatch: {len(items)} items, {len(levels)} levels")
            return
        
        # Get or create ol_counters for ordered lists
        ol_counters = {}
        
        # Get text frame from first paragraph
        text_frame = first_paragraph._element.getparent()
        
        for i, (item, item_level) in enumerate(zip(items, levels)):
            # Preserve original HTML to keep inline formatting
            item_html = item.strip()

            # Obtain text frame to add paragraphs
            para = first_paragraph if i == 0 else first_paragraph._parent.add_paragraph()

            para.clear()
            para.level = item_level

            # Remove default spacing
            para.space_before = Pt(0)
            li_mb_px = self.theme_config['margins'].get('li', 0)
            para.space_after = Pt(li_mb_px * 0.75)

            if list_type == 'ol':
                # Maintain simple counters per level
                if item_level not in ol_counters:
                    ol_counters[item_level] = 1
                else:
                    # Reset deeper level counters if we move up
                    for deeper in list(range(item_level + 1, max(ol_counters.keys()) + 1)):
                        ol_counters.pop(deeper, None)
                    ol_counters[item_level] += 1
                bullet_text = f"{ol_counters[item_level]}. "
            else:
                bullet_text = "• "

            # Prepend bullet/number run
            bullet_run = para.add_run()
            bullet_run.text = bullet_text

            # Parse inline HTML to runs preserving combinations
            self._parse_html_to_runs(para, item_html)
    
    def _parse_html_to_runs(self, paragraph, html_content):
        """Parse HTML content and create formatted runs in the paragraph."""
        from html import unescape
        
        # Stack to track nested formatting
        format_stack = []
        
        # Regular expression to find HTML tags and text
        html_pattern = r'(</?(?:strong|em|code|mark|b|i|u)>)|([^<]+)'
        
        # Split content into tokens (tags and text)
        tokens = re.findall(html_pattern, html_content, re.IGNORECASE)
        
        for tag, text in tokens:
            if tag:
                # Handle HTML tags
                tag = tag.lower()
                if tag.startswith('</'):
                    # Closing tag - pop from format stack
                    tag_name = tag[2:-1]  # Remove </ and >
                    if format_stack and format_stack[-1] == tag_name:
                        format_stack.pop()
                else:
                    # Opening tag - push to format stack
                    tag_name = tag[1:-1]  # Remove < and >
                    if tag_name in ['strong', 'b', 'em', 'i', 'code', 'mark', 'u']:
                        format_stack.append(tag_name)
            elif text:
                # Handle text content - preserve spaces but unescape HTML entities
                text = unescape(text)
                if text:  # Only add non-empty text (including spaces)
                    run = paragraph.add_run()
                    run.text = text
                    
                    # Apply formatting based on current format stack
                    is_code = False
                    for fmt in format_stack:
                        if fmt in ['strong', 'b']:
                            run.font.bold = True
                        elif fmt in ['em', 'i']:
                            run.font.italic = True
                        elif fmt == 'u':
                            run.font.underline = True
                        elif fmt == 'code':
                            run.font.name = 'Courier New'
                            is_code = True
                            # Apply code color from CSS theme
                            code_color = self.theme_config['colors']['code_text']
                            if code_color.startswith('#'):
                                rgb = self._hex_to_rgb(code_color)
                                run.font.color.rgb = RGBColor(*rgb)
                            # Apply code font size reduction (use default paragraph size + delta)
                            code_font_size = self.theme_config['font_sizes']['code']
                            run.font.size = Pt(code_font_size)
                        elif fmt == 'mark':
                            # Highlight formatting - use bright background color simulation
                            # Since we can't set background, we'll use bright text color
                            run.font.color.rgb = RGBColor(255, 140, 0)  # Orange highlight color
                            run.font.bold = True  # Make highlighted text bold too
                    
                    # Always set font family to match CSS exactly (unless it's code)
                    if not is_code:
                        run.font.name = self.theme_config['font_family']
    
    def _add_element_to_slide(self, slide, block: Block, adjusted_top_px: Optional[int] = None, extra_padding_px: int = 0):
        """Add a Block element to a slide."""
        # Convert browser coordinates to slide coordinates using CSS-defined dimensions
        
        slide_width_inches = self.theme_config['slide_dimensions']['width_inches']
        slide_height_inches = self.theme_config['slide_dimensions']['height_inches']
        browser_width_px = self.theme_config['slide_dimensions']['width_px']
        browser_height_px = self.theme_config['slide_dimensions']['height_px']
        
        # Calculate scaling factors
        x_scale = slide_width_inches / browser_width_px
        y_scale = slide_height_inches / browser_height_px
        
        # Use adjusted top if provided (to account for cumulative offsets)
        effective_top_px = adjusted_top_px if adjusted_top_px is not None else block.y
        top = Inches(effective_top_px * y_scale)
        
        # Apply small extra padding if requested
        effective_height_px = block.height + extra_padding_px
        height = Inches(effective_height_px * y_scale)
        
        # For text-based blocks, use the remaining slide width instead of tight content width
        is_text_block = block.tag in ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'] or block.is_list_item() or block.tag in ['ul', 'ol', 'pre']

        if is_text_block:
            # Calculate width as slide width minus left margin so line wrapping matches HTML measurement
            available_width_px = browser_width_px - block.x
            width = Inches(available_width_px * x_scale)
        else:
            width = Inches(block.width * x_scale)
        
        # Skip layout-only divs (both columns wrapper and individual column divs)
        if block.tag == 'div' and block.className and (
                'columns' in block.className or 'column' in block.className):
            return

        # Handle images early (they may have empty textContent)
        if block.is_image():
            import os
            image_path = block.src
            
            # Debug image path resolution
            if self.debug:
                print(f"🖼️ Attempting to add image: {image_path}")
                print(f"   - Path exists: {os.path.exists(image_path) if image_path else False}")
                print(f"   - Block dimensions: {block.width}x{block.height}px")
                
            try:
                if image_path and os.path.exists(image_path):
                    slide.shapes.add_picture(image_path, Inches(block.x * x_scale), top, width=width, height=height)
                    if self.debug:
                        print(f"✅ Successfully added image to slide")
                    return  # Successfully added image, exit early
                else:
                    if self.debug:
                        print(f"⚠️ Image file not accessible: {image_path}")
                    raise FileNotFoundError(f"Image file not found: {image_path}")
            except Exception as e:
                # fallback placeholder with more details
                if self.debug:
                    print(f"❌ Failed to add image: {e}")
                placeholder = slide.shapes.add_textbox(Inches(block.x * x_scale), top, width, height)
                placeholder.text_frame.text = f"[Missing image: {os.path.basename(image_path) if image_path else 'No src'}]"
            return
        
        # Skip elements that have no textual content
        if not block.content.strip():
            return
        
        # Ensure minimum dimensions for text boxes
        if width < Inches(0.5):
            width = Inches(0.5)
        if height < Inches(0.3):
            height = Inches(0.3)
        
        # Add text box to slide
        textbox = slide.shapes.add_textbox(Inches(block.x * x_scale), top, width, height)
        text_frame = textbox.text_frame
        text_frame.clear()
        
        # Configure text frame
        text_frame.margin_left = 0
        text_frame.margin_right = 0
        text_frame.margin_top = 0
        text_frame.margin_bottom = 0
        text_frame.word_wrap = True
        
        # Remove default paragraph spacing for all new paragraphs created later
        for para in text_frame.paragraphs:
            para.space_before = Pt(0)
            para.space_after = Pt(0)
        
        # Handle tables separately
        if block.is_table():
            self._add_table_to_slide(slide, block, Inches(block.x * x_scale), top, width, height)
            return
        
        # Add paragraph with rich text formatting
        p = text_frame.paragraphs[0]
        
        # Check if this is a nested list before calling _add_formatted_text
        content = block.content
        level_match = re.search(r'data-list-levels="([^"]*)"', content)
        list_type_match = re.search(r'data-list-type="([^"]*)"', content)
        
        if level_match and list_type_match:
            # This is a nested list - handle with text frame directly
            # Extract the actual content from the HTML metadata format
            content_match = re.search(r'<p[^>]*>(.*?)</p>', content, re.DOTALL)
            if content_match:
                list_content = content_match.group(1)
            else:
                # Fallback if no p tags found
                list_content = content
            
            self._add_nested_list_paragraphs(p, list_content, level_match.group(1), list_type_match.group(1))
        elif block.tag in ['ul', 'ol']:
            # FALLBACK: Handle ul/ol blocks that weren't converted by layout engine
            if self.debug:
                print(f"⚠️ Processing unconverted {block.tag} block - converting to nested list format")
            
            # Extract list items from raw HTML
            items = re.findall(r'<li[^>]*>(.*?)</li>', content, re.DOTALL | re.IGNORECASE)
            if items:
                # Clean each item and create level data (all level 0 for simple lists)
                cleaned_items = []
                for item in items:
                    # Clean HTML tags but preserve inline formatting
                    clean_item = re.sub(r'<[^>]*>', '', item).strip()
                    cleaned_items.append(clean_item)
                
                # Create the format expected by _add_nested_list_paragraphs
                list_content = '<br>'.join(cleaned_items)
                level_data = ','.join('0' for _ in items)  # All items at level 0
                list_type = block.tag
                
                self._add_nested_list_paragraphs(p, list_content, level_data, list_type)
            else:
                # Fallback to regular text processing if no items found
                self._add_formatted_text(p, block)
        else:
            # Regular content - use single paragraph approach
            self._add_formatted_text(p, block)
        
        # Configure paragraph formatting using theme-aware font sizes
        # For nested lists, apply formatting to all paragraphs in text frame
        paragraphs_to_format = []
        if level_match and list_type_match:
            # Nested list - format all paragraphs in text frame
            paragraphs_to_format = text_frame.paragraphs
        else:
            # Single paragraph content
            paragraphs_to_format = [p]
        
        # First, normalise PowerPoint paragraph spacing to match CSS (margin-top/bottom already in measured y/height)
        for para in paragraphs_to_format:
            para.space_before = Pt(0)
            # Determine margin-bottom in px based on block tag
            mb_px = 0
            if block.tag in ['h1', 'h2', 'h3']:
                mb_px = self.theme_config['margins'].get(block.tag, 0)
            elif block.tag == 'p':
                mb_px = self.theme_config['margins'].get('p', 0)
            elif block.tag in ['ul', 'ol'] or block.is_list_item():
                mb_px = self.theme_config['margins'].get('li', 0)
            para.space_after = Pt(mb_px * 0.75)

        if block.is_heading():
            # Heading formatting - apply to all runs in all paragraphs
            font_size = self.theme_config['font_sizes'].get(block.tag, 16)
            for para in paragraphs_to_format:
                for run in para.runs:
                    run.font.size = Pt(font_size)
                    if not run.font.bold:  # Only set if not already bold from inline formatting
                        run.font.bold = True
        elif block.is_code_block():
            # Code block formatting - apply to all runs in all paragraphs
            font_size = self.theme_config['font_sizes']['code']
            code_font_delta = self.theme_config['table_deltas']['font_delta']
            for para in paragraphs_to_format:
                for run in para.runs:
                    run.font.name = 'Courier New'
                    run.font.size = Pt(max(8, font_size + code_font_delta))
            # Set background color for code blocks
            if hasattr(textbox, 'fill'):
                textbox.fill.solid()
                if self.theme == "dark":
                    textbox.fill.fore_color.rgb = RGBColor(45, 45, 45)  # Dark gray
                else:
                    textbox.fill.fore_color.rgb = RGBColor(244, 244, 244)  # Light gray
        else:
            # Regular paragraph formatting - apply to all runs in all paragraphs
            font_size = self.theme_config['font_sizes']['p']
            for para in paragraphs_to_format:
                for run in para.runs:
                    if not run.font.size:  # Only set if not already set by inline formatting
                        run.font.size = Pt(font_size)
        
        # Apply color if specified
        if hasattr(block, 'style') and block.style and 'color' in block.style and block.style['color']:
            color = block.style['color']
            if isinstance(color, dict) and 'r' in color and 'g' in color and 'b' in color:
                for para in paragraphs_to_format:
                    para.font.color.rgb = RGBColor(color['r'], color['g'], color['b'])
        
        # Apply text alignment
        if hasattr(block, 'style') and block.style and 'textAlign' in block.style:
            align = block.style['textAlign']
            alignment = None
            if align == 'center':
                alignment = PP_ALIGN.CENTER
            elif align == 'right':
                alignment = PP_ALIGN.RIGHT
            else:
                alignment = PP_ALIGN.LEFT
            
            for para in paragraphs_to_format:
                para.alignment = alignment
        
        # Handle oversized content
        if hasattr(block, 'oversized') and block.oversized:
            # Make font smaller for oversized content
            for para in paragraphs_to_format:
                if para.font.size:
                    para.font.size = Pt(max(10, int(para.font.size.pt * 0.8))) 

    def _add_table_to_slide(self, slide, block: Block, left, top, width, height):
        """Add a PowerPoint table to the slide from HTML table content."""
        from html import unescape
        
        # Parse the HTML table to extract structure
        table_data = self._parse_html_table(block.content)
        
        if not table_data or not table_data['rows']:
            # Fallback to text if table parsing fails
            textbox = slide.shapes.add_textbox(left, top, width, height)
            text_frame = textbox.text_frame
            p = text_frame.paragraphs[0]
            self._add_formatted_text(p, block)
            return
        
        # Create PowerPoint table
        rows = len(table_data['rows'])
        cols = len(table_data['rows'][0]) if table_data['rows'] else 1
        
        # Adjust table width based on HTML column calculations if available
        if hasattr(block, 'table_column_widths') and block.table_column_widths:
            # Use the sum of HTML column widths as the table width
            html_total_width = sum(block.table_column_widths)
            table_width = px(html_total_width)
        else:
            table_width = width
        
        # Add table to slide - use a more conservative height estimate
        # PowerPoint will auto-adjust, but we need a reasonable starting point
        estimated_row_height = px(25)  # Conservative estimate per row
        estimated_table_height = estimated_row_height * rows
        table_shape = slide.shapes.add_table(rows, cols, left, top, table_width, estimated_table_height)
        table = table_shape.table
        
        # Get theme colors for table styling
        border_color = self.theme_config['colors']['table_border']
        text_color = self.theme_config['colors']['table_text']
        
        # Parse colors (hex to RGB)
        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip('#')
            if len(hex_color) != 6:
                # Fallback to black if invalid color
                hex_color = '000000'
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        border_rgb = hex_to_rgb(border_color)
        text_rgb = hex_to_rgb(text_color)
        
        # Populate table data
        for row_idx, row_data in enumerate(table_data['rows']):
            for col_idx, cell_data in enumerate(row_data):
                if row_idx < len(table.rows) and col_idx < len(table.columns):
                    cell = table.cell(row_idx, col_idx)
                    
                    # Set cell content with formatting
                    if cell.text_frame.paragraphs:
                        p = cell.text_frame.paragraphs[0]
                    else:
                        p = cell.text_frame.add_paragraph()
                    
                    # Create a temporary block for the cell content
                    cell_block = Block(
                        tag='td',
                        x=0, y=0, w=0, h=0,
                        content=cell_data['content']
                    )
                    
                    # Add formatted text to the cell
                    self._add_formatted_text(p, cell_block)
                    
                    # Apply table-specific styling
                    for run in p.runs:
                        # Set text color based on theme
                        run.font.color.rgb = RGBColor(*text_rgb)
                        
                        # Apply header styling if this is a header row
                        if cell_data.get('is_header', False):
                            run.font.bold = True
                    
                    # Set transparent background (black-and-white theme)
                    # No background color - PowerPoint default is transparent
                    
                    # Apply border styling
                    # NOTE: python-pptx has limited table border color support
                    # See: https://github.com/scanny/python-pptx/issues/71
                    # However, basic border styling and table layout work correctly
                    if self.debug and row_idx == 0 and col_idx == 0:
                        print(f"✅ TABLE STYLING: Applied theme '{self.theme}' styling successfully")
                        print(f"📏 Border color: {border_color} (PowerPoint defaults used)")
        
        # COMPLETELY disable PowerPoint's automatic table styling
        table.first_row = False
        table.first_col = False  
        table.last_row = False
        table.last_col = False
        table.horz_banding = False
        table.vert_banding = False
        
        # Do NOT apply any built-in PowerPoint table style – we want raw grid only
        # Built-in styles override our column widths and look inconsistent with the CSS theme
        if self.debug:
            print("🎨 Skipped built-in PowerPoint table styles – using raw XML borders only")
        
        # Use HTML-calculated column widths if available
        if hasattr(block, 'table_column_widths') and block.table_column_widths:
            for col_idx, col in enumerate(table.columns):
                if col_idx < len(block.table_column_widths):
                    # Use the HTML-calculated column width directly
                    html_col_width = block.table_column_widths[col_idx]
                    col.width = px(html_col_width)
        # Otherwise let PowerPoint auto-size columns
        
        # Match PowerPoint table dimensions to HTML exactly
        self._match_table_to_html_dimensions(table, block, rows, cols)
            
        # Apply theme-aware styling with standard PowerPoint features
        for row_idx, row in enumerate(table.rows):
            for col_idx, cell in enumerate(row.cells):
                # Set transparent background using standard API
                try:
                    cell.fill.background()  # Force transparent background
                except:
                    pass
                
                # Set border color using python-pptx API
                try:
                    border_rgb = self._hex_to_rgb(border_color)
                    cell.border_color = RGBColor(*border_rgb)
                    if self.debug and row_idx == 0 and col_idx == 0:
                        print(f"🔧 Applied border_color API: {border_color} -> RGB{border_rgb}")
                except Exception as e:
                    if self.debug and row_idx == 0 and col_idx == 0:
                        print(f"⚠️ border_color API failed: {e}")
                    pass
                
                # Apply text color and table-specific font sizing
                for paragraph in cell.text_frame.paragraphs:
                    for run in paragraph.runs:
                        if run.text.strip():  # Only apply to non-empty runs
                            run.font.color.rgb = RGBColor(*text_rgb)
                            
                            # Reduce TABLE font size based on CSS variable (--table-font-delta)
                            # This only affects table cells, not other text elements
                            font_delta = self.theme_config['table_deltas']['font_delta']
                            if run.font.size:
                                current_size = run.font.size.pt
                                run.font.size = Pt(max(8, current_size + font_delta))
                            else:
                                # Default table font size (body text + delta)
                                body_font_size = self.theme_config['font_sizes']['p']
                                run.font.size = Pt(max(8, body_font_size + font_delta))
                
                # NOTE: python-pptx has limited table border color support
                # See: https://github.com/scanny/python-pptx/issues/71
                # However, basic border styling and table layout work correctly
                if self.debug and row_idx == 0 and col_idx == 0:
                    print(f"✅ TABLE STYLING: Applied theme '{self.theme}' styling successfully")
                    print(f"📏 Border color: {border_color} (PowerPoint defaults used)")
        
        # ------------------------------------------------------------------
        # FINAL GUARANTEED BORDER PASS USING RAW XML
        # ------------------------------------------------------------------
        try:
            border_hex_final = border_color.lstrip('#') if border_color else '000000'
            self._apply_table_borders(table, border_hex_final)
            if self.debug:
                print(f"🔒 Applied raw XML borders with color #{border_hex_final} and width 12700 EMU")
        except Exception as e:
            if self.debug:
                print(f"⚠️  Raw XML border application failed: {e}")
            pass
        
        # ------------------------------------------------------------------
        # Ensure visible borders in DEFAULT theme by injecting an
        # <a:tblBorders> block.  macOS/Office ignores cell-level <a:ln*>
        # when the table itself has none, so we add a minimal grid once.
        # ------------------------------------------------------------------
        if self.theme == "default":
            try:
                border_pt = self.theme_config['table_deltas']['border_width_pt']  # e.g. 0.25
                border_emu = int(max(0.1, border_pt) * 12700)  # convert pt → EMU; enforce min width
                hex_col = self.theme_config['colors']['table_border'].lstrip('#') or '000000'

                tblPr = table._tbl.tblPr
                # wipe inherited styles but keep tblPr node
                for child in list(tblPr):
                    tblPr.remove(child)

                grid_xml = (
                    f'<a:tblBorders {nsdecls("a")}>'
                    f'<a:lnL w="{border_emu}"><a:solidFill><a:srgbClr val="{hex_col}"/></a:solidFill></a:lnL>'
                    f'<a:lnR w="{border_emu}"><a:solidFill><a:srgbClr val="{hex_col}"/></a:solidFill></a:lnR>'
                    f'<a:lnT w="{border_emu}"><a:solidFill><a:srgbClr val="{hex_col}"/></a:solidFill></a:lnT>'
                    f'<a:lnB w="{border_emu}"><a:solidFill><a:srgbClr val="{hex_col}"/></a:solidFill></a:lnB>'
                    f'<a:lnInsideH w="{border_emu}"><a:solidFill><a:srgbClr val="{hex_col}"/></a:solidFill></a:lnInsideH>'
                    f'<a:lnInsideV w="{border_emu}"><a:solidFill><a:srgbClr val="{hex_col}"/></a:solidFill></a:lnInsideV>'
                    f'</a:tblBorders>'
                )

                tblPr.append(parse_xml(grid_xml))

                if self.debug:
                    print(f"🔲 Injected tblBorders grid: {border_pt}pt #{hex_col}")
            except Exception as e:
                if self.debug:
                    print(f"⚠️  tblBorders injection failed: {e}")
                pass
        
        # Helper ends here (no recursive calls)
    
    def _parse_html_table(self, html_content):
        """Parse HTML table content into structured data."""
        
        # Extract table structure
        table_data = {
            'rows': [],
            'has_header': False
        }
        
        # Check for header
        header_match = re.search(r'<thead>(.*?)</thead>', html_content, re.DOTALL | re.IGNORECASE)
        if header_match:
            table_data['has_header'] = True
            header_content = header_match.group(1)
            header_rows = re.findall(r'<tr[^>]*>(.*?)</tr>', header_content, re.DOTALL | re.IGNORECASE)
            
            for row_html in header_rows:
                cells = re.findall(r'<th[^>]*>(.*?)</th>', row_html, re.DOTALL | re.IGNORECASE)
                row_data = []
                for cell_html in cells:
                    row_data.append({
                        'content': cell_html.strip(),
                        'is_header': True
                    })
                if row_data:
                    table_data['rows'].append(row_data)
        
        # Extract body rows
        tbody_match = re.search(r'<tbody>(.*?)</tbody>', html_content, re.DOTALL | re.IGNORECASE)
        if tbody_match:
            tbody_content = tbody_match.group(1)
        else:
            # If no tbody, use the whole content
            tbody_content = html_content
        
        body_rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody_content, re.DOTALL | re.IGNORECASE)
        for row_html in body_rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL | re.IGNORECASE)
            if cells:  # Only add rows that have td cells (not th cells)
                row_data = []
                for cell_html in cells:
                    row_data.append({
                        'content': cell_html.strip(),
                        'is_header': False
                    })
                if row_data:
                    table_data['rows'].append(row_data)
        
        return table_data

    # ------------------------------------------------------------------
    # Table border helpers
    # ------------------------------------------------------------------

    def _apply_table_borders(self, table, color_hex: str = "000000", width: str = "12700"):
        """Apply solid borders to every cell in the table using raw XML.

        Args:
            table: python-pptx table object
            color_hex: Hex string without '#', e.g. '000000'
            width: Line width in EMUs as string. 12700 ≈ 0.5pt, 25400 ≈ 1pt.
        """
        color_hex = color_hex.lstrip('#').lower()

        # XML snippet for a solid line
        def _solid_line_xml(side):
            return (
                f'<a:{side} w="{width}" {nsdecls("a")}>'
                f'<a:solidFill><a:srgbClr val="{color_hex}"/></a:solidFill>'
                f'<a:prstDash val="solid"/>'
                f'</a:{side}>'
            )

        for row in table.rows:
            for cell in row.cells:
                tcPr = cell._tc.get_or_add_tcPr()
                for border_side in ("lnL", "lnR", "lnT", "lnB"):
                    ln = tcPr.find(qn(f'a:{border_side}'))
                    if ln is None:
                        ln = parse_xml(_solid_line_xml(border_side))
                        tcPr.append(ln)
                    else:
                        # Update existing line
                        ln.set('w', width)
                        # Clear children then add new solidFill
                        ln.clear()
                        ln.append(parse_xml(f'<a:solidFill><a:srgbClr val="{color_hex}"/></a:solidFill>'))
                        ln.append(parse_xml('<a:prstDash val="solid"/>'))
        
        # Helper ends here (no recursive calls) 