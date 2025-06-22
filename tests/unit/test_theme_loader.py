"""Test theme loader functionality."""

import pytest
from src.slide_generator.theme_loader import get_css, list_available_themes, validate_theme


def test_get_css_default():
    """Test that default theme loads and returns CSS content."""
    css = get_css("default")
    
    # Should return a non-empty string
    assert isinstance(css, str)
    assert len(css) > 0
    
    # Should contain basic CSS elements
    assert "body" in css
    assert ".slide" in css
    assert "font-family" in css


def test_get_css_dark():
    """Test that dark theme loads and returns CSS content."""
    css = get_css("dark")
    
    # Should return a non-empty string
    assert isinstance(css, str)
    assert len(css) > 0
    
    # Should contain dark theme specific elements
    assert "body" in css
    assert ".slide" in css
    assert "#1a1a1a" in css  # Dark background color


def test_get_css_invalid_theme():
    """Test that invalid theme names raise appropriate errors."""
    # Non-existent theme
    with pytest.raises(FileNotFoundError):
        get_css("nonexistent")
    
    # Invalid characters (path traversal attempt)
    with pytest.raises(ValueError):
        get_css("../evil")
    
    with pytest.raises(ValueError):
        get_css("theme/../../evil")


def test_list_available_themes():
    """Test that list_available_themes returns expected themes."""
    themes = list_available_themes()
    
    # Should return a list
    assert isinstance(themes, list)
    
    # Should contain at least default and dark themes
    assert "default" in themes
    assert "dark" in themes
    
    # Should have at least 2 themes
    assert len(themes) >= 2


def test_validate_theme():
    """Test theme validation function."""
    # Valid themes
    assert validate_theme("default") is True
    assert validate_theme("dark") is True
    
    # Invalid themes
    assert validate_theme("nonexistent") is False
    assert validate_theme("../evil") is False


def test_css_content_quality():
    """Test that CSS content has expected quality and structure."""
    # Test default theme
    default_css = get_css("default")
    
    # Should have reasonable length (more than just a few characters)
    assert len(default_css) > 100
    
    # Should contain essential slide styling
    assert "h1" in default_css
    assert "h2" in default_css
    assert "p" in default_css
    assert "ul" in default_css
    assert "pre" in default_css
    assert "code" in default_css
    
    # Test dark theme
    dark_css = get_css("dark")
    
    # Should be different from default
    assert dark_css != default_css
    
    # Should have reasonable length
    assert len(dark_css) > 100 