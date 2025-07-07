#!/usr/bin/env python3
"""
Notebook-style slide generation example.

This demonstrates creating slides by providing markdown content per slide,
with figure functions and pandas DataFrames. Each slide is created in a
separate code block to simulate a notebook environment.
"""
# %%
import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Add the parent directory to the path so we can import slide_generator
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slide_generator import SlideNotebook
from chart_helpers import create_bar_chart, create_line_chart, create_scatter_plot, create_pie_chart

# %%
# Initialize the notebook
notebook = SlideNotebook(theme="default", debug=True)

# %%
# Slide 1: Title slide
slide1_markdown = """
# Business Analytics Report

## Q4 2024 Performance Review

**Prepared by:** Data Science Team  
**Date:** December 2024

This presentation covers our quarterly performance metrics, growth trends, and customer insights.
"""

notebook.new_slide(slide1_markdown)

# %%
# Slide 2: Sales performance with chart
slide2_markdown = """
# Quarterly Sales Performance

Our sales team has shown consistent growth throughout the year:

![sales_chart]()

**Key Insights:**
- Q4 achieved highest sales at $200K
- 67% growth from Q1 to Q4
- Exceeded annual target by 15%
"""

def create_sales_chart():
    """Generate a sales bar chart using helper function."""
    data = {
        'categories': ['Q1', 'Q2', 'Q3', 'Q4'],
        'values': [120, 150, 180, 200]
    }
    return create_bar_chart(
        data, 
        title='Quarterly Sales Performance',
        xlabel='Quarter',
        ylabel='Sales (K$)',
        color='steelblue'
    )

notebook.new_slide(
    slide2_markdown,
    figure_functions={'sales_chart': create_sales_chart}
)

# %%
# Slide 3: Growth trends
slide3_markdown = """
# Monthly Growth Analysis

The growth trajectory shows strong momentum:

![growth_trend]()

**Growth Highlights:**
- Consistent month-over-month improvement
- Peak growth of 18.4% in June
- Average monthly growth: 11.3%
"""

def create_growth_trend():
    """Generate a growth trend line chart."""
    data = {
        'x': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
        'y': [5.2, 7.1, 8.9, 12.3, 15.7, 18.4]
    }
    return create_line_chart(
        data,
        title='Monthly Growth Rate',
        xlabel='Month',
        ylabel='Growth Rate (%)',
        color='green',
        linewidth=3,
        markersize=8
    )

notebook.new_slide(
    slide3_markdown,
    figure_functions={'growth_trend': create_growth_trend}
)

# %%
# Slide 4: Customer analysis with table
slide4_markdown = """
# Customer Insights

## Satisfaction vs Loyalty Analysis

![customer_scatter]()

## Regional Performance

{{regional_data}}

**Key Findings:**
- Strong correlation between satisfaction and loyalty
- North region leads in customer retention
- West region shows highest growth potential
"""

def create_customer_scatter():
    """Generate a customer satisfaction scatter plot."""
    np.random.seed(42)
    satisfaction = np.random.normal(8.5, 1.2, 100)
    loyalty = satisfaction * 0.8 + np.random.normal(0, 0.5, 100)
    
    data = {'x': satisfaction, 'y': loyalty}
    return create_scatter_plot(
        data,
        title='Customer Satisfaction vs Loyalty',
        xlabel='Satisfaction Score',
        ylabel='Loyalty Score',
        color='purple',
        alpha=0.6,
        size=60
    )

# Create sample regional data using pandas DataFrame
regional_data = pd.DataFrame({
    'Region': ['North', 'South', 'East', 'West'],
    'Customers': [1250, 980, 1100, 750],
    'Satisfaction': [8.7, 8.2, 8.5, 7.9],
    'Retention': ['94%', '89%', '91%', '86%']
})

notebook.new_slide(
    slide4_markdown,
    figure_functions={'customer_scatter': create_customer_scatter},
    dataframes={'regional_data': regional_data}
)

