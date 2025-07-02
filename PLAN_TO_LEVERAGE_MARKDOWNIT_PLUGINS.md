Many people regex their way through Markdown until they discover that `mdit-py-plugins` exists. Here's the **full list** of officially supported plugins under [`mdit-py-plugins`](https://github.com/executablebooks/mdit-py-plugins), all compatible with `markdown-it-py`.

---

### ✅ **Core plugin list (as of 2024)**

| Plugin                | Usage                            | What it adds                                                 |
| --------------------- | -------------------------------- | ------------------------------------------------------------ |
| `attrs_plugin`        | `.use(attrs_plugin)`             | `{.class #id key=val}` on inline/block                       |
| `container_plugin`    | `.use(container_plugin, "name")` | `:::name` fenced containers (e.g., `:::warning`)             |
| `deflist_plugin`      | `.use(deflist_plugin)`           | Definition lists (`Term\n: definition`)                      |
| `dollarmath_plugin`   | `.use(dollarmath_plugin)`        | Inline and block math with `$...$`, `$$...$$`                |
| `fieldlist_plugin`    | `.use(fieldlist_plugin)`         | Field lists like `:field name: value`                        |
| `front_matter_plugin` | `.use(front_matter_plugin)`      | Parse YAML frontmatter `---` blocks                          |
| `colon_fence_plugin`  | `.use(colon_fence_plugin)`       | Alternate fence syntax like `:::code` (instead of \`\`\`\`)  |
| `tasklists_plugin`    | `.use(tasklists_plugin)`         | GitHub-style checkboxes: `- [x]`                             |
| `texmath_plugin`      | `.use(texmath_plugin)`           | LaTeX math with multiple delimiters (e.g., `\[ \]`, `$$ $$`) |

---

### 🧩 Additional integrations (not plugins per se, but relevant):

* You can combine these with `markdown-it` parser options like `html`, `linkify`, `typographer`.
* You can extend with **custom plugins** if you want something like:

  * Mermaid diagrams
  * Interactive containers
  * PPTX-aware directives

---


---

### 🛠️ Recommended combo for slide/pptx workflows:

```python
md = MarkdownIt("commonmark", {
    "html": True,
    "linkify": True,
    "typographer": True,
}) \
.use(attrs_plugin) \
.use(container_plugin, "columns") \
.use(container_plugin, "column") \
.use(deflist_plugin) \
.use(tasklists_plugin)
```

----

**PPTX-aware directives** refer to custom Markdown syntax or semantic hints embedded in the Markdown that control **PowerPoint-specific rendering**, such as:

* Slide structure
* Layout logic (columns, spacing)
* Textbox positioning
* Style application (font size, background, image sizing)
* Dynamic chart/table injection

They’re not part of standard Markdown or `markdown-it`, but you can build them via:

* `container_plugin` (`:::note`)
* `attrs_plugin` (`{.h1 .center}`)
* Custom tokens (e.g., `::slide`, `::table`, `::figure`, `::layout`)

---

### ✅ Use cases for PPTX-aware directives

| Markdown Input                             | What It Controls in PPTX                    |
| ------------------------------------------ | ------------------------------------------- |
| `::slide[title="Overview"]`                | Start a new slide with given title          |
| `:::columns` / `:::column`                 | Two-column textbox layout                   |
| `[Figure: Revenue](!img.png){.full-width}` | Full-width image with caption               |
| `:::chart type=bar data=foo.csv`           | Insert bar chart from source                |
| `::layout[x=100 y=200 w=400 h=100]`        | Place textbox at absolute coords (px or pt) |
| `[CTA Button]{.rounded .bg-blue}`          | Stylized textbox for button-style links     |
| `- [ ] TODO Item` (tasklists)              | Add checkboxes or icon badges               |
| `---` or `<!-- break -->`                  | Slide/page breaks                           |

---

### 🧠 How to implement

You extend the Markdown parser using:

1. `attrs_plugin` for attaching position/style metadata to spans/blocks
2. `container_plugin` for parsing blocks like `:::slide`
3. A **custom postprocessor** (Python) that:

   * Walks parsed tokens
   * Interprets them as layout directives
   * Translates them into `python-pptx` slide shapes

Example:

```markdown
:::slide [title="Q2 Revenue"]
# Growth by Region

:::columns
:::column
**EMEA**: 14% ↑  
**APAC**: 8% ↓
:::

:::column
![Chart](q2_growth.png){.full-width}
:::
:::
```

Would be parsed into:

* A new slide
* Left/right text and image boxes
* Stylings from `attrs`

---

### ✅ Why this is powerful

* You stay **within Markdown**, no YAML or HTML needed.
* Designers or PMs can edit content with no PPTX knowledge.
* Works perfectly with `puppeteer` layout and `python-pptx` rendering.

---


### ✅ Setup for "use these contents for layout on each page"

1. **Markdown** is parsed into **HTML** (with attrs and containers preserved)
2. **Puppeteer** renders the HTML, measures boxes, and **injects layout info** back (e.g., via `style="left:..., top:..., width:..."`, or `data-*` attributes)
3. You then **read that HTML** in Python (via `BeautifulSoup`), and want to:

   * Extract structured layout info (box, style, text)
   * Feed that into `python-pptx`
   * **Avoid regex completely**

---



The note lays out a solid direction: rely on markdown-it-py’s plugin ecosystem (attrs, container, colon_fence, tasklists, etc.) and let the parser produce a richly tagged HTML/AST so we avoid home-grown regex transformations.

Current state of our pipeline
• We already use markdown-it-py with `html`, `linkify`, `typographer`.
• We manually regex-convert highlight, underline, wavy underline, strike, image scaling, column containers, etc.
• We manually validate triple-colon blocks and build custom columns via regex + helper.
• The renderer relies on `data-*` attributes from Puppeteer for x/y/w/h, but inline styles/classes are still parsed in Python with regex.

Where plugins could replace custom code
1. attrs_plugin  
   – Gives `{.class #id key=val}` on any span/block → replaces our `[text]{.red}` regex and future color/size classes.  
   – Also lets us add layout metadata in Markdown instead of post-HTML regex.

2. container_plugin / colon_fence_plugin  
   – Can parse `:::columns`, `:::column`, `:::note`, etc. cleanly.  
   – Removes the need for `_validate_fenced_blocks()` and all column-building regex.

3. tasklists_plugin, deflist_plugin, etc.  
   – Provide richer list options without regex.

4. front_matter_plugin  
   – Could accept slide-level metadata at top of file instead of magic comments.

Benefits
• Far fewer regex substitutions → lower maintenance & fewer edge-case bugs.  
• AST tokens carry attributes directly; we can map them to HTML or even JSON, bypassing risky text substitution.  
• Easier to extend: want a new style? define a class and CSS – no code changes.  
• Closer WYSIWYG parity: preview = final because the same attrs drive CSS and PPTX.

Challenges / incremental plan
1. We already wrote custom code for highlight/underline/strike/etc. Replacing it means re-implementing those as small plugins or attrs-based classes. That is manageable but touches both parser and renderer.

2. Our Puppeteer layout step expects certain HTML scaffolding. Migrating to plugin-based output must ensure the same `data-*` attributes or provide an AST→layout mapping step.

Actionable Next Steps
1. Short-term (low-risk, quick wins)  
   a. Adopt `attrs_plugin` fully:  
      • Remove our `[text]{.red}` regex – it’s redundant; use plugin + CSS classes.  
      • For underline/strike/highlight, also allow users to write `{.underline}`, `{.strike}`, etc., and map those to font styles in renderer (simpler than parsing `<u>` or `<del>`).  
   b. Keep our existing regex conversions as fallback until migration is complete; guard them with “if plugin not available”.

2. Mid-term  
   a. Replace custom column handling with `container_plugin("columns")` and individual `:::column`.  
      • Parse widths via attrs (`{width=60%}`) instead of curly braces in regex.  
      • Drop `_validate_fenced_blocks()`; let the parser’s nesting rules handle it.  
   b. Retire manual triple-colon validation/mutation code.

3. Longer-term / stretch  
   a. Explore emitting a lightweight JSON layout spec directly from markdown-it tokens, skipping HTML parsing in Python altogether.  
   b. Add `tasklists_plugin`, `deflist_plugin` for richer list types.  
   c. Define custom plugin(s) for PPTX-specific directives (`::slide`, `::chart`, etc.) so authors stay in Markdown.

4. Tooling / CI  
   • Add tests that render markdown with plugin syntax and assert correct PPTX output (color class, container structure).  
   • Document supported plugins & syntax in README.

5. Compatibility  
   • Keep regex fallbacks behind a feature flag (`use_legacy_markdown=True`) until migration is proven stable.
