#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_independent.py -- an INDEPENDENT second implementation of the Worldyard
(formerly openunit) verification procedure.

This verifier is written from the published documents alone -- `SPEC.md`
(method, formulas, verification rules) and `ARTIFACT_FORMAT.md` (byte-level
canonical encoding, hashing, field layout; format `worldyard-artifact-3`,
which accepts every shipped `worldyard-artifact-2` and `openunit-artifact-1`
artifact unchanged). It deliberately
does NOT import `worldyard`, `openunit`, `cli`, or `anchor`, and shares no code
with them: if the engine
were wrong, subtly non-deterministic, or tampered with, this program would
disagree with its output. Standard library only (json, hashlib, decimal,
fractions, sys, argparse).

Usage:
    python3 verify_independent.py <spec.json> <artifact.json>

It re-derives, from the spec alone: every population share, effective weight,
fixed amount, the baseline value, the valuation value, both realized-weight
columns, the conditional multiplier fields, `input_digest`, and
`artifact_hash`. It then compares the fully recomputed artifact against the
published one, field by field. For a spec with a declared numeraire (a
fictional scenario identifier; hypothetical scenarios only) it rebuilds the
source artifact, checks that the spec binds it, and recomputes the two
restated values with exact fractions.

As a library it also recomputes the frozen record of a whole-basket successor
event (`recompute_frozen_record`, `compare_frozen_record`; hypothetical
scenarios only).

A PASS means that the published artifact reproduces from the spec. It does
not mean that the spec's inputs, or a declared rate, are authentic, right or
fair.

Exit status:
    0   the published artifact matches the independent recomputation exactly
        (every field, both hashes)
    1   verification failed; each differing field is listed on stdout
    2   operational error (unreadable file, invalid JSON, malformed spec)

> Don't trust me. Verify me.  -- so here is the second pair of eyes.
"""

import argparse
import hashlib
import json
import sys
import decimal
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from fractions import Fraction

# ARTIFACT_FORMAT.md section 1: exact decimal arithmetic, precision 50,
# ROUND_HALF_EVEN, inside a context that does not leak to the caller and
# takes nothing from the caller either.
DEC_PRECISION = 50


def fixed_context():
    """A new decimal context with every field stated (ARTIFACT_FORMAT.md
    section 1): precision 50, ties to even, the widest exponent range, an
    upper-case exponent letter, no clamping, no flags, and traps on invalid
    operations, division by zero and overflow only. The decimal context of
    whoever calls this program has no influence on any result."""
    return decimal.Context(
        prec=DEC_PRECISION, rounding=ROUND_HALF_EVEN, Emin=-999999,
        Emax=999999, capitals=1, clamp=0, flags=[],
        traps=[decimal.InvalidOperation, decimal.DivisionByZero,
               decimal.Overflow])

# ARTIFACT_FORMAT.md sections 4 and 6: the two accepted method names (the name
# before the rename first: it is also what an absent `method` means).
ACCEPTED_METHODS = ("openunit", "worldyard")


# --- canonical bytes & hashing (ARTIFACT_FORMAT.md sections 2-3) -------------
def canonical_bytes(value):
    """UTF-8 bytes of json.dumps(value, sort_keys=True, separators=(",", ":"),
    ensure_ascii=False) -- the only encoding ever hashed."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return text.encode("utf-8")


def hash_of(value):
    """Lowercase-hex SHA-256 over the canonical bytes, 'sha256:'-prefixed."""
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


# --- exact values and the single rounding (ARTIFACT_FORMAT.md section 1) -----
# The numbers of a declared-numeraire artifact and of a frozen record are
# exact rational expressions over verbatim decimal strings, rounded once.
# This program evaluates them with fractions.Fraction.
def exact_declared(text, what="declared number"):
    """The exact value of a DECLARED number (a declared rate), which must be
    a plain decimal string: 1 to 80 characters, only the ASCII digits and at
    most one '.', a digit first and a digit last, value > 0. ValueError
    otherwise."""
    plain = (isinstance(text, str) and 1 <= len(text) <= 80
             and set(text) <= set("0123456789.") and text.count(".") <= 1
             and text[0] != "." and text[-1] != ".")
    if not plain:
        raise ValueError("%s is not a plain decimal string: %r" % (what, text))
    whole, _, tail = text.partition(".")
    value = Fraction(int(whole + tail), 10 ** len(tail))
    if value <= 0:
        raise ValueError("%s must be > 0: %r" % (what, text))
    return value


