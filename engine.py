# Generic rule evaluator: knows how to check "exists" / "contains" / "equals"
# against a context and how to turn matched rule weights into a confidence
# score, but knows nothing about Cloudflare, Next.js, WordPress, etc.

from html_signals import extract_html_signals

MIN_DETECTION_SCORE = 40


def confidence_label(score):
    if score >= 80:
        return "strong"
    if score >= 60:
        return "likely"
    if score >= 40:
        return "possible"
    return "weak"


def make_context(headers, html, cookies=None):
    signals = extract_html_signals(html)

    return {
        "headers": {k.lower(): v for k, v in headers.items()},
        "cookies": dict(cookies or {}),
        "html": html,
        "scripts": signals["scripts"],
        "stylesheets": signals["stylesheets"],
        "meta": signals["meta"],
    }


def build_context(response):
    return make_context(response.headers, response.text, response.cookies)


def _get_meta_content(context, key):
    key = key.lower()

    for meta in context.get("meta", []):
        name = (meta.get("name") or "").lower()
        prop = (meta.get("property") or "").lower()

        if key in (name, prop):
            return meta.get("content")

    return None


def _get_value(rule, context):
    source = rule["source"]

    if source == "header":
        return context["headers"].get(rule["key"].lower())
    if source == "cookie":
        return context["cookies"].get(rule["key"])
    if source == "html":
        return context["html"]
    if source == "script_src":
        return context.get("scripts", [])
    if source == "stylesheet_href":
        return context.get("stylesheets", [])
    if source == "meta":
        return _get_meta_content(context, rule["key"])

    raise ValueError(f"Unknown rule source: {source!r}")


def _describe(rule):
    source = rule["source"]

    if source == "html":
        return f"HTML {rule['operator']} '{rule['value']}'"
    if source == "script_src":
        return f"script_src {rule['operator']} '{rule['value']}'"
    if source == "stylesheet_href":
        return f"stylesheet_href {rule['operator']} '{rule['value']}'"
    if source == "meta":
        if rule["operator"] == "exists":
            return f"meta '{rule['key']}' exists"
        return f"meta '{rule['key']}' {rule['operator']} '{rule['value']}'"
    if rule["operator"] == "exists":
        return f"{source} '{rule['key']}' exists"
    return f"{source} '{rule['key']}' {rule['operator']} '{rule['value']}'"


def evaluate_rule(rule, context):
    value = _get_value(rule, context)
    operator = rule["operator"]

    if operator == "exists":
        if isinstance(value, list):
            return len(value) > 0
        return value is not None

    if isinstance(value, list):
        if operator == "contains":
            return any(rule["value"].lower() in str(item).lower() for item in value)
        if operator == "equals":
            return any(str(item).lower() == rule["value"].lower() for item in value)
        raise ValueError(f"Unknown rule operator: {operator!r}")

    if value is None:
        return False

    if operator == "contains":
        return rule["value"].lower() in str(value).lower()

    if operator == "equals":
        return str(value).lower() == rule["value"].lower()

    raise ValueError(f"Unknown rule operator: {operator!r}")


def evaluate_group(group, context):
    """Returns (satisfied, matched_rules) for one rule group.

    "any" is OR: satisfied as soon as one rule matches.
    "all" is AND: satisfied only if every rule in the group matches —
    a partial match on an "all" group counts for nothing.
    """
    logic = group["logic"]
    matched_rules = [rule for rule in group["rules"] if evaluate_rule(rule, context)]

    if logic == "any":
        satisfied = len(matched_rules) > 0
    elif logic == "all":
        satisfied = len(matched_rules) == len(group["rules"])
    else:
        raise ValueError(f"Unknown group logic: {logic!r}")

    return satisfied, matched_rules if satisfied else []


def detect(fingerprints, context):
    detected = []

    for fingerprint in fingerprints:
        score = 0
        evidence = []

        for group in fingerprint["groups"]:
            satisfied, matched_rules = evaluate_group(group, context)

            if satisfied:
                score += group["weight"]
                joiner = " AND " if group["logic"] == "all" else " OR "
                descriptions = joiner.join(_describe(rule) for rule in matched_rules)
                evidence.append(f"[{group['logic']} +{group['weight']}] {descriptions}")

        score = min(score, 100)

        if score >= MIN_DETECTION_SCORE:
            detected.append({
                "technology": fingerprint["technology"],
                "category": fingerprint["category"],
                "confidence_score": score,
                "confidence": confidence_label(score),
                "evidence": evidence,
            })

    return detected
