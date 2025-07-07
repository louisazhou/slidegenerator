#!/usr/bin/env python3
"""
Chart helper functions for slide generation.

These are convenience functions for common chart types that can be used
with the SlideNotebook API.
"""

import matplotlib.pyplot as plt
import numpy as np


def create_bar_chart(data, title="Bar Chart", xlabel="Categories", ylabel="Values", **kwargs):
    """
    Create a bar chart figure.
    
    Args:
        data: Dict with 'categories' and 'values' keys, or list of tuples
        title: Chart title
        xlabel: X-axis label
        ylabel: Y-axis label
        **kwargs: Additional matplotlib arguments
        
    Returns:
        matplotlib Figure object
    """
    if isinstance(data, dict):
        categories = data.get('categories', [])
        values = data.get('values', [])
    elif isinstance(data, list):
        categories, values = zip(*data) if data else ([], [])
    else:
        raise ValueError("Data must be dict with 'categories'/'values' or list of tuples")
    
    fig, ax = plt.subplots(figsize=kwargs.get('figsize', (8, 6)))
    bars = ax.bar(categories, values, color=kwargs.get('color', 'steelblue'))
    
    ax.set_title(title, fontsize=16, fontweight='bold')
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    
    # Add value labels on bars if requested
    if kwargs.get('show_values', True):
        for bar, value in zip(bars, values):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + max(values) * 0.01,
                    f'{value}', ha='center', va='bottom')
    
    plt.tight_layout()
    return fig


def create_line_chart(data, title="Line Chart", xlabel="X", ylabel="Y", **kwargs):
    """
    Create a line chart figure.
    
    Args:
        data: Dict with 'x' and 'y' keys, or list of tuples
        title: Chart title
        xlabel: X-axis label
        ylabel: Y-axis label
        **kwargs: Additional matplotlib arguments
        
    Returns:
        matplotlib Figure object
    """
    if isinstance(data, dict):
        x_data = data.get('x', [])
        y_data = data.get('y', [])
    elif isinstance(data, list):
        x_data, y_data = zip(*data) if data else ([], [])
    else:
        raise ValueError("Data must be dict with 'x'/'y' or list of tuples")
    
    fig, ax = plt.subplots(figsize=kwargs.get('figsize', (8, 6)))
    ax.plot(x_data, y_data, 
            color=kwargs.get('color', 'red'),
            linewidth=kwargs.get('linewidth', 2),
            marker=kwargs.get('marker', 'o'),
            markersize=kwargs.get('markersize', 4))
    
    ax.set_title(title, fontsize=16, fontweight='bold')
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    
    if kwargs.get('grid', True):
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig


def create_scatter_plot(data, title="Scatter Plot", xlabel="X", ylabel="Y", **kwargs):
    """
    Create a scatter plot figure.
    
    Args:
        data: Dict with 'x' and 'y' keys, or list of tuples
        title: Chart title
        xlabel: X-axis label
        ylabel: Y-axis label
        **kwargs: Additional matplotlib arguments
        
    Returns:
        matplotlib Figure object
    """
    if isinstance(data, dict):
        x_data = data.get('x', [])
        y_data = data.get('y', [])
        colors = data.get('colors', None)
    elif isinstance(data, list):
        x_data, y_data = zip(*data) if data else ([], [])
        colors = None
    else:
        raise ValueError("Data must be dict with 'x'/'y' or list of tuples")
    
    fig, ax = plt.subplots(figsize=kwargs.get('figsize', (8, 6)))
    
    scatter = ax.scatter(x_data, y_data,
                        c=colors or kwargs.get('color', 'blue'),
                        alpha=kwargs.get('alpha', 0.6),
                        s=kwargs.get('size', 50),
                        cmap=kwargs.get('cmap', 'viridis'))
    
    ax.set_title(title, fontsize=16, fontweight='bold')
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    
    if colors is not None and kwargs.get('colorbar', True):
        plt.colorbar(scatter)
    
    if kwargs.get('grid', True):
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig


def create_pie_chart(data, title="Pie Chart", **kwargs):
    """
    Create a pie chart figure.
    
    Args:
        data: Dict with 'labels' and 'values' keys, or list of tuples
        title: Chart title
        **kwargs: Additional matplotlib arguments
        
    Returns:
        matplotlib Figure object
    """
    if isinstance(data, dict):
        labels = data.get('labels', [])
        values = data.get('values', [])
    elif isinstance(data, list):
        labels, values = zip(*data) if data else ([], [])
    else:
        raise ValueError("Data must be dict with 'labels'/'values' or list of tuples")
    
    fig, ax = plt.subplots(figsize=kwargs.get('figsize', (8, 6)))
    
    colors = kwargs.get('colors', None)
    autopct = kwargs.get('autopct', '%1.1f%%')
    startangle = kwargs.get('startangle', 90)
    
    ax.pie(values, labels=labels, colors=colors, autopct=autopct, startangle=startangle)
    ax.set_title(title, fontsize=16, fontweight='bold')
    
    return fig


def create_histogram(data, title="Histogram", xlabel="Values", ylabel="Frequency", **kwargs):
    """
    Create a histogram figure.
    
    Args:
        data: List or array of values
        title: Chart title
        xlabel: X-axis label
        ylabel: Y-axis label
        **kwargs: Additional matplotlib arguments
        
    Returns:
        matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=kwargs.get('figsize', (8, 6)))
    
    bins = kwargs.get('bins', 30)
    color = kwargs.get('color', 'skyblue')
    alpha = kwargs.get('alpha', 0.7)
    
    ax.hist(data, bins=bins, color=color, alpha=alpha, edgecolor='black')
    ax.set_title(title, fontsize=16, fontweight='bold')
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    
    if kwargs.get('grid', True):
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig 