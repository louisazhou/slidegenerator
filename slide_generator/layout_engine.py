"""Layout engine for measuring HTML elements and pagination."""

import asyncio
import tempfile
import os
import json
import re
from typing import List, Optional, Callable
from pathlib import Path
from PIL import Image
from html import unescape
from bs4 import BeautifulSoup

from .models import Block
from .markdown_parser import MarkdownParser
from .theme_loader import get_css


class CSSVariableReader:
    """Utility class to read CSS variables from theme files."""
    
    def __init__(self, theme: str = "default"):
        self.theme = theme
        self._variables = {}
        self._load_variables()
    
    def _load_variables(self):
        """Load CSS variables from the theme file."""
        css_content = get_css(self.theme)
        
        # Extract CSS variables from :root section
        root_match = re.search(r':root\s*\{([^}]+)\}', css_content, re.DOTALL)
        if not root_match:
            raise ValueError(f"No :root section found in theme '{self.theme}'")
        
        root_content = root_match.group(1)
        
        # Parse CSS variables
        variable_pattern = r'--([^:]+):\s*([^;]+);'
        for match in re.finditer(variable_pattern, root_content):
            var_name = match.group(1).strip()
            var_value = match.group(2).strip()
            self._variables[var_name] = var_value
    
    def get_px_value(self, variable_name: str) -> int:
        """Get a pixel value from CSS variable."""
        value = self._variables.get(variable_name)
        if not value:
            raise ValueError(f"CSS variable '--{variable_name}' not found in theme '{self.theme}'")
        
        # Extract pixel value
        px_match = re.search(r'(\d+)px', value)
        if not px_match:
            raise ValueError(f"CSS variable '--{variable_name}' is not a pixel value: {value}")
        
        return int(px_match.group(1))
    
    def get_value(self, variable_name: str) -> str:
        """Get raw CSS variable value."""
        value = self._variables.get(variable_name)
        if not value:
            raise ValueError(f"CSS variable '--{variable_name}' not found in theme '{self.theme}'")
        return value
    
    def get_column_gap(self) -> int:
        """Get column gap value from CSS variables."""
        return self.get_px_value('column-gap')
    
    def get_column_padding(self) -> int:
        """Get column padding value from CSS variables."""
        return self.get_px_value('column-padding')


