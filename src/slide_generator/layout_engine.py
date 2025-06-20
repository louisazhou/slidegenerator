#!/usr/bin/env python3
"""
Layout Engine for measuring and paginating slide content.
"""

import asyncio
import tempfile
import re
from pathlib import Path
import markdown
from pyppeteer import launch

from .block import Block

class LayoutEngine:
    """
    Engine for measuring HTML layout and paginating content for slides.
    """
    
    def __init__(self, debug_dir=None):
        """
        Initialize the layout engine.
        
        Args:
            debug_dir: Directory for debug output (uses temp dir if None)
        """
        if debug_dir:
            self.temp_dir = Path(debug_dir)
        else:
            self.temp_dir = Path(tempfile.mkdtemp())
        print(f"Debug files will be saved to: {self.temp_dir}")
    
    def convert_markdown_to_html(self, markdown_text):
        """
        Convert markdown to HTML with layout CSS.
        
        Args:
            markdown_text: Markdown content to convert
            
        Returns:
            HTML string with CSS styling
        """
        # Process page breaks in markdown (--- or <!-- slide -->)
        slides_md = []
        current_slide = []
        
        for line in markdown_text.split('\n'):
            if line.strip() == '---' or '<!-- slide -->' in line:
                if current_slide:
                    slides_md.append('\n'.join(current_slide))
                    current_slide = []
            else:
                current_slide.append(line)
                
        if current_slide:
            slides_md.append('\n'.join(current_slide))
        
        # If no page breaks were found, treat the whole content as one slide
        if not slides_md:
            slides_md = [markdown_text]
        
        # Convert each slide to HTML
        html_slides = []
        for slide_md in slides_md:
            # Use extra extension to allow raw HTML and output as HTML5
            html = markdown.markdown(
                slide_md,
                extensions=['tables', 'fenced_code', 'extra'],
                output_format='html5'
            )
            html_slides.append(html)
        
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
            }
            
            h1 {
                font-size: 36px;
                margin-bottom: 20px;
            }
            
            h2 {
                font-size: 28px;
                margin-top: 30px;
                margin-bottom: 15px;
            }
            
            p {
                font-size: 18px;
                line-height: 1.5;
                margin-bottom: 15px;
            }
            
            ul, ol {
                margin-top: 10px;
                margin-bottom: 20px;
            }
            
            li {
                font-size: 18px;
                line-height: 1.5;
                margin-bottom: 8px;
            }
            
            pre {
                background-color: #f5f5f5;
                padding: 15px;
                border-radius: 5px;
                font-family: 'Courier New', monospace;
                font-size: 16px;
                overflow: auto;
                margin: 20px 0;
            }
            
            .two-column {
                display: flex;
                gap: 20px;
                margin-top: 20px;
            }
            
            .column {
                flex: 1;
                padding: 15px;
                background-color: #f9f9f9;
                border-radius: 5px;
            }
        </style>
        """
        
        # Combine all slides into one HTML document for measurement
        combined_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            {css}
        </head>
        <body>
            <div class="slide">
                {html_slides[0]}
            </div>
        """
        
        # Add page break markers between slides
        for slide_html in html_slides[1:]:
            combined_html += f"""
            <!-- slide -->
            <div class="slide">
                {slide_html}
            </div>
            """
            
        combined_html += """
        </body>
        </html>
        """
        
        return combined_html
    
    async def measure_layout(self, html_content):
        """
        Use Puppeteer to measure the layout of HTML elements.
        
        Args:
            html_content: HTML to measure
            
        Returns:
            List of Block objects with measured positions and sizes
        """
        browser = await launch(headless=True)
        page = await browser.newPage()
        
        # Set viewport to match slide dimensions (16:9 ratio)
        await page.setViewport({'width': 960, 'height': 540})
        
        # Set content and wait for it to load
        await page.setContent(html_content)
        await page.waitForSelector('.slide')
        
        # Take a screenshot for debugging
        await page.screenshot({'path': f'{self.temp_dir}/debug_screenshot.png'})
        
        # Get element positions and sizes for layout information
        layout_data = await page.evaluate('''() => {
            // Select all elements inside the slide
            const elements = document.querySelectorAll('.slide > *, .slide div > *');
            const result = [];
            
            // Process regular elements
            Array.from(elements).forEach(el => {
                const rect = el.getBoundingClientRect();
                const styles = window.getComputedStyle(el);
                const tagName = el.tagName.toLowerCase();
                const textContent = el.textContent;
                const className = el.className;
                
                // Get text style information
                const fontSize = styles.fontSize;
                const fontWeight = styles.fontWeight;
                const fontStyle = styles.fontStyle;
                const color = styles.color;
                const backgroundColor = styles.backgroundColor;
                
                // Get computed RGB values
                const rgbToHex = (rgb) => {
                    if (rgb === 'rgba(0, 0, 0, 0)') return null;
                    
                    // Extract RGB values
                    const rgbMatch = rgb.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*[\\d.]+)?\\)/);
                    if (!rgbMatch) return null;
                    
                    const r = parseInt(rgbMatch[1]);
                    const g = parseInt(rgbMatch[2]);
                    const b = parseInt(rgbMatch[3]);
                    
                    return { r, g, b };
                };
                
                // Get parent information for hierarchy
                const parentTagName = el.parentElement ? el.parentElement.tagName.toLowerCase() : null;
                const parentClassName = el.parentElement ? el.parentElement.className : null;
                
                result.push({
                    tagName: tagName,
                    className: className,
                    textContent: textContent,
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                    parentTagName: parentTagName,
                    parentClassName: parentClassName,
                    style: {
                        fontSize,
                        fontWeight,
                        fontStyle,
                        color: rgbToHex(color),
                        backgroundColor: rgbToHex(backgroundColor),
                        textAlign: styles.textAlign
                    }
                });
            });
            
            // Find and add HTML comments (for slide breaks)
            const findComments = (node) => {
                if (node.nodeType === 8) { // Comment node
                    result.push({
                        tagName: '#comment',
                        textContent: node.textContent,
                        x: 0,
                        y: 0,
                        width: 0,
                        height: 0
                    });
                }
                
                // Process child nodes
                if (node.childNodes) {
                    Array.from(node.childNodes).forEach(child => findComments(child));
                }
            };
            
            // Start from document body
            findComments(document.body);
            
            return result;
        }''')
        
        # Get HTML content of the entire slide for debugging
        html_debug = await page.evaluate('() => document.documentElement.outerHTML')
        with open(f'{self.temp_dir}/debug_html.html', 'w') as f:
            f.write(html_debug)
        
        await browser.close()
        
        # Convert layout data to Block objects
        blocks = [Block(element) for element in layout_data]
        
        # Save layout info for debugging
        import json
        with open(f"{self.temp_dir}/layout_info.json", "w") as f:
            json.dump([block.to_dict() for block in blocks], f, indent=2)
        
        return blocks
    
    def process_layout(self, blocks):
        """
        Process layout blocks to prepare for pagination.
        
        Args:
            blocks: List of Block objects
            
        Returns:
            List of Block objects with page breaks inserted
        """
        # Filter out container divs
        filtered_blocks = []
        for block in blocks:
            # Skip container divs (two-column, column)
            if block.tag_name == 'div' and block.class_name:
                if 'column' in block.class_name or 'two-column' in block.class_name:
                    continue
            filtered_blocks.append(block)
            
        # Process HTML comments for slide breaks
        layout_with_breaks = []
        page_break_indices = []
        
        # First pass: identify slide breaks from HTML comments
        for i, block in enumerate(filtered_blocks):
            if block.is_comment() and '<!-- slide -->' in block.text_content:
                page_break_indices.append(i)
        
        # Second pass: add page breaks at the identified positions
        for i, block in enumerate(filtered_blocks):
            if i in page_break_indices:
                # Create a page break block
                page_break = Block({'role': 'page_break'})
                layout_with_breaks.append(page_break)
            elif not block.is_comment():  # Skip comment nodes
                layout_with_breaks.append(block)
        
        return layout_with_breaks
    
    def paginate(self, blocks, max_px=540):
        """
        Split blocks into pages based on vertical height constraints.
        
        Args:
            blocks: List of Block objects
            max_px: Maximum height in pixels for a single slide
            
        Returns:
            List of lists, where each inner list contains Block objects for one slide
        """
        if not blocks:
            return []
        
        slides = []
        current_slide = []
        current_height = 0
        
        for block in blocks:
            # Handle explicit page breaks
            if block.is_page_break():
                if current_slide:
                    slides.append(current_slide)
                    current_slide = []
                    current_height = 0
                continue
                
            block_height = block.height
            
            # If this block would exceed the max height, start a new slide
            if current_height + block_height > max_px and current_slide:
                slides.append(current_slide)
                current_slide = []
                current_height = 0
                
            # Handle oversized blocks by setting auto_size
            if block_height > max_px:
                block.oversized = True
                block_height = max_px - 2  # Leave a small margin
                
            # Add block to current slide
            current_slide.append(block)
            current_height += block_height
        
        # Add the last slide if it has content
        if current_slide:
            slides.append(current_slide)
            
        return slides
    
    def sort_blocks_by_position(self, blocks):
        """
        Sort blocks by their vertical and horizontal position.
        
        Args:
            blocks: List of Block objects
            
        Returns:
            Sorted list of Block objects
        """
        # Skip page breaks in sorting
        return sorted(blocks, key=lambda b: (b.y, b.x) if not b.is_page_break() else (-1, -1))
    
    def measure_markdown(self, markdown_text):
        """
        Convert markdown to HTML and measure layout.
        
        Args:
            markdown_text: Markdown content
            
        Returns:
            List of Block objects with measured positions
        """
        # Convert markdown to HTML
        html = self.convert_markdown_to_html(markdown_text)
        
        # Save the HTML for debugging
        with open(f"{self.temp_dir}/input.html", "w") as f:
            f.write(html)
        
        # Measure layout using Puppeteer
        blocks = asyncio.get_event_loop().run_until_complete(
            self.measure_layout(html)
        )
        
        # Process layout to handle page breaks
        processed_blocks = self.process_layout(blocks)
        
        return processed_blocks
    
    def get_paginated_layout(self, markdown_text, max_px=460):
        """
        Get fully processed and paginated layout from markdown.
        
        Args:
            markdown_text: Markdown content
            max_px: Maximum height per slide in pixels
            
        Returns:
            List of lists, where each inner list contains Block objects for one slide
        """
        # Measure layout
        blocks = self.measure_markdown(markdown_text)
        
        # Paginate blocks
        paginated_blocks = self.paginate(blocks, max_px)
        
        # Sort blocks within each page by position
        sorted_pages = [self.sort_blocks_by_position(page) for page in paginated_blocks]
        
        return sorted_pages 