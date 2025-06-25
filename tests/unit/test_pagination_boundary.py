#!/usr/bin/env python3
"""
Systematic test for pagination boundary detection.
This test validates that content is properly split across slides when it exceeds slide boundaries.
"""

import pytest
import tempfile
import json
from slide_generator.generator import SlideGenerator
from slide_generator.layout_engine import LayoutEngine


class TestPaginationBoundary:
    """Test suite for pagination boundary detection and slide splitting."""
    
    def test_content_exceeding_slide_boundary_gets_paginated(self):
        """Test that content extending beyond slide boundary is moved to next slide."""
        # Create content that will definitely exceed slide height
        markdown_content = """# Large Content Test

## Section 1
This is the first section with some content.

## Section 2  
This is the second section with more content.

## Section 3
This is the third section with even more content.

## Section 4
This is the fourth section that should push us over the limit.

## Section 5
This is the fifth section that definitely exceeds the boundary.

## Section 6
This is the sixth section that should be on a new slide.

## Section 7
This is the seventh section for good measure.

## Section 8
This is the eighth section to ensure pagination.

## Section 9
This is the ninth section that definitely needs a new slide.

## Section 10
This is the tenth section to verify multiple pages."""
        
        generator = SlideGenerator(debug=True)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Generate slides with debug info
            engine = LayoutEngine(debug=True)
            pages = engine.measure_and_paginate(markdown_content, page_height=540, temp_dir=temp_dir)
            
            # Load the layout info to check actual positions
            layout_file = f"{temp_dir}/layout_info.json"
            with open(layout_file, 'r') as f:
                layout_info = json.load(f)
            
            # Verify pagination occurred
            assert len(pages) > 1, f"Expected multiple pages, got {len(pages)}"
            
            # Check that pagination is reasonable - no page should be excessively tall
            for page_idx, page in enumerate(pages):
                if not page:
                    continue
                    
                # Calculate the total height of content on this page
                min_y = min(block.y for block in page)
                max_bottom = max(block.y + block.height for block in page)
                page_content_height = max_bottom - min_y
                
                # Page content height should be reasonable (allow some margin for spacing)
                assert page_content_height <= 600, (
                    f"Page {page_idx + 1}: Content height {page_content_height}px "
                    f"is excessive (should be ≤ 600px)"
                )
            
            print(f"✅ Content properly paginated into {len(pages)} pages")
            for i, page in enumerate(pages):
                print(f"   Page {i+1}: {len(page)} blocks")
    
    def test_boundary_detection_accuracy(self):
        """Test that boundary detection is accurate to the pixel."""
        # Create content that gets very close to but doesn't exceed the boundary
        markdown_content = """# Boundary Test

## Precise Content
This content is designed to test precise boundary detection.

## More Content
Additional content to approach the boundary.

## Final Content
This should fit within the boundary."""
        
        engine = LayoutEngine(debug=True)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            pages = engine.measure_and_paginate(markdown_content, page_height=540, temp_dir=temp_dir)
            
            # Load layout info
            layout_file = f"{temp_dir}/layout_info.json"
            with open(layout_file, 'r') as f:
                layout_info = json.load(f)
            
            # Find the block that's closest to the boundary
            max_bottom = 0
            closest_block = None
            
            for item in layout_info:
                bottom = item['y'] + item['height']
                if bottom > max_bottom:
                    max_bottom = bottom
                    closest_block = item
            
            print(f"Closest block bottom: {max_bottom}px (limit: 540px)")
            print(f"Closest block content: '{closest_block['textContent'][:50]}...'")
            
            # Verify boundary detection logic
            if max_bottom > 540:
                # If content exceeds boundary, it should be on multiple pages
                assert len(pages) > 1, (
                    f"Content exceeds boundary ({max_bottom}px > 540px) "
                    f"but only {len(pages)} page(s) created"
                )
            else:
                # If content fits, it should be on one page
                assert len(pages) == 1, (
                    f"Content fits within boundary ({max_bottom}px <= 540px) "
                    f"but {len(pages)} pages created"
                )
    
    def test_oversized_block_handling(self):
        """Test that oversized blocks are properly marked and handled."""
        # Create content with a very large block
        markdown_content = """# Oversized Block Test

## Normal Content
This is normal content that should fit fine.

## Large List
- This is a very long list item that contains a lot of text and should be quite large
- Another very long list item with extensive content that might be oversized
- A third very long list item to ensure we have substantial content
- Fourth item with even more extensive content to push the boundaries
- Fifth item that definitely makes this block very large
- Sixth item for good measure with additional content
- Seventh item to ensure this becomes an oversized block
- Eighth item with more content to guarantee oversized status
- Ninth item that pushes this way over the size limit
- Tenth item that definitely makes this oversized

## More Normal Content
This should be normal sized content again."""
        
        engine = LayoutEngine(debug=True)
        pages = engine.measure_and_paginate(markdown_content, page_height=540)
        
        # Find oversized blocks
        oversized_blocks = []
        for page in pages:
            for block in page:
                if hasattr(block, 'oversized') and block.oversized:
                    oversized_blocks.append(block)
        
        # Check if any blocks should be marked as oversized
        large_blocks = []
        for page in pages:
            for block in page:
                if block.height > 540 * 0.8:  # > 432px
                    large_blocks.append(block)
        
        print(f"Found {len(large_blocks)} blocks > 80% of slide height")
        print(f"Found {len(oversized_blocks)} blocks marked as oversized")
        
        # If we have large blocks, they should be marked as oversized
        if large_blocks:
            assert len(oversized_blocks) > 0, (
                f"Found {len(large_blocks)} blocks > 432px but none marked as oversized"
            )
            
            for block in oversized_blocks:
                # Oversized blocks should be > 80% of slide height
                assert block.height > 540 * 0.8, (
                    f"Block marked as oversized but height {block.height}px "
                    f"is not > 80% of 540px ({540 * 0.8}px)"
                )
        else:
            print("No blocks large enough to be marked as oversized")
        
        print(f"✅ Found {len(oversized_blocks)} oversized blocks properly marked")
    
    def test_empty_page_prevention(self):
        """Test that empty pages are not created during pagination."""
        markdown_content = """# Page Prevention Test

Content that should not create empty pages.

---

# Explicit Page Break

This content follows an explicit page break."""
        
        engine = LayoutEngine(debug=True)
        pages = engine.measure_and_paginate(markdown_content, page_height=540)
        
        # Verify no empty pages
        for i, page in enumerate(pages):
            assert len(page) > 0, f"Page {i+1} is empty"
            
            # Verify all blocks have content
            for j, block in enumerate(page):
                assert block.content.strip(), (
                    f"Page {i+1}, Block {j+1} has no content: '{block.content}'"
                )
        
        print(f"✅ All {len(pages)} pages have content")
    
    def test_y_coordinate_normalization(self):
        """Test that Y coordinates are properly normalized for each page."""
        markdown_content = """# Multi-Page Test

## Content 1
First section content.

## Content 2  
Second section content.

## Content 3
Third section content that might push to next page.

## Content 4
Fourth section that should definitely be on next page.

## Content 5
Fifth section for additional page testing."""
        
        engine = LayoutEngine(debug=True)
        pages = engine.measure_and_paginate(markdown_content, page_height=300)  # Small height to force pagination
        
        # Verify multiple pages were created
        assert len(pages) > 1, "Expected multiple pages for testing"
        
        # Check Y coordinate normalization for each page
        for page_idx, page in enumerate(pages):
            if not page:
                continue
                
            min_y = min(block.y for block in page)
            max_y = max(block.y for block in page)
            
            # Y coordinates should start near the top margin (around 40px)
            assert min_y >= 30, (
                f"Page {page_idx + 1}: Minimum Y coordinate {min_y} "
                f"should be >= 30 (page top margin)"
            )
            assert min_y <= 50, (
                f"Page {page_idx + 1}: Minimum Y coordinate {min_y} "
                f"should be <= 50 (reasonable top margin)"
            )
            
            # Y coordinates should not exceed reasonable page height
            assert max_y <= 600, (
                f"Page {page_idx + 1}: Maximum Y coordinate {max_y} "
                f"should be <= 600 (reasonable page height)"
            )
        
        print(f"✅ Y coordinates properly normalized across {len(pages)} pages")


if __name__ == "__main__":
    # Allow running this test standalone
    test_suite = TestPaginationBoundary()
    test_suite.test_content_exceeding_slide_boundary_gets_paginated()
    test_suite.test_boundary_detection_accuracy()
    test_suite.test_oversized_block_handling()
    test_suite.test_empty_page_prevention()
    test_suite.test_y_coordinate_normalization()
    print("\n🎉 All pagination boundary tests passed!") 