# Project Structure Documentation

## 📁 Directory Structure

```
Slide_generate/
├── src/slide_generator/          # Main package
│   ├── __init__.py              # Package exports
│   ├── layout_engine.py         # HTML measurement & pagination
│   ├── pptx_renderer.py         # PowerPoint rendering
│   ├── generator.py             # Main SlideGenerator class
│   └── models.py                # Data models (Block class)
├── examples/
│   └── slide_proto.py           # Demo/example usage
├── tests/
│   ├── unit/                    # Unit tests
│   │   ├── test_slide_generator.py
│   │   ├── test_slide_nonempty.py
│   │   ├── test_no_overlap.py
│   │   └── test_pptx_content_validation.py
│   └── check_pptx.py           # PPTX inspection utility
├── output/                      # Generated files directory
│   └── demo.pptx               # Generated presentations
├── requirements.txt             # Python dependencies
├── token.json                  # Google API credentials (for future use)
├── .gitignore                  # Git ignore rules
└── PROJECT_STRUCTURE.md        # This documentation
```

## 📋 File Registry & Purposes

### **Core Package Files** ✅

#### `src/slide_generator/__init__.py`
- **Purpose**: Package initialization and exports
- **Exports**: `SlideGenerator`, `LayoutEngine`, `PPTXRenderer`, `Block`
- **Status**: Active, required for package imports

#### `src/slide_generator/models.py`
- **Purpose**: Data models for representing layout elements
- **Key Classes**: 
  - `Block`: Represents a layout element with position, size, content, and type information
  - Provides compatibility properties and type checking methods
- **Status**: Core data structure, used throughout the pipeline
- **⚠️ DO NOT REMOVE**: This class is essential for the layout system

#### `src/slide_generator/layout_engine.py`
- **Purpose**: HTML measurement and pagination using Puppeteer
- **Key Functions**:
  - `measure_layout()`: Browser-based element measurement
  - `convert_markdown_to_html()`: Markdown to HTML conversion with CSS
  - `measure_and_paginate()`: Complete measurement pipeline, returns Block objects
- **Dependencies**: `pyppeteer`, `markdown`
- **Status**: Core functionality, DO NOT MODIFY without understanding browser measurement

#### `src/slide_generator/pptx_renderer.py`
- **Purpose**: PowerPoint slide rendering from Block objects
- **Key Functions**:
  - `create_pptx()`: Main PPTX creation
  - `_process_layout()`: Layout processing and pagination
  - `_add_element_to_slide()`: Individual element rendering
- **Dependencies**: `python-pptx`
- **Status**: Core functionality, handles precise positioning

#### `src/slide_generator/generator.py`
- **Purpose**: Main coordinator class that ties everything together
- **Key Functions**:
  - `generate_slide()`: Main public API
- **Default Output**: `output/demo.pptx`
- **Status**: Main entry point, safe to modify for API changes

### **Example & Demo Files** ✅

#### `examples/slide_proto.py`
- **Purpose**: Demonstration of package usage
- **Features**: Multi-slide markdown example with various content types
- **Output**: Creates `output/demo.pptx`
- **Status**: Example only, safe to modify for demos

### **Test Files** ✅

#### `tests/unit/test_slide_generator.py`
- **Purpose**: Basic functionality tests for SlideGenerator
- **Tests**: Basic slide creation, multi-slide generation
- **Status**: Essential for CI/CD

#### `tests/unit/test_slide_nonempty.py`
- **Purpose**: Ensures generated slides contain actual content
- **Tests**: Non-empty slides, handling of empty slide markers
- **Status**: Critical for quality assurance

#### `tests/unit/test_no_overlap.py`
- **Purpose**: Validates layout positioning and element overlap prevention
- **Tests**: Shape overlap detection, textbox height validation
- **Dependencies**: Requires `output/demo.pptx` to exist
- **Status**: Critical for layout quality

#### `tests/unit/test_pptx_content_validation.py` ✅ **NEW**
- **Purpose**: **CRITICAL** content validation test (replaces manual check_pptx.py)
- **Tests**: 
  - Content structure validation
  - Slide dimension verification  
  - Content type detection (headings, lists, code)