def exact_published(text, what="published number"):
    """The exact value of a number an artifact carries (`fixed_amount`,
    `value_usd`, `baseline_value_usd`): finite and >= 0, and, unless it is
    zero, 1E-200 <= x < 1E+201 (the range in which such a number may be used
    exactly). ValueError otherwise."""
    number = Decimal(text)
    if not number.is_finite() or number < 0:
        raise ValueError("%s must be finite and >= 0: %r" % (what, text))
    if number == 0:
        return Fraction(0)
    if not -200 <= number.adjusted() <= 200:
        raise ValueError("%s is outside the supported range: %r"
                         % (what, text))
    return Fraction(number)


def round_once(value):
    """An exact Fraction, rounded once to 50 significant digits (ties to
    even) and written as the decimal string the format uses: the shortest
    form when the value is exact, 50 digits otherwise."""
    with localcontext(fixed_context()):
        return str(Decimal(value.numerator) / Decimal(value.denominator))


def has_currency_code_shape(text):
    """Exactly three upper-case ASCII letters. Shape only; no code list."""
    return (isinstance(text, str) and len(text) == 3
            and all("A" <= ch <= "Z" for ch in text))


def is_fictional_identifier(text):
    """1 to 16 ASCII letters and digits, at least one letter, and not exactly
    three letters: the shape a fictional scenario identifier must have."""
    if not isinstance(text, str) or not 1 <= len(text) <= 16:
        return False
    letters = sum(1 for ch in text if "A" <= ch <= "Z" or "a" <= ch <= "z")
    digits = sum(1 for ch in text if "0" <= ch <= "9")
    if letters + digits != len(text) or letters == 0:
        return False
    return not (len(text) == 3 and letters == 3)


def is_sha256_text(text):
    """'sha256:' followed by 64 lower-case hexadecimal characters."""
    return (isinstance(text, str) and len(text) == 71
            and text[:7] == "sha256:"
            and set(text[7:]) <= set("0123456789abcdef"))


