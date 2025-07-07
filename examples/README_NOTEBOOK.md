# Notebook API Documentation

The Notebook API provides a new way to create slides by providing markdown content per slide, along with figure generation functions and pandas DataFrames for tables.

## Overview

Instead of building slides element by element, you provide:
1. **Markdown content** for each slide
2. **Figure functions** that generate matplotlib figures
3. **DataFrames** for tables (using `df.to_markdown(index=False)`)

The API processes your markdown content, generates figures on-the-fly, and converts DataFrames to markdown tables.

## Basic Usage

```python
from slide_generator import SlideNotebook
import pandas as pd

# Create notebook
notebook = SlideNotebook(theme="default", debug=True)

# Add a slide with markdown content
markdown_content = """
# My Slide Title

Here's some text with a figure:

![my_chart]()

And here's a table:

{{sales_data}}
"""

def create_chart():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 2])
    return fig

# Use pandas DataFrame directly
sales_data = pd.DataFrame({
    'Quarter': ['Q1', 'Q2', 'Q3', 'Q4'],
    'Sales': [100, 150, 120, 180]
})

notebook.new_slide(
    markdown_content,
    figure_functions={'my_chart': create_chart},
    dataframes={'sales_data': sales_data}
)

# Generate presentation
notebook.save("output/presentation.pptx")
```

## API Reference

### SlideNotebook Class

#### Constructor
```python
SlideNotebook(theme="default", debug=False)
```

- `theme`: Theme name ("default" or "dark")
- `debug`: Enable debug output

#### Methods

##### `new_slide(markdown_content, figure_functions=None, dataframes=None)`

Add a new slide with markdown content.

**Parameters:**
- `markdown_content` (str): Markdown text for the slide
- `figure_functions` (dict, optional): Dict mapping figure names to functions
- `dataframes` (dict, optional): Dict mapping table names to DataFrames

**Figure References:**
Use `![figure_name]()` syntax in markdown to reference figures.

**Table References:**
Use `{{table_name}}` syntax in markdown to reference tables.

##### `set_theme(theme)`

Change the theme.

##### `save(output_path)`

Generate and save the presentation.

##### `preview_markdown()`

Get combined markdown for debugging.

## Figure Functions

Figure functions should return matplotlib Figure objects:

```python
def create_bar_chart():
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.bar(['A', 'B', 'C'], [1, 2, 3])
    ax.set_title('My Chart')
    return fig

notebook.new_slide(
    "# Chart Slide\n\n![my_chart]()",
    figure_functions={'my_chart': create_bar_chart}
)
```

### Chart Helper Functions

The `examples/chart_helpers.py` file provides convenience functions for common chart types:

```python
from chart_helpers import create_bar_chart, create_line_chart, create_scatter_plot, create_pie_chart

def my_sales_chart():
    data = {
        'categories': ['Q1', 'Q2', 'Q3', 'Q4'],
        'values': [120, 150, 180, 200]
    }
    return create_bar_chart(
        data, 
        title='Quarterly Sales',
        xlabel='Quarter',
        ylabel='Sales (K$)',
        color='steelblue'
    )
```

Available helper functions:
- `create_bar_chart(data, title, xlabel, ylabel, **kwargs)`
- `create_line_chart(data, title, xlabel, ylabel, **kwargs)`
- `create_scatter_plot(data, title, xlabel, ylabel, **kwargs)`
- `create_pie_chart(data, title, **kwargs)`
- `create_histogram(data, title, xlabel, ylabel, **kwargs)`

## DataFrame Tables

The API uses pandas DataFrame's `to_markdown(index=False)` method directly:

```python
import pandas as pd

# Create DataFrame
df = pd.DataFrame({
    'Name': ['Alice', 'Bob'],
    'Age': [25, 30],
    'City': ['New York', 'London']
})

notebook.new_slide(
    "# Table Slide\n\n{{my_table}}",
    dataframes={'my_table': df}
)
```

The DataFrame will be automatically converted to a clean markdown table.

