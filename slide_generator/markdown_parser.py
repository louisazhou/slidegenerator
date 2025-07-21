"""
Enhanced markdown parser with support for multiple page break formats.
"""
from typing import List, Optional
from markdown_it import MarkdownIt
import os
from pathlib import Path

from .paths import resolve_asset
from .models import SpeakerNote

class MarkdownParser:
    """
    Enhanced markdown parser with page break support using markdown-it-py.
    """
    
    def __init__(self, base_dir: Path, extract_speaker_notes: bool = True):
        """
        Initialize the markdown parser.
        
        Args:
            base_dir: Base directory for resolving relative image paths. Required.
            extract_speaker_notes: Whether to extract speaker notes during processing
        """
        self.base_dir = base_dir
        self.extract_speaker_notes = extract_speaker_notes
        # Storage for extracted speaker notes
        self.speaker_notes: List[SpeakerNote] = []
        
        # markdown-it-py doesn't use the same extension system as the old markdown library
        # but it has most features built-in by default
        self.markdown_processor = MarkdownIt('commonmark', {
            'html': True,          # Enable HTML tags
            'linkify': True,       # Auto-convert URLs to links
            'typographer': True,   # Enable smart quotes and other typographic replacements
        })
        
        # Enable additional features
        self.markdown_processor.enable(['table', 'strikethrough'])
        
        # ---------------------------------------------------------
        # PLUGIN ECOSYSTEM
        # ---------------------------------------------------------
        # 1) attrs_plugin      : `{.class #id key=val}` inline/block attributes (already relied on)
        # 2) container_plugin  : `:::note`, `:::columns`, `:::column`, etc.  
        # 3) dollarmath_plugin : `$...$` / `$$...$$` math support inside slides.
        # 4) front_matter_plugin: YAML front-matter (`---`) for per-deck config that can override
        #                       CSS variables (e.g. slide width/height) – no effect yet but parsed.
        # 5) tasklists_plugin  : GitHub style `- [x] Done` checkboxes (renders <input> elements).
        # 6) deflist_plugin    : Definition lists (`Term\n: definition`). Gives <dl>/<dt>/<dd> HTML.
        #
        # NOTE  The renderer / layout engine treats these as normal block/inline HTML so no
        #       additional Python changes are required right now. Enabling them early guarantees
        #       markdown authored with these syntaxes will not break the pipeline.

        from mdit_py_plugins.attrs import attrs_plugin
        from mdit_py_plugins.container import container_plugin
        from mdit_py_plugins.dollarmath import dollarmath_plugin
        from mdit_py_plugins.front_matter import front_matter_plugin
        from mdit_py_plugins.tasklists import tasklists_plugin
        from mdit_py_plugins.deflist import deflist_plugin
        from mdit_py_plugins.admon import admon_plugin  # ✅ NEW – admonition support

        # ------------------------------------------------------------------
        # Plugin registration chain
        # ------------------------------------------------------------------
        # NOTE on columns/column:
        # We experimented with `container_plugin('columns')` & `('column')` to
        # replace our hand-rolled :::columns/:::column regex logic.  It worked
        # syntactically but still required a lot of post-processing (flex styles,
        # width parsing, bid stamping, image marking).  The net result was more
        # code than the current custom `convert_columns()` helper, so we're
        # deferring the switch.  The two lines are left commented so the intent
        # is visible when we revisit.
        #
        # NOTE on tasklists/deflist:
        # Similar story: enabling them renders correct HTML, but our list-merge
        # pagination step would need extra logic to keep checkbox inputs / <dl>
        # pairs intact.  We'll re-enable once list handling is refactored.

        self.markdown_processor = (
            self.markdown_processor
                .use(attrs_plugin)                     # {.class #id key=val}
                # .use(container_plugin, 'columns')   # see note above
                # .use(container_plugin, 'column')    # see note above
                .use(container_plugin, 'note')         # admonition / call-out boxes
                .use(dollarmath_plugin,
                     allow_space=False,                # Don't allow spaces after/before $
                     allow_digits=False,               # Don't allow digits before/after $
                     double_inline=False               # Don't allow $$ in inline context
                )                                     # inline & block math
                .use(front_matter_plugin)              # YAML front-matter parsing
                # .use(tasklists_plugin)              # see note above
                # .use(deflist_plugin)                # see note above
                .use(admon_plugin)                     # ✅ enable admonition blocks
        )
    
    def parse(self, markdown_text: str) -> str:
        """
        Parse markdown text to HTML.
        
        Args:
            markdown_text: Raw markdown content
            
        Returns:
            HTML string
        """
        # Preprocess custom syntax before markdown processing
        processed_text = self._preprocess_custom_syntax(markdown_text)
        
        # Convert markdown to HTML
        html = self.markdown_processor.render(processed_text)

        # ------------------------------------------------------------------
        # POST-PROCESSING – stamp admonition boxes so downstream HTML / PPTX can
        # recognise them quickly (bonus: Puppeteer preview styling hook).
        # ------------------------------------------------------------------
        import re

        def _add_data_attr(match):
            tag = match.group(0)
            # Skip if attribute already present (double-processing safeguard)
            if 'data-box-type="admonition"' in tag:
                return tag
            return tag[:-1] + ' data-box-type="admonition">'

        html = re.sub(r'<div[^>]*class="[^"]*\badmonition\b[^"]*"[^>]*>', _add_data_attr, html)

        return html
    
    def _validate_fenced_blocks(self, markdown_text: str) -> None:
        """Ensure triple-colon fenced blocks are properly opened / closed.

        The rules enforced are minimal but catch the most common authoring
        mistakes so that the rest of the pipeline can rely on valid HTML:

        1. Every opening ":::xyz" has a matching closing ":::".
        2. ":::column" must be nested directly inside a ":::columns" block.
        3. A ":::fit-slide" block may *contain* columns but cannot itself be
           placed *inside* any column.*

        A ``ValueError`` with a line number is raised on violation so that the
        caller (tests or CLI) can surface a helpful error message to the user.
        """
        from typing import List

        stack: List[str] = []  # keeps the sequence of open blocks

        for lineno, raw_line in enumerate(markdown_text.splitlines(), 1):
            line = raw_line.strip()

            if not line.startswith(":::"):
                continue

            # -------------------------
            # Closing fence
            # -------------------------
            if line == ":::":
                if not stack:
                    raise ValueError(f"Unmatched closing ':::' at line {lineno}")
                stack.pop()
                continue

            # -------------------------
            # Opening fences
            # -------------------------
            if line.startswith(":::columns"):
                stack.append("columns")
            elif line.startswith(":::column"):
                if not stack or stack[-1] != "columns":
                    raise ValueError(f"':::column' outside ':::columns' (line {lineno})")
                stack.append("column")
            elif line.startswith(":::fit-slide"):
                if any(b in ("columns", "column") for b in stack):
                    raise ValueError(f"':::fit-slide' nested inside column block (line {lineno})")
                stack.append("fit-slide")
            else:
                # Generic custom fenced block – treat like other for balance check
                stack.append("other")

        # If we exit with still-open blocks, report the last one for context
        if stack:
            raise ValueError("Missing closing ':::' for fenced block opened earlier")
    
    def _preprocess_custom_syntax(self, markdown_text: str) -> str:
        """
        Preprocess custom syntax that isn't supported by markdown-it-py.
        
        Args:
            markdown_text: Raw markdown content
            
        Returns:
            Processed markdown with custom syntax converted
        """
        # Validate fenced-block structure *before* we start mutating the text
        self._validate_fenced_blocks(markdown_text)

        import re
        
        # Extract speaker notes FIRST, before any other processing
        # Only extract notes if this is NOT individual slide processing
        if self.extract_speaker_notes:
            processed = self._extract_and_store_speaker_notes(markdown_text)
        else:
            processed = markdown_text
        
        # Convert ==highlight== to HTML <mark> tags
        # This needs to be done before markdown processing to avoid conflicts
        processed = re.sub(r'==(.*?)==', r'<mark>\1</mark>', processed)
        
        # Convert ++underline++ (single) and ^^wavy^^ underline first
        processed = re.sub(r'\+\+(.*?)\+\+', r'<u>\1</u>', processed)
        processed = re.sub(r'\^\^(.*?)\^\^', r'<u class="wavy">\1</u>', processed)

        # Convert ~~strikethrough~~ to <del>
        processed = re.sub(r'~~(.*?)~~', r'<del>\1</del>', processed)
        
        # ------------------------------------------------------------------
        # Fallback inline attrs conversion
        # ------------------------------------------------------------------
        # markdown-it-attrs presently does **not** transform inline `[text]{.red}`
        # when running under the CommonMark preset (see GH issue #70).  Until the
        # plugin supports it natively we convert the syntax to a `<span>` so the
        # downstream HTML carries the class and our renderer can map it.
        
        # Handle markdown-it-attrs syntax: [text]{.class1 .class2 attr=value}
        def convert_attrs(match):
            text = match.group(1)
            attrs_content = match.group(2).strip()
            
            # Parse the attributes content
            classes = []
            attributes = []
            
            # Split by spaces but be careful with quoted values
            import shlex
            try:
                tokens = shlex.split(attrs_content.replace('=', ' = '))
            except:
                # Fallback to simple split if shlex fails
                tokens = attrs_content.split()
            
            i = 0
            while i < len(tokens):
                token = tokens[i]
                if token.startswith('.'):
                    # CSS class
                    classes.append(token[1:])
                elif token.startswith('#'):
                    # ID attribute
                    attributes.append(f'id="{token[1:]}"')
                elif '=' in token or (i + 2 < len(tokens) and tokens[i + 1] == '='):
                    # Attribute with value
                    if '=' in token:
                        attr_name, attr_value = token.split('=', 1)
                        clean_value = attr_value.strip('\'"')
                        attributes.append(f'{attr_name}="{clean_value}"')
                    else:
                        attr_name = token
                        attr_value = tokens[i + 2] if i + 2 < len(tokens) else ''
                        clean_value = attr_value.strip('\'"')
                        attributes.append(f'{attr_name}="{clean_value}"')
                        i += 2  # Skip the '=' and value
                i += 1
            
            # Check for special numeric formatting classes
            formatted_text = text
            numeric_classes = {'dollar', 'percent', 'order'}
            
            if any(cls in classes for cls in numeric_classes):
                try:
                    # Try to parse as number for formatting
                    if 'dollar' in classes:
                        # Format as currency: 1234567 → $1.23M
                        value = float(formatted_text.replace(',', '').replace('$', ''))
                        formatted_text = self._format_currency(value)
                    elif 'percent' in classes:
                        # Format as percentage: 0.15 → 15.0% or 15 → 15.0%
                        value = float(formatted_text.replace('%', ''))
                        # Auto-detect if it's decimal (0.15) or whole number (15)
                        if value <= 1.0 and '.' in formatted_text:
                            formatted_text = f"{value * 100:.1f}%"
                        else:
                            formatted_text = f"{value:.1f}%"
                    elif 'order' in classes:
                        # Format as ordinal: 1 → 1st, 2 → 2nd, etc.
                        value = int(float(formatted_text))
                        formatted_text = self._format_ordinal(value)
                except (ValueError, TypeError):
                    # If parsing fails, keep original text
                    pass
            
            # Build the span tag
            span_attrs = []
            if classes:
                span_attrs.append(f'class="{" ".join(classes)}"')
            span_attrs.extend(attributes)
            
            attr_str = ' '.join(span_attrs)
            return f'<span {attr_str}>{formatted_text}</span>' if attr_str else f'<span>{formatted_text}</span>'
        
        # Apply the conversion
        processed = re.sub(r'\[([^\]]+)\]\{([^}]+)\}', convert_attrs, processed)

        # Handle Pandoc-style multi-column blocks
        def convert_columns(text: str) -> str:
            lines = text.split('\n')
            out_lines = []
            i = 0
            while i < len(lines):
                if lines[i].strip().startswith(':::columns'):
                    i += 1
                    columns = []
                    current = []
                    current_width = 'default'
                    in_column = False
                    
                    while i < len(lines):
                        line = lines[i].strip()
                        
                        if line.startswith(':::column'):
                            # Detect optional width attribute – supports legacy ":::column{60%}" or
                            # attrs-style ":::column {width=60%}"
                            import re as _re
                            width_match = _re.match(r':::column\s+\{([^}]+)\}', line)
                            if width_match:
                                pending_width = width_match.group(1).strip()
                            else:
                                pending_width = "default"

                            # Start new column, flush current if exists
                            if current:
                                columns.append((current_width if 'current_width' in locals() else 'default', '\n'.join(current).strip()))
                                current = []
                            else:
                                # Placeholder to capture width even if column starts empty for now
                                current = []
                            current_width = pending_width  # Track width for this column's lines
                            in_column = True
                            i += 1
                            continue
                        elif line == ':::' and in_column:
                            # End current column
                            if current:
                                columns.append((current_width, '\n'.join(current).strip()))
                                current = []
                            in_column = False
                            i += 1
                            continue
                        elif line == ':::' and not in_column:
                            # End entire columns block
                            i += 1
                            break
                        
                        # Regular content line
                        current.append(lines[i])
                        i += 1
                    
                    # Build HTML - filter out empty columns and parse markdown content
                    col_html = []
                    for width_token, c in columns:
                        if c.strip():  # Only add non-empty columns
                            # Reuse main markdown_processor so all plugins (e.g. admonition)
                            # are active. We still need to run preprocessing beforehand.
                            processed_column = self._preprocess_custom_syntax(c.strip())
                            column_html = self.markdown_processor.render(processed_column)
                            
                            # Extract just the value part for CSS matching
                            if '=' in width_token:
                                css_value = width_token.split('=')[1]  # "width=auto" -> "auto"
                            else:
                                css_value = width_token
                                
                            width_attr = f'data-column-width="{css_value}"'  # Use clean value
                            style_attr = ''
                            if css_value.endswith('%') or css_value == 'auto' or css_value == 'default':
                                if css_value == 'auto':
                                    style_attr = 'style="flex:0 0 auto;"'
                                elif css_value == 'default':
                                    style_attr = 'style="flex:1 1 0;"'
                                else:  # percentage
                                    style_attr = f'style="flex:0 0 {css_value};"'
                            col_html.append(f'<div class="column" {width_attr} {style_attr}>\n{column_html}</div>')
                    out_lines.append('<div class="columns">')
                    out_lines.extend(col_html)
                    out_lines.append('</div>')
                    # i is already positioned after the closing :::
                else:
                    out_lines.append(lines[i])
                    i += 1
            return '\n'.join(out_lines)

        processed = convert_columns(processed)
        
        # Handle image scaling syntax ![alt|0.8x](path) and new caption syntax ![Caption: text|0.8x](path)
        def replace_image(match):
            alt_and_maybe_caption = match.group(1)
            scale = match.group(2)
            axis = match.group(3)
            src = match.group(4)

            # Parse caption and alt text from the alt field
            caption = ""
            alt = alt_and_maybe_caption
            
            # Check if alt starts with "Caption: "
            if alt_and_maybe_caption.startswith("Caption: "):
                # Extract caption and remove it from alt text
                caption_start = len("Caption: ")
                if '|' in alt_and_maybe_caption[caption_start:]:
                    caption_part, rest = alt_and_maybe_caption[caption_start:].split('|', 1)
                    caption = caption_part.strip()
                    alt = rest.strip()  # The rest becomes the alt text
                else:
                    caption = alt_and_maybe_caption[caption_start:].strip()
                    alt = ""  # No alt text, just caption
            else:
                # No caption, the whole thing is alt text
                alt = alt_and_maybe_caption
                caption = ""

            # Resolve asset once via helper (copies into tmp_dir for browser)
            browser_src, abs_path = resolve_asset(
                src,
                base_dir=self.base_dir,
            )

            attrs = [f'data-filepath="{abs_path}"']
            if scale and axis:
                # Store scaling information for the layout engine to process
                # The layout engine will calculate exact dimensions using theme CSS values
                attrs.append(f'data-scale-{axis.lower()}="{scale}"')
                attrs.append(f'data-scale-type="{axis.lower()}"')
            
            # Add caption data if present
            if caption:
                attrs.append(f'data-caption="{caption}"')

            attr_str = ' '.join(attrs)
            return f'<img src="{browser_src}" alt="{alt}" {attr_str} />'

        # First process images to add scaling attributes and caption data
        processed = re.sub(r'!\[([^\]|]+)(?:\|([0-9.]+)([xy]))?\]\(([^)\s]+)\)', replace_image, processed)
        
        # After processing columns, mark images that are within column divs
        def mark_column_images(text: str) -> str:
            """Add data-in-column attribute to images within column divs"""
            import re
            
            # Find all column divs and mark images within them
            def process_column_div(match):
                opening_tag = match.group(1)
                column_content = match.group(2)
                # Add data-in-column="true" to all images within this column
                marked_content = re.sub(
                    r'(<img[^>]*?)(/?>)',
                    r'\1 data-in-column="true"\2',
                    column_content
                )
                return f'{opening_tag}{marked_content}</div>'
            
            # Process all column divs
            result = re.sub(
                r'(<div[^>]*class="[^\"]*\bcolumn\b[^\"]*"[^>]*>)(.*?)</div>',
                process_column_div,
                text,
                flags=re.DOTALL
            )
            
            return result
        
        processed = mark_column_images(processed)
        
        return processed
    
    def _format_currency(self, value: float) -> str:
        """Format number as currency: 1234567 → $1.23M"""
        sign = "-" if value < 0 else ""
        abs_value = abs(value)
        
        for div, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
            if abs_value >= div:
                return f"{sign}${abs_value/div:,.2f}{unit}"
        return f"{sign}${abs_value:,.0f}"
    
    def _format_ordinal(self, n: int) -> str:
        """Format number as ordinal: 1 → 1st, 2 → 2nd, etc."""
        suffix = 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
        return f"{n}{suffix}"
    
    def parse_with_page_breaks(self, markdown_text: str) -> List[str]:
        """
        Parse markdown text and split on page breaks.
        
        Supported page break formats:
        - Horizontal rule: ---
        - HTML comment: <!-- slide -->
        - Slide directive: <!-- NewSlide: -->
        - Explicit directive: [slide]
        
        Args:
            markdown_text: Raw markdown content
            
        Returns:
            List of HTML strings, one per slide
        """
        # Handle empty or whitespace-only content
        if not markdown_text or not markdown_text.strip():
            return []
        
        # Process page breaks in markdown
        slides_md = []
        current_slide = []
        
        lines = markdown_text.strip().split('\n')
        
        for line in lines:
            line_stripped = line.strip()
            
            # Check for various page break formats
            is_page_break = False
            
            # 1. Horizontal rule (must be exactly ---)
            if line_stripped == '---':
                is_page_break = True
            
            # 2. HTML slide comments (various formats)
            elif ('<!-- slide -->' in line_stripped or 
                  '<!-- Slide -->' in line_stripped or 
                  '<!-- SLIDE -->' in line_stripped or
                  '<!--slide-->' in line_stripped):
                is_page_break = True
            
            # 3. NewSlide directive
            elif ('<!-- NewSlide:' in line_stripped or 
                  '<!--NewSlide:' in line_stripped):
                is_page_break = True
            
            # 4. Explicit [slide] directive
            elif line_stripped == '[slide]':
                is_page_break = True
            
            # 5. Three or more asterisks or underscores (alternate horizontal rules)
            elif (line_stripped.startswith('***') and 
                  all(c == '*' for c in line_stripped)):
                is_page_break = True
            elif (line_stripped.startswith('___') and 
                  all(c == '_' for c in line_stripped)):
                is_page_break = True
            
            if is_page_break:
                # Add current slide content if it exists
                if current_slide:
                    slides_md.append('\n'.join(current_slide))
                # Start a new slide after a page break
                current_slide = []
            else:
                current_slide.append(line)
                
        # Add the last slide if it has content
        if current_slide:
            slides_md.append('\n'.join(current_slide))
        
        # If no page breaks were found, treat the whole content as one slide
        if not slides_md:
            slides_md = [markdown_text]
        
        # Convert each slide to HTML
        html_slides = []
        for slide_md in slides_md:
            if not slide_md.strip():
                # Skip completely empty slides
                continue
            
            html = self.parse(slide_md)
            html_slides.append(html)
        
        return html_slides
    
    def count_page_breaks(self, markdown_text: str) -> int:
        """
        Count the number of page breaks in markdown text.
        
        Args:
            markdown_text: Raw markdown content
            
        Returns:
            Number of page breaks found
        """
        if not markdown_text or not markdown_text.strip():
            return 0
        
        page_breaks = 0
        lines = markdown_text.strip().split('\n')
        
        for line in lines:
            line_stripped = line.strip()
            
            # Check for various page break formats (same logic as parse_with_page_breaks)
            if (line_stripped == '---' or
                '<!-- slide -->' in line_stripped or
                '<!-- Slide -->' in line_stripped or
                '<!-- SLIDE -->' in line_stripped or
                '<!--slide-->' in line_stripped or
                '<!-- NewSlide:' in line_stripped or
                '<!--NewSlide:' in line_stripped or
                line_stripped == '[slide]' or
                (line_stripped.startswith('***') and all(c == '*' for c in line_stripped)) or
                (line_stripped.startswith('___') and all(c == '_' for c in line_stripped))):
                page_breaks += 1
        
        return page_breaks
    
    def estimate_slide_count(self, markdown_text: str) -> int:
        """
        Estimate the number of slides that will be generated.
        
        Args:
            markdown_text: Raw markdown content
            
        Returns:
            Estimated number of slides
        """
        if not markdown_text or not markdown_text.strip():
            return 0
        
        page_breaks = self.count_page_breaks(markdown_text)
        
        # If there are page breaks, slide count is page breaks + 1
        # If no page breaks, it's just 1 slide
        return page_breaks + 1

    def _extract_and_store_speaker_notes(self, markdown_text: str) -> str:
        """
        Extract speaker notes from markdown and store them, returning clean markdown.
        
        Notes have the syntax: <!-- NOTE: content --> (can span multiple lines)
        
        Args:
            markdown_text: Original markdown content
            
        Returns:
            Markdown with speaker notes removed
        """
        import re
        
        # Don't clear existing notes - accumulate them across multiple parse calls
        # self.speaker_notes.clear()
        
        # First, find all speaker notes (including multi-line ones) using a global regex
        note_pattern = r'<!--\s*NOTE:\s*(.*?)\s*-->'
        note_matches = list(re.finditer(note_pattern, markdown_text, re.IGNORECASE | re.DOTALL))
        
        # Process notes in reverse order to avoid position shifting during removal
        clean_text = markdown_text
        for match in reversed(note_matches):
            note_content = match.group(1).strip()
            
            # Process the note content through the same markdown pipeline as main content
            processed_note_content = self._process_note_content(note_content)
            
            # Find the line number where this note starts
            text_before_note = markdown_text[:match.start()]
            note_line = text_before_note.count('\n') + 1
            
            # Collect preceding content for page association (last 5 lines before the note)
            lines_before = text_before_note.split('\n')
            preceding_content = '\n'.join(lines_before[-5:]) if len(lines_before) >= 5 else '\n'.join(lines_before)
            
            # Store the processed note
            speaker_note = SpeakerNote(
                content=processed_note_content,
                original_line=note_line,
                preceding_content=preceding_content
            )
            self.speaker_notes.append(speaker_note)
            
            # Remove the note from the markdown
            clean_text = clean_text[:match.start()] + clean_text[match.end():]
        
        # Reverse the notes list to maintain original order (since we processed in reverse)
        self.speaker_notes.reverse()
        
        return clean_text
    
    def _process_note_content(self, note_content: str) -> str:
        """
        Process speaker note content through the same markdown pipeline as main content.
        
        Args:
            note_content: Raw note content
            
        Returns:
            Processed note content (HTML converted to plain text with formatting indicators)
        """
        import re
        from html import unescape
        
        # Apply the same custom syntax preprocessing as main content
        processed = note_content
        
        # Convert ==highlight== to HTML <mark> tags
        processed = re.sub(r'==(.*?)==', r'<mark>\1</mark>', processed)
        
        # Convert ++underline++ (single) and ^^wavy^^ underline first
        processed = re.sub(r'\+\+(.*?)\+\+', r'<u>\1</u>', processed)
        processed = re.sub(r'\^\^(.*?)\^\^', r'<u class="wavy">\1</u>', processed)

        # Convert ~~strikethrough~~ to <del>
        processed = re.sub(r'~~(.*?)~~', r'<del>\1</del>', processed)
        
        # Process through markdown renderer
        html_content = self.markdown_processor.render(processed)
        
        # Convert HTML back to plain text for PowerPoint notes, preserving formatting indicators
        plain_text = html_content
        
        # Replace HTML tags with text equivalents that show the formatting
        plain_text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', plain_text, flags=re.DOTALL)
        plain_text = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', plain_text, flags=re.DOTALL)
        plain_text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', plain_text, flags=re.DOTALL)
        plain_text = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', plain_text, flags=re.DOTALL)
        plain_text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', plain_text, flags=re.DOTALL)
        plain_text = re.sub(r'<mark[^>]*>(.*?)</mark>', r'==\1==', plain_text, flags=re.DOTALL)
        plain_text = re.sub(r'<u[^>]*>(.*?)</u>', r'+++\1+++', plain_text, flags=re.DOTALL)
        plain_text = re.sub(r'<del[^>]*>(.*?)</del>', r'~~~\1~~~', plain_text, flags=re.DOTALL)
        
        # Handle links - convert to readable format
        plain_text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'\2 (\1)', plain_text, flags=re.DOTALL)
        
        # Remove remaining HTML tags
        plain_text = re.sub(r'<[^>]+>', '', plain_text)
        
        # Decode HTML entities
        plain_text = unescape(plain_text)
        
        # Clean up whitespace
        plain_text = re.sub(r'\n\s*\n', '\n\n', plain_text)  # Normalize line breaks
        plain_text = plain_text.strip()
        
        return plain_text

    def get_speaker_notes(self) -> List[SpeakerNote]:
        """Get the speaker notes extracted during the last parse."""
        return self.speaker_notes.copy()
    
    def clear_speaker_notes(self) -> None:
        """Clear all stored speaker notes. Call this before processing a new document."""
        self.speaker_notes.clear()


def parse_markdown(markdown_text: str, extensions: Optional[List[str]] = None) -> str:
    """
    Convenience function to parse markdown text to HTML.
    
    Args:
        markdown_text: Raw markdown content
        extensions: List of extensions (for compatibility)
        
    Returns:
        HTML string
    """
    parser = MarkdownParser(extensions)
    return parser.parse(markdown_text)


def parse_markdown_slides(markdown_text: str, extensions: Optional[List[str]] = None) -> List[str]:
    """
    Convenience function to parse markdown text and split on page breaks.
    
    Args:
        markdown_text: Raw markdown content
        extensions: List of extensions (for compatibility)
        
    Returns:
        List of HTML strings, one per slide
    """
    parser = MarkdownParser(extensions)
    return parser.parse_with_page_breaks(markdown_text) 