# Project Structure Documentation

## 📁 Directory Structure

```
Slide_generate/
├── src/slide_generator/          # Main package (M2 ✅ Complete)
│   ├── __init__.py              # Package exports: SlideGenerator, LayoutEngine, PPTXRenderer, Block
│   ├── models.py                # Block class with type checking & compatibility methods
│   ├── layout_engine.py         # HTML measurement & pagination (now returns List[List[Block]])
│   ├── pptx_renderer.py         # PowerPoint rendering (accepts paginated blocks)
│   ├── generator.py             # Main SlideGenerator.generate() orchestrator
│   ├── markdown_parser.py       # 🆕 Modern markdown-it-py parser with enhanced features
│   └── theme_loader.py          # 🆕 CSS theme system for consistent styling
├── examples/
│   ├── slide_proto.py           # Demo script using new API
│   └── sample.md                # Sample markdown for CLI testing
├── tests/unit/                  # Unit tests (41/41 passing ✅)
│   ├── test_layout_engine.py    # LayoutEngine.measure_and_paginate() tests
│   ├── test_slide_generator.py  # SlideGenerator.generate() tests
│   ├── test_slide_nonempty.py   # Empty slide prevention tests
│   ├── test_no_overlap.py       # Layout overlap & positioning tests
│   ├── test_pptx_content_validation.py # **CRITICAL** content structure validation
│   ├── test_markdown_parser.py  # 🆕 Comprehensive markdown-it-py parser tests
│   └── test_theme_loader.py     # 🆕 Theme system tests
├── output/                      # Generated files directory
│   ├── demo.pptx               # Main demo presentation
│   └── cli_demo.pptx           # CLI-generated presentation
├── requirements.txt             # Dependencies (Google APIs preserved for M3+)
├── token.json                  # Google API credentials (future M3+ use)
├── .gitignore                  # Comprehensive ignore rules
└── PROJECT_STRUCTURE.md        # This documentation
```

## 🎯 **Milestone 2 Complete** ✅

### **Architecture Overview**
The codebase now follows an enhanced modular pipeline with modern markdown processing:

```
Markdown Text → MarkdownParser → LayoutEngine.measure_and_paginate() → List[List[Block]] → PPTXRenderer.render() → PPTX File
      ↓               ↓                      ↓                              ↓                        ↓
  markdown-it-py   Enhanced HTML    HTML + CSS + Puppeteer        Page-aware Block objects    PowerPoint generation
   processing      with themes      Browser measurement           with proper list formatting  with fixed rendering
```

### **Major M2 Achievements**
- ✅ **Modern Markdown Parser**: Upgraded from old `markdown` library to `markdown-it-py`
- ✅ **Enhanced List Processing**: Fixed list rendering with proper line breaks and formatting
- ✅ **Theme System**: Added CSS theme loader with default and dark themes
- ✅ **Content Rendering Fixes**: Fixed PPTX text box margins and sizing issues
- ✅ **Test Suite Expansion**: 41 comprehensive tests covering all functionality
- ✅ **Conda Environment**: Created `gslides_test` environment with modern dependencies

## 📋 File Registry & Purposes

### **Core Package Files** ✅

#### `src/slide_generator/__init__.py`
- **Purpose**: Package initialization and exports
- **Exports**: `SlideGenerator`, `LayoutEngine`, `PPTXRenderer`, `Block`, `MarkdownParser`, `ThemeLoader`
- **Status**: M2 complete, ready for M3 extensions

#### `src/slide_generator/models.py` ⭐ **CRITICAL**
- **Purpose**: Structured data models for layout elements
- **Key Classes**: 
  - `Block`: Core data structure with position, content, style, and type information
  - Methods: `is_heading()`, `is_paragraph()`, `is_list()`, `is_list_item()`, `is_code_block()`, `is_page_break()`
  - Compatibility: Properties for legacy code (`width`, `height`, `textContent`, `tagName`)
