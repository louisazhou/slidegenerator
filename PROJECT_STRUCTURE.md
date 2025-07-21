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
│   ├── theme_loader.py       # CSS theme loading
│   ├── css_utils.py          # Centralized CSS parsing utilities
│   ├── math_renderer.py      # KaTeX math rendering
│   ├── notebook.py           # Jupyter notebook integration
│   └── paths.py              # Path utilities & temp file management
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

## **📊 Algorithm Pipeline Overview**

The slide generator follows a sophisticated **browser-guided layout pipeline** that ensures accurate visual presentation by leveraging real browser rendering for measurements:

```
Input Markdown
      ↓
[1] MarkdownParser → HTML + KaTeX Math
      ↓
[2] LayoutEngine → Browser Measurement & Pagination  
      ↓
[3] LayoutParser → Structured Block Objects
      ↓
[4] PPTXRenderer → PowerPoint Presentation
      ↓
Output: .pptx + .html
```

### **🔄 Detailed Algorithm Steps**

#### **Step 1: Markdown Processing & Math Rendering**
```python
# Input: Raw markdown text
markdown_text = """
# My Slide
Here's some math: $E = mc^2$
![Chart|0.8x](./chart.png)
"""

# MarkdownParser processes:
1. **Plugin Integration**: Tables, admonitions, math syntax
2. **KaTeX Math Rendering**: LaTeX → PNG images in temp directory  
3. **Image Path Resolution**: Relative paths → absolute file:// URLs
4. **Custom Syntax**: Image scaling ![alt|0.8x](path) → data-scale-x="0.8"
5. **Output**: Clean HTML with embedded math images and metadata
```

#### **Step 2: Browser-Based Layout Engine**
```python
# LayoutEngine: The core intelligence of the system
async def measure_and_paginate(markdown_text):
    1. **HTML Preprocessing**: Add unique block IDs (BIDs)
    2. **CSS Theme Loading**: Apply slide dimensions and styling
    3. **Browser Launch**: Headless Chrome with slide viewport
    4. **Element Measurement**: Get precise width/height/position
    5. **Image Scaling Logic**: 6-step intelligent scaling algorithm
    6. **Pagination Algorithm**: Height-based page breaks with content grouping
    7. **Output**: List[List[Block]] - pages of positioned elements
```

**🖼️ Image Scaling Algorithm (6 Steps):**
1. **Parse Request**: Extract scale factors from data-scale-x/y attributes
2. **Calculate Target**: Apply percentage to available width/height
3. **Check Constraints**: Will the image fit on current page?
4. **Calculate Available Space**: Height minus content above this element
5. **Adjust if Needed**: Reverse-engineer scaling to fit available space
6. **Apply Final Dimensions**: Update Block object with precise pixel sizes

**📄 Pagination Algorithm:**
```python
def paginate_blocks(blocks, max_height_px):
    pages = []
    current_page = []
    current_height = 0
    
    for block in blocks:
        # Check if adding this block would exceed page height
        if current_height + block.height > max_height_px:
            # Start new page, but keep headings with their content
            if current_page:
                pages.append(current_page)
            current_page = [block]
            current_height = block.height
        else:
            current_page.append(block)
            current_height += block.height
    
    # Add final page
    if current_page:
        pages.append(current_page)
```

#### **Step 3: Structured Layout Parsing**
```python
# LayoutParser: Convert HTML elements to PowerPoint-ready objects
await parse_html_with_structured_layout(html):
    1. **pptx-box Wrapper**: Inject JavaScript to wrap elements
    2. **Precise Measurement**: getBoundingClientRect() for each element
    3. **Block Conversion**: HTML elements → Block objects with position/size
    4. **Table Processing**: Complex table structure → PowerPoint table format
    5. **List Merging**: Consecutive list items → single text blocks
    6. **Output**: Precisely positioned Block objects
```

#### **Step 4: PowerPoint Generation**
```python
# PPTXRenderer: Create final presentation
def render(pages, output_path):
    1. **Slide Creation**: One slide per page of blocks
    2. **Coordinate Transformation**: Browser pixels → PowerPoint inches
    3. **Font & Style Application**: CSS values → PowerPoint formatting
    4. **Table Rendering**: Complex table borders, fonts, and spacing
    5. **Image Placement**: Exact positioning from browser measurements
    6. **Math Integration**: PNG math images with baseline alignment
    7. **Output**: Professional PowerPoint presentation
```

### **🎨 Theme System Architecture**

**CSS-Driven Configuration:**
```css
/* themes/default.css */
:root {
    --slide-width: 960px;
    --slide-height: 720px;
    --slide-padding: 40px;
    --slide-font-family: "Segoe UI", sans-serif;
    --text-color: #000000;
    --background-color: #ffffff;
    /* ... more variables */
}

h1 { font-size: 36px; font-weight: bold; }
h2 { font-size: 28px; font-weight: 600; }
table { border: 1px solid var(--table-border-color); }
```

**Centralized CSS Parsing (css_utils.py):**
- **Variable Extraction**: Parse `:root` CSS variables 
- **Font Size Parsing**: Extract typography from CSS rules
- **Color Management**: Handle both hex and color names
- **Dimension Calculation**: Convert CSS units to pixels
- **Performance Caching**: Cache parsed values for reuse

### **🗂️ File & Path Management**

**Centralized Temporary File Handling (`paths.py`):**
```python
def prepare_workspace(output_dir, keep_tmp=False):
    # Creates: output_dir/.sg_tmp/ for all temporary files
    # Automatic cleanup unless keep_tmp=True
    # Fallback to system temp if output_dir read-only
```

**Consistent Usage Across Components:**
- **Math Renderer**: Uses workspace temp dir for KaTeX PNG cache
- **Layout Engine**: HTML files and browser assets in temp dir  
- **Notebook**: Figure generation in slide-specific temp folders
- **No System Temp**: All temporary files controlled by paths.py

### **⚡ Performance Optimizations**

1. **Image Dimension Caching**: Avoid repeated PIL.Image.open() calls
2. **CSS Parsing Cache**: Parse theme CSS once per component instance
3. **Math Equation Cache**: Rendered math images cached by LaTeX hash
4. **Browser Session Reuse**: Single browser instance for all measurements
5. **Block ID System**: Efficient HTML element tracking with unique identifiers

### **🔧 Advanced Features**

**Mathematical Expression Support:**
- **KaTeX Integration**: High-quality LaTeX rendering
- **Inline & Display Math**: Both `$...$` and `$$...$$` syntax
- **PNG Output**: Math rendered as images for PowerPoint compatibility
- **Baseline Alignment**: Precise vertical positioning of math elements

**Column Layout System:**
```markdown
::: columns
:::: left
Content in left column
::::
:::: right  
Content in right column
::::
:::
```

**Image Scaling Syntax:**
```markdown
![Caption: Chart title|0.8x](./chart.png)  # 80% of available width
![Pie Chart|0.6y](./pie.png)              # 60% of available height
```

**Table Auto-Sizing:**
- **HTML Table Processing**: Complex nested table structures
- **Intelligent Column Distribution**: Based on content width
- **Border & Styling**: CSS-driven table appearance
- **PowerPoint Native Tables**: Full formatting preservation

## **🎯 Key Design Principles**

1. **Browser-First Accuracy**: Use real browser rendering for all measurements
2. **CSS-Driven Theming**: Centralized styling through CSS variables
3. **Modular Architecture**: Each component has a single, clear responsibility
4. **Performance-Conscious**: Caching and optimization at every level
5. **Path Consistency**: All temporary files managed by centralized system
6. **Robust Error Handling**: Graceful fallbacks for missing assets or errors

## 📋 File Registry & Purposes

### Core Package Files

- **`generator.py`**: Main orchestrator class that coordinates the entire pipeline
- **`models.py`**: Data structures (Block, table definitions, etc.)
- **`markdown_parser.py`**: Converts markdown to HTML with plugins (math, tables, admonitions)
- **`layout_engine.py`**: Browser automation, element measurement, and intelligent pagination
- **`layout_parser.py`**: Converts measured HTML into Block objects for PowerPoint
- **`pptx_renderer.py`**: Generates PowerPoint presentations with precise positioning
- **`theme_loader.py`**: Simple CSS file loading utilities
- **`css_utils.py`**: Centralized CSS parsing with caching and variable extraction
- **`math_renderer.py`**: KaTeX integration for mathematical expressions
- **`notebook.py`**: Jupyter notebook-style API with Jinja2 templating
- **`paths.py`**: Centralized path resolution and temporary file management

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