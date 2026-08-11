"""
Vault hygiene checks.

Each check scans a vault and returns a list of issues. They are pure functions
over an already-filtered file list, so they never decide what is in scope --
that is policy.py's job, and it is why confidential folders no longer reach an
audit report.
"""

import re
from pathlib import Path

from ..policy import (
    is_excluded_name,
    iter_vault_dirs,
    iter_vault_files,
)
from ..staging import is_valid_notebook
from ..transforms.links import slugify_heading

# =============================================================================
# CONFIGURATION
# =============================================================================
# Exclusion rules live in policy.py. This module previously kept its own copy
# that omitted the confidential-folder convention entirely, so audit reports
# listed the filenames and link targets inside `5_*` folders and wrote them to
# disk as markdown (S-1).

PASTED_IMAGE_PATTERN = re.compile(r'^Pasted[\s_]image[\s_]\d+', re.IGNORECASE)
SCREENSHOT_PATTERN = re.compile(r'^Screenshot[\s_]\d+', re.IGNORECASE)
GENERIC_NAME_PATTERN = re.compile(r'^(Untitled|New[\s_]Note|Note[\s_]\d+|Document[\s_]\d+)\.md$', re.IGNORECASE)

# Notion import patterns
# Notion exports append a 32-char hex ID to filenames, e.g. "My Page abc123def456.md"
NOTION_HEX_SUFFIX = re.compile(r'\s[0-9a-f]{32}(?:\.\w+)?$', re.IGNORECASE)
# Notion CSV exports
NOTION_CSV_PATTERN = re.compile(r'_all\.csv$|_[0-9a-f]{32}\.csv$', re.IGNORECASE)
# Notion-style folder names with hex IDs
NOTION_FOLDER_PATTERN = re.compile(r'\s[0-9a-f]{32}$', re.IGNORECASE)

# Fenced code blocks. A protocol that documents markdown syntax will contain
# lines that look exactly like headings and links; they are not either.
FENCE_PATTERN = re.compile(
    r'^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$',
    re.MULTILINE | re.DOTALL,
)

# ATX headings, with optional trailing hashes: `## Setup ##`
HEADING_PATTERN = re.compile(r'^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$', re.MULTILINE)

# MyST explicit targets: `(my-label)=` on its own line above a heading
MYST_LABEL_PATTERN = re.compile(r'^\(([^)\n]+)\)=[ \t]*$', re.MULTILINE)

# `[[Page#Heading]]`, `[[Page#Heading|alias]]`, `[[#Heading]]`.
# (?<!!) so image embeds are not mistaken for page links.
WIKI_ANCHOR_PATTERN = re.compile(r'(?<!!)\[\[([^\]\n#|]*)#([^\]\n|]+)(?:\|[^\]\n]*)?\]\]')

# Standard markdown links carrying a fragment: `[text](page.md#anchor)`.
# Requiring a `#` and forbidding parentheses inside keeps this away from the
# balanced-paren problem that makes naive link regexes wrong.
MD_ANCHOR_PATTERN = re.compile(r'\]\(([^()\s#]*)#([^()\s]+)\)')

# Page links, as opposed to embeds: `[[Build Guide]]`, `[[Guide|the guide]]`.
WIKI_PAGE_PATTERN = re.compile(r'(?<!!)\[\[([^\]\n|#]+)(?:#[^\]\n|]*)?(?:\|[^\]\n]*)?\]\]')


# =============================================================================
# SCANNING FUNCTIONS
# =============================================================================

def iter_markdown_links(text):
    """
    Yield (bang, label, destination) for every markdown link and image.
    `destination` is None when the link is never closed.

    A regex cannot do this correctly. CommonMark allows balanced parentheses in
    a link destination, and this vault contains `Linear_ramp_B(5100).png` --
    with `\\(([^)]+)\\)` the destination truncates at the first `)` and the
    audit reports a broken reference to a file nobody ever wrote. That same
    pattern also runs past the end of an unterminated link, swallowing lines of
    unrelated text into the "filename" it then reports as missing.
    """
    for match in re.finditer(r'(!?)\[([^\]\n]*)\]\(', text):
        depth = 1
        i = match.end()
        destination = None

        while i < len(text):
            character = text[i]
            if character == '\\':
                i += 2
                continue
            if character == '\n':
                # A destination cannot span lines, so this link is unclosed.
                break
            if character == '(':
                depth += 1
            elif character == ')':
                depth -= 1
                if depth == 0:
                    destination = text[match.end():i]
                    break
            i += 1

        yield match.group(1), match.group(2), destination


