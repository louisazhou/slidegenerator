#!/usr/bin/env python3
"""
Jupyter Notebook-style slide generator example.

This demonstrates the enhanced SlideNotebook with:
- Auto-detection of figure functions and dataframes
- Individual slide previews
- {% figure "function_name" width=0.8 caption="text" %} for figures
- {% table "dataframe_name" order_by="col" highlight={...} %} for tables
- Enhanced template variables and filters
"""

# %%
import asyncio
from datetime import datetime
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from slide_generator.notebook import SlideNotebook
from chart_helpers import create_bar_chart, create_line_chart, create_pie_chart

# %%
# Create notebook instance with auto-detection enabled by default
notebook = SlideNotebook(
    output_dir="output",
    theme="default",
    debug=True,  # Enable for individual slide previews
    base_dir=Path(__file__).parent
)

# %%
# ═══ Data Setup ═══

# Sample DataFrames for tables (will be auto-detected)
regional_data = pd.DataFrame({
    'Region': ['North', 'South', 'East', 'West'],
    'Revenue': [1200000, 950000, 1100000, 800000],
    'Growth': [12.5, 8.3, 15.2, 6.7],
    'Satisfaction': [4.2, 3.8, 4.5, 3.6]
})

quarterly_data = pd.DataFrame({
    'Quarter': ['Q1', 'Q2', 'Q3', 'Q4'],
    'Sales': [85, 92, 78, 95],
    'Target': [80, 85, 85, 90],
    'Performance': ['Good', 'Excellent', 'Fair', 'Excellent']
})

# %%
# ═══ Figure Functions (will be auto-detected) ═══

def create_sales_chart():
    """Generate a sales trend chart."""
    quarters = ['Q1', 'Q2', 'Q3', 'Q4']
    sales = [85, 92, 78, 95]
    targets = [80, 85, 85, 90]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(quarters, sales, 'o-', linewidth=3, label='Actual Sales', color='#2E8B57')
    ax.plot(quarters, targets, 's--', linewidth=2, label='Targets', color='#FF6B35')
    ax.set_title('Quarterly Sales Performance', fontsize=16, fontweight='bold')
    ax.set_ylabel('Performance Score')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    return fig

def create_market_share():
    """Generate a market share pie chart."""
    data = {
        'labels': ['Our Company', 'Competitor A', 'Competitor B', 'Others'],
        'values': [35, 25, 20, 20]
    }
    return create_pie_chart(
        data,
        title='Market Share Distribution',
        colors=['#FF6B35', '#F7931E', '#FFD23F', '#C5C5C5'],
        figsize=(8, 8)
    )

def create_growth_trend():
    """Generate a growth trend chart."""
    data = {
        'categories': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
        'values': [5.2, 7.1, 8.5, 12.3, 15.8, 18.2]
    }
    return create_bar_chart(
        data,
        title='Monthly Growth Rate',
        ylabel='Growth Rate (%)',
        color='#2E8B57',
        figsize=(10, 6)
    )

# %%
# ═══ Slide Creation with Auto-Detection ═══

# Title slide
notebook.new_slide("""
# 📊 Advanced Business Analytics
## Quarterly Performance Review

Presented by: **Analytics Team**  
Date: {{date}}  
Quarter: {{quarter}}
""", template_vars={
    'date': 'December 2024',
    'quarter': 'Q4'
})
notebook.preview_slide()

# %%
# Overview with template variables
notebook.new_slide("""
# Executive Summary

## Key Achievements This Quarter

- **Revenue Growth**: {{revenue_growth}}% increase
- **Market Position**: {{market_position | ordinal}} in industry
- **Customer Satisfaction**: {{satisfaction | pct}}
- **Target Achievement**: {{target_achievement | pct}}

> *{{company}}* continues to lead in innovation and customer satisfaction.
""", template_vars={
    'revenue_growth': 15.2,
    'market_position': 2,
    'satisfaction': 0.912,
    'target_achievement': 1.08,
    'company': 'TechCorp Solutions'
})
notebook.preview_slide()

# %%
# Sales analysis with auto-detected figure
notebook.new_slide("""
# Sales Performance Analysis

Our quarterly sales performance shows consistent improvement:

{% figure "create_sales_chart" width=0.8 caption="Quarterly sales performance vs targets showing steady improvement" %}

## Key Insights

- {{style("Q4 exceeded targets", "green", "bold")}} by {{q4_excess}}%
- Average performance: {{avg_performance}}%
- {{style("Trend is positive", "blue", "italic")}} across all quarters
""", template_vars={
    'q4_excess': 5.6,
    'avg_performance': 87.5
})
notebook.preview_slide()

# %%
# Market analysis with auto-detected figure
notebook.new_slide("""
# Market Position

Our market share remains strong in the competitive landscape:

{% figure "create_market_share" height=0.6 caption="Current market share distribution showing our leadership position" %}

### Strategic Advantages

1. {{style("Market Leader", "green", "bold")}}: 35% market share
2. Strong brand recognition
3. Customer loyalty: {{loyalty_score | pct}}
""", template_vars={
    'loyalty_score': 0.847
})
notebook.preview_slide()

