"""Test markdown parser functionality."""

import pytest
from src.slide_generator.markdown_parser import MarkdownParser, parse_markdown, parse_markdown_slides


def test_basic_markdown_parsing():
    """Test basic markdown to HTML conversion."""
    parser = MarkdownParser()
    
    markdown_text = """# Hello World

This is a paragraph.

## Section 2

- Item 1
- Item 2"""
    
    html = parser.parse(markdown_text)
    
    # Should contain basic HTML elements
    assert "<h1>Hello World</h1>" in html
    assert "<h2>Section 2</h2>" in html
    assert "<p>This is a paragraph.</p>" in html
    assert "<ul>" in html
    assert "<li>Item 1</li>" in html


def test_code_block_parsing():
    """Test code block parsing with fenced_code extension."""
    parser = MarkdownParser()
    
    markdown_text = """# Code Example

```python
def hello():
    print("world")
```"""
    
    html = parser.parse(markdown_text)
    
    # Should contain code block
    assert "<pre><code" in html
    assert "def hello():" in html
    assert "python" in html


def test_table_parsing():
    """Test table parsing with tables extension."""
    parser = MarkdownParser()
    
    markdown_text = """# Table Example

| Name | Age |
|------|-----|
| John | 25  |
| Jane | 30  |"""
    
    html = parser.parse(markdown_text)
    
    # Should contain table elements
    assert "<table>" in html
    assert "<th>Name</th>" in html
    assert "<th>Age</th>" in html
    assert "<td>John</td>" in html
    assert "<td>25</td>" in html


def test_page_breaks_horizontal_rule():
    """Test page break handling with horizontal rules."""
    parser = MarkdownParser()
    
    markdown_text = """# Page 1

Content for page 1.

---

# Page 2

Content for page 2."""
    
    html_slides = parser.parse_with_page_breaks(markdown_text)
    
    # Should create 2 slides
    assert len(html_slides) == 2
    
    # First slide should contain Page 1
    assert "<h1>Page 1</h1>" in html_slides[0]
    assert "Content for page 1" in html_slides[0]
    
    # Second slide should contain Page 2
    assert "<h1>Page 2</h1>" in html_slides[1]
    assert "Content for page 2" in html_slides[1]


def test_page_breaks_html_comment():
    """Test page break handling with HTML comments."""
    parser = MarkdownParser()
    
    markdown_text = """# Page 1

Content for page 1.

<!-- slide -->

# Page 2

Content for page 2."""
    
    html_slides = parser.parse_with_page_breaks(markdown_text)
    
    # Should create 2 slides
    assert len(html_slides) == 2
    
    # Verify content distribution
    assert "<h1>Page 1</h1>" in html_slides[0]
    assert "<h1>Page 2</h1>" in html_slides[1]


def test_empty_content_handling():
    """Test handling of empty or whitespace content."""
    parser = MarkdownParser()
    
    # Empty content
    html_slides = parser.parse_with_page_breaks("")
    assert len(html_slides) == 0
    
    # Whitespace only
    html_slides = parser.parse_with_page_breaks("   \n\n   ")
    assert len(html_slides) == 0
    
    # Empty slides with page breaks
    html_slides = parser.parse_with_page_breaks("---\n\n---")
    assert len(html_slides) == 0


def test_extension_management():
    """Test extension adding and listing."""
    parser = MarkdownParser(extensions=['table'])
    
    # Should start with table
    extensions = parser.get_extensions()
    assert 'table' in extensions
    
    # Add new extension (note: markdown-it-py has built-in extensions)
    parser.add_extension('footnotes')  # This is a no-op in markdown-it-py
    extensions = parser.get_extensions()
    # Should still have the original extensions since add_extension is a compatibility stub
    assert 'table' in extensions
    
    # Don't add duplicates
    parser.add_extension('table')
    extensions = parser.get_extensions()
    assert extensions.count('table') == 1


def test_convenience_functions():
    """Test convenience functions for simple usage."""
    markdown_text = "# Test\n\nContent"
    
    # Simple parse
    html = parse_markdown(markdown_text)
    assert "<h1>Test</h1>" in html
    assert "<p>Content</p>" in html
    
    # Parse slides
    slides = parse_markdown_slides(markdown_text)
    assert len(slides) == 1
    assert "<h1>Test</h1>" in slides[0]


def test_custom_extensions():
    """Test parser with custom extensions."""
    # Test with minimal extensions
    parser = MarkdownParser(extensions=['markdown.extensions.extra'])
    
    markdown_text = "# Test\n\nContent"
    html = parser.parse(markdown_text)
    
    assert "<h1>Test</h1>" in html
    assert "<p>Content</p>" in html


def test_parser_reset():
    """Test that parser resets properly between uses."""
    parser = MarkdownParser()
    
    # Parse first content
    html1 = parser.parse("# First")
    assert "<h1>First</h1>" in html1
    
    # Parse different content
    html2 = parser.parse("# Second")
    assert "<h1>Second</h1>" in html2
    assert "First" not in html2 


def test_enhanced_extensions_integration():
    """Test that enhanced markdown extensions work correctly together."""
    parser = MarkdownParser()
    
    # Test content with tables, fenced code, and lists
    markdown_text = """# Enhanced Features Demo

## Tables Work
| Feature | Status |
|---------|--------|
| Tables  | ✅     |
| Code    | ✅     |
| Lists   | ✅     |

## Fenced Code Blocks
```python
def test_function():
    return "This should work!"
```

## Better Lists
1. First item
2. Second item with bullets:
   - Nested bullet
   - Another nested item
3. Third item

## Inline Code
Use `inline code` for small snippets."""
    
    html = parser.parse(markdown_text)
    
    # Verify tables extension
    assert "<table>" in html
    assert "<thead>" in html
    assert "<tbody>" in html
    assert "<th>Feature</th>" in html
    assert "<td>Tables</td>" in html
    
    # Verify fenced_code extension  
    assert '<pre><code class="language-python">' in html
    assert "def test_function():" in html
    
    # Verify enhanced lists (from extra extension)
    assert "<ol>" in html
    assert "<li>First item</li>" in html
    
    # Check for nested list structure (may be nested ul inside li)
    assert "Nested bullet" in html
    assert "Another nested item" in html
    
    # Verify inline code
    assert "<code>inline code</code>" in html
    
    # Verify all expected content is present
    assert "Enhanced Features Demo" in html
    assert "This should work!" in html 


def test_enhanced_page_break_formats():
    """Test all supported page break formats."""
    parser = MarkdownParser()
    
    # Test various page break formats
    test_cases = [
        # Horizontal rule
        ("# Page 1\n\n---\n\n# Page 2", 2),
        
        # HTML comments (various formats)
        ("# Page 1\n\n<!-- slide -->\n\n# Page 2", 2),
        ("# Page 1\n\n<!-- Slide -->\n\n# Page 2", 2),
        ("# Page 1\n\n<!-- SLIDE -->\n\n# Page 2", 2),
        ("# Page 1\n\n<!--slide-->\n\n# Page 2", 2),
        
        # NewSlide directive
        ("# Page 1\n\n<!-- NewSlide: Title -->\n\n# Page 2", 2),
        ("# Page 1\n\n<!--NewSlide:-->\n\n# Page 2", 2),
        
        # Explicit [slide] directive
        ("# Page 1\n\n[slide]\n\n# Page 2", 2),
        
        # Alternate horizontal rules
        ("# Page 1\n\n***\n\n# Page 2", 2),
        ("# Page 1\n\n****\n\n# Page 2", 2),
        ("# Page 1\n\n___\n\n# Page 2", 2),
        ("# Page 1\n\n____\n\n# Page 2", 2),
        
        # Multiple breaks
        ("# Page 1\n\n---\n\n# Page 2\n\n<!-- slide -->\n\n# Page 3", 3),
        
        # No breaks
        ("# Single Page\n\nContent here", 1),
    ]
    
    for markdown_text, expected_count in test_cases:
        html_slides = parser.parse_with_page_breaks(markdown_text)
        assert len(html_slides) == expected_count, (
            f"Expected {expected_count} slides, got {len(html_slides)} "
            f"for markdown: {repr(markdown_text[:50])}"
        )