def should_skip_dir(dir_path):
    """Check if a path should be excluded from scanning"""
    return any(is_excluded_name(part) for part in Path(dir_path).parts)


def get_all_files(vault_path):
    """
    Get all auditable files in the vault.

    Uses the shared traversal, so confidential folders and any subtree carrying
    a .qbi-exclude marker are skipped. Audit reports are written to disk and
    may be shared, so they must never name files the vault owner has marked
    as not-for-publication.
    """
    return [absolute for absolute, _ in iter_vault_files(vault_path)]


def get_all_dirs(vault_path):
    """Get all auditable directories in the vault"""
    return [absolute for absolute, _ in iter_vault_dirs(vault_path)]


# =============================================================================
# AUDIT CHECKS
# =============================================================================

def check_pasted_images(files, vault_path):
    """Find default-named pasted images that should be renamed"""
    issues = []
    for f in files:
        if PASTED_IMAGE_PATTERN.match(f.stem) or SCREENSHOT_PATTERN.match(f.stem):
            rel = f.relative_to(vault_path)
            issues.append({
                'file': str(rel),
                'suggestion': 'Rename to something descriptive (e.g., what the image shows)'
            })
    return issues


def check_generic_filenames(files, vault_path):
    """Find generic/default note names"""
    issues = []
    for f in files:
        if GENERIC_NAME_PATTERN.match(f.name):
            rel = f.relative_to(vault_path)
            issues.append({
                'file': str(rel),
                'suggestion': 'Rename to describe the content'
            })
    return issues


def check_broken_references(files, vault_path):
    """Find wikilinks and markdown image links that point to nonexistent files"""
    md_files = [f for f in files if f.suffix == '.md']
    all_filenames = {f.name: f for f in files}
    all_filenames_lower = {f.name.lower(): f for f in files}
    all_relative_paths = {str(f.relative_to(vault_path)).replace('\\', '/'): f for f in files}

    # Page links name a page without its extension, so they need their own
    # lookup: `[[Build Guide]]` for `1_eln/Build Guide.md`.
    page_keys = set()
    for f in files:
        rel = str(f.relative_to(vault_path)).replace('\\', '/')
        page_keys.update({_key(f.name), _key(f.stem), _key(rel), _key(rel.rsplit('.', 1)[0])})

    broken = []

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

        rel_md = str(md_file.relative_to(vault_path))

        # Find ![[...]] references
        for match in re.finditer(r'!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]', content):
            ref = match.group(1).strip()
            ref_filename = Path(ref).name

            if (ref_filename not in all_filenames and
                ref_filename.lower() not in all_filenames_lower and
                ref.replace('\\', '/') not in all_relative_paths):
                broken.append({
                    'source_file': rel_md,
                    'reference': ref,
                    'type': 'wikilink',
                    'suggestion': 'File not found in vault. Rename the reference or add the missing file.'
                })

        # Find [...](...) references, images and plain links alike
        for bang, label, url in iter_markdown_links(_strip_code_blocks(content)):
            if url is None:
                broken.append({
                    'source_file': rel_md,
                    'reference': f'{bang}[{label[:60]}](...',
                    'type': 'unterminated_link',
                    'suggestion': 'This link is missing its closing parenthesis, so the '
                                  'whole thing renders as literal text on the page.'
                })
                continue

            url = url.split('#', 1)[0].strip()
            if not url or url.startswith(('http://', 'https://', 'data:', 'mailto:', '//')):
                continue

            ref_filename = Path(url).name
            if (ref_filename not in all_filenames and
                ref_filename.lower() not in all_filenames_lower and
                url.replace('\\', '/') not in all_relative_paths):
                broken.append({
                    'source_file': rel_md,
                    'reference': url,
                    'type': 'markdown_image' if bang else 'markdown_link',
                    'suggestion': 'File not found in vault. Check the path or add the missing file.'
                })

        # Find [[Page]] links -- page-to-page links, not embeds. These are
        # published as real links now, so a link to a page that does not exist
        # is a 404 on the site rather than literal text on the page.
        for match in WIKI_PAGE_PATTERN.finditer(_strip_code_blocks(content)):
            ref = match.group(1).strip()
            if not ref:
                continue
            name = Path(ref).name
            if (_key(name) in page_keys or
                    _key(ref.replace('\\', '/')) in page_keys or
                    name in all_filenames or
                    name.lower() in all_filenames_lower):
                continue
            broken.append({
                'source_file': rel_md,
                'reference': f'[[{ref}]]',
                'type': 'wikilink',
                'suggestion': 'No page by that name in the vault. Check the spelling, '
                              'or the page may live in a folder that is not published.'
            })

    return broken


