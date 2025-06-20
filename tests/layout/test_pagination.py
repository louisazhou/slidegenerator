#!/usr/bin/env python3
"""
Test for pagination functionality - ensures content is properly split across slides
when it exceeds the maximum slide height.
"""

import os
import sys
import pytest
from pathlib import Path

# Add the project root to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Import the paginate function from slide_proto
from examples.slide_proto import paginate

def dummy_measure(html_content):
    """Create dummy blocks for testing pagination."""
    # Parse the HTML to extract blocks
    blocks = []
    
    # Simple h2 block
    if "<h2>big</h2>" in html_content:
        blocks.append({
            "tagName": "h2",
            "textContent": "big",
            "x": 40,
            "y": 40,
            "width": 880,
            "height": 40
        })
    
    # Add paragraph blocks
    p_count = html_content.count("<p style='height:300px'>x</p>")
    y_pos = 100  # Start position after the heading
    
    for i in range(p_count):
        blocks.append({
            "tagName": "p",
            "textContent": "x",
            "x": 40,
            "y": y_pos,
            "width": 880,
            "height": 300
        })
        y_pos += 320  # Add some spacing between paragraphs
    
    return blocks

def test_pagination_splits_content():
    """Test that content is properly split across slides."""
    # Create HTML content that should span multiple slides
    html = "<h2>big</h2>" + "<p style='height:300px'>x</p>" * 3  # ~900 px total height
    
    # Get blocks from dummy measure function
    blocks = dummy_measure(html)
    
    # Verify we have the expected number of blocks
    assert len(blocks) == 4, f"Expected 4 blocks, got {len(blocks)}"
    
    # Call the paginate function with a max height of 540px
    slides = paginate(blocks, max_px=540)
    
    # We should have at least 2 slides
    assert len(slides) >= 2, f"Expected at least 2 slides, got {len(slides)}"
    
    # First slide should not have more than 540px of content
    total_height_slide1 = sum(block["height"] for block in slides[0])
    assert total_height_slide1 <= 540, f"First slide content exceeds 540px: {total_height_slide1}px"
    
    # Check that all content is included across all slides
    total_blocks_in_slides = sum(len(slide) for slide in slides)
    assert total_blocks_in_slides == len(blocks), "Not all blocks were included in the slides"

def test_respects_page_breaks():
    """Test that page breaks are respected during pagination."""
    # Create blocks with a page break
    blocks = [
        {
            "tagName": "h1",
            "textContent": "Slide 1",
            "x": 40,
            "y": 40,
            "width": 880,
            "height": 60
        },
        {
            "tagName": "p",
            "textContent": "Content for slide 1",
            "x": 40,
            "y": 120,
            "width": 880,
            "height": 100
        },
        {
            "role": "page_break"  # This should force a new slide
        },
        {
            "tagName": "h1",
            "textContent": "Slide 2",
            "x": 40,
            "y": 40,  # Y position doesn't matter for page breaks
            "width": 880,
            "height": 60
        }
    ]
    
    # Call the paginate function
    slides = paginate(blocks, max_px=540)
    
    # We should have exactly 2 slides
    assert len(slides) == 2, f"Expected 2 slides, got {len(slides)}"
    
    # First slide should have 2 blocks
    assert len(slides[0]) == 2, f"Expected 2 blocks in first slide, got {len(slides[0])}"
    
    # Second slide should have 1 block
    assert len(slides[1]) == 1, f"Expected 1 block in second slide, got {len(slides[1])}"
    
    # Check content of each slide
    assert slides[0][0]["textContent"] == "Slide 1", "First slide should start with 'Slide 1'"
    assert slides[1][0]["textContent"] == "Slide 2", "Second slide should start with 'Slide 2'"

if __name__ == "__main__":
    test_pagination_splits_content()
    test_respects_page_breaks()
    print("All tests passed!") 