- **Status**: Enhanced with list item detection, foundation for entire pipeline
- **⚠️ DO NOT REMOVE**: Used throughout layout and rendering systems

#### `src/slide_generator/layout_engine.py` ⭐ **CORE**
- **Purpose**: HTML measurement and pagination using Puppeteer
- **Key Functions**:
  - `measure_and_paginate(markdown, page_height=540)`: **Main API** - returns `List[List[Block]]`
  - `paginate(blocks, max_height)`: Page-aware block organization
  - `convert_markdown_to_html()`: Markdown to HTML with responsive CSS
  - `measure_layout()`: Browser-based precise element measurement with list handling
- **Enhanced Features**: 
  - Processes `ul`/`ol` elements directly instead of individual `li` elements
  - Proper line break formatting for lists (`\n` between items)
  - `SLIDES_DEBUG=1` shows detailed pagination info
- **Dependencies**: `pyppeteer`, `markdown-it-py`, `asyncio`
- **Status**: M2 complete with enhanced list processing

#### `src/slide_generator/pptx_renderer.py`
- **Purpose**: PowerPoint generation from paginated Block objects
- **Key Functions**:
  - `render(pages: List[List[Block]], output_path)`: **Main API**
  - `_add_element_to_slide()`: Individual element positioning with proper scaling
  - `_add_formatted_text()`: Enhanced text formatting (placeholder for future rich text)
- **M2 Improvements**: 
  - Fixed text box margin issues (set to 0 instead of Inches(0.1))
  - Implemented minimum text box dimensions for visibility
  - Enhanced content rendering to prevent truncation
- **Features**: 16:9 aspect ratio (13.33" x 7.5"), coordinate scaling, text formatting
- **Dependencies**: `python-pptx`
- **Status**: M2 complete with rendering fixes

#### `src/slide_generator/generator.py` ⭐ **ENTRY POINT**
- **Purpose**: Main coordinator orchestrating the entire pipeline
- **Key Functions**:
  - `generate(markdown_text, output_path="output/demo.pptx")`: **Public API**
  - `main()`: Command-line interface
- **Pipeline**: MarkdownParser → LayoutEngine → PPTXRenderer coordination
- **Status**: M2 complete, clean API ready for extensions

#### `src/slide_generator/markdown_parser.py` 🆕 **NEW IN M2**
- **Purpose**: Modern markdown processing with markdown-it-py
- **Key Features**:
  - Enhanced markdown parsing with tables, strikethrough, linkify, typographer
  - Comprehensive page break support (---, <!-- slide -->, [slide], etc.)
  - Page break counting and slide estimation
  - Backward compatibility with old markdown library API
- **Key Functions**:
  - `parse(markdown_text)`: Convert markdown to HTML
  - `parse_with_page_breaks(markdown_text)`: Split content on page breaks
  - `count_page_breaks()`, `estimate_slide_count()`: Content analysis
- **Dependencies**: `markdown-it-py`
- **Status**: M2 complete, modern markdown processing

#### `src/slide_generator/theme_loader.py` 🆕 **NEW IN M2**
- **Purpose**: CSS theme system for consistent styling
- **Key Features**:
  - Default and dark theme support
  - Theme validation and listing
  - Extensible theme system for future customization
- **Key Functions**:
  - `get_css(theme_name)`: Load theme CSS
  - `list_available_themes()`: List all available themes
  - `validate_theme(theme_name)`: Check theme validity
- **Status**: M2 complete, ready for theme expansion

### **Example & Demo Files** ✅

#### `examples/slide_proto.py`
- **Purpose**: Demonstration of the complete M2 pipeline
- **Features**: Multi-slide markdown with headings, lists, code blocks, page breaks
- **Output**: Creates `output/demo.pptx` with debug logging
- **Status**: Updated for M2 API with enhanced markdown processing

#### `examples/sample.md`
- **Purpose**: Sample markdown content for CLI testing
- **Features**: Multi-slide content with various elements
- **Usage**: `python -m src.slide_generator.generator examples/sample.md output.pptx`
- **Status**: M2 ready with enhanced markdown features

