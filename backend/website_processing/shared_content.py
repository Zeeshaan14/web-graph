# Detects content repeated across most pages of the SAME crawl (a site's
# nav bar, sidebar, footer, ...) so it can be pulled out once instead of
# duplicated on every single page -- pure noise for a downstream RAG
# pipeline, which is what this exists for.
#
# Deliberately NOT the same idea as trafilatura's old per-page density
# scoring (removed earlier in this project for silently guessing wrong).
# This never guesses at a single page in isolation -- it only ever acts on
# something OBSERVED to repeat across several of THIS crawl's own pages,
# which is evidence, not a heuristic. A page with no siblings to compare
# against (a 1-page crawl) is never touched by this at all.

# Landmark tags worth fingerprinting -- deliberately narrow (real semantic
# HTML5 landmarks) rather than a link-density guess over arbitrary <div>s,
# which is exactly the kind of guessing this project moved away from. A
# site that marks up its sidebar as a bare <div> won't be caught here; see
# README.md for this as a known, honest limitation rather than something
# worked around with a fragile heuristic.
CANDIDATE_TAGS = ("nav", "aside", "header", "footer")

# A crawl needs at least this many successfully-extracted pages before
# cross-page comparison means anything at all -- on a single page, "appears
# on 100% of pages" is true of everything, which would strip real content.
MIN_PAGES_FOR_DEDUP = 2

# A candidate must repeat on at least this many DIFFERENT pages, verbatim
# or near-verbatim, to count as shared site chrome. A real site (verified
# against lakshx.in) commonly runs several page TEMPLATES at once --
# marketing pages, docs pages, legal pages each compose their header/nav
# differently -- so no single container is likely to hit a high percentage
# of the WHOLE crawl even when it's genuinely template chrome within its
# own section. An absolute minimum, not a percentage, is what actually
# holds up: 2 independent pages showing the identical nav is already good
# evidence, regardless of how many other, differently-templated pages
# happen to be in the same crawl.
MIN_OCCURRENCES = 2

# ...but purely absolute has its own failure mode at the other end -- 2
# matching pages out of a 200-page crawl is *not* good evidence, it's
# coincidence. This floor only matters for larger crawls; MIN_OCCURRENCES
# is what actually does the work for typical crawl sizes.
SHARED_CONTENT_THRESHOLD = 0.1

# A candidate needs at least this many links to be fingerprinted at all --
# guards against a plain, linkless one-line footer ("Copyright 2024 Example
# Site") spuriously "matching" every other equally-linkless footer just
# because they're both empty.
MIN_LINKS_TO_CONSIDER = 2

# How much two containers' link sets need to overlap to count as "the same"
# container. Real nav/sidebar markup is rarely byte-for-byte identical
# across pages even when it's the same template -- the current page's own
# entry is often highlighted, or wrapped with an extra page-specific link
# (a self-referential page title, a "next article" link). Exact-set
# equality (verified against lakshx.in) misses this; overlap doesn't.
SIMILARITY_THRESHOLD = 0.75


def signature(container) -> frozenset:
    """A container's identity for cross-page comparison: the set of (link
    text, href) pairs inside it -- not its raw HTML or text. This is what
    lets a sidebar match itself across pages even though it's rarely
    byte-identical (the current page's own entry is usually highlighted
    with a different class/aria-current) -- two instances with mostly the
    same links to the same places are the same nav, whichever one is
    highlighted right now, or whatever one extra page-specific link sits
    alongside them."""
    return frozenset(
        (a.get_text(" ", strip=True), a["href"])
        for a in container.find_all("a", href=True)
    )


def _similarity(a: frozenset, b: frozenset) -> float:
    """Jaccard similarity -- how much of the combined link set two
    containers share. 1.0 for byte-identical link sets, 0.0 for no overlap
    at all."""
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_shared_containers(bodies: list) -> list:
    """bodies: one parsed <body> Tag per successfully-extracted page in the
    crawl (see content_extraction.fetch_and_prepare()). Groups candidate
    containers across pages by similarity (not exact-match -- see
    SIMILARITY_THRESHOLD), then returns one representative Tag per group
    that repeated on enough distinct pages to count as shared chrome
    rather than a genuine per-page coincidence."""
    if len(bodies) < MIN_PAGES_FOR_DEDUP:
        return []

    # Each group: the first-seen signature (used as the similarity
    # reference for later comparisons), its representative Tag, and the
    # set of page indices it's been seen on.
    groups: list[dict] = []

    for page_index, body in enumerate(bodies):
        # A group counts once per PAGE even if a matching container shape
        # appears twice on that one page -- that says nothing about
        # cross-page repetition.
        matched_this_page: set[int] = set()

        for tag in body.find_all(CANDIDATE_TAGS):
            sig = signature(tag)

            if len(sig) < MIN_LINKS_TO_CONSIDER:
                continue

            group_index = next(
                (i for i, g in enumerate(groups) if _similarity(sig, g["signature"]) >= SIMILARITY_THRESHOLD),
                None,
            )

            if group_index is None:
                groups.append({"signature": sig, "tag": tag, "pages": set()})
                group_index = len(groups) - 1

            if group_index not in matched_this_page:
                groups[group_index]["pages"].add(page_index)
                matched_this_page.add(group_index)

    threshold_count = max(MIN_OCCURRENCES, SHARED_CONTENT_THRESHOLD * len(bodies))

    return [g["tag"] for g in groups if len(g["pages"]) >= threshold_count]


def remove_shared_containers(body, shared_signatures: list) -> None:
    """Strips every container in `body` similar enough to any signature in
    `shared_signatures` (see SIMILARITY_THRESHOLD), in place. Guards
    against a container whose PARENT was already removed earlier in the
    same find_all() pass (e.g. a matched <header> nested inside a matched
    <nav>) -- decompose() detaches descendants along with their ancestor,
    so a later entry for that same descendant is already gone and must be
    skipped rather than decomposed again."""
    for tag in body.find_all(CANDIDATE_TAGS):
        if tag.parent is None:
            continue

        sig = signature(tag)

        if len(sig) < MIN_LINKS_TO_CONSIDER:
            continue

        if any(_similarity(sig, shared) >= SIMILARITY_THRESHOLD for shared in shared_signatures):
            tag.decompose()
