#!/usr/bin/env python3
"""
Example script to test the slide generator.
"""

import os
import sys
from pathlib import Path

# Add the project root to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slide_generator.generator import SlideGenerator

def main():
    """Run the example script."""
    # Create directory structure if it doesn't exist
    os.makedirs("output", exist_ok=True)
    
    # Example markdown content with multiple slides
    markdown_content = """
# Milestone 2 Demo

## Text Content

This is a paragraph with some text content. The text should automatically fit within the textbox without overflowing.

## List Items

- First bullet point with some text that might be long enough to wrap to the next line
- Second bullet point
- Third bullet point with additional information

---

## Code Example

```python
def hello_world():
    print("Hello, world!")
    # This is a comment
    return True
```

## Two-Column Layout

<div class="two-column">
<div class="column">

### Left Column

- Item 1
- Item 2
- Item 3

</div>
<div class="column">

### Right Column

This is content in the right column.
It should be positioned correctly.

</div>
</div>

<!-- slide -->

# Pagination Test

## Very Long Content

This slide contains a lot of content that should be automatically paginated if it exceeds the maximum slide height.

- Item 1
- Item 2
- Item 3
- Item 4
- Item 5
- Item 6
- Item 7
- Item 8
- Item 9
- Item 10

## More Content

This is additional content that might be pushed to a new slide if needed.

```python
# This is a long code block
def example_function():
    # This function does something interesting
    result = 0
    for i in range(100):
        result += i
    return result
```
"""
    
    # Generate slide
    generator = SlideGenerator()
    generator.generate(markdown_content, "output/example.pptx")

if __name__ == "__main__":
    main() 