### **Test Files** ✅ (41/41 passing)

#### `tests/unit/test_layout_engine.py`
- **Purpose**: Core layout and pagination testing
- **Tests**: Markdown conversion, page breaks, code blocks, empty content, height-based pagination
- **M2 Updates**: Fixed list detection to check for `ul`/`ol` elements instead of `li`
- **Key Validations**: Block type detection, page count accuracy
- **Status**: M2 complete, validates enhanced list processing

#### `tests/unit/test_slide_generator.py`
- **Purpose**: End-to-end SlideGenerator testing
- **Tests**: Basic generation, multi-slide creation, file output validation
- **Status**: M2 complete with enhanced markdown processing

#### `tests/unit/test_slide_nonempty.py`
- **Purpose**: Quality assurance - prevents empty slides
- **Tests**: Content validation, empty markdown handling, multi-page consistency
- **Status**: M2 complete, ensures robust output

#### `tests/unit/test_no_overlap.py`
- **Purpose**: Layout positioning and overlap prevention
- **Tests**: Shape overlap detection, textbox height validation, coordinate accuracy
- **Dependencies**: Requires `output/demo.pptx` to exist
- **Status**: M2 complete, critical for layout quality

#### `tests/unit/test_pptx_content_validation.py` ⭐ **CRITICAL**
- **Purpose**: **ESSENTIAL** comprehensive content validation
- **Tests**: 
  - Content structure (headings, lists, code detection)
  - Slide dimensions (16:9 aspect ratio validation)
  - Element count and distribution across slides
- **Usage**: `python tests/unit/test_pptx_content_validation.py` for detailed inspection
- **Output**: Color-coded inspection report with shape counts and content analysis
- **Status**: M2 complete, validates enhanced content rendering

#### `tests/unit/test_markdown_parser.py` 🆕 **NEW IN M2**
- **Purpose**: Comprehensive testing of markdown-it-py parser
- **Tests**: 
  - Basic markdown parsing (headings, paragraphs, lists, code)
  - Table parsing and rendering
  - Page break handling (all supported formats)
  - Extension management and compatibility
  - Enhanced features integration
- **Coverage**: 22 test cases covering all parser functionality
- **Status**: M2 complete, validates modern markdown processing

#### `tests/unit/test_theme_loader.py` 🆕 **NEW IN M2**
- **Purpose**: Theme system validation
- **Tests**: 
  - Theme loading and validation
  - CSS content quality checks
  - Theme listing and error handling
- **Status**: M2 complete, validates theme system

### **Configuration Files** ✅

#### `requirements.txt`
- **Purpose**: Python package dependencies with clear organization
- **M2 Core Dependencies**: 
  - `python-pptx>=0.6.21` - PowerPoint generation
  - `pyppeteer>=1.0.2` - Browser automation  
  - `markdown-it-py>=3.0.0` - **NEW** Modern markdown processing
  - `websockets==10.4` - **NEW** Compatibility fix for pyppeteer
  - `pytest>=6.2.4` - Testing framework
- **Future M3+ Dependencies** (preserved as requested):
  - `google-api-python-client>=2.88.0` - Google Slides API
  - `google-auth-httplib2>=0.1.0` - Google authentication
  - `google-auth-oauthlib>=1.0.0` - Google OAuth
- **Status**: Updated for M2 with modern dependencies

#### `token.json` & `credentials.json`
- **Purpose**: Google API credentials for future Google Slides integration
- **Status**: Present for M3+ development, not currently used

#### `.gitignore`
- **Purpose**: Comprehensive git ignore patterns
- **Covers**: Python cache, temp files, OS files, IDE files, output directories
- **Status**: Complete protection for development workflow

### **Output Directory** ✅

#### `output/`
- **Purpose**: All generated presentation files
- **Contents**: 
  - `demo.pptx` - Main demo from slide_proto.py with enhanced formatting
  - `cli_demo.pptx` - CLI-generated example
  - Test output files (cleaned automatically)