# --- independent recomputation (SPEC.md sections 2.1-2.2, format sec 6-7) ----
def _recompute_undeclared(spec):
    """Derive the complete expected artifact of a spec WITHOUT a declared
    numeraire, using only the published formulas:

        effective_weight_i = (population_i * m_i) / sum_j(population_j * m_j)
        population_share_i = population_i / sum_j(population_j)
        amount_i           = effective_weight_i / fx_baseline_i
        baseline_value     = sum_i(amount_i * fx_baseline_i)    (= 1)
        value              = sum_i(amount_i * fx_valuation_i)
        realized@pin_i     = amount_i * fx_baseline_i / baseline_value
        realized@val_i     = amount_i * fx_valuation_i / value

    The two multiplier fields are emitted only when at least one basket entry
    carries `weight_multiplier` (the backward-compatibility rule). The
    numeraire (absent: "USD") must be three upper-case ASCII letters
    (ARTIFACT_FORMAT.md section 4).
    """
    method = spec.get("method", ACCEPTED_METHODS[0])
    if method not in ACCEPTED_METHODS:
        raise ValueError("spec method must be one of %r, got %r"
                         % (ACCEPTED_METHODS, method))
    numeraire = spec.get("numeraire", "USD")
    if not has_currency_code_shape(numeraire):
        raise ValueError("an undeclared numeraire must be three upper-case "
                         "ASCII letters, got %r" % (numeraire,))
    entries = spec["basket"]
    multipliers_present = any("weight_multiplier" in e for e in entries)

    with localcontext(fixed_context()):
        headcount = Decimal(0)
        weighted_headcount = Decimal(0)
        for e in entries:
            p = Decimal(e["population"])
            if p < 0:
                raise ValueError("population must be >= 0 for %r" % e.get("code"))
            headcount += p
            weighted_headcount += p * Decimal(e.get("weight_multiplier", "1"))
        if headcount <= 0 or weighted_headcount <= 0:
            raise ValueError(
                "spec basket has non-positive total population / effective weight")

        per_entry = []
        baseline_total = Decimal(0)
        valuation_total = Decimal(0)
        for e in entries:
            p = Decimal(e["population"])
            m = Decimal(e.get("weight_multiplier", "1"))
            rate_pin = Decimal(e["fx_baseline_usd_per_unit"])
            rate_val = Decimal(e["fx_valuation_usd_per_unit"])
            if rate_pin <= 0 or rate_val <= 0:
                raise ValueError("non-positive FX rate in spec entry %r"
                                 % e.get("code"))
            share = p / headcount
            eff = (p * m) / weighted_headcount
            qty = eff / rate_pin
            at_pin = qty * rate_pin
            at_val = qty * rate_val
            baseline_total += at_pin
            valuation_total += at_val
            per_entry.append((e, m, share, eff, qty, at_pin, at_val))

        rows = []
        for (e, m, share, eff, qty, at_pin, at_val) in per_entry:
            row = {
                "code": e["code"],
                "name": e.get("name", e["code"]),
                "population_share": str(share),
                "fixed_amount": str(qty),
                "realized_weight_at_pin": str(at_pin / baseline_total),
                "realized_weight_at_valuation": str(at_val / valuation_total),
            }
            if multipliers_present:
                row["weight_multiplier"] = str(m)
                row["effective_weight"] = str(eff)
            rows.append(row)

        body = {
            "method": method,
            "method_version": spec.get("method_version", "v0"),
            "numeraire": numeraire,
            "weight_vintage_label": spec["weight_vintage"]["label"],
            "weight_basis": spec["weight_vintage"]["basis"],
            "baseline_value_usd": str(baseline_total),
            "value_usd": str(valuation_total),
            "basket": rows,
            "input_digest": hash_of(spec),
        }
        expected = dict(body)
        expected["artifact_hash"] = hash_of(body)
        return expected


# --- declared numeraire (ARTIFACT_FORMAT.md sections 4.1 and 6.1) ------------
DECLARATION_KEYS = {"code", "kind", "scenario"}
CONVERSION_KEYS = {"from", "units_of_old_per_new", "source_artifact_hash",
                   "source_input_digest"}


def check_numeraire_declaration(declaration):
    """ValueError unless the object is exactly {"code", "kind", "scenario"}
    with kind "fictional_scenario_identifier", scenario "hypothetical" and a
    fictional identifier as code."""
    if not isinstance(declaration, dict) \
            or set(declaration) != DECLARATION_KEYS:
        raise ValueError("numeraire_declaration must have exactly the keys "
                         "code, kind, scenario")
    if declaration["kind"] != "fictional_scenario_identifier" \
            or declaration["scenario"] != "hypothetical":
        raise ValueError("numeraire_declaration must declare a fictional "
                         "scenario identifier of a hypothetical scenario")
    if not is_fictional_identifier(declaration["code"]):
        raise ValueError("numeraire_declaration.code is not a fictional "
                         "identifier: %r" % (declaration["code"],))


