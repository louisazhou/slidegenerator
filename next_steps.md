### What to tackle next — a pragmatic sequence

| Step                                                                  | Why it’s next                                                                                                                                                          | Scope (files & tests)                                                                                                                                                                                                                                              | Time-to-value      |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------ |
| **1. Theme system skeleton**                                          | Every later task (Markdown-to-HTML renderer, font-scale YAML, highlight colours) will inject or switch themes; having a clean place for CSS now avoids rewiring later. | *New* `themes/default.css` (copy hard-coded CSS)  <br>*New* `themes/dark.css` (minimal variant)  <br>*New* `src/slide_generator/theme_loader.py` → `get_css(theme="default")`  <br>Tests: `test_theme_loader.py` simply asserts file read + css string length > 0. | ≈ 20 min           |
| **2. Move Markdown→HTML into separate module (`markdown_parser.py`)** | Unblocks enhanced extensions and Lua / markdown-it work while keeping `layout_engine` slim.                                                                            | *New* `src/slide_generator/markdown_parser.py` — wrap `markdown.markdown()` plus future plugins.  <br>Refactor `layout_engine` to call it.  <br>Update tests to import `markdown_parser`.                                                                          | ≈ 30 min           |
| **3. Enhanced Markdown extensions (quick win)**                       | Gives users tables & fenced-code styles now, required for M3 highlights/lists anyway.                                                                                  | Add `tables`, `fenced_code`, `sane_lists`, `attr_list` to parser; unit test converts sample table and asserts `<table>` present.                                                                                                                                   | ≈ 15 min           |
| **4. Visual-regression harness (snapshot diff ≤ 2 %)**                | It’s the milestone test-gate for M2; better to wire the infra early while pages are still simple.                                                                      | *New* `tests/visual/test_snapshot.py`  <br>Uses Puppeteer to screenshot `.slide`, compares with golden PNG via pillow diff; threshold 2 %.                                                                                                                         | ≈ 45 min (one-off) |
| **5. Rewrite hard-coded CSS injection**                               | Now that themes exist, replace the multiline string in `layout_engine.convert_markdown_to_html()` with `css = theme_loader.get_css(theme)`; drop duplication.          | A few lines changed; all tests must still pass.                                                                                                                                                                                                                    | ≈ 10 min           |

After these five tasks you will have:

* A **theming infrastructure** ready for font scaling & dark mode (future M4).
* A **dedicated Markdown parser module** ready for Pandoc/Lua or markdown-it swap-in.
* Automated **visual diff testing** that will gate all style changes.

---

### Ordering rationale

1. **Theme loader first** – everything else (font sizes, colours, highlight `<mark>`) builds on it, but it’s surgically small.
2. **Markdown parser extraction** – unblocks richer extensions without risking layout engine code.
3. **Extensions** – immediate user benefit; zero impact on block model.
4. **Snapshot infra** – required by milestone spec; easier before CSS gets complex.
5. **CSS refactor** – trivial once theme files exist.

All tasks are self-contained, each should keep the current 18 unit tests green; you’ll add one or two new tests per task.

---

### After these quick wins

You’ll be ready to implement **Milestone 2 proper** (renderer module that wraps fragment + CSS, golden screenshot test ≤ 2 % diff) with almost no additional groundwork.