# %%
# Regional performance with auto-detected table
notebook.new_slide("""
# Regional Performance Analysis

## Performance by Region

{% table "regional_data" 
   order_by="Revenue" desc=true
   highlight={
       (0, "Revenue"): ["green", "bold"],
       (0, "Growth"): ["green", "bold"],
       (3, "Growth"): ["red", "underline"],
       (2, "Satisfaction"): ["blue", "bold"]
   } %}

### Regional Insights

- **{{best_region}}** leads in revenue with {{best_revenue | money}}
- **East** shows highest growth at {{east_growth}}%
- West region requires attention for growth improvement
""", template_vars={
    'best_region': 'North',
    'best_revenue': 1200000,
    'east_growth': 15.2
})
notebook.preview_slide()

# %%
# Growth trends with auto-detected figure
notebook.new_slide("""
# Growth Trajectory

## Monthly Growth Analysis

{% figure "create_growth_trend" width=0.9 caption="Monthly growth rate showing accelerating trend throughout the year" %}

### Growth Drivers

- **Product Innovation**: {{innovation_impact | pct}} impact
- **Market Expansion**: {{expansion_impact | pct}} contribution  
- **Customer Acquisition**: {{acquisition_rate | pct}} new customers

{{style("Sustained growth expected into next quarter", "green", "bold", "italic")}}
""", template_vars={
    'innovation_impact': 0.32,
    'expansion_impact': 0.28,
    'acquisition_rate': 0.15
})
notebook.preview_slide()

# %%
# Multi-column layout with auto-detected figure and table
notebook.new_slide("""
# Comprehensive Overview

:::columns
:::column {width=60%}

### Performance Metrics

{% figure "create_sales_chart" width=1.0 caption="Performance overview" %}

**Key Highlights:**
- Revenue: {{total_revenue | money}}
- Growth: {{overall_growth | pct}}

:::
:::column {width=40%}

### Quarterly Summary

{% table "quarterly_data" 
   highlight={
       (3, "Performance"): ["green", "bold"]
   } %}

**Status:** {{style("On Track", "green", "bold")}}

:::

:::
""", template_vars={
    'total_revenue': 4050000,
    'overall_growth': 0.126
})
notebook.preview_slide()

# %%
# Action items and next steps
notebook.new_slide("""
# Action Items & Next Steps

## Immediate Actions

1. **{{style("West Region Focus", "red", "bold")}}**
   - Implement growth strategy
   - Target: {{west_target | pct}} improvement

2. **Product Development**
   - Launch new features in {{next_quarter}}
   - Expected impact: {{expected_impact | money}} revenue

3. **Market Expansion**
   - Enter {{new_markets}} new markets
   - Timeline: {{timeline}}

## Success Metrics

- Overall growth target: {{growth_target | pct}}
- Customer satisfaction: {{satisfaction_target | pct}}
- Market share goal: {{market_share_target}}%
""", template_vars={
    'west_target': 0.10,
    'next_quarter': 'Q1 2025',
    'expected_impact': 500000,
    'new_markets': 3,
    'timeline': '6 months',
    'growth_target': 0.18,
    'satisfaction_target': 0.95,
    'market_share_target': 38
})
notebook.preview_slide()

# %%
# Test slide for inline formatting
notebook.new_slide("""
# Inline Formatting Test

This slide tests various inline formatting options:

- **Bold text** and *italic text*
- [Red text]{.red} and [Blue text]{.blue .bold}
- Regular underline with ++underline++
- ^^Wavy underlined text^^ using double caret for ^^emphasized information^^
- ~~Strikethrough text~~ for deleted content
- ==Highlighted text== for important notes

All formatting should render correctly in both HTML and PowerPoint.
""")
notebook.preview_slide()

# %%
# Generate final presentation
try:
    # Save PPTX files
    pptx_default = notebook.save_sync('output/notebook_example_default.pptx')
    
    notebook.set_theme('dark')
    pptx_dark = notebook.save_sync('output/notebook_example_dark.pptx')
    
    print(f"✅ Generated presentations:")
    print(f"   📄 Default theme: {pptx_default}")
    print(f"   📄 Dark theme: {pptx_dark}")
    
except Exception as e:
    print(f"❌ Error generating slides: {e}")
    raise

print("\n🎯 Features demonstrated:")
print("   • Auto-detection of figure functions and dataframes")
print("   • Individual slide previews after creation")
print("   • Jinja2 template syntax: {% figure %} and {% table %}")
print("   • Enhanced filters: ordinal, pct, money")
print("   • Figure captions with Caption: syntax")
print("   • Table highlighting and sorting")
print("   • Template variables and styling")
print("   • Multi-column layouts")
print("   • Advanced template features")

# %% 