# =============================================================================
# HEADING ANCHORS
# =============================================================================

def _strip_code_blocks(content):
    """Blank out fenced code so example markdown is not read as real markup"""
    return FENCE_PATTERN.sub('', content)


def _key(text):
    """Normalize a page name for lookup.

    Obsidian is relaxed about spelling a link the way the file is named: a
    file `Build Guide.md` is linked as `[[Build Guide]]`, `[[build guide]]`, or
    -- once someone has copied a path out of the published site -- `Build_Guide`.
    All three mean the same page.
    """
    return text.lower().replace('%20', ' ').replace('_', ' ').strip()


def collect_anchors(content):
    """
    Every anchor a page offers: one per heading, plus MyST explicit targets.

    MyST disambiguates repeated headings by appending `-1`, `-2`, so those are
    included -- otherwise a legitimate link to the second `## Results` would be
    reported as broken.
    """
    text = _strip_code_blocks(content)
    anchors = set()
    seen = {}

    for match in HEADING_PATTERN.finditer(text):
        slug = slugify_heading(match.group(1))
        if not slug:
            continue
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f'{slug}-{count}')

    for match in MYST_LABEL_PATTERN.finditer(text):
        anchors.add(match.group(1).strip())

    return anchors


def check_broken_anchors(files, vault_path):
    """
    Find links to a heading that does not exist on the target page.

    A link like `[[Protocol#6. Degauss the shield]]` survives a rename or a
    renumbering of the heading silently: the link still points at a real page,
    so the broken-reference check passes, and the reader lands at the top of
    the page instead of the section. Numbered protocol headings get renumbered
    often, which is exactly when this happens.
    """
    md_files = [f for f in files if f.suffix == '.md']

    contents = {}
    for f in md_files:
        try:
            contents[f] = f.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

    rel_of = {f: str(f.relative_to(vault_path)).replace('\\', '/') for f in contents}
    anchors = {rel_of[f]: collect_anchors(text) for f, text in contents.items()}

    # A page can be addressed by name, by stem, or by path from the vault root.
    pages = {}
    for f, rel in rel_of.items():
        for form in (f.name, f.stem, rel, rel[:-3]):
            pages.setdefault(_key(form), rel)

    issues = []

    def report(source, reference, target, heading):
        issues.append({
            'source_file': source,
            'reference': reference,
            'type': 'anchor',
            'suggestion': f'No heading matching "{heading}" in `{target}`. '
                          f'The link resolves to the page but lands at the top of it.'
        })

    for f, content in contents.items():
        source = rel_of[f]
        text = _strip_code_blocks(content)

        for match in WIKI_ANCHOR_PATTERN.finditer(text):
            page, heading = match.group(1).strip(), match.group(2).strip()
            if heading.startswith('^'):
                continue  # a block reference, not a heading
            target = source if not page else pages.get(_key(page))
            if target is None or target not in anchors:
                continue  # a missing page is the broken-reference check's business
            if slugify_heading(heading) not in anchors[target]:
                report(source, f'[[{page}#{heading}]]', target, heading)

        for match in MD_ANCHOR_PATTERN.finditer(text):
            url, fragment = match.group(1).strip(), match.group(2).strip()
            if url.startswith(('http', 'data:', 'mailto:', '//')):
                continue
            if url and not url.lower().endswith('.md'):
                continue
            target = source if not url else pages.get(_key(Path(url).name))
            if target is None or target not in anchors:
                continue
            if fragment not in anchors[target]:
                report(source, f'{url}#{fragment}', target, fragment)

    return issues


