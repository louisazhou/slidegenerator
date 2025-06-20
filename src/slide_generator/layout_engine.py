"""Layout engine for measuring HTML elements and pagination."""

import asyncio
import tempfile
import os
import json
import markdown
from pyppeteer import launch
from pptx.util import Inches
from .models import Block
from typing import List, Optional


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
    current_height = 0
    
    for block in blocks:
        # Handle explicit page breaks
        if block.is_page_break():
            # Only add non-empty pages
            if current_page:
                pages.append(current_page)
            current_page = []
            current_height = 0
            continue
        
        # Get the height of the block
        block_height = block.height
        
        # Check for oversized blocks and mark them
        if block_height > max_height_px * 0.8:  # 80% of slide height
            block.oversized = True
            
        # If adding this block would exceed the max height, start a new page
        if current_height + block_height > max_height_px and current_page:
            # Only add non-empty pages
            pages.append(current_page)
            current_page = []
            current_height = 0
            
        # Add the block to the current page
        current_page.append(block)
        current_height += block_height
    
    # Add the last page if it's not empty
    if current_page:
        pages.append(current_page)
    
    return pages


class LayoutEngine:
    """Handles HTML measurement and pagination for slide generation."""
    
    def __init__(self, debug: bool = False):
        self.debug = debug or os.getenv('SLIDES_DEBUG') == '1'
    
    async def measure_layout(self, html_content, temp_dir=None):
        """Use Puppeteer to measure the layout of HTML elements."""
        browser = await launch(headless=True)
        page = await browser.newPage()
        
        # Set viewport to match slide dimensions (16:9 ratio)
        await page.setViewport({'width': 960, 'height': 540})
        
        # Set content and wait for it to load
        await page.setContent(html_content)
        await page.waitForSelector('.slide')
        
        # Take a screenshot for debugging
        if temp_dir:
            await page.screenshot({'path': f'{temp_dir}/debug_screenshot.png'})
        
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
                
                // Skip elements that are children of elements we've already processed
                for (const parent of result) {
                    if (parent.element && parent.element.contains(el)) {
                        return;
                    }
                }
                
                const rect = el.getBoundingClientRect();
                const computedStyle = window.getComputedStyle(el);
                
                // Get text content, handling special cases
                let textContent = el.textContent;
                
                // For list items, add bullet points manually
                if (el.tagName.toLowerCase() === 'li') {
                    const listType = el.parentElement.tagName.toLowerCase();
                    if (listType === 'ul') {
                        textContent = '• ' + textContent;
                    } else if (listType === 'ol') {
                        // Find the index of this li among its siblings
                        const siblings = Array.from(el.parentElement.children);
                        const index = siblings.indexOf(el) + 1;
                        textContent = index + '. ' + textContent;
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
        
        # Process page breaks in markdown (--- or <!-- slide -->)
        slides_md = []
        current_slide = []
        
        # Add a leading newline to ensure proper parsing
        lines = markdown_text.strip().split('\n')
        
        for line in lines:
            if line.strip() == '---' or '<!-- slide -->' in line:
                # Add current slide content if it exists
                if current_slide:
                    slides_md.append('\n'.join(current_slide))
                # Always start a new slide after a page break
                current_slide = []
            else:
                current_slide.append(line)
                
        # Add the last slide if it has content
        if current_slide:
            slides_md.append('\n'.join(current_slide))
        
        # If no page breaks were found, treat the whole content as one slide
        if not slides_md:
            slides_md = [markdown_text]
        
        # Convert each slide to HTML
        html_slides = []
        for slide_md in slides_md:
            if not slide_md.strip():
                # Skip completely empty slides
                continue
            
            # Use extra extension to allow raw HTML and output as HTML5
            html = markdown.markdown(
                slide_md,
                extensions=['tables', 'fenced_code', 'extra'],
                output_format='html5'
            )
            html_slides.append(html)
        
        # If no content slides, return empty string
        if not html_slides:
            return ""
        
        # Add CSS for layout
        css = """
        <style>
            body {
                margin: 0;
                padding: 0;
                font-family: Arial, sans-serif;
            }
            
            .slide {
                width: 960px;
                height: 540px;
                padding: 40px;
                box-sizing: border-box;
                position: relative;
                page-break-after: always;
            }
            
            h1 {
                font-size: 36px;
                margin-bottom: 20px;
            }
            
            h2 {
                font-size: 28px;
                margin-bottom: 15px;
            }
            
            h3 {
                font-size: 22px;
                margin-bottom: 12px;
            }
            
            p {
                font-size: 18px;
                line-height: 1.4;
                margin-bottom: 15px;
            }
            
            ul, ol {
                font-size: 18px;
                line-height: 1.4;
                margin-left: 20px;
                margin-bottom: 15px;
            }
            
            li {
                margin-bottom: 8px;
            }
            
            pre, code {
                font-family: 'Courier New', monospace;
                font-size: 14px;
                background-color: #f4f4f4;
                padding: 10px;
                border-radius: 4px;
                margin-bottom: 15px;
            }
            
            table {
                border-collapse: collapse;
                width: 100%;
                margin-bottom: 15px;
            }
            
            th, td {
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }
            
            th {
                background-color: #f2f2f2;
                font-weight: bold;
            }
            
            .page-break {
                display: none;  /* Hidden in CSS but will be detected by JavaScript */
            }
        </style>
        """
        
        # Combine HTML slides
        full_html = f"{css}\n<body>\n"
        for i, html_slide in enumerate(html_slides):
            full_html += f'<div class="slide" id="slide-{i}">\n{html_slide}\n</div>\n'
            
            # Add a page break marker (except after the last slide)
            if i < len(html_slides) - 1:
                full_html += '<div class="page-break"><!-- slide --></div>\n'
        
        full_html += "</body>"
        
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
        
        # Save the HTML content to a file for debugging
        with open(os.path.join(temp_dir, "input.html"), "w") as f:
            f.write(html_content)
        
        # Measure layout using Puppeteer
        layout_info = asyncio.run(self.measure_layout(html_content, temp_dir))
        
        # Save layout information for debugging
        with open(os.path.join(temp_dir, "layout_info.json"), "w") as f:
            json.dump(layout_info, f, indent=2)
        
        # Convert raw layout data to Block objects
        blocks = [Block.from_element(element) for element in layout_info]
        
        # Paginate the blocks
        pages = paginate(blocks, page_height)
        
        if self.debug:
            print(f"Layout engine created {len(pages)} pages:")
            for i, page in enumerate(pages):
                print(f"  Page {i+1}: {len(page)} blocks (height limit: {page_height}px)")
                for j, block in enumerate(page):
                    oversized_flag = " [OVERSIZED]" if hasattr(block, 'oversized') and block.oversized else ""
                    print(f"    Block {j+1}: {block.tag} ({block.height}px) - '{block.content[:30]}...'{oversized_flag}")
        
        return pages 