def test_page_break_counting():
    """Test page break counting functionality."""
    parser = MarkdownParser()
    
    test_cases = [
        ("# Single slide", 0),
        ("# Page 1\n\n---\n\n# Page 2", 1),
        ("# P1\n\n---\n\n# P2\n\n<!-- slide -->\n\n# P3", 2),
        ("# P1\n\n***\n\n# P2\n\n___\n\n# P3\n\n[slide]\n\n# P4", 3),
        ("", 0),
        ("   \n\n   ", 0),
    ]
    
    for markdown_text, expected_breaks in test_cases:
        break_count = parser.count_page_breaks(markdown_text)
        assert break_count == expected_breaks, (
            f"Expected {expected_breaks} breaks, got {break_count} "
            f"for: {repr(markdown_text[:30])}"
        )


def test_slide_count_estimation():
    """Test slide count estimation."""
    parser = MarkdownParser()
    
    test_cases = [
        ("# Single slide", 1),
        ("# Page 1\n\n---\n\n# Page 2", 2),
        ("# P1\n\n---\n\n# P2\n\n<!-- slide -->\n\n# P3", 3),
        ("", 0),
    ]
    
    for markdown_text, expected_slides in test_cases:
        slide_count = parser.estimate_slide_count(markdown_text)
        assert slide_count == expected_slides, (
            f"Expected {expected_slides} slides, got {slide_count} "
            f"for: {repr(markdown_text[:30])}"
        )


def test_page_break_edge_cases():
    """Test edge cases in page break handling."""
    parser = MarkdownParser()
    
    # Test content with only page breaks (should result in empty slides list)
    empty_breaks_content = "---\n\n<!-- slide -->\n\n***"
    html_slides = parser.parse_with_page_breaks(empty_breaks_content)
    assert len(html_slides) == 0, "Only page breaks should result in no slides"
    
    # Test mixed content with some empty slides
    mixed_content = """# First slide

Some content here.

---



---

# Third slide

More content.

[slide]

# Fourth slide"""
    
    html_slides = parser.parse_with_page_breaks(mixed_content)
    assert len(html_slides) == 3, "Should skip empty slides but keep content slides"
    
    # Verify content is in right slides
    assert "First slide" in html_slides[0]
    assert "Third slide" in html_slides[1] 
    assert "Fourth slide" in html_slides[2]


def test_page_break_not_confused_with_content():
    """Test that page breaks aren't confused with similar content."""
    parser = MarkdownParser()
    
    # Test content that looks like page breaks but isn't
    not_breaks_content = """# Test Slide

Here's some code with dashes:
```
var x = y - z - w;
```

And here's a list:
- Item with --- dashes
- Another item

<!-- This is a comment but not: slide -->

This [slide] word should not break.

These *stars* are not page breaks.
These _underscores_ are not breaks either.
"""
    
    html_slides = parser.parse_with_page_breaks(not_breaks_content)
    assert len(html_slides) == 1, "Should be one slide with no page breaks"
    
    # Verify all content is preserved
    html = html_slides[0]
    assert "var x = y - z - w;" in html
    assert "Item with --- dashes" in html
    assert "This is a comment but not: slide" in html
    assert "This [slide] word" in html


def test_page_break_whitespace_handling():
    """Test page break detection with various whitespace."""
    parser = MarkdownParser()
    
    # Test breaks with extra whitespace
    whitespace_content = """# Page 1

  ---  

# Page 2

    <!-- slide -->    

# Page 3

	[slide]	

# Page 4"""
    
    html_slides = parser.parse_with_page_breaks(whitespace_content)
    assert len(html_slides) == 4, "Should handle whitespace around page breaks" 