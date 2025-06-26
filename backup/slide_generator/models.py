"""
Data models for the slide generator.
"""
from dataclasses import dataclass
from typing import Dict, Optional, Union


@dataclass
class Block:
    """
    Represents a layout block with position, size, and content information.
    """
    tag: str
    x: int
    y: int
    w: int
    h: int
    content: str = ""
    role: Optional[str] = None
    style: Optional[Dict] = None
    table_column_widths: Optional[list] = None
    src: Optional[str] = None  # For images
    className: Optional[str] = None  # For CSS class names
    
    @property
    def width(self):
        """Alias for w for compatibility."""
        return self.w
    
    @property
    def height(self):
        """Alias for h for compatibility."""
        return self.h
    
    @property
    def textContent(self):
        """Alias for content for compatibility."""
        return self.content
    
    @property
    def tagName(self):
        """Alias for tag for compatibility."""
        return self.tag
    
    def is_page_break(self):
        """Check if this block represents a page break."""
        return self.role == "page_break" or self.tag == "page_break"
    
    def is_heading(self):
        """Check if this block is a heading."""
        return self.tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']
    
    def is_paragraph(self):
        """Check if this block is a paragraph."""
        return self.tag == 'p'
    
    def is_list(self):
        """Check if this block is a list."""
        return self.tag in ['ul', 'ol']
    
    def is_code_block(self):
        """Check if this block is a code block."""
        return self.tag in ['pre', 'code']
    
    def is_list_item(self):
        """Check if this block is a list item."""
        return self.tag == 'li'
    
    def is_table(self):
        """Check if this block is a table."""
        return self.tag == 'table'
    
    def is_image(self):
        """Check if this block is an image."""
        return self.tag == 'img'
    
    @classmethod
    def from_element(cls, element):
        """
        Create a Block from an element dictionary.
        """
        return cls(
            tag=element.get('tagName', ''),
            x=int(element.get('x', 0)),
            y=int(element.get('y', 0)),
            w=int(element.get('width', 0)),
            h=int(element.get('height', 0)),
            content=element.get('textContent', ''),
            role=element.get('role'),
            style=element.get('style', {}),
            table_column_widths=element.get('tableColumnWidths'),
            src=element.get('src'),
            className=element.get('className')
        ) 