def check_image_linebreaks(files, vault_path):
    """Find images that are inline (text immediately before ![[) instead of block"""
    md_files = [f for f in files if f.suffix == '.md']
    issues = []

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

        rel_md = str(md_file.relative_to(vault_path))

        # Find cases where non-whitespace immediately precedes an image
        inline_matches = re.findall(r'(\S)(\!\[\[)', content)
        if inline_matches:
            issues.append({
                'file': rel_md,
                'count': len(inline_matches),
                'suggestion': 'Add a blank line before images so they render as blocks, not inline.'
            })

        # Also check standard markdown images
        inline_md_matches = re.findall(r'(\S)(!\[)', content)
        if inline_md_matches:
            real_count = len(inline_md_matches) - len(inline_matches)
            if real_count > 0:
                issues.append({
                    'file': rel_md,
                    'count': real_count,
                    'suggestion': 'Add a blank line before markdown images so they render as blocks.'
                })

    return issues


def check_empty_files(files, vault_path):
    """Find empty or near-empty markdown files"""
    issues = []
    for f in files:
        if f.suffix == '.md':
            try:
                content = f.read_text(encoding='utf-8', errors='ignore').strip()
                if len(content) < 10:  # basically empty
                    rel = f.relative_to(vault_path)
                    issues.append({
                        'file': str(rel),
                        'suggestion': 'This file is empty or nearly empty. Add content or delete it.'
                    })
            except Exception:
                continue
    return issues


def check_invalid_notebooks(files, vault_path):
    """
    Find notebooks the build cannot publish.

    The build already skips these, but it says so in the cron log, which no
    researcher reads. The notebook is simply absent from the site and nobody
    is told. A file containing `{}` is valid JSON and passes any JSON check,
    yet has no `cells` and no `nbformat`, and used to fail the entire build.
    """
    issues = []
    for f in files:
        if f.suffix.lower() != '.ipynb':
            continue
        if is_valid_notebook(f):
            continue
        issues.append({
            'file': str(f.relative_to(vault_path)),
            'suggestion': 'This notebook is empty or malformed, so it is skipped '
                          'and never appears on the site. Re-save it from Jupyter, '
                          'or delete it if it was created by accident.'
        })
    return issues


def check_notion_imports(files, vault_path):
    """Find files and folders that look like raw Notion exports"""
    issues = []
    seen_files = set()

    # Check files with Notion's 32-char hex suffix
    for f in files:
        if NOTION_HEX_SUFFIX.search(f.stem):
            rel = f.relative_to(vault_path)
            rel_str = str(rel)
            if rel_str not in seen_files:
                seen_files.add(rel_str)
                issues.append({
                    'file': rel_str,
                    'suggestion': 'This looks like a Notion import (hex ID in filename). Please consolidate into your primary lab notebook files and remove the Notion export artifacts.'
                })

        # Notion CSV exports
        if NOTION_CSV_PATTERN.search(f.name):
            rel = f.relative_to(vault_path)
            rel_str = str(rel)
            if rel_str not in seen_files:
                seen_files.add(rel_str)
                issues.append({
                    'file': rel_str,
                    'suggestion': 'This looks like a Notion CSV export. Please consolidate relevant data into your primary lab notebook files.'
                })

    # Check for Notion-style folder names with hex IDs
    dirs = get_all_dirs(vault_path)
    for d in dirs:
        if NOTION_FOLDER_PATTERN.search(d.name):
            rel = d.relative_to(vault_path)
            issues.append({
                'file': str(rel) + '/',
                'suggestion': 'This folder looks like a Notion import (hex ID in name). Please consolidate its contents into your primary lab notebook and remove the Notion export folder.'
            })

    return issues