class ImageScaler:
    """Utility class for consistent image scaling logic."""
    
    def __init__(self, css_reader: CSSVariableReader, debug: bool = False):
        self.css_reader = css_reader
        self.debug = debug
        
        # Cache frequently used values
        self.viewport_width = css_reader.get_px_value('slide-width')
        self.viewport_height = css_reader.get_px_value('slide-height')
        self.padding_px = css_reader.get_px_value('slide-padding')
        self.content_width = self.viewport_width - 2 * self.padding_px
        self.content_height = self.viewport_height - 2 * self.padding_px
        self.column_width = (self.content_width - css_reader.get_column_gap()) / 2
    
    def calculate_image_dimensions(self, image_path: str, scale_x: Optional[str] = None, 
                                 scale_y: Optional[str] = None, in_column: bool = False, parent_column_width: Optional[float] = None) -> tuple:
        """
        Calculate target image dimensions based on scaling parameters.
        
        Args:
            image_path: Path to the image file
            scale_x: X-axis scale factor (as string)
            scale_y: Y-axis scale factor (as string)  
            in_column: Whether the image is in a column layout
            
        Returns:
            Tuple of (target_width, target_height)
        """
        try:
            # Get original image dimensions
            with Image.open(image_path) as img:
                original_width, original_height = img.size
                aspect_ratio = original_width / original_height
        except Exception as e:
            if self.debug:
                print(f"⚠️ Could not read image dimensions for {image_path}: {e}")
            return None, None
        
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
        
        # Calculate target dimensions based on scaling
        if scale_x:
            scale_factor = float(scale_x)
            target_width = base_width * scale_factor
            target_height = target_width / aspect_ratio
            
            # Check if height exceeds boundaries
            if target_height > base_height:
                target_height = base_height * 0.95  # Leave margin
                target_width = target_height * aspect_ratio
                if self.debug:
                    context = "column" if in_column else "full-width"
                    print(f"📏 Image {image_path} height-constrained ({context}): {target_width:.0f}x{target_height:.0f}")
        
        elif scale_y:
            scale_factor = float(scale_y)
            target_height = base_height * scale_factor
            target_width = target_height * aspect_ratio
            
            # Check if width exceeds boundaries
            if target_width > base_width:
                target_width = base_width * 0.95  # Leave margin
                target_height = target_width / aspect_ratio
                if self.debug:
                    context = "column" if in_column else "full-width"
                    print(f"📏 Image {image_path} width-constrained ({context}): {target_width:.0f}x{target_height:.0f}")
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
    # group isn't split across slides. This specifically fixes the "Figures
    # Demo / Bar chart" slide where the combined height exceeded the limit by
    # just a few pixels.
    allowable = available_space * 1.10  # 10 % tolerance
    return group_height <= allowable

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
# Uncomment for debugging:
                # Debug code removed - pagination working correctly
                
                if rule.action == "break":
                    return True
                elif rule.action == "allow":
                    return False  # Explicit allow overrides other rules
        except Exception as e:
            # Log rule evaluation errors but don't break pagination
            print(f"Warning: Pagination rule '{rule.name}' failed: {e}")
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
    
    # Simple pagination with lookahead grouping
    processed_block_indices = set()  # Track which blocks have been processed as part of groups
    
    for i, block in enumerate(blocks):
        # Skip blocks that were already processed as part of a group
        if i in processed_block_indices:
            continue
        # Handle explicit page breaks
        if block.is_page_break():
            # Only add non-empty pages
            if current_page:
                pages.append(current_page)
            current_page = []
            page_start_y = None
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
    
    def __init__(self, debug: bool = False, theme: str = "default"):
        """Initialize the layout engine with theme support."""
        self.debug = debug
        self.theme = theme
        self.css_reader = CSSVariableReader(theme)
        self.image_scaler = ImageScaler(self.css_reader, debug)
    
    async def measure_layout(self, html_content, temp_dir=None):
        """Use Puppeteer to measure HTML element layout."""
        from pyppeteer import launch
        import os
        
        # Get slide dimensions from CSS theme
        viewport_width = self.css_reader.get_px_value('slide-width')
        viewport_height = self.css_reader.get_px_value('slide-height')
        
        # Copy images to temp directory (without scaling yet)
        if temp_dir:
            html_content = self._copy_images_for_measurement(html_content, temp_dir)
        
        browser = await launch()
        page = await browser.newPage()
        
        # Set viewport size to match CSS theme dimensions
        await page.setViewport({'width': viewport_width, 'height': viewport_height})
        
        # Write HTML to temp file and load it so images can be accessed
        if temp_dir:
            html_file_path = os.path.join(temp_dir, "measurement.html")
            with open(html_file_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Load from file so relative image URLs work
            await page.goto(f'file://{html_file_path}')
        else:
            # Fallback to setContent if no temp_dir (images may not work)
            await page.setContent(html_content)
        
        # Extract layout information for all elements
        layout_info = await page.evaluate('''() => {
            const elements = document.querySelectorAll('.slide *, .page-break');
            const result = [];
            
            Array.from(elements).forEach(el => {
                // Handle page breaks
                if (el.classList && el.classList.contains('page-break')) {
                    result.push({
                        tagName: 'div',
                        className: 'page-break',
                        textContent: '<!-- slide -->',
                        x: 0,
                        y: 0,
                        width: 0,
                        height: 0,
                        role: 'page_break'
                    });
                    return;
                }
                
                // Skip script/style elements entirely
                if (el.tagName.toLowerCase() === 'script' || el.tagName.toLowerCase() === 'style') {
                    return;
                }

                // Skip non-img elements that are empty
                if (el.tagName.toLowerCase() !== 'img' && !el.textContent.trim()) {
                    return;
                }
                
                // Skip li elements - we'll process their parent ul/ol instead
                if (el.tagName.toLowerCase() === 'li') {
                    return;
                }
                
                // Skip column container divs entirely - we only want their children
                if (el.className && (el.className.includes('columns') || el.className.includes('column'))) {
                    return;
                }
                
                // Skip elements that are children of elements we've already processed
                for (const parent of result) {
                    if (parent.element && parent.element.contains(el)) {
                        return; // skip - this element is a child of an already processed element
                    }
                }
                
                const rect = el.getBoundingClientRect();
                const computedStyle = window.getComputedStyle(el);
                
                // Include vertical margins for better pagination accuracy
                const marginTop = parseFloat(computedStyle.marginTop) || 0;
                const marginBottom = parseFloat(computedStyle.marginBottom) || 0;
                const adjustedHeight = rect.height + marginTop + marginBottom;
                
                // Get content, preserving HTML for inline formatting and data attributes
                let textContent;
                
                // For paragraph elements with data attributes, preserve the outer HTML
                if (el.tagName.toLowerCase() === 'p' && (el.hasAttribute('data-list-levels') || el.hasAttribute('data-list-type'))) {
                    textContent = el.outerHTML.trim();
                } else {
                    // For other elements, preserve innerHTML to keep formatting tags
                    textContent = el.innerHTML.trim();
                    
                    // If innerHTML is the same as textContent, use textContent to avoid unnecessary HTML
                    if (textContent === el.textContent.trim()) {
                        textContent = el.textContent.trim();
                    }
                }
                
                // Extract table column widths if this is a table
                let tableColumnWidths = null;
                if (el.tagName.toLowerCase() === 'table') {
                    const firstRow = el.querySelector('tr');
                    if (firstRow) {
                        const cells = firstRow.querySelectorAll('th, td');
                        tableColumnWidths = Array.from(cells).map(cell => {
                            const cellRect = cell.getBoundingClientRect();
                            return cellRect.width;
                        });
                    }
                }

                const item = {
                    tagName: el.tagName.toLowerCase(),
                    className: el.className,
                    textContent: textContent,
                    x: rect.left,
                    y: rect.top,
                    width: rect.width,
                    height: adjustedHeight,
                    element: el,  // Store reference to the element for parent checking
                    parentTagName: el.parentElement ? el.parentElement.tagName.toLowerCase() : null,
                    parentClassName: el.parentElement ? el.parentElement.className : null,
                    tableColumnWidths: tableColumnWidths,  // Add column width information
                    style: {
                        fontSize: computedStyle.fontSize,
                        fontWeight: computedStyle.fontWeight,
                        fontStyle: computedStyle.fontStyle,
                        lineHeight: computedStyle.lineHeight,
                        color: (() => {
                            const color = computedStyle.color;
                            const match = color.match(/rgb\\((\\d+), (\\d+), (\\d+)\\)/);
                            if (match) {
                                return {
                                    r: parseInt(match[1]),
                                    g: parseInt(match[2]),
                                    b: parseInt(match[3])
                                };
                            }
                            return null;
                        })(),
                        backgroundColor: (() => {
                            const bgColor = computedStyle.backgroundColor;
                            if (bgColor === 'rgba(0, 0, 0, 0)' || bgColor === 'transparent') {
                                return null;
                            }
                            const match = bgColor.match(/rgb\\((\\d+), (\\d+), (\\d+)\\)/);
                            if (match) {
                                return {
                                    r: parseInt(match[1]),
                                    g: parseInt(match[2]),
                                    b: parseInt(match[3])
                                };
                            }
                            return null;
                        })(),
                        textAlign: computedStyle.textAlign
                    }
                };

                // If this is an image, capture src attribute and scaling data
                if (el.tagName.toLowerCase() === 'img') {
                    const filepath = el.getAttribute('data-filepath');
                    item['src'] = filepath ? filepath : el.getAttribute('src');
                    
                    // Capture scaling data attributes for column-aware adjustments
                    const scaleX = el.getAttribute('data-scale-x');
                    const scaleY = el.getAttribute('data-scale-y');
                    const scaleType = el.getAttribute('data-scale-type');
                    const inColumn = el.getAttribute('data-in-column');
                    
                    if (scaleX) item['scaleX'] = scaleX;
                    if (scaleY) item['scaleY'] = scaleY;
                    if (scaleType) item['scaleType'] = scaleType;
                    if (inColumn) item['inColumn'] = inColumn;
                }

                // Capture parent column information (width + mode)
                const parentColumn = el.closest('.column');
                if (parentColumn) {
                    const colRect = parentColumn.getBoundingClientRect();
                    item['parentColumnWidth'] = colRect.width;
                    const mode = parentColumn.getAttribute('data-column-width');
                    if (mode) item['columnMode'] = mode;
                }

                // Capture unique bid stamped earlier
                const bid = el.getAttribute('data-bid');
                if (bid) item['bid'] = bid;

                result.push(item);
            });
            
            // Remove the element references before returning
            return result.map(item => {
                const { element, ...rest } = item;
                return rest;
            });
        }''')
        
        # Close the browser
        await browser.close()
        
        return layout_info
    
    def convert_markdown_to_html(self, markdown_text):
        """Convert markdown to HTML with layout CSS."""
        # Handle empty or whitespace-only content
        if not markdown_text or not markdown_text.strip():
            return ""
        
        # Use the new markdown parser
        parser = MarkdownParser()
        html_slides = parser.parse_with_page_breaks(markdown_text)
        
        # If no content slides, return empty string
        if not html_slides:
            return ""
        
        # Get CSS from theme system - use the configured theme
        css = get_css(self.theme)
        
        # Combine HTML slides with proper UTF-8 document structure
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Slide Content</title>
<style>
{css}
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
    
    def measure_and_paginate(self, markdown_text: str, page_height: int = 540, temp_dir: Optional[str] = None) -> List[List[Block]]:
        """
        Convert markdown to HTML, measure layout, and return paginated Block objects.
        
        Args:
            markdown_text: Markdown content to process
            page_height: Maximum height in pixels for a single slide
            temp_dir: Optional directory for debug files
            
        Returns:
            List of pages, where each page is a list of Block objects
        """
        # Handle empty or whitespace-only content
        if not markdown_text or not markdown_text.strip():
            return []
        
        # Convert markdown to HTML
        html_content = self.convert_markdown_to_html(markdown_text)
        
        # If no HTML content was generated, return empty list
        if not html_content:
            return []
        
        # Create a temporary directory for debug files if not provided
        if temp_dir is None:
            temp_dir = tempfile.mkdtemp()
            if self.debug:
                print(f"Debug files will be saved to: {temp_dir}")
        
        # Store temp_dir for image processing
        self._current_temp_dir = temp_dir
        
        # Preprocess HTML to match what will be rendered in PowerPoint
        processed_html = self._preprocess_html_for_measurement(html_content)
        
        # Save the HTML content to a file for debugging
        with open(os.path.join(temp_dir, "input.html"), "w", encoding='utf-8') as f:
            f.write(html_content)
        with open(os.path.join(temp_dir, "processed.html"), "w", encoding='utf-8') as f:
            f.write(processed_html)
        
        # Also save to output directory for easy access
        if self.debug:
            # Use absolute path to workspace root output directory (NOT relative to script location)
            # This ensures consistent behavior regardless of execution directory
            current_working_dir = Path.cwd()
            output_dir = current_working_dir / "output"
            output_dir.mkdir(exist_ok=True)
            
            # Images remain in their original locations (examples/assets/)
            
            # Clear file names that indicate their purpose:
            # - conversion_result_*.html = Final converted content ready for PowerPoint (for technical debugging)
            with open(output_dir / f"conversion_result_{self.theme}.html", "w", encoding='utf-8') as f:
                f.write(processed_html)
        
        # Measure layout using Puppeteer on the processed HTML
        layout_info = asyncio.run(self.measure_layout(processed_html, temp_dir))
        
        # Save layout information for debugging
        with open(os.path.join(temp_dir, "layout_info.json"), "w") as f:
            json.dump(layout_info, f, indent=2)
        
        # Convert raw layout data to Block objects
        blocks = [Block.from_element(element) for element in layout_info]
        
        # Apply intelligent image scaling based on column context
        blocks = self._apply_intelligent_image_scaling_to_blocks(blocks, temp_dir)
        
        # Merge consecutive list items into text blocks
        blocks = self._merge_consecutive_lists(blocks)
        
        # --- Determine usable page height (slide height minus padding) ---
        slide_height_px = page_height if page_height else self.css_reader.get_px_value('slide-height')
        padding_px = self.css_reader.get_px_value('slide-padding')
        
        usable_height_px = slide_height_px - 2 * padding_px
        if usable_height_px <= 0:
            raise ValueError(f"❌ CSS theme '{self.theme}' has invalid dimensions: "
                           f"slide height {slide_height_px}px minus 2×{padding_px}px padding = {usable_height_px}px")
        
        # Paginate the blocks using usable height
        pages = paginate(blocks, usable_height_px, padding_px)
        
        # Generate paginated debug HTML to show actual slide structure
        if self.debug:
            paginated_html = self._generate_paginated_debug_html(pages, processed_html, temp_dir)
            
            # Save to output directory for easy viewing
            current_working_dir = Path.cwd()
            output_dir = current_working_dir / "output"
            output_dir.mkdir(exist_ok=True)
            
            with open(output_dir / f"paginated_slides_{self.theme}.html", "w", encoding='utf-8') as f:
                f.write(paginated_html)
                
            print(f"📄 Generated paginated HTML: output/paginated_slides_{self.theme}.html")
            print(f"Layout engine created {len(pages)} pages:")
            for i, page in enumerate(pages):
                print(f"  Page {i+1}: {len(page)} blocks (height limit: {usable_height_px}px)")
                for j, block in enumerate(page):
                    oversized_flag = " [OVERSIZED]" if hasattr(block, 'oversized') and block.oversized else ""
                    print(f"    Block {j+1}: {block.tag} ({block.height}px) - '{block.content[:30]}...'{oversized_flag}")
        
        return pages 

    def _preprocess_html_for_measurement(self, html_content):
        """
        Preprocess HTML content to match what will actually be rendered in PowerPoint.
        This ensures the browser measures the same content that will be displayed.
        """
        
        # FIRST: Prepare images for measurement (copy to temp dir and fix URLs)
        # This must be done BEFORE any other processing to ensure images display correctly
        temp_dir = getattr(self, '_current_temp_dir', None)
        if temp_dir:
            html_content = self._prepare_images_for_measurement(html_content, temp_dir)
        
        def process_list_content(match):
            """Process a single list (ul or ol) and convert to formatted text with level information"""
            list_tag = match.group(1).lower()  # 'ul' or 'ol'
            list_content = match.group(2)
            
            # Extract list items with their nested structure
            items_with_levels = self._extract_list_items_with_levels(list_content, list_tag)
            
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
        
        # Keep processing until no more top-level lists are found
        max_iterations = 50  # Increased limit for complex documents with many lists
        iteration = 0
        
        if self.debug:
            initial_list_count = len(re.findall(r'<(ul|ol)[^>]*>', processed_html, flags=re.IGNORECASE))
            print(f"🔄 Processing {initial_list_count} lists in HTML document...")
        
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
            # Skip page-break markers – they are separate divs we already handle
            if el.has_attr('data-bid'):
                continue
            el['data-bid'] = f'b{bid_counter}'
            bid_counter += 1

        # Save pristine soup for later DOM slicing in debug HTML
        self._original_soup = soup

        return str(soup)
    
    def _extract_list_items_with_levels(self, list_content, list_tag, base_level=0):
        """Extract list items with their nesting levels"""
        import re
        
        items_with_levels = []
        
        # Use a more robust approach: find top-level <li> tags only
        current_pos = 0
        
        while current_pos < len(list_content):
            # Find next <li> or </li> tag
            li_open_match = re.search(r'<li(?:[^>]*)>', list_content[current_pos:])
            li_close_match = re.search(r'</li>', list_content[current_pos:])
            
            if not li_open_match:
                break
                
            # Start of <li> tag
            li_start = current_pos + li_open_match.start()
            li_content_start = current_pos + li_open_match.end()
            
            # Find the matching closing </li> by tracking depth
            search_pos = li_content_start
            li_depth = 1
            
            while search_pos < len(list_content) and li_depth > 0:
                # Look for next <li> or </li>
                next_open = re.search(r'<li(?:[^>]*)>', list_content[search_pos:])
                next_close = re.search(r'</li>', list_content[search_pos:])
                
                if next_close and (not next_open or next_close.start() < next_open.start()):
                    # Found closing tag first
                    li_depth -= 1
                    if li_depth == 0:
                        # This is our matching closing tag
                        li_content_end = search_pos + next_close.start()
                        break
                    search_pos += next_close.end()
                elif next_open:
                    # Found opening tag first
                    li_depth += 1
                    search_pos += next_open.end()
                else:
                    # No more tags found
                    li_content_end = len(list_content)
                    break
            else:
                # Reached end without finding closing tag
                li_content_end = len(list_content)
            
            # Extract the content of this <li> item
            item_content = list_content[li_content_start:li_content_end]
            
            # Check if this item contains nested lists
            nested_list_pattern = r'<(ul|ol)[^>]*>(.*?)</\1>'
            nested_matches = list(re.finditer(nested_list_pattern, item_content, re.DOTALL | re.IGNORECASE))
            
            if nested_matches:
                # Extract text before the first nested list
                first_nested_start = nested_matches[0].start()
                text_before_nested = item_content[:first_nested_start]
                
                # Clean and add the text content if not empty
                text_content = self._clean_html_for_measurement(text_before_nested)
                if text_content.strip():
                    items_with_levels.append((text_content, base_level))
                
                # Process each nested list
                for nested_match in nested_matches:
                    nested_tag = nested_match.group(1).lower()
                    nested_content = nested_match.group(2)
                    nested_items = self._extract_list_items_with_levels(nested_content, nested_tag, base_level + 1)
                    items_with_levels.extend(nested_items)
            else:
                # Simple item without nesting
                text_content = self._clean_html_for_measurement(item_content)
                if text_content.strip():
                    items_with_levels.append((text_content, base_level))
            
            # Move to after this </li> tag - advance position  
            if li_depth == 0 and 'next_close' in locals():
                current_pos = search_pos + next_close.end()
            else:
                current_pos = len(list_content)  # End if we couldn't find proper closing
            
        return items_with_levels

    def _clean_html_for_measurement_preserve_lists(self, text):
        """Clean HTML tags but preserve inline formatting and list structure for measurement."""
        
        # First, handle inline formatting tags that we want to preserve
        # Convert them to a temporary format
        text = re.sub(r'<(strong|b)(?:[^>]*)>(.*?)</\1>', r'**\2**', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<(em|i)(?:[^>]*)>(.*?)</\1>', r'*\2*', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<code(?:[^>]*)>(.*?)</code>', r'`\1`', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<mark(?:[^>]*)>(.*?)</mark>', r'==\1==', text, flags=re.IGNORECASE | re.DOTALL)
        
        # Handle nested lists by converting them to indented text
        def convert_nested_list(match):
            list_tag = match.group(1).lower()
            list_content = match.group(2)
            
            # Extract nested list items
            nested_items = re.findall(r'<li[^>]*>(.*?)</li>', list_content, re.DOTALL | re.IGNORECASE)
            
            if not nested_items:
                return ""
            
            # Format nested items with additional indentation
            formatted_nested = []
            is_ordered = list_tag == 'ol'
            
            for i, item in enumerate(nested_items):
                # Clean the nested item
                clean_item = self._clean_html_for_measurement(item)
                if is_ordered:
                    formatted_nested.append(f"    {i + 1}. {clean_item}")
                else:
                    formatted_nested.append(f"    • {clean_item}")
            
            return '<br>' + '<br>'.join(formatted_nested)
        
        # Convert nested lists to indented text
        text = re.sub(r'<(ul|ol)[^>]*>(.*?)</\1>', convert_nested_list, text, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove any remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Convert back to HTML formatting tags
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
        text = re.sub(r'==(.*?)==', r'<mark>\1</mark>', text)
        
        return unescape(text)

    def _clean_html_for_measurement(self, text):
        """Clean HTML tags but preserve inline formatting for measurement."""
        
        # First, handle inline formatting tags that we want to preserve
        # Convert them to a temporary format
        text = re.sub(r'<(strong|b)(?:[^>]*)>(.*?)</\1>', r'**\2**', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<(em|i)(?:[^>]*)>(.*?)</\1>', r'*\2*', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<code(?:[^>]*)>(.*?)</code>', r'`\1`', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<mark(?:[^>]*)>(.*?)</mark>', r'==\1==', text, flags=re.IGNORECASE | re.DOTALL)
        
        # Remove all other HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
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

 
    
    def _copy_images_for_measurement(self, html_content: str, temp_dir: str) -> str:
        """
        Copy images to temp directory and convert file:// URLs to relative URLs.
        Image scaling happens later after browser measurement.
        """
        import re
        import os
        import shutil
        
        # Find all file:// image URLs
        pattern = r'src="file://([^"]*)"'
        matches = re.finditer(pattern, html_content)
        
        # Process each image
        updated_html = html_content
        for match in matches:
            file_path = match.group(1)
            
            if os.path.exists(file_path):
                # Copy image to temp directory
                filename = os.path.basename(file_path)
                temp_image_path = os.path.join(temp_dir, filename)
                
                try:
                    shutil.copy2(file_path, temp_image_path)
                    
                    # Replace file:// URL with relative URL (no scaling yet)
                    old_src = f'src="file://{file_path}"'
                    new_src = f'src="{filename}"'
                    updated_html = updated_html.replace(old_src, new_src)
                    
                    if self.debug:
                        print(f"📸 Copied image: {filename} -> {temp_image_path}")
                        
                except Exception as e:
                    if self.debug:
                        print(f"⚠️ Failed to copy image {file_path}: {e}")
            else:
                if self.debug:
                    print(f"⚠️ Image file not found: {file_path}")
        
        return updated_html

    def _prepare_images_for_measurement(self, html_content: str, temp_dir: str) -> str:
        """
        Copy image files to temp directory and convert file:// URLs to relative URLs
        so the browser can access them for proper dimension measurement.
        Image scaling happens later after browser measurement.
        """
        return self._copy_images_for_measurement(html_content, temp_dir)



    def _apply_intelligent_image_scaling_to_blocks(self, blocks: List[Block], temp_dir: str) -> List[Block]:
        """
        Apply intelligent image scaling to Block objects based on their scaling attributes.
        This is called after browser measurement captures the scaling data.
        """
        if self.debug:
            print(f"🔍 Applying intelligent image scaling to {len(blocks)} blocks...")
        
        for block in blocks:
            if block.is_image() and hasattr(block, 'src'):
                # Check if this block has scaling information
                scale_x = getattr(block, 'scaleX', None)
                scale_y = getattr(block, 'scaleY', None)
                in_column = getattr(block, 'inColumn', None) == 'true'
                
                if scale_x or scale_y:
                    # Use ImageScaler to calculate correct dimensions
                    parent_col_width = getattr(block, 'parentColumnWidth', None)
                    target_width, target_height = self.image_scaler.calculate_image_dimensions(
                        block.src, scale_x, scale_y, in_column=in_column, parent_column_width=parent_col_width
                    )
                    
                    if target_width is not None and target_height is not None:
                        old_dims = f"{block.width}x{block.height}"
                        
                        # ------------------------------------------------------------------
                        # NEW: Clamp image height to remaining vertical space on the slide
                        # ------------------------------------------------------------------
                        try:
                            # Total inner slide height (viewport minus padding)
                            slide_inner_h = self.image_scaler.content_height  # px
                            
                            # Vertical space until slide bottom
                            remaining_h = max(0, slide_inner_h - block.y)
                            
                            # How much vertical space is left until either slide bottom or the next block
                            next_block_y = None
                            for other in blocks:
                                if other is block:
                                    continue
                                if other.y > block.y:
                                    next_block_y = other.y if next_block_y is None else min(next_block_y, other.y)
                            if next_block_y is not None:
                                remaining_h = min(remaining_h, next_block_y - block.y)
                            
                            # Leave a small margin (same 5 % used elsewhere)
                            max_allowed_h = remaining_h * 0.95
                            if target_height > max_allowed_h and max_allowed_h > 0:
                                # Shrink proportionally so aspect ratio is kept
                                shrink_factor = max_allowed_h / target_height
                                target_height = max_allowed_h
                                target_width = target_width * shrink_factor
                                if self.debug:
                                    print(f"↕️  Clamped image {block.src} to remaining space: {target_width:.0f}x{target_height:.0f} (remaining {remaining_h:.0f}px)")
                        except Exception as e:
                            # In debug mode report but continue gracefully
                            if self.debug:
                                print(f"⚠️  Failed to clamp image height for {block.src}: {e}")
                        
                        # --------------------------------------------------
                        # HORIZONTAL CLAMP (symmetry with vertical logic)
                        # --------------------------------------------------
                        try:
                            if in_column and parent_col_width:
                                avail_w = float(parent_col_width) - (block.x if block.x else 0)
                            else:
                                avail_w = self.image_scaler.content_width - block.x

                            avail_w = max(0, avail_w * 0.95)  # 5% safety margin

                            if target_width > avail_w and avail_w > 0:
                                shrink_factor = avail_w / target_width
                                target_width = avail_w
                                target_height = target_height * shrink_factor
                                if self.debug:
                                    print(f"↔️  Clamped image {block.src} to available width: {target_width:.0f}x{target_height:.0f} (avail {avail_w:.0f}px)")
                        except Exception as e:
                            if self.debug:
                                print(f"⚠️  Failed horizontal clamp for {block.src}: {e}")
                        
                        # Update block dimensions
                        block.w = int(target_width)
                        block.h = int(target_height)
                        
                        context = "column" if in_column else "full-width"
                        if self.debug:
                            print(f"📐 Scaled block {block.src}: {old_dims} -> {target_width:.0f}x{target_height:.0f} ({context})")
                    elif self.debug:
                        print(f"⚠️ Failed to calculate dimensions for {block.src}")
                elif self.debug and block.is_image():
                    print(f"📍 Image block {block.src} has no scaling data")
        
        return blocks

    def _generate_paginated_debug_html(self, pages: List[List[Block]], processed_html: str, temp_dir: str) -> str:
        """Generate HTML showing content split across actual slide pages."""
        
        css_content = get_css(self.theme)

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
            html_parts.append(f'<div class="slide" id="slide-{page_idx}" data-idx="{page_idx}">')
            
            # Use WYSIWYG slice – copy original DOM nodes for this page
            bids_this_page = [blk.bid for blk in page_blocks if hasattr(blk, 'bid')]
            page_html = self._slice_dom_for_page(bids_this_page)

            # ---- Beautify lists for debug view ----
            try:
                from bs4 import BeautifulSoup as _BS
                soup_page = _BS(page_html, 'html.parser')
                for p in soup_page.select('p[data-list-levels]'):
                    levels = [int(x) for x in p['data-list-levels'].split(',')]
                    list_type = p.get('data-list-type', 'ul')
                    # counters per nesting level for ordered lists
                    counters = {}
                    import re as _re
                    raw_html = p.decode_contents()
                    # split on any <br>, <br/>, or <br /> (case-insensitive)
                    segments = [seg for seg in _re.split(r'<br[^>]*>', raw_html, flags=_re.IGNORECASE) if seg.strip()]
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
                    p.append(_BS(''.join(new_html_parts), 'html.parser'))
                page_html = str(soup_page)
            except Exception:
                pass

            html_parts.append(page_html)
            html_parts.append('</div>')  # close .slide

        # Small CSS for debug bullets
        html_parts.extend([
            "<style>.dbg-list{display:block;text-indent:-1em;padding-left:1em;margin-left:20px;margin-top:0;margin-bottom:0;line-height:inherit;}</style>",
            "</body>", "</html>"])

        paginated_html = "\n".join(html_parts)

        # Copy images used in this HTML from temp_dir to output/debug_assets
        if temp_dir:
            import os, shutil, re
            output_dir = Path.cwd() / "output" / "debug_assets"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Find all <img src="..."> paths in HTML
            for match in re.finditer(r'<img[^>]+src="([^">]+)"', paginated_html):
                src = match.group(1)
                # Only copy if src is a simple filename (no path separators)
                if src and not any(sep in src for sep in ['/', '\\']):
                    src_path = os.path.join(temp_dir, src)
                    if os.path.exists(src_path):
                        dest_path = output_dir / src
                        try:
                            shutil.copy2(src_path, dest_path)
                        except Exception:
                            pass

            # Update img src to point to debug_assets folder relative path
            paginated_html = paginated_html.replace('src="', 'src="debug_assets/')

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