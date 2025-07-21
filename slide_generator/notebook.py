#!/usr/bin/env python3
"""
Notebook-style slide generation API.

This module provides a way to build slides by providing markdown content per slide,
along with figure generation functions and pandas DataFrames for tables.
"""

import os
import uuid
import re
import logging
from typing import List, Callable, Any, Optional, Union, Dict
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import pandas as pd

from jinja2 import Environment, DictLoader, pass_context, nodes
from jinja2.ext import Extension
from pathlib import Path

# Local imports
from .paths import prepare_workspace
from .generator import SlideGenerator
from .markdown_parser import MarkdownParser

logger = logging.getLogger(__name__)


class Counter:
    """
    Progress counter for tracking slides within sections.
    
    Supports both numeric (1/4) and visual dot (●●○○) styles for displaying progress.
    """
    
    def __init__(self):
        self.totals = {}  # section_name → [done, total]
    
    def set_total(self, section: str, total: int):
        """Set the total count for a section."""
        if section not in self.totals:
            self.totals[section] = [0, total]
        else:
            self.totals[section][1] = total
    
    @pass_context
    def next(self, ctx, section: str, style: str = "numeric") -> str:
        """
        Get the next counter value for a section and increment.
        
        Args:
            ctx: Jinja2 context (automatically passed)
            section: Section name (e.g., "Conversion Rate", "Revenue Analysis")  
            style: Display style - "numeric" (1/4) or "dots" (●●○○)
            
        Returns:
            Formatted counter string
        """
        if section not in self.totals:
            # Initialize with 0 total if not set
            self.totals[section] = [0, 0]
        
        done, total = self.totals[section]
        done += 1
        self.totals[section][0] = done
        
        if style == "dots":
            return "●" * done + "○" * (total - done)
        else:  # numeric (default)
            return f"{done}/{total}"
    
    def bump_total(self, section: str, k: int = 1):
        """Increase the total count for a section (for real-time pagination)."""
        if section not in self.totals:
            self.totals[section] = [0, k]
        else:
            self.totals[section][1] += k
    
    def reset(self, section: str):
        """Reset the done count for a section to 0."""
        if section in self.totals:
            self.totals[section][0] = 0
    
    def status(self, section: str) -> tuple:
        """Get the current (done, total) status for a section."""
        return tuple(self.totals.get(section, [0, 0]))


class FigureTag(Extension):
    """Jinja2 extension for inserting figures with optional caption and scaling."""
    tags = {"figure"}

    def _parse_kwargs_fallback(self, parser):
        kwargs = []
        while not parser.stream.current.test('block_end'):
            token = parser.stream.expect('name')
            key = token.value
            parser.stream.expect('assign')
            value = parser.parse_expression()
            kwargs.append(nodes.Keyword(key, value))
            # Skip optional commas
            parser.stream.skip_if('comma')
        return kwargs

    def parse(self, parser):
        lineno = next(parser.stream).lineno
        # First argument: figure key/name
        name_expr = parser.parse_expression()
        if hasattr(parser, 'parse_kwargs'):
            kw_list = parser.parse_kwargs()
            call = self.call_method("_render", [name_expr], kwargs=kw_list)
            return nodes.CallBlock(call, [], [], []).set_lineno(lineno)
        else:
            kw_list = self._parse_kwargs_fallback(parser)
            call = self.call_method("_render", [name_expr], kwargs=kw_list)
            return nodes.CallBlock(call, [], [], []).set_lineno(lineno)

    @pass_context
    def _render(self, ctx, key, caller=None, **kw):
        fig_registry = ctx.get("fig_registry", {})
        if key not in fig_registry:
            return f"<!-- Figure '{key}' not found -->"
        desc = fig_registry[key]
        path = self._resolve_path(desc, key, kw, ctx)
        spec = ""
        if "width" in kw:
            spec = f"|{kw['width']}x"
        elif "height" in kw:
            spec = f"|{kw['height']}y"
        # Build the image markdown consistently with our caption syntax
        alt_parts = []
        if "caption" in kw:
            alt_parts.append(f"Caption: {kw['caption']}")
        # Don't include the function name in alt text to avoid confusion
        alt_text = "|".join(alt_parts) if alt_parts else ""
        return f"![{alt_text}{spec}]({path})"

    def _resolve_path(self, desc, key, gen_kw, ctx):
        fig_kw = {k: v for k, v in gen_kw.items() if k not in ("caption", "_ctx", "width", "height")}
        if callable(desc):
            fig = desc(**fig_kw)
        elif isinstance(desc, tuple) and callable(desc[0]):
            func, base_kw = desc
            fig = func(**{**base_kw, **fig_kw})
        else:
            return str(desc)
        temp_dir = ctx.get("slide_temp_dir") or ctx.get("tmp_dir")
        if not temp_dir:
            # This should not happen since we always set tmp_dir in context
            raise RuntimeError("No temporary directory available in template context")

        # deterministic & readable filename: slide_<id>_<key>.png
        slug = f"slide_{ctx.get('slide_id', '0000')}_{key}.png"
        out_path = os.path.join(temp_dir, slug)
        fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return out_path

