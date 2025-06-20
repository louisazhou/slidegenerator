#!/usr/bin/env python3
"""
PowerPoint renderer for converting layout blocks to PowerPoint slides.
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE
from pptx.dml.color import RGBColor

from .block import Block

# Helper function to convert pixels to inches
def px_to_inches(pixels):
    """Convert pixels to inches for PowerPoint."""
    return Inches(pixels / 96)

class PPTXRenderer:
    """
    Renderer for converting layout blocks to PowerPoint slides.
    """
    
    def __init__(self):
        """Initialize the PowerPoint renderer."""
        pass
    
    def create_presentation(self, paginated_blocks, output_path):
        """
        Create a PowerPoint presentation from paginated blocks.
        
        Args:
            paginated_blocks: List of lists of Block objects
            output_path: Path to save the PowerPoint file
            
        Returns:
            Path to the saved PowerPoint file
        """
        prs = Presentation()
        
        # Set slide dimensions to 16:9 aspect ratio
        prs.slide_width = Inches(10)
        prs.slide_height = Inches(5.625)
        
        # Create slides for each page of blocks
        for page in paginated_blocks:
            # Add a blank slide
            slide_layout = prs.slide_layouts[6]  # Blank layout
            slide = prs.slides.add_slide(slide_layout)
            
            # Add elements to this slide
            for block in page:
                self._add_element_to_slide(slide, block)
        
        # Save the presentation
        prs.save(output_path)
        return output_path
    
    def _add_element_to_slide(self, slide, block):
        """
        Add a single element to the slide based on its type.
        
        Args:
            slide: PowerPoint slide object
            block: Block object to add to the slide
        """
        # Skip page breaks
        if block.is_page_break():
            return
            
        # Convert browser coordinates to PowerPoint coordinates
        x = px_to_inches(block.x)
        y = px_to_inches(block.y)
        width = px_to_inches(block.width)
        
        # Use the exact browser-measured height with 1px padding for safety
        height = px_to_inches(block.height + 1)
        
        # Skip empty elements
        if not block.text_content:
            return
            
        # Skip elements with zero width or height
        if block.width <= 1 or block.height <= 1:
            return
        
        if block.is_heading():
            # Add a title or heading
            textbox = slide.shapes.add_textbox(x, y, width, height)
            text_frame = textbox.text_frame
            text_frame.word_wrap = True
            
            # Use auto-size for oversized elements
            if block.oversized:
                text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
            
            p = text_frame.paragraphs[0]
            p.text = block.text_content
            
            # Set font size based on heading level
            font_sizes = {'h1': Pt(36), 'h2': Pt(28), 'h3': Pt(24), 
                         'h4': Pt(20), 'h5': Pt(18), 'h6': Pt(16)}
            p.font.size = font_sizes.get(block.tag_name, Pt(18))
            p.font.bold = True
            
        elif block.is_paragraph():
            # Add a paragraph
            textbox = slide.shapes.add_textbox(x, y, width, height)
            text_frame = textbox.text_frame
            text_frame.word_wrap = True
            
            # Use auto-size for oversized elements
            if block.oversized:
                text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
            
            p = text_frame.paragraphs[0]
            p.text = block.text_content
            p.font.size = Pt(18)
            
            # Set font style
            font_weight = block.style.get('fontWeight', '')
            if font_weight and (
                (isinstance(font_weight, str) and font_weight == 'bold') or
                (isinstance(font_weight, (int, float)) and int(font_weight) >= 600)
            ):
                p.font.bold = True
                
            if block.style.get('fontStyle') == 'italic':
                p.font.italic = True
            
        elif block.is_list():
            # Add a list
            textbox = slide.shapes.add_textbox(x, y, width, height)
            text_frame = textbox.text_frame
            text_frame.word_wrap = True
            
            # Use auto-size for oversized elements
            if block.oversized:
                text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
            
            # Get list items directly from the element's textContent
            # Split by line breaks and filter out empty lines
            list_items = [li.strip() for li in block.text_content.split('\n') if li.strip()]
            
            # Add each list item as a separate paragraph with bullet
            first = True
            for i, item in enumerate(list_items):
                if first:
                    p = text_frame.paragraphs[0]
                    first = False
                else:
                    p = text_frame.add_paragraph()
                
                # For unordered lists, add bullet character
                if block.tag_name == 'ul':
                    p.text = "• " + item
                else:
                    # For ordered lists, add number
                    p.text = f"{i+1}. " + item
                
                # Set paragraph level (for indentation)
                p.level = 0
                
                # Set alignment
                from pptx.enum.text import PP_ALIGN
                p.alignment = PP_ALIGN.LEFT
                
                # Set font size
                p.font.size = Pt(18)
        
        elif block.is_code_block():
            # Add a code block
            textbox = slide.shapes.add_textbox(x, y, width, height)
            text_frame = textbox.text_frame
            text_frame.word_wrap = True
            
            # Use auto-size for oversized elements
            if block.oversized:
                text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
            
            p = text_frame.paragraphs[0]
            p.text = block.text_content
            p.font.name = 'Courier New'
            p.font.size = Pt(16) 