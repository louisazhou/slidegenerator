"""
Enhanced markdown parser with support for multiple page break formats.
"""
from typing import List, Optional
from markdown_it import MarkdownIt


class MarkdownParser:
    """
    Enhanced markdown parser with page break support using markdown-it-py.
    """
    
    def __init__(self, extensions: Optional[List[str]] = None):
        """
        Initialize the markdown parser.
        
        Args:
            extensions: List of markdown extensions to enable (for compatibility)
        """
        # markdown-it-py doesn't use the same extension system as the old markdown library
        # but it has most features built-in by default
        self.markdown_processor = MarkdownIt('commonmark', {
            'html': True,          # Enable HTML tags
            'linkify': True,       # Auto-convert URLs to links
            'typographer': True,   # Enable smart quotes and other typographic replacements
        })
        
        # Enable additional features
        self.markdown_processor.enable(['table', 'strikethrough'])
    
    def parse(self, markdown_text: str) -> str:
        """
        Parse markdown text to HTML.
        
        Args:
            markdown_text: Raw markdown content
            
        Returns:
            HTML string
        """
        # Preprocess custom syntax before markdown processing
        processed_text = self._preprocess_custom_syntax(markdown_text)
        
        # Convert markdown to HTML
        html = self.markdown_processor.render(processed_text)
        
        return html
    
    def _preprocess_custom_syntax(self, markdown_text: str) -> str:
        """
        Preprocess custom syntax that isn't supported by markdown-it-py.
        
        Args:
            markdown_text: Raw markdown content
            
        Returns:
            Processed markdown with custom syntax converted
        """
        import re
        
        # Convert ==highlight== to HTML <mark> tags
        # This needs to be done before markdown processing to avoid conflicts
        processed = re.sub(r'==(.*?)==', r'<mark>\1</mark>', markdown_text)
        
        # Convert ++underline++ to HTML <u> tags
        # Using ++ to avoid conflict with markdown bold (**bold**)
        processed = re.sub(r'\+\+(.*?)\+\+', r'<u>\1</u>', processed)
        
        return processed
    
    def parse_with_page_breaks(self, markdown_text: str) -> List[str]:
        """
        Parse markdown text and split on page breaks.
        
        Supported page break formats:
        - Horizontal rule: ---
        - HTML comment: <!-- slide -->
        - Slide directive: <!-- NewSlide: -->
        - Explicit directive: [slide]
        
        Args:
            markdown_text: Raw markdown content
            
        Returns:
            List of HTML strings, one per slide
        """
        # Handle empty or whitespace-only content
        if not markdown_text or not markdown_text.strip():
            return []
        
        # Process page breaks in markdown
        slides_md = []
        current_slide = []
        
        lines = markdown_text.strip().split('\n')
        
        for line in lines:
            line_stripped = line.strip()
            
            # Check for various page break formats
            is_page_break = False
            
            # 1. Horizontal rule (must be exactly ---)
            if line_stripped == '---':
                is_page_break = True
            
            # 2. HTML slide comments (various formats)
            elif ('<!-- slide -->' in line_stripped or 
                  '<!-- Slide -->' in line_stripped or 
                  '<!-- SLIDE -->' in line_stripped or
                  '<!--slide-->' in line_stripped):
                is_page_break = True
            
            # 3. NewSlide directive
            elif ('<!-- NewSlide:' in line_stripped or 
                  '<!--NewSlide:' in line_stripped):
                is_page_break = True
            
            # 4. Explicit [slide] directive
            elif line_stripped == '[slide]':
                is_page_break = True
            
            # 5. Three or more asterisks or underscores (alternate horizontal rules)
            elif (line_stripped.startswith('***') and 
                  all(c == '*' for c in line_stripped)):
                is_page_break = True
            elif (line_stripped.startswith('___') and 
                  all(c == '_' for c in line_stripped)):
                is_page_break = True
            
            if is_page_break:
                # Add current slide content if it exists
                if current_slide:
                    slides_md.append('\n'.join(current_slide))
                # Start a new slide after a page break
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
            
            html = self.parse(slide_md)
            html_slides.append(html)
        
        return html_slides
    
    def count_page_breaks(self, markdown_text: str) -> int:
        """
        Count the number of page breaks in markdown text.
        
        Args:
            markdown_text: Raw markdown content
            
        Returns:
            Number of page breaks found
        """
        if not markdown_text or not markdown_text.strip():
            return 0
        
        page_breaks = 0
        lines = markdown_text.strip().split('\n')
        
        for line in lines:
            line_stripped = line.strip()
            
            # Check for various page break formats (same logic as parse_with_page_breaks)
            if (line_stripped == '---' or
                '<!-- slide -->' in line_stripped or
                '<!-- Slide -->' in line_stripped or
                '<!-- SLIDE -->' in line_stripped or
                '<!--slide-->' in line_stripped or
                '<!-- NewSlide:' in line_stripped or
                '<!--NewSlide:' in line_stripped or
                line_stripped == '[slide]' or
                (line_stripped.startswith('***') and all(c == '*' for c in line_stripped)) or
                (line_stripped.startswith('___') and all(c == '_' for c in line_stripped))):
                page_breaks += 1
        
        return page_breaks
    
    def estimate_slide_count(self, markdown_text: str) -> int:
        """
        Estimate the number of slides that will be generated.
        
        Args:
            markdown_text: Raw markdown content
            
        Returns:
            Estimated number of slides
        """
        if not markdown_text or not markdown_text.strip():
            return 0
        
        page_breaks = self.count_page_breaks(markdown_text)
        
        # If there are page breaks, slide count is page breaks + 1
        # If no page breaks, it's just 1 slide
        return page_breaks + 1
    
    def add_extension(self, extension: str) -> None:
        """
        Add a new extension to the parser.
        
        Args:
            extension: Extension name to add (for compatibility)
        """
        # markdown-it-py handles extensions differently
        # Most common extensions are already enabled
        pass
    
    def get_extensions(self) -> List[str]:
        """
        Get list of currently enabled extensions.
        
        Returns:
            List of extension names (for compatibility)
        """
        return ['table', 'strikethrough', 'linkify', 'typographer']


def parse_markdown(markdown_text: str, extensions: Optional[List[str]] = None) -> str:
    """
    Convenience function to parse markdown text to HTML.
    
    Args:
        markdown_text: Raw markdown content
        extensions: List of extensions (for compatibility)
        
    Returns:
        HTML string
    """
    parser = MarkdownParser(extensions)
    return parser.parse(markdown_text)


def parse_markdown_slides(markdown_text: str, extensions: Optional[List[str]] = None) -> List[str]:
    """
    Convenience function to parse markdown text and split on page breaks.
    
    Args:
        markdown_text: Raw markdown content
        extensions: List of extensions (for compatibility)
        
    Returns:
        List of HTML strings, one per slide
    """
    parser = MarkdownParser(extensions)
    return parser.parse_with_page_breaks(markdown_text) 