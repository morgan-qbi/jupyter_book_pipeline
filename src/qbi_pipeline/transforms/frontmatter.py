"""
Phase 0a: frontmatter injection.

Ensures every page carries a title so MyST does not have to guess one.
"""

import yaml

FRONTMATTER_DELIMITER = '---'
FRONTMATTER_TERMINATORS = (FRONTMATTER_DELIMITER, '...')


def format_title_line(title):
    """
    Render `title: <value>` as valid YAML.

    Delegates quoting and escaping to PyYAML rather than hand-rolling it, so
    titles containing colons, apostrophes, or both are emitted correctly.
    `width` is raised to stop the emitter line-wrapping long titles.
    """
    return yaml.safe_dump(
        {'title': title},
        default_flow_style=False,
        allow_unicode=True,
        width=4096,
    ).strip()


def find_frontmatter(content):
    """
    Locate an existing YAML frontmatter block.

    Returns (body, insert_at), where `body` is the YAML text between the
    delimiters and `insert_at` is the offset just past the opening delimiter
    line -- the correct splice point for a new key.

    Returns (None, None) when there is no usable frontmatter: either the
    content does not open with a bare `---` line, or that line is never closed.
    A `---` followed by text on the same line is a horizontal rule, not a
    delimiter, and is treated as body content.
    """
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None, None

    for i, line in enumerate(lines[1:], start=1):
        if line.strip() in FRONTMATTER_TERMINATORS:
            return ''.join(lines[1:i]), len(lines[0])

    return None, None


def has_title(frontmatter_body):
    """
    True if the frontmatter already defines a top-level `title` key.

    Parses rather than substring-matching, so keys like `subtitle:` are not
    mistaken for an existing title.
    """
    try:
        parsed = yaml.safe_load(frontmatter_body)
    except yaml.YAMLError:
        # Malformed YAML: fall back to a conservative textual check so we never
        # clobber something that may already be a title.
        return 'title:' in frontmatter_body

    return isinstance(parsed, dict) and 'title' in parsed


def inject_frontmatter(content, title):
    """Add MyST frontmatter with a title, preserving any existing frontmatter"""
    body, insert_at = find_frontmatter(content)

    if body is None:
        return (
            f'{FRONTMATTER_DELIMITER}\n'
            f'{format_title_line(title)}\n'
            f'{FRONTMATTER_DELIMITER}\n\n'
            f'{content}'
        )

    if has_title(body):
        return content

    # Splice the title in as the first key, after the opening delimiter.
    newline = '\r\n' if content[:insert_at].endswith('\r\n') else '\n'
    return content[:insert_at] + format_title_line(title) + newline + content[insert_at:]
