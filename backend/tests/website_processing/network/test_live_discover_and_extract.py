# Real end-to-end check of the full crawl-then-extract-then-dedup
# pipeline against a real site. NOT run by default (pyproject.toml's
# addopts excludes -m network) -- run explicitly with:
#   uv run pytest -m network
#
# lakshx.in specifically: its docs/terms/privacy pages share a consistent
# header+nav (verified directly during development), which is exactly the
# real-world shape find_shared_containers()/remove_shared_containers() are
# for -- a synthetic fixture proves the algorithm works, this proves it
# still works against real, messy, inconsistently-templated HTML.

import pytest

from website_processing.pipeline import discover_and_extract

pytestmark = pytest.mark.network


def test_shared_nav_is_deduped_across_lakshx_in_pages():
    result = discover_and_extract("https://lakshx.in/", max_pages=5)

    assert result["status"] == "success"

    successful_pages = [page for page in result["pages"] if page["status"] == "success"]
    assert len(successful_pages) >= 2

    # Real, per-page content must still be there.
    assert any("Terms of Service" in page["content_markdown"] for page in successful_pages)

    # Something was found common enough across pages to report once,
    # rather than once per page.
    assert result["shared_content_markdown"]