class TableTag(Extension):
    """Jinja2 extension for rendering DataFrames with optional styling."""
    tags = {"table"}

    def _parse_kwargs_fallback(self, parser):
        kwargs = []
        while not parser.stream.current.test('block_end'):
            token = parser.stream.expect('name')
            key = token.value
            parser.stream.expect('assign')
            value = parser.parse_expression()
            kwargs.append(nodes.Keyword(key, value))
            parser.stream.skip_if('comma')
        return kwargs

    def parse(self, parser):
        lineno = next(parser.stream).lineno
        name_expr = parser.parse_expression()
        if hasattr(parser, 'parse_kwargs'):
            kw_list = parser.parse_kwargs()
            call = self.call_method("_render", [name_expr], kwargs=kw_list)
            return nodes.CallBlock(call, [], [], []).set_lineno(lineno)
        else:
            kw_list = self._parse_kwargs_fallback(parser)
            call = self.call_method("_render", [name_expr], kwargs=kw_list)
            return nodes.CallBlock(call, [], [], []).set_lineno(lineno)

    @pass_context
    def _render(self, ctx, key, caller=None, **kw):
        table_registry = ctx.get("table_registry", {})
        if key not in table_registry:
            return f"<!-- Table '{key}' not found -->"
        df = table_registry[key].copy()
        
        # Smart index handling: automatically detect if index should be meaningful
        df = self._handle_smart_index(df, kw)
        
        if "order_by" in kw:
            ascending = not kw.get("desc", False)
            col = kw["order_by"]
            if col in df.columns:
                df = df.sort_values(col, ascending=ascending)
        
        # Apply numeric styling before highlights
        if "style" in kw:
            df = self._apply_numeric_styles(df, kw["style"])
        
        # Apply lambda-based conditional styling rules
        if "rules" in kw:
            df = self._apply_lambda_rules(df, kw["rules"])
        
        if "highlight" in kw:
            df = self._apply_highlights(df, kw["highlight"])
        
        # Make index inclusion configurable, with smart default
        include_index = kw.get("index", self._should_show_index(df))
        return df.to_markdown(index=include_index)

    def _handle_smart_index(self, df, kw):
        """
        Smart index handling: detect if first column should be the index.
        
        This addresses the common DataFrame workflow issue where users:
        1. Create a DataFrame with meaningful row identifiers in the first column
        2. Want to reference rows by these identifiers in styling rules
        3. But forget to set_index(), leaving the default numeric index
        
        Args:
            df: DataFrame to analyze
            kw: Table keyword arguments
            
        Returns:
            DataFrame with potentially adjusted index
        """
        # Skip if user explicitly controls the index  
        if "index" in kw or "dropindex" in kw:
            return df
        
        # Skip if index is already meaningful (not default RangeIndex)
        if not isinstance(df.index, pd.RangeIndex):
            return df
            
        # Skip if DataFrame is too simple (< 2 columns or < 2 rows)
        if len(df.columns) < 2 or len(df) < 2:
            return df
        
        # Check if first column looks like meaningful row identifiers
        first_col = df.iloc[:, 0]
        
        # Heuristics for meaningful identifiers:
        # 1. All values are strings
        # 2. All values are unique  
        # 3. Values look like labels (contain letters)
        if (first_col.dtype == 'object' and  # String-like
            first_col.nunique() == len(first_col) and  # All unique
            all(isinstance(val, str) and any(c.isalpha() for c in val) for val in first_col)):
            
            # Move first column to index
            new_df = df.set_index(df.columns[0])
            return new_df
        
        return df
    
    def _should_show_index(self, df):
        """
        Determine if index should be shown by default.
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            bool: True if index should be shown
        """
        # Show index if it's not a simple RangeIndex (0, 1, 2, ...)
        if not isinstance(df.index, pd.RangeIndex):
            return True
        
        # Hide default numeric index
        return False

    def _apply_numeric_styles(self, df, style_rules):
        """Apply numeric formatting styles to DataFrame rows or columns.
        
        Args:
            df: DataFrame to style
            style_rules: Dict with 'rows' and/or 'columns' keys
                        rows: {row_index: ['dollar', 'red']} - applies to entire row excluding index
                              row_index can be numeric (0,1,2) or string ("Revenue", "Profit")
                        columns: {column_name: ['percent', 'blue']} - applies to entire column
        
        Example:
            style={'rows': {0: ['dollar', 'green']}, 'columns': {'Growth': ['percent', 'blue']}}
        """
        df = df.copy()
        
        # Apply row styles (excluding index column)
        if 'rows' in style_rules:
            for row_ref, style_classes in style_rules['rows'].items():
                try:
                    # Handle both numeric and string-based row references
                    if isinstance(row_ref, str):
                        # String-based row reference (for meaningful indices)
                        if row_ref in df.index:
                            for col in df.columns:
                                current_value = df.at[row_ref, col]
                                class_str = ''.join(f' .{c}' for c in style_classes)
                                df.at[row_ref, col] = f"[{current_value}]{{{class_str}}}"
                    else:
                        # Numeric row reference (traditional positional)
                        if row_ref < len(df):
                            for col in df.columns:
                                # Use iloc for positional access when dealing with non-numeric indices
                                current_value = df.iloc[row_ref, df.columns.get_loc(col)]
                                class_str = ''.join(f' .{c}' for c in style_classes)
                                df.iloc[row_ref, df.columns.get_loc(col)] = f"[{current_value}]{{{class_str}}}"
                except (KeyError, IndexError, TypeError):
                    # Skip invalid row references
                    continue
        
        # Apply column styles  
        if 'columns' in style_rules:
            for col_name, style_classes in style_rules['columns'].items():
                if col_name in df.columns:
                    # Apply to all rows in this column
                    for row_idx in range(len(df)):
                        try:
                            # Use iloc for positional access when dealing with non-numeric indices
                            current_value = df.iloc[row_idx, df.columns.get_loc(col_name)]
                            class_str = ''.join(f' .{c}' for c in style_classes)
                            df.iloc[row_idx, df.columns.get_loc(col_name)] = f"[{current_value}]{{{class_str}}}"
                        except (KeyError, IndexError, TypeError):
                            # Skip invalid row/column combinations
                            continue
        
        return df
    
    def _apply_lambda_rules(self, df, rules):
        """Apply conditional styling rules to DataFrame using string expressions.
        
        Args:
            df: DataFrame to style
            rules: List of [condition_string, {"class": ["red", "bold"]}] pairs
                   Condition string supports row access like 'Growth < 0' or 'Revenue > 1000000'
        
        Example:
            rules=[
                ['Growth < 0', {"class": ["red", "bold"]}],              # Row-wise: red if Growth < 0
                ['Revenue > 1000000', {"class": ["green"]}],             # Row-wise: green if Revenue > 1M
                ['Q4 > Q3', {"class": ["green", "bold"]}]                # Row-wise: green if Q4 > Q3
            ]
        """
        df = df.copy()
        
        for rule in rules:
            if not isinstance(rule, (list, tuple)) or len(rule) != 2:
                continue
                
            condition_str, style_config = rule
            if not isinstance(condition_str, str) or not isinstance(style_config, dict):
                continue
            
            classes = style_config.get("class", [])
            if not isinstance(classes, list):
                classes = [classes]
            
            class_str = ''.join(f' .{c}' for c in classes)
            
            # Apply condition row-wise
            try:
                for row_idx in range(len(df)):
                    # Create evaluation context with row values
                    row_context = {}
                    for col in df.columns:
                        # Safe column name for evaluation (replace spaces with underscores)
                        safe_col = col.replace(' ', '_').replace('(', '').replace(')', '')
                        row_context[safe_col] = df.at[row_idx, col]
                        # Also add original column name if it's a valid identifier
                        if col.isidentifier():
                            row_context[col] = df.at[row_idx, col]
                    
                    # Safely evaluate the condition
                    try:
                        # Replace column names in condition for safe evaluation
                        eval_condition = condition_str
                        for col in df.columns:
                            safe_col = col.replace(' ', '_').replace('(', '').replace(')', '')
                            eval_condition = eval_condition.replace(col, safe_col)
                        
                        if eval(eval_condition, {"__builtins__": {}}, row_context):
                            # Apply to entire row
                            for col in df.columns:
                                current_value = df.at[row_idx, col]
                                df.at[row_idx, col] = f"[{current_value}]{{{class_str}}}"
                    except Exception:
                        # Skip this row if evaluation fails
                        continue
            except Exception:
                # Skip this rule if it fails completely
                continue
        
        return df
    
    def _apply_highlights(self, df, rules):
        """
        Apply highlighting to specific cells in the DataFrame.
        
        Args:
            df: DataFrame to style
            rules: Dict mapping (row_ref, col_name) to style classes
                   row_ref can be numeric index or row label (if meaningful index)
                   
        Example:
            highlight={
                (1, "Q4"): ["bold", "blue"],           # Row index 1, column Q4  
                ("Profit", "Q1"): ["red", "italic"]   # Row labeled "Profit", column Q1
            }
        """
        df = df.copy()
        for (row_ref, col), classes in rules.items():
            try:
                # Handle both numeric indices and string-based row labels
                if isinstance(row_ref, str):
                    # String-based row reference (for meaningful indices)
                    if row_ref in df.index and col in df.columns:
                        current_value = df.at[row_ref, col]
                        class_str = ''.join(f' .{c}' for c in classes)
                        df.at[row_ref, col] = f"[{current_value}]{{{class_str}}}"
                else:
                    # Numeric row reference (traditional positional)
                    if row_ref < len(df) and col in df.columns:
                        current_value = df.iloc[row_ref, df.columns.get_loc(col)]
                        class_str = ''.join(f' .{c}' for c in classes)
                        df.iloc[row_ref, df.columns.get_loc(col)] = f"[{current_value}]{{{class_str}}}"
            except (KeyError, IndexError, TypeError):
                # Skip invalid row/column references
                continue
        return df