## Notebook-Style Development

Structure your code in blocks like a Jupyter notebook:

```python
#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
from slide_generator import SlideNotebook
from chart_helpers import create_bar_chart

# %%
# Initialize the notebook
notebook = SlideNotebook(theme="default", debug=True)

# %%
# Slide 1: Title slide
slide1_markdown = """
# My Presentation

## Subtitle

Content goes here...
"""

notebook.new_slide(slide1_markdown)

# %%
# Slide 2: Chart slide
slide2_markdown = """
# Data Analysis

![sales_chart]()

Key insights:
- Point 1
- Point 2
"""

def create_sales_chart():
    data = {'categories': ['A', 'B', 'C'], 'values': [1, 2, 3]}
    return create_bar_chart(data, title='Sales Data')

notebook.new_slide(
    slide2_markdown,
    figure_functions={'sales_chart': create_sales_chart}
)

# %%
# Slide 3: Table slide
slide3_markdown = """
# Data Table

{{my_data}}
"""

my_data = pd.DataFrame({
    'Item': ['X', 'Y', 'Z'],
    'Value': [10, 20, 30]
})

notebook.new_slide(
    slide3_markdown,
    dataframes={'my_data': my_data}
)

# %%
# Generate presentations
notebook.save("output/my_presentation.pptx")
```

## Markdown Features

The API supports all standard markdown features:

### Headings
```markdown
# Heading 1
## Heading 2
### Heading 3
```

### Text Formatting
```markdown
**Bold text**
*Italic text*
`Code text`
```

### Lists
```markdown
- Bullet point 1
- Bullet point 2

1. Numbered item 1
2. Numbered item 2
```

### Math Equations
```markdown
Inline math: $E = mc^2$

Display math:
$$\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}$$
```

### Code Blocks
```markdown
```python
def hello():
    print("Hello, World!")
```
```

## Figure Rendering

Figures are automatically:
- Generated from your functions
- Saved to `output/debug_assets/` directory
- Referenced correctly in both HTML and PowerPoint
- Cached for reuse across themes

The HTML output will show figures correctly since they're saved to permanent paths.

## Complete Example

See `examples/notebook_example.py` for a complete working example with:
- 8 slides with varied content
- Multiple chart types using helper functions
- DataFrames converted to tables
- Math equations
- Both default and dark themes
- Notebook-style code organization

## Debugging

Enable debug mode to see processing details:

```python
notebook = SlideNotebook(debug=True)
```

This will show:
- Slide creation progress
- Figure generation and file paths
- DataFrame table conversion
- Markdown processing steps

Use `preview_markdown()` to see the generated markdown:

```python
print(notebook.preview_markdown())
```

## Themes

Two themes are available:
- `"default"`: Light theme with professional styling
- `"dark"`: Dark theme with high contrast

Switch themes anytime:

```python
notebook.set_theme("dark")
```

## Error Handling

The API handles errors gracefully:

- **Missing figures**: Shows `*[Figure not found: name]*`
- **Figure generation errors**: Shows `*[Figure generation failed: name]*`
- **Missing tables**: Shows `*[Table not found: name]*`
- **Table processing errors**: Shows `*[Table processing failed: name]*`

## File Organization

```
examples/
├── chart_helpers.py          # Convenience chart functions
├── notebook_example.py       # Complete working example
└── README_NOTEBOOK.md        # This documentation

output/
├── debug_assets/             # Generated figure images
├── notebook_example_default.pptx
└── notebook_example_dark.pptx
```

## Tips

1. **Figure naming**: Use descriptive names that match your markdown references
2. **DataFrames**: Use pandas DataFrames for cleanest table formatting
3. **Debug mode**: Always use debug mode during development
4. **Code blocks**: Organize your code in `# %%` blocks like a notebook
5. **Chart helpers**: Use the provided helper functions for common chart types
6. **Themes**: Generate both light and dark versions for different contexts
7. **File paths**: Images are saved permanently in `debug_assets/` for HTML viewing 