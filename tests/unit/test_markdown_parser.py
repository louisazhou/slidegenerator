"""Test markdown parser functionality."""

import tempfile
from pathlib import Path

import pytest
from slide_generator.markdown_parser import MarkdownParser


@pytest.fixture
def temp_base_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_basic_markdown_parsing(temp_base_dir):
    """Test basic markdown to HTML conversion."""
    parser = MarkdownParser(base_dir=temp_base_dir)

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


def test_code_block_parsing(temp_base_dir):
    """Test code block parsing with fenced_code extension."""
    parser = MarkdownParser(base_dir=temp_base_dir)

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


def test_table_parsing(temp_base_dir):
    """Test table parsing with tables extension."""
    parser = MarkdownParser(base_dir=temp_base_dir)

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


def test_page_breaks_horizontal_rule(temp_base_dir):
    """Test page break handling with horizontal rules."""
    parser = MarkdownParser(base_dir=temp_base_dir)

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


def test_empty_content_handling(temp_base_dir):
    """Test handling of empty or whitespace content."""
    parser = MarkdownParser(base_dir=temp_base_dir)

    # Empty content
    html_slides = parser.parse_with_page_breaks("")
    assert len(html_slides) == 0

    # Whitespace only
    html_slides = parser.parse_with_page_breaks("   \n\n   ")
    assert len(html_slides) == 0

    # Empty slides with page breaks
    html_slides = parser.parse_with_page_breaks("---\n\n---")
    assert len(html_slides) == 0


def test_parser_reset(temp_base_dir):
    """Test that parser resets properly between uses."""
    parser = MarkdownParser(base_dir=temp_base_dir)

    # Parse first content
    html1 = parser.parse("# First")
    assert "<h1>First</h1>" in html1

    # Parse different content
    html2 = parser.parse("# Second")
    assert "<h1>Second</h1>" in html2
    assert "First" not in html2


def test_enhanced_extensions_integration(temp_base_dir):
    """Test that enhanced markdown extensions work correctly together."""
    parser = MarkdownParser(base_dir=temp_base_dir)

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


def test_enhanced_page_break_formats(temp_base_dir):
    """Test all supported page break formats."""
    parser = MarkdownParser(base_dir=temp_base_dir)

    # Test various page break formats (HTML comment variant removed)
    test_cases = [
        # Horizontal rule
        ("# Page 1\n\n---\n\n# Page 2", 2),

        # Explicit [slide] directive
        ("# Page 1\n\n[slide]\n\n# Page 2", 2),

        # Alternate horizontal rules
        ("# Page 1\n\n***\n\n# Page 2", 2),
        ("# Page 1\n\n* * *\n\n# Page 2", 2),

        # Thematic break with spaces
        ("# Page 1\n\n- - -\n\n# Page 2", 2),
    ]

    for md_input, expected_slides in test_cases:
        html_slides = parser.parse_with_page_breaks(md_input)
        assert len(html_slides) == expected_slides, f"Failed on: {md_input}"


def test_page_break_counting(temp_base_dir):
    """Test that page break counting is accurate."""
    parser = MarkdownParser(base_dir=temp_base_dir)
    
    markdown_with_breaks = """
# Slide 1
Content...
---
# Slide 2
More...
[slide]
# Slide 3
"""
    assert parser.count_page_breaks(markdown_with_breaks) == 2


def test_slide_count_estimation(temp_base_dir):
    """Test that slide count estimation is correct."""
    parser = MarkdownParser(base_dir=temp_base_dir)
    
    markdown_with_breaks = """
# Slide 1
---
# Slide 2
[slide]
# Slide 3
"""
    assert parser.estimate_slide_count(markdown_with_breaks) == 3
    assert parser.estimate_slide_count("# Just one slide") == 1
    assert parser.estimate_slide_count("") == 0


def test_page_break_edge_cases(temp_base_dir):
    """Test edge cases for page break handling."""
    parser = MarkdownParser(base_dir=temp_base_dir)
    
    # Break at the very beginning
    md1 = "---\n# Slide"
    slides1 = parser.parse_with_page_breaks(md1)
    assert len(slides1) == 1
    assert "<h1>Slide</h1>" in slides1[0]
    
    # Break at the very end
    md2 = "# Slide\n---"
    slides2 = parser.parse_with_page_breaks(md2)
    assert len(slides2) == 1
    assert "<h1>Slide</h1>" in slides2[0]
    
    # Multiple breaks together
    md3 = "# Slide 1\n---\n---\n# Slide 2"
    slides3 = parser.parse_with_page_breaks(md3)
    assert len(slides3) == 2
    
    # No content between breaks
    md4 = "# Slide 1\n---\n\n---\n# Slide 2"
    slides4 = parser.parse_with_page_breaks(md4)
    assert len(slides4) == 2

    # Breaks inside code blocks should be ignored
    md5 = """
```
---
```
"""
    slides5 = parser.parse_with_page_breaks(md5)
    assert len(slides5) == 1
    assert "<hr>" not in slides5[0]


def test_page_break_not_confused_with_content(temp_base_dir):
    """Ensure page breaks aren't triggered by similar-looking content."""
    parser = MarkdownParser(base_dir=temp_base_dir)

    # Content that looks like a page break but isn't
    test_cases = [
        "Text with --- inside it",
        "A line with more than three --- like so -----",
        "Some text\n---\nand more on same line",
        "Not a [slide] if it has text after it",
        "What about a `[slide]` in code?",
        "Or a line with just [slide"
    ]

    for content in test_cases:
        slides = parser.parse_with_page_breaks(content)
        assert len(slides) == 1, f"Failed on content: {content}"
        
        
def test_page_break_whitespace_handling(temp_base_dir):
    """Test that page breaks work with various amounts of whitespace."""
    parser = MarkdownParser(base_dir=temp_base_dir)
    
    # Whitespace around page breaks
    md = "# Slide 1\n\n   ---   \n\n# Slide 2\n\n  [slide]  \n\n# Slide 3"
    slides = parser.parse_with_page_breaks(md)
    assert len(slides) == 3
    assert "<h1>Slide 1</h1>" in slides[0]
    assert "<h1>Slide 2</h1>" in slides[1]
    assert "<h1>Slide 3</h1>" in slides[2] 