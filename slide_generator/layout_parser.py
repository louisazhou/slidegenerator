#!/usr/bin/env python3
"""
Layout parser for converting HTML to Block objects with precise measurements.
"""

import json
import logging
import os
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup

from .models import Block
from .theme_loader import get_css

logger = logging.getLogger(__name__)


class StructuredLayoutParser:
    """
    Parser that uses pptx-box approach for structured HTML parsing.
    
    This eliminates most regex parsing by having Puppeteer wrap elements
    in structured containers with layout data, then using BeautifulSoup
    to extract this information.
    """
    
    def __init__(self, theme: str = "default", debug: bool = False):
        self.theme = theme
        self.debug = debug
        self._load_theme_variables()
    
    def _load_theme_variables(self):
        """Load CSS variables from theme for layout calculations."""
        css_content = get_css(self.theme)
        
        # Extract CSS variables from :root section
        import re
        root_match = re.search(r':root\s*\{([^}]+)\}', css_content, re.DOTALL)
        if not root_match:
            raise ValueError(f"No :root section found in theme '{self.theme}'")
        
        root_content = root_match.group(1)
        
        # Parse CSS variables
        self._css_vars = {}
        variable_pattern = r'--([^:]+):\s*([^;]+);'
        for match in re.finditer(variable_pattern, root_content):
            var_name = match.group(1).strip()
            var_value = match.group(2).strip()
            self._css_vars[var_name] = var_value
    
    def _get_px_value(self, var_name: str) -> int:
        """Get pixel value from CSS variable."""
        value = self._css_vars.get(var_name)
        if not value:
            raise ValueError(f"CSS variable '--{var_name}' not found")
        
        import re
        px_match = re.search(r'(\d+)px', value)
        if not px_match:
            raise ValueError(f"CSS variable '--{var_name}' is not a pixel value: {value}")
        
        return int(px_match.group(1))
    
    async def parse_html_with_layout(self, html_content: str, temp_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Parse HTML using the pptx-box approach.
        
        Args:
            html_content: HTML content to parse
            temp_dir: Temporary directory for files
            
        Returns:
            List of structured layout elements
        """
        from pyppeteer import launch
        
        # Get slide dimensions from CSS theme
        viewport_width = self._get_px_value('slide-width')
        viewport_height = self._get_px_value('slide-height')
        
        # Copy images to temp directory if needed
        if temp_dir:
            html_content = self._copy_images_for_measurement(html_content, temp_dir)
        
        browser = await launch()
        page = await browser.newPage()
        
        # Set viewport size to match CSS theme dimensions
        await page.setViewport({'width': viewport_width, 'height': viewport_height})
        
        # Write HTML to temp file and load it
        if temp_dir:
            html_file_path = os.path.join(temp_dir, "structured_layout.html")
            with open(html_file_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            await page.goto(f'file://{html_file_path}')
        else:
            await page.setContent(html_content)
        
        # Inject JavaScript to wrap elements in pptx-box containers
        await page.evaluate(self._get_pptx_box_wrapper_script())
        
        # Get the modified HTML with pptx-box wrappers
        structured_html = await page.content()
        
        await browser.close()
        
        # Parse the structured HTML using BeautifulSoup
        return self._parse_structured_html(structured_html)
    
    def _get_pptx_box_wrapper_script(self) -> str:
        """
        JavaScript code to wrap HTML elements in pptx-box containers.
        
        This script identifies renderable elements and wraps them with
        structured containers containing layout data.
        """
        return """
        () => {
            let boxId = 0;
            
            // Helper to generate unique box IDs
            function getNextBoxId() {
                return 'pptx-box-' + (boxId++);
            }
            
            // Helper to determine element type
            function getElementType(el) {
                const tagName = el.tagName.toLowerCase();
                
                // Handle preprocessed lists (from legacy _preprocess_html_for_measurement)
                if (tagName === 'p' && el.hasAttribute('data-list-levels')) {
                    return 'list';
                }
                
                if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(tagName)) {
                    return 'heading';
                }
                if (tagName === 'img') {
                    return 'image';
                }
                if (tagName === 'table') {
                    return 'table';
                }
                if (['ul', 'ol'].includes(tagName)) {
                    return 'list';
                }
                if (tagName === 'blockquote') {
                    return 'quote';
                }
                if (tagName === 'pre') {
                    return 'code';
                }
                return 'text';
            }
            
            // Helper to extract style information
            function extractStyleInfo(el) {
                const computedStyle = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                
                // Include margins for accurate spacing
                const marginTop = parseFloat(computedStyle.marginTop) || 0;
                const marginBottom = parseFloat(computedStyle.marginBottom) || 0;
                const adjustedHeight = rect.height + marginTop + marginBottom;
                
                return {
                    x: rect.left,
                    y: rect.top,
                    width: rect.width,
                    height: adjustedHeight,
                    fontSize: computedStyle.fontSize,
                    fontWeight: computedStyle.fontWeight,
                    fontStyle: computedStyle.fontStyle,
                    textAlign: computedStyle.textAlign,
                    color: computedStyle.color,
                    backgroundColor: computedStyle.backgroundColor,
                    lineHeight: computedStyle.lineHeight
                };
            }
            
            // Helper to extract content with formatting preserved
            function extractContent(el) {
                const tagName = el.tagName.toLowerCase();
                
                if (tagName === 'img') {
                    return {
                        type: 'image',
                        src: el.getAttribute('data-filepath') || el.getAttribute('src'),
                        alt: el.getAttribute('alt') || '',
                        scaleX: el.getAttribute('data-scale-x'),
                        scaleY: el.getAttribute('data-scale-y'),
                        scaleType: el.getAttribute('data-scale-type'),
                        inColumn: el.getAttribute('data-in-column'),
                        html: el.outerHTML,  // Preserve full HTML with all attributes
                        originalTag: tagName  // Preserve original tag
                    };
                }
                
                if (tagName === 'table') {
                    // Extract table structure
                    const rows = Array.from(el.querySelectorAll('tr')).map(row => {
                        return Array.from(row.querySelectorAll('th, td')).map(cell => ({
                            content: cell.innerHTML.trim(),
                            isHeader: cell.tagName.toLowerCase() === 'th'
                        }));
                    });
                    
                    // Calculate column widths (matching legacy behavior)
                    let tableColumnWidths = null;
                    const firstRow = el.querySelector('tr');
                    if (firstRow) {
                        const cells = firstRow.querySelectorAll('th, td');
                        tableColumnWidths = Array.from(cells).map(cell => {
                            const rect = cell.getBoundingClientRect();
                            return rect.width;
                        });
                    }
                    
                    return {
                        type: 'table',
                        rows: rows,
                        html: el.outerHTML,
                        originalTag: tagName,  // Preserve original tag
                        tableColumnWidths: tableColumnWidths  // Add column width information
                    };
                }
                
                // Handle preprocessed lists (legacy format from _preprocess_html_for_measurement)
                if (tagName === 'p' && el.hasAttribute('data-list-levels')) {
                    const listType = el.getAttribute('data-list-type') || 'ul';
                    const levels = el.getAttribute('data-list-levels').split(',').map(l => parseInt(l));
                    const innerHTML = el.innerHTML;
                    
                    // Split content by <br> tags to get individual items
                    const segments = innerHTML.split(/<br[^>]*>/i).filter(s => s.trim());
                    const items = [];
                    
                    for (let i = 0; i < segments.length && i < levels.length; i++) {
                        const level = levels[i] || 0;
                        const content = segments[i].trim();
                        items.push({
                            level: level,
                            content: content,
                            text: content.replace(/<[^>]*>/g, '').trim()
                        });
                    }
                    
                    return {
                        type: 'list',
                        listType: listType,
                        items: items,
                        html: el.outerHTML,
                        originalTag: tagName  // Preserve original tag
                    };
                }
                
                // Handle regular lists (ol/ul structure)
                if (tagName === 'ul' || tagName === 'ol') {
                    // Extract list items with proper nesting level calculation
                    const items = [];
                    
                    // Helper function to recursively extract list items with correct levels
                    function extractListItems(listEl, baseLevel = 0) {
                        const directItems = Array.from(listEl.children).filter(child => 
                            child.tagName.toLowerCase() === 'li'
                        );
                        
                        directItems.forEach(li => {
                            // Get the text content without nested lists
                            let itemContent = '';
                            let itemText = '';
                            
                            // Clone the li element to manipulate
                            const liClone = li.cloneNode(true);
                            
                            // Remove nested ul/ol elements to get just this item's content
                            const nestedLists = liClone.querySelectorAll('ul, ol');
                            nestedLists.forEach(nestedList => nestedList.remove());
                            
                            itemContent = liClone.innerHTML.trim();
                            itemText = liClone.textContent.trim();
                            
                            // Add this item
                            items.push({
                                content: itemContent,
                                text: itemText,
                                level: baseLevel
                            });
                            
                            // Process nested lists
                            const nestedListsInOriginal = li.querySelectorAll(':scope > ul, :scope > ol');
                            nestedListsInOriginal.forEach(nestedList => {
                                extractListItems(nestedList, baseLevel + 1);
                            });
                        });
                    }
                    
                    extractListItems(el);
                    
                    return {
                        type: 'list',
                        listType: tagName,
                        items: items,
                        html: el.outerHTML,
                        originalTag: tagName  // Preserve original tag
                    };
                }
                
                // For text elements, preserve formatting AND original tag
                // Special handling for paragraphs with inline math images
                if (tagName === 'p' && el.querySelector('img.math-image.inline')) {
                    // This paragraph contains inline math images
                    // We need to preserve the HTML structure but ensure math images are handled correctly
                    let processedHTML = el.innerHTML.trim();
                    
                    // Find all inline math images and ensure they're properly formatted
                    const mathImages = el.querySelectorAll('img.math-image.inline');
                    mathImages.forEach(img => {
                        // Ensure the math image has all necessary attributes
                        const latex = img.getAttribute('data-latex') || img.getAttribute('alt') || '';
                        const width = img.getAttribute('data-math-width') || '20';
                        const height = img.getAttribute('data-math-height') || '20';
                        const baseline = img.getAttribute('data-math-baseline') || '0';
                        const src = img.getAttribute('src') || '';
                        
                        // Create a properly formatted math image tag
                        const mathImgHTML = `<img alt="${latex}" class="math-image inline" data-latex="${latex}" data-math-width="${width}" data-math-height="${height}" data-math-baseline="${baseline}" src="${src}" style="vertical-align: -${baseline}px;"/>`;
                        
                        // Replace the original img tag with the properly formatted one
                        processedHTML = processedHTML.replace(img.outerHTML, mathImgHTML);
                    });
                    
                    return {
                        type: 'text',
                        html: processedHTML,
                        text: el.textContent.trim(),
                        originalTag: tagName,
                        hasInlineMath: true  // Flag to indicate this paragraph has inline math
                    };
                }
                
                // For other text elements, preserve formatting AND original tag
                return {
                    type: 'text',
                    html: el.innerHTML.trim(),
                    text: el.textContent.trim(),
                    originalTag: tagName  // Preserve original tag (h1, h2, h3, p, etc.)
                };
            }
            
            // Main function to wrap elements
            function wrapElementsInPptxBoxes() {
                const elementsToWrap = document.querySelectorAll('.slide *, .page-break');
                const processedElements = new Set();
                
                Array.from(elementsToWrap).forEach(el => {
                    // Skip if already processed or is a child of processed element
                    if (processedElements.has(el)) return;
                    
                    // Skip script/style elements
                    if (['script', 'style'].includes(el.tagName.toLowerCase())) return;
                    
                    // Handle page breaks specially
                    if (el.classList.contains('page-break')) {
                        const wrapper = document.createElement('div');
                        wrapper.className = 'pptx-box page-break';
                        wrapper.setAttribute('data-box-id', getNextBoxId());
                        wrapper.setAttribute('data-type', 'page-break');
                        wrapper.setAttribute('data-x', '0');
                        wrapper.setAttribute('data-y', '0');
                        wrapper.setAttribute('data-width', '0');
                        wrapper.setAttribute('data-height', '0');
                        wrapper.innerHTML = '<!-- slide -->';
                        
                        el.parentNode.replaceChild(wrapper, el);
                        processedElements.add(wrapper);
                        return;
                    }
                    
                    // Skip empty non-img elements
                    if (el.tagName.toLowerCase() !== 'img' && !el.textContent.trim()) return;
                    
                    // Skip li elements - process their parent ul/ol instead
                    if (el.tagName.toLowerCase() === 'li') return;
                    
                    // Skip column container divs - process their children
                    if (el.className && (el.className.includes('columns') || el.className.includes('column'))) return;
                    
                    // Check if this element is a child of an already processed element
                    let isChild = false;
                    for (const processed of processedElements) {
                        if (processed.contains && processed.contains(el)) {
                            isChild = true;
                            break;
                        }
                    }
                    if (isChild) return;
                    
                    // Extract layout and content information
                    const styleInfo = extractStyleInfo(el);
                    const content = extractContent(el);
                    const elementType = getElementType(el);
                    
                    // Create pptx-box wrapper
                    const wrapper = document.createElement('div');
                    wrapper.className = 'pptx-box ' + elementType;
                    
                    // Add layout data attributes
                    wrapper.setAttribute('data-box-id', getNextBoxId());
                    wrapper.setAttribute('data-type', elementType);
                    wrapper.setAttribute('data-x', styleInfo.x.toString());
                    wrapper.setAttribute('data-y', styleInfo.y.toString());
                    wrapper.setAttribute('data-width', styleInfo.width.toString());
                    wrapper.setAttribute('data-height', styleInfo.height.toString());
                    
                    // Add style data attributes
                    wrapper.setAttribute('data-font-size', styleInfo.fontSize);
                    wrapper.setAttribute('data-font-weight', styleInfo.fontWeight);
                    wrapper.setAttribute('data-font-style', styleInfo.fontStyle);
                    wrapper.setAttribute('data-text-align', styleInfo.textAlign);
                    wrapper.setAttribute('data-color', styleInfo.color);
                    wrapper.setAttribute('data-background-color', styleInfo.backgroundColor);
                    wrapper.setAttribute('data-line-height', styleInfo.lineHeight);
                    
                    // Add content data (as JSON for complex structures)
                    wrapper.setAttribute('data-content', JSON.stringify(content));
                    
                    // Add parent information
                    if (el.parentElement) {
                        wrapper.setAttribute('data-parent-tag', el.parentElement.tagName.toLowerCase());
                        wrapper.setAttribute('data-parent-class', el.parentElement.className || '');
                    }
                    
                    // Add column information if in a column
                    const parentColumn = el.closest('.column');
                    if (parentColumn) {
                        const colRect = parentColumn.getBoundingClientRect();
                        wrapper.setAttribute('data-column-width', colRect.width.toString());
                        const mode = parentColumn.getAttribute('data-column-width');
                        if (mode) wrapper.setAttribute('data-column-mode', mode);
                    }
                    
                    // Add unique bid if present
                    const bid = el.getAttribute('data-bid');
                    if (bid) wrapper.setAttribute('data-bid', bid);
                    
                    // Preserve original element classes
                    if (el.className) {
                        wrapper.setAttribute('data-original-class', el.className);
                    }
                    
                    // Move the original element inside the wrapper
                    wrapper.appendChild(el.cloneNode(true));
                    
                    // Replace original element with wrapper
                    el.parentNode.replaceChild(wrapper, el);
                    processedElements.add(wrapper);
                });
            }
            
            // Execute the wrapping
            wrapElementsInPptxBoxes();
        }
        """
    
    def _parse_structured_html(self, html_content: str) -> List[Dict[str, Any]]:
        """
        Parse structured HTML with pptx-box wrappers using BeautifulSoup.
        
        Args:
            html_content: HTML content with pptx-box wrappers
            
        Returns:
            List of structured layout elements
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        elements = []
        
        # Find all pptx-box elements
        pptx_boxes = soup.find_all(class_='pptx-box')
        
        for box in pptx_boxes:
            try:
                element_data = {
                    'box_id': box.get('data-box-id'),
                    'type': box.get('data-type'),
                    'x': float(box.get('data-x') or 0),
                    'y': float(box.get('data-y') or 0),
                    'width': float(box.get('data-width') or 0),
                    'height': float(box.get('data-height') or 0),
                    'style': {
                        'fontSize': box.get('data-font-size'),
                        'fontWeight': box.get('data-font-weight'),
                        'fontStyle': box.get('data-font-style'),
                        'textAlign': box.get('data-text-align'),
                        'color': box.get('data-color'),
                        'backgroundColor': box.get('data-background-color'),
                        'lineHeight': box.get('data-line-height')
                    },
                    'parent': {
                        'tag': box.get('data-parent-tag'),
                        'class': box.get('data-parent-class')
                    },
                    'column': {
                        'width': float(box.get('data-column-width') or 0) if box.get('data-column-width') else None,
                        'mode': box.get('data-column-mode')
                    } if box.get('data-column-width') else None,
                    'bid': box.get('data-bid'),
                    'original_class': box.get('data-original-class')
                }
                
                # Parse content data
                content_json = box.get('data-content')
                if content_json:
                    try:
                        element_data['content'] = json.loads(content_json)
                    except json.JSONDecodeError:
                        # Fallback to text content
                        element_data['content'] = {
                            'type': 'text',
                            'text': box.get_text(strip=True),
                            'html': str(box)
                        }
                else:
                    element_data['content'] = {
                        'type': 'text',
                        'text': box.get_text(strip=True),
                        'html': str(box)
                    }
                
                elements.append(element_data)
                
            except (ValueError, TypeError) as e:
                if self.debug:
                    logger.warning(f"Failed to parse pptx-box element: {e}")
                continue
        
        return elements
    
    def convert_to_blocks(self, structured_elements: List[Dict[str, Any]]) -> List[Block]:
        """
        Convert structured elements to Block objects for compatibility.
        
        Args:
            structured_elements: List of structured layout elements
            
        Returns:
            List of Block objects
        """
        blocks = []
        
        for element in structured_elements:
            # Handle page breaks
            if element['type'] == 'page-break':
                block = Block(
                    tag='div',
                    content='<!-- slide -->',
                    x=0, y=0, w=0, h=0,
                    role='page_break'
                )
                blocks.append(block)
                continue
            
            # Initialize BID candidate
            block_bid_candidate = None
            
            # Create Block object
            content = element['content']
            
            # Determine tag name from type
            tag_map = {
                'heading': 'h1',  # Default, but will be overridden by originalTag
                'text': 'p',
                'image': 'img',
                'table': 'table',
                'list': 'ul',
                'quote': 'blockquote',
                'code': 'pre'
            }
            
            tag = tag_map.get(element['type'], 'div')
            
            # Use the original tag if available (more accurate than parsing HTML)
            if 'originalTag' in content and content['originalTag']:
                tag = content['originalTag']
            elif element['type'] == 'heading':
                # Fallback: try to determine heading level from HTML if originalTag is missing
                html_content = content.get('html', '')
                if html_content:
                    import re
                    h_match = re.search(r'<(h[1-6])', html_content, re.IGNORECASE)
                    if h_match:
                        tag = h_match.group(1).lower()
                    # If no heading tag found in HTML, default to h1 (from tag_map)
            
            # Extract text content
            if content['type'] == 'text':
                # Use HTML content to preserve inline formatting instead of plain text
                text_content = content.get('html', content.get('text', ''))
                # No need to re-parse tag from HTML since we have originalTag
            elif content['type'] == 'image':
                # For images, preserve the original HTML to retain data attributes
                text_content = content.get('html', content.get('alt', ''))
            else:
                text_content = content.get('text', str(content))
            
            # Special handling for lists - convert to legacy format
            if content['type'] == 'list' or tag in ['ul', 'ol']:
                # Convert list to legacy format that the PPTX renderer expects
                list_items = content.get('items', [])
                
                if list_items:
                    # Create formatted text content with levels, preserving HTML in items
                    formatted_items = []
                    levels = []
                    
                    for item in list_items:
                        # Use HTML content if available, otherwise fall back to text
                        item_text = item.get('content', item.get('text', '')).strip()
                        if item_text:
                            formatted_items.append(item_text)
                            levels.append(str(item.get('level', 0)))
                    
                    if formatted_items:
                        # Join with <br> instead of \n to preserve HTML structure
                        formatted_text = '<br>'.join(formatted_items)
                        level_data = ','.join(levels)
                        list_type = content.get('listType', tag)
                        
                        # Create block with list-specific format, preserving existing BIDs
                        text_content = f'<p data-list-levels="{level_data}" data-list-type="{list_type}">{formatted_text}</p>'
                        
                        # For lists, try to find a BID from the original HTML content
                        list_html = content.get('html', '')
                        import re
                        bid_matches = re.findall(r'data-bid="([^"]+)"', list_html)
                        if bid_matches:
                            # Look for the parent container BID that should have been assigned by _preprocess_html_for_measurement
                            # The parent container for lists is typically a <p> with data-list-levels
                            # We need to check if this list corresponds to an existing container BID
                            # For now, use the first BID pattern found in children
                            first_child_bid = bid_matches[0]
                            # Extract the numeric part to construct the container BID
                            bid_num_match = re.search(r'b(\d+)', first_child_bid)
                            if bid_num_match:
                                # The container typically has one less than the first child
                                container_bid_num = max(0, int(bid_num_match.group(1)) - 1)
                                block_bid_candidate = f'b{container_bid_num}'
                            else:
                                block_bid_candidate = first_child_bid
            
            # Create block
            block = Block(
                tag=tag,
                content=text_content,
                x=int(element['x']),
                y=int(element['y']),
                w=int(element['width']),
                h=int(element['height']),
                className=element.get('original_class', ''),
                style=element.get('style', {}),
                parentClassName=element['parent'].get('class') if element.get('parent') else None
            )
            
            # Add additional attributes for images
            if content['type'] == 'image':
                block.src = content.get('src')
                block.scaleX = content.get('scaleX')
                block.scaleY = content.get('scaleY')
                block.scaleType = content.get('scaleType')
                block.inColumn = content.get('inColumn')
            
            # Add table column width information
            if content['type'] == 'table' and 'tableColumnWidths' in content:
                block.table_column_widths = content['tableColumnWidths']
            
            # Add column information
            if element.get('column'):
                block.parentColumnWidth = element['column']['width']
                block.columnMode = element['column']['mode']
            
            # Add bid from the structured element or generate one
            if element.get('bid'):
                block.bid = element['bid']
            elif block_bid_candidate:
                # Use the candidate BID found during processing (e.g., from list content)
                block.bid = block_bid_candidate
            else:
                # Extract BID from HTML content if available
                import re
                html_content = content.get('html', '')
                bid_match = re.search(r'data-bid="([^"]+)"', html_content)
                if bid_match:
                    block.bid = bid_match.group(1)
                else:
                    block.bid = f"structured_{len(blocks)}"
            
            blocks.append(block)
        
        return blocks
    
    def _copy_images_for_measurement(self, html_content: str, temp_dir: str) -> str:
        """Copy images to temp directory for measurement."""
        import re
        import shutil
        
        def replace_image_src(match):
            src = match.group(1)
            
            # Skip if already absolute path or URL
            if src.startswith(('http://', 'https://', 'file://', '/')):
                return match.group(0)
            
            # Copy image to temp directory
            try:
                if os.path.exists(src):
                    filename = os.path.basename(src)
                    temp_path = os.path.join(temp_dir, filename)
                    if not os.path.exists(temp_path):
                        shutil.copy2(src, temp_path)
                    # Use just the filename, not the full temp path
                    return f'src="{filename}" data-filepath="{src}"'
                else:
                    return match.group(0)
            except Exception:
                return match.group(0)
        
        # Replace image src attributes
        return re.sub(r'src="([^"]+)"', replace_image_src, html_content)


# Convenience function for backward compatibility
async def parse_html_with_structured_layout(html_content: str, theme: str = "default", 
                                           temp_dir: Optional[str] = None, debug: bool = False) -> List[Block]:
    """
    Parse HTML using the structured pptx-box approach.
    
    Args:
        html_content: HTML content to parse
        theme: Theme name for CSS variables
        temp_dir: Temporary directory for files
        debug: Enable debug output
        
    Returns:
        List of Block objects
    """
    parser = StructuredLayoutParser(theme=theme, debug=debug)
    structured_elements = await parser.parse_html_with_layout(html_content, temp_dir)
    return parser.convert_to_blocks(structured_elements)