# %%
# Slide 5: Market share
slide5_markdown = """
# Market Share Analysis

## Product Portfolio Performance

![market_share]()

**Product Performance:**
- Product A maintains market leadership
- Product B shows strong competitive position
- Products C & D have equal market share
- Total market coverage: 100%
"""

def create_market_share():
    """Generate a market share pie chart."""
    data = {
        'labels': ['Product A', 'Product B', 'Product C', 'Product D'],
        'values': [35, 25, 20, 20]
    }
    return create_pie_chart(
        data,
        title='Market Share Distribution',
        colors=['#ff9999', '#66b3ff', '#99ff99', '#ffcc99'],
        startangle=90
    )

notebook.new_slide(
    slide5_markdown,
    figure_functions={'market_share': create_market_share}
)

# %%
# Slide 6: Mathematical analysis
slide6_markdown = """
# Financial Projections

## Revenue Growth Model

Our revenue follows the exponential growth model:

$$R(t) = R_0 \cdot e^{rt}$$

Where:
- $R_0$ = Initial revenue
- $r$ = Growth rate
- $t$ = Time period

**Projected Revenue for 2025:**

Given our current growth rate of $r = 0.15$, we project:

$$R(12) = 650 \cdot e^{0.15 \times 12} = 650 \cdot e^{1.8} ≈ 3,930K$$

This represents a **504% increase** from our current baseline.
"""

notebook.new_slide(slide6_markdown)

# %%
# Slide 7: Mixed content with table and math
slide7_markdown = """
# Investment Analysis

## Portfolio Performance

{{portfolio_data}}

## Risk Assessment

The portfolio risk can be calculated using:

$$\sigma_p = \sqrt{\sum_{i=1}^{n} w_i^2 \sigma_i^2 + \sum_{i=1}^{n} \sum_{j \neq i} w_i w_j \sigma_i \sigma_j \rho_{ij}}$$

**Current Portfolio Risk:** $\sigma_p = 12.3\%$
"""

# Create portfolio data using pandas DataFrame
portfolio_data = pd.DataFrame({
    'Asset': ['Stocks', 'Bonds', 'REITs'],
    'Weight': ['60%', '30%', '10%'],
    'Return': ['8.5%', '4.2%', '6.8%'],
    'Risk': ['15.2%', '6.8%', '12.1%']
})

notebook.new_slide(
    slide7_markdown,
    dataframes={'portfolio_data': portfolio_data}
)

# %%
# Slide 8: Conclusion
slide8_markdown = """
# Key Takeaways

## Summary of Results

1. **Strong Financial Performance**
   - Q4 sales exceeded targets
   - Consistent growth trajectory
   - Positive customer feedback

2. **Market Position**
   - Leading market share in Product A
   - Balanced portfolio across regions
   - High customer satisfaction scores

3. **Future Outlook**
   - Projected 504% revenue growth
   - Low portfolio risk (12.3%)
   - Continued expansion opportunities

## Next Steps

- Expand into West region
- Invest in Product B development
- Maintain customer satisfaction initiatives
"""

notebook.new_slide(slide8_markdown)

# %%
# Generate presentations
print(f"\n📊 Generated {len(notebook)} slides")

# Save default theme
output_path_default = "output/notebook_example_default.pptx"
result_default = notebook.save(output_path_default)
print(f"✅ Default theme saved: {result_default}")

# Save dark theme
notebook.set_theme("dark")
output_path_dark = "output/notebook_example_dark.pptx"
result_dark = notebook.save(output_path_dark)
print(f"✅ Dark theme saved: {result_dark}")

# %%
# Show preview of generated markdown
print("\n📝 Generated Markdown Preview:")
print("=" * 50)
preview = notebook.preview_markdown()
print(preview[:500] + "..." if len(preview) > 500 else preview)

print("\n🎉 Notebook example completed successfully!")
print(f"📁 Output files:")
print(f"   - {result_default}")
print(f"   - {result_dark}") 