# Generic rule evaluator: knows how to check "exists" / "contains" / "equals"
# against an evidence dict and how to turn matched rule weights into a
# confidence score, but knows nothing about Cloudflare, Next.js, WordPress,
# etc. — and, just as importantly, nothing about HTTP or Playwright either.
# It only ever sees the flat evidence shape evidence.py/browser.py build:
#
#   {headers, cookies, html, script_src, stylesheet_href, meta,
#    javascript_globals}
#
# javascript_globals only ever has entries once a browser pass has run —
# on plain HTTP evidence it's simply absent, so rules using it naturally
# never match until browser.py has contributed something.
#
# so a browser-enriched evidence dict is evaluated exactly the same way a
# plain HTTP one is.

from fingerprints import FINGERPRINTS

MIN_DETECTION_SCORE = 40


def confidence_label(score):
    if score >= 80:
        return "strong"
    if score >= 60:
        return "likely"
    if score >= 40:
        return "possible"
    return "weak"


def _get_meta_content(context, key):
    key = key.lower()

    for meta in context.get("meta", []):
        name = (meta.get("name") or "").lower()
        prop = (meta.get("property") or "").lower()

        if key in (name, prop):
            return meta.get("content")

    return None


def evaluate_condition(actual_value, operator, expected_value=None):
    """Checks one {field, operator, value} condition against one already-
    extracted field value (e.g. a single meta tag's "content")."""
    actual_value = actual_value or ""

    if operator == "exists":
        return bool(actual_value)

    if operator == "equals":
        return actual_value.lower() == (expected_value or "").lower()

    if operator == "contains":
        return (expected_value or "").lower() in actual_value.lower()

    return False


def evaluate_meta_rule(rule, meta_tags):
    """A meta rule with "conditions" matches if some SINGLE meta tag
    satisfies every condition at once — e.g. that tag's "name" equals
    "generator" AND its "content" contains "wordpress". This is different
    from checking each field independently across the whole tag list,
    because both conditions must be true of the same tag."""
    conditions = rule["conditions"]

    for meta in meta_tags:
        all_conditions_match = True

        for condition in conditions:
            field = condition["field"]
            operator = condition["operator"]
            expected_value = condition.get("value")

            actual_value = meta.get(field)

            if not evaluate_condition(actual_value, operator, expected_value):
                all_conditions_match = False
                break

        if all_conditions_match:
            return True

    return False


def _get_value(rule, context):
    source = rule["source"]

    if source == "header":
        return context["headers"].get(rule["key"].lower())
    if source == "cookie":
        return context["cookies"].get(rule["key"])
    if source == "html":
        return context["html"]
    if source == "script_src":
        return context.get("script_src", [])
    if source == "stylesheet_href":
        return context.get("stylesheet_href", [])
    if source == "javascript_globals":
        return context.get("javascript_globals", [])
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
    if source == "javascript_globals":
        return f"javascript_globals {rule['operator']} '{rule['value']}'"
    if source == "meta" and "conditions" in rule:
        parts = [
            f"{c['field']} {c['operator']} '{c.get('value', '')}'"
            for c in rule["conditions"]
        ]
        return "meta [" + " AND ".join(parts) + "]"
    if source == "meta":
        if rule["operator"] == "exists":
            return f"meta '{rule['key']}' exists"
        return f"meta '{rule['key']}' {rule['operator']} '{rule['value']}'"
    if rule["operator"] == "exists":
        return f"{source} '{rule['key']}' exists"
    return f"{source} '{rule['key']}' {rule['operator']} '{rule['value']}'"


def evaluate_rule(rule, context):
    if rule["source"] == "meta" and "conditions" in rule:
        return evaluate_meta_rule(rule, context.get("meta", []))

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


def detect_technologies(evidence):
    """Convenience entry point for orchestration code (main.py): runs the
    real fingerprint set against one evidence dict. detect() above stays
    the generic, fingerprint-set-agnostic form — test_matrix.py uses that
    one directly so it can test with its own synthetic fixtures."""
    return detect(FINGERPRINTS, evidence)
