"""
Centralized CSS utilities for slide generation.

This module consolidates all CSS variable extraction, font size parsing, 
and other CSS-related operations that were previously duplicated across 
multiple files (layout_engine.py, layout_parser.py, pptx_renderer.py).
"""
import re
from typing import Dict, Optional, List, Tuple, Any
from .theme_loader import get_css


class CSSParser:
    """
    Centralized CSS parsing utilities.
    
    Consolidates CSS variable extraction, font size parsing, and color extraction
    that was previously duplicated across LayoutEngine, LayoutParser, and PPTXRenderer.
    """
    
    def __init__(self, theme: str = "default"):
        self.theme = theme
        self.css_content = get_css(theme)
        self._css_vars = None
        self._font_sizes = None
        self._colors = None
    
    def get_css_variables(self) -> Dict[str, str]:
        """Extract all CSS variables from :root section. Cached for performance."""
        if self._css_vars is not None:
            return self._css_vars
            
        # Extract CSS variables from :root section
        root_match = re.search(r':root\s*\{([^}]+)\}', self.css_content, re.DOTALL)
        if not root_match:
            raise ValueError(f"No :root section found in theme '{self.theme}'")
        
        root_content = root_match.group(1)
        
        # Parse all CSS variables at once
        variable_pattern = r'--([^:]+):\s*([^;]+);'
        css_vars = re.findall(variable_pattern, root_content)
        self._css_vars = {name.strip(): value.strip() for name, value in css_vars}
        
        return self._css_vars
    
    def get_px_value(self, variable_name: str) -> int:
        """Get pixel value from CSS variable."""
        vars_dict = self.get_css_variables()
        value = vars_dict.get(variable_name)
        if not value:
            raise ValueError(f"CSS variable '--{variable_name}' not found in theme '{self.theme}'")
        
        # Extract pixel value
        px_match = re.search(r'(\d+)px', value)
        if not px_match:
            raise ValueError(f"CSS variable '--{variable_name}' is not a pixel value: {value}")
        
        return int(px_match.group(1))
    
    def get_raw_value(self, variable_name: str) -> str:
        """Get raw CSS variable value."""
        vars_dict = self.get_css_variables()
        value = vars_dict.get(variable_name)
        if not value:
            raise ValueError(f"CSS variable '--{variable_name}' not found in theme '{self.theme}'")
        return value
    
    def get_font_sizes(self) -> Dict[str, float]:
        """Extract all font sizes from CSS, converting px to pt. Cached for performance."""
        if self._font_sizes is not None:
            return self._font_sizes
            
        font_size_patterns = {
            'h1': r'h1\s*{[^}]*font-size:\s*(\d+)px',
            'h2': r'h2\s*{[^}]*font-size:\s*(\d+)px',
            'h3': r'h3\s*{[^}]*font-size:\s*(\d+)px',
            'p': r'p\s*{[^}]*font-size:\s*(\d+)px',
            'ul, ol': r'ul,\s*ol\s*{[^}]*font-size:\s*(\d+)px',
            'pre': r'pre\s*{[^}]*font-size:\s*(\d+)px'
        }
        
        font_sizes = {}
        for element, pattern in font_size_patterns.items():
            match = re.search(pattern, self.css_content, re.IGNORECASE | re.DOTALL)
            if match:
                px_size = int(match.group(1))
                # PowerPoint/Microsoft Office's point system is 1 px ≈ 1 pt at standard screen resolution
                pt_size = round(px_size * 2) / 2  # Round to nearest 0.5pt
                
                if element == 'ul, ol':
                    font_sizes['li'] = pt_size
                elif element == 'pre':
                    font_sizes['code'] = pt_size
                else:
                    font_sizes[element] = pt_size
        
        self._font_sizes = font_sizes
        return font_sizes
    
    def get_line_height(self) -> float:
        """Extract line-height from CSS."""
        line_height_match = re.search(r'line-height:\s*([\d.]+)', self.css_content)
        if not line_height_match:
            raise ValueError(f"❌ CSS theme '{self.theme}' missing line-height")
        return float(line_height_match.group(1))
    
    def get_colors(self) -> Dict[str, str]:
        """Extract all colors from CSS theme. Cached for performance."""
        if self._colors is not None:
            return self._colors
            
        colors = {}
        
        # Required color types that MUST be defined in CSS
        color_patterns = {
            'text': [
                r'body\s*{[^}]*?(?<!background-)color:\s*([^;}\s]+)',
                r'p\s*{[^}]*?(?<!background-)color:\s*([^;}\s]+)'
            ],
            'background': [
                r'body\s*{[^}]*background-color:\s*([^;}\s]+)',
                r'\.slide\s*{[^}]*background-color:\s*([^;}\s]+)'
            ],
            'table_border': [
                r'th,?\s*td\s*{[^}]*border:[^}]*solid\s+([^;}\s]+)',
                r'table\s*{[^}]*border-color:\s*([^;}\s]+)'
            ],
            'table_text': [
                r'th,?\s*td\s*{[^}]*color:\s*([^;}\s]+)',
                r'th\s*{[^}]*color:\s*([^;}\s]+)'
            ],
            'code_text': [
                r'pre\s*{[^}]*color:\s*([^;}\s]+)',
                r'code\s*{[^}]*color:\s*([^;}\s]+)'
            ],
            'heading_text': [
                r'h[1-6]\s*{[^}]*color:\s*([^;}\s]+)',
                r'h1\s*{[^}]*color:\s*([^;}\s]+)'
            ],
            'highlight': [
                r'mark\s*{[^}]*?(?<!-)color:\s*([^;}\s]+)'
            ]
        }
        
        for color_type, patterns in color_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, self.css_content, re.IGNORECASE | re.DOTALL)
                if match:
                    color_value = match.group(1).strip()
                    # Skip transparent and inherit values
                    if color_value not in ['transparent', 'inherit']:
                        colors[color_type] = color_value
                        break
        
        self._colors = colors
        return colors
    
    def get_color_value(self, selector_pattern: str, property_name: str = 'color') -> Optional[str]:
        """Extract color value from CSS selector."""
        pattern = rf'{selector_pattern}\s*{{[^}}]*{property_name}:\s*([^;}}]+)'
        match = re.search(pattern, self.css_content, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else None
    
    def get_class_colors(self) -> Dict[str, Tuple[int, int, int]]:
        """Extract inline color classes (e.g., .red { color: #RRGGBB })."""
        class_colors = {}
        class_color_pattern = r'\.([a-zA-Z0-9_-]+)\s*\{[^}]*?color:\s*([^;}{]+)'
        
        for cls, val in re.findall(class_color_pattern, self.css_content, re.IGNORECASE | re.DOTALL):
            val = val.strip()
            rgb = None
            
            if val.startswith('#') and len(val) in (4, 7):  # #rgb or #rrggbb
                hexval = val[1:]
                if len(hexval) == 3:
                    hexval = ''.join([c*2 for c in hexval])
                try:
                    rgb = tuple(int(hexval[i:i+2], 16) for i in (0, 2, 4))
                except ValueError:
                    rgb = None
            else:
                # rgb(r,g,b) format
                rgb_match = re.match(r'rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', val, re.IGNORECASE)
                if rgb_match:
                    rgb = tuple(int(rgb_match.group(i)) for i in range(1, 4))
            
            if rgb:
                class_colors[cls] = rgb
        
        return class_colors
    
    def get_admonition_colors(self) -> Dict[str, Dict[str, str]]:
        """Parse CSS for .admonition.<type> color rules, including combined selectors."""
        colors = {}
        
        # Pattern to match both single and combined selectors
        pattern = re.compile(r'\.admonition\.([^,\s{]+)(?:\s*,\s*\.admonition\.([^,\s{]+))*\s*\{([^}]+)\}', re.DOTALL)
        
        for match in pattern.finditer(self.css_content):
            # Get the CSS rule body
            rule_body = match.group(3) if len(match.groups()) >= 3 else match.group(2)
            
            # Extract all admonition types from the selector
            selector_part = match.group(0).split('{')[0]  # Get everything before the {
            type_matches = re.findall(r'\.admonition\.(\w+)', selector_part)
            
            # Parse colors from the rule body
            bg_match = re.search(r'background(?:-color)?:\s*([^;]+);', rule_body)
            bar_match = re.search(r'border-color:\s*([^;]+);', rule_body)
            
            if bg_match or bar_match:
                # Apply colors to all types found in this selector
                for atype in type_matches:
                    if atype not in colors:
                        colors[atype] = {}
                    if bg_match:
                        colors[atype]['bg'] = bg_match.group(1).strip()
                    if bar_match:
                        colors[atype]['bar'] = bar_match.group(1).strip()
        
        return colors
    
    def get_slide_dimensions(self) -> Dict[str, Any]:
        """Extract slide dimensions from CSS variables."""
        vars_dict = self.get_css_variables()
        
        width_px = self.get_px_value('slide-width')
        height_px = self.get_px_value('slide-height')
        padding_px = self.get_px_value('slide-padding')
        
        # Extract font family
        font_family_match = re.search(r'--slide-font-family:\s*[\'"]([^\'\"]+)[\'"]', self.css_content)
        if not font_family_match:
            raise ValueError(f"❌ CSS theme '{self.theme}' missing required --slide-font-family variable")
        
        return {
            'width_px': width_px,
            'height_px': height_px,
            'padding_px': padding_px,
            'width_inches': width_px / 96,  # 96 DPI standard
            'height_inches': height_px / 96,
            'font_family': font_family_match.group(1)
        }
    
    def get_table_config(self) -> Dict[str, Any]:
        """Extract table styling configuration from CSS variables."""
        font_delta_match = re.search(r'--table-font-delta:\s*(-?\d+)pt', self.css_content)
        width_safety_match = re.search(r'--table-width-safety:\s*([\d.]+)', self.css_content)
        
        if not font_delta_match or not width_safety_match:
            raise ValueError(f"❌ CSS theme '{self.theme}' missing required table styling variables")
        
        return {
            'font_delta': int(font_delta_match.group(1)),
            'width_safety': float(width_safety_match.group(1))
        }
    
    def get_column_config(self) -> Dict[str, int]:
        """Get column gap and padding values from CSS variables."""
        return {
            'gap': self.get_px_value('column-gap'),
            'padding': self.get_px_value('column-padding')
        }


def extract_data_attributes(html_content: str, prefix: str = '') -> Dict[str, str]:
    """
    Extract HTML data attributes in one operation.
    
    Args:
        html_content: HTML content to parse
        prefix: Optional prefix to filter attributes (e.g., 'math' for data-math-*)
        
    Returns:
        Dictionary of attribute names to values
    """
    if prefix:
        pattern = rf'data-{prefix}-([a-z-]+)="([^"]*)"'
        matches = re.findall(pattern, html_content)
        return {name: value for name, value in matches}
    else:
        pattern = r'data-([a-z-]+)="([^"]*)"'
        matches = re.findall(pattern, html_content)
        return {name: value for name, value in matches} 