def recompute_artifact(spec):
    """Derive the complete expected artifact from the spec alone.

    Without `numeraire_declaration` and `numeraire_conversion` this is the
    artifact every earlier version of the format defines. With them (both
    are then required) the numeraire is a DECLARED fictional scenario
    identifier, and the artifact restates its source artifact:

        source spec    = the spec without the two keys, numeraire := from
        source         = the artifact of the source spec (undeclared rules);
                         its artifact_hash and input_digest must be the two
                         hashes the conversion object carries
        baseline_value = R50( source.baseline_value_usd / units_of_old_per_new )
        value          = R50( source.value_usd          / units_of_old_per_new )
        basket         = source.basket, unchanged

    R50 = the exact quotient rounded once to 50 significant digits, ties to
    even. Anything malformed raises ValueError (no artifact)."""
    has_declaration = "numeraire_declaration" in spec
    has_conversion = "numeraire_conversion" in spec
    if not has_declaration and not has_conversion:
        return _recompute_undeclared(spec)
    if not (has_declaration and has_conversion):
        raise ValueError("a declared numeraire needs both "
                         "numeraire_declaration and numeraire_conversion")

    declaration = spec["numeraire_declaration"]
    conversion = spec["numeraire_conversion"]
    check_numeraire_declaration(declaration)
    if spec.get("numeraire") != declaration["code"]:
        raise ValueError("numeraire must equal numeraire_declaration.code")
    if not isinstance(conversion, dict) or set(conversion) != CONVERSION_KEYS:
        raise ValueError("numeraire_conversion must have exactly the keys "
                         "from, units_of_old_per_new, source_artifact_hash, "
                         "source_input_digest")
    if not has_currency_code_shape(conversion["from"]):
        raise ValueError("numeraire_conversion.from must be three upper-case "
                         "ASCII letters")
    old_per_new = exact_declared(conversion["units_of_old_per_new"],
                                 "units_of_old_per_new")
    if not is_sha256_text(conversion["source_artifact_hash"]) \
            or not is_sha256_text(conversion["source_input_digest"]):
        raise ValueError("numeraire_conversion hashes must be 'sha256:' plus "
                         "64 lower-case hex characters")

    source_spec = dict(spec)
    del source_spec["numeraire_declaration"]
    del source_spec["numeraire_conversion"]
    source_spec["numeraire"] = conversion["from"]
    source = _recompute_undeclared(source_spec)
    if is_ppp_valued(source_spec):
        raise ValueError("a PPP-valued spec cannot carry a declared "
                         "numeraire (its value is in international dollars)")
    if source["artifact_hash"] != conversion["source_artifact_hash"] \
            or source["input_digest"] != conversion["source_input_digest"]:
        raise ValueError("numeraire_conversion does not bind the source "
                         "artifact")

    body = {
        "method": source["method"],
        "method_version": source["method_version"],
        "numeraire": spec["numeraire"],
        "numeraire_declaration": dict(declaration),
        "numeraire_conversion": dict(conversion),
        "weight_vintage_label": source["weight_vintage_label"],
        "weight_basis": source["weight_basis"],
        "baseline_value": round_once(
            exact_published(source["baseline_value_usd"]) / old_per_new),
        "value": round_once(
            exact_published(source["value_usd"]) / old_per_new),
        "basket": source["basket"],
        "input_digest": hash_of(spec),
    }
    expected = dict(body)
    expected["artifact_hash"] = hash_of(body)
    return expected


# --- whole-basket successor event and frozen record ----------------------------
# (SPEC.md, "Whole-basket successor event"; ARTIFACT_FORMAT.md sections 10-11.)
# Hypothetical scenarios only: the successor is a fictional scenario
# identifier, never a currency code. Recomputing a record shows that its
# arithmetic reproduces; it says nothing about whether a declared rate is
# authentic, right or fair.
FROZEN_RECORD_NOTICE = (
    "Hypothetical scenario record: a thought experiment, not a forecast, a "
    "proposal or an offer of any currency. final_value is the pinned basket "
    "quantities divided by the declared rates; it does not show that the "
    "rates are authentic, right or fair. The comparison block is information "
    "only and depends on the bridge currency.")

EVENT_REQUIRED_KEYS = {"event", "id", "scenario", "successor",
                       "successor_kind", "effective", "units_per_successor"}


def day_number(date):
    """Days from 0001-01-01 (day 1) to the date 'YYYY-MM-DD' of the proleptic
    Gregorian calendar. ValueError unless the text has exactly that form and
    names a real calendar date. Only differences and comparisons of these
    numbers are used."""
    well_formed = (isinstance(date, str) and len(date) == 10
                   and date[4] == "-" and date[7] == "-"
                   and all(ch in "0123456789"
                           for ch in date[:4] + date[5:7] + date[8:]))
    if not well_formed:
        raise ValueError("a date must be 'YYYY-MM-DD': %r" % (date,))
    year, month, day = int(date[:4]), int(date[5:7]), int(date[8:])
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    lengths = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if year < 1 or not 1 <= month <= 12 or not 1 <= day <= lengths[month - 1]:
        raise ValueError("no such date: %r" % (date,))
    past = year - 1
    return (past * 365 + past // 4 - past // 100 + past // 400
            + sum(lengths[:month - 1]) + day)