- **Status**: Enhanced content with proper list formatting and rendering

## 🚨 **DO NOT TOUCH** Guidelines

### Critical Files (Extreme Caution Required)
1. **`src/slide_generator/models.py`** - Block class is foundation of entire system
2. **`src/slide_generator/layout_engine.py`** - Complex browser measurement and pagination logic
3. **`src/slide_generator/pptx_renderer.py`** - Precise coordinate scaling and PowerPoint generation
4. **All test files** - Must maintain 41/41 passing status

### Safe to Modify for M3+
1. **`src/slide_generator/generator.py`** - Main API, but test thoroughly
2. **`src/slide_generator/markdown_parser.py`** - Can extend with new features
3. **`src/slide_generator/theme_loader.py`** - Can add new themes
4. **`examples/`** - Demo scripts, safe for experimentation
5. **New files for M3** - Can add new modules without breaking existing code

### Configuration Files
1. **`requirements.txt`** - Safe to add new dependencies, **preserve Google APIs**
2. **`.gitignore`** - Safe to extend patterns
3. **`PROJECT_STRUCTURE.md`** - Keep updated with changes

## 🔧 **M2 Lessons Learned**

### **Critical Testing Protocol** ⚠️
**After ANY code changes, always run:**
1. `PYTHONPATH=/Users/louisazhou/Downloads/Slide_generate pytest tests/unit/ -v` (all 41 tests)
2. `PYTHONPATH=/Users/louisazhou/Downloads/Slide_generate python tests/unit/test_pptx_content_validation.py` (detailed content inspection)
3. Verify `output/demo.pptx` opens correctly in PowerPoint

### **Key M2 Achievements & Fixes**
1. **List Rendering Fixed**: Proper separation between ordered/unordered lists with correct numbering
2. **Content Visibility**: All content now renders correctly in PPTX files without truncation
3. **Modern Parser**: Upgraded to `markdown-it-py` for better markdown processing and features
4. **Line Breaks**: Lists maintain HTML-calculated spacing with `\n` between items
5. **Test Coverage**: Expanded from 18 to 41 tests with comprehensive validation
6. **Environment Setup**: Created dedicated `gslides_test` conda environment

### **Development Workflow**
1. **Environment**: Always use `conda activate gslides_test` for development
2. **Testing**: Test incrementally after each significant change
3. **Module boundaries**: Respect separation between parsing, layout, and rendering
4. **API consistency**: Maintain clean interfaces between components
5. **Debug output**: Use `SLIDES_DEBUG=1` for pagination insights

## 🎯 **Ready for M3: Advanced Features**

### **Current M2 Capabilities**
- ✅ Modern markdown processing with markdown-it-py
- ✅ Enhanced list formatting with proper line breaks
- ✅ Theme system with CSS styling
- ✅ Comprehensive testing framework (41 tests)
- ✅ Fixed content rendering and PPTX generation
- ✅ Clean Block-based data model
- ✅ Browser-based precise layout measurement

### **M3 Integration Points**
- Enhanced markdown extensions (footnotes, math, advanced tables)
- Rich text formatting in PPTX (bold, italic, colors)
- Advanced theme system with custom CSS
- Google Slides API integration
- Image and media support
- Interactive elements and animations

### **M3 Quick Win Opportunities**
- Enhanced text formatting in PPTXRenderer
- Advanced markdown extensions integration
- Custom theme creation tools
- Performance optimizations
- Advanced debugging and validation tools

## ✅ **Current Status**
- **M2 Complete**: ✅ All major improvements finished successfully
- **All tests passing**: 41/41 unit tests green
- **Enhanced architecture**: Modern markdown processing with fixed rendering
- **API stability**: Backward compatible, ready for M3 without breaking changes
- **Quality assurance**: Comprehensive validation and inspection tools
- **Development ready**: Solid foundation for advanced features
- **Environment**: Dedicated conda environment with modern dependencies 