# Branch Strategy: Math Support

This repository maintains two branches to support different deployment environments:

## 🏢 Main Branch (Company Server Compatible)
- **Purpose**: Production deployment on company servers without KaTeX dependencies
- **Math Support**: Text fallbacks only (no LaTeX rendering)
- **Dependencies**: Minimal, no external math rendering requirements
- **Use Case**: Corporate environments with limited package support

## 🧮 Feature/KaTeX-Math Branch (Full Math Support)
- **Purpose**: Development and future deployment with full math capabilities
- **Math Support**: Full LaTeX rendering via KaTeX CLI
- **Dependencies**: Requires KaTeX installation (`npm install katex`)
- **Use Case**: Environments that support full math rendering

## Branch Management

### Current State
- **Main branch**: Math functionality disabled, text fallbacks active
- **feature/katex-math branch**: Full KaTeX math rendering preserved

### Switching Between Versions

#### To use the company-compatible version (main):
```bash
git checkout main
pip install -r requirements.txt
# No additional setup needed
```

#### To use the full math version (feature/katex-math):
```bash
git checkout feature/katex-math
pip install -r requirements.txt
npm install katex  # Install KaTeX CLI
```

### Future Integration

When company servers support KaTeX dependencies:

1. **Test the math branch**: Ensure feature/katex-math works in the new environment
2. **Merge back to main**: 
   ```bash
   git checkout main
   git merge feature/katex-math
   ```
3. **Update documentation**: Remove this branching strategy

## Technical Differences

### Math Rendering Behavior

| Feature | Main Branch | KaTeX Branch |
|---------|-------------|--------------|
| Inline math (`$E=mc^2$`) | Text fallback: `[Math: E=mc^2]` | Rendered LaTeX |
| Display math (`$$...$$`) | Text fallback | Rendered LaTeX |
| CSS styling | `.math-fallback` classes | `.katex` classes |
| Dependencies | No KaTeX required | Requires KaTeX CLI |

### Code Changes in Main Branch

1. **Math renderer**: Stub implementation with text fallbacks
2. **CSS themes**: Fallback styling instead of KaTeX styles  
3. **Requirements**: KaTeX dependency commented out
4. **Examples**: Math examples replaced with text formatting demos

### Maintaining Both Branches

- **Bug fixes**: Apply to both branches as needed
- **New features**: Develop on feature/katex-math, backport non-math features to main
- **Testing**: Test both versions before releases

## Files Modified for Company Compatibility

- `requirements.txt`: KaTeX dependency disabled
- `slide_generator/math_renderer.py`: Stub implementation
- `themes/default.css`: Fallback math styling
- `themes/dark.css`: Fallback math styling  
- `examples/demo_content.md`: Math examples replaced
- `slide_generator/layout_engine.py`: Updated comments

All changes preserve the same API interface, ensuring compatibility across both versions.