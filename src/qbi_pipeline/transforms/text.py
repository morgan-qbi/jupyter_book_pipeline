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


def ensure_image_linebreaks(content):
    """Ensure images render as blocks, not inline"""
    # If there's text immediately before ![[, split it to a new line
    content = re.sub(r'(\S)(\!\[\[)', r'\1\n\n\2', content)
    # Ensure blank line before ![[ even if already on own line (e.g. inside lists)
    content = re.sub(r'(?<!\n)\n([ \t]*\!\[\[)', r'\n\n\1', content)
    # Same for standard markdown images
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