def check_successor_event(event):
    """ValueError unless `event` is a well-formed whole-basket successor event
    (ARTIFACT_FORMAT.md section 10). Returns the day number of `effective`."""
    if not isinstance(event, dict):
        raise ValueError("the event must be an object")
    keys = set(event)
    if not EVENT_REQUIRED_KEYS <= keys:
        raise ValueError("the event lacks a required key")
    if keys - EVENT_REQUIRED_KEYS - {"declaration"}:
        raise ValueError("the event has a key the format does not define")
    if event["event"] != "whole_basket_successor":
        raise ValueError("event must be 'whole_basket_successor'")
    if not isinstance(event["id"], str) or event["id"] == "":
        raise ValueError("the event id must be a non-empty string")
    if event["scenario"] != "hypothetical":
        raise ValueError("the event scenario must be 'hypothetical'")
    if event["successor_kind"] != "fictional_scenario_identifier":
        raise ValueError("successor_kind must be "
                         "'fictional_scenario_identifier'")
    if not is_fictional_identifier(event["successor"]):
        raise ValueError("the successor is not a fictional identifier: %r"
                         % (event["successor"],))
    effective = day_number(event["effective"])
    table = event["units_per_successor"]
    if not isinstance(table, dict) or len(table) == 0:
        raise ValueError("units_per_successor must be a non-empty object")
    for code in table:
        if not isinstance(code, str) or code == "":
            raise ValueError("a code of units_per_successor is not a "
                             "non-empty string: %r" % (code,))
        if code == event["successor"]:
            raise ValueError("the successor is among the converted codes")
        exact_declared(table[code], "units_per_successor[%s]" % code)
    if "declaration" in event and not isinstance(event["declaration"], dict):
        raise ValueError("the event declaration must be an object")
    return effective


def recompute_frozen_record(spec, event, valuation_date):
    """Derive the complete frozen record (format `worldyard-frozen-record-1`,
    ARTIFACT_FORMAT.md section 11) from a spec, an event and the declared
    valuation date:

        final_value = R50( sum_i  fixed_amount_i / units_per_successor_i )
        bridged     = R50( value_usd / units_per_successor[numeraire] )
        gap         = R50( final_value - bridged )     (the two strings)

    where fixed_amount_i and value_usd are the strings of the artifact this
    program recomputes for the spec, and R50 rounds an exact rational once to
    50 significant digits, ties to even. Anything the format refuses raises
    ValueError: a malformed event, a date that is malformed or not before
    the event, a declared numeraire, a PPP-valued spec, an event that does
    not cover exactly the basket codes, a quantity that is negative or
    outside the supported range."""
    effective = check_successor_event(event)
    if not day_number(valuation_date) < effective:
        raise ValueError("the valuation date must be before the event")
    if not isinstance(spec, dict):
        raise ValueError("the spec must be an object")
    if "numeraire_declaration" in spec or "numeraire_conversion" in spec:
        raise ValueError("a spec with a declared numeraire is not frozen; "
                         "its source spec is")
    artifact = _recompute_undeclared(spec)
    if is_ppp_valued(spec):
        raise ValueError("a PPP-valued spec has no FX valuation leg to "
                         "freeze")

    table = event["units_per_successor"]
    for row in artifact["basket"]:
        if not isinstance(row["code"], str):
            raise ValueError("a basket code is not a string: %r"
                             % (row["code"],))
    in_basket = {row["code"] for row in artifact["basket"]}
    if in_basket != set(table):
        raise ValueError("the event must declare a rate for exactly the "
                         "codes of the basket")

    total = Fraction(0)
    rows = []
    for row in artifact["basket"]:
        rate_text = table[row["code"]]
        total += (exact_published(row["fixed_amount"], "fixed_amount")
                  / exact_declared(rate_text, "units_per_successor"))
        rows.append({"code": row["code"],
                     "fixed_amount": row["fixed_amount"],
                     "units_per_successor": rate_text})
    final_value = round_once(total)

    old_numeraire = artifact["numeraire"]
    if old_numeraire in table:
        bridged = round_once(
            exact_published(artifact["value_usd"], "value_usd")
            / exact_declared(table[old_numeraire], "units_per_successor"))
        comparison = {
            "information_only": True,
            "bridge_code": old_numeraire,
            "bridge_units_per_successor": table[old_numeraire],
            "last_fx_leg_value_bridged": bridged,
            "final_minus_bridged": round_once(
                Fraction(Decimal(final_value)) - Fraction(Decimal(bridged))),
        }
        flags = ["FROZEN_AT_CHANGEOVER"]
    else:
        comparison = None
        flags = ["FROZEN_AT_CHANGEOVER", "NO_BRIDGE_RATE"]

    try:
        event_hash = hash_of(event)
    except TypeError:
        raise ValueError("the event declaration is not plain JSON data")
    body = {
        "format": "worldyard-frozen-record-1",
        "kind": "frozen_fx_leg",
        "state": "frozen_at_changeover",
        "flags": flags,
        "scenario": event["scenario"],
        "notice": FROZEN_RECORD_NOTICE,
        "event_id": event["id"],
        "event_hash": event_hash,
        "successor": event["successor"],
        "successor_kind": event["successor_kind"],
        "effective": event["effective"],
        "source_artifact_hash": artifact["artifact_hash"],
        "source_input_digest": artifact["input_digest"],
        "declared_valuation_date": valuation_date,
        "last_fx_leg_value": artifact["value_usd"],
        "last_fx_leg_numeraire": old_numeraire,
        "basket": rows,
        "final_value": final_value,
        "final_value_numeraire": event["successor"],
        "comparison": comparison,
    }
    expected = dict(body)
    expected["record_hash"] = hash_of(body)
    return expected


