# Project Structure Documentation

## 📁 Directory Structure

```
Slide_generate/
├── slide_generator/           # Core package
│   ├── __init__.py           # Package initialization
│   ├── generator.py          # Main SlideGenerator class
│   ├── models.py             # Data models (Block, etc.)
│   ├── markdown_parser.py    # Markdown to HTML conversion
│   ├── layout_engine.py      # HTML measurement & pagination
│   ├── layout_parser.py      # HTML to Block conversion
│   ├── pptx_renderer.py      # PowerPoint generation
│   ├── theme_loader.py       # CSS theme loading (simplified)
│   ├── math_renderer.py      # KaTeX math rendering
│   ├── notebook.py           # Jupyter notebook integration
│   └── paths.py              # Path utilities
├── themes/                   # CSS theme files
│   ├── default.css          # Default light theme
│   └── dark.css             # Dark theme
├── examples/                 # Demo scripts and assets
│   ├── comprehensive_demo.py # Full feature demonstration
│   ├── notebook_example.py  # Jupyter notebook demo
│   ├── demo_content.md      # Sample markdown content
│   ├── chart_helpers.py     # Chart generation utilities
│   ├── assets/              # Sample images
│   └── output/              # Generated presentations
├── tests/                   # Test suite
│   ├── unit/                # Unit tests
│   └── visual/              # Visual regression tests
├── requirements.txt         # Python dependencies
└── pytest.ini             # Test configuration
```

## **Architecture Overview**

The slide generator follows a streamlined pipeline architecture:

1. **Markdown Input** → `MarkdownParser` converts to HTML
2. **HTML Processing** → `LayoutEngine` measures elements and paginates
3. **Block Conversion** → `LayoutParser` converts HTML to Block objects
4. **PowerPoint Output** → `PPTXRenderer` generates final presentation

Key simplifications made:
- **Single CSS Loading**: Each component loads CSS once per instance
- **Direct Theme Access**: No complex caching or configuration objects
- **Streamlined Processing**: Removed redundant HTML parsing steps
- **Simplified Imports**: Cleaner dependency structure

## 📋 File Registry & Purposes

### Core Package Files

- **`generator.py`**: Main orchestrator class that coordinates the entire pipeline
- **`models.py`**: Data structures (Block, table definitions, etc.)
- **`markdown_parser.py`**: Converts markdown to HTML with plugins (math, tables, admonitions)
- **`layout_engine.py`**: Measures HTML elements and handles pagination logic
- **`layout_parser.py`**: Converts measured HTML into Block objects for PowerPoint
- **`pptx_renderer.py`**: Generates PowerPoint presentations from Block objects
- **`theme_loader.py`**: Simple CSS loading without complex caching
- **`math_renderer.py`**: KaTeX integration for mathematical expressions
- **`notebook.py`**: Jupyter notebook integration and preview functionality
- **`paths.py`**: Path resolution utilities

### Theme System

- **`themes/default.css`**: Light theme with comprehensive styling
- **`themes/dark.css`**: Dark theme variant
- CSS variables in `:root` sections define colors and spacing
- Direct CSS loading without intermediate configuration objects

### Examples & Demos

- **`comprehensive_demo.py`**: Showcases all features (tables, math, themes, etc.)
- **`notebook_example.py`**: Jupyter notebook integration demo
- **`demo_content.md`**: Sample markdown content for testing
- **`chart_helpers.py`**: Utilities for generating sample charts

### Testing

- **`tests/unit/`**: Unit tests for individual components
- **`tests/visual/`**: Visual regression tests using image comparison
- **`pytest.ini`**: Test configuration and markers 