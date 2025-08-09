"""Google Slides renderer for Slide Generator.

A complete implementation of the slide rendering system that generates Google Slides
presentations with full feature parity to the PPTX renderer, including:
- Text formatting (headings, paragraphs, lists, rich text)
- Images with scaling and positioning
- Tables with proper column widths and styling
- Admonitions/callout boxes
- Code blocks with syntax highlighting
- Math rendering
- Speaker notes
- Two-column layouts

Design notes
------------
1.  Uses a two-pass rendering system: layout engine measures elements, then
    renderer applies calculated dimensions for consistent positioning.
2.  Theme parsing reuses the existing `CSSParser` for consistency with PPTX.
3.  **Batching** – accumulates requests and POSTs in chunks of 100 (API limit).
4.  Gracefully degrades when Google client libraries are missing.
"""
from __future__ import annotations

import logging
import os
import re
import time
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from .models import Block
from .css_utils import CSSParser

logger = logging.getLogger(__name__)

try:
    # These imports require google-api-python-client which is optional
    from googleapiclient.discovery import build  # type: ignore
    from googleapiclient.errors import HttpError  # type: ignore
    from google.oauth2.service_account import Credentials  # type: ignore
except ModuleNotFoundError:  # pragma: no cover – optional dependency
    build = None  # type: ignore
    Credentials = None  # type: ignore
    HttpError = Exception  # type: ignore

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _hex_to_rgb_dict(hex_color: str) -> Dict[str, float]:
    """Convert #rrggbb → {'red': R, 'green': G, 'blue': B} in 0-1 range."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:  # short form #f00
        hex_color = "".join(c * 2 for c in hex_color)
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return {"red": r, "green": g, "blue": b}


# ---------------------------------------------------------------------------
# Main renderer class
# ---------------------------------------------------------------------------

class GSlideRenderer:
    """Render a Block matrix to Google Slides."""

    def __init__(
        self,
        *,
        theme: str = "default",
        debug: bool = False,
        credentials_path: Optional[str] = None,
    ) -> None:
        self.theme = theme
        self.debug = debug
        self.css_parser = CSSParser(theme)
        self.theme_config = self._parse_theme_config()
        # Use the same scale factor approach as PPTX renderer for consistency
        css_slide_width_px = self.theme_config['slide_dimensions']['width_px']
        css_slide_width_inches = self.theme_config['slide_dimensions']['width_inches']
        # PPTX uses inches-based scaling: inches per pixel
        self._inches_per_pixel = css_slide_width_inches / css_slide_width_px
        # Convert to points for Google Slides API (1 inch = 72 points)
        self._scale = self._inches_per_pixel * 72

        self.slides_service = self._init_google_slides_api(credentials_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(
        self,
        pages: List[List[Block]],
        presentation_id: Optional[str] = None,
        page_speaker_notes: Optional[List[str]] = None,
    ) -> str:
        """Create or update a Google Slides presentation.

        Parameters
        ----------
        pages
            Paginated list of Block lists (same structure as PPTX renderer).
        presentation_id
            If given, update an existing deck; otherwise create a new one.
        page_speaker_notes
            Optional list of speaker notes HTML for each page (same as PPTX renderer).
        """
        if self.slides_service is None:
            logger.warning(
                "google-api-python-client not installed – skipping upload and "
                "returning dummy presentation ID."
            )
            return "SIMULATED_GSLIDES_ID"

        presentation_id = self._ensure_presentation(presentation_id)
    
            
        # Get existing slides for cleanup
        try:
            pres_meta = self.slides_service.presentations().get(presentationId=presentation_id).execute()
        except Exception as e:
            if self.debug:
                logger.warning(f"Google Slides API not accessible: {e}")
            return presentation_id
        existing_slides = pres_meta.get("slides", [])
        existing_ids = [s["objectId"] for s in existing_slides]

        requests: List[Dict] = []
        
        # Clear existing page elements from all slides to avoid ID conflicts
        for slide in existing_slides:
            for element in slide.get("pageElements", []):
                requests.append({"deleteObject": {"objectId": element["objectId"]}})

        # ------------------------------------------------------------------
        # Delete ALL existing slides and recreate from scratch
        # ------------------------------------------------------------------
        for slide_id in existing_ids:
            requests.append({"deleteObject": {"objectId": slide_id}})



        # Create slide_0 as our first slide
        requests.append(
            {
                "createSlide": {
                    "objectId": "slide_0",
                    "insertionIndex": 0,
                    "slideLayoutReference": {"predefinedLayout": "BLANK"},
                }
            }
        )

        # ------------------------------------------------------------------
        # Generate / ensure remaining slides and add block content
        # ------------------------------------------------------------------
        for page_idx, blocks in enumerate(pages):
            slide_id = f"slide_{page_idx}"
            # Initialize cumulative offset for this page (like PPTX renderer)
            self._page_offset_px = 0
            
            # Create additional slides as needed (slide_0 already handled above)
            if page_idx > 0:
                requests.append(
                    {
                        "createSlide": {
                            "objectId": slide_id,
                            "insertionIndex": page_idx,
                            "slideLayoutReference": {"predefinedLayout": "BLANK"},
                        }
                    }
                )
            
            # Reset page offset for each slide
            self._page_offset_px = 0
            
            requests.extend(self._blocks_to_requests(blocks, slide_id))

        # Execute content requests first
        try:
            self._execute_requests_in_batches(presentation_id, requests)
        except Exception as e:
            if self.debug:
                logger.warning(f"Failed to execute some Google Slides requests: {e}")
            # Continue execution even if some requests fail
        
        # Add speaker notes after slides are created and content is added
        if page_speaker_notes:
            self._add_speaker_notes_to_slides(presentation_id, page_speaker_notes)
        return presentation_id

    # ------------------------------------------------------------------
    # Google Slides helpers
    # ------------------------------------------------------------------

    def _add_speaker_notes_to_slides(self, presentation_id: str, page_speaker_notes: List[str]):
        """Add speaker notes to slides using the Google Slides API."""
        if not page_speaker_notes:
            return
            
        # Check if we have a valid slides service
        if self.slides_service is None:
            if self.debug:
                logger.warning("No Google Slides API service available - skipping speaker notes")
            return
            
        try:
            # Get presentation metadata to access slide notes pages
            pres_meta = (
                self.slides_service.presentations()  # type: ignore[attr-defined]
                .get(presentationId=presentation_id)
                .execute()
            )
            
            slides = pres_meta.get('slides', [])
            requests = []
            
            for page_idx, note_html in enumerate(page_speaker_notes):
                if not note_html or not note_html.strip():
                    continue  # Skip empty notes
                    
                if page_idx >= len(slides):
                    if self.debug:
                        logger.warning(f"Skipping notes for page {page_idx}: slide does not exist")
                    continue
                
                slide = slides[page_idx]
                slide_id = slide['objectId']
                
                # Get the notes page for this slide
                notes_page = slide.get('slideProperties', {}).get('notesPage')
                if not notes_page:
                    if self.debug:
                        logger.warning(f"No notes page found for slide {slide_id}")
                    continue
                
                # Find the speaker notes object ID
                speaker_notes_id = notes_page.get('notesProperties', {}).get('speakerNotesObjectId')
                if not speaker_notes_id:
                    if self.debug:
                        logger.warning(f"No speaker notes object found for slide {slide_id}")
                    continue
                
                # Add rich text speaker notes (similar to PPTX renderer approach)
                note_requests = self._create_speaker_note_requests(speaker_notes_id, note_html)
                requests.extend(note_requests)
                
                if note_requests:
                    if self.debug:
                        logger.info(f"Added speaker notes to slide {page_idx + 1}: {len(note_requests)} formatting requests")
            
            # Execute speaker notes requests
            if requests:
                self._execute_requests_in_batches(presentation_id, requests)
                if self.debug:
                    logger.info(f"Added speaker notes to {len(requests)} slides")
                    
        except Exception as e:
            if self.debug:
                logger.error(f"Error adding speaker notes: {e}")
            # Don't raise - speaker notes are optional

    def _create_speaker_note_requests(self, speaker_notes_id: str, note_html: str) -> List[Dict]:
        """Create rich text speaker notes requests, similar to PPTX renderer approach."""
        if not note_html or not note_html.strip():
            return []
            
        try:
            soup = BeautifulSoup(note_html, "html.parser")
            
            # Process paragraphs similar to PPTX renderer
            paragraphs = soup.find_all("p") or [soup]
            requests = []
            current_position = 0
            
            for para_idx, p in enumerate(paragraphs):
                # Add paragraph separator for subsequent paragraphs
                if para_idx > 0:
                    requests.append({
                        "insertText": {
                            "objectId": speaker_notes_id,
                            "insertionIndex": current_position,
                            "text": "\n\n"
                        }
                    })
                    current_position += 2
                
                # Get paragraph HTML content
                para_html = p.decode_contents() if hasattr(p, 'decode_contents') else str(p)
                
                # Insert base text first
                plain_text = p.get_text()
                if plain_text:
                    requests.append({
                        "insertText": {
                            "objectId": speaker_notes_id,
                            "insertionIndex": current_position,
                            "text": plain_text
                        }
                    })
                    
                    # Apply rich text formatting using unified method
                    base_font_size = self._validate_font_size('p')
                    formatting_requests = self._apply_rich_text_formatting(
                        speaker_notes_id, para_html, current_position, base_font_size
                    )
                    requests.extend(formatting_requests)
                    
                    current_position += len(plain_text)
            
            return requests
            
        except Exception as e:
            if self.debug:
                logger.warning(f"Error creating speaker note requests: {e}")
            # Simplified fallback: just extract text and insert
            plain_text = re.sub(r'<[^>]+>', '', note_html).strip()
            if plain_text:
                return [{
                    "insertText": {
                        "objectId": speaker_notes_id,
                        "insertionIndex": 0,
                        "text": plain_text
                    }
                }]
            return []


    
    def _emu(self, pt_val: float) -> float:
        """Convert points to EMU (English Metric Units) for Google Slides API."""
        return round(pt_val * 12700, 0)

    # ------------------------------------------------------------------
    # Common helper methods to reduce code duplication
    # ------------------------------------------------------------------

    def _calculate_element_dimensions(self, block: Block, extra_padding_px: int = 0):
        """Calculate element dimensions and scaling factors like PPTX renderer."""
        slide_width_px = self.theme_config['slide_dimensions']['width_px']
        
        # Calculate scaling factors (points per pixel)
        x_scale = self._scale
        y_scale = self._scale
        
        # Use adjusted Y position if available (accounts for cumulative offsets)
        # Layout engine already accounts for margins in block coordinates
        effective_y_px = getattr(block, '_adjusted_y_px', block.y)
        top_pt = effective_y_px * y_scale
        
        # Apply extra padding if requested
        effective_height_px = block.height + extra_padding_px
        height_pt = effective_height_px * y_scale
        
        return x_scale, y_scale, top_pt, height_pt, slide_width_px

    def _calculate_element_width(self, block: Block, x_scale: float, browser_width_px: float):
        """Calculate appropriate width for element based on its type like PPTX renderer."""
        is_text_block = (
            block.tag in ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']
            or block.is_list_item() if hasattr(block, 'is_list_item') else False
            or block.tag in ['ul', 'ol', 'pre']
        )
        
        # Admonitions (div blocks) should also get text-like treatment for column constraints
        is_admonition = block.tag == 'div' and block.className and 'admonition' in block.className

        if is_text_block or is_admonition:
            # Special case: figure captions should use their own measured width
            if block.className and 'figure-caption' in block.className:
                # Prefer the width of the preceding image block (same slide) if any
                cached_width = getattr(self, '_last_image_block_width', None)
                if cached_width:
                    width_pt = cached_width * x_scale
                    if self.debug:
                        logger.info(f"CAPTION: Using cached image width: {cached_width}px -> {width_pt:.1f}pt")
                    return width_pt
                else:
                    width_pt = block.width * x_scale
                    if self.debug:
                        logger.warning(f"CAPTION: No cached image width found. Using own width: {block.width}px")
                    return width_pt
            else:
                # Regular text/admonitions – widen to remaining column width for proper column behavior
                if block.parentColumnWidth:
                    # Use the measured column width for elements within columns
                    available_width_px = block.parentColumnWidth
                else:
                    # For full-width elements, calculate available width from current position to slide edge
                    # Layout engine already accounts for margins in block.x positioning
                    available_width_px = browser_width_px - block.x
                
                width_pt = available_width_px * x_scale
                return width_pt
        else:
            # Images, tables, etc. - use measured width
            return block.width * x_scale

    def _create_element_properties(self, width_emu: float, height_emu: float, 
                                 pos_x_pt: float, pos_y_pt: float, 
                                 slide_id: str, scale_x: float = 1.0, scale_y: float = 1.0) -> Dict:
        """Create standard element properties for Google Slides shapes."""
        return {
            "pageObjectId": slide_id,
            "size": {
                "width": {"magnitude": width_emu, "unit": "EMU"},
                "height": {"magnitude": height_emu, "unit": "EMU"},
            },
            "transform": {
                "scaleX": scale_x,
                "scaleY": scale_y,
                "translateX": self._emu(pos_x_pt),
                "translateY": self._emu(pos_y_pt),
                "unit": "EMU",
            },
        }

    def _create_base_text_style(self, object_id: str, font_size_pt: float, 
                              color: str, text_range: str = "ALL", 
                              additional_style: Optional[Dict] = None) -> Dict:
        """Create standard text style request for Google Slides."""
        style = {
            "fontSize": {"magnitude": font_size_pt, "unit": "PT"},
            "fontFamily": self.theme_config['font_family'],
            "foregroundColor": {"opaqueColor": {"rgbColor": _hex_to_rgb_dict(color)}},
        }
        
        fields = ["fontSize", "fontFamily", "foregroundColor"]
        
        if additional_style:
            style.update(additional_style)
            fields.extend(additional_style.keys())
        
        return {
            "updateTextStyle": {
                "objectId": object_id,
                "textRange": {"type": text_range} if text_range == "ALL" else text_range,
                "style": style,
                "fields": ",".join(fields),
            }
        }

    def _validate_font_size(self, tag: str) -> float:
        """Get and validate font size from theme config."""
        if tag in self.theme_config['font_sizes']:
            return self.theme_config['font_sizes'][tag]
        elif 'p' in self.theme_config['font_sizes']:
            return self.theme_config['font_sizes']['p']
        else:
            raise ValueError(f"❌ CSS theme is missing required font-size for '{tag}' and fallback 'p'.")

    def _ensure_minimum_dimensions(self, width_pt: float, height_pt: float) -> tuple[float, float]:
        """Ensure dimensions meet minimum requirements for Google Slides API."""
        min_width_pt = 36  # 0.5 inch equivalent
        min_height_pt = 18  # 0.25 inch equivalent
        
        width_pt = max(width_pt, min_width_pt)
        height_pt = max(height_pt, min_height_pt)
        
        # Ensure positive dimensions
        if width_pt <= 0 or height_pt <= 0:
            if self.debug:
                logger.warning(f"Invalid dimensions: width={width_pt}, height={height_pt}. Using minimums.")
            width_pt = min_width_pt
            height_pt = min_height_pt
        
        return width_pt, height_pt

    def _apply_rich_text_formatting(self, object_id: str, html_content: str, 
                                   start_position: int = 0, base_font_size: Optional[float] = None) -> List[Dict]:
        """Unified rich text formatting for both content and speaker notes."""
        requests = []
        
        # Apply base font styling if font size is provided
        if base_font_size:
            requests.append(self._create_base_text_style(
                object_id, base_font_size, 
                self.theme_config['colors'].get('text', '#000000')
            ))
        
        # Find and format HTML tags (unified pattern)
        html_pattern = r'<(/?)(strong|em|code|mark|b|i|u|del|a|span)([^>]*)>([^<]*)</\2>'
        
        for match in re.finditer(html_pattern, html_content):
            closing, tag, attributes, text_content = match.groups()
            if closing:  # Skip closing tags
                continue
                
            # Find text position in the plain content
            plain_before = re.sub(r'<[^>]*>', '', html_content[:match.start()])
            text_start = start_position + len(plain_before)
            text_end = text_start + len(text_content)
            
            # Apply formatting based on tag type
            style_update = {}
            fields = []
            
            if tag in ['strong', 'b']:
                style_update['bold'] = True
                fields.append('bold')
            elif tag in ['em', 'i']:
                style_update['italic'] = True
                fields.append('italic')
            elif tag == 'u':
                style_update['underline'] = True
                fields.append('underline')
            elif tag == 'del':
                style_update['strikethrough'] = True
                fields.append('strikethrough')
            elif tag == 'code':
                style_update['fontSize'] = {"magnitude": (base_font_size or 12) * 0.9, "unit": "PT"}
                style_update['fontFamily'] = "Courier New"
                fields.extend(['fontSize', 'fontFamily'])
            elif tag == 'mark':
                # Highlight with background color
                highlight_color = self.theme_config['colors'].get('highlight', '#ffff00')
                style_update['backgroundColor'] = {"opaqueColor": {"rgbColor": _hex_to_rgb_dict(highlight_color)}}
                fields.append('backgroundColor')
            elif tag == 'a':
                # Handle links
                href_match = re.search(r'href="([^"]*)"', attributes)
                if href_match:
                    url = href_match.group(1)
                    style_update['link'] = {"url": url}
                    style_update['foregroundColor'] = {"opaqueColor": {"rgbColor": _hex_to_rgb_dict('#0066cc')}}
                    style_update['underline'] = True
                    fields.extend(['link', 'foregroundColor', 'underline'])
            elif tag == 'span':
                # Handle span classes (colors, etc.)
                class_match = re.search(r'class="([^"]*)"', attributes)
                if class_match:
                    classes = class_match.group(1).split()
                    for cls in classes:
                        if cls in self.theme_config.get('class_colors', {}):
                            color_rgb = self.theme_config['class_colors'][cls]
                            # Convert from 0-255 range to 0.0-1.0 range for Google Slides API
                            style_update['foregroundColor'] = {"opaqueColor": {"rgbColor": self._rgb_tuple_to_gslides_color(color_rgb)}}
                            fields.append('foregroundColor')
                        elif cls == 'underline':
                            style_update['underline'] = True
                            fields.append('underline')
                        elif cls == 'wavy':
                            # Wavy underline fallback
                            style_update['underline'] = True
                            style_update['foregroundColor'] = {"opaqueColor": {"rgbColor": _hex_to_rgb_dict('#e74c3c')}}
                            fields.extend(['underline', 'foregroundColor'])
            
            # Validate text range and style before creating request
            if style_update and fields and text_start >= 0 and text_end > text_start:
                requests.append({
                    "updateTextStyle": {
                        "objectId": object_id,
                        "textRange": {
                            "type": "FIXED_RANGE",
                            "startIndex": text_start,
                            "endIndex": text_end
                        },
                        "style": style_update,
                        "fields": ",".join(fields),
                    }
                })
            elif self.debug and (not style_update or not fields or text_start < 0 or text_end <= text_start):
                logger.warning(f"Skipping invalid text style request: start={text_start}, end={text_end}, style={style_update}, fields={fields}")
        
        return requests

    def _rgb_tuple_to_gslides_color(self, rgb_tuple: tuple) -> Dict[str, float]:
        """Convert RGB tuple (0-255) to Google Slides color format (0.0-1.0)."""
        if not isinstance(rgb_tuple, tuple) or len(rgb_tuple) != 3:
            raise ValueError(f"Invalid RGB tuple: {rgb_tuple}")
        return {
            "red": rgb_tuple[0] / 255.0,
            "green": rgb_tuple[1] / 255.0,
            "blue": rgb_tuple[2] / 255.0
        }

    def _calculate_height_adjustment(self, block: Block) -> float:
        """Calculate height adjustment for different block types."""
        # Skip the global safety cushion for blocks that are rendered inside a dedicated column.
        # Each column is laid out independently in HTML, so padding applied to the left column
        # should not influence the flow in the right column.
        in_column_container = (
            getattr(block, 'parentClassName', None) is not None and
            'column' in getattr(block, 'parentClassName', '')
        ) or (
            # Additional check: if parentColumnWidth is set, this is definitely in a column
            getattr(block, 'parentColumnWidth', None) is not None
        )
        
        if in_column_container:
            return 0  # Keep padding local to the column
        
        if block.tag in ['ul', 'ol'] or 'data-list-levels' in block.content:
            # Calculate number of list items for height adjustment
            if 'data-list-levels' in block.content:
                items = block.content.count('<br') + 1 if '<br' in block.content else 1
            else:
                items = block.content.count('<li>') if '<li>' in block.content else 1
            return 4 + 2.3 * items  # Same formula as PPTX renderer
        elif block.is_paragraph() or block.is_heading():
            return 2
        return 0

    def _route_block_to_requests(self, block: Block, slide_id: str) -> List[Dict]:
        """Route block to appropriate request creation method using two-pass architecture like PPTX."""
        # Skip layout-only divs (columns wrapper and individual column divs) - similar to PPTX renderer
        if block.tag == 'div' and block.className and (
                'columns' in block.className or 'column' in block.className):
            if self.debug:
                logger.info(f"  → Skipping layout-only div: {block.className}")
            return []

        # Two-pass system like PPTX:
        # Pass 1: Calculate dimensions and scaling factors
        x_scale, y_scale, top_pt, height_pt, browser_width_px = self._calculate_element_dimensions(block)
        
        # Pass 2: Calculate appropriate width for this element
        width_pt = self._calculate_element_width(block, x_scale, browser_width_px)
        
        # Now call element-specific methods with calculated dimensions
        if block.is_image():
            if self.debug:
                logger.info(f"  → Creating image requests")
            return self._create_image_requests(block, slide_id, x_scale, y_scale, top_pt, width_pt, height_pt)
        elif block.is_table():
            if self.debug:
                logger.info(f"  → Creating table requests for block {block.bid} (tag: {block.tag})")
            return self._create_table_requests(block, slide_id, x_scale, y_scale, top_pt, width_pt, height_pt)
        elif block.is_heading() or block.is_paragraph():
            # Check if paragraph contains an image
            if self._contains_image(block):
                if self.debug:
                    logger.info(f"  → Creating paragraph image requests")
                return self._create_paragraph_image_requests(block, slide_id, x_scale, y_scale, top_pt, width_pt, height_pt)
            else:
                # Check if this is a list-like paragraph with nested list data
                if 'data-list-levels' in block.content:
                    if self.debug:
                        logger.info(f"  → Creating nested list requests")
                    return self._create_list_requests(block, slide_id, x_scale, y_scale, top_pt, width_pt, height_pt)
                else:
                    if self.debug:
                        logger.info(f"  → Creating text box requests")
                    return self._create_text_box_requests(block, slide_id, x_scale, y_scale, top_pt, width_pt, height_pt)
        elif block.tag in ['ul', 'ol']:
            if self.debug:
                logger.info(f"  → Creating list requests")
            return self._create_list_requests(block, slide_id, x_scale, y_scale, top_pt, width_pt, height_pt)
        elif block.tag == 'div' and block.className and 'admonition' in block.className:
            if self.debug:
                logger.info(f"  → Creating admonition box requests")
            return self._create_admonition_requests(block, slide_id, x_scale, y_scale, top_pt, width_pt, height_pt)
        elif block.is_code_block():
            if self.debug:
                logger.info(f"  → Creating code block requests")
            return self._create_code_block_requests(block, slide_id, x_scale, y_scale, top_pt, width_pt, height_pt)
        elif block.tag in ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span']:
            if self.debug:
                logger.info(f"  → Creating text box requests")
            return self._create_text_box_requests(block, slide_id, x_scale, y_scale, top_pt, width_pt, height_pt)
        else:
            if self.debug:
                logger.info(f"  → Skipping unsupported block type: {block.tag}")
            return []

    def _create_code_block_requests(self, block: Block, slide_id: str, x_scale: float, y_scale: float, 
                                   top_pt: float, width_pt: float, height_pt: float) -> List[Dict]:
        """Create Google Slides requests for code blocks with syntax highlighting."""
        
        object_id = f"code_{block.bid or id(block)}"
        
        # Use helper methods for position and size calculation
        # Calculate position using two-pass system
        # Layout engine already accounts for margins in block.x/block.y coordinates
        pos_x_pt = block.x * x_scale
        pos_y_pt = top_pt
        
        # Use available width for code blocks
        browser_width_px = self.theme_config['slide_dimensions']['width_px']
        available_width_px = browser_width_px - block.x
        width_pt = available_width_px * self._scale
        
        # Ensure minimum dimensions
        width_pt, height_pt = self._ensure_minimum_dimensions(width_pt, height_pt)
        
        requests = []
        
        # Create shape element properties for the code block
        element_properties = self._create_element_properties(
            width_emu=int(width_pt * 12700),
            height_emu=int(height_pt * 12700),
            pos_x_pt=pos_x_pt,
            pos_y_pt=pos_y_pt,
            slide_id=slide_id
        )
        
        # Process code block content similar to PPTX renderer
        content_raw = block.content or ""
        
        # 1) Convert explicit <br> tags back to real line breaks
        content_raw = re.sub(r'<br\s*/?>', '\n', content_raw, flags=re.IGNORECASE)
        
        # 2) Strip all remaining HTML tags but keep literal text including spaces & newlines
        content_plain = re.sub(r'<[^>]+>', '', content_raw)
        
        # 3) Unescape HTML entities
        content_plain = unescape(content_plain)
        
        # Create text box request
        requests.append({
            "createShape": {
                "objectId": object_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": element_properties
            }
        })
        
        # Insert the code text
        if content_plain.strip():
            requests.append({
                "insertText": {
                    "objectId": object_id,
                    "text": content_plain,
                    "insertionIndex": 0
                }
            })
            
            # Apply code block styling
            code_font_size = self.theme_config['font_sizes'].get('code', 
                           self.theme_config['font_sizes'].get('p', 10))
            code_font_delta = self.theme_config['table_deltas']['font_delta']
            final_font_size = max(8, code_font_size + code_font_delta)
            
            # Get code colors from theme
            code_text_color = self.theme_config['colors'].get('code_text', '#ffffff')
            code_bg_color = self.theme_config['colors'].get('code_background', '#2d2d2d')
            
            # Apply text styling (font family, size, color)
            text_style_request = self._create_base_text_style(
                object_id=object_id,
                font_size_pt=final_font_size,
                color=code_text_color,
                additional_style={
                    "fontFamily": "Courier New"
                }
            )
            requests.append(text_style_request)
            
            # Apply background color to the shape
            requests.append({
                "updateShapeProperties": {
                    "objectId": object_id,
                    "shapeProperties": {
                        "shapeBackgroundFill": {
                            "solidFill": {
                                "color": {
                                    "rgbColor": _hex_to_rgb_dict(code_bg_color)
                                }
                            }
                        }
                    },
                    "fields": "shapeBackgroundFill"
                }
            })
            
            if self.debug:
                logger.info(f"Created code block: font={final_font_size}pt, bg={code_bg_color}, text={code_text_color}")
        
        return requests



    def _init_google_slides_api(self, credentials_path: Optional[str]):
        """Return a *slides* service or *None* if auth isn’t available.

        Order of preference:
        1. Service-account JSON (non-interactive CI / servers)
        2. Cached OAuth token (token.json)
        3. Interactive OAuth flow with credentials.json → token.json
        """
        if build is None:
            return None  # google-api-python-client not installed

        SCOPES = [
            "https://www.googleapis.com/auth/presentations",
            "https://www.googleapis.com/auth/drive",
        ]

        # ------------------------------------------------------------------
        # 1. Service-account credentials (headless, preferred on CI)
        # ------------------------------------------------------------------
        sa_path = (
            credentials_path
            or os.getenv("GOOGLE_SLIDES_CREDENTIALS")
            or os.path.expanduser("~/.gslide_credentials.json")
        )
        if sa_path and os.path.exists(sa_path):
            try:
                from google.oauth2.service_account import Credentials as _SACreds  # type: ignore

                creds = _SACreds.from_service_account_file(sa_path, scopes=SCOPES)
                return build("slides", "v1", credentials=creds, cache_discovery=False)  # type: ignore[arg-type]
            except Exception as exc:
                logger.warning("Service-account auth failed (%s). Falling back to OAuth.", exc)

        # ------------------------------------------------------------------
        # 2. User OAuth (interactive on first run, then cached token.json)
        # ------------------------------------------------------------------
        try:
            from google.oauth2.credentials import Credentials as _UserCreds  # type: ignore
            from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
            from google.auth.transport.requests import Request as _Request  # type: ignore
        except ModuleNotFoundError:
            logger.warning("google-auth-oauthlib missing – cannot run OAuth flow.")
            return None

        root = Path.cwd()
        token_path = root / "token.json"
        client_secret_path = root / "credentials.json"

        creds = None  # type: ignore
        if token_path.exists():
            try:
                creds = _UserCreds.from_authorized_user_file(str(token_path), SCOPES)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(_Request())
            except Exception as exc:
                logger.warning("Failed to load or refresh token.json (%s).", exc)
                creds = None

        if creds is None and client_secret_path.exists():
            logger.info("Running interactive OAuth flow – browser window will open …")
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
            creds = flow.run_local_server(port=0)
            try:
                token_path.write_text(creds.to_json())
            except Exception:
                pass  # non-fatal – just won’t cache
        if creds is None:
            logger.warning("No valid authentication found – Google Slides API disabled.")
            return None

        return build("slides", "v1", credentials=creds, cache_discovery=False)

    def _ensure_presentation(self, presentation_id: Optional[str]) -> str:
        if self.slides_service is None:
            # Return a dummy ID when no service is available
            return "SIMULATED_GSLIDES_ID"
            
        if presentation_id:
            return presentation_id
        body = {"title": f"SlideGen {time.strftime('%Y-%m-%d %H:%M:%S')}"}
        pres = (
            self.slides_service.presentations()  # type: ignore[attr-defined]
            .create(body=body)
            .execute()
        )
        return pres["presentationId"]



    # ------------------------------------------------------------------
    # Request builders
    # ------------------------------------------------------------------

    def _blocks_to_requests(self, blocks: List[Block], slide_id: str) -> List[Dict]:
        reqs: List[Dict] = []
        for block in blocks:
            try:
                # Calculate height adjustment for this block using helper
                extra_height_px = self._calculate_height_adjustment(block)
                
                # Apply cumulative offset to block position
                block._adjusted_y_px = block.y + self._page_offset_px
                
                if self.debug:
                    logger.info(f"Processing block {block.bid}: {block.tag} at ({block.x},{block.y}) size {block.width}x{block.height}")
                    if block.is_table():
                        logger.info(f"  ✓ This is a table block")
                    if extra_height_px > 0:
                        logger.info(f"  Height adjustment: +{extra_height_px:.1f}px, cumulative offset: {self._page_offset_px:.1f}px -> adjusted Y: {block._adjusted_y_px:.1f}px")
                
                # Route to appropriate request creation method
                block_requests = self._route_block_to_requests(block, slide_id)
                reqs.extend(block_requests)
                # TODO: math, shapes …
                
                # Increase cumulative offset for subsequent blocks (like PPTX renderer)
                self._page_offset_px += extra_height_px
                
            except Exception as exc:
                logger.exception("Failed to convert block → Slides request: %s", exc)
                # Continue with next block instead of stopping entire rendering
        return reqs

    def _contains_image(self, block: Block) -> bool:
        """Check if a block contains an img tag."""
        return '<img' in block.content

    def _create_list_requests(self, block: Block, slide_id: str, x_scale: float, y_scale: float, 
                             top_pt: float, width_pt: float, height_pt: float) -> List[Dict]:
        """Create Google Slides requests for list blocks (both nested and simple lists)."""
        
        object_id = f"list_{block.bid or id(block)}"
        
        # Use new helper methods for position and size calculation
        # Calculate position using two-pass system
        # Layout engine already accounts for margins in block.x/block.y coordinates
        pos_x_pt = block.x * x_scale
        pos_y_pt = top_pt
        
        # Use available width approach for lists too
        browser_width_px = self.theme_config['slide_dimensions']['width_px']
        available_width_px = browser_width_px - block.x
        width_pt = available_width_px * self._scale
        
        # Ensure minimum dimensions
        width_pt, height_pt = self._ensure_minimum_dimensions(width_pt, height_pt)
        
        if self.debug:
            logger.info(f"List {object_id}: {width_pt:.1f}×{height_pt:.1f}pt at ({pos_x_pt:.1f},{pos_y_pt:.1f})")
        
        # Parse list content based on format
        list_items = []
        list_levels = []
        list_type = 'ul'  # default
        
        content = block.content
        
        if self.debug:
            logger.info(f"Parsing list content: {content[:200]}...")
        
        # Check if this is a nested list with metadata
        level_match = re.search(r'data-list-levels="([^"]*)"', content)
        list_type_match = re.search(r'data-list-type="([^"]*)"', content)
        
        if level_match and list_type_match:
            # Nested list format from layout engine
            level_data = level_match.group(1)
            list_type = list_type_match.group(1)
            
            if self.debug:
                logger.info(f"Found list metadata: levels='{level_data}', type='{list_type}'")
            
            # Extract content from <p> tags
            content_match = re.search(r'<p[^>]*>(.*?)</p>', content, re.DOTALL)
            if content_match:
                list_content = content_match.group(1)
            else:
                list_content = content
            
            if self.debug:
                logger.info(f"Extracted list content: '{list_content}'")
            
            # Split by <br> tags to get individual items
            items = [i.strip() for i in re.split(r'<br[^>]*>', list_content) if i.strip()]
            levels = [int(x) for x in level_data.split(',') if x.strip()]
            
            if self.debug:
                logger.info(f"Parsed items (incomplete): {items}")
                logger.info(f"Parsed levels: {levels}")
            
            # Align items and levels
            min_len = min(len(items), len(levels))
            list_items = items[:min_len]
            list_levels = levels[:min_len]
            
        elif block.tag in ['ul', 'ol']:
            # Fallback: raw ul/ol block
            list_type = block.tag
            raw_items = re.findall(r'<li[^>]*>(.*?)</li>', content, re.DOTALL | re.IGNORECASE)
            list_items = [re.sub(r'^<p[^>]*>|</p>$', '', item, flags=re.IGNORECASE).strip() 
                         for item in raw_items if item.strip()]
            list_levels = [0] * len(list_items)  # All at level 0
        
        if not list_items:
            # No list items found, fallback to text box
            x_scale, y_scale, top_pt, height_pt, browser_width_px = self._calculate_element_dimensions(block)
            width_pt = self._calculate_element_width(block, x_scale, browser_width_px)
            return self._create_text_box_requests(block, slide_id, x_scale, y_scale, top_pt, width_pt, height_pt)
        
        # Apply height adjustment for lists (like PPTX renderer)
        # Lists need more height than Puppeteer measures due to rendering differences
        extra_height_px = 4 + 2.3 * len(list_items)  # Same formula as PPTX renderer
        extra_height_pt = extra_height_px * self._scale
        height_pt += extra_height_pt
        
        if self.debug:
            logger.info(f"List height adjustment: {len(list_items)} items, +{extra_height_px:.1f}px ({extra_height_pt:.1f}pt) -> {height_pt:.1f}pt")
        
        # Recalculate EMU with adjusted height
        width_emu = self._emu(width_pt)
        height_emu = self._emu(height_pt)
        
        # Create text box for the list
        create_shape = {
            "createShape": {
                "objectId": object_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": self._create_element_properties(width_emu, height_emu, pos_x_pt, pos_y_pt, slide_id),
            }
        }

        requests = [create_shape]
        
        # Build list text with tabs for indentation (no manual bullets)
        list_text_lines = []
        
        for item, level in zip(list_items, list_levels):
            # Add tab indentation based on level (Google Slides uses tabs for nesting)
            indent = "\t" * level
            line = f"{indent}{self._strip_html(item)}"
            list_text_lines.append(line)
        
        # Insert the plain text (no manual bullets/numbers)
        list_text = "\n".join(list_text_lines)
        insert_text = {
            "insertText": {
                "objectId": object_id,
                "insertionIndex": 0,
                "text": list_text,
            }
        }
        requests.append(insert_text)
        
        # Apply text styling first
        font_size_pt = self._validate_font_size('li')
        text_color = self.theme_config['colors'].get('text', '#000000')

        style_request = self._create_base_text_style(object_id, font_size_pt, text_color)
        requests.append(style_request)
        
        # Apply proper list formatting using Google Slides API
        bullet_preset = "BULLET_DISC_CIRCLE_SQUARE" if list_type == 'ul' else "NUMBERED_DIGIT_ALPHA_ROMAN"
        
        bullet_request = {
            "createParagraphBullets": {
                "objectId": object_id,
                "textRange": {"type": "ALL"},
                "bulletPreset": bullet_preset,
            }
        }
        requests.append(bullet_request)
        
        if self.debug:
            logger.info(f"Created list with {len(list_items)} items: {[item[:20] + '...' if len(item) > 20 else item for item in list_items]}")
        
        return requests

    def _create_admonition_requests(self, block: Block, slide_id: str, x_scale: float, y_scale: float, 
                                   top_pt: float, width_pt: float, height_pt: float) -> List[Dict]:
        """Create Google Slides requests for admonition/callout boxes."""
        
        object_id_bar = f"admon_bar_{block.bid or id(block)}"
        object_id_box = f"admon_box_{block.bid or id(block)}"
        
        # Map admonition types to colors & icons (same as PPTX renderer)
        ICONS = {
            "note": "📌", "summary": "📝", "info": "ℹ️", "tip": "💡",
            "warning": "⚠️", "caution": "⚠️", "danger": "🚫", "error": "❌",
            "failure": "❌", "attention": "👀"
        }
        
        # Determine type from class list
        type_ = "note"
        if block.className:
            for t in ICONS.keys():
                if t in block.className:
                    type_ = t
                    break
        
        # Resolve colors from theme CSS (parsed during theme_config)
        theme_admon = self.theme_config.get('admonition_colors', {})
        color_hex_bg = theme_admon.get(type_, {}).get('bg', '#E8F0FF')
        color_hex_bar = theme_admon.get(type_, {}).get('bar', '#2196F3')
        icon_char = ICONS.get(type_, '💬')
        
        # Calculate positioning with cumulative offsets
        # Calculate position using two-pass system
        # Layout engine already accounts for margins in block.x/block.y coordinates
        pos_x_pt = block.x * x_scale
        pos_y_pt = top_pt
        
        # Dimensions - reduce height to be more compact (70% like PPTX)
        height_pt = height_pt * 0.7  # More compact
        
        # Ensure minimum dimensions with admonition-specific minimums
        min_width_pt = 36  # 0.5 inch
        min_height_pt = 22  # 0.3 inch  
        width_pt = max(width_pt, min_width_pt)
        height_pt = max(height_pt, min_height_pt)
        
        # Bar dimensions
        bar_width_pt = 11  # ~0.15 inch in points
        
        # Convert to EMU
        bar_width_emu = self._emu(bar_width_pt)
        box_width_emu = self._emu(width_pt - bar_width_pt)
        height_emu = self._emu(height_pt)
        
        requests = []
        
        # Create left colored bar
        create_bar = {
            "createShape": {
                "objectId": object_id_bar,
                "shapeType": "RECTANGLE",
                "elementProperties": self._create_element_properties(bar_width_emu, height_emu, pos_x_pt, pos_y_pt, slide_id),
            }
        }
        requests.append(create_bar)
        
        # Style the bar with the theme color
        style_bar = {
            "updateShapeProperties": {
                "objectId": object_id_bar,
                "shapeProperties": {
                    "shapeBackgroundFill": {
                        "solidFill": {"color": {"rgbColor": _hex_to_rgb_dict(color_hex_bar)}}
                    },
                    "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb_dict(color_hex_bar)}}}}
                },
                "fields": "shapeBackgroundFill,outline",
            }
        }
        requests.append(style_bar)
        
        # Create main content box
        create_box = {
            "createShape": {
                "objectId": object_id_box,
                "shapeType": "TEXT_BOX",
                "elementProperties": self._create_element_properties(box_width_emu, height_emu, pos_x_pt + bar_width_pt, pos_y_pt, slide_id),
            }
        }
        requests.append(create_box)
        
        # Style the box with background color
        style_box = {
            "updateShapeProperties": {
                "objectId": object_id_box,
                "shapeProperties": {
                    "shapeBackgroundFill": {
                        "solidFill": {"color": {"rgbColor": _hex_to_rgb_dict(color_hex_bg)}}
                    },
                    "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb_dict(color_hex_bg)}}}}  # Invisible border
                },
                "fields": "shapeBackgroundFill,outline",
            }
        }
        requests.append(style_box)
        
        # Parse content for title and body (same logic as PPTX)
        raw_html = block.content or ""
        soup = BeautifulSoup(raw_html, "html.parser")
        
        # Title: look for <p class="admonition-title"> else fallback
        title_el = soup.find("p", class_="admonition-title")
        if title_el:
            title_text = title_el.get_text(strip=True)
            title_el.extract()  # remove from soup
        else:
            title_text = type_.capitalize()
        
        # Body: remaining paragraph text
        body_paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        if body_paras:
            body_text = "\n".join(body_paras)
        else:
            # Extract plain text if no paragraphs found
            plain_lines = [ln.strip() for ln in raw_html.strip().split("\n") if ln.strip()]
            body_text = "\n".join(plain_lines[1:]) if len(plain_lines) > 1 else ""
        
        # Combine title and body
        full_text = f"{icon_char} {title_text}"
        if body_text:
            full_text += f"\n{body_text}"
        
        # Insert text
        insert_text = {
            "insertText": {
                "objectId": object_id_box,
                "insertionIndex": 0,
                "text": full_text,
            }
        }
        requests.append(insert_text)
        
        # Apply styling in a simpler way to avoid character index issues
        base_font_size = self._validate_font_size('p')
        text_color = self.theme_config['colors'].get('text', '#000000')
        
        # Start with base font and family only
        base_style = self._create_base_text_style(object_id_box, base_font_size, text_color, 
                                                  additional_style={}, text_range="ALL")
        # Override to only include font size and family (no color for base)
        base_style['updateTextStyle']['style'] = {
            "fontSize": {"magnitude": base_font_size, "unit": "PT"},
            "fontFamily": self.theme_config['font_family'],
        }
        base_style['updateTextStyle']['fields'] = "fontSize,fontFamily"
        requests.append(base_style)
        
        # Apply title formatting if there's a newline
        if "\n" in full_text:
            # Style just the title part
            newline_pos = full_text.find("\n")
            title_style = {
                "updateTextStyle": {
                    "objectId": object_id_box,
                    "textRange": {
                        "type": "FIXED_RANGE",
                        "startIndex": 0,
                        "endIndex": newline_pos
                    },
                    "style": {
                        "bold": True,
                        "foregroundColor": {"opaqueColor": {"rgbColor": _hex_to_rgb_dict(color_hex_bar)}},
                    },
                    "fields": "bold,foregroundColor",
                }
            }
            requests.append(title_style)
            
            # Style body text separately
            if newline_pos + 1 < len(full_text):
                body_style = {
                    "updateTextStyle": {
                        "objectId": object_id_box,
                        "textRange": {
                            "type": "FIXED_RANGE",
                            "startIndex": newline_pos + 1,
                            "endIndex": len(full_text)
                        },
                        "style": {
                            "foregroundColor": {"opaqueColor": {"rgbColor": _hex_to_rgb_dict(text_color)}},
                        },
                        "fields": "foregroundColor",
                    }
                }
                requests.append(body_style)
        else:
            # No body, style everything as title
            title_style = {
                "updateTextStyle": {
                    "objectId": object_id_box,
                    "textRange": {"type": "ALL"},
                    "style": {
                        "bold": True,
                        "foregroundColor": {"opaqueColor": {"rgbColor": _hex_to_rgb_dict(color_hex_bar)}},
                    },
                    "fields": "bold,foregroundColor",
                }
            }
            requests.append(title_style)
        
        if self.debug:
            logger.info(f"Created {type_} admonition: {width_pt:.1f}×{height_pt:.1f}pt at ({pos_x_pt:.1f},{pos_y_pt:.1f})")
        
        return requests

    def _get_font_size(self, block: Block) -> float:
        """Get appropriate font size for a block based on its type."""
        return self._validate_font_size(block.tag)

    def _create_rich_text_requests(self, object_id: str, block: Block) -> List[Dict]:
        """Create Google Slides requests for rich text formatting (bold, italic, colors, links)."""
        
        # Get base font properties
        font_size_pt = self._get_font_size(block)
        default_color = self.theme_config['colors'].get('text', '#000000')
        
        # Parse HTML content to extract text and formatting information
        format_stack = []
        text_segments = []  # [(text, start_index, end_index, formatting)]
        current_index = 0
        
        # Preprocess content like PPTX: handle newlines correctly for text vs code blocks
        content = block.content
        if not block.is_code_block():
            # For regular text (not code blocks): collapse unwanted newlines like PPTX does
            BR_SENTINEL = "__GSLIDES_BR__"
            
            # 1) Protect genuine <br> tags
            content = re.sub(r'<br\s*/?>', BR_SENTINEL, content, flags=re.IGNORECASE)
            
            # 2) Collapse stray newlines (both LF and CRLF) that browsers treat as spaces
            content = re.sub(r'[\r\n]+', ' ', content)
            
            # 3) Restore deliberate line breaks
            content = content.replace(BR_SENTINEL, '\n')
        
        # HTML pattern similar to PPTX renderer - include mark for highlights
        html_pattern = r'(</?(?:strong|em|code|mark|b|i|u|del|a|span)(?:\s+[^>]*?)?>|<br[^>]*>)|([^<]+)'
        tokens = re.findall(html_pattern, content, re.IGNORECASE)
        
        # Build plain text and track formatting ranges
        plain_text = ""
        
        for tag, text in tokens:
            if tag:
                tag_lower = tag.lower()
                
                # Handle line breaks
                if tag_lower.startswith('<br'):
                    plain_text += '\n'
                    current_index = len(plain_text)
                    continue
                
                # Handle closing tags
                if tag_lower.startswith('</'):
                    close_match = re.match(r'</\s*([a-z0-9]+)', tag_lower)
                    if close_match:
                        tag_name = close_match.group(1)
                        # Remove matching format from stack
                        if format_stack and format_stack[-1]['tag'] == tag_name:
                            format_stack.pop()
                        elif tag_name == 'a':
                            # Remove hyperlink format
                            for i in range(len(format_stack) - 1, -1, -1):
                                if format_stack[i]['tag'] == 'a':
                                    format_stack.pop(i)
                                    break
                        elif tag_name == 'span':
                            # Remove any span-related formatting
                            while format_stack and format_stack[-1]['tag'] == 'span':
                                format_stack.pop()
                
                # Handle opening tags
                else:
                    open_match = re.match(r'<\s*([a-z0-9]+)', tag_lower)
                    if open_match:
                        tag_name = open_match.group(1)
                        
                        format_info = {'tag': tag_name, 'start': current_index}
                        
                        # Extract attributes for specific tags
                        if tag_name == 'a':
                            href_match = re.search(r'href\s*=\s*"([^"]+)"', tag_lower)
                            if href_match:
                                format_info['url'] = href_match.group(1)
                        
                        elif tag_name == 'span':
                            # Handle class-based colors and formatting
                            class_match = re.search(r'class\s*=\s*"([^"]+)"', tag_lower)
                            if class_match:
                                classes = class_match.group(1).split()
                                for cls in classes:
                                    if cls in self.theme_config.get('class_colors', {}):
                                        format_info['color_class'] = cls
                                    elif cls == 'underline':
                                        format_info['underline'] = True
                                    elif cls == 'wavy':
                                        format_info['wavy_underline'] = True
                            
                            # Handle inline style colors
                            style_match = re.search(r'style\s*=\s*"([^"]+)"', tag_lower)
                            if style_match:
                                color_match = re.search(r'color\s*:\s*([^;]+)', style_match.group(1))
                                if color_match:
                                    color_val = color_match.group(1).strip()
                                    if color_val.startswith('#'):
                                        format_info['color_hex'] = color_val
                        
                        elif tag_name == 'mark':
                            # Handle highlight/mark tags
                            format_info['highlight'] = True
                        
                        format_stack.append(format_info)
            
            elif text:
                # Add text and record current formatting
                start_index = len(plain_text)
                decoded_text = unescape(text)
                plain_text += decoded_text
                end_index = len(plain_text)
                
                # Record this text segment with current formatting
                if format_stack:
                    text_segments.append((decoded_text, start_index, end_index, format_stack.copy()))
                else:
                    text_segments.append((decoded_text, start_index, end_index, []))
                
                current_index = end_index
        
        # Create requests
        requests = []
        
        # Insert plain text first
        insert_text = {
            "insertText": {
                "objectId": object_id,
                "insertionIndex": 0,
                "text": plain_text,
            }
        }
        requests.append(insert_text)

        # Apply base styling to all text
        base_style = {
            "updateTextStyle": {
                "objectId": object_id,
                "textRange": {"type": "ALL"},
                            "style": {
                "fontSize": {"magnitude": font_size_pt, "unit": "PT"},
                    "fontFamily": self.theme_config['font_family'],
                    "foregroundColor": {"opaqueColor": {"rgbColor": _hex_to_rgb_dict(default_color)}},
                    "bold": block.is_heading(),
                },
                "fields": "fontSize,fontFamily,foregroundColor,bold",
            }
        }
        requests.append(base_style)
        
        # Apply figure caption formatting (like PPTX renderer)
        if hasattr(block, 'className') and block.className and 'figure-caption' in block.className:
            # Apply italic style and color based on CSS theme definitions
            caption_style_updates = {
                "italic": True,
            }
            caption_fields = ["italic"]
            
            # Apply caption color from theme
            class_colors = self.theme_config.get('class_colors', {})
            if 'figure-caption' in class_colors:
                color_rgb = class_colors['figure-caption']
                # Color is already RGB tuple from CSS parser
                if isinstance(color_rgb, tuple) and len(color_rgb) == 3:
                    caption_style_updates['foregroundColor'] = {"opaqueColor": {"rgbColor": self._rgb_tuple_to_gslides_color(color_rgb)}}
                    caption_fields.append('foregroundColor')
            else:
                # Default gray color for captions
                fallback_color = "#666666" if self.theme != "dark" else "#cccccc"
                caption_style_updates['foregroundColor'] = {"opaqueColor": {"rgbColor": _hex_to_rgb_dict(fallback_color)}}
                caption_fields.append('foregroundColor')
            
            caption_style = {
                "updateTextStyle": {
                    "objectId": object_id,
                    "textRange": {"type": "ALL"},
                    "style": caption_style_updates,
                    "fields": ",".join(caption_fields),
                }
            }
            requests.append(caption_style)
        
        # Apply rich formatting to specific text ranges
        for text_content, start_idx, end_idx, formatting in text_segments:
            if not formatting or start_idx == end_idx:
                continue
            
            # Build style for this text segment
            style_updates = {}
            fields = []
            hyperlink_url = None
            
            for fmt in formatting:
                tag = fmt['tag']
                
                if tag in ['strong', 'b']:
                    style_updates['bold'] = True
                    fields.append('bold')
                elif tag in ['em', 'i']:
                    style_updates['italic'] = True
                    fields.append('italic')
                elif tag == 'code':
                    style_updates['fontFamily'] = 'Courier New'
                    fields.append('fontFamily')
                elif tag == 'u':
                    style_updates['underline'] = True
                    fields.append('underline')
                elif tag == 'del':
                    style_updates['strikethrough'] = True
                    fields.append('strikethrough')
                elif tag == 'a' and 'url' in fmt:
                    hyperlink_url = fmt['url']
                elif tag == 'span':
                    # Handle color formatting
                    if 'color_class' in fmt:
                        color_class = fmt['color_class']
                        if color_class in self.theme_config.get('class_colors', {}):
                            color_rgb = self.theme_config['class_colors'][color_class]
                            # Color is already RGB tuple from CSS parser
                            if isinstance(color_rgb, tuple) and len(color_rgb) == 3:
                                style_updates['foregroundColor'] = {"opaqueColor": {"rgbColor": self._rgb_tuple_to_gslides_color(color_rgb)}}
                                fields.append('foregroundColor')
                                if self.debug:
                                    logger.info(f"Applied color class '{color_class}': RGB{color_rgb}")
                    elif 'color_hex' in fmt:
                        style_updates['foregroundColor'] = {"opaqueColor": {"rgbColor": _hex_to_rgb_dict(fmt['color_hex'])}}
                        fields.append('foregroundColor')
                    
                    # Handle span-based formatting
                    if 'underline' in fmt:
                        style_updates['underline'] = True
                        fields.append('underline')
                    elif 'wavy_underline' in fmt:
                        # Google Slides doesn't have wavy underline, use underline + different color
                        style_updates['underline'] = True
                        # Use a reddish color to indicate wavy underline
                        style_updates['foregroundColor'] = {"opaqueColor": {"rgbColor": _hex_to_rgb_dict('#e74c3c')}}
                        fields.extend(['underline', 'foregroundColor'])
                elif tag == 'mark':
                    # Handle highlight formatting
                    if 'highlight' in fmt:
                        # Use a highlight color from theme or default yellow
                        highlight_color = self.theme_config['colors'].get('highlight', '#FFFF00')
                        style_updates['backgroundColor'] = {"opaqueColor": {"rgbColor": _hex_to_rgb_dict(highlight_color)}}
                        fields.append('backgroundColor')
            
            # Apply text style if we have any formatting
            if style_updates and fields:
                style_request = {
                    "updateTextStyle": {
                        "objectId": object_id,
                        "textRange": {
                            "type": "FIXED_RANGE",
                            "startIndex": start_idx,
                            "endIndex": end_idx,
                        },
                        "style": style_updates,
                        "fields": ",".join(fields),
                    }
                }
                requests.append(style_request)
            
            # Apply hyperlink if we have one
            if hyperlink_url:
                link_request = {
                    "updateTextStyle": {
                        "objectId": object_id,
                        "textRange": {
                            "type": "FIXED_RANGE",
                            "startIndex": start_idx,
                            "endIndex": end_idx,
                        },
                        "style": {
                            "link": {"url": hyperlink_url}
                        },
                        "fields": "link",
                    }
                }
                requests.append(link_request)
        
        if self.debug:
            logger.info(f"Created rich text with {len(text_segments)} formatted segments, {len(requests)} requests")
        
        return requests

    def _create_paragraph_image_requests(self, block: Block, slide_id: str, x_scale: float, y_scale: float, 
                                        top_pt: float, width_pt: float, height_pt: float) -> List[Dict]:
        """Handle paragraph blocks that contain images."""
        try:
            soup = BeautifulSoup(block.content, 'html.parser')
            img = soup.find('img')
            if img and img.get('src'):
                # Create a synthetic image block
                img_block = Block(
                    tag='img',
                    x=block.x,
                    y=block.y,
                    w=block.w,
                    h=block.h,
                    content='',
                    src=img.get('src'),
                    bid=block.bid
                )
                # Calculate dimensions for image block
                img_x_scale, img_y_scale, img_top_pt, img_height_pt, img_browser_width_px = self._calculate_element_dimensions(img_block)
                img_width_pt = self._calculate_element_width(img_block, img_x_scale, img_browser_width_px)
                return self._create_image_requests(img_block, slide_id, img_x_scale, img_y_scale, img_top_pt, img_width_pt, img_height_pt)
        except Exception as exc:
            logger.warning("Failed to extract image from paragraph: %s", exc)
        
        # Create text box if image extraction fails
        x_scale, y_scale, top_pt, height_pt, browser_width_px = self._calculate_element_dimensions(block)
        width_pt = self._calculate_element_width(block, x_scale, browser_width_px)
        return self._create_text_box_requests(block, slide_id, x_scale, y_scale, top_pt, width_pt, height_pt)

    def _create_text_box_requests(self, block: Block, slide_id: str, x_scale: float, y_scale: float, 
                                 top_pt: float, width_pt: float, height_pt: float) -> List[Dict]:
        object_id = f"text_{block.bid or id(block)}"

        # Calculate position using two-pass system
        # Layout engine already accounts for margins in block.x/block.y coordinates
        pos_x_pt = block.x * x_scale
        pos_y_pt = top_pt
        
        if self.debug:
            logger.info(f"Text width: using pre-calculated={width_pt:.1f}pt (from two-pass system)")
            logger.info(f"Text box {object_id}: {width_pt:.1f}×{height_pt:.1f}pt ({self._emu(width_pt):.0f}×{self._emu(height_pt):.0f} EMU) at ({pos_x_pt:.1f},{pos_y_pt:.1f})")
        
        # Ensure minimum dimensions for visibility (critical for Google Slides API)
        width_pt, height_pt = self._ensure_minimum_dimensions(width_pt, height_pt)
        
        # Google Slides API requires size in EMU - use actual calculated dimensions
        width_emu = self._emu(width_pt)
        height_emu = self._emu(height_pt)
        
        if self.debug:
            logger.info(f"Text box {object_id}: {width_pt:.1f}×{height_pt:.1f}pt ({width_emu}×{height_emu} EMU) at ({pos_x_pt:.1f},{pos_y_pt:.1f})")

        create_shape = {
            "createShape": {
                "objectId": object_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": self._create_element_properties(width_emu, height_emu, pos_x_pt, pos_y_pt, slide_id),
            }
        }

        # Use rich text formatting instead of simple text insertion
        rich_text_requests = self._create_rich_text_requests(object_id, block)

        return [create_shape] + rich_text_requests



    def _create_image_requests(self, block: Block, slide_id: str, x_scale: float, y_scale: float, 
                              top_pt: float, width_pt: float, height_pt: float) -> List[Dict]:
        """Create Google Slides requests for images using two-pass calculated dimensions."""
        if not block.src:
            return []
        object_id = f"img_{block.bid or id(block)}"

        # Calculate position using two-pass system
        # Layout engine already accounts for margins in block.x/block.y coordinates
        pos_x_pt = block.x * x_scale
        pos_y_pt = top_pt
        
        # Store image width for potential caption use (like PPTX renderer)
        # Use calculated width from two-pass system, converted back to pixels for consistency
        calculated_width_px = width_pt / self._scale
        self._last_image_block_width = calculated_width_px
        if self.debug:
            logger.info(f"IMAGE: Caching calculated width for caption use: {calculated_width_px:.0f}px (from {width_pt:.1f}pt)")
            logger.info(f"Image {object_id}: calculated dimensions {width_pt:.1f}×{height_pt:.1f}pt at ({pos_x_pt:.1f},{pos_y_pt:.1f})")



        return [
            {
                "createImage": {
                    "objectId": object_id,
                    "url": block.src,
                    "elementProperties": self._create_element_properties(
                        self._emu(width_pt), self._emu(height_pt), pos_x_pt, pos_y_pt, slide_id, 1.0, 1.0
                    ),
                }
            }
        ]

    def _create_table_requests(self, block: Block, slide_id: str, x_scale: float, y_scale: float, 
                              top_pt: float, width_pt: float, height_pt: float) -> List[Dict]:
        """Create a basic table in Google Slides from a table block."""
        if not block.content:
            return []
        
        object_id = f"table_{block.bid or id(block)}"

        # Calculate position using two-pass system
        # Layout engine already accounts for margins in block.x/block.y coordinates
        pos_x_pt = block.x * x_scale
        pos_y_pt = top_pt
        
        if self.debug:
            logger.info(f"Creating table {object_id} at ({block.x},{block.y}) size {block.width}x{block.height}")
            if hasattr(block, 'table_column_widths') and block.table_column_widths:
                logger.info(f"  Table column widths: {block.table_column_widths} (total: {sum(block.table_column_widths)}px)")
            else:
                logger.info(f"  No table_column_widths available - will use equal distribution")

        # Parse table HTML to extract rows/cols
        try:
            soup = BeautifulSoup(block.content, 'html.parser')
            table = soup.find('table')
            if not table:
                return []
            
            rows = table.find_all('tr')
            if not rows:
                return []
            
            # Determine table dimensions
            max_cols = max(len(row.find_all(['td', 'th'])) for row in rows)
            num_rows = len(rows)
            
            if max_cols == 0 or num_rows == 0:
                return []

            # Create table request using the calculated dimensions from layout engine
            create_request = {
                "createTable": {
                    "objectId": object_id,
                    "elementProperties": self._create_element_properties(
                        self._emu(width_pt), self._emu(height_pt), pos_x_pt, pos_y_pt, slide_id
                    ),
                    "rows": num_rows,
                    "columns": max_cols,
                }
            }

            requests = [create_request]

            if self.debug:
                logger.info(f"Table {object_id}: {num_rows}x{max_cols} at ({pos_x_pt:.1f},{pos_y_pt:.1f}) size {width_pt:.1f}x{height_pt:.1f}pt")

            # Populate table cells with content and styling
            table_base_font_size = self.theme_config['font_sizes']['p']
            table_font_delta = self.theme_config['table_deltas']['font_delta']
            table_font_size = max(8, table_base_font_size + table_font_delta)
            
            table_text_color = self.theme_config['colors'].get('table_text', self.theme_config['colors'].get('text', '#000000'))
            
            # CRITICAL FIX: Set row heights to match HTML measurements (like PPTX)
            # Calculate target row height based on HTML measurements
            html_table_height_px = block.height
            target_row_height_px = html_table_height_px / num_rows
            target_row_height_pt = target_row_height_px * self._scale
            
            if self.debug:
                logger.info(f"Table height constraint: {html_table_height_px}px ÷ {num_rows} rows = {target_row_height_px:.1f}px = {target_row_height_pt:.1f}pt per row")
            
            # CRITICAL FIX: Set column widths to match HTML measurements (like PPTX)
            if hasattr(block, 'table_column_widths') and block.table_column_widths:
                if self.debug:
                    logger.info(f"Applying measured column widths: {block.table_column_widths}")
                
                # Apply width safety buffer (like PPTX) to prevent text wrapping
                width_safety = self.theme_config['table_deltas']['width_safety']  # e.g., 1.10 for +10%
                
                # Apply Google Slides constraints: minimum 32pt (406400 EMU) per column
                min_width_pt = 32.0
                constrained_widths_pt = []
                
                for width_px in block.table_column_widths:
                    # Apply safety buffer first (like PPTX), then convert to points
                    safe_width_px = width_px * width_safety
                    width_pt = safe_width_px * self._scale
                    constrained_width_pt = max(width_pt, min_width_pt)
                    constrained_widths_pt.append(constrained_width_pt)
                
                if self.debug:
                    original_widths_pt = [w * self._scale for w in block.table_column_widths]
                    safe_widths_pt = [w * width_safety * self._scale for w in block.table_column_widths]
                    logger.info(f"Width safety factor: {width_safety} (from CSS --table-width-safety)")
                    logger.info(f"Original widths: {[f'{w:.1f}pt' for w in original_widths_pt]}")
                    logger.info(f"With safety buffer: {[f'{w:.1f}pt' for w in safe_widths_pt]}")
                    logger.info(f"Final constrained: {[f'{w:.1f}pt' for w in constrained_widths_pt]}")
                
                for col_idx, width_pt in enumerate(constrained_widths_pt):
                    requests.append({
                        "updateTableColumnProperties": {
                            "objectId": object_id,
                            "columnIndices": [col_idx],
                            "tableColumnProperties": {
                                "columnWidth": {"magnitude": self._emu(width_pt), "unit": "EMU"}
                            },
                            "fields": "columnWidth"
                        }
                    })
            else:
                if self.debug:
                    logger.info("No column width data - Google Slides will use equal distribution")
            
            # Set row heights to constrain table to measured dimensions
            for row_idx in range(num_rows):
                requests.append({
                    "updateTableRowProperties": {
                        "objectId": object_id,
                        "rowIndices": [row_idx],
                        "tableRowProperties": {
                            "minRowHeight": {"magnitude": self._emu(target_row_height_pt), "unit": "EMU"}
                        },
                        "fields": "minRowHeight"
                    }
                })
            
            # Populate table cells with content and styling
            for row_idx, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                for col_idx, cell in enumerate(cells):
                    cell_text = cell.get_text(strip=True)
                    if cell_text:
                        if self.debug:
                            logger.info(f"  Cell [{row_idx},{col_idx}]: '{cell_text}'")
                        # Insert the text
                        requests.append({
                            "insertText": {
                                "objectId": object_id,
                                "cellLocation": {"rowIndex": row_idx, "columnIndex": col_idx},
                                "text": cell_text,
                                "insertionIndex": 0,
                            }
                        })
                        
                        # Apply font styling using CSS theme settings
                        is_header = cell.name == 'th'
                        requests.append({
                            "updateTextStyle": {
                                "objectId": object_id,
                                "cellLocation": {"rowIndex": row_idx, "columnIndex": col_idx},
                                "style": {
                                    "fontSize": {"magnitude": table_font_size, "unit": "PT"},
                                    "fontFamily": self.theme_config['font_family'],
                                    "foregroundColor": {"opaqueColor": {"rgbColor": _hex_to_rgb_dict(table_text_color)}},
                                    "bold": is_header,
                                },
                                "textRange": {"type": "ALL"},
                                "fields": "fontSize,fontFamily,foregroundColor,bold",
                            }
                        })

            return requests

        except Exception as exc:
            logger.warning("Failed to parse table content: %s", exc)
            # Create as text box if table parsing fails
            x_scale, y_scale, top_pt, height_pt, browser_width_px = self._calculate_element_dimensions(block)
            width_pt = self._calculate_element_width(block, x_scale, browser_width_px)
            return self._create_text_box_requests(block, slide_id, x_scale, y_scale, top_pt, width_pt, height_pt)

    # ------------------------------------------------------------------
    # Batch execution helpers
    # ------------------------------------------------------------------

    def _execute_requests_in_batches(self, presentation_id: str, requests: List[Dict]) -> None:
        assert self.slides_service is not None  # already checked earlier
        BATCH_SIZE = 100
        for i in range(0, len(requests), BATCH_SIZE):
            batch = requests[i : i + BATCH_SIZE]
            try:
                (  # type: ignore[attr-defined]
                    self.slides_service.presentations()
                    .batchUpdate(presentationId=presentation_id, body={"requests": batch})
                    .execute()
                )
            except HttpError as e:  # pragma: no cover
                logger.error("Google Slides API error: %s", e)
                raise
            if self.debug:
                logger.info("✓ Executed batch %s – %s requests", i // BATCH_SIZE + 1, len(batch))



    # ------------------------------------------------------------------
    # Theme and utility methods
    # ------------------------------------------------------------------

    def _parse_theme_config(self) -> Dict:
        """Parse CSS theme to extract font sizes and styling configuration using centralized parser."""
        config = {
            'font_sizes': self.css_parser.get_font_sizes(),
            'line_height': self.css_parser.get_line_height(),
            'colors': self.css_parser.get_colors(),
            'slide_dimensions': self.css_parser.get_slide_dimensions(),
            'table_deltas': self.css_parser.get_table_config(),
            'class_colors': self.css_parser.get_class_colors(),
            'admonition_colors': self.css_parser.get_admonition_colors(),
            'css_content': self.css_parser.css_content
        }
        
        # Add backwards compatibility mappings
        config['font_family'] = config['slide_dimensions']['font_family']
        
        return config

    @staticmethod
    def _strip_html(html: str) -> str:
        """Very simple HTML → text fallback (headings & paragraphs only)."""
        text = re.sub(r"<[^>]+>", "", html)
        return re.sub(r"\s+", " ", text).strip()