class SlideNotebook:
    """
    Notebook-style slide generator that accepts markdown content per slide
    with enhanced Jinja2 template support for figures and tables.
    """

    def __init__(self, *, output_dir: str, base_dir: Path, keep_tmp: bool = False, theme: str = "default", debug: bool = False):
        """
        Initialize the notebook with Jinja2 environment and slide generator.

        Args:
            output_dir: Directory where output files are saved
            base_dir: Base directory for resolving relative image paths
            keep_tmp: Whether to keep temporary files
            theme: Theme name ("default" or "dark")
            debug: Enable debug mode for HTML preview
        """
        self.theme = theme
        self.debug = debug
        self.base_dir = base_dir

        # ------ workspace & tmp dir -----------------------------
        self.paths = prepare_workspace(output_dir, keep_tmp=keep_tmp)
        self.temp_dir = str(self.paths["tmp_dir"])  # maintain old attr name for internal use

        if self.debug:
            logger.info(f"Notebook workspace  : {self.paths['output_dir']}")
            logger.info(f"Notebook temp assets: {self.temp_dir}")

        self.slides = []
        
        # Initialize counter for slide progress tracking
        self.counter = Counter()
        
        # Initialize MarkdownIt renderer with same plugins as production
        self._md_renderer = MarkdownParser(base_dir=self.base_dir)
        
        # ── Jinja2 Setup ───────────────────────────────────────────
        # Each notebook instance gets its own env (thread-safe, theme-aware)
        self.jinja_env = Environment(
            loader=DictLoader({}),  # Use DictLoader since we're processing strings directly
            extensions=["jinja2.ext.do", FigureTag, TableTag]
        )
        
        # ── filters / helpers ───────────────────────────────────────────
        self.jinja_env.filters["ordinal"] = lambda n: f"{n}{'th' if 10<=n%100<=20 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"
        self.jinja_env.filters["pct"] = lambda x: f"{x*100:.1f}%"
        self.jinja_env.filters["money"] = self._money_filter
        self.jinja_env.globals["style"] = (
            lambda txt,*cls: f"[{txt}]{{{''.join(f'.{c} ' for c in cls).strip()}}}"
        )
        self.jinja_env.globals["render_log"] = []  # for {% do %}
        # Expose tmp_dir to templates so FigureTag can use it
        self.jinja_env.globals["tmp_dir"] = self.temp_dir
        # Expose counter for slide progress tracking
        self.jinja_env.globals["counter"] = self.counter
        # Register counter.next as a Jinja2 function  
        self.jinja_env.globals["counter_next"] = self.counter.next
        # Expose debug flag to templates
        self.jinja_env.globals["debug_mode"] = self.debug
        
        if self.debug:
            logger.info("Initialized Jinja2 environment with custom filters and globals")
    
    def _money_filter(self, v: float) -> str:
        """Convert number to money format: 1234567 → $1.23M"""
        sign = "-" if v < 0 else ""
        v = abs(v)
        for div, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
            if v >= div:
                return f"{sign}${v/div:,.2f}{unit}"
        return f"{sign}${v:,.0f}"
    


    def new_slide(self, 
                  markdown_content: str,
                  figure_functions: Optional[Dict[str, Callable]] = None,
                  dataframes: Optional[Dict[str, Any]] = None,
                  template_vars: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a new slide with markdown content and optional figure functions/dataframes/template vars.
        Automatically detects figure functions and dataframes from caller's scope if not provided.
        
        Args:
            markdown_content: Markdown text for the slide content (can include Jinja2 templates)
            figure_functions: Dict mapping figure names to functions that generate them
            dataframes: Dict mapping table names to pandas DataFrames or table data
            template_vars: Dict of variables for Jinja2 template rendering
            
        Example:
            ```python
            # Auto-detection mode (just define functions and dataframes in scope)
            def create_sales_chart():
                # ... chart creation logic
                return fig
            
            sales_data = pd.DataFrame(...)
            
            notebook.new_slide('''
            # Sales Report
            {% figure "create_sales_chart" width=0.8 %}
            {% table "sales_data" %}
            ''')
            
            # Manual mode (explicit registries)
            notebook.new_slide(
                markdown,
                figure_functions={'my_chart': create_chart},
                dataframes={'sales_data': my_df}
            )
            ```
        """
        import inspect
        import re
        
        slide_id = str(uuid.uuid4())[:8]
        
        # Create slide-specific temp directory
        slide_temp_dir = os.path.join(self.temp_dir, f"slide_{slide_id}")
        os.makedirs(slide_temp_dir, exist_ok=True)
        
        # Build complete registries by merging auto-detected and manual
        final_figure_functions = figure_functions.copy() if figure_functions else {}
        final_dataframes = dataframes.copy() if dataframes else {}
        
        # Auto-detect missing functions and dataframes from caller's scope
        caller_frame = inspect.currentframe().f_back
        if caller_frame:
            caller_locals = caller_frame.f_locals
            caller_globals = caller_frame.f_globals
            
            # Find all figure references in markdown
            figure_matches = re.findall(r'{%\s*figure\s+["\']([^"\']+)["\']', markdown_content)
            for fig_name in figure_matches:
                if fig_name not in final_figure_functions:
                    func = caller_locals.get(fig_name) or caller_globals.get(fig_name)
                    if func and callable(func):
                        final_figure_functions[fig_name] = func
                        if self.debug:
                            logger.info(f"Auto-detected figure function: {fig_name}")
            
            # Find all table references in markdown
            table_matches = re.findall(r'{%\s*table\s+["\']([^"\']+)["\']', markdown_content)
            for table_name in table_matches:
                if table_name not in final_dataframes:
                    df = caller_locals.get(table_name)
                    if df is None:
                        df = caller_globals.get(table_name)
                    if df is not None:
                        final_dataframes[table_name] = df
                        if self.debug:
                            logger.info(f"Auto-detected dataframe: {table_name}")
        
        # Process the markdown content
        processed_markdown = self._process_slide_content(
            markdown_content,
            final_figure_functions,
            final_dataframes,
            template_vars or {},
            slide_temp_dir,
            slide_id
        )
        
        slide_data = {
            'id': slide_id,
            'markdown': processed_markdown,
            'temp_dir': slide_temp_dir,
            'original_markdown': markdown_content  # Store original for debugging
        }
        
        self.slides.append(slide_data)
        
        if self.debug:
            logger.info(f"Created slide {slide_id} with {len(final_figure_functions)} figures, {len(final_dataframes)} tables, and {len(template_vars or {})} template vars")
    
    def remove_slide(self, index: Optional[int] = None, title: Optional[str] = None) -> bool:
        """
        Remove a slide by index or by title.
        
        Args:
            index: Zero-based index of slide to remove (if provided, title is ignored)
            title: H1 title of slide to remove (used if index not provided)
            
        Returns:
            True if slide was removed, False if not found
            
        Example:
            ```python
            # Remove by index
            notebook.remove_slide(index=2)  # Remove 3rd slide
            
            # Remove by title  
            notebook.remove_slide(title="Sales Performance")
            
            # Remove the last slide
            notebook.remove_slide(index=-1)
            ```
        """
        if index is not None:
            # Remove by index
            if -len(self.slides) <= index < len(self.slides):
                removed_slide = self.slides.pop(index)
                if self.debug:
                    logger.info(f"Removed slide {removed_slide['id']} at index {index}")
                return True
            else:
                if self.debug:
                    logger.warning(f"Invalid slide index: {index}. Valid range: 0 to {len(self.slides)-1}")
                return False
        
        elif title is not None:
            # Remove by title - look for H1 titles in markdown
            title_lower = title.lower().strip()
            for i, slide in enumerate(self.slides):
                # Extract H1 titles from markdown
                h1_matches = re.findall(r'^# (.+)$', slide['markdown'], re.MULTILINE)
                for h1_title in h1_matches:
                    if h1_title.lower().strip() == title_lower:
                        removed_slide = self.slides.pop(i)
                        if self.debug:
                            logger.info(f"Removed slide {removed_slide['id']} with title '{h1_title}'")
                        return True
            
            if self.debug:
                logger.warning(f"No slide found with title: '{title}'")
            return False
        
        else:
            if self.debug:
                logger.warning("remove_slide() requires either index or title parameter")
            return False
    
    def list_slides(self) -> List[Dict[str, str]]:
        """
        Get a list of slides with their IDs and titles.
        
        Returns:
            List of dicts with 'id', 'title', and 'index' keys
        """
        slide_info = []
        for i, slide in enumerate(self.slides):
            # Extract first H1 title from markdown
            h1_matches = re.findall(r'^# (.+)$', slide['markdown'], re.MULTILINE)
            title = h1_matches[0] if h1_matches else f"Slide {i+1}"
            
            slide_info.append({
                'index': i,
                'id': slide['id'],
                'title': title
            })
        
        return slide_info
    
    def _render_jinja2_template(self, markdown_content: str, template_vars: Dict[str, Any]) -> str:
        """
        Render Jinja2 templates in markdown content.
        
        Args:
            markdown_content: Markdown content that may contain Jinja2 templates
            template_vars: Variables to use in template rendering
            
        Returns:
            Processed markdown with templates rendered
        """
        if not template_vars or not self.jinja_env:
            return markdown_content
        
        try:
            # Create template and render using the pre-configured environment
            template = self.jinja_env.from_string(markdown_content)
            rendered = template.render(**template_vars)
            
            if self.debug:
                logger.info(f"Rendered Jinja2 template with {len(template_vars)} variables")
            
            return rendered
            
        except Exception as e:
            if self.debug:
                logger.warning(f"Jinja2 template rendering failed: {e}")
            return markdown_content
    
    def _process_slide_content(self,
                              markdown_content: str,
                              figure_functions: Dict[str, Callable],
                              dataframes: Dict[str, Any],
                              template_vars: Dict[str, Any],
                              slide_temp_dir: str,
                              slide_id: str) -> str:
        """
        Process markdown content by rendering Jinja2 templates, generating figures and converting dataframes to tables.
        
        Args:
            markdown_content: Raw markdown content
            figure_functions: Dict of figure generation functions
            dataframes: Dict of dataframes/table data
            template_vars: Dict of template variables for Jinja2 rendering
            slide_temp_dir: Temporary directory for this slide
            slide_id: Unique slide identifier
            
        Returns:
            Processed markdown with templates rendered, actual image paths and table markdown
        """
        # Prepare template context with registries and variables
        context = {
            **template_vars,
            'fig_registry': figure_functions,
            'table_registry': dataframes,
            'slide_temp_dir': slide_temp_dir,
            'slide_id': slide_id,
            'tmp_dir': self.temp_dir
        }
        
        try:
            # Create template from markdown content and render
            template = self.jinja_env.from_string(markdown_content)
            processed = template.render(context)
            
            if self.debug:
                logger.info(f"Processed slide content with Jinja2 template system")
            
            return processed
            
        except Exception as e:
            logger.error(f"Error processing Jinja2 template: {e}")
            if self.debug:
                logger.error(f"Template content: {markdown_content}")
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
            # Return original content on error
            return markdown_content
    
    def set_theme(self, theme: str) -> None:
        """
        Set the theme for the notebook.
        
        Args:
            theme: Theme name
        """
        self.theme = theme
        
        if self.debug:
            logger.info(f"Set theme to: {theme}")
    
    async def save(self, output_path: str) -> str:
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
                # Ensure proper separation with newlines before the page break
                all_markdown.append("\n\n<!-- slide -->\n\n")
            all_markdown.append(slide['markdown'])
        
        combined_markdown = "".join(all_markdown)
        
        if self.debug:
            logger.info(f"Combined markdown from {len(self.slides)} slides")
            logger.info(f"Total markdown length: {len(combined_markdown)} characters")
        
        # Use the existing SlideGenerator to create the presentation
        generator = SlideGenerator(
            output_dir=self.paths["output_dir"], 
            debug=self.debug, 
            theme=self.theme,
            base_dir=str(self.base_dir)
        )
        result_path = await generator.generate(combined_markdown, output_path)
        
        if self.debug:
            logger.info(f"Generated presentation: {result_path}")
        
        return result_path

    # ------------------------------------------------------------------
    # Convenience helpers for notebook users
    # ------------------------------------------------------------------
    def save_sync(self, output_path: str) -> str:
        """Save presentation but work in *both* scripts and Jupyter cells.
        If an event-loop is already running (Jupyter) we create a task.
        Otherwise we start a fresh loop with ``asyncio.run``.
        """
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            # We're in a running event loop (like Jupyter), create a task
            import concurrent.futures
            
            # Create a new thread to run the async function
            def run_in_thread():
                return asyncio.run(self.save(output_path))
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()
        else:
            # No event loop running, we can use asyncio.run
            return asyncio.run(self.save(output_path))

    def preview_slide(self, index: int = -1):
        """Render **one** slide as HTML (default: the last one) – useful
        when authoring page-by-page in a notebook.
        Works only when ``debug=True`` and IPython is available.
        """
        if not self.debug or not self.slides:
            return
        # normalise index
        if index < 0:
            index += len(self.slides)
        if index < 0 or index >= len(self.slides):
            raise IndexError("slide index out of range")
        slide = self.slides[index]
        html_body = self._md_renderer.parse(slide['markdown'])
        from IPython.display import HTML, display
        from .theme_loader import get_css
        theme_css = get_css(self.theme)
        styled_html = f"""
        <style>
        {theme_css}
        body {{ font-family: inherit; }}
        .slide-preview {{ border: 2px solid #0066cc; margin: 20px 0; padding: 20px; }}
        </style>
        <div class='slide-preview'>{html_body}</div>
        """
        display(HTML(styled_html))
    
    def preview(self):
        """
        Display combined markdown as HTML inline for Jupyter notebooks.
        Only works when debug=True and IPython is available.
        """
        if not self.debug:
            if logger.isEnabledFor(logging.INFO):
                logger.info("Preview only available when debug=True")
            return
        
        try:
            from IPython.display import HTML, display
            from .theme_loader import get_css
            theme_css = get_css(self.theme)
            
            # Get properly processed HTML using the markdown parser
            html_body = self._md_renderer.parse(self.preview_markdown())

            # Embed any <img> whose src points into tmp_dir so notebook is self-contained
            from bs4 import BeautifulSoup
            import base64, mimetypes, os

            soup_nb = BeautifulSoup(html_body, "html.parser")
            for img in soup_nb.find_all("img"):
                src = img.get("src", "")
                if src.startswith("data:"):
                    continue
                if src.startswith("file://"):
                    path = src[7:]
                else:
                    path = src
                if not os.path.exists(path):
                    continue
                try:
                    mime,_ = mimetypes.guess_type(path)
                    if not mime:
                        mime = "image/png"
                    with open(path, "rb") as fh:
                        b64 = base64.b64encode(fh.read()).decode()
                    img["src"] = f"data:{mime};base64,{b64}"
                except Exception:
                    continue

            html_body = str(soup_nb)

            # Create styled HTML for inline display with math support
            styled_html = f"""
            <style>
            {theme_css}
            /* Jupyter-specific styling adjustments */
            body {{ font-family: inherit; }}
            .slide {{ border: 1px solid #ddd; margin-bottom: 20px; padding: 10px; }}
            
            /* Math rendering for Jupyter preview */
            .math-html {{ display: inline; }}
            .math-html.display {{ display: block; text-align: center; margin: 0.5em auto; }}
            
            /* Hide any math images that should only appear in PPTX */
            .math-image {{ display: none; }}
            </style>
            {html_body}
            """
            display(HTML(styled_html))
            
        except ImportError:
            if self.debug:
                logger.info("IPython not available, skipping inline preview")
    
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