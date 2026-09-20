# Regression suite for the cross-page shared-content detector itself --
# signature(), find_shared_containers(), remove_shared_containers(). Fully
# offline, works on hand-built HTML fixtures. pipeline.py's own tests
# (test_discover_and_extract.py::TestSharedContentWiring) cover that this
# module is wired in correctly; this file covers the algorithm's own
# behavior in detail.

from bs4 import BeautifulSoup

from website_processing.shared_content import (
    MIN_OCCURRENCES,
    find_shared_containers,
    remove_shared_containers,
    signature,
)


def body(inner_html: str):
    return BeautifulSoup(f"<html><body>{inner_html}</body></html>", "html.parser").body


NAV = (
    '<nav><a href="https://example.com/">Home</a>'
    '<a href="https://example.com/docs">Docs</a>'
    '<a href="https://example.com/pricing">Pricing</a>'
    '<a href="https://example.com/blog">Blog</a></nav>'
)


SMALL_NAV = '<nav><a href="https://example.com/">Home</a><a href="https://example.com/docs">Docs</a></nav>'


class TestSignature:
    def test_signature_is_the_set_of_link_text_and_href_pairs(self):
        tag = body(SMALL_NAV).nav
        assert signature(tag) == frozenset(
            {("Home", "https://example.com/"), ("Docs", "https://example.com/docs")}
        )

    def test_links_outside_the_container_are_not_included(self):
        html = f'<div>{SMALL_NAV}<a href="https://example.com/outside">Outside</a></div>'
        tag = body(html).nav
        assert ("Outside", "https://example.com/outside") not in signature(tag)

    def test_a_tags_with_no_href_are_ignored(self):
        tag = body('<nav><a>No href</a><a href="https://example.com/x">X</a></nav>').nav
        assert signature(tag) == frozenset({("X", "https://example.com/x")})


class TestFindSharedContainers:
    def test_returns_nothing_for_fewer_than_two_pages(self):
        assert find_shared_containers([body(NAV)]) == []
        assert find_shared_containers([]) == []

    def test_detects_an_exact_match_repeated_across_pages(self):
        bodies = [body(f"{NAV}<p>Page {i}</p>") for i in range(3)]
        found = find_shared_containers(bodies)

        assert len(found) == 1
        assert signature(found[0]) == signature(body(NAV).nav)

    def test_detects_a_near_match_with_one_extra_page_specific_link(self):
        # The real-world case this exists for (verified against
        # lakshx.in): the same nav, but one page's copy also carries an
        # extra, page-specific link (e.g. a self-referential page title)
        # mixed into the same container.
        page_a = body(NAV + "<p>A</p>")
        page_b_nav = NAV.replace("</nav>", '<a href="https://example.com/b">Page B Title</a></nav>')
        page_b = body(page_b_nav + "<p>B</p>")

        found = find_shared_containers([page_a, page_b])

        assert len(found) == 1

    def test_does_not_match_containers_below_the_similarity_threshold(self):
        page_a = body(NAV)
        page_b = body('<nav><a href="https://example.com/totally">Unrelated</a></nav>')

        assert find_shared_containers([page_a, page_b]) == []

    def test_a_candidate_with_too_few_links_is_never_fingerprinted(self):
        # A single-link "footer" repeated everywhere still isn't
        # considered -- MIN_LINKS_TO_CONSIDER guards against a trivial
        # one-link container spuriously "matching" itself.
        one_link_footer = '<footer><a href="https://example.com/x">X</a></footer>'
        bodies = [body(one_link_footer) for _ in range(3)]

        assert find_shared_containers(bodies) == []

    def test_same_container_appearing_twice_on_one_page_counts_once(self):
        # A nested <nav> inside an <aside> with the same links (the real
        # shape seen on lakshx.in's docs sidebar) must not inflate the
        # cross-page count just because it matched twice on one page.
        nested = f'<aside>{NAV}</aside>'
        bodies = [body(nested), body("<p>No nav here.</p>")]

        # Only ONE page actually has it -- below MIN_OCCURRENCES (2) even
        # though it matched twice within that single page.
        assert find_shared_containers(bodies) == []

    def test_genuinely_unique_per_page_content_is_never_reported(self):
        bodies = [
            body('<nav><a href="https://example.com/a1">A1</a><a href="https://example.com/a2">A2</a></nav>'),
            body('<nav><a href="https://example.com/b1">B1</a><a href="https://example.com/b2">B2</a></nav>'),
        ]

        assert find_shared_containers(bodies) == []

    def test_a_larger_crawl_needs_more_than_the_bare_minimum_occurrences(self):
        # MIN_OCCURRENCES alone would let 2 matches through even in a
        # 100-page crawl -- SHARED_CONTENT_THRESHOLD's percentage floor is
        # what actually kicks in for bigger crawls, guarding against a
        # coincidental 2-page match being treated as site-wide chrome.
        matching = [body(f"{NAV}<p>{i}</p>") for i in range(MIN_OCCURRENCES)]
        unique = [
            body(f'<nav><a href="https://example.com/u{i}">U{i}</a><a href="https://example.com/v{i}">V{i}</a></nav>')
            for i in range(30)
        ]

        assert find_shared_containers(matching + unique) == []


class TestRemoveSharedContainers:
    def test_removes_a_container_matching_a_shared_signature(self):
        page = body(f"{NAV}<p>Real content.</p>")
        shared = [signature(body(NAV).nav)]

        remove_shared_containers(page, shared)

        assert page.find("nav") is None
        assert "Real content." in page.get_text()

    def test_removes_a_near_match_within_the_similarity_threshold(self):
        page_nav = NAV.replace("</nav>", '<a href="https://example.com/x">Page-specific</a></nav>')
        page = body(page_nav + "<p>Real content.</p>")
        shared = [signature(body(NAV).nav)]

        remove_shared_containers(page, shared)

        assert page.find("nav") is None
        assert "Real content." in page.get_text()

    def test_leaves_a_container_below_the_similarity_threshold_untouched(self):
        page = body('<nav><a href="https://example.com/totally">Unrelated</a><a href="https://example.com/other">Other</a></nav>')
        shared = [signature(body(NAV).nav)]

        remove_shared_containers(page, shared)

        assert page.find("nav") is not None

    def test_a_matched_parent_removing_a_nested_matched_child_does_not_error(self):
        # decompose()-ing the outer container also detaches its nested
        # child from the tree; a later entry for that same child (found in
        # the same find_all() pass) must be skipped, not re-decomposed.
        page = body(f'<aside>{NAV}</aside><p>Real content.</p>')
        shared = [signature(body(NAV).nav)]

        remove_shared_containers(page, shared)  # must not raise

        assert page.find("nav") is None
        assert page.find("aside") is None
        assert "Real content." in page.get_text()

    def test_non_candidate_tags_are_never_touched_regardless_of_content(self):
        # A <div> styled as a sidebar, with links directly inside it and
        # no real <nav>/<aside>/<header>/<footer> wrapper at all -- a
        # known, honest scope limitation (see shared_content.py's own
        # module comment), not something this guards against.
        div_html = '<div class="sidebar"><a href="https://example.com/">Home</a><a href="https://example.com/docs">Docs</a></div>'
        page = body(div_html)
        shared = [signature(body(div_html).div)]

        remove_shared_containers(page, shared)

        assert page.find("div") is not None
        assert page.find("a") is not None
