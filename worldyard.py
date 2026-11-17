#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Worldyard (formerly openunit) -- reference implementation (engine)

A deterministic, publicly verifiable, population-weighted *unit of account*.
It does not issue money and it does not settle payments. It only *measures*:
given the same pinned inputs, anyone recomputes the same value and the same
hashes, byte for byte.

Method versions
  v0     one person, one vote          weight_i = pop_i / sum(pop)
  v0.1   same method, real pinned data  (UN population + ECB reference FX)
  v0.2   PPP-aware                       see SPEC.md sections 2 and 7
  v0.3   input domain: negative populations rejected
  v0.4   inputs resolved under SPEC.md "Data states and fallbacks"; specs
         carry the method name "worldyard" (earlier ones "openunit")

Mechanism (see SPEC.md):
  - one person, one vote : weight_i proportional to population_i (optionally
                           x a per-entry `weight_multiplier`, default 1)
  - frequency separation : weights pinned at a low-frequency vintage; value
                           read from a separate (e.g. daily, or PPP) FX leg
  - vintage pinning      : fixed currency amounts -- the population version of
                           the SDR fixed-basket method

Determinism properties:
  - stdlib only (json, hashlib, decimal)
  - exact arithmetic with decimal.Decimal (prec=50, ROUND_HALF_EVEN) inside an
    isolated, fully specified localcontext (nothing is inherited from the
    caller's decimal context); numbers parsed from strings, never from floats
  - never reads the wall clock (no datetime / time)
  - SHA-256 over canonical JSON for input_digest and artifact_hash

Backward compatibility:
  A spec whose basket entries carry no `weight_multiplier` produces output that
  is byte-for-byte identical to openunit v0 (the extra weighting fields are
  emitted only when at least one multiplier is present).
  The project was renamed from openunit to Worldyard. The artifact's `method`
  is copied from the spec: "openunit" (every spec written before the rename,
  and the default when a spec has none) or "worldyard"; any other name is
  rejected. So every artifact built before the rename rebuilds byte for byte.
  `import openunit` still works (openunit.py is a deprecated alias of this
  module).

Numeraire:
  A numeraire of three upper-case letters needs no declaration and gives the
  artifact it always gave. Any other numeraire must be declared as a
  fictional scenario identifier (hypothetical scenarios only; see
  redenominate and ARTIFACT_FORMAT.md): the published values are restated,
  the basket is untouched.

Data states and fallbacks:
  resolve_input(target, series, max_age_days, rate_type) resolves ONE input
  under the pre-declared rules of SPEC.md ("Data states and fallbacks"): ok,
  stale (within a maximum age), fixed_conversion (extinct currency), or an
  explicit unavailable with a reason -- never a guess. It is a pure function,
  separate from build_artifact, so it changes no artifact and no hash.
  With the optional `changeover` argument (a whole-basket successor event;
  hypothetical scenarios only) every FX-leg input on or after the event's
  date is unavailable with the reason FX_LEG_FROZEN_AT_CHANGEOVER.

Frozen record (hypothetical scenarios only):
  freeze_fx_leg(spec, event, valuation_date) states the value of the pinned
  basket in the successor unit of such an event: the pinned quantities
  divided by the declared rates, as an exact sum rounded once. "W" in the
  tests is a fictional scenario identifier, not a currency code. A record
  shows that the arithmetic reproduces from its inputs, not that a declared
  rate is authentic, right or fair.

Rate comparison (hypothetical scenarios only; information only):
  rate_comparison(event, market, ppp) sets the declared rates of such an
  event beside pinned market rates and PPP factors, as ratios. It compares;
  it does not grade. Its implied column is not a conversion rate, and a PPP
  factor is not an exchange rate.

"Don't trust me. Verify me."
"""

import json
import hashlib
from decimal import (Context, Decimal, DivisionByZero, InvalidOperation,
                     Overflow, localcontext, ROUND_HALF_EVEN)

PRECISION = 50
ROUNDING = ROUND_HALF_EVEN


def _context():
    """The one decimal context of every computation in this module. Every
    field is given, so nothing is inherited from the caller's context or from
    decimal.DefaultContext: not the letter case of an exponent (`capitals`),
    not the exponent limits, not the traps. Use it as
    `with localcontext(_context()):` and call str() on a Decimal inside the
    block (the exponent letter is chosen when the string is made)."""
    return Context(prec=PRECISION, rounding=ROUNDING, Emin=-999999,
                   Emax=999999, capitals=1, clamp=0, flags=[],
                   traps=[InvalidOperation, DivisionByZero, Overflow])

METHOD = "worldyard"          # the method name new specs carry
LEGACY_METHOD = "openunit"    # the name before the rename; default if absent
METHOD_NAMES = (LEGACY_METHOD, METHOD)
METHOD_VERSION = "v0"   # default for specs that do not pin their own version


def method_name(spec):
    """The spec's method name, as the artifact will carry it. A spec without
    `method` is read as the legacy name (as before the rename); any name other
    than "openunit" or "worldyard" is rejected."""
    m = spec.get("method", LEGACY_METHOD)
    if m not in METHOD_NAMES:
        raise ValueError("method must be one of %r, got %r" % (METHOD_NAMES, m))
    return m


# --- canonicalization & hashing ---------------------------------------------
def canonical(obj):
    """Deterministic JSON encoding used for every hash."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256(obj):
    return "sha256:" + hashlib.sha256(canonical(obj)).hexdigest()


# --- core computation --------------------------------------------------------
def _D(x):
    """Exact Decimal from a string. Never build a Decimal from a float."""
    return Decimal(str(x))


def _compute(spec):
    """Pure function: spec -> (baseline_value, value, rows). No I/O, no clock."""
    basket = spec["basket"]
    use_mult = any("weight_multiplier" in e for e in basket)

    with localcontext(_context()):
        total_pop = Decimal(0)
        total_eff = Decimal(0)
        for e in basket:
            pop = _D(e["population"])
            mult = _D(e.get("weight_multiplier", "1"))
            if pop < 0:
                raise ValueError("population must be >= 0 for %s" % e.get("code"))
            total_pop += pop
            total_eff += pop * mult
        if total_pop <= 0 or total_eff <= 0:
            raise ValueError("total population (and effective weight) must be > 0")

        baseline_value = Decimal(0)
        valuation_value = Decimal(0)
        tmp = []
        for e in basket:
            pop = _D(e["population"])
            mult = _D(e.get("weight_multiplier", "1"))
            fx_b = _D(e["fx_baseline_usd_per_unit"])
            fx_v = _D(e["fx_valuation_usd_per_unit"])
            if fx_b <= 0 or fx_v <= 0:
                raise ValueError("fx rates must be > 0 for %s" % e.get("code"))

            pop_share = pop / total_pop           # pure population share
            weight = (pop * mult) / total_eff     # effective (pinned) weight
            amount = weight / fx_b                 # fixed quantity pinned at vintage
            contrib_b = amount * fx_b              # == weight, by construction
            contrib_v = amount * fx_v

            baseline_value += contrib_b
            valuation_value += contrib_v
            tmp.append((e, pop_share, mult, weight, amount, contrib_b, contrib_v))

        rows = []
        for (e, pop_share, mult, weight, amount, contrib_b, contrib_v) in tmp:
            row = {
                "code": e["code"],
                "name": e.get("name", e["code"]),
                "population_share": str(pop_share),
                "fixed_amount": str(amount),
                "realized_weight_at_pin": str(contrib_b / baseline_value),
                "realized_weight_at_valuation": str(contrib_v / valuation_value),
            }
            if use_mult:
                # Emitted only when weighting differs from pure population, so
                # that plain v0 specs stay byte-for-byte identical to openunit v0.
                row["weight_multiplier"] = str(mult)
                row["effective_weight"] = str(weight)
            rows.append(row)

        return str(baseline_value), str(valuation_value), rows


# --- exact values and the single rounding (ARTIFACT_FORMAT.md section 1) ------
# The numbers of the hypothetical-scenario records (a declared numeraire, a
# frozen record) are not computed step by step at precision 50. Each one is an
# exact rational expression over verbatim decimal strings, rounded ONCE at the
# end. Here a rational is a pair of Python integers (numerator, denominator),
# denominator > 0; only integer arithmetic is used.

MAX_DECLARED_CHARS = 80   # longest accepted declared number, in characters
MAX_ADJUSTED = 200        # numbers read back from an artifact: 1E-200 <= x < 1E+201


def _declared(s, what):
    """Exact (numerator, denominator) of a DECLARED number (a declared rate).

    A declared number is kept verbatim in records, so its form is restricted
    to a plain decimal string: 1 to 80 characters, ASCII digits and at most
    one '.', a digit first and a digit last, and a value > 0. No sign, no
    exponent, no spaces, no '_', no digits of other scripts. Leading and
    trailing zeros are allowed and kept ("01.250" is another text for the
    value of "1.25"). Anything else raises ValueError."""
    if (not isinstance(s, str) or not 1 <= len(s) <= MAX_DECLARED_CHARS
            or any(c not in "0123456789." for c in s)
            or s.count(".") > 1 or s[0] == "." or s[-1] == "."):
        raise ValueError("%s must be a plain decimal string such as '1.25' "
                         "(digits and at most one '.', a digit first and "
                         "last, at most %d characters), got %r"
                         % (what, MAX_DECLARED_CHARS, s))
    v = Decimal(s)
    if v <= 0:
        raise ValueError("%s must be > 0: %r" % (what, s))
    return v.as_integer_ratio()


def _engine_number(s, what):
    """Exact (numerator, denominator) of a number that build_artifact itself
    wrote into an artifact (`fixed_amount`, `value_usd`, `baseline_value_usd`):
    finite, >= 0, exponent notation allowed. Unless it is zero it must satisfy
    1E-200 <= x < 1E+201, so that exact integer arithmetic stays small;
    anything else raises ValueError."""
    v = Decimal(s)
    if not v.is_finite() or v < 0:
        raise ValueError("%s must be finite and >= 0: %r" % (what, s))
    if v == 0:
        return (0, 1)
    if not -MAX_ADJUSTED <= v.adjusted() <= MAX_ADJUSTED:
        raise ValueError("%s is outside the supported range "
                         "(1E-%d <= x < 1E+%d): %r"
                         % (what, MAX_ADJUSTED, MAX_ADJUSTED + 1, s))
    return v.as_integer_ratio()


def _gcd(a, b):
    """Greatest common divisor of two integers (Euclid), >= 0."""
    a, b = abs(a), abs(b)
    while b:
        a, b = b, a % b
    return a


def _round50(p, q):
    """The exact rational p / q (integers, q > 0) rounded ONCE to 50
    significant digits, ties to even, as the decimal string every hash uses.

    An exact result is written in its shortest form (1281/1600 -> "0.800625",
    6400/100 -> "64"); a rounded one has 50 digits; exponent notation appears
    where str(Decimal) uses it ("5E-9"). The string depends only on the value
    p / q, not on how the fraction is written."""
    if q <= 0:
        raise ValueError("denominator must be > 0")
    g = _gcd(p, q)
    with localcontext(_context()):
        return str(Decimal(p // g) / Decimal(q // g))


def _is_conventional_code(s):
    """Exactly three upper-case ASCII letters: the shape of a conventional
    currency code. Only the shape is checked; no list of assigned codes is
    consulted."""
    return (isinstance(s, str) and len(s) == 3 and s.isascii()
            and s.isalpha() and s.isupper())


def _is_fictional_identifier(s):
    """A fictional scenario identifier: 1 to 16 ASCII letters and digits, at
    least one letter, and NOT exactly three letters (in any case), so that it
    can never have the shape of a conventional currency code. "W", "W1" and
    "World2100" qualify; "WLD", "wld", "USD", "840" and "" do not."""
    return (isinstance(s, str) and 1 <= len(s) <= 16 and s.isascii()
            and s.isalnum() and any(c.isalpha() for c in s)
            and not (len(s) == 3 and s.isalpha()))


def _is_hash(s):
    """'sha256:' followed by 64 lower-case hexadecimal characters."""
    return (isinstance(s, str) and len(s) == 71 and s.startswith("sha256:")
            and all(c in "0123456789abcdef" for c in s[7:]))


# --- numeraire rules (ARTIFACT_FORMAT.md sections 4.1 and 6.1) ----------------
# A numeraire is either a conventional code (three upper-case ASCII letters;
# nothing to declare, the artifact is what it always was) or a DECLARED
# fictional scenario identifier such as "W". The second kind exists for
# hypothetical scenarios only: a thought experiment, not a forecast, a
# proposal or an offer of any currency.
FICTIONAL_KIND = "fictional_scenario_identifier"
SCENARIO = "hypothetical"

_NUMERAIRE_KEYS = ("numeraire_declaration", "numeraire_conversion")
_DECLARATION_KEYS = {"code", "kind", "scenario"}
_CONVERSION_KEYS = {"from", "units_of_old_per_new", "source_artifact_hash",
                    "source_input_digest"}


def _has_declared_numeraire(spec):
    return any(k in spec for k in _NUMERAIRE_KEYS)


def _undeclared_numeraire(spec):
    """The numeraire of a spec that declares nothing: absent means "USD";
    otherwise it must have the shape of a conventional code."""
    numeraire = spec.get("numeraire", "USD")
    if not _is_conventional_code(numeraire):
        raise ValueError(
            "numeraire must be three upper-case ASCII letters (or be declared "
            "with numeraire_declaration and numeraire_conversion), got %r"
            % (numeraire,))
    return numeraire


def _validate_declaration(declaration):
    """Raise ValueError unless `declaration` is exactly
    {"code": <fictional identifier>, "kind": "fictional_scenario_identifier",
     "scenario": "hypothetical"}."""
    if not isinstance(declaration, dict) \
            or set(declaration) != _DECLARATION_KEYS:
        raise ValueError("numeraire_declaration needs exactly %s"
                         % sorted(_DECLARATION_KEYS))
    if declaration["kind"] != FICTIONAL_KIND:
        raise ValueError("numeraire_declaration.kind must be %r"
                         % FICTIONAL_KIND)
    if declaration["scenario"] != SCENARIO:
        raise ValueError("numeraire_declaration.scenario must be %r"
                         % SCENARIO)
    if not _is_fictional_identifier(declaration["code"]):
        raise ValueError(
            "numeraire_declaration.code must be a fictional identifier (1-16 "
            "ASCII letters and digits, at least one letter, not exactly three "
            "letters), got %r" % (declaration["code"],))


def _build_undeclared(spec, method):
    """The artifact of a spec without a declared numeraire: the field set and
    the bytes of every earlier version of the format."""
    numeraire = _undeclared_numeraire(spec)
    baseline_value_s, value_s, rows = _compute(spec)

    core = {
        "method": method,
        "method_version": spec.get("method_version", METHOD_VERSION),
        "numeraire": numeraire,
        "weight_vintage_label": spec["weight_vintage"]["label"],
        "weight_basis": spec["weight_vintage"]["basis"],
        "baseline_value_usd": baseline_value_s,   # == 1 by construction
        "value_usd": value_s,                     # 1 unit in the numeraire
        "basket": rows,
        "input_digest": sha256(spec),
    }
    artifact = dict(core)
    artifact["artifact_hash"] = sha256(core)
    return artifact


def _build_declared(spec, method):
    """The artifact of a spec with a declared numeraire: the SOURCE artifact
    (the same spec without the two declaration keys, in its old numeraire)
    is rebuilt, the spec must bind its two hashes, and its two published
    values are restated: each divided once by the declared rate. The basket
    rows are the source's rows, unchanged."""
    for key in _NUMERAIRE_KEYS:
        if key not in spec:
            raise ValueError("a declared numeraire needs both %s and %s"
                             % _NUMERAIRE_KEYS)
    declaration = spec["numeraire_declaration"]
    conversion = spec["numeraire_conversion"]
    _validate_declaration(declaration)
    if "numeraire" not in spec or spec["numeraire"] != declaration["code"]:
        raise ValueError("numeraire must be present and equal "
                         "numeraire_declaration.code")
    if not isinstance(conversion, dict) \
            or set(conversion) != _CONVERSION_KEYS:
        raise ValueError("numeraire_conversion needs exactly %s"
                         % sorted(_CONVERSION_KEYS))
    if not _is_conventional_code(conversion["from"]):
        raise ValueError("numeraire_conversion.from must be three upper-case "
                         "ASCII letters, got %r" % (conversion["from"],))
    rate_n, rate_d = _declared(conversion["units_of_old_per_new"],
                               "numeraire_conversion.units_of_old_per_new")
    for key in ("source_artifact_hash", "source_input_digest"):
        if not _is_hash(conversion[key]):
            raise ValueError("numeraire_conversion.%s must be 'sha256:' and "
                             "64 lower-case hex characters" % key)

    source_spec = {k: v for k, v in spec.items() if k not in _NUMERAIRE_KEYS}
    source_spec["numeraire"] = conversion["from"]
    # built first, so that a spec the ordinary rules reject is rejected the
    # way they reject it
    source = _build_undeclared(source_spec, method)
    if _ppp_valued(source_spec):
        raise ValueError("a PPP-valued spec cannot be re-denominated: its "
                         "value is in international dollars, not an amount "
                         "of a converting currency")
    if source["artifact_hash"] != conversion["source_artifact_hash"] \
            or source["input_digest"] != conversion["source_input_digest"]:
        raise ValueError("numeraire_conversion does not bind the source "
                         "artifact (the spec without the declaration keys, "
                         "in its old numeraire)")

    base_n, base_d = _engine_number(source["baseline_value_usd"],
                                    "source baseline_value_usd")
    value_n, value_d = _engine_number(source["value_usd"], "source value_usd")
    core = {
        "method": source["method"],
        "method_version": source["method_version"],
        "numeraire": spec["numeraire"],
        "numeraire_declaration": dict(declaration),
        "numeraire_conversion": dict(conversion),
        "weight_vintage_label": source["weight_vintage_label"],
        "weight_basis": source["weight_basis"],
        # the published value / the declared rate, rounded once (never
        # multiplied by an inverse rate)
        "baseline_value": _round50(base_n * rate_d, base_d * rate_n),
        "value": _round50(value_n * rate_d, value_d * rate_n),
        "basket": source["basket"],
        "input_digest": sha256(spec),
    }
    artifact = dict(core)
    artifact["artifact_hash"] = sha256(core)
    return artifact


# --- public API --------------------------------------------------------------
def build_artifact(spec):
    """Build a deterministic, self-describing artifact from a spec dict.

    The numeraire is `spec["numeraire"]` (absent: "USD"). It must be three
    upper-case ASCII letters, in which case the artifact has the fields it
    always had (`baseline_value_usd`, `value_usd`). Any other numeraire must
    be DECLARED as a fictional scenario identifier with the two keys
    `numeraire_declaration` and `numeraire_conversion` (see redenominate);
    the artifact then carries `baseline_value` and `value`, the published
    values of the source artifact divided once by the declared rate, and the
    same basket rows. A spec that only renames its numeraire is rejected
    (ValueError)."""
    method = method_name(spec)
    if _has_declared_numeraire(spec):
        return _build_declared(spec, method)
    return _build_undeclared(spec, method)


def _json_copy(value):
    """A deep copy of plain JSON data (dicts and lists are copied; strings
    and other leaves are shared)."""
    if isinstance(value, dict):
        return {k: _json_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_copy(v) for v in value]
    return value


def redenominate(spec, artifact, declaration, units_of_old_per_new):
    """Return the spec that restates `artifact` in a DECLARED fictional
    numeraire. Hypothetical scenarios only: "W" in the tests is a fictional
    scenario identifier, not a currency code, and nothing here is a forecast
    or a proposal.

    spec, artifact        a spec with a conventional numeraire, stated
                          explicitly, and the artifact built from it
    declaration           {"code": "W", "kind": "fictional_scenario_identifier",
                           "scenario": "hypothetical"}
    units_of_old_per_new  declared number: units of the old numeraire equal
                          to ONE unit of the new one (kept verbatim; values
                          are divided by it, no inverse rate is ever formed)

    The result is a new spec (the input is not changed): the same spec with
    `numeraire` set to the declared code, plus `numeraire_declaration` and
    `numeraire_conversion` = {"from", "units_of_old_per_new",
    "source_artifact_hash", "source_input_digest"}. build_artifact of that
    spec rebuilds the source artifact, checks the two hashes, keeps every
    basket row and divides the two published values by the rate.

    "Re-denominating" changes the unit in which the published values are
    stated and nothing else. It does not show that the declared rate is
    authentic, right or fair.

    ValueError: a spec that already has a declared numeraire (no chains), a
    spec without an explicit `numeraire` or with one that is not three
    upper-case letters, a malformed declaration or rate, a PPP-valued spec,
    an artifact that does not reproduce from the spec, published values that
    cannot be restated (negative, or outside the supported range)."""
    if not isinstance(spec, dict):
        raise ValueError("spec must be a dict")
    if _has_declared_numeraire(spec):
        raise ValueError("the spec already has a declared numeraire; "
                         "re-denominate its source spec instead")
    if "numeraire" not in spec:
        raise ValueError("the source spec must state its numeraire explicitly")
    old = _undeclared_numeraire(spec)
    _validate_declaration(declaration)
    _declared(units_of_old_per_new, "units_of_old_per_new")
    built = build_artifact(spec)
    if _ppp_valued(spec):
        raise ValueError("a PPP-valued spec cannot be re-denominated: its "
                         "value is in international dollars, not an amount "
                         "of a converting currency")
    if artifact != built:
        raise ValueError("artifact does not reproduce from spec")
    # the two values to restate must be usable exactly, so that the returned
    # spec is one build_artifact accepts
    _engine_number(built["baseline_value_usd"], "baseline_value_usd")
    _engine_number(built["value_usd"], "value_usd")
    out = _json_copy(spec)
    out["numeraire"] = declaration["code"]
    out["numeraire_declaration"] = dict(declaration)
    out["numeraire_conversion"] = {
        "from": old,
        "units_of_old_per_new": units_of_old_per_new,
        "source_artifact_hash": built["artifact_hash"],
        "source_input_digest": built["input_digest"],
    }
    return out


def artifact_value(artifact):
    """The value string of an artifact: `value` when the artifact carries a
    declared numeraire, `value_usd` otherwise."""
    if "numeraire_declaration" in artifact:
        return artifact["value"]
    return artifact["value_usd"]


def verify_artifact(artifact, spec, explain=False):
    """True iff `artifact` is internally consistent AND reproduces `spec`."""
    reasons = []

    if artifact.get("input_digest") != sha256(spec):
        reasons.append("input_digest does not match spec")

    core = {k: v for k, v in artifact.items() if k != "artifact_hash"}
    if sha256(core) != artifact.get("artifact_hash"):
        reasons.append("artifact_hash does not match artifact content")

    if build_artifact(spec) != artifact:
        reasons.append("artifact does not reproduce from spec")

    ok = not reasons
    if explain and not ok:
        for r in reasons:
            print("  - " + r)
    return ok


# --- data states and fallbacks (SPEC.md, "Data states and fallbacks") --------
# A pure, deterministic resolver for ONE input (e.g. an FX rate) at ONE target
# date, under pre-declared rules. It is not called by build_artifact, so it
# changes no artifact and no hash; a publisher runs it BEFORE building, and an
# input that resolves to "unavailable" must not be put into a spec at all.

# Pre-declared maximum ages (SPEC.md, "Data states and fallbacks"). The
# observation date of an annual series is 1 July of its reference year; that of
# a population revision is the revision's release date.
DECLARED_MAX_AGE_DAYS = {
    "ECB euro reference rates": 4,     # weekends + TARGET closing days
    "UN World Population Prospects": 1461,   # 4 years from the release
    "World Bank PA.NUS.PPP": 1096,     # 3 years from 1 July of the year
}

_SERIES_KEYS = {"observations", "suspended_since", "retired_since",
                "permanent_holes", "fixed_conversion"}
_OBS_KEYS = {"date", "value", "rate_type"}
_FIXED_KEYS = {"effective", "units_per_successor", "successor"}


def _days(date):
    """Strict 'YYYY-MM-DD' (proleptic Gregorian) -> day number. Pure integer
    arithmetic (H. Hinnant's days-from-civil); no calendar library, no clock."""
    if not isinstance(date, str) or len(date) != 10 or date[4] != "-" \
            or date[7] != "-" or not (date[:4] + date[5:7] + date[8:]).isdigit() \
            or not date.isascii():
        raise ValueError("date must be 'YYYY-MM-DD': %r" % (date,))
    y, m, d = int(date[:4]), int(date[5:7]), int(date[8:])
    leap = (y % 4 == 0 and y % 100 != 0) or y % 400 == 0
    mdays = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if y < 1 or not 1 <= m <= 12 or not 1 <= d <= mdays[m - 1]:
        raise ValueError("no such date: %r" % (date,))
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe


def _positive_decimal(s, what):
    """A finite, > 0 Decimal parsed from a STRING (never from a float)."""
    if not isinstance(s, str):
        raise ValueError("%s must be a decimal string, got %r" % (what, s))
    try:
        v = Decimal(s)
    except ArithmeticError:
        raise ValueError("%s is not a decimal: %r" % (what, s))
    if not v.is_finite() or v <= 0:
        raise ValueError("%s must be finite and > 0: %r" % (what, s))
    return v


def _max_age(n):
    if isinstance(n, bool) or not isinstance(n, (int, str)):
        raise ValueError("max_age_days must be an int or a decimal-integer "
                         "string, got %r" % (n,))
    if isinstance(n, str):
        if not (n.isascii() and n.isdigit()):
            raise ValueError("max_age_days must be a non-negative integer: %r"
                             % (n,))
        n = int(n)
    if n < 0:
        raise ValueError("max_age_days must be >= 0: %r" % (n,))
    return n


def _result(state, value=None, date=None, age=None, rate_type=None,
            flags=(), reason=None):
    return {"state": state, "value": value, "observation_date": date,
            "age_days": None if age is None else str(age),
            "rate_type": rate_type, "flags": sorted(set(flags)),
            "reason": reason}


# A whole-basket successor event (SPEC.md, "Whole-basket successor event";
# ARTIFACT_FORMAT.md section 10). HYPOTHETICAL SCENARIOS ONLY: a thought
# experiment in which every currency of a basket is converted into one
# successor unit on one date. The successor is a fictional scenario
# identifier such as "W", never a currency code. Nothing here is a forecast,
# a proposal or an offer of any currency.
EVENT_KIND = "whole_basket_successor"
FX_LEG_FROZEN_AT_CHANGEOVER = "FX_LEG_FROZEN_AT_CHANGEOVER"   # reason code

_EVENT_REQUIRED = {"event", "id", "scenario", "successor", "successor_kind",
                   "effective", "units_per_successor"}
_EVENT_OPTIONAL = {"declaration"}


def _validate_event(event):
    """Raise ValueError unless `event` is a well-formed whole-basket successor
    event; return the day number of its `effective` date.

      event                "whole_basket_successor"
      id                   a non-empty string
      scenario             "hypothetical" (nothing else is accepted)
      successor            a fictional identifier (never three letters)
      successor_kind       "fictional_scenario_identifier"
      effective            'YYYY-MM-DD', the first date on which it applies
      units_per_successor  a non-empty object: old currency code -> declared
                           number, the units of that currency equal to ONE
                           unit of the successor; no code equals the successor
      declaration          optional object, free-form provenance; it is
                           hashed with the event and never interpreted

    Any other key is an error. Whether the event covers a given basket is
    checked where the basket is known, not here."""
    if not isinstance(event, dict):
        raise ValueError("a whole-basket successor event must be a dict, "
                         "got %r" % (event,))
    missing = _EVENT_REQUIRED - set(event)
    unknown = set(event) - _EVENT_REQUIRED - _EVENT_OPTIONAL
    if missing or unknown:
        raise ValueError("event keys: missing %s, unknown %s"
                         % (sorted(missing), sorted(repr(k) for k in unknown)))
    if event["event"] != EVENT_KIND:
        raise ValueError("event must be %r, got %r"
                         % (EVENT_KIND, event["event"]))
    if not isinstance(event["id"], str) or not event["id"]:
        raise ValueError("event id must be a non-empty string")
    if event["scenario"] != SCENARIO:
        raise ValueError("event scenario must be %r (only hypothetical "
                         "scenarios are supported)" % SCENARIO)
    if event["successor_kind"] != FICTIONAL_KIND:
        raise ValueError("event successor_kind must be %r" % FICTIONAL_KIND)
    if not _is_fictional_identifier(event["successor"]):
        raise ValueError(
            "event successor must be a fictional identifier (1-16 ASCII "
            "letters and digits, at least one letter, not exactly three "
            "letters), got %r" % (event["successor"],))
    effective = _days(event["effective"])
    rates = event["units_per_successor"]
    if not isinstance(rates, dict) or not rates:
        raise ValueError("units_per_successor must be a non-empty dict (an "
                         "event without rates is not a successor event)")
    for code, rate in rates.items():
        if not isinstance(code, str) or not code:
            raise ValueError("units_per_successor has a code that is not a "
                             "non-empty string: %r" % (code,))
        if code == event["successor"]:
            raise ValueError("the successor %r cannot be one of the "
                             "converted codes" % (code,))
        _declared(rate, "units_per_successor[%s]" % code)
    if "declaration" in event and not isinstance(event["declaration"], dict):
        raise ValueError("event declaration must be a dict")
    return effective


def resolve_input(target, series, max_age_days=0, rate_type=None,
                  changeover=None):
    """Resolve one input at `target` ('YYYY-MM-DD') from `series` under the
    pre-declared rules of SPEC.md ("Data states and fallbacks").

    series = {
      "observations": [{"date": "YYYY-MM-DD", "value": "<decimal string>",
                        "rate_type": "<optional label>"}, ...],
      "suspended_since": "YYYY-MM-DD",        # optional: publisher suspended it
      "retired_since":   "YYYY-MM-DD",        # optional: publisher stopped it
      "permanent_holes": ["YYYY-MM-DD", ...], # optional: never to be published
      "fixed_conversion": {                   # optional: extinct currency
          "effective": "YYYY-MM-DD",
          "units_per_successor": "<decimal string>",  # e.g. BGN per EUR
          "successor": <series of the successor, same numeraire>},
    }

    changeover = a whole-basket successor event (optional; HYPOTHETICAL
    SCENARIOS ONLY, see _validate_event and SPEC.md): pass it when resolving
    an FX-leg input, i.e. an exchange rate of a basket currency against the
    numeraire. It is not for population or PPP inputs.

    Rules, applied in this order (the first that applies decides):
      0. changeover given and target >= its `effective` date -> unavailable
         FX_LEG_FROZEN_AT_CHANGEOVER, for every series: on and after that
         date the FX leg has ended, nothing is missing. This comes after the
         validation of all arguments and before every per-series rule
         (a fixed_conversion, whatever its date, included; its successor
         series is then not looked at).
      1. fixed_conversion with target >= effective: resolve the successor
         (same max_age_days / rate_type) and divide by units_per_successor;
         state "fixed_conversion", flags FIXED_CONVERSION + the successor's.
      2. target in permanent_holes            -> unavailable PERMANENT_HOLE
      3. target >= suspended_since            -> unavailable SUSPENDED
      4. target >= retired_since              -> unavailable SOURCE_RETIRED
      5. take observations dated <= target (never a later one), restricted to
         rate_type if one is declared; none   -> unavailable NO_OBSERVATION
      6. more than one on the latest date     -> unavailable
         AMBIGUOUS_MULTIPLE_RATES (never averaged, never picked silently);
         flag MULTIPLE_RATES when a declared rate_type resolved a date that
         carries several rates
      7. age = target - that date in days; age > max_age_days -> unavailable
         TOO_OLD; age == 0 -> "ok"; otherwise "stale" (flag STALE).

    Returns {"state", "value", "observation_date", "age_days", "rate_type",
    "flags", "reason"}; "value" is the observation's string verbatim (or the
    exact quotient for a fixed conversion) and None whenever state is
    "unavailable". Pure: no I/O, no clock, inputs never mutated, the result
    does not depend on the order of the observations. Malformed input raises
    ValueError (a malformed changeover too, also when the target is before
    it). Without `changeover`, and for targets before its date, the function
    behaves exactly as it did before the argument existed.
    """
    t = _days(target)
    max_age = _max_age(max_age_days)
    if rate_type is not None and not isinstance(rate_type, str):
        raise ValueError("rate_type must be a string or None")
    frozen_from = None if changeover is None else _validate_event(changeover)
    if not isinstance(series, dict):
        raise ValueError("series must be a dict")
    unknown = set(series) - _SERIES_KEYS
    if unknown:
        raise ValueError("series has unknown keys: %r" % sorted(unknown))

    obs = []
    for o in series.get("observations", []):
        if not isinstance(o, dict) or set(o) - _OBS_KEYS or \
                "date" not in o or "value" not in o:
            raise ValueError("malformed observation: %r" % (o,))
        _positive_decimal(o["value"], "observation value")
        rt = o.get("rate_type")
        if rt is not None and not isinstance(rt, str):
            raise ValueError("rate_type must be a string: %r" % (o,))
        obs.append((_days(o["date"]), o["date"], o["value"], rt))
    holes = set()
    for h in series.get("permanent_holes", []):
        holes.add(_days(h))
    if any(d in holes for d, _, _, _ in obs):
        raise ValueError("an observation is dated inside a declared "
                         "permanent hole")
    suspended = series.get("suspended_since")
    retired = series.get("retired_since")
    suspended = None if suspended is None else _days(suspended)
    retired = None if retired is None else _days(retired)

    fixed = series.get("fixed_conversion")
    fixed_from = None
    if fixed is not None:
        if not isinstance(fixed, dict) or set(fixed) != _FIXED_KEYS:
            raise ValueError("fixed_conversion needs exactly %s"
                             % sorted(_FIXED_KEYS))
        units = _positive_decimal(fixed["units_per_successor"],
                                  "units_per_successor")
        fixed_from = _days(fixed["effective"])

    # Rule 0: on and after a whole-basket successor event the FX leg has
    # ended. Every argument has been validated above; no per-series rule is
    # consulted, and the successor series of a fixed_conversion is not read.
    if frozen_from is not None and t >= frozen_from:
        return _result("unavailable", reason=FX_LEG_FROZEN_AT_CHANGEOVER)

    if fixed is not None and t >= fixed_from:
        succ = resolve_input(target, fixed["successor"], max_age, rate_type)
        if succ["state"] == "unavailable":
            return _result("unavailable", date=succ["observation_date"],
                           age=succ["age_days"],
                           rate_type=succ["rate_type"],
                           reason="SUCCESSOR_UNAVAILABLE:" + succ["reason"])
        with localcontext(_context()):
            value = str(Decimal(succ["value"]) / units)
        return _result("fixed_conversion", value, succ["observation_date"],
                       succ["age_days"], succ["rate_type"],
                       list(succ["flags"]) + ["FIXED_CONVERSION"])

    if t in holes:
        return _result("unavailable", reason="PERMANENT_HOLE")
    if suspended is not None and t >= suspended:
        return _result("unavailable", reason="SUSPENDED")
    if retired is not None and t >= retired:
        return _result("unavailable", reason="SOURCE_RETIRED")

    eligible = [o for o in obs if o[0] <= t and
                (rate_type is None or o[3] == rate_type)]
    if not eligible:
        return _result("unavailable", rate_type=rate_type,
                       reason="NO_OBSERVATION")
    latest = max(o[0] for o in eligible)
    same_day = [o for o in eligible if o[0] == latest]
    date = same_day[0][1]
    age = t - latest
    if len(same_day) > 1:
        return _result("unavailable", date=date, age=age, rate_type=rate_type,
                       reason="AMBIGUOUS_MULTIPLE_RATES")
    flags = []
    if sum(1 for o in obs if o[0] == latest) > 1:
        flags.append("MULTIPLE_RATES")
    if age > max_age:
        return _result("unavailable", date=date, age=age, rate_type=rate_type,
                       flags=flags, reason="TOO_OLD")
    if age > 0:
        flags.append("STALE")
    return _result("ok" if age == 0 else "stale", same_day[0][2], date, age,
                   rate_type, flags)


# --- frozen record (ARTIFACT_FORMAT.md section 11) ------------------------------
# HYPOTHETICAL SCENARIOS ONLY. When every currency of the basket is converted
# into one successor unit, the pinned quantities become fixed amounts of that
# unit, so the value of the basket in the successor unit is a constant. The
# frozen record states that constant and what it was computed from.
FROZEN_RECORD_FORMAT = "worldyard-frozen-record-1"
FROZEN_NOTICE = (
    "Hypothetical scenario record: a thought experiment, not a forecast, a "
    "proposal or an offer of any currency. final_value is the pinned basket "
    "quantities divided by the declared rates; it does not show that the "
    "rates are authentic, right or fair. The comparison block is information "
    "only and depends on the bridge currency.")


def _event_hash(event):
    """sha256 of the canonical event (a validated event whose optional
    `declaration` holds something that is not JSON data is refused)."""
    try:
        return sha256(event)
    except TypeError:
        raise ValueError("the event's declaration is not plain JSON data")


def freeze_fx_leg(spec, event, valuation_date):
    """Freeze the FX leg of `spec` at a whole-basket successor event and
    return the frozen record (format "worldyard-frozen-record-1").

    HYPOTHETICAL SCENARIOS ONLY: a thought experiment in which every currency
    of the basket is converted into one successor unit on one date. The
    successor ("W" in the tests) is a fictional scenario identifier, not a
    currency code. Nothing here is a forecast, a proposal or an offer of any
    currency.

    spec            a spec with an undeclared numeraire and an FX valuation
                    leg (the last one before the event)
    event           the event (see _validate_event); it must declare a rate
                    for exactly the codes of the basket
    valuation_date  'YYYY-MM-DD', the valuation date of the spec's FX leg,
                    strictly before the event's `effective` date. It is a
                    declaration by the caller: build_artifact reads no dates,
                    so only the order of the two dates can be checked here.

    The record binds the artifact built from the spec (both hashes, its
    value verbatim), the event (its hash), the pinned quantities and the
    declared rates actually used, row by row, and the declared date. Its
    value is

        final_value = R50( sum_i  fixed_amount_i / units_per_successor_i )

    an exact rational sum of the artifact's verbatim `fixed_amount` strings,
    each DIVIDED by its declared rate (no inverse rate is formed), rounded
    once to 50 significant digits, ties to even. It does not depend on the
    order of the basket.

    `comparison` (information only; null when the old numeraire has no
    declared rate) restates the artifact's last value through the declared
    rate of the old numeraire alone, and gives final_value minus that. The
    two differ when the declared rates are not proportional to the last
    market rates; the restated number depends on the bridge currency.

    A record shows that the arithmetic reproduces from its inputs. It does
    not show that a declared rate is authentic, right or fair.

    ValueError: a malformed event, a valuation date that is malformed or not
    before `effective`, a spec with a declared numeraire (freeze its source
    spec), a PPP-valued spec, an event that does not cover exactly the basket
    codes, basket codes that are not strings, quantities that are negative
    or outside the supported range. Whatever build_artifact rejects is
    rejected as build_artifact rejects it. Pure: no I/O, no clock, inputs not
    mutated, the result is plain JSON data."""
    effective = _validate_event(event)
    if _days(valuation_date) >= effective:
        raise ValueError("valuation_date %r must be before the event's "
                         "effective date %r"
                         % (valuation_date, event["effective"]))
    if not isinstance(spec, dict):
        raise ValueError("spec must be a dict")
    if _has_declared_numeraire(spec):
        raise ValueError("freeze_fx_leg needs a spec with an undeclared "
                         "numeraire; freeze the source spec instead")
    artifact = build_artifact(spec)
    if _ppp_valued(spec):
        raise ValueError("freeze_fx_leg applies to an FX valuation leg; this "
                         "spec is PPP-valued (its value is in international "
                         "dollars, not an amount of a converting currency)")

    rates = event["units_per_successor"]
    codes = [row["code"] for row in artifact["basket"]]
    if not all(isinstance(code, str) for code in codes):
        raise ValueError("every basket code must be a string to be frozen")
    missing = sorted(set(codes) - set(rates))
    extra = sorted(set(rates) - set(codes))
    if missing or extra:
        raise ValueError("the event must declare a rate for exactly the "
                         "basket codes: missing %r, not in the basket %r"
                         % (missing, extra))

    rows = []
    total_n, total_d = 0, 1               # the exact sum, as total_n / total_d
    for row in artifact["basket"]:
        rate = rates[row["code"]]
        amount_n, amount_d = _engine_number(
            row["fixed_amount"], "fixed_amount of %s" % row["code"])
        rate_n, rate_d = _declared(
            rate, "units_per_successor[%s]" % row["code"])
        term_n, term_d = amount_n * rate_d, amount_d * rate_n   # amount / rate
        total_n, total_d = total_n * term_d + term_n * total_d, total_d * term_d
        rows.append({"code": row["code"],
                     "fixed_amount": row["fixed_amount"],
                     "units_per_successor": rate})
    final_value = _round50(total_n, total_d)

    flags = ["FROZEN_AT_CHANGEOVER"]
    bridge = artifact["numeraire"]
    if bridge in rates:
        value_n, value_d = _engine_number(artifact["value_usd"], "value_usd")
        rate_n, rate_d = _declared(rates[bridge],
                                   "units_per_successor[%s]" % bridge)
        bridged = _round50(value_n * rate_d, value_d * rate_n)
        # the difference of the two PUBLISHED strings, exactly, rounded once
        final_n, final_d = Decimal(final_value).as_integer_ratio()
        bridged_n, bridged_d = Decimal(bridged).as_integer_ratio()
        comparison = {
            "information_only": True,
            "bridge_code": bridge,
            "bridge_units_per_successor": rates[bridge],
            "last_fx_leg_value_bridged": bridged,
            "final_minus_bridged": _round50(
                final_n * bridged_d - bridged_n * final_d,
                final_d * bridged_d),
        }
    else:
        comparison = None
        flags.append("NO_BRIDGE_RATE")

    body = {
        "format": FROZEN_RECORD_FORMAT,
        "kind": "frozen_fx_leg",
        "state": "frozen_at_changeover",
        "flags": sorted(flags),
        "scenario": event["scenario"],
        "notice": FROZEN_NOTICE,
        "event_id": event["id"],
        "event_hash": _event_hash(event),
        "successor": event["successor"],
        "successor_kind": event["successor_kind"],
        "effective": event["effective"],
        "source_artifact_hash": artifact["artifact_hash"],
        "source_input_digest": artifact["input_digest"],
        "declared_valuation_date": valuation_date,
        "last_fx_leg_value": artifact["value_usd"],
        "last_fx_leg_numeraire": bridge,
        "basket": rows,
        "final_value": final_value,
        "final_value_numeraire": event["successor"],
        "comparison": comparison,
    }
    record = dict(body)
    record["record_hash"] = sha256(body)
    return record


# --- rate comparison (ARTIFACT_FORMAT.md section 12) ----------------------------
# HYPOTHETICAL SCENARIOS ONLY, and INFORMATION ONLY. The declared rates of a
# whole-basket successor event are set beside pinned market rates and PPP
# factors, as ratios. It compares; it does not grade. No column is a
# conversion rate, and a PPP factor is not an exchange rate.
RATE_COMPARISON_FORMAT = "worldyard-rate-comparison-1"
RATE_COMPARISON_ANCHOR = "USD"   # the numeraire of every rate field here
RATE_NOTICE = (
    "Information only. Hypothetical scenario: a thought experiment, not a "
    "forecast, a proposal or an offer of any currency. "
    "declared_implied_usd_per_unit is a comparison quantity derived from two "
    "declared rates; it is not a conversion rate and must not be used to "
    "convert amounts. A PPP factor is not an exchange rate: no column shows a "
    "correct rate, or that a currency is over- or undervalued.")

_MARKET_KEYS = {"source", "date", "numeraire", "usd_per_unit"}
_PPP_KEYS = {"source", "reference_year", "lcu_per_intl_usd"}


def _pinned_table(table, rates, what):
    """Exact values of one pinned table of a rate comparison: an object whose
    keys are codes of the event and whose values are declared numbers; an
    entry for the anchor currency must equal 1. A code of the event that is
    missing from the table is allowed (the comparison is then null)."""
    if not isinstance(table, dict):
        raise ValueError("%s must be a dict" % what)
    extra = [code for code in table if code not in rates]
    if extra:
        raise ValueError("%s has codes the event does not declare: %s"
                         % (what, ", ".join(sorted(repr(c) for c in extra))))
    exact = {}
    for code, text in table.items():
        exact[code] = _declared(text, "%s[%s]" % (what, code))
    if exact.get(RATE_COMPARISON_ANCHOR, (1, 1)) != (1, 1):
        raise ValueError("%s[%s] must be 1 (the table is in %s)"
                         % (what, RATE_COMPARISON_ANCHOR,
                            RATE_COMPARISON_ANCHOR))
    return exact


def rate_comparison(event, market, ppp):
    """Set the declared rates of a whole-basket successor event beside pinned
    market rates and PPP factors; return the record (format
    "worldyard-rate-comparison-1").

    HYPOTHETICAL SCENARIOS ONLY, and INFORMATION ONLY. The successor ("W" in
    the tests) is a fictional scenario identifier, not a currency code.
    Nothing here is a forecast, a proposal or an offer of any currency. The
    record compares; it does not grade. Its implied column is a comparison
    quantity, NOT a conversion rate, and must not be used to convert amounts
    (in the euro precedent, rates between two old currencies were not
    defined). A PPP factor is not an exchange rate: no column shows a correct
    rate, or that a currency is over- or undervalued.

    event   a whole-basket successor event (see _validate_event) that
            declares a rate for USD, the anchor of every rate field here
    market  {"source": <non-empty string>, "date": 'YYYY-MM-DD' before the
             event's `effective`, "numeraire": "USD",
             "usd_per_unit": {code: <declared number>, ...}}
    ppp     {"source": <non-empty string>, "reference_year": 'YYYY' (its
             observation date, 1 July, before `effective`),
             "lcu_per_intl_usd": {code: <declared number>, ...}}

    Every table key must be a code of the event; every value is a declared
    number (a plain decimal string, > 0); a USD entry must be 1. The caller
    resolves each input under SPEC.md "Data states and fallbacks" first, as
    for build_artifact, and leaves out an input that resolved unavailable: a
    missing code gives explicit nulls and the flag NO_MARKET_RATE or
    NO_PPP_FACTOR, never a guess.

    One row per event code, sorted by code, with u = units_per_successor:

        declared_implied_usd_per_unit = R50( u[USD] / u[code] )
        declared_over_market          = R50( u[USD] / u[code] / market )
        declared_over_ppp             = R50( u[USD] / u[code] * factor )

    each computed from the exact values of the verbatim strings and rounded
    once (50 significant digits, ties to even); no column is computed from
    another, already rounded one, and no inverse rate is formed.
    declared_over_ppp is a price level index computed with the
    declared-implied rate instead of a market rate (United States = 1).

    The record is self-hashed (record_hash) and not anchored. A record shows
    that the arithmetic reproduces from its inputs. It does not show that a
    declared rate, a market rate or a PPP factor is authentic, right or fair.

    ValueError for anything malformed. Pure: no I/O, no clock, inputs not
    mutated, the result is plain JSON data."""
    effective = _validate_event(event)
    rates = event["units_per_successor"]
    if not isinstance(market, dict) or set(market) != _MARKET_KEYS:
        raise ValueError("market must be a dict with exactly the keys %s"
                         % sorted(_MARKET_KEYS))
    if not isinstance(ppp, dict) or set(ppp) != _PPP_KEYS:
        raise ValueError("ppp must be a dict with exactly the keys %s"
                         % sorted(_PPP_KEYS))
    for table, name in ((market, "market"), (ppp, "ppp")):
        if not isinstance(table["source"], str) or not table["source"]:
            raise ValueError("%s.source must be a non-empty string" % name)
    if market["numeraire"] != RATE_COMPARISON_ANCHOR:
        raise ValueError("market.numeraire must be %r"
                         % RATE_COMPARISON_ANCHOR)
    if RATE_COMPARISON_ANCHOR not in rates:
        raise ValueError("the event declares no rate for %s, the anchor of "
                         "the comparison" % RATE_COMPARISON_ANCHOR)
    if _days(market["date"]) >= effective:
        raise ValueError("market.date %r must be before the event's "
                         "effective date %r"
                         % (market["date"], event["effective"]))
    year = ppp["reference_year"]
    if not (isinstance(year, str) and len(year) == 4 and year.isascii()
            and year.isdigit()):
        raise ValueError("ppp.reference_year must be a string 'YYYY', got %r"
                         % (year,))
    if _days(year + "-07-01") >= effective:
        raise ValueError("ppp.reference_year %r: its observation date (1 "
                         "July) must be before the event's effective date %r"
                         % (year, event["effective"]))
    market_rates = _pinned_table(market["usd_per_unit"], rates,
                                 "market.usd_per_unit")
    factors = _pinned_table(ppp["lcu_per_intl_usd"], rates,
                            "ppp.lcu_per_intl_usd")

    anchor_n, anchor_d = _declared(
        rates[RATE_COMPARISON_ANCHOR],
        "units_per_successor[%s]" % RATE_COMPARISON_ANCHOR)
    rows = []
    for code in sorted(rates):
        rate_n, rate_d = _declared(rates[code],
                                   "units_per_successor[%s]" % code)
        implied_n, implied_d = anchor_n * rate_d, anchor_d * rate_n
        flags = []
        row = {"code": code,
               "declared_units_per_successor": rates[code],
               "declared_implied_usd_per_unit": _round50(implied_n,
                                                         implied_d)}
        if code in market_rates:
            market_n, market_d = market_rates[code]
            row["market_usd_per_unit"] = market["usd_per_unit"][code]
            row["declared_over_market"] = _round50(implied_n * market_d,
                                                   implied_d * market_n)
        else:
            row["market_usd_per_unit"] = None
            row["declared_over_market"] = None
            flags.append("NO_MARKET_RATE")
        if code in factors:
            factor_n, factor_d = factors[code]
            row["ppp_lcu_per_intl_usd"] = ppp["lcu_per_intl_usd"][code]
            row["declared_over_ppp"] = _round50(implied_n * factor_n,
                                                implied_d * factor_d)
        else:
            row["ppp_lcu_per_intl_usd"] = None
            row["declared_over_ppp"] = None
            flags.append("NO_PPP_FACTOR")
        row["flags"] = sorted(flags)
        rows.append(row)

    body = {
        "format": RATE_COMPARISON_FORMAT,
        "kind": "rate_comparison",
        "information_only": True,
        "scenario": event["scenario"],
        "notice": RATE_NOTICE,
        "event_id": event["id"],
        "event_hash": _event_hash(event),
        "successor": event["successor"],
        "successor_kind": event["successor_kind"],
        "effective": event["effective"],
        "market": {"source": market["source"], "date": market["date"],
                   "numeraire": market["numeraire"]},
        "ppp": {"source": ppp["source"],
                "reference_year": ppp["reference_year"]},
        "rows": rows,
    }
    record = dict(body)
    record["record_hash"] = sha256(body)
    return record


# --- display (never hashed) ---------------------------------------------------
INTL_DOLLAR = "international $"
FICTIONAL_UNIT_NOTE = "(fictional scenario identifier, not a currency)"


def _ppp_valued(spec):
    """True iff every basket entry records `ppp_factor_lcu_per_intl_usd` and
    its `fx_valuation_usd_per_unit` is exactly 1 / that factor, i.e. the
    valuation leg is PPP (SPEC.md section 2.3)."""
    basket = spec.get("basket") or []
    if not basket:
        return False
    with localcontext(_context()):
        for e in basket:
            factor = e.get("ppp_factor_lcu_per_intl_usd")
            if factor is None:
                return False
            try:
                if (Decimal(1) / Decimal(factor)
                        != Decimal(e["fx_valuation_usd_per_unit"])):
                    return False
            except (ArithmeticError, KeyError, TypeError, ValueError):
                return False
    return True


def display_unit(artifact, spec=None):
    """The unit text printed after an artifact's value. Display only: it
    changes no hashed field.

    PPP vintages (v0.2, v0.4) keep the hashed `numeraire` "USD", but their
    value is in international dollars (SPEC.md section 2.3), so they print as
    'international $ (numeraire field: USD)'. With the spec, a PPP vintage is
    recognised exactly (see _ppp_valued). From an artifact alone the only hint
    is its hashed `weight_vintage_label`: the PPP vintages carry the token
    "PPP" there ("WB-PPP-2024"). An artifact with a declared numeraire
    (hypothetical scenarios only) prints its code with the note
    "(fictional scenario identifier, not a currency)", e.g. "W (fictional
    scenario identifier, not a currency)". Every other artifact prints its
    numeraire."""
    numeraire = artifact.get("numeraire", "USD")
    if "numeraire_declaration" in artifact:
        return "%s %s" % (numeraire, FICTIONAL_UNIT_NOTE)
    if numeraire != "USD":
        return numeraire
    if spec is not None:
        ppp = _ppp_valued(spec)
    else:
        label = artifact.get("weight_vintage_label", "")
        ppp = "PPP" in "".join(c if c.isalnum() else " " for c in label).split()
    if not ppp:
        return numeraire
    return "%s (numeraire field: %s)" % (INTL_DOLLAR, numeraire)


# --- demo --------------------------------------------------------------------
def _demo(path="sample_input.json"):
    with open(path, "r", encoding="utf-8") as fh:
        spec = json.load(fh)

    artifact = build_artifact(spec)
    ok = verify_artifact(artifact, spec, explain=True)

    q = Decimal("0.000001")
    value = Decimal(artifact_value(artifact)).quantize(q)
    has_mult = any("weight_multiplier" in r for r in artifact["basket"])
    print("Worldyard reference demo  (%s %s)"
          % (artifact["method"], artifact["method_version"]))
    print("-" * 62)
    print("1 %-9s = %s %s"
          % (artifact["method"], value, display_unit(artifact, spec)))
    print("weight basis: %s   vintage: %s"
          % (artifact["weight_basis"], artifact["weight_vintage_label"]))
    print()
    header = "  code   pop.share    realized@pin   realized@val"
    if has_mult:
        header += "    eff.weight"
    print(header)
    rows = sorted(artifact["basket"],
                  key=lambda r: Decimal(r["realized_weight_at_pin"]), reverse=True)
    for r in rows:
        ps = Decimal(r["population_share"]).quantize(q)
        rp = Decimal(r["realized_weight_at_pin"]).quantize(q)
        rv = Decimal(r["realized_weight_at_valuation"]).quantize(q)
        line = "  %-5s  %9s    %12s   %12s" % (r["code"], ps, rp, rv)
        if has_mult:
            ew = Decimal(r["effective_weight"]).quantize(q)
            line += "  %12s" % ew
        print(line)
    print()
    print("input_digest : %s" % artifact["input_digest"])
    print("artifact_hash: %s" % artifact["artifact_hash"])
    print("-" * 62)
    print("verify_artifact(...) -> %s" % ok)


if __name__ == "__main__":
    import sys
    _demo(sys.argv[1] if len(sys.argv) > 1 else "sample_input.json")