# --- field-by-field comparison ------------------------------------------------
def _walk_diffs(expected, published, path, out):
    """Collect every (path, expected, published) difference between the two
    JSON values, recursing into objects and arrays."""
    if isinstance(expected, dict) and isinstance(published, dict):
        for key in sorted(set(expected) | set(published)):
            here = "%s.%s" % (path, key) if path else key
            if key not in published:
                out.append((here, expected[key], "<missing>"))
            elif key not in expected:
                out.append((here, "<unexpected>", published[key]))
            else:
                _walk_diffs(expected[key], published[key], here, out)
    elif isinstance(expected, list) and isinstance(published, list):
        if len(expected) != len(published):
            out.append((path + ".length", len(expected), len(published)))
        for i, (a, b) in enumerate(zip(expected, published)):
            _walk_diffs(a, b, "%s[%d]" % (path, i), out)
    elif expected != published:
        out.append((path, expected, published))


def compare(spec, artifact):
    """Return the list of differences between the independent recomputation
    and the published artifact. Empty list == verified."""
    diffs = []
    expected = recompute_artifact(spec)

    # SPEC.md section 5, condition 1: the artifact must be paired with this spec.
    if artifact.get("input_digest") != expected["input_digest"]:
        diffs.append(("input_digest (sha256 of canonical spec)",
                      expected["input_digest"], artifact.get("input_digest")))

    # SPEC.md section 5, condition 2: internal integrity of the published file
    # (hash of the published artifact minus its own artifact_hash key).
    claimed = {k: v for k, v in artifact.items() if k != "artifact_hash"}
    if hash_of(claimed) != artifact.get("artifact_hash"):
        diffs.append(("artifact_hash (internal integrity)",
                      hash_of(claimed), artifact.get("artifact_hash")))

    # SPEC.md section 5, condition 3: full reproduction, every field.
    _walk_diffs(expected, artifact, "", diffs)

    # de-duplicate while preserving order (a tampered hash can trip two checks)
    seen, unique = set(), []
    for d in diffs:
        k = repr(d)
        if k not in seen:
            seen.add(k)
            unique.append(d)
    return unique


