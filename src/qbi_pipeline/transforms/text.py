"""
Phases 0b and 3: block-level image spacing, and text cleanup for MyST.
"""

import re

# Fenced blocks (``` or ~~~, any length, opening and closing must match) and
# inline code spans. Matched together so a single pass can walk the document and
# hand back the code regions untouched.
CODE_SPAN_PATTERN = re.compile(
    r'(?P<fenced>^[ \t]*(?P<fence>`{3,}|~{3,})[^\n]*\n.*?^[ \t]*(?P=fence)[ \t]*$)'
    r'|(?P<inline>`+[^`\n]*`+)',
    re.MULTILINE | re.DOTALL,
)


def apply_outside_code(content, transform):
    """
    Apply `transform` to prose only, leaving code spans byte-for-byte intact.

    Text substitutions that are right for prose are wrong for code: escaping
    `@` turns a Python decorator into `\\@dataclass`, and normalizing dashes
    silently edits string literals. Anything rewriting document text has to
    know where the code is.
    """
    out = []
    position = 0

    for match in CODE_SPAN_PATTERN.finditer(content):
        out.append(transform(content[position:match.start()]))
        out.append(match.group(0))
        position = match.end()

    out.append(transform(content[position:]))
    return ''.join(out)


def _split_inline_images(text):
    """Push images that share a line with text onto a line of their own"""
    # Anything other than whitespace before an image on the same line makes
    # MyST render it inline -- a thumbnail in the flow of the paragraph rather
    # than a figure. Allow spaces between the text and the image: requiring the
    # text to sit flush against the embed missed the common
    # `Analysed the run. ![[plot.png]]` case entirely.
    #
    # `[` is excluded from the preceding character on purpose. In
    # `[![badge](img.svg)](https://example.org)` the image is the *content* of
    # a link, and splitting it would tear the link syntax apart. Those images
    # are meant to be inline.
    lines = []
    for line in text.split('\n'):
        # A table cell image is deliberately inline; splitting breaks the table.
        if line.lstrip().startswith('|'):
            lines.append(line)
        else:
            lines.append(re.sub(r'([^\s\[])[ \t]*(!\[)', r'\1\n\n\2', line))
    return '\n'.join(lines)


def ensure_image_linebreaks(content):
    """Ensure images render as blocks, not inline"""
    # Code blocks are left alone: an example that shows markdown syntax should
    # keep the layout it was written with.
    content = apply_outside_code(content, _split_inline_images)

    # Ensure a blank line before an image that is already on its own line
    # (e.g. indented inside a list), or it still gets absorbed into the
    # preceding paragraph.
    content = re.sub(r'(?<!\n)\n([ \t]*\!\[\[)', r'\n\n\1', content)
    content = re.sub(r'(?<!\n)\n([ \t]*!\[)', r'\n\n\1', content)
    return content


def _fix_prose(text):
    """Text cleanup for a single run of prose"""
    text = text.replace('–', '-')  # en-dash
    text = text.replace('—', '-')  # em-dash
    text = text.replace('−', '-')  # minus sign

    # MyST reads a bare `@` as the start of a citation reference, so in prose
    # it has to be escaped to render literally. Inside code it must not be.
    text = text.replace('@', '\\@')
    return text


def fix_text_issues(content):
    """Fix text formatting issues that break MyST, skipping code (S-9)"""
    return apply_outside_code(content, _fix_prose)
