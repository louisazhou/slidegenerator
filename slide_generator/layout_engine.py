#!/usr/bin/env python3
"""Layout engine for measuring HTML elements and pagination."""

import base64
import logging
import mimetypes
import os
import re
from html import unescape
from pathlib import Path
from typing import List, Optional, Callable, Dict, Tuple

from bs4 import BeautifulSoup
from PIL import Image

from .css_utils import CSSParser
from .layout_parser import parse_html_with_structured_layout
from .markdown_parser import MarkdownParser
from .models import Block
from .theme_loader import get_css

logger = logging.getLogger(__name__)


class ImageDimensionCache:
    """Cache for image dimensions to avoid repeated PIL Image.open calls."""
    
    def __init__(self, debug: bool = False):
        self.cache: Dict[str, Tuple[int, int]] = {}
        self.debug = debug
    
    def get_dimensions(self, image_path: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Get image dimensions, using cache if available.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Tuple of (width, height) or (None, None) if failed
        """
        if image_path in self.cache:
            if self.debug:
                logger.debug(f"📦 Using cached dimensions for {image_path}: {self.cache[image_path]}")
            return self.cache[image_path]
        
        try:
            with Image.open(image_path) as img:
                dimensions = img.size
                self.cache[image_path] = dimensions
                if self.debug:
                    logger.debug(f"📷 Cached new image dimensions for {image_path}: {dimensions}")
                return dimensions
        except Exception as e:
            if self.debug:
                logger.warning(f"⚠️ Could not read image dimensions for {image_path}: {e}")
            return None, None


class ImageScaler:
    """Utility class for consistent image scaling logic."""
    
    def __init__(self, css_parser: CSSParser, debug: bool = False):
        self.css_parser = css_parser
        self.debug = debug
        self.image_cache = ImageDimensionCache(debug)
        
        # Cache frequently used values
        self.viewport_width = css_parser.get_px_value('slide-width')
        self.viewport_height = css_parser.get_px_value('slide-height')
        self.padding_px = css_parser.get_px_value('slide-padding')
        self.content_width = self.viewport_width - 2 * self.padding_px
        self.content_height = self.viewport_height - 2 * self.padding_px
        column_config = css_parser.get_column_config()
        self.column_width = (self.content_width - column_config['gap']) / 2
    
    def calculate_image_dimensions(self, image_path: str, scale_x: Optional[str] = None, 
                                 scale_y: Optional[str] = None, in_column: bool = False, 
                                 parent_column_width: Optional[float] = None,
                                 apply_constraints: bool = False) -> tuple:
        """
        Calculate target image dimensions based on scaling parameters.
        
        Args:
            image_path: Path to the image file
            scale_x: X-axis scale factor (as string)
            scale_y: Y-axis scale factor (as string)  
            in_column: Whether the image is in a column layout
            parent_column_width: Width of parent column in px
            apply_constraints: Whether to apply automatic size constraints (default: False for old logic compatibility)
            
        Returns:
            Tuple of (target_width, target_height)
        """
        # Use cached dimensions
        original_width, original_height = self.image_cache.get_dimensions(image_path)
        if original_width is None or original_height is None:
            return None, None
        
        aspect_ratio = original_width / original_height
        
        # Determine base dimensions
        if in_column:
            if parent_column_width:
                try:
                    base_width = float(parent_column_width)
                except:
                    base_width = self.column_width
            else:
                base_width = self.column_width
        else:
            base_width = self.content_width
        base_height = self.content_height
        
        # Calculate target dimensions based on scaling - USE PURE PERCENTAGE SCALING (OLD LOGIC)
        if scale_x:
            scale_factor = float(scale_x)
            target_width = base_width * scale_factor
            target_height = target_width / aspect_ratio
            
            # Only apply constraints if explicitly requested (not default behavior)
            if apply_constraints and target_height > base_height:
                target_height = base_height * 0.95  # Leave margin
                target_width = target_height * aspect_ratio
                if self.debug:
                    context = "column" if in_column else "full-width"
                    logger.info(f"Image {image_path} height-constrained ({context}): {target_width:.0f}x{target_height:.0f}")
        
        elif scale_y:
            scale_factor = float(scale_y)
            target_height = base_height * scale_factor
            target_width = target_height * aspect_ratio
            
            # Only apply constraints if explicitly requested (not default behavior)
            if apply_constraints and target_width > base_width:
                target_width = base_width * 0.95  # Leave margin
                target_height = target_width / aspect_ratio
                if self.debug:
                    context = "column" if in_column else "full-width"
                    logger.info(f"Image {image_path} width-constrained ({context}): {target_width:.0f}x{target_height:.0f}")
        else:
            return None, None
        
        return target_width, target_height


class PaginationRule:
    """Represents a single pagination rule with conditions and actions."""
    
    def __init__(self, name: str, condition: Callable, action: str = "break", priority: int = 1):
        self.name = name
        self.condition = condition  # Function that takes (current_page, new_block, max_height) -> bool
        self.action = action  # "break" or "allow"
        self.priority = priority  # Higher priority rules are checked first

def _get_page_content_types(current_page: List[Block]) -> set:
    """Get set of content types on current page."""
    types = set()
    for block in current_page:
        if block.height > 200:
            types.add('large_content')
        if block.tag in ['img']:
            types.add('image')
        if block.tag in ['table']:
            types.add('table')
        if block.tag == 'h1':
            types.add('heading')
        if block.tag in ['p', 'h2', 'h3']:
            types.add('text')
    return types


def _is_heading_section(current_page: List[Block]) -> bool:
    """Check if current page is just a heading section (h1/h2/h3 + optional text)."""
    if not current_page or len(current_page) > 2:
        return False
    if current_page[0].tag not in ['h1', 'h2', 'h3']:
        return False
    if len(current_page) == 2 and current_page[1].tag not in ['p', 'h2', 'h3']:
        return False
    return True


def _is_lonely_heading(current_page: List[Block]) -> bool:
    """Check if current page has only a lonely heading (H1, H2, or H3)."""
    return len(current_page) == 1 and current_page[0].tag in ['h1', 'h2', 'h3']


def _is_divider_slide(page_blocks: List[Block]) -> bool:
    """
    Check if a page should be treated as a divider slide.
    A divider slide contains only headings (H1, H2, H3) with no other content.
    """
    if not page_blocks:
        return False
    
    # Check if all blocks are headings
    for block in page_blocks:
        if block.tag not in ['h1', 'h2', 'h3']:
            return False
    
    return True


def _should_keep_content_group_together(current_page: List[Block], new_block: Block, max_height: int) -> bool:
    """
    Determine if a new block should be kept with the current page based on content grouping.
    Analyzes logical content groups (heading + children) and their combined heights.
    """
    if not current_page:
        return False
    
    # Find the most recent heading on the current page
    recent_heading_idx = None
    for i in range(len(current_page) - 1, -1, -1):
        if current_page[i].is_heading():
            recent_heading_idx = i
            break
    
    if recent_heading_idx is None:
        return False  # No heading to group with
    
    recent_heading = current_page[recent_heading_idx]
    
    # Determine if new_block is likely a child of the recent heading
    is_child_content = (
        new_block.tag in ['h3', 'table', 'img', 'p'] and
        # h3 can be a child of h1, table/img/p can be children of h1/h3
        (recent_heading.tag == 'h1' or 
         (recent_heading.tag == 'h3' and new_block.tag in ['table', 'img', 'p']))
    )
    
    if not is_child_content:
        return False
    
    # Calculate the height of the content group (heading + its children + new block)
    group_blocks = current_page[recent_heading_idx:] + [new_block]
    group_height = sum(b.height for b in group_blocks)
    
    # Calculate remaining space on page (considering existing content before the group)
    existing_height = sum(b.height for b in current_page[:recent_heading_idx])
    available_space = max_height - existing_height
    
    # Additional: if new_block belongs to same .column container as any block in group, force allow
    if new_block.parentClassName and 'column' in new_block.parentClassName:
        for b in group_blocks:
            if b.parentClassName == new_block.parentClassName:
                return True

    # Allow slight overflow (≤ 10 %) so that a compact heading+paragraph+image
    # group isn't split across slides. This specifically fixes issues where the combined height exceeded the limit by just a few pixels.
    allowable = available_space * 1.10
    
    # Only allow grouping if the group fits within allowable space
    if group_height <= allowable:
        return True
    
    return False

# Define pagination rules in order of priority
PAGINATION_RULES = [
    # Rule 0: Keep content groups together based on logical structure
    PaginationRule(
        name="keep_content_groups_together",
        condition=lambda page, block, max_h: (
            _should_keep_content_group_together(page, block, max_h)
        ),
        action="allow",
        priority=30
    ),
    
    # Rule 1: Allow lonely headings to collect their content
    PaginationRule(
        name="allow_lonely_heading_with_any_content",
        condition=lambda page, block, max_h: (
            _is_lonely_heading(page)
        ),
        action="allow",
        priority=25
    ),
    
    # Rule 2: Multiple large images should be separated
    PaginationRule(
        name="separate_multiple_large_images",
        condition=lambda page, block, max_h: (
            'large_content' in _get_page_content_types(page) and
            block.height > 200 and
            not _is_heading_section(page)
        ),
        action="break",
        priority=10
    ),
]


def _should_break_page(current_page: List[Block], new_block: Block, max_height: int):
    """
    Determine if a page break should occur based on configurable rules.
    Returns:
    - True: Rule says break page
    - False: Rule says allow (explicit override)
    - None: No rule matched, use default logic
    """
    if not current_page:
        return None
    
    # Sort rules by priority (higher first)
    sorted_rules = sorted(PAGINATION_RULES, key=lambda r: r.priority, reverse=True)
    
    for rule in sorted_rules:
        try:
            if rule.condition(current_page, new_block, max_height):
                # Debug logging for content grouping decisions
                if rule.name == "keep_content_groups_together":
                    total_height = sum(b.height for b in current_page) + new_block.height
                    logger.debug(f"📋 Content grouping: Keeping {new_block.tag}({new_block.height}px) with page (total: {total_height}px, limit: {max_height}px)")
                
                if rule.action == "break":
                    return True
                elif rule.action == "allow":
                    return False  # Explicit allow overrides other rules
        except Exception as e:
            # Log rule evaluation errors but don't break pagination
            logger.warning(f"Pagination rule '{rule.name}' failed: {e}")
            continue
    
    return None  # No rule matched


def paginate(blocks: List[Block], max_height_px: int = 540, padding_px: int = 19) -> List[List[Block]]:
    """
    Paginate blocks based on height and explicit page breaks.
    
    Args:
        blocks: List of Block objects
        max_height_px: Maximum height in pixels for a single slide
        
    Returns:
        List of pages, where each page is a list of Block objects
    """
    pages = []
    current_page = []
    page_start_y = None  # Track where the current page starts
    _source_slide_idx = 0  # Track originating markdown slide index
    
    # Simple pagination with lookahead grouping
    processed_block_indices = set()  # Track which blocks have been processed as part of groups
    
    for i, block in enumerate(blocks):
        # Skip blocks that were already processed as part of a group
        if i in processed_block_indices:
            continue

        # Annotate block with its originating markdown slide index
        try:
            block.source_slide = _source_slide_idx
        except Exception:
            pass
        # Handle explicit page breaks
        if block.is_page_break():
            # Encountered explicit page break – finish current page and advance logical slide index
            if current_page:
                pages.append(current_page)
            current_page = []
            page_start_y = None
            _source_slide_idx += 1  # next blocks belong to following markdown slide
            continue
        
        # Get the height of the block
        block_height = block.height
        
        # Check for oversized blocks and mark them
        if block_height > max_height_px * 0.8:  # 80% of slide height
            block.oversized = True
        
        # Determine if this block fits on the current page
        should_start_new_page = False
        
        if current_page:
            # Calculate where this block would end relative to the page start
            if page_start_y is None:
                page_start_y = current_page[0].y
                  
            # Apply content-aware pagination rules first
            rule_decision = _should_break_page(current_page, block, max_height_px)
            
            # If rules explicitly allow, skip height checks
            if rule_decision is False:  # Explicit "allow" from rules
                should_start_new_page = False
            elif rule_decision is True:  # Explicit "break" from rules
                should_start_new_page = True
            else:  # No rule matched (rule_decision is None), use simple height logic
                # Simple height check - no spatial analysis needed
                relative_y = block.y - page_start_y
                relative_bottom = relative_y + block_height
                
                # If this block would extend beyond the page boundary, start new page
                if relative_bottom > max_height_px:
                    should_start_new_page = True
        
        # Fallback: limit number of blocks per slide to prevent overcrowding
        # if not should_start_new_page and len(current_page) >= 18:
        #     should_start_new_page = True
        
        if should_start_new_page:
            # Only add non-empty pages
            pages.append(current_page)
            current_page = []
            page_start_y = None
            
        # Add the block to the current page
        current_page.append(block)
        
        # Set page start Y if this is the first block on the page
        if page_start_y is None:
            page_start_y = block.y
    
    # Add the last page if it's not empty
    if current_page:
        pages.append(current_page)
    
    # Normalize Y coordinates for each page
    for page in pages:
        if not page:
            continue
            
        # Find the minimum Y coordinate on this page
        min_y = min(block.y for block in page)
        
        # Adjust all Y coordinates to start from CSS padding position (dynamic from CSS variables)
        page_top_margin = padding_px  # Use dynamic padding from CSS
        for block in page:
            block.y = block.y - min_y + page_top_margin
    
    return pages


class LayoutEngine:
    """
    Layout engine for measuring HTML elements and pagination.
    """
    
    def __init__(self, *, debug: bool = False, theme: str = "default", tmp_dir: Path, base_dir: Path = None):
        """
        Args:
            debug: Whether to enable debug output
            theme: Theme name (e.g. "default", "dark")
            tmp_dir: Directory to store temporary files
            base_dir: Base directory for resolving relative image paths
        """
        self.debug = debug
        self.theme = theme
        self.tmp_dir = tmp_dir
        self.base_dir = base_dir or Path.cwd()
        self.css_parser = CSSParser(theme)
        self._default_tmp_dir = tmp_dir  # may be None; used if caller passes explicit tmp
        self.image_scaler = ImageScaler(self.css_parser, debug)
    
    def convert_markdown_to_html(self, markdown_text):
        """Convert markdown to HTML with layout CSS."""
        # Handle empty or whitespace-only content
        if not markdown_text or not markdown_text.strip():
            return ""
        
        # Use the new markdown parser
        parser = MarkdownParser(base_dir=self.base_dir)
        html_slides = parser.parse_with_page_breaks(markdown_text)
        # Expose speaker notes collected by the parser so that upstream callers (e.g. SlideGenerator) can access them
        self.slide_notes = parser.slide_notes
        
        # If no content slides, return empty string
        if not html_slides:
            return ""
        
        # Get CSS from theme system - use the configured theme
        theme_css = get_css(self.theme)
        
        # Import HTML-specific CSS that contains column and admonition styles
        from .layout_parser import HTML_SPECIFIC_CSS
        
        # Combine theme CSS with HTML-specific layout styles
        combined_css = theme_css + "\n" + HTML_SPECIFIC_CSS
        
        # Combine HTML slides with proper UTF-8 document structure
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Slide Content</title>
<style>
{combined_css}
</style>
</head>
<body>
"""
        for i, html_slide in enumerate(html_slides):
            full_html += f'<div class="slide" id="slide-{i}">\n{html_slide}\n</div>\n'
            
            # Add a page break marker (except after the last slide)
            if i < len(html_slides) - 1:
                full_html += '<div class="page-break"><!-- slide --></div>\n'
        
        full_html += "</body></html>"
        
        return full_html
    
    def _process_math_equations(self, html_content: str, temp_dir: Optional[str]) -> str:
        """
        Process math equations in HTML content and convert them to images.
        
        Args:
            html_content: HTML content that may contain math elements
            temp_dir: Temporary directory for storing SVG files
            
        Returns:
            HTML content with math equations replaced by img tags
        """
        # Check if there are any math elements in the HTML
        if 'class="math' not in html_content:
            return html_content
        
        if temp_dir is None:
            # Use the engine's configured temp directory instead of system temp
            temp_dir = str(self.tmp_dir)
        
        try:
            # Import math renderer
            from .math_renderer import get_math_renderer
            
            # Use temp_dir for math rendering (no persistent cache)
            math_renderer = get_math_renderer(cache_dir=temp_dir, debug=self.debug)
            
            # Process math elements 
            processed_html = math_renderer.render_math_html(html_content, temp_dir, mode="html")
            
            if self.debug:
                logger.info(f"Processed math equations in HTML")
            
            return processed_html
            
        except ImportError:
            if self.debug:
                logger.warning("Math renderer not available, skipping math processing")
            return html_content
        except Exception as e:
            if self.debug:
                logger.warning(f"Error processing math equations: {e}")
            return html_content
    
    async def measure_and_paginate(self, markdown_text: str) -> List[List[Block]]:
        """
        Convert markdown to HTML, measure layout, and return paginated Block objects.
        
        Args:
            markdown_text: Markdown content to process

        Returns:
            List of pages, where each page is a list of Block objects
        """
        # Handle empty or whitespace-only content
        if not markdown_text or not markdown_text.strip():
            return []

        # Convert markdown to HTML
        html_raw = self.convert_markdown_to_html(markdown_text)

        # Create two versions:
                    # 1. HTML version with text fallbacks for browser preview
        # 2. PowerPoint version with PNG images for display math, text for inline math
        try:
            from .math_renderer import get_math_renderer
            math_renderer = get_math_renderer(cache_dir=str(self.tmp_dir), debug=self.debug)
            # Derive theme text colour from CSS so math PNGs match theme
            css = get_css(self.theme)
            m = re.search(r'body\s*{[^}]*?color:\s*([^;\s]+)', css, re.IGNORECASE | re.DOTALL)
            theme_text_color = m.group(1).strip() if m else '#000000'
            math_renderer.png_text_color = theme_text_color
            
                            # For HTML debug output - text fallback rendering
            preview_html = math_renderer.render_math_html(html_raw, str(self.tmp_dir), mode="html")

            # For PowerPoint processing - display math as images, inline as text
            measurement_html = math_renderer.render_math_html(html_raw, str(self.tmp_dir), mode="mixed")
            
        except Exception as e:
            if self.debug:
                logger.warning(f"Math renderer failed: {e}")
            preview_html = html_raw
            measurement_html = html_raw

        # Use measurement_html for layout processing
        html_content = measurement_html
        
        # If no HTML content was generated, return empty list
        if not html_content:
            return []

        # Use the tmp_dir passed at construction
        temp_dir = self.tmp_dir
        if self.debug:
            logger.info(f"Debug files will be saved to: {temp_dir}")
        
        # Store temp_dir for image processing
        self._current_temp_dir = temp_dir
        
        # Always use structured pptx-box parser
        
        if self.debug:
            logger.info("Using structured pptx-box parser")
        
        # Set up _original_soup for debug HTML generation and add bid attributes
        # Use the same BID assignment logic as legacy preprocessing
        processed_html_for_bids = self._preprocess_html_for_measurement(html_content)
        
        # Use structured parser with properly preprocessed HTML that has BIDs
        blocks = await parse_html_with_structured_layout(
            processed_html_for_bids,
            theme=self.theme,
            temp_dir=str(temp_dir),
            debug=self.debug,
            base_dir=str(self.base_dir)
        )
        
        # Build _original_soup from the MEASUREMENT version to ensure BID consistency
        # IMPORTANT: Use the SAME HTML structure that was used for block creation
        self._original_soup = BeautifulSoup(processed_html_for_bids, 'html.parser')
        
        # The BIDs are already assigned in processed_html_for_bids, so we don't need to add them again

        # Apply intelligent image scaling based on column context
        for block in blocks:
            if block.is_image():
                logger.info(f"IMAGE BLOCK: src='{block.src}', content='{block.content}'")
        blocks = self._apply_intelligent_image_scaling_to_blocks(blocks, str(temp_dir))

        # Merge consecutive list items into text blocks
        blocks = self._merge_consecutive_lists(blocks)
        
        # --- Determine usable page height (slide height minus padding) ---
        slide_height_px = self.css_parser.get_px_value('slide-height')
        padding_px = self.css_parser.get_px_value('slide-padding')
        
        usable_height_px = slide_height_px - 2 * padding_px
        if usable_height_px <= 0:
            raise ValueError(f"❌ CSS theme '{self.theme}' has invalid dimensions: "
                           f"slide height {slide_height_px}px minus 2×{padding_px}px padding = {usable_height_px}px")
        
        # Paginate the blocks using usable height
        pages = paginate(blocks, usable_height_px, padding_px)

        # Generate paginated debug HTML to show actual slide structure
        if self.debug:
            # Use the already-rendered preview HTML (text fallbacks)
            debug_html = preview_html

            paginated_html = self._generate_paginated_debug_html(pages, debug_html, temp_dir)
                
            # Save to output directory for easy viewing
            current_working_dir = Path.cwd()
            output_dir = current_working_dir / "output"
            output_dir.mkdir(exist_ok=True)
            
            with open(output_dir / f"paginated_slides_{self.theme}.html", "w", encoding='utf-8') as f:
                f.write(paginated_html)
                
            logger.info(f"📄 Generated paginated HTML: output/paginated_slides_{self.theme}.html")
            logger.info(f"Layout engine created {len(pages)} pages:")
            for i, page in enumerate(pages):
                logger.info(f"  Page {i+1}: {len(page)} blocks (height limit: {usable_height_px}px)")
                for j, block in enumerate(page):
                    oversized_flag = " [OVERSIZED]" if hasattr(block, 'oversized') and block.oversized else ""
                    logger.info(f"    Block {j+1}: {block.tag} ({block.height}px) - '{block.content[:30]}...'{oversized_flag}")

        return pages

    def _preprocess_html_for_measurement(self, html_content):
        """
        Preprocess HTML content to match what will actually be rendered in PowerPoint.
        This ensures the browser measures the same content that will be displayed.
        """

        def process_list_content(match):
            """Process a single list (ul or ol) and convert to formatted text with level information"""
            list_tag = match.group(1).lower()  # 'ul' or 'ol'
            list_content = match.group(2)
            
            # Extract list items with their nested structure
            items_with_levels = self._extract_list_items_with_levels(list_content, list_tag)

            # Debug: show what the parser extracted to help diagnose missing items
            if self.debug:
                try:
                    logger.debug("📝 List (%s) extracted %d items: %s", list_tag, len(items_with_levels), [txt for txt, _ in items_with_levels])
                except Exception:
                    pass
            
            if not items_with_levels:
                return match.group(0)  # Return original if no items found
            
            # Format list items for PowerPoint (flat text with level metadata)
            formatted_items = []
            
            for i, (item_text, level) in enumerate(items_with_levels):
                # Preserve inline formatting tags (strong, em, code, mark, u)
                clean_text = item_text.strip()
                
                # Don't add manual bullets/numbers - PowerPoint will handle this via paragraph.level
                formatted_items.append(clean_text)
            
            # Create a special data attribute to store level information
            formatted_text = '<br>'.join(formatted_items)
            
            # Add level metadata as data attribute for PPTX renderer to use
            level_data = ','.join(str(level) for _, level in items_with_levels)
            return f'<p data-list-levels="{level_data}" data-list-type="{list_tag}">{formatted_text}</p>'
        
        # Process all lists in the HTML - handle nested lists properly
        # We need to process from outermost to innermost to preserve structure
        processed_html = html_content
        
        # ------------------------------------------------------------
        # DEBUG-ONLY: Insert <p class="figure-caption"> after each
        # <img data-caption> so that the paginated HTML preview shows
        # captions exactly as the JS step will create them.  Because the
        # JavaScript in layout_parser now skips caption creation when one
        # already exists, this will not cause duplicates in PPTX.
        # ------------------------------------------------------------
        if self.debug:
            try:
                _soup = BeautifulSoup(processed_html, 'html.parser')
                for _img in _soup.find_all('img'):
                    cap_txt = _img.get('data-caption')
                    if cap_txt and cap_txt.strip():
                        nxt = _img.find_next_sibling()
                        if not (nxt and getattr(nxt, 'get', lambda *_: None)('class') and 'figure-caption' in nxt['class']):
                            cap_el = _soup.new_tag('p', **{'class': 'figure-caption'})
                            cap_el.string = cap_txt
                            _img.insert_after(cap_el)
                processed_html = str(_soup)
            except Exception:
                pass  # Fail silently – preview captions are a convenience
        
        # Keep processing until no more top-level lists are found
        max_iterations = 50  # Increased limit for complex documents with many lists
        iteration = 0
        
        if self.debug:
            initial_list_count = len(re.findall(r'<(ul|ol)[^>]*>', processed_html, flags=re.IGNORECASE))
            logger.info(f"🔄 Processing {initial_list_count} lists in HTML document...")
        
        while iteration < max_iterations:
            # Find all list starts
            list_starts = []
            for match in re.finditer(r'<(ul|ol)[^>]*>', processed_html, flags=re.IGNORECASE):
                list_starts.append((match.start(), match.end(), match.group(1).lower()))
            
            if not list_starts:
                break
                
            # Process the first list with balanced tag matching
            start_pos, tag_end_pos, list_tag = list_starts[0]
            
            # Find the matching closing tag using balanced counting
            content_start = tag_end_pos
            current_pos = content_start
            depth = 1
            
            while current_pos < len(processed_html) and depth > 0:
                # Look for opening or closing tags of the same type
                open_pattern = f'<{list_tag}[^>]*>'
                close_pattern = f'</{list_tag}>'
                
                next_open = re.search(open_pattern, processed_html[current_pos:], re.IGNORECASE)
                next_close = re.search(close_pattern, processed_html[current_pos:], re.IGNORECASE)
                
                if next_close and (not next_open or next_close.start() < next_open.start()):
                    # Found closing tag first
                    depth -= 1
                    if depth == 0:
                        # This is our matching closing tag
                        content_end = current_pos + next_close.start()
                        tag_close_start = current_pos + next_close.start()
                        tag_close_end = current_pos + next_close.end()
                        break
                    current_pos += next_close.end()
                elif next_open:
                    # Found opening tag first
                    depth += 1
                    current_pos += next_open.end()
                else:
                    # No more tags found
                    content_end = len(processed_html)
                    tag_close_start = len(processed_html)
                    tag_close_end = len(processed_html)
                    break
            else:
                # Reached end without finding balanced closing
                content_end = len(processed_html)
                tag_close_start = len(processed_html)
                tag_close_end = len(processed_html)
                
            # Extract the balanced list content
            list_content = processed_html[content_start:content_end]
            
            # Create a mock match object for the process_list_content function
            class MockMatch:
                def __init__(self, tag, content, full_match):
                    self._tag = tag
                    self._content = content
                    self._full_match = full_match
                    
                def group(self, n):
                    if n == 0:
                        return self._full_match
                    elif n == 1:
                        return self._tag
                    elif n == 2:
                        return self._content
                        
            full_match = processed_html[start_pos:tag_close_end]
            mock_match = MockMatch(list_tag, list_content, full_match)
            
            # Process this list
            replacement = process_list_content(mock_match)
            processed_html = (processed_html[:start_pos] + 
                            replacement + 
                            processed_html[tag_close_end:])
            iteration += 1
        
        # ------------------------------------------------------------------
        # 4) WYSIWYG SUPPORT – stamp every measurable element with bid
        # ------------------------------------------------------------------
        soup = BeautifulSoup(processed_html, 'html.parser')
        bid_counter = 0
        for el in soup.select('.slide *'):
            # Skip page-break markers or admonition internal children (only top-level)
            if el.has_attr('data-bid'):
                continue
            skip = False
            for parent in el.parents:
                if parent.has_attr('class') and 'admonition' in parent.get('class', []):
                    # If parent is admonition and it's not the same element, skip
                    if parent != el:
                        skip = True
                        break
            if skip:
                continue
            el['data-bid'] = f'b{bid_counter}'
            bid_counter += 1

        # Save pristine soup for later DOM slicing in debug HTML
        self._original_soup = soup

        return str(soup)
    
    def _extract_list_items_with_levels(self, list_content, list_tag, base_level=0):
        """Extract list items and their nesting level using BeautifulSoup (robust)."""

        soup = BeautifulSoup(list_content, 'html.parser')

        items_with_levels = []

        def _walk(list_element, level):
            for li in list_element.find_all('li', recursive=False):
                # capture text/html before any nested lists
                parts = []
                for child in li.contents:
                    if child.name in ('ul', 'ol'):
                        break
                    parts.append(str(child))

                combined = ''.join(parts)
                clean = self._clean_html_for_measurement(combined)
                if clean.strip():
                    items_with_levels.append((clean, level))

                # recurse into nested lists directly under this li
                for sub in li.find_all(['ul', 'ol'], recursive=False):
                    _walk(sub, level + 1)

        # Locate the correct root list element
        if soup.name == list_tag:
            # The soup itself is the correct list type
            root = soup
        else:
            # For fragments, we need to wrap them to ensure we process ALL items
            # Don't use soup.find() as it might find nested lists instead of the root
            wrapped = f'<{list_tag}>' + list_content + f'</{list_tag}>'
            root = BeautifulSoup(wrapped, 'html.parser').find(list_tag)

        if root:
            _walk(root, base_level)

        return items_with_levels

    def _clean_html_for_measurement(self, text):
        """Clean HTML tags but preserve inline formatting for measurement."""
        
        # First, handle inline formatting tags that we want to preserve
        # Convert them to a temporary format
        text = re.sub(r'<(strong|b)(?:[^>]*)>(.*?)</\1>', r'**\2**', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<(em|i)(?:[^>]*)>(.*?)</\1>', r'*\2*', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<code(?:[^>]*)>(.*?)</code>', r'`\1`', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<mark(?:[^>]*)>(.*?)</mark>', r'==\1==', text, flags=re.IGNORECASE | re.DOTALL)
        
        # Remove all other HTML tags EXCEPT inline formatting we want to preserve
        # Keep span/u/del/strong/em/i/b/code/mark tags with any attributes
        text = re.sub(r'<(?!/?(?:span|u|del|strong|b|em|i|code|mark)\b)[^>]+>', '', text, flags=re.IGNORECASE)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Convert back to HTML formatting tags
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
        text = re.sub(r'==(.*?)==', r'<mark>\1</mark>', text)
        
        return unescape(text)

    def _merge_consecutive_lists(self, blocks: List[Block]) -> List[Block]:
        """Merge consecutive list items into single text blocks."""
        merged_blocks = []
        current_block = None
        
        for block in blocks:
            if block.is_list_item():
                if current_block:
                    current_block.content += " " + block.content
                else:
                    current_block = block
            else:
                if current_block:
                    merged_blocks.append(current_block)
                    current_block = None
                merged_blocks.append(block)
        
        if current_block:
            merged_blocks.append(current_block)
        
        return merged_blocks 



    def _apply_intelligent_image_scaling_to_blocks(self, blocks: List[Block], temp_dir: str) -> List[Block]:
        """
        Apply intelligent image scaling to Block objects based on their scaling attributes.
        This implements the 6-step algorithm:
        1. Try to apply "X% of available width" (excluding padding, considering columns)
        2. Check if resulting height would exceed current page
        3. Calculate available height (total height - padding - all content above)
        4. Reverse-engineer scaling % to fit available height
        5. Apply the adjusted scaling
        6. Provide final dimensions to PPTX
        """
        if self.debug:
            logger.info(f"🔍 Applying intelligent image scaling to {len(blocks)} blocks...")
        
        # Track pagination context for accurate height constraints
        usable_height = self.css_parser.get_px_value('slide-height') - 2 * self.css_parser.get_px_value('slide-padding')
        
        for i, block in enumerate(blocks):
            if block.is_image() and hasattr(block, 'src'):
                # Check if this block has scaling information
                scale_x = getattr(block, 'scaleX', None)
                scale_y = getattr(block, 'scaleY', None)
                in_column = getattr(block, 'inColumn', None) == 'true'
                
                if scale_x or scale_y:
                    # STEP 1: Apply requested percentage of available width
                    parent_col_width = getattr(block, 'parentColumnWidth', None)
                    initial_width, initial_height = self.image_scaler.calculate_image_dimensions(
                        block.src, scale_x, scale_y, in_column=in_column, parent_column_width=parent_col_width
                    )
                    
                    if initial_width is not None and initial_height is not None:
                        # STEP 2 & 3: Calculate available height more accurately
                        # Look for natural page breaks (new headings) to determine page boundaries
                        page_start_idx = 0
                        for j in range(i-1, -1, -1):
                            if blocks[j].tag == 'h1':  # Major heading indicates likely page start
                                page_start_idx = j
                                break
                        
                        # Calculate content height from likely page start to this image
                        content_above_height = sum(b.height for b in blocks[page_start_idx:i])
                        available_height = usable_height - content_above_height
                        
                        final_width = initial_width
                        final_height = initial_height
                        
                        # STEP 4: Only constrain if image really exceeds reasonable bounds  
                        # Be more generous with height constraints to avoid unnecessary scaling
                        max_reasonable_height = usable_height * 0.70  # Allow up to 70% of slide height
                        
                        if initial_height > max_reasonable_height:
                            # STEP 5: Apply height-constrained scaling
                            original_width, original_height = self.image_scaler.image_cache.get_dimensions(block.src)
                            if original_width and original_height:
                                aspect_ratio = original_width / original_height
                                
                                # Use 70% of slide height as maximum, not available height
                                final_height = max_reasonable_height
                                final_width = final_height * aspect_ratio
                                
                                if self.debug:
                                    original_scale = float(scale_x) if scale_x else float(scale_y)
                                    new_scale = final_width / (self.image_scaler.content_width * (1 if not in_column else 0.5))
                                    logger.info(f"📐 Height-constrained scaling for {block.src}:")
                                    logger.info(f"   Original request: {original_scale*100}% -> {initial_width:.0f}x{initial_height:.0f}")
                                    logger.info(f"   Max reasonable height: {max_reasonable_height:.0f}px")
                                    logger.info(f"   Adjusted to: {new_scale*100:.1f}% -> {final_width:.0f}x{final_height:.0f}")
                            else:
                                if self.debug:
                                    logger.warning(f"⚠️ Could not load image {block.src} for aspect ratio")
                                # Fallback: use requested size but warn about potential overflow
                                final_width = initial_width
                                final_height = initial_height
                        elif self.debug:
                            # Image fits reasonably within slide bounds
                            logger.info(f"📐 Keeping original scale for {block.src}: {final_width:.0f}x{final_height:.0f} (within {max_reasonable_height:.0f}px limit)")
                        
                        # STEP 6: Update block dimensions with final calculated values
                        old_dims = f"{block.width}x{block.height}"
                        # --- NEW: track original height before resizing ---
                        original_height_px = block.height
                        block.w = int(final_width)
                        block.h = int(final_height)

                        # --- NEW: shift subsequent blocks on the same logical slide ---
                        height_delta = block.h - original_height_px  # positive: image became taller, negative: smaller
                        if height_delta != 0:
                            # Determine the column context of the current image (None if not in a column)
                            current_parent_col_w = getattr(block, 'parentColumnWidth', None)
                            current_col_x = block.x

                            for k in range(i + 1, len(blocks)):
                                next_block = blocks[k]
                                if next_block.is_page_break():
                                    break  # new slide, stop adjusting

                                # Apply the shift ONLY to blocks that share the same column context.
                                if (getattr(next_block, 'parentColumnWidth', None) == current_parent_col_w and
                                    abs(next_block.x - current_col_x) <= 5):
                                    next_block.y += height_delta

                        # --- NEW: ensure debug HTML reflects the new dimensions ---
                        if hasattr(self, '_original_soup') and hasattr(block, 'bid'):
                            try:
                                node = self._original_soup.select_one(f'[data-bid="{block.bid}"]')
                                if node and node.name == 'img':
                                    node['width'] = str(block.w)
                                    node['height'] = str(block.h)
                            except Exception:
                                pass
                        
                        context = "column" if in_column else "full-width"
                        constraint_type = "height-constrained" if initial_height > max_reasonable_height else "original-scale"
                        if self.debug:
                            logger.info(f"📐 Scaled block {block.src}: {old_dims} -> {final_width:.0f}x{final_height:.0f} ({context}, {constraint_type})")
                    elif self.debug:
                        logger.warning(f"⚠️ Failed to calculate dimensions for {block.src}")
                elif block.is_image():
                    # AUTO-FIT when no data-scale-x / data-scale-y is present
                    
                    # 1. Calculate available width (respecting columns)
                    available_w = (block.parentColumnWidth
                                   if getattr(block, 'parentColumnWidth', None)
                                   else self.image_scaler.content_width) * 0.95

                    # 2. Estimate available HEIGHT on *this* page so far
                    #    Approximate page start = last major heading (h1) before this image
                    page_start_idx = 0
                    for j in range(i-1, -1, -1):
                        if blocks[j].tag == 'h1':
                            page_start_idx = j
                            break

                    content_above_height = sum(b.height for b in blocks[page_start_idx:i])
                    available_h = max(0, usable_height - content_above_height) * 0.95

                    original_w, original_h = self.image_scaler.image_cache.get_dimensions(block.src)
                    if original_w is None or original_h is None:
                        if self.debug:
                            logger.warning(f"⚠️ Auto-fit failed to read image size for {block.src}")
                        continue
                    
                    # If image already fits, no scaling needed
                    if original_w <= available_w and original_h <= available_h:
                        continue

                    # 3. Calculate shrink ratio for both axes and pick the smallest
                    ratio_w = available_w / original_w if original_w > 0 else 1
                    ratio_h = available_h / original_h if original_h > 0 else 1
                    ratio = min(ratio_w, ratio_h, 1) # Use min to guarantee fit, cap at 1 (no enlarging)

                    # 4. Apply final dimensions to block
                    # Track original height before resizing so we can shift following blocks
                    original_height_px = block.h
                    block.w = int(original_w * ratio)
                    block.h = int(original_h * ratio)

                    # Shift subsequent blocks to compensate for the change in image height
                    height_delta = block.h - original_height_px
                    if height_delta != 0:
                        current_parent_col_w = getattr(block, 'parentColumnWidth', None)
                        current_col_x = block.x
                        for k in range(i + 1, len(blocks)):
                            next_block = blocks[k]
                            if next_block.is_page_break():
                                break
                            if (getattr(next_block, 'parentColumnWidth', None) == current_parent_col_w and
                                abs(next_block.x - current_col_x) <= 5):
                                next_block.y += height_delta

                    # Ensure the corresponding <img> in the debug HTML reflects new size
                    if hasattr(self, '_original_soup') and hasattr(block, 'bid'):
                        try:
                            node = self._original_soup.select_one(f'[data-bid="{block.bid}"]')
                            if node and node.name == 'img':
                                node['width'] = str(block.w)
                                node['height'] = str(block.h)
                        except Exception:
                            pass

                    if self.debug:
                        context = "column" if getattr(block, 'inColumn', None) == "true" else "full-width"
                        logger.info(f"🖼️  Auto-fit {block.src} ({context}): "
                                    f"{original_w}x{original_h} → {block.w}x{block.h} ({ratio*100:.1f}%)")
        
        return blocks

    def _generate_paginated_debug_html(self, pages: List[List[Block]], processed_html: str, temp_dir: str) -> str:
        """Generate HTML showing content split across actual slide pages."""
        
        # Get both theme CSS and HTML-specific styles (for columns, admonitions, etc.)
        theme_css = get_css(self.theme)
        from .layout_parser import HTML_SPECIFIC_CSS
        css_content = theme_css + "\n" + HTML_SPECIFIC_CSS

        html_parts = [
            "<!DOCTYPE html>",
            "<html lang=\"en\">",
            "<head>",
            "<meta charset=\"UTF-8\">",
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
            "<title>Paginated Slide Content</title>",
            "<style>",
            css_content,
            "/* list bullet helper for debug view will be injected later */",
            ".slide{margin-bottom:40px;border:3px solid red;position:relative;}",
            ".slide:before{position:absolute;top:-26px;left:0;background:red;color:#fff;padding:4px 8px;font-weight:bold;content:attr(data-idx);}",
            "</style>",
            "</head>",
            "<body>"
        ]

        # Build HTML based on the actual paginated blocks structure
        for page_idx, page_blocks in enumerate(pages, start=1):
            if not page_blocks:
                continue
                
            html_parts.append('<hr style="border:2px dashed #999;margin:40px 0;">')
            
            # Check if this is a divider slide
            is_divider = _is_divider_slide(page_blocks)
            slide_class = "slide divider" if is_divider else "slide"
            
            html_parts.append(f'<div class="{slide_class}" id="slide-{page_idx}" data-idx="{page_idx}">')
            
            # Use WYSIWYG slice – copy original DOM nodes for this page
            bids_this_page = [blk.bid for blk in page_blocks if hasattr(blk, 'bid')]
            page_html = self._slice_dom_for_page(bids_this_page)

            # ---- Beautify lists for debug view ----
            try:
                soup_page = BeautifulSoup(page_html, 'html.parser')
                for p in soup_page.select('p[data-list-levels]'):
                    levels = [int(x) for x in p['data-list-levels'].split(',')]
                    list_type = p.get('data-list-type', 'ul')
                    # counters per nesting level for ordered lists
                    counters = {}
                    raw_html = p.decode_contents()
                    # split on any <br>, <br/>, or <br /> (case-insensitive)
                    segments = [seg for seg in re.split(r'<br[^>]*>', raw_html, flags=re.IGNORECASE) if seg.strip()]
                    new_html_parts = []
                    for seg_idx, seg in enumerate(segments):
                        level = levels[seg_idx] if seg_idx < len(levels) else 0
                        if list_type == 'ol':
                            # update counter for this level
                            counters[level] = counters.get(level, 0) + 1
                            # reset deeper level counters
                            deeper = [k for k in counters.keys() if k > level]
                            for k in deeper:
                                del counters[k]
                            bullet = f"{counters[level]}."
                        else:
                            bullet = '•'
                        indent = 20 * level
                        new_html_parts.append(f'<span class="dbg-list" style="margin-left:{indent}px">{bullet}&nbsp;{seg.strip()}</span>')
                    p.clear()
                    p.append(BeautifulSoup(''.join(new_html_parts), 'html.parser'))
                page_html = str(soup_page)
            except Exception:
                pass

            html_parts.append(page_html)
            html_parts.append('</div>')  # close .slide

        # Small CSS for debug bullets
        # Update img src to point to embedded versions happened above.

        html_parts.extend([
            "<style>.dbg-list{display:block;text-indent:-1em;padding-left:1em;margin-left:20px;margin-top:0;margin-bottom:0;line-height:inherit;}</style>",
            "</body>", "</html>"])

        paginated_html = "\n".join(html_parts)

        # Embed images in the generated HTML
        soup_embed = BeautifulSoup(paginated_html, "html.parser")
        for img_tag in soup_embed.find_all("img"):
            src = img_tag.get("src", "")
            if src.startswith("data:"):
                continue  # already embedded
            # Resolve file path
            if src.startswith("file://"):
                file_path = src[7:]
            else:
                file_path = os.path.join(temp_dir or "", src)
                if not os.path.exists(file_path):
                    file_path = os.path.abspath(src)
            if not os.path.exists(file_path):
                continue
            try:
                mime, _ = mimetypes.guess_type(file_path)
                if not mime:
                    mime = "image/png"
                with open(file_path, "rb") as fh:
                    b64 = base64.b64encode(fh.read()).decode()
                img_tag["src"] = f"data:{mime};base64,{b64}"
            except Exception:
                pass

        paginated_html = str(soup_embed)

        return paginated_html
    
    def _slice_dom_for_page(self, bids):
        """Copy the minimal DOM subtrees that contain all bids, preserving wrappers
        like .columns/.column so the debug HTML matches the measured layout."""
        if not hasattr(self, '_original_soup') or self._original_soup is None:
            return ''

        src = self._original_soup
        copied_roots = []        # original nodes that will be deep-copied once
        copied_root_ids = set()  # use id() to avoid duplicates

        for bid in bids:
            if not bid:
                continue
            node = src.select_one(f'[data-bid="{bid}"]')
            if not node:
                continue

            # climb until parent is the slide container (has class "slide")
            anc = node
            while anc.parent and not (anc.parent.has_attr('class') and 'slide' in anc.parent['class']):
                anc = anc.parent

            # anc is now direct child of slide (or node itself if already)
            if id(anc) not in copied_root_ids:
                copied_roots.append(anc)
                copied_root_ids.add(id(anc))

        # Deep-copy each root to avoid mutating original soup
        html_parts = [str(root) for root in copied_roots]
        return '\n'.join(html_parts)