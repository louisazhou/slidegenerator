# Aspirational Feature: Syntax Highlighting for Code Blocks

## Overview

This document outlines the planned implementation of syntax highlighting for code blocks in both PowerPoint (PPTX) and Google Slides renderers. This feature would enhance code presentation by applying language-specific color coding to keywords, strings, comments, and other syntax elements.

## Technical Approach

### Core Technology: Pygments

- **Library**: [Pygments](https://pygments.org/) - Industry-standard Python syntax highlighting library
- **Capabilities**: 500+ languages, 40+ color schemes, fine-grained token-level highlighting
- **Integration**: Parse code content, extract tokens with types, apply colors per token

### Architecture Design

```python
# New module: slide_generator/syntax_highlighter.py
class SyntaxHighlighter:
    def __init__(self, theme: str = "default"):
        self.theme = theme
        self.color_mapping = self._load_color_mapping()
    
    def tokenize_code(self, code: str, language: str) -> List[TokenSegment]:
        """Parse code into colored segments using Pygments."""
        # Returns: [TokenSegment(text, start_pos, end_pos, color, style)]
    
    def extract_language(self, block: Block) -> str:
        """Extract language from HTML class attributes."""
        # Look for: class="language-python", class="lang-js", etc.
    
    def get_token_color(self, token_type: TokenType, theme: str) -> str:
        """Map Pygments token types to theme-appropriate colors."""
```

### Language Detection

Code blocks would be detected from HTML class attributes:
- `<pre><code class="language-python">` → Python
- `<pre><code class="lang-javascript">` → JavaScript  
- `<pre><code class="highlight-css">` → CSS
- `<pre><code>` (no class) → Plain text fallback

### Color Scheme Integration

**Theme-Aware Colors:**
- **Light theme**: Dark text on light background
  - Keywords: `#0066cc` (blue)
  - Strings: `#009900` (green)
  - Comments: `#999999` (gray)
  - Numbers: `#ff6600` (orange)

- **Dark theme**: Light text on dark background
  - Keywords: `#66ccff` (light blue)
  - Strings: `#99ff99` (light green)
  - Comments: `#cccccc` (light gray)
  - Numbers: `#ffcc66` (light orange)

## Implementation Strategy

### Phase 1: Dependency and Core Module
1. Add `pygments` to project dependencies
2. Create `slide_generator/syntax_highlighter.py`
3. Implement language detection from HTML classes
4. Create color mapping system for light/dark themes

### Phase 2: PPTX Renderer Integration
```python
# In _add_formatted_text() for code blocks
def _apply_syntax_highlighting(self, paragraph, block: Block):
    if not block.is_code_block():
        return self._add_formatted_text_regular(paragraph, block)
    
    # Extract language and tokenize
    language = self.syntax_highlighter.extract_language(block)
    tokens = self.syntax_highlighter.tokenize_code(block.content, language)
    
    # Create colored text runs
    paragraph.clear()
    for token in tokens:
        run = paragraph.add_run()
        run.text = token.text
        run.font.name = 'Courier New'
        run.font.size = Pt(self._validate_font_size('code'))
        
        # Apply token-specific color
        if token.color:
            rgb = self._hex_to_rgb(token.color)
            run.font.color.rgb = RGBColor(*rgb)
```

### Phase 3: Google Slides Renderer Integration
```python
# In _create_code_block_requests()
def _apply_syntax_highlighting_gslides(self, block: Block, object_id: str) -> List[Dict]:
    language = self.syntax_highlighter.extract_language(block)
    tokens = self.syntax_highlighter.tokenize_code(block.content, language)
    
    requests = []
    
    # Insert plain text first
    requests.append({
        "insertText": {
            "objectId": object_id,
            "text": block.content,
            "insertionIndex": 0
        }
    })
    
    # Apply formatting per token range
    for token in tokens:
        if token.color:
            requests.append({
                "updateTextStyle": {
                    "objectId": object_id,
                    "textRange": {
                        "startIndex": token.start_pos,
                        "endIndex": token.end_pos
                    },
                    "style": {
                        "foregroundColor": {
                            "opaqueColor": {
                                "rgbColor": self._hex_to_rgb_dict(token.color)
                            }
                        }
                    },
                    "fields": "foregroundColor"
                }
            })
    
    return requests
```

### Phase 4: Testing and Refinement
- Test with major languages: Python, JavaScript, HTML, CSS, SQL, Bash
- Verify theme consistency across light/dark modes
- Ensure graceful fallback when language detection fails
- Performance testing with large code blocks

## Expected Benefits

1. **Enhanced Readability**: Color-coded syntax makes code easier to read and understand
2. **Professional Appearance**: Industry-standard highlighting improves presentation quality
3. **Language Support**: Automatic detection and highlighting for 500+ programming languages
4. **Theme Integration**: Colors automatically adapt to light/dark presentation themes
5. **Backward Compatibility**: Falls back to monospace formatting if highlighting fails

## Technical Considerations

### Challenges
- **Performance**: Large code blocks with many tokens could slow rendering
- **API Limits**: Google Slides has request limits that many `updateTextStyle` calls might hit
- **Color Accessibility**: Ensuring sufficient contrast for all token colors
- **Language Detection**: Reliable extraction of language from HTML class attributes

### Mitigation Strategies
- **Batching**: Group multiple style requests to reduce API calls
- **Caching**: Cache tokenization results for repeated code blocks
- **Fallback**: Always preserve existing monospace formatting as backup
- **Testing**: Comprehensive testing across languages and themes

## Dependencies

### New Requirements
```
pygments>=2.15.0  # Syntax highlighting engine
```

### Optional Enhancements
```
pygments-styles>=1.0.0  # Additional color schemes
tree-sitter>=0.20.0     # Alternative parsing engine (future)
```

## Future Enhancements

1. **Custom Themes**: Allow users to define custom color schemes
2. **Line Numbers**: Optional line numbering for code blocks
3. **Diff Highlighting**: Special formatting for code diffs and changes
4. **Interactive Features**: Clickable imports/functions (Google Slides only)
5. **Performance Optimization**: Incremental highlighting for large files

## Status

- **Current**: Parked for future implementation
- **Priority**: Medium (after core features stabilization)
- **Effort Estimate**: 2-3 weeks development + testing
- **Dependencies**: None (can be implemented independently)

This feature would significantly enhance the code presentation capabilities of both renderers while maintaining backward compatibility and theme consistency.