def compare_frozen_record(spec, event, record):
    """Return the list of differences between a published frozen record and
    its independent recomputation. Empty list == the record reproduces.

    A malformed spec or event raises ValueError, as compare() does. Whatever
    is wrong with the RECORD is reported as a difference: a record that is
    not an object; a `declared_valuation_date` that is missing, malformed or
    not before the event's `effective` date (one entry, nothing is
    recomputed); a `record_hash` that is not the hash of the rest of the
    record; and every field that differs from the recomputation, missing and
    unexpected keys included."""
    effective = check_successor_event(event)
    if not isinstance(record, dict):
        return [("record", "an object", record)]
    date = record.get("declared_valuation_date")
    try:
        dated_before = day_number(date) < effective
    except ValueError:
        dated_before = False
    if not dated_before:
        return [("declared_valuation_date",
                 "a date 'YYYY-MM-DD' before %s" % event["effective"], date)]

    diffs = []
    expected = recompute_frozen_record(spec, event, date)

    # internal integrity of the published record
    claimed = {k: v for k, v in record.items() if k != "record_hash"}
    try:
        own_hash = hash_of(claimed)
    except (TypeError, ValueError):
        own_hash = "<the record is not plain JSON data>"
    if own_hash != record.get("record_hash"):
        diffs.append(("record_hash (internal integrity)", own_hash,
                      record.get("record_hash")))

    # full reproduction, every field
    _walk_diffs(expected, record, "", diffs)

    seen, unique = set(), []
    for d in diffs:
        k = repr(d)
        if k not in seen:
            seen.add(k)
            unique.append(d)
    return unique


# --- display only (SPEC.md section 2.3; never hashed) -------------------------
def is_ppp_valued(spec):
    """True iff every basket entry records `ppp_factor_lcu_per_intl_usd` and
    its `fx_valuation_usd_per_unit` equals 1 / that factor exactly: a PPP
    valuation leg, whose value is read in international dollars although the
    hashed `numeraire` stays "USD" (SPEC.md section 2.3)."""
    basket = spec.get("basket") or []
    if not basket:
        return False
    with localcontext(fixed_context()):
        for entry in basket:
            factor = entry.get("ppp_factor_lcu_per_intl_usd")
            if factor is None:
                return False
            try:
                one_over = Decimal(1) / Decimal(factor)
                if one_over != Decimal(entry["fx_valuation_usd_per_unit"]):
                    return False
            except (ArithmeticError, KeyError, TypeError, ValueError):
                return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="verify_independent.py",
        description="Independently re-verify a Worldyard (or openunit) "
                    "artifact against its spec, from the published format "
                    "documents alone (no engine import). Exit 0 iff every "
                    "field matches.")
    parser.add_argument("spec", help="path to spec.json (the hashed input)")
    parser.add_argument("artifact", help="path to artifact.json (the published "
                                         "result)")
    args = parser.parse_args(argv)

    try:
        with open(args.spec, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
        with open(args.artifact, "r", encoding="utf-8") as fh:
            artifact = json.load(fh)
        diffs = compare(spec, artifact)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("ERROR: %s" % exc)
        return 2

    if diffs:
        print("INDEPENDENT VERIFICATION: FAIL  (%d field(s) differ)"
              % len(diffs))
        for where, want, got in diffs:
            print("  field    : %s" % where)
            print("    expected : %s" % (want,))
            print("    published: %s" % (got,))
        return 1

    print("INDEPENDENT VERIFICATION: PASS")
    print("  spec          : %s" % args.spec)
    print("  artifact      : %s" % args.artifact)
    print("  input_digest  : %s" % artifact["input_digest"])
    print("  artifact_hash : %s" % artifact["artifact_hash"])
    unit = artifact["numeraire"]
    if "numeraire_declaration" in artifact:
        # a declared numeraire: the value field is `value`, and the unit is
        # a fictional scenario identifier (hypothetical scenarios only)
        print("  value         : %s %s (fictional scenario identifier, not "
              "a currency)" % (artifact["value"], unit))
        return 0
    if unit == "USD" and is_ppp_valued(spec):
        unit = "international $ (numeraire field: USD)"
    print("  value_usd     : %s %s" % (artifact["value_usd"], unit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
