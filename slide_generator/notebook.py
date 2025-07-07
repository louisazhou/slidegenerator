#!/usr/bin/env python3
"""
Notebook-style slide generation API.

This module provides a way to build slides by providing markdown content per slide,
along with figure generation functions and pandas DataFrames for tables.
"""

import os
import tempfile
import uuid
import re
import shutil
import logging
from typing import List, Callable, Any, Optional, Union, Dict
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend

from .generator import SlideGenerator

logger = logging.getLogger(__name__)


class SlideNotebook:
    """
    Notebook-style slide generator that accepts markdown content per slide
    with separate figure functions and pandas DataFrames.
    """
    
    def __init__(self, theme: str = "default", debug: bool = False):
        """
        Initialize the slide notebook.
        
        Args:
            theme: Theme name for styling
            debug: Enable debug output
        """
        self.theme = theme
        self.debug = debug
        self.slides = []  # List of slide dictionaries
        
        # Create temp directory for this notebook session
        self.temp_dir = tempfile.mkdtemp(prefix="slide_notebook_")
        
        # Create debug_assets directory for permanent image storage
        self.debug_assets_dir = os.path.join("output", "debug_assets")
        os.makedirs(self.debug_assets_dir, exist_ok=True)
        
        if self.debug:
            logger.info(f"Created notebook temp directory: {self.temp_dir}")
            logger.info(f"Using debug assets directory: {self.debug_assets_dir}")
    
    def new_slide(self, 
                  markdown_content: str,
                  figure_functions: Optional[Dict[str, Callable]] = None,
                  dataframes: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a new slide with markdown content and optional figure functions/dataframes.
        
        Args:
            markdown_content: Markdown text for the slide content
            figure_functions: Dict mapping figure names to functions that generate them
            dataframes: Dict mapping table names to pandas DataFrames or table data
            
        Example:
            ```python
            markdown = '''
            # My Slide Title
            
            Here's some text with a figure:
            
            ![my_chart]()
            
            And here's a table:
            
            {{sales_data}}
            '''
            
            def create_chart():
                fig, ax = plt.subplots()
                ax.plot([1, 2, 3], [1, 4, 2])
                return fig
            
            notebook.new_slide(
                markdown,
                figure_functions={'my_chart': create_chart},
                dataframes={'sales_data': my_df}
            )
            ```
        """
        slide_id = str(uuid.uuid4())[:8]
        
        # Create slide-specific temp directory
        slide_temp_dir = os.path.join(self.temp_dir, f"slide_{slide_id}")
        os.makedirs(slide_temp_dir, exist_ok=True)
        
        # Process the markdown content
        processed_markdown = self._process_slide_content(
            markdown_content,
            figure_functions or {},
            dataframes or {},
            slide_temp_dir,
            slide_id
        )
        
        slide_data = {
            'id': slide_id,
            'markdown': processed_markdown,
            'temp_dir': slide_temp_dir
        }
        
        self.slides.append(slide_data)
        
        if self.debug:
            logger.info(f"Created slide {slide_id} with {len(figure_functions or {})} figures and {len(dataframes or {})} tables")
    
    def _process_slide_content(self,
                              markdown_content: str,
                              figure_functions: Dict[str, Callable],
                              dataframes: Dict[str, Any],
                              slide_temp_dir: str,
                              slide_id: str) -> str:
        """
        Process markdown content by generating figures and converting dataframes to tables.
        
        Args:
            markdown_content: Raw markdown content
            figure_functions: Dict of figure generation functions
            dataframes: Dict of dataframes/table data
            slide_temp_dir: Temporary directory for this slide
            slide_id: Unique slide identifier
            
        Returns:
            Processed markdown with actual image paths and table markdown
        """
        processed = markdown_content
        
        # Process figure references like ![figure_name]()
        figure_pattern = r'!\[([^\]]+)\]\(\)'
        
        def replace_figure(match):
            figure_name = match.group(1)
            if figure_name in figure_functions:
                try:
                    # Generate the figure
                    fig = figure_functions[figure_name]()
                    
                    # Save to temp directory first
                    temp_figure_path = os.path.join(slide_temp_dir, f"{figure_name}.png")
                    fig.savefig(temp_figure_path, dpi=150, bbox_inches='tight',
                               facecolor='white', edgecolor='none')
                    plt.close(fig)
                    
                    # Copy to debug_assets for permanent storage
                    permanent_figure_path = os.path.join(self.debug_assets_dir, f"{figure_name}_{slide_id}.png")
                    shutil.copy2(temp_figure_path, permanent_figure_path)
                    
                    if self.debug:
                        logger.info(f"Generated figure: {figure_name} -> {permanent_figure_path}")
                    
                    # Return markdown with permanent path
                    return f'<img src="{permanent_figure_path}" alt="{figure_name}" style="width: 70%;">'
                    
                except Exception as e:
                    logger.warning(f"Failed to generate figure {figure_name}: {e}")
                    return f"*[Figure generation failed: {figure_name}]*"
            else:
                logger.warning(f"Figure function not found: {figure_name}")
                return f"*[Figure not found: {figure_name}]*"
        
        processed = re.sub(figure_pattern, replace_figure, processed)
        
        # Process table references like {{table_name}}
        table_pattern = r'\{\{([^}]+)\}\}'
        
        def replace_table(match):
            table_name = match.group(1)
            if table_name in dataframes:
                try:
                    df_or_data = dataframes[table_name]
                    
                    # Handle pandas DataFrame - use to_markdown directly
                    if hasattr(df_or_data, 'to_markdown'):
                        # It's a pandas DataFrame
                        table_markdown = df_or_data.to_markdown(index=False)
                        if self.debug:
                            logger.info(f"Converted DataFrame to table: {table_name}")
                        return table_markdown
                        
                except Exception as e:
                    logger.warning(f"Failed to process table {table_name}: {e}")
                    return f"*[Table processing failed: {table_name}]*"
            else:
                logger.warning(f"Table data not found: {table_name}")
                return f"*[Table not found: {table_name}]*"
        
        processed = re.sub(table_pattern, replace_table, processed)
        
        return processed
    
    def set_theme(self, theme: str) -> None:
        """
        Set the theme for the notebook.
        
        Args:
            theme: Theme name
        """
        self.theme = theme
        
        if self.debug:
            logger.info(f"Set theme to: {theme}")
    
    def save(self, output_path: str) -> str:
        """
        Generate and save the presentation.
        
        Args:
            output_path: Path where the PPTX file should be saved
            
        Returns:
            Path to the generated PPTX file
        """
        if not self.slides:
            raise ValueError("No slides have been created. Use new_slide() to create slides.")
        
        # Combine all slide markdown
        all_markdown = []
        for i, slide in enumerate(self.slides):
            if i > 0:
                all_markdown.append("<!-- slide -->\n\n")
            all_markdown.append(slide['markdown'])
        
        combined_markdown = "".join(all_markdown)
        
        if self.debug:
            logger.info(f"Combined markdown from {len(self.slides)} slides")
            logger.info(f"Total markdown length: {len(combined_markdown)} characters")
        
        # Use the existing SlideGenerator to create the presentation
        generator = SlideGenerator(debug=self.debug, theme=self.theme)
        result_path = generator.generate(combined_markdown, output_path)
        
        if self.debug:
            logger.info(f"Generated presentation: {result_path}")
        
        return result_path
    
    def preview_markdown(self) -> str:
        """
        Get the combined markdown for all slides (for debugging).
        
        Returns:
            Combined markdown content
        """
        all_markdown = []
        for i, slide in enumerate(self.slides):
            if i > 0:
                all_markdown.append("<!-- slide -->\n\n")
            all_markdown.append(slide['markdown'])
        
        return "".join(all_markdown)
    
    def __len__(self) -> int:
        """Return the number of slides."""
        return len(self.slides)
    
    def __getitem__(self, index: int) -> Dict:
        """Get a slide by index."""
        return self.slides[index]
    
    def __del__(self):
        """Clean up temp directory when notebook is destroyed."""
        try:
            import shutil
            if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except:
            pass  # Ignore cleanup errors 