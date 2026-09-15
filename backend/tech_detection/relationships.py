# What a directly-detected technology implies about the stack, even
# though we never observed the implied technology's own fingerprints.
# This is a separate knowledge layer from fingerprints.py: fingerprints
# describe what we can directly OBSERVE; this describes what a detection
# IMPLIES. Keep it deliberately small — only add a relationship once it's
# genuinely near-certain (Next.js is built ON React, not just commonly
# paired with it), not a loose correlation.

RELATIONSHIPS = {
    "Next.js": ["React"],
}
