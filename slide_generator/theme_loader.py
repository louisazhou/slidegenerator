"""Theme loader for slide generation CSS themes."""
from pathlib import Path
from typing import List


def get_css(theme: str = "default") -> str:
    """
    Load CSS content for the specified theme.
    
    Args:
        theme: Theme name (default, dark, etc.)
        
    Returns:
        CSS content as string
        
    Raises:
        FileNotFoundError: If theme file doesn't exist
        ValueError: If theme name is invalid
    """
    # Validate theme name (security: prevent path traversal)
    if not theme.replace("_", "").replace("-", "").isalnum():
        raise ValueError(f"Invalid theme name: {theme}")
    
    # Get project root directory
    project_root = Path(__file__).parent.parent
    theme_path = project_root / "themes" / f"{theme}.css"
    
    # Check if theme file exists
    if not theme_path.exists():
        available_themes = [
            f.stem for f in (project_root / "themes").glob("*.css")
            if f.is_file()
        ]
        raise FileNotFoundError(
            f"Theme '{theme}' not found. Available themes: {available_themes}"
        )
    
    # Read and return CSS content
    with open(theme_path, 'r', encoding='utf-8') as f:
        css_content = f.read()
    
    return css_content


def list_available_themes() -> List[str]:
    """
    List all available themes.
    
    Returns:
        List of theme names
    """
    project_root = Path(__file__).parent.parent
    themes_dir = project_root / "themes"
    
    if not themes_dir.exists():
        return []
    
    return [f.stem for f in themes_dir.glob("*.css") if f.is_file()]


def validate_theme(theme: str) -> bool:
    """
    Check if a theme exists.
    
    Args:
        theme: Theme name to validate
        
    Returns:
        True if theme exists, False otherwise
    """
    try:
        get_css(theme)
        return True
    except (FileNotFoundError, ValueError):
        return False 