"""Layout engine for measuring HTML elements and pagination."""

import asyncio
import tempfile
import os
import json
from typing import List, Optional
from pathlib import Path
from pyppeteer import launch
from pptx.util import Inches
from .models import Block
from .markdown_parser import MarkdownParser
from .theme_loader import get_css


def paginate(blocks: List[Block], max_height_px: int = 540) -> List[List[Block]]:
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
    
    for block in blocks:
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
            
            # Calculate the relative position and bottom of this block
            relative_y = block.y - page_start_y
            relative_bottom = relative_y + block_height
            
            # If this block would extend beyond the page boundary, start new page
            if relative_bottom > max_height_px:
                should_start_new_page = True
        
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
        
        # Adjust all Y coordinates to start from a reasonable position (e.g., 40px for padding)
        page_top_margin = 40
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
    
    async def measure_layout(self, html_content, temp_dir=None):
        """Use Puppeteer to measure HTML element layout."""
        from pyppeteer import launch
        import tempfile
        import os
        from .theme_loader import get_css
        
        # Extract slide dimensions from CSS theme
        css_content = get_css(self.theme)
        
        # Parse CSS for slide dimensions
        import re
        width_match = re.search(r'--slide-width:\s*(\d+)px', css_content)
        height_match = re.search(r'--slide-height:\s*(\d+)px', css_content)
        
        if not width_match or not height_match:
            raise ValueError(f"❌ CSS theme '{self.theme}' missing slide dimensions. "
                           f"Add '--slide-width: XXXpx' and '--slide-height: XXXpx' to :root")
        
        viewport_width = int(width_match.group(1))
        viewport_height = int(height_match.group(1))
        
        browser = await launch()
        page = await browser.newPage()
        
        # Set viewport size to match CSS theme dimensions
        await page.setViewport({'width': viewport_width, 'height': viewport_height})
        
        # Set the HTML content
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
                
                // Skip empty elements and script tags
                if (!el.textContent.trim() || el.tagName.toLowerCase() === 'script' || el.tagName.toLowerCase() === 'style') {
                    return;
                }
                
                // Skip li elements - we'll process their parent ul/ol instead
                if (el.tagName.toLowerCase() === 'li') {
                    return;
                }
                
                // Skip elements that are children of elements we've already processed
                for (const parent of result) {
                    if (parent.element && parent.element.contains(el)) {
                        return;
                    }
                }
                
                const rect = el.getBoundingClientRect();
                const computedStyle = window.getComputedStyle(el);
                
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

                result.push({
                    tagName: el.tagName.toLowerCase(),
                    className: el.className,
                    textContent: textContent,
                    x: rect.left,
                    y: rect.top,
                    width: rect.width,
                    height: rect.height,
                    element: el,  // Store reference to the element for parent checking
                    parentTagName: el.parentElement ? el.parentElement.tagName.toLowerCase() : null,
                    parentClassName: el.parentElement ? el.parentElement.className : null,
                    tableColumnWidths: tableColumnWidths,  // Add column width information
                    style: {
                        fontSize: computedStyle.fontSize,
                        fontWeight: computedStyle.fontWeight,
                        fontStyle: computedStyle.fontStyle,
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
                });
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
            
            # Clear file names that indicate their purpose:
            # - measurement_debug_*.html = Layout measurement visualization with slide boundaries (for debugging)
            # - conversion_result_*.html = Final converted content ready for PowerPoint (for technical debugging)
            with open(output_dir / f"measurement_debug_{self.theme}.html", "w", encoding='utf-8') as f:
                f.write(html_content)
            with open(output_dir / f"conversion_result_{self.theme}.html", "w", encoding='utf-8') as f:
                f.write(processed_html)
        
        # Measure layout using Puppeteer on the processed HTML
        layout_info = asyncio.run(self.measure_layout(processed_html, temp_dir))
        
        # Save layout information for debugging
        with open(os.path.join(temp_dir, "layout_info.json"), "w") as f:
            json.dump(layout_info, f, indent=2)
        
        # Convert raw layout data to Block objects
        blocks = [Block.from_element(element) for element in layout_info]
        
        # Merge consecutive list items into text blocks
        blocks = self._merge_consecutive_lists(blocks)
        
        # --- Determine usable page height (slide height minus padding) ---
        css_content_for_height = get_css(self.theme)
        import re
        height_match2 = re.search(r'--slide-height:\s*(\d+)px', css_content_for_height)
        padding_match = re.search(r'\.slide\s*\{[^}]*padding:\s*(\d+)px', css_content_for_height, re.DOTALL)
        if height_match2:
            slide_height_px = int(height_match2.group(1))
        else:
            slide_height_px = page_height  # fallback
        padding_px = int(padding_match.group(1)) if padding_match else 0
        usable_height_px = slide_height_px - 2 * padding_px
        if usable_height_px <= 0:
            usable_height_px = slide_height_px  # safety
        
        # Paginate the blocks using usable height
        pages = paginate(blocks, usable_height_px)
        
        if self.debug:
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
        import re
        from html import unescape
        
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
            is_ordered = list_tag == 'ol'
            
            for i, (item_text, level) in enumerate(items_with_levels):
                # Clean the item content but preserve inline formatting
                clean_text = self._clean_html_for_measurement(item_text)
                
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
        
        return processed_html
    
    def _extract_list_items_with_levels(self, list_content, list_tag, base_level=0):
        """Extract list items with their nesting levels"""
        import re
        
        items_with_levels = []
        
        # Use a more robust approach: find top-level <li> tags only
        current_pos = 0
        depth = 0
        
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
        import re
        from html import unescape
        
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
        import re
        from html import unescape
        
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