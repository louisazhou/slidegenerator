import pytest
from slide_generator.layout_engine import LayoutEngine


@pytest.mark.parametrize(
    "html,expected",
    [
        ("<ul><li>A</li><li>B</li><li>C</li></ul>", ["A", "B", "C"]),
        ("<ol><li>One</li><li>Two</li></ol>", ["One", "Two"]),
    ],
)
def test_extract_all_items(html, expected, tmp_path):
    le = LayoutEngine(debug=False, tmp_dir=tmp_path, theme="default", base_dir=".")
    processed = le._preprocess_html_for_measurement(f'<div class="slide">{html}</div>')

    # extract list segment
    inner = processed.split('data-list-levels', 1)[1]
    # split items by <br> boundaries
    import re
    parts = [seg for seg in re.split(r'<br[^>]*>', inner) if seg]
    # pull visible text between last '>' and next '<'
    items = []
    for part in parts:
        txt_start = part.rfind('>') + 1
        txt_end = part.find('<', txt_start)
        items.append(part[txt_start:txt_end].strip())

    assert items == expected 