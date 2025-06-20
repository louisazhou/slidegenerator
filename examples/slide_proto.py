#!/usr/bin/env python3
"""
Milestone 0: Overflow-safe Prototype
Demonstrates browser->pptx replay with no overlap using a single file.
"""

import os
import sys
from pathlib import Path

# Add the project root to the path so we can import our modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.slide_generator.generator import SlideGenerator

def main():
    """Generate slides from sample markdown."""
    # Sample markdown content
    markdown_text = """# Welcome to Slide Generator

This is a demo presentation created from markdown.

## Features

- Converts markdown to PowerPoint
- Automatic layout and formatting
- Multiple slide support

---

# Second Slide

This content will be on a separate slide.

## Code Example

```python
def hello_world():
    print("Hello, World!")
    return "Success"
```

## Lists Work Too

1. First item
2. Second item
3. Third item

---

# Final Slide

Thank you for using Slide Generator!

### Questions?

Feel free to reach out for support."""

    # Create generator
    generator = SlideGenerator(debug=True)
    
    # Generate slides
    output_path = "output/demo.pptx"
    result_path = generator.generate(markdown_text, output_path)
    
    print(f"\nSlides successfully generated: {result_path}")
    print("You can now open the PowerPoint file to view your slides!")

if __name__ == "__main__":
    main() 