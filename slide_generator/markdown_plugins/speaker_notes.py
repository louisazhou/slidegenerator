from markdown_it import MarkdownIt
from markdown_it.rules_block import StateBlock


def speaker_notes_plugin(md: MarkdownIt):
    """Markdown-it-py plugin that turns lines beginning with `???` into HTML
    comments of the form `<!-- NOTE: ... -->`.  This lets the existing
    speaker-notes extraction in *MarkdownParser* pick them up without any
    layout-engine changes.
    """

    def _note_block(state: StateBlock, start_line: int, end_line: int, silent: bool):
        src = state.src
        line_start = state.bMarks[start_line] + state.tShift[start_line]
        max_pos = state.eMarks[start_line]

        # Must start with ??? (optionally preceded by spaces)
        if not src.startswith('???', line_start):
            return False

        # Content after the ??? marker
        content_start = line_start + 3
        note_content = src[content_start:max_pos].strip()

        if silent:
            return True

        token = state.push('html_block', '', 0)
        token.content = f"<!-- NOTE: {note_content} -->\n"
        token.map = [start_line, start_line + 1]

        state.line = start_line + 1
        return True

    # Insert before paragraph rule so it captures lines first
    md.block.ruler.before('paragraph', 'speaker_notes', _note_block)
