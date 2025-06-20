#!/usr/bin/env python3
"""
Block class for representing layout elements in slides.
"""

class Block:
    """
    Represents a layout block in a slide with position, size, and content information.
    """
    
    def __init__(self, element_data):
        """
        Initialize a Block from element data.
        
        Args:
            element_data: Dictionary with element properties from browser measurement
        """
        self.tag_name = element_data.get('tagName', '')
        self.text_content = element_data.get('textContent', '').strip()
        self.class_name = element_data.get('className', '')
        
        # Position and size
        self.x = element_data.get('x', 0)
        self.y = element_data.get('y', 0)
        self.width = element_data.get('width', 0)
        self.height = element_data.get('height', 0)
        
        # Style information
        self.style = element_data.get('style', {})
        
        # Parent information
        self.parent_tag_name = element_data.get('parentTagName', '')
        self.parent_class_name = element_data.get('parentClassName', '')
        
        # Special roles
        self.role = element_data.get('role', '')
        
        # Flags
        self.oversized = element_data.get('oversized', False)
    
    def to_dict(self):
        """Convert block to dictionary representation."""
        return {
            'tagName': self.tag_name,
            'textContent': self.text_content,
            'className': self.class_name,
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'style': self.style,
            'parentTagName': self.parent_tag_name,
            'parentClassName': self.parent_class_name,
            'role': self.role,
            'oversized': self.oversized
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create a Block instance from a dictionary."""
        return cls(data)
    
    def is_page_break(self):
        """Check if this block represents a page break."""
        return self.role == 'page_break'
    
    def is_heading(self):
        """Check if this block is a heading."""
        return self.tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']
    
    def is_paragraph(self):
        """Check if this block is a paragraph."""
        return self.tag_name == 'p'
    
    def is_list(self):
        """Check if this block is a list."""
        return self.tag_name in ['ul', 'ol']
    
    def is_code_block(self):
        """Check if this block is a code block."""
        return self.tag_name == 'pre'
    
    def is_comment(self):
        """Check if this block is an HTML comment."""
        return self.tag_name == '#comment'
    
    def __repr__(self):
        """String representation of the block."""
        if self.is_page_break():
            return f"<Block: PAGE_BREAK>"
        return f"<Block: {self.tag_name} at ({self.x}, {self.y}) size {self.width}x{self.height}>" 