- **Usage**: Can be run standalone: `python tests/unit/test_pptx_content_validation.py`
- **Status**: **ESSENTIAL** - Run this after any changes to verify output quality
- **⚠️ IMPORTANT**: This test provides detailed inspection output and should be part of your validation workflow

#### `tests/check_pptx.py`
- **Purpose**: Legacy utility script for manual PPTX inspection
- **Usage**: `python tests/check_pptx.py`
- **Status**: Kept for backward compatibility, but use `test_pptx_content_validation.py` instead

### **Configuration Files** ✅

#### `requirements.txt`
- **Purpose**: Python package dependencies
- **Contents**: 
  - `markdown==3.4.1` - Markdown processing
  - `pyppeteer==1.0.2` - Browser automation
  - `python-pptx==0.6.21` - PowerPoint generation
  - `google-api-python-client==2.79.0` - **Future Google Slides integration**
  - `google-auth-httplib2==0.1.0` - **Future Google Slides integration**
  - `google-auth-oauthlib==1.0.0` - **Future Google Slides integration**
- **Status**: All dependencies are intentional (Google APIs for future use)

#### `token.json`
- **Purpose**: Google API credentials for future Google Slides integration
- **Status**: Present for future development, not currently used in code

#### `.gitignore`
- **Purpose**: Git ignore patterns
- **Covers**: Python cache, temporary files, macOS files, IDE files
- **Status**: Comprehensive ignore rules

### **Output Directory** ✅

#### `output/`
- **Purpose**: Generated presentation files
- **Contents**: `demo.pptx` and other generated files
- **Status**: Auto-created by SlideGenerator, safe to clean

## 🚨 **DO NOT TOUCH** Guidelines

### Critical Files (Modify with Extreme Caution)
1. **`src/slide_generator/models.py`** - Contains Block class used throughout the system
2. **`src/slide_generator/layout_engine.py`** - Contains complex browser measurement logic
3. **`src/slide_generator/pptx_renderer.py`** - Handles precise PowerPoint positioning
4. **Test files** - All tests must continue to pass

### Safe to Modify
1. **`examples/slide_proto.py`** - Demo script only
2. **`src/slide_generator/generator.py`** - Main API, but test thoroughly
3. **Output directory contents** - Generated files

### Configuration Files
1. **`.gitignore`** - Safe to extend, don't remove existing patterns
2. **`PROJECT_STRUCTURE.md`** - This file, keep updated
3. **`requirements.txt`** - **DO NOT remove Google dependencies** (future use)

## 🔧 Development Workflow

1. **Adding Features**: Extend `SlideGenerator` class in `generator.py`
2. **Fixing Bugs**: Usually in `layout_engine.py` or `pptx_renderer.py`
3. **Testing**: Always run `pytest tests/unit/` before commits
4. **Content Validation**: Run `python tests/unit/test_pptx_content_validation.py` for detailed output inspection
5. **Output**: All generated files go to `output/` directory

## 🧪 **Critical Testing Protocol**

### After ANY changes to the codebase:

1. **Run all unit tests**: `pytest tests/unit/ -v`
2. **Run content validation**: `python tests/unit/test_pptx_content_validation.py`
3. **Verify output**: Check that `output/demo.pptx` opens correctly in PowerPoint

### The content validation test is ESSENTIAL because it:
- ✅ Validates slide content structure
- ✅ Ensures proper element positioning  
- ✅ Checks for expected content types
- ✅ Provides detailed inspection output
- ✅ Verifies slide dimensions

## ✅ Current Status
- **All tests passing**: 8/8 tests pass (including new content validation)
- **Block class properly integrated**: Layout pipeline uses structured data models
- **Google dependencies preserved**: Ready for future Google Slides integration
- **Consistent output**: All files generated in `output/`
- **Comprehensive testing**: Content validation ensures output quality
- **Proper gitignore**: Temporary files excluded from git 