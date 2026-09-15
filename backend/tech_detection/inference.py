# Derives technologies implied by what was directly detected, using
# relationships.py. Inference is knowledge about the ecosystem ("Next.js
# is built on React"), not observed evidence — an inferred technology
# never gets fingerprint evidence or a confidence score, only a note
# about which direct detection implied it. This stays a separate pass
# AFTER engine.py's direct rule evaluation is done — engine.py itself
# never sees or knows about relationships.py.

from .engine import detect_technologies as _detect_technologies
from .relationships import RELATIONSHIPS


def add_inferred_technologies(direct_technologies):
    """Takes engine.detect_technologies()'s raw output (plain direct
    detections) and returns the final combined list: every direct
    detection tagged detection_type="direct" (unchanged otherwise —
    same confidence/evidence it already had), plus whatever those imply,
    tagged detection_type="inferred" with no evidence/confidence of its
    own. A technology that was ALSO directly detected is never duplicated
    as an inferred entry."""
    direct_names = {tech["technology"] for tech in direct_technologies}

    result = [
        {**tech, "detection_type": "direct"}
        for tech in direct_technologies
    ]

    seen_inferred = set()

    for tech in direct_technologies:
        for implied_name in RELATIONSHIPS.get(tech["technology"], []):
            if implied_name in direct_names or implied_name in seen_inferred:
                continue

            result.append({
                "technology": implied_name,
                "detection_type": "inferred",
                "inferred_from": tech["technology"],
            })
            seen_inferred.add(implied_name)

    return result


def detect_technologies_with_inference(evidence):
    """Convenience entry point: direct detection + the inference pass,
    in one call — mirrors how engine.detect_technologies() wraps
    engine.detect() with the real fingerprint set."""
    direct_technologies = _detect_technologies(evidence)
    return add_inferred_technologies(direct_technologies)
