# Regression suite for inference.py. Fully synthetic — operates on plain
# direct-technology dicts, no fetching or detection needed.

from tech_detection.inference import add_inferred_technologies


def direct(technology, confidence="strong"):
    return {
        "technology": technology,
        "category": "whatever",
        "confidence_score": 100,
        "confidence": confidence,
        "evidence": ["fake"],
        "browser_enrichable": False,
    }


class TestAddInferredTechnologies:
    def test_direct_detections_get_tagged_and_keep_their_fields(self):
        result = add_inferred_technologies([direct("Next.js")])
        next_js = next(t for t in result if t["technology"] == "Next.js")

        assert next_js["detection_type"] == "direct"
        assert next_js["confidence"] == "strong"
        assert next_js["evidence"] == ["fake"]

    def test_relationship_adds_inferred_entry(self):
        result = add_inferred_technologies([direct("Next.js")])
        react = next(t for t in result if t["technology"] == "React")

        assert react["detection_type"] == "inferred"
        assert react["inferred_from"] == "Next.js"

    def test_inferred_entry_has_no_fabricated_evidence(self):
        # The core rule this whole layer exists to enforce: an inferred
        # technology must never carry fingerprint evidence that belongs
        # to what actually implied it.
        result = add_inferred_technologies([direct("Next.js")])
        react = next(t for t in result if t["technology"] == "React")

        assert set(react.keys()) == {"technology", "detection_type", "inferred_from"}

    def test_already_directly_detected_is_not_also_inferred(self):
        # If React ever gets its own real fingerprint hit alongside
        # Next.js, it must stay a single direct entry, not be duplicated.
        result = add_inferred_technologies([direct("Next.js"), direct("React")])
        react_entries = [t for t in result if t["technology"] == "React"]

        assert len(react_entries) == 1
        assert react_entries[0]["detection_type"] == "direct"

    def test_no_relationship_defined_adds_nothing(self):
        result = add_inferred_technologies([direct("Cloudflare")])
        assert len(result) == 1
        assert result[0]["technology"] == "Cloudflare"

    def test_empty_input_returns_empty(self):
        assert add_inferred_technologies([]) == []

    def test_works_regardless_of_confidence_level(self):
        # Inference triggers off presence in direct_technologies, not
        # confidence tier -- even a "possible" Next.js still implies React.
        result = add_inferred_technologies([direct("Next.js", confidence="possible")])
        assert any(t["technology"] == "React" for t in result)
