"""Test layout engine functionality."""

import pytest
from src.slide_generator.layout_engine import LayoutEngine
from src.slide_generator.models import Block


def test_basic_markdown_conversion():
    """Test basic markdown to HTML conversion."""
    engine = LayoutEngine()
    markdown_text = """# Hello World

This is a paragraph.

## Section 2

- Item 1
- Item 2
"""
    pages = engine.measure_and_paginate(markdown_text)
    
    # Should produce at least one page
    assert len(pages) >= 1
    
    # First page should have blocks
    assert len(pages[0]) > 0
    
    # Should have heading blocks
    headings = [block for page in pages for block in page if block.is_heading()]
    assert len(headings) >= 2  # h1 and h2
    
    # Should have list blocks (ul/ol elements)
    lists = [block for page in pages for block in page if block.is_list()]
    assert len(lists) >= 1  # one list element


def test_page_break_handling():
    """Test that page breaks create separate pages."""
    engine = LayoutEngine()
    markdown_text = """# Page 1

Content for page 1.

---

# Page 2

Content for page 2.

<!-- slide -->

# Page 3

Content for page 3."""

    pages = engine.measure_and_paginate(markdown_text)
    
    # Should create exactly 3 pages
    assert len(pages) == 3
    
    # Each page should have content
    for page in pages:
        assert len(page) > 0


def test_code_block_handling():
    """Test that code blocks are properly identified."""
    engine = LayoutEngine()
    markdown_text = """# Code Example

Here's some code:

```python
def hello():
    print("Hello, world!")
```

More text after code."""

    pages = engine.measure_and_paginate(markdown_text)
    
    # Should have at least one page
    assert len(pages) >= 1
    
    # Should have code blocks
    code_blocks = [block for page in pages for block in page if block.is_code_block()]
    assert len(code_blocks) >= 1


def test_empty_content():
    """Test handling of empty or whitespace-only content."""
    engine = LayoutEngine()
    
    # Empty content
    pages = engine.measure_and_paginate("")
    assert len(pages) == 0
    
    # Whitespace only
    pages = engine.measure_and_paginate("   \n\n   ")
    assert len(pages) == 0


def test_pagination_with_height_limit():
    """Test that content is properly paginated based on height."""
    engine = LayoutEngine()
    
    # Create content with many items that should exceed page height
    markdown_text = "# Large Content\n\n" + "\n\n".join([f"## Section {i}\n\nContent for section {i}." for i in range(20)])
    
    pages = engine.measure_and_paginate(markdown_text, page_height=300)  # Smaller page height
    
    # Should create multiple pages due to height constraints
    assert len(pages) > 1 