"""Layout engine for measuring HTML elements and pagination."""
import tempfile
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
                    print(f"📏 Image {image_path} height-constrained ({context}): {target_width:.0f}x{target_height:.0f}")
        
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
        
        # Always use structured pptx-box parser
        from .layout_parser import parse_html_with_structured_layout
        
        if self.debug:
            print("🏗️  Using structured pptx-box parser")
        
        import asyncio
        loop = asyncio.get_event_loop()
        blocks = loop.run_until_complete(
            parse_html_with_structured_layout(
                html_content, 
                theme=self.theme, 
                temp_dir=temp_dir, 
                debug=self.debug
            )
        )
        
        if self.debug:
            print(f"🧱 Structured parser created {len(blocks)} Block objects")
        
        # Set up _original_soup for debug HTML generation and add bid attributes
        # Use the same BID assignment logic as legacy preprocessing
        processed_html_for_bids = self._preprocess_html_for_measurement(html_content)
        from bs4 import BeautifulSoup
        self._original_soup = BeautifulSoup(processed_html_for_bids, 'html.parser')
        
        # Re-run structured parser with properly preprocessed HTML
        import asyncio
        loop = asyncio.get_event_loop()
        blocks = loop.run_until_complete(
            parse_html_with_structured_layout(
                processed_html_for_bids, 
                theme=self.theme, 
                temp_dir=temp_dir, 
                debug=self.debug
            )
        )
        
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
            # Debug HTML is simply the original HTML content after preprocessing
            debug_html = html_content
            paginated_html = self._generate_paginated_debug_html(pages, debug_html, temp_dir)
            
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
            html_content = self._copy_images_for_measurement(html_content, temp_dir)
        
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
            print(f"🔍 Applying intelligent image scaling to {len(blocks)} blocks...")
        
        # Track pagination context for accurate height constraints
        usable_height = self.css_reader.get_px_value('slide-height') - 2 * self.css_reader.get_px_value('slide-padding')
        current_page_height = 0
        
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
                            from PIL import Image
                            try:
                                with Image.open(block.src) as img:
                                    original_width, original_height = img.size
                                    aspect_ratio = original_width / original_height
                                    
                                    # Use 70% of slide height as maximum, not available height
                                    final_height = max_reasonable_height
                                    final_width = final_height * aspect_ratio
                                    
                                    if self.debug:
                                        original_scale = float(scale_x) if scale_x else float(scale_y)
                                        new_scale = final_width / (self.image_scaler.content_width * (1 if not in_column else 0.5))
                                        print(f"📐 Height-constrained scaling for {block.src}:")
                                        print(f"   Original request: {original_scale*100}% -> {initial_width:.0f}x{initial_height:.0f}")
                                        print(f"   Max reasonable height: {max_reasonable_height:.0f}px")
                                        print(f"   Adjusted to: {new_scale*100:.1f}% -> {final_width:.0f}x{final_height:.0f}")
                            except Exception as e:
                                if self.debug:
                                    print(f"⚠️ Could not load image {block.src} for aspect ratio: {e}")
                                # Fallback: use requested size but warn about potential overflow
                                final_width = initial_width
                                final_height = initial_height
                        elif self.debug:
                            # Image fits reasonably within slide bounds
                            print(f"📐 Keeping original scale for {block.src}: {final_width:.0f}x{final_height:.0f} (within {max_reasonable_height:.0f}px limit)")
                        
                        # STEP 6: Update block dimensions with final calculated values
                        old_dims = f"{block.width}x{block.height}"
                        block.w = int(final_width)
                        block.h = int(final_height)
                        
                        context = "column" if in_column else "full-width"
                        constraint_type = "height-constrained" if initial_height > max_reasonable_height else "original-scale"
                        if self.debug:
                            print(f"📐 Scaled block {block.src}: {old_dims} -> {final_width:.0f}x{final_height:.0f} ({context}, {constraint_type})")
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
            
            # Track which images we've copied
            copied_images = {}

            # Find all <img> tags in HTML and extract src and data-filepath
            for match in re.finditer(r'<img[^>]+', paginated_html):
                img_tag = match.group(0)
                
                # Extract src and data-filepath attributes
                src_match = re.search(r'src="([^"]+)"', img_tag)
                filepath_match = re.search(r'data-filepath="([^"]+)"', img_tag)
                
                if src_match:
                    src = src_match.group(1)
                    original_filepath = filepath_match.group(1) if filepath_match else None
                    
                    # Determine the source file to copy
                    source_file = None
                    filename = None
                    
                    if src.startswith('file://'):
                        # Extract path from file:// URL
                        file_path = src[7:]  # Remove 'file://' prefix
                        if os.path.exists(file_path):
                            source_file = file_path
                            filename = os.path.basename(file_path)
                    elif original_filepath and os.path.exists(original_filepath):
                        # Use the original filepath
                        source_file = original_filepath
                        filename = os.path.basename(original_filepath)
                    elif not any(sep in src for sep in ['/', '\\']):
                        # Simple filename, check in temp_dir
                        temp_file = os.path.join(temp_dir, src)
                        if os.path.exists(temp_file):
                            source_file = temp_file
                            filename = src
                    
                    # Copy the file if we found a valid source and haven't copied it yet
                    if source_file and filename and filename not in copied_images:
                        dest_path = output_dir / filename
                        try:
                            shutil.copy2(source_file, dest_path)
                            copied_images[filename] = str(dest_path)
                            if self.debug:
                                print(f"📁 Copied image for debug HTML: {filename}")
                        except Exception as e:
                            if self.debug:
                                print(f"⚠️ Failed to copy image {filename}: {e}")

            # Update img src to point to debug_assets folder
            def fix_img_src(match):
                full_match = match.group(0)
                src = match.group(1)
                
                # Handle different types of src attributes
                if src.startswith('file://'):
                    # Extract filename from file:// URL
                    file_path = src[7:]
                    filename = os.path.basename(file_path)
                    if filename in copied_images:
                        return full_match.replace(f'src="{src}"', f'src="debug_assets/{filename}"')
                elif not any(sep in src for sep in ['/', '\\']) and not src.startswith('debug_assets/'):
                    # Simple filename that should be in debug_assets
                    return full_match.replace(f'src="{src}"', f'src="debug_assets/{src}"')
                
                return full_match
                    
            paginated_html = re.sub(r'src="([^"]*)"', fix_img_src, paginated_html)

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