#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_changeover.py -- a hypothetical scenario: every currency of the basket is
converted into one successor unit on one date (a "whole-basket successor
event"). The tests pin the declared-numeraire readout, the frozen record, the
resolver rule, the information-only rate comparison and the independent
recomputation.

Framing (read first):
  - This is a hypothetical scenario, a thought experiment. It is not a
    forecast, not a proposal of any currency, and not an offer of anything.
  - "W" is a fictional scenario identifier. It is not a currency code.
  - Every number, date and rate below is illustrative and invented for the
    tests. None is a real exchange rate, PPP factor or announced decision.
    One fixture reuses the DIGITS of the 1998 euro conversion rates (Council
    Regulation (EC) No 2866/98) only as realistic six-significant-figure
    numbers that do not divide evenly; the event it belongs to is fictional.
  - A passing test shows that a record reproduces from its inputs. It does
    not show that a declared rate is authentic, right or fair.

Expected values are exact: they are compared as strings or as Fractions,
never as floats.

Standalone (`python3 test_changeover.py`) and pytest compatible.
"""

import copy
import decimal
import json
import os
import random
import subprocess
import sys
import tempfile
from decimal import Decimal
from fractions import Fraction

import worldyard
import verify_independent

HERE = os.path.dirname(os.path.abspath(__file__))


# --- fixtures (illustrative values; none is real data) -------------------------
# Populations sum to 1000 and the rates are chosen so that weights, pinned
# quantities and values are exact decimals:
#   pinned quantities = 0.1, 0.08, 2.8, 3.125, 0.02, 32
#   value at the valuation rates = 0.92453125 (USD)
SPEC_USD = {
    "method": "worldyard", "method_version": "v0.4", "numeraire": "USD",
    "weight_vintage": {"label": "hypothetical-test", "basis": "population_share",
                       "note": "illustrative inputs for a hypothetical "
                               "scenario test; not real data"},
    "basket": [
        {"code": "USD", "population": "100",
         "fx_baseline_usd_per_unit": "1", "fx_valuation_usd_per_unit": "1"},
        {"code": "EUR", "population": "100",
         "fx_baseline_usd_per_unit": "1.25", "fx_valuation_usd_per_unit": "1.25"},
        {"code": "CNY", "population": "350",
         "fx_baseline_usd_per_unit": "0.125", "fx_valuation_usd_per_unit": "0.1"},
        {"code": "JPY", "population": "25",
         "fx_baseline_usd_per_unit": "0.008",
         "fx_valuation_usd_per_unit": "0.00625"},
        {"code": "GBP", "population": "25",
         "fx_baseline_usd_per_unit": "1.25", "fx_valuation_usd_per_unit": "1.25"},
        {"code": "INR", "population": "400",
         "fx_baseline_usd_per_unit": "0.0125",
         "fx_valuation_usd_per_unit": "0.0125"},
    ],
}

# A declared whole-basket successor event. "units_per_successor": old units
# per 1 successor unit (like BGN 1.95583 = EUR 1). The date is fictional, not
# a forecast.
EVENT = {
    "event": "whole_basket_successor",
    "id": "hypothetical-W-test-1",
    "scenario": "hypothetical",
    "successor": "W",
    "successor_kind": "fictional_scenario_identifier",
    "effective": "2100-01-01",
    "units_per_successor": {"USD": "1.25", "EUR": "1", "CNY": "10",
                            "JPY": "200", "GBP": "0.8", "INR": "100"},
}
EVENT_HASH = ("sha256:ff43b2b379004b197eb74cd3ba0ed590b88b1ef20c42e821507a06"
              "4aa27a0c17")
VALUATION_DATE = "2099-12-31"      # the FX-leg valuation date of SPEC_USD

# Rates that do not divide evenly. EVENT_SIX reuses the DIGITS of the 1998
# euro conversion rates (Council Regulation (EC) No 2866/98) only as
# realistic six-significant-figure numbers; the event itself is fictional.
EVENT_SIX = dict(EVENT, id="hypothetical-W-test-2",
                 units_per_successor={"USD": "1.95583", "EUR": "0.787564",
                                      "CNY": "6.55957", "JPY": "166.386",
                                      "GBP": "13.7603", "INR": "40.3399"})
EVENT_AWKWARD = dict(EVENT, id="hypothetical-W-test-3",
                     units_per_successor={"USD": "3", "EUR": "7", "CNY": "0.3",
                                          "JPY": "13.7603", "GBP": "0.0009",
                                          "INR": "1936.27"})

FROZEN_NOTICE = (
    "Hypothetical scenario record: a thought experiment, not a forecast, a "
    "proposal or an offer of any currency. final_value is the pinned basket "
    "quantities divided by the declared rates; it does not show that the "
    "rates are authentic, right or fair. The comparison block is information "
    "only and depends on the bridge currency.")

# How the fictional numeraire W is declared in a spec.
W_DECLARATION = {"code": "W", "kind": "fictional_scenario_identifier",
                 "scenario": "hypothetical"}

SRC_ARTIFACT_HASH = ("sha256:1718ce9d9498f64552d2dab4f5b8f11905cea9a45bd48f77"
                     "065ff27189e43189")
SRC_INPUT_DIGEST = ("sha256:53aa2053116a7b2ec27c8635ae04b11459c833d631f91986"
                    "1131800a72eebd33")


# The whole frozen record of the exact fixture, as it must be, key for key:
#   0.1/1.25 + 0.08/1 + 2.8/10 + 3.125/200 + 0.02/0.8 + 32/100 = 0.800625
#   0.92453125 / 1.25 = 0.739625        0.800625 - 0.739625 = 0.061
EXPECTED_FROZEN = {
    "format": "worldyard-frozen-record-1",
    "kind": "frozen_fx_leg",
    "state": "frozen_at_changeover",
    "flags": ["FROZEN_AT_CHANGEOVER"],
    "scenario": "hypothetical",
    "notice": FROZEN_NOTICE,
    "event_id": "hypothetical-W-test-1",
    "event_hash": EVENT_HASH,
    "successor": "W",
    "successor_kind": "fictional_scenario_identifier",
    "effective": "2100-01-01",
    "source_artifact_hash": SRC_ARTIFACT_HASH,
    "source_input_digest": SRC_INPUT_DIGEST,
    "declared_valuation_date": "2099-12-31",
    "last_fx_leg_value": "0.92453125",
    "last_fx_leg_numeraire": "USD",
    "basket": [
        {"code": "USD", "fixed_amount": "0.1", "units_per_successor": "1.25"},
        {"code": "EUR", "fixed_amount": "0.08", "units_per_successor": "1"},
        {"code": "CNY", "fixed_amount": "2.8", "units_per_successor": "10"},
        {"code": "JPY", "fixed_amount": "3.125", "units_per_successor": "200"},
        {"code": "GBP", "fixed_amount": "0.02", "units_per_successor": "0.8"},
        {"code": "INR", "fixed_amount": "32", "units_per_successor": "100"},
    ],
    "final_value": "0.800625",
    "final_value_numeraire": "W",
    "comparison": {
        "information_only": True,
        "bridge_code": "USD",
        "bridge_units_per_successor": "1.25",
        "last_fx_leg_value_bridged": "0.739625",
        "final_minus_bridged": "0.061",
    },
    "record_hash": ("sha256:046a68629bc2a04c9bc67c4e9acb729ea4d6588c24c8258c"
                    "8154878769124e15"),
}

# Six-significant-figure rates: the exact sum is this fraction; the record
# carries its 50-significant-digit rounding (ties to even).
SIX_EXACT = Fraction(324998693014926737430846021869425,
                     233298442807885135774037893098282)
SIX_FINAL = "1.3930598468784219051669093597680785533906689928212"
SIX_RECORD_HASH = ("sha256:2511f81a81c7554bab2dbd063fe8f9e61767d4323bebde881"
                   "bc3ad197e158207")


def _load(*parts):
    with open(os.path.join(HERE, *parts), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _self_hash_ok(record, field):
    body = {k: v for k, v in record.items() if k != field}
    return record.get(field) == worldyard.sha256(body)


def _rehashed(record):
    """The record with its record_hash recomputed (what a forger would do)."""
    out = {k: v for k, v in record.items() if k != "record_hash"}
    out["record_hash"] = worldyard.sha256(out)
    return out


def _exact_frozen_sum(artifact, event):
    """The exact value of the basket at the declared rates, as a Fraction."""
    return sum(Fraction(r["fixed_amount"])
               / Fraction(event["units_per_successor"][r["code"]])
               for r in artifact["basket"])


def _cli_verify(spec, artifact):
    """Run `verify_independent.py spec.json artifact.json` on the two objects;
    return (exit code, stdout)."""
    with tempfile.TemporaryDirectory() as tmp:
        sp = os.path.join(tmp, "spec.json")
        ap = os.path.join(tmp, "artifact.json")
        with open(sp, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, ensure_ascii=False)
        with open(ap, "w", encoding="utf-8") as fh:
            json.dump(artifact, fh, ensure_ascii=False)
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "verify_independent.py"),
             sp, ap], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return proc.returncode, proc.stdout.decode("utf-8")


# --- test-side rounding: integer arithmetic only --------------------------------
# The expected values below never come out of the decimal module: an exact
# Fraction is rounded here with integers alone, so the tests share no rounding
# or formatting code with the engine or with the independent verifier.
def _round50_parts(fr):
    """(sign, coefficient, exponent) of the exact Fraction `fr` rounded once
    to 50 significant digits, ties to even: sign * coefficient * 10**exponent.
    An exact value keeps only the digits it needs (but an exact integer keeps
    exponent 0); a rounded value has 50 digits."""
    if fr == 0:
        return (1, 0, 0)
    sign = -1 if fr < 0 else 1
    n, d = abs(fr.numerator), fr.denominator
    e = 0                       # find e with 10^49 <= (n/d) * 10^e < 10^50
    while n * 10 ** max(e, 0) < d * 10 ** (49 + max(-e, 0)):
        e += 1
    while n * 10 ** max(e, 0) >= d * 10 ** (50 + max(-e, 0)):
        e -= 1
    num, den = n * 10 ** max(e, 0), d * 10 ** max(-e, 0)
    q, r = divmod(num, den)
    exact = r == 0
    if 2 * r > den or (2 * r == den and q % 2 == 1):
        q += 1
    exp = -e
    if q == 10 ** 50:           # 99...9 rounded up
        q, exp = 10 ** 49, exp + 1
    if exact:
        while exp < 0 and q % 10 == 0:
            q, exp = q // 10, exp + 1
    return (sign, q, exp)


def _round50(fr):
    """The rounded value as a Fraction."""
    sign, q, exp = _round50_parts(fr)
    return sign * q * Fraction(10) ** exp


def _round50_text(fr):
    """The rounded value as the decimal string the format uses: plain
    notation unless the exponent is positive or the value is below 1E-6."""
    sign, q, exp = _round50_parts(fr)
    digits = str(q)
    adjusted = exp + len(digits) - 1
    if exp <= 0 and adjusted >= -6:
        if exp == 0:
            body = digits
        elif len(digits) > -exp:
            body = digits[:exp] + "." + digits[exp:]
        else:
            body = "0." + "0" * (-exp - len(digits)) + digits
    else:
        body = digits[0] + ("." + digits[1:] if len(digits) > 1 else "") \
            + "E%+d" % adjusted
    return ("-" if sign < 0 else "") + body


def _raises_value_error(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError:
        return True
    return False


def _leaf_paths(obj, prefix=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaf_paths(v, prefix + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _leaf_paths(v, prefix + (i,))
    else:
        yield prefix


def _tampered(obj, path):
    """A copy of `obj` with the one leaf at `path` changed."""
    bad = copy.deepcopy(obj)
    node = bad
    for k in path[:-1]:
        node = node[k]
    old = node[path[-1]]
    if isinstance(old, bool):
        node[path[-1]] = not old
    elif isinstance(old, str):
        node[path[-1]] = old + "9"
    else:
        node[path[-1]] = "x"
    return bad


# --- the single rounding ---------------------------------------------------------
# (numerator, denominator, expected string, why)
ROUNDING_TABLE = [
    (1281, 1600, "0.800625", "exact: shortest form"),
    (128100, 160000, "0.800625", "not reduced: same string"),
    (10 ** 50 + 5, 10 ** 50,
     "1.0000000000000000000000000000000000000000000000000",
     "half-way, kept digit 0 (even): stays"),
    (10 ** 50 + 15, 10 ** 50,
     "1.0000000000000000000000000000000000000000000000002",
     "half-way, kept digit 1 (odd): up"),
    (10 ** 50 + 25, 10 ** 50,
     "1.0000000000000000000000000000000000000000000000002",
     "half-way, kept digit 2 (even): stays"),
    (10 ** 51 + 51, 10 ** 51,
     "1.0000000000000000000000000000000000000000000000001",
     "just above half-way"),
    (10 ** 51 + 49, 10 ** 51,
     "1.0000000000000000000000000000000000000000000000000",
     "just below half-way"),
    (1, 3, "0.33333333333333333333333333333333333333333333333333", ""),
    (2, 3, "0.66666666666666666666666666666666666666666666666667", ""),
    (0, 7, "0", "zero"),
    (-61, 1000, "-0.061", "a difference can be negative"),
    (-2, 3, "-0.66666666666666666666666666666666666666666666666667",
     "rounding is symmetric"),
    (-(10 ** 50 + 15), 10 ** 50,
     "-1.0000000000000000000000000000000000000000000000002",
     "negative half-way: to even, not toward zero"),
    (5, 10 ** 9, "5E-9", "exponent notation below 1E-6"),
    (1, 10 ** 6, "0.000001", "the smallest value in plain notation"),
    (1, 10 ** 7, "1E-7", ""),
    (6400, 100, "64", "an exact integer has no exponent"),
    (600, 1, "600", "trailing zeros of an integer are kept"),
    (10 ** 60, 1,
     "1.0000000000000000000000000000000000000000000000000E+60",
     "more than 50 integer digits"),
    (10 ** 50 - 1, 10 ** 50,
     "0.99999999999999999999999999999999999999999999999999",
     "fifty nines are exact"),
    (10 ** 51 - 1, 10 ** 51, "1.0000000000000000000000000000000000000000000000000",
     "fifty-one nines round up to 1 with 50 digits"),
    (10 ** 51 - 5, 10 ** 51, "1.0000000000000000000000000000000000000000000000000",
     "half-way below 1: the even neighbour is 1"),
    (10 ** 51 - 15, 10 ** 51,
     "0.99999999999999999999999999999999999999999999999998",
     "half-way, kept digit 9 would be odd: to the even 8"),
]


def test_rounding_table():
    """Every new number is an exact rational rounded ONCE to 50 significant
    digits, ties to even. The engine works on integer pairs, the verifier on
    Fractions; both must give these strings, and so must the integer-only
    rounding of this file."""
    for p, q, want, why in ROUNDING_TABLE:
        assert worldyard._round50(p, q) == want, (p, q, why)
        assert verify_independent.round_once(Fraction(p, q)) == want, (p, q)
        assert _round50_text(Fraction(p, q)) == want, (p, q, why)
        if want != "0":
            assert Fraction(want) == _round50(Fraction(p, q)), (p, q)
    assert _raises_value_error(worldyard._round50, 1, 0)
    assert _raises_value_error(worldyard._round50, 1, -3)


def test_rounding_agrees_on_random_fractions_and_on_ties():
    """Three routes, one string: integer pairs through Decimal (engine),
    Fraction through Decimal (verifier), integers only (this file)."""
    rng = random.Random(20261117)
    cases = []
    for _ in range(1500):
        p = rng.randrange(-10 ** rng.randrange(1, 130), 10 ** rng.randrange(1, 130))
        q = rng.randrange(1, 10 ** rng.randrange(1, 130))
        cases.append((p, q))
    for _ in range(500):            # exact half-way cases at the 50th digit
        c = rng.randrange(10 ** 49, 10 ** 50)
        k = rng.randrange(0, 120)
        sign = rng.choice((1, -1))
        cases.append((sign * (2 * c + 1), 2 * 10 ** k))
        want = c + (c % 2)          # the even neighbour
        got = Fraction(worldyard._round50(sign * (2 * c + 1), 2 * 10 ** k))
        assert got == sign * Fraction(want, 10 ** k), (c, k)
    for _ in range(300):            # values with few digits (exact results)
        cases.append((rng.randrange(-10 ** 12, 10 ** 12),
                      2 ** rng.randrange(0, 40) * 5 ** rng.randrange(0, 40)))
    for p, q in cases:
        fr = Fraction(p, q)
        want = _round50_text(fr)
        assert worldyard._round50(p, q) == want, (p, q)
        assert worldyard._round50(7 * p, 7 * q) == want, (p, q)   # unreduced
        assert verify_independent.round_once(fr) == want, (p, q)
    assert len(cases) == 2300


# --- declared numbers and numbers read back from an artifact -----------------------
BAD_DECLARED = (
    " 1.25", "1.25 ", "1.25\n", "\t1.25", "+1.25", "-1.25", "1_000", "1E+2",
    "1e2", "1.25e0", "\uff11.\uff12\uff15", "\u0661\u0662", "\u00b2", ".5",
    "5.", ".", "", "1.2.3", "1..2", "1,25", "1 000", "1/2", "0x10", "0", "0.0",
    "000", "00.000", "9" * 81, "0." + "0" * 78 + "1", "NaN", "nan", "Infinity",
    "inf", "1.25\x00", 1.25, 1, True, None, ["1.25"], b"1.25",
    Decimal("1.25"), Fraction(5, 4))
GOOD_DECLARED = (
    ("1", Fraction(1)), ("1.25", Fraction(5, 4)),
    ("0.000001", Fraction(1, 10 ** 6)), ("1936.27", Fraction(193627, 100)),
    ("01.250", Fraction(5, 4)), ("9" * 80, Fraction(10 ** 80 - 1)),
    ("0." + "0" * 77 + "1", Fraction(1, 10 ** 78)), ("0.1", Fraction(1, 10)),
    ("10", Fraction(10)), ("1.95583", Fraction(195583, 100000)))


def test_declared_number_grammar():
    """A declared number is kept verbatim in records, so its form is
    restricted: ASCII digits with at most one '.', a digit first and last,
    no sign, no exponent, no spaces, at most 80 characters, and > 0.
    (decimal.Decimal alone would also accept ' 1.25', '+1.25', '1_000',
    '1E+2' and digits of other scripts.)"""
    for text in BAD_DECLARED:
        assert _raises_value_error(worldyard._declared, text, "rate"), text
        assert _raises_value_error(verify_independent.exact_declared,
                                   text), text
    for text, value in GOOD_DECLARED:
        n, d = worldyard._declared(text, "rate")
        assert d > 0 and Fraction(n, d) == value, text
        assert verify_independent.exact_declared(text) == value, text


def test_numbers_read_back_from_an_artifact_have_a_supported_range():
    """A number the artifact builder wrote is used exactly only if it is
    zero or 1E-200 <= x < 1E+201 (never negative, never NaN or infinite)."""
    good = (("0", 0), ("0E+3", 0), ("0E-999999", 0), ("-0", 0),
            ("1", 1), ("1.000000", 1), ("6E+1", 60), ("0.800625",
                                                       Fraction(1281, 1600)),
            ("1E-200", Fraction(1, 10 ** 200)),
            ("9.99E+200", Fraction(999 * 10 ** 198)),
            ("1.0E-200", Fraction(1, 10 ** 200)))
    for text, value in good:
        n, d = worldyard._engine_number(text, "x")
        assert d > 0 and Fraction(n, d) == value, text
        assert verify_independent.exact_published(text) == value, text
    for text in ("1E+201", "9.99E-201", "1E+999999", "1E-999999", "-1",
                 "-1E-300", "NaN", "sNaN", "Infinity", "-Infinity"):
        assert _raises_value_error(worldyard._engine_number, text, "x"), text
        assert _raises_value_error(verify_independent.exact_published,
                                   text), text


# --- identifiers -----------------------------------------------------------------
def test_identifier_shapes():
    """A conventional code is exactly three upper-case ASCII letters. A
    fictional identifier is 1-16 ASCII letters and digits with at least one
    letter and is never exactly three letters, so neither can be taken for
    the other. Only shapes are checked; no list of codes is consulted."""
    fictional = ("W", "w", "W1", "WX", "World2100", "W" * 16, "A1B", "1W",
                 "x9", "ABCD", "ab", "a2c")
    not_fictional = ("WLD", "wld", "Wld", "USD", "XTS", "", "W-1", "W 1",
                     "W_1", "840", "9", "W" * 17, "\uff37", "\u00df", "W\n",
                     " W", "W.", "\u0661", "W\u00e9", 7, None, ["W"], b"W")
    for text in fictional:
        assert worldyard._is_fictional_identifier(text), text
        assert verify_independent.is_fictional_identifier(text), text
        assert not worldyard._is_conventional_code(text), text
        assert not verify_independent.has_currency_code_shape(text), text
    for text in not_fictional:
        assert not worldyard._is_fictional_identifier(text), text
        assert not verify_independent.is_fictional_identifier(text), text
    for text in ("USD", "EUR", "XDR", "XTS", "WLD", "AAA"):
        assert worldyard._is_conventional_code(text), text
        assert verify_independent.has_currency_code_shape(text), text
    for text in ("usd", "Usd", "US", "USDX", "", "U$D", "US1", "\uff35\uff33\uff24",
                 "\u00c4BC", "W", 12345, None, ["USD"], b"USD"):
        assert not worldyard._is_conventional_code(text), text
        assert not verify_independent.has_currency_code_shape(text), text
    h = "sha256:" + "0123456789abcdef" * 4
    for text, ok in ((h, True), (h.upper(), False), (h[:-1], False),
                     (h + "0", False), ("sha1:" + h[5:], False),
                     (h[:-1] + "g", False), (h[:-1] + "A", False),
                     (" " + h[1:], False), (None, False), (7, False)):
        assert worldyard._is_hash(text) is ok, text
        assert verify_independent.is_sha256_text(text) is ok, text


# --- the fixture itself -----------------------------------------------------------
def test_fixture_is_exact():
    """The illustrative inputs give exact decimals, so the tests that use them
    pin behaviour; the rounding rule is pinned by the other fixtures."""
    art = worldyard.build_artifact(SPEC_USD)
    amounts = {r["code"]: Fraction(r["fixed_amount"]) for r in art["basket"]}
    assert amounts == {"USD": Fraction("0.1"), "EUR": Fraction("0.08"),
                       "CNY": Fraction("2.8"), "JPY": Fraction("3.125"),
                       "GBP": Fraction("0.02"), "INR": Fraction("32")}
    assert art["baseline_value_usd"] == "1.000000"
    assert art["value_usd"] == "0.92453125"
    assert art["artifact_hash"] == SRC_ARTIFACT_HASH
    assert art["input_digest"] == SRC_INPUT_DIGEST
    assert verify_independent.recompute_artifact(SPEC_USD) == art
    assert sum(amounts[c] / Fraction(u)
               for c, u in EVENT["units_per_successor"].items()) \
        == Fraction("0.800625")


# --- a declared numeraire ----------------------------------------------------------
W_INPUT_DIGEST = ("sha256:676c6dda30505922c831776caa964725d4e2e25803a68a6d0e"
                  "afb6c5e7747115")
W_ARTIFACT_HASH = ("sha256:482f2276034e0133c00059d0fee485ec1b2bfa15f641dbe4d"
                   "d48616f74e39892")


def _spec_w(rate="1.25"):
    art = worldyard.build_artifact(SPEC_USD)
    return worldyard.redenominate(SPEC_USD, art, W_DECLARATION, rate)


def test_declared_numeraire_w_keeps_basket_quantities():
    art_usd = worldyard.build_artifact(SPEC_USD)
    # declared, fictional: 1 W = 1.25 USD
    spec_w = worldyard.redenominate(SPEC_USD, art_usd, W_DECLARATION,
                                    units_of_old_per_new="1.25")
    art_w = worldyard.build_artifact(spec_w)

    assert art_w["numeraire"] == "W"
    assert spec_w["numeraire_declaration"] == W_DECLARATION
    assert spec_w["numeraire_conversion"] == {
        "from": "USD", "units_of_old_per_new": "1.25",
        "source_artifact_hash": SRC_ARTIFACT_HASH,
        "source_input_digest": SRC_INPUT_DIGEST}
    # the spec differs from its source in exactly these three keys
    restored = {k: v for k, v in spec_w.items()
                if k not in ("numeraire_declaration", "numeraire_conversion")}
    restored["numeraire"] = "USD"
    assert restored == SPEC_USD
    # the unit is the same basket: the rows do not move at all ...
    assert art_w["basket"] == art_usd["basket"]
    # ... the value fields are read in W: the published values / 1.25 ...
    assert art_w["baseline_value"] == "0.8"
    assert art_w["value"] == "0.739625"
    assert "value_usd" not in art_w and "baseline_value_usd" not in art_w
    # ... and the artifact says what its numeraire is and where it comes from
    assert art_w["numeraire_declaration"] == W_DECLARATION
    assert art_w["numeraire_conversion"] == spec_w["numeraire_conversion"]
    assert sorted(art_w) == sorted([
        "method", "method_version", "numeraire", "numeraire_declaration",
        "numeraire_conversion", "weight_vintage_label", "weight_basis",
        "baseline_value", "value", "basket", "input_digest", "artifact_hash"])
    for key in ("method", "method_version", "weight_vintage_label",
                "weight_basis"):
        assert art_w[key] == art_usd[key], key
    assert art_w["input_digest"] == W_INPUT_DIGEST == worldyard.sha256(spec_w)
    assert art_w["artifact_hash"] == W_ARTIFACT_HASH
    # the input spec in USD is untouched, and nothing is shared with it
    assert SPEC_USD["numeraire"] == "USD"
    assert "numeraire_declaration" not in SPEC_USD
    spec_w["basket"][0]["population"] = "999"
    spec_w["numeraire_declaration"]["code"] = "V"
    assert SPEC_USD["basket"][0]["population"] == "100"
    assert W_DECLARATION["code"] == "W"
    spec_w = _spec_w()
    # both verifiers agree on the re-denominated artifact
    assert worldyard.verify_artifact(art_w, spec_w) is True
    assert verify_independent.compare(spec_w, art_w) == []
    assert verify_independent.recompute_artifact(spec_w) == art_w
    # helpers that read the value field
    assert worldyard.artifact_value(art_w) == "0.739625"
    assert worldyard.artifact_value(art_usd) == "0.92453125"
    # the frozen record's bridged value is this artifact's value, byte for byte
    rec = worldyard.freeze_fx_leg(SPEC_USD, EVENT, VALUATION_DATE)
    assert rec["comparison"]["last_fx_leg_value_bridged"] == art_w["value"]


def test_declared_artifact_is_deterministic_and_plain_json():
    spec_w = _spec_w()
    art_w = worldyard.build_artifact(spec_w)
    before = copy.deepcopy(spec_w)
    assert worldyard.build_artifact(copy.deepcopy(spec_w)) == art_w
    assert spec_w == before                              # input not mutated
    assert json.loads(json.dumps(art_w)) == art_w
    assert worldyard.build_artifact(json.loads(json.dumps(spec_w))) == art_w
    # the order of the keys of the spec does not matter
    shuffled = dict(reversed(list(spec_w.items())))
    shuffled["numeraire_conversion"] = dict(
        reversed(list(spec_w["numeraire_conversion"].items())))
    assert worldyard.build_artifact(shuffled) == art_w
    assert verify_independent.recompute_artifact(shuffled) == art_w
    # the artifact does not alias the spec's objects
    art_w["numeraire_declaration"]["code"] = "V"
    art_w["numeraire_conversion"]["from"] = "EUR"
    assert spec_w == before
    # the command-line verifier accepts it and prints the value in W
    art_w = worldyard.build_artifact(spec_w)
    code, out = _cli_verify(spec_w, art_w)
    assert code == 0, out
    assert "0.739625 W (fictional scenario identifier, not a currency)" in out
    bad = dict(art_w, value="0.739626")
    assert _cli_verify(spec_w, bad)[0] == 1
    relabel = dict(SPEC_USD, numeraire="W")
    assert _cli_verify(relabel, art_w)[0] == 2           # no artifact at all


def test_a_relabelled_spec_is_not_a_declared_numeraire():
    """Only renaming the numeraire (and even adding the declaration) is
    rejected: without the conversion the values would still be USD values."""
    spec_w = _spec_w()
    relabel = copy.deepcopy(SPEC_USD)
    relabel["numeraire"] = "W"
    with_decl = dict(relabel, numeraire_declaration=W_DECLARATION)
    only_conv = {k: v for k, v in spec_w.items()
                 if k != "numeraire_declaration"}
    no_numeraire = {k: v for k, v in spec_w.items() if k != "numeraire"}
    wrong_code = dict(spec_w, numeraire="V")
    usd_declared = dict(spec_w, numeraire="USD")
    edited = copy.deepcopy(spec_w)                 # the basket was edited
    edited["basket"][0]["population"] = "101"
    reordered = copy.deepcopy(spec_w)              # two entries swapped
    reordered["basket"][0], reordered["basket"][1] = \
        reordered["basket"][1], reordered["basket"][0]
    padded = copy.deepcopy(spec_w)                 # an empty entry appended
    padded["basket"].append({"code": "XXX", "population": "0",
                             "fx_baseline_usd_per_unit": "1",
                             "fx_valuation_usd_per_unit": "1"})
    renamed = copy.deepcopy(spec_w)                # provenance edited
    renamed["weight_vintage"]["note"] = "another note"
    wrong_hash = copy.deepcopy(spec_w)
    wrong_hash["numeraire_conversion"]["source_artifact_hash"] = \
        "sha256:" + "0" * 64
    wrong_digest = copy.deepcopy(spec_w)
    wrong_digest["numeraire_conversion"]["source_input_digest"] = \
        "sha256:" + "0" * 64
    swapped = copy.deepcopy(spec_w)                # the two hashes exchanged
    swapped["numeraire_conversion"]["source_artifact_hash"] = SRC_INPUT_DIGEST
    swapped["numeraire_conversion"]["source_input_digest"] = SRC_ARTIFACT_HASH
    wrong_from = copy.deepcopy(spec_w)
    wrong_from["numeraire_conversion"]["from"] = "EUR"
    chained = copy.deepcopy(spec_w)                # "from" another fiction
    chained["numeraire_conversion"]["from"] = "V"
    extra_key = copy.deepcopy(spec_w)
    extra_key["numeraire_conversion"]["note"] = "x"
    bad = [relabel, with_decl, only_conv, no_numeraire, wrong_code,
           usd_declared, edited, reordered, padded, renamed, wrong_hash,
           wrong_digest, swapped, wrong_from, chained, extra_key]
    for value in (None, "W", ["W"], 7):            # objects of another type
        bad.append(dict(spec_w, numeraire_declaration=value))
        bad.append(dict(spec_w, numeraire_conversion=value))
    for rate in (1.25, 1, "0", "-1.25", "NaN", "Infinity", "1,25", None,
                 " 1.25", "+1.25", "1E+0", "1_0"):
        s = copy.deepcopy(spec_w)
        s["numeraire_conversion"]["units_of_old_per_new"] = rate
        bad.append(s)
    for key in ("source_artifact_hash", "source_input_digest"):
        good = spec_w["numeraire_conversion"][key]
        for value in (good.upper(), good[:-1], good + "0", good[7:],
                      "sha512:" + good[7:], None, 7):
            s = copy.deepcopy(spec_w)
            s["numeraire_conversion"][key] = value
            bad.append(s)
    for key, value in (("kind", "currency"), ("scenario", "real"),
                       ("code", "WLD"), ("code", "USD"), ("code", ""),
                       ("code", 7), ("kind", None), ("scenario", None)):
        s = copy.deepcopy(spec_w)
        s["numeraire_declaration"][key] = value
        bad.append(s)
    s = copy.deepcopy(spec_w)
    s["numeraire_declaration"]["note"] = "x"
    bad.append(s)
    assert len(bad) == 59
    art_w = worldyard.build_artifact(spec_w)
    for s in bad:
        assert _raises_value_error(worldyard.build_artifact, s), s
        assert _raises_value_error(verify_independent.recompute_artifact, s), s
        # no artifact, so nothing to compare: verification raises as well
        assert _raises_value_error(worldyard.verify_artifact, art_w, s), s
        assert _raises_value_error(verify_independent.compare, s, art_w), s
    # the correct spec, for contrast, builds and verifies
    assert verify_independent.compare(
        spec_w, worldyard.build_artifact(spec_w)) == []


def test_undeclared_numeraire_w_is_rejected():
    for numeraire in ("W", 12345, "usd", "Usd", "US", "USDX", "", None,
                      ["USD"], "U$D", "\uff35\uff33\uff24", "US1", " USD",
                      "USD ", True, 1.5):
        spec = copy.deepcopy(SPEC_USD)
        spec["numeraire"] = numeraire
        assert _raises_value_error(worldyard.build_artifact, spec), numeraire
        assert _raises_value_error(verify_independent.recompute_artifact,
                                   spec), numeraire


def test_three_letter_numeraires_keep_the_old_rules():
    """Unchanged from before: a three-letter upper-case numeraire needs no
    declaration and gives the artifact it always gave (and an absent one
    still means USD)."""
    base = worldyard.build_artifact(SPEC_USD)
    assert sorted(base) == sorted([
        "method", "method_version", "numeraire", "weight_vintage_label",
        "weight_basis", "baseline_value_usd", "value_usd", "basket",
        "input_digest", "artifact_hash"])
    for numeraire in ("EUR", "XDR", "JPY"):
        spec = dict(SPEC_USD, numeraire=numeraire)
        art = worldyard.build_artifact(spec)
        assert art["numeraire"] == numeraire
        assert art["basket"] == base["basket"]
        assert art["value_usd"] == base["value_usd"]
        assert verify_independent.compare(spec, art) == []
    absent = {k: v for k, v in SPEC_USD.items() if k != "numeraire"}
    assert worldyard.build_artifact(absent)["numeraire"] == "USD"
    assert verify_independent.compare(
        absent, worldyard.build_artifact(absent)) == []
    # every shipped vintage still gives its published bytes
    for vid in ("v0.1-2026-05-15", "v0.2-ppp-2026-05-15",
                "v0.3-unwpp-2026-05-15", "v0.4-ppp-unwpp-2026-05-15"):
        spec = _load("data", vid, "spec.json")
        art = _load("data", vid, "artifact.json")
        assert worldyard.build_artifact(spec) == art, vid
        assert verify_independent.recompute_artifact(spec) == art, vid


def test_fictional_identifiers_cannot_look_like_currency_codes():
    art = worldyard.build_artifact(SPEC_USD)
    for code in ("WLD", "wld", "Wld", "USD", "", "W-1", "W 1", "840", "9",
                 "W" * 17, "\uff37", 7, None):
        decl = dict(W_DECLARATION, code=code)
        assert _raises_value_error(worldyard.redenominate, SPEC_USD, art,
                                   decl, "1.25"), code
    for code in ("W", "w", "W1", "WX", "World2100", "W" * 16, "A1B"):
        decl = dict(W_DECLARATION, code=code)
        spec = worldyard.redenominate(SPEC_USD, art, decl, "1.25")
        built = worldyard.build_artifact(spec)
        assert built["numeraire"] == code
        assert built["value"] == "0.739625"
        assert verify_independent.compare(spec, built) == []


def test_redenominate_refuses_bad_requests():
    art = worldyard.build_artifact(SPEC_USD)
    spec_w = worldyard.redenominate(SPEC_USD, art, W_DECLARATION, "1.25")
    art_w = worldyard.build_artifact(spec_w)
    absent = {k: v for k, v in SPEC_USD.items() if k != "numeraire"}
    tampered = dict(art, value_usd="0.9")
    swapped_rows = copy.deepcopy(art)
    swapped_rows["basket"][0], swapped_rows["basket"][1] = \
        swapped_rows["basket"][1], swapped_rows["basket"][0]
    cases = [
        (spec_w, art_w, W_DECLARATION, "1.25"),        # no chains
        (absent, worldyard.build_artifact(absent), W_DECLARATION, "1.25"),
        (SPEC_USD, tampered, W_DECLARATION, "1.25"),   # does not reproduce
        (SPEC_USD, swapped_rows, W_DECLARATION, "1.25"),
        (SPEC_USD, art_w, W_DECLARATION, "1.25"),      # another artifact
        (SPEC_USD, {}, W_DECLARATION, "1.25"),
        (SPEC_USD, None, W_DECLARATION, "1.25"),
        (None, art, W_DECLARATION, "1.25"),
        ([SPEC_USD], art, W_DECLARATION, "1.25"),
        (SPEC_USD, art, dict(W_DECLARATION, kind="currency"), "1.25"),
        (SPEC_USD, art, dict(W_DECLARATION, scenario="real"), "1.25"),
        (SPEC_USD, art, dict(W_DECLARATION, note="x"), "1.25"),
        (SPEC_USD, art, {"code": "W"}, "1.25"),
        (SPEC_USD, art, None, "1.25"),
        (SPEC_USD, art, "W", "1.25"),
        (SPEC_USD, art, W_DECLARATION, 1.25),
        (SPEC_USD, art, W_DECLARATION, "0"),
        (SPEC_USD, art, W_DECLARATION, "-1"),
        (SPEC_USD, art, W_DECLARATION, "NaN"),
        (SPEC_USD, art, W_DECLARATION, "0.8E0"),
    ]
    for args in cases:
        assert _raises_value_error(worldyard.redenominate, *args), args[2:]
    # a rejected request changes nothing
    assert art == worldyard.build_artifact(SPEC_USD)


def test_declared_value_is_the_published_value_divided_once():
    """Shipped v0.3 at a rate that does not divide evenly: each value field
    is the published USD string divided by the declared rate, rounded once."""
    spec = _load("data", "v0.3-unwpp-2026-05-15", "spec.json")
    art = _load("data", "v0.3-unwpp-2026-05-15", "artifact.json")
    spec_w = worldyard.redenominate(spec, art, W_DECLARATION, "1.95583")
    art_w = worldyard.build_artifact(spec_w)
    assert art_w["baseline_value"] == \
        "0.51129188119621848524667276808311560820725727696169"
    assert art_w["value"] == \
        "0.50395688143790367895816403771567294878218729325863"
    k = Fraction("1.95583")
    assert art_w["baseline_value"] == \
        _round50_text(Fraction(art["baseline_value_usd"]) / k)
    assert art_w["value"] == _round50_text(Fraction(art["value_usd"]) / k)
    assert art_w["basket"] == art["basket"]
    assert art_w["artifact_hash"] == (
        "sha256:aaec25517b9c132dee5fe8f77fc0d6266703303be099043d88434c875ac5"
        "6351")
    assert worldyard.verify_artifact(art_w, spec_w) is True
    assert verify_independent.compare(spec_w, art_w) == []
    for field in ("value", "baseline_value"):
        bad = dict(art_w)
        bad[field] = bad[field][:-1] + ("4" if bad[field][-1] != "4" else "5")
        assert worldyard.verify_artifact(bad, spec_w) is False
        assert verify_independent.compare(spec_w, bad) != []
    # the shipped files are untouched by all of this
    assert spec == _load("data", "v0.3-unwpp-2026-05-15", "spec.json")
    assert "numeraire_declaration" not in art


def test_values_are_divided_by_the_rate_never_multiplied_by_an_inverse():
    """1,000,000 old units at 1.95583 old units per new unit. Dividing gives
    511291.88...; multiplying by the inverse rate rounded to six significant
    figures (0.511292) would give 511292 exactly, about 0.12 more. The
    library divides by the declared rate and never forms an inverse."""
    spec = {"method": "worldyard", "method_version": "v0.4",
            "numeraire": "USD",
            "weight_vintage": {"label": "inverse-rate-test",
                               "basis": "population_share"},
            "basket": [{"code": "USD", "population": "1",
                        "fx_baseline_usd_per_unit": "0.000001",
                        "fx_valuation_usd_per_unit": "1"}]}
    art = worldyard.build_artifact(spec)
    assert Fraction(art["value_usd"]) == 10 ** 6
    spec_w = worldyard.redenominate(spec, art, W_DECLARATION, "1.95583")
    art_w = worldyard.build_artifact(spec_w)
    assert art_w["value"] == \
        "511291.88119621848524667276808311560820725727696170"
    assert art_w["value"] == _round50_text(Fraction(10 ** 11, 195583))
    by_inverse = Fraction(10 ** 6) * Fraction("0.511292")
    assert by_inverse == 511292
    assert Fraction(art_w["value"]) != by_inverse
    assert Fraction("0.118") < by_inverse - Fraction(art_w["value"]) \
        < Fraction("0.119")
    assert verify_independent.compare(spec_w, art_w) == []
    # the reciprocal rate gives another artifact: direction matters
    other = worldyard.build_artifact(
        worldyard.redenominate(spec, art, W_DECLARATION, "0.511292"))
    assert other["value"] == _round50_text(Fraction(10 ** 6)
                                           / Fraction("0.511292"))
    assert other["value"] != art_w["value"]


def test_the_text_of_a_declared_rate_is_part_of_the_identity():
    """"1.25", "01.250" and "1.250" are three texts for one value. The value
    fields are equal; the hashes are not, because the rate is kept and
    hashed verbatim."""
    base = worldyard.build_artifact(_spec_w("1.25"))
    seen = {base["artifact_hash"]}
    for text in ("01.250", "1.250", "1.2500000000", "0001.25"):
        spec_w = _spec_w(text)
        art_w = worldyard.build_artifact(spec_w)
        assert spec_w["numeraire_conversion"]["units_of_old_per_new"] == text
        assert art_w["numeraire_conversion"]["units_of_old_per_new"] == text
        assert art_w["value"] == base["value"] == "0.739625"
        assert art_w["baseline_value"] == base["baseline_value"] == "0.8"
        assert art_w["basket"] == base["basket"]
        assert art_w["artifact_hash"] not in seen
        seen.add(art_w["artifact_hash"])
        assert verify_independent.compare(spec_w, art_w) == []
        # one artifact does not verify against the spec with another text
        assert worldyard.verify_artifact(base, spec_w) is False
        assert verify_independent.compare(spec_w, base) != []


def test_declared_numeraire_on_odd_baskets():
    """One entry, three entries, a repeated code, an entry of nobody: the
    rows are the source's rows and the values are restated once."""
    def entry(code, pop, fx_b, fx_v):
        return {"code": code, "population": pop,
                "fx_baseline_usd_per_unit": fx_b,
                "fx_valuation_usd_per_unit": fx_v}

    baskets = (
        [entry("USD", "7", "1", "1")],
        [entry("USD", "1", "1", "1"), entry("EUR", "1", "3", "7"),
         entry("JPY", "1", "0.007", "0.003")],
        [entry("EUR", "2", "1.1", "1.3"), entry("EUR", "5", "1.1", "1.3"),
         entry("USD", "3", "1", "1")],
        [entry("USD", "9", "1", "1"), entry("XXX", "0", "0.125", "9"),
         entry("INR", "4", "0.0125", "0.013")],
    )
    for basket in baskets:
        spec = {"method": "worldyard", "method_version": "v0.4",
                "numeraire": "EUR",
                "weight_vintage": {"label": "odd-basket-test",
                                   "basis": "population_share"},
                "basket": basket}
        art = worldyard.build_artifact(spec)
        for rate in ("3", "0.7", "1936.27"):
            spec_w = worldyard.redenominate(spec, art, W_DECLARATION, rate)
            art_w = worldyard.build_artifact(spec_w)
            assert art_w["basket"] == art["basket"]
            assert art_w["numeraire_conversion"]["from"] == "EUR"
            for new, old in (("value", "value_usd"),
                             ("baseline_value", "baseline_value_usd")):
                assert art_w[new] == _round50_text(
                    Fraction(art[old]) / Fraction(rate)), (rate, new)
            assert verify_independent.recompute_artifact(spec_w) == art_w


def test_negative_published_values_are_not_restated():
    """A negative multiplier can pin a negative quantity and give a negative
    value. Such an artifact still builds as it always did, but it is not
    re-denominated: a value below zero is refused, never restated."""
    spec = {"method": "worldyard", "method_version": "v0.4",
            "numeraire": "USD",
            "weight_vintage": {"label": "negative-test",
                               "basis": "population_share"},
            "basket": [
                {"code": "USD", "population": "100", "weight_multiplier": "1",
                 "fx_baseline_usd_per_unit": "1",
                 "fx_valuation_usd_per_unit": "1"},
                {"code": "EUR", "population": "10", "weight_multiplier": "-5",
                 "fx_baseline_usd_per_unit": "1",
                 "fx_valuation_usd_per_unit": "3"}]}
    art = worldyard.build_artifact(spec)
    assert [r["fixed_amount"] for r in art["basket"]] == ["2", "-1"]
    assert art["value_usd"] == "-1"
    assert verify_independent.compare(spec, art) == []
    assert _raises_value_error(worldyard.redenominate, spec, art,
                               W_DECLARATION, "1.25")
    # a hand-made declared spec with the right hashes is refused as well
    forged = copy.deepcopy(spec)
    forged["numeraire"] = "W"
    forged["numeraire_declaration"] = dict(W_DECLARATION)
    forged["numeraire_conversion"] = {
        "from": "USD", "units_of_old_per_new": "1.25",
        "source_artifact_hash": art["artifact_hash"],
        "source_input_digest": art["input_digest"]}
    assert _raises_value_error(worldyard.build_artifact, forged)
    assert _raises_value_error(verify_independent.recompute_artifact, forged)


def test_declared_artifact_tampering_is_detected():
    spec_w = _spec_w()
    art_w = worldyard.build_artifact(spec_w)

    def rejected(bad, spec=spec_w):
        return (worldyard.verify_artifact(bad, spec) is False
                and verify_independent.compare(spec, bad) != [])

    n = 0
    for path in _leaf_paths(art_w):
        assert rejected(_tampered(art_w, path)), path
        n += 1
    assert n == 52
    # an edit that also recomputes the artifact_hash is caught by rebuilding
    forged = dict(art_w, value="0.8")
    forged["artifact_hash"] = worldyard.sha256(
        {k: v for k, v in forged.items() if k != "artifact_hash"})
    assert rejected(forged)
    # rows exchanged, a row dropped, a row repeated, old field names back
    swapped = copy.deepcopy(art_w)
    swapped["basket"][2], swapped["basket"][3] = \
        swapped["basket"][3], swapped["basket"][2]
    assert rejected(swapped)
    assert rejected(dict(art_w, basket=art_w["basket"][:-1]))
    assert rejected(dict(art_w, basket=art_w["basket"] + art_w["basket"][-1:]))
    assert rejected(dict(art_w, value_usd="0.92453125"))
    assert rejected({k: v for k, v in art_w.items() if k != "baseline_value"})
    assert rejected({k: v for k, v in art_w.items()
                     if k != "numeraire_conversion"})
    # the source artifact is not the declared artifact, and the reverse
    assert rejected(worldyard.build_artifact(SPEC_USD))
    assert rejected(art_w, SPEC_USD)


def test_ppp_valued_specs_are_not_re_denominated():
    """The value of a PPP-valued vintage is in international dollars, not an
    amount of a converting currency: no declared conversion rate applies."""
    for vid in ("v0.2-ppp-2026-05-15", "v0.4-ppp-unwpp-2026-05-15"):
        spec = _load("data", vid, "spec.json")
        art = _load("data", vid, "artifact.json")
        assert _raises_value_error(worldyard.redenominate, spec, art,
                                   W_DECLARATION, "1.25"), vid
        forged = copy.deepcopy(spec)               # hand-made, right hashes
        forged["numeraire"] = "W"
        forged["numeraire_declaration"] = dict(W_DECLARATION)
        forged["numeraire_conversion"] = {
            "from": "USD", "units_of_old_per_new": "1.25",
            "source_artifact_hash": art["artifact_hash"],
            "source_input_digest": art["input_digest"]}
        assert _raises_value_error(worldyard.build_artifact, forged), vid
        assert _raises_value_error(verify_independent.recompute_artifact,
                                   forged), vid
    for vid in ("v0.1-2026-05-15", "v0.3-unwpp-2026-05-15"):
        spec = _load("data", vid, "spec.json")
        art = _load("data", vid, "artifact.json")
        spec_w = worldyard.redenominate(spec, art, W_DECLARATION, "1.25")
        assert verify_independent.compare(
            spec_w, worldyard.build_artifact(spec_w)) == []


# --- the whole-basket successor event ---------------------------------------------
def _event(**changes):
    ev = copy.deepcopy(EVENT)
    for k, v in changes.items():
        if v is KeyError:
            del ev[k]
        else:
            ev[k] = v
    return ev


def _rates(**changes):
    return dict(EVENT["units_per_successor"], **changes)


BAD_EVENTS = {
    "not a dict": [EVENT],
    "a string": "whole_basket_successor",
    "missing event": _event(event=KeyError),
    "missing id": _event(id=KeyError),
    "missing scenario": _event(scenario=KeyError),
    "missing successor": _event(successor=KeyError),
    "missing successor_kind": _event(successor_kind=KeyError),
    "missing effective": _event(effective=KeyError),
    "missing rates": _event(units_per_successor=KeyError),
    "unknown key": _event(note="x"),
    "misspelt key": _event(efective="2100-01-01"),
    "the other direction is not a key": _event(successor_per_unit={"USD": "0.8"}),
    "unknown keys of mixed types": {**_event(note="x"), 7: "y"},
    "another event kind": _event(event="successor"),
    "event kind in another case": _event(event="Whole_Basket_Successor"),
    "empty id": _event(id=""),
    "id is a number": _event(id=7),
    "scenario not hypothetical": _event(scenario="real"),
    "scenario in another case": _event(scenario="Hypothetical"),
    "scenario None": _event(scenario=None),
    "successor_kind not fictional": _event(successor_kind="currency"),
    "successor_kind None": _event(successor_kind=None),
    "successor of three letters": _event(successor="WLD"),
    "successor of three lower-case letters": _event(successor="wld"),
    "successor shaped like a currency code": _event(successor="EUR"),
    "successor empty": _event(successor=""),
    "successor too long": _event(successor="W" * 17),
    "successor with a hyphen": _event(successor="W-1"),
    "successor only digits": _event(successor="840"),
    "successor full-width": _event(successor="\uff37"),
    "successor is a number": _event(successor=7),
    "no such date": _event(effective="2100-02-30"),
    "date not YYYY-MM-DD": _event(effective="2100-1-1"),
    "date with a time": _event(effective="2100-01-01T00:00"),
    "date is a number": _event(effective=21000101),
    "date None": _event(effective=None),
    "rates not a dict": _event(units_per_successor=[["USD", "1.25"]]),
    "no rates": _event(units_per_successor={}),
    "rates None": _event(units_per_successor=None),
    "rate is a number": _event(units_per_successor=_rates(EUR=1)),
    "rate is a float": _event(units_per_successor=_rates(EUR=1.0)),
    "rate is True": _event(units_per_successor=_rates(EUR=True)),
    "rate is None": _event(units_per_successor=_rates(EUR=None)),
    "rate is a list": _event(units_per_successor=_rates(EUR=["1"])),
    "rate is zero": _event(units_per_successor=_rates(EUR="0")),
    "rate is negative": _event(units_per_successor=_rates(EUR="-1")),
    "rate is NaN": _event(units_per_successor=_rates(EUR="NaN")),
    "rate is infinite": _event(units_per_successor=_rates(EUR="Infinity")),
    "rate is not a decimal": _event(units_per_successor=_rates(EUR="1,25")),
    "rate with a sign": _event(units_per_successor=_rates(EUR="+1")),
    "rate with an exponent": _event(units_per_successor=_rates(EUR="1E+0")),
    "rate with a space": _event(units_per_successor=_rates(EUR=" 1")),
    "successor among the old codes": _event(units_per_successor=_rates(W="1")),
    "empty code": _event(units_per_successor=_rates(**{"": "1"})),
    "code is a number": _event(units_per_successor={**_rates(), 7: "1"}),
    "declaration not an object": _event(declaration="1 W = 1.25 USD"),
    "declaration is a list": _event(declaration=["1 W = 1.25 USD"]),
    "declaration None": _event(declaration=None),
}


def test_malformed_events_are_rejected_everywhere():
    """A malformed event raises ValueError (never another exception, never a
    silent pass) in the engine, in the independent verifier and in the
    resolver, there also when the target is before the event."""
    eur = {"observations": [{"date": "2099-12-31", "value": "1.25"}]}
    rec = worldyard.freeze_fx_leg(SPEC_USD, EVENT, VALUATION_DATE)
    assert len(BAD_EVENTS) == 58
    for label, ev in BAD_EVENTS.items():
        assert _raises_value_error(worldyard.freeze_fx_leg, SPEC_USD, ev,
                                   VALUATION_DATE), label
        assert _raises_value_error(
            verify_independent.recompute_frozen_record, SPEC_USD, ev,
            VALUATION_DATE), label
        for record in (rec, {}, None):
            assert _raises_value_error(
                verify_independent.compare_frozen_record, SPEC_USD, ev,
                record), label
        for target in ("2099-12-31", "2100-01-01", "2100-06-30"):
            assert _raises_value_error(worldyard.resolve_input, target, eur,
                                       4, None, ev), (label, target)
            assert _raises_value_error(worldyard.resolve_input, target, eur,
                                       max_age_days=4, changeover=ev), label
    # no event at all is an error where an event is required
    assert _raises_value_error(worldyard.freeze_fx_leg, SPEC_USD, None,
                               VALUATION_DATE)
    assert _raises_value_error(verify_independent.recompute_frozen_record,
                               SPEC_USD, None, VALUATION_DATE)
    # the well-formed event, and one with a free-form declaration, pass
    with_text = _event(declaration={"text": "1 W = 1.25 USD (illustrative)",
                                    "source": "invented for the test"})
    for ev in (EVENT, with_text):
        r = worldyard.resolve_input("2099-12-31", eur, 4, None, ev)
        assert r["state"] == "ok"
    assert worldyard.sha256(EVENT) == EVENT_HASH
    rec_text = worldyard.freeze_fx_leg(SPEC_USD, with_text, VALUATION_DATE)
    assert rec_text["event_hash"] == worldyard.sha256(with_text) != EVENT_HASH
    assert rec_text["final_value"] == "0.800625"
    assert rec_text["record_hash"] != rec["record_hash"]
    assert verify_independent.compare_frozen_record(SPEC_USD, with_text,
                                                    rec_text) == []
    # a declaration is hashed, so it must be JSON data
    for junk in ({"text": {1, 2}}, {"text": b"bytes"}, {1: "a", "b": 2}):
        ev = _event(declaration=junk)
        assert _raises_value_error(worldyard.freeze_fx_leg, SPEC_USD, ev,
                                   VALUATION_DATE), junk
        assert _raises_value_error(
            verify_independent.recompute_frozen_record, SPEC_USD, ev,
            VALUATION_DATE), junk


# --- the resolver: FX-leg inputs after the event ----------------------------------
FROZEN_RESULT = {"state": "unavailable", "value": None,
                 "observation_date": None, "age_days": None, "rate_type": None,
                 "flags": [], "reason": "FX_LEG_FROZEN_AT_CHANGEOVER"}


def test_later_fx_leg_inputs_are_refused_with_a_clear_state():
    eur = {"observations": [{"date": "2099-12-31", "value": "1.25"}]}
    # before the event: the ordinary rules still apply
    r = worldyard.resolve_input("2099-12-31", eur, max_age_days=4,
                                changeover=EVENT)
    assert r == worldyard.resolve_input("2099-12-31", eur, max_age_days=4)
    assert r["state"] == "ok" and r["value"] == "1.25"
    # on and after the event: refused, explicitly, for every input
    for target in ("2100-01-01", "2100-01-04", "2150-06-30", "9999-12-31"):
        r = worldyard.resolve_input(target, eur, max_age_days=4,
                                    changeover=EVENT)
        assert r == FROZEN_RESULT, target
        assert worldyard.resolve_input(target, eur, 4, None, EVENT) == r
    assert worldyard.FX_LEG_FROZEN_AT_CHANGEOVER == \
        "FX_LEG_FROZEN_AT_CHANGEOVER"
    # without the event the old answer is unchanged (stale, then too old)
    assert worldyard.resolve_input("2100-01-01", eur,
                                   max_age_days=4)["state"] == "stale"
    assert worldyard.resolve_input("2100-01-01", eur, max_age_days=4,
                                   changeover=None)["state"] == "stale"
    assert worldyard.resolve_input("2100-01-05", eur,
                                   max_age_days=4)["reason"] == "TOO_OLD"


def test_effective_is_a_civil_date_and_inclusive():
    """A target is before the event iff it is earlier than `effective`. There
    is no time of day and no time zone: the last ordinary day is the day
    before, whatever the month or the leap year."""
    for effective, day_before in (("2100-01-01", "2099-12-31"),
                                  ("2096-03-01", "2096-02-29"),   # leap year
                                  ("2100-03-01", "2100-02-28"),   # 2100 is not
                                  ("2000-03-01", "2000-02-29"),   # 2000 is
                                  ("2099-07-15", "2099-07-14")):
        ev = _event(effective=effective)
        series = {"observations": [{"date": day_before, "value": "1.25"},
                                   {"date": effective, "value": "1.3"}]}
        before = worldyard.resolve_input(day_before, series, changeover=ev)
        assert before["state"] == "ok" and before["value"] == "1.25"
        assert before == worldyard.resolve_input(day_before, series)
        # on the date itself the input is refused, even though the series
        # carries an observation dated that very day
        assert worldyard.resolve_input(effective, series,
                                       changeover=ev) == FROZEN_RESULT
        assert worldyard.resolve_input(effective, series)["value"] == "1.3"


def test_the_event_takes_precedence_over_every_per_series_rule():
    succ = {"observations": [{"date": "2099-12-31", "value": "1.1642"},
                             {"date": "2100-01-04", "value": "1.17"}]}
    bgn = {"observations": [{"date": "2025-12-31", "value": "0.5980"}],
           "fixed_conversion": {"effective": "2026-01-01",
                                "units_per_successor": "1.95583",
                                "successor": succ}}
    r = worldyard.resolve_input("2099-12-31", bgn, max_age_days=4,
                                changeover=EVENT)
    assert r["state"] == "fixed_conversion"          # before: rule 1 as today
    assert r == worldyard.resolve_input("2099-12-31", bgn, max_age_days=4)
    assert worldyard.resolve_input("2100-01-04", bgn, max_age_days=4,
                                   changeover=EVENT) == FROZEN_RESULT
    # a per-series conversion that takes effect on the same day, or later
    for effective in ("2100-01-01", "2100-01-03", "2101-01-01"):
        late = dict(bgn, fixed_conversion=dict(bgn["fixed_conversion"],
                                               effective=effective))
        assert worldyard.resolve_input("2100-01-04", late, max_age_days=4,
                                       changeover=EVENT) == FROZEN_RESULT
    for extra in ({"permanent_holes": ["2100-01-04"]},
                  {"suspended_since": "2090-01-01"},
                  {"retired_since": "2090-01-01"},
                  {"suspended_since": "2100-01-04"},
                  {"retired_since": "2100-01-04"}):
        s = dict({"observations": [{"date": "2089-12-30", "value": "1"}]},
                 **extra)
        assert worldyard.resolve_input("2100-01-04", s, max_age_days=4,
                                       changeover=EVENT) == FROZEN_RESULT
    # a declared rate_type, several rates on a day, an empty series
    multi = {"observations": [
        {"date": "2100-01-04", "value": "1", "rate_type": "official"},
        {"date": "2100-01-04", "value": "2", "rate_type": "parallel"}]}
    assert worldyard.resolve_input("2100-01-04", multi, 4, "official",
                                   EVENT) == FROZEN_RESULT
    assert worldyard.resolve_input("2100-01-04", multi, 4, None,
                                   EVENT) == FROZEN_RESULT
    assert worldyard.resolve_input("2100-01-04", {}, 0, None,
                                   EVENT) == FROZEN_RESULT
    # malformed input still raises, also after the event
    assert _raises_value_error(worldyard.resolve_input, "2100-01-04",
                               {"observations": [], "surprise": 1}, 4, None,
                               EVENT)
    assert _raises_value_error(worldyard.resolve_input, "2100-02-30",
                               {"observations": []}, 4, None, EVENT)
    assert _raises_value_error(worldyard.resolve_input, "2100-01-04",
                               {"observations": []}, -1, None, EVENT)
    assert _raises_value_error(worldyard.resolve_input, "2100-01-04",
                               {"observations": []}, 4, 7, EVENT)
    assert _raises_value_error(worldyard.resolve_input, "2100-01-04",
                               {"observations": [{"date": "2100-01-04",
                                                  "value": "-1"}]}, 4, None,
                               EVENT)
    for broken in ({"effective": "2026-01-01", "units_per_successor": "0",
                    "successor": succ},
                   {"effective": "2026-13-01", "units_per_successor": "2",
                    "successor": succ},
                   {"effective": "2026-01-01", "units_per_successor": "2"},
                   "BGN 1.95583 = EUR 1"):
        assert _raises_value_error(
            worldyard.resolve_input, "2100-01-04",
            {"observations": [], "fixed_conversion": broken}, 4, None, EVENT)
    # the successor series of a per-series conversion is not looked at once
    # the event applies; before the event it is resolved, so it must be sound
    odd = dict(bgn, fixed_conversion=dict(bgn["fixed_conversion"],
                                          successor={"surprise": 1}))
    assert worldyard.resolve_input("2100-01-04", odd, 4, None,
                                   EVENT) == FROZEN_RESULT
    assert _raises_value_error(worldyard.resolve_input, "2099-12-31", odd, 4,
                               None, EVENT)
    # pure: nothing is mutated
    before = copy.deepcopy((bgn, EVENT))
    worldyard.resolve_input("2100-01-04", bgn, max_age_days=4, changeover=EVENT)
    assert (bgn, EVENT) == before


def test_older_inputs_keep_their_looser_number_form():
    """The plain-decimal rule is for DECLARED numbers of the new objects. The
    fields that existed before are read as before: a per-series
    `fixed_conversion` rate and an observation may still be written with a
    sign or an exponent, and a spec may still carry exponent notation."""
    for units in ("1.95583", "+1.95583", "195583E-5", "1.95583E0"):
        series = {"observations": [{"date": "2025-12-31", "value": "1"}],
                  "fixed_conversion": {
                      "effective": "2026-01-01", "units_per_successor": units,
                      "successor": {"observations": [
                          {"date": "2026-01-09", "value": "1.1642E0"}]}}}
        for ev in (None, EVENT):
            r = worldyard.resolve_input("2026-01-09", series, 0, None, ev)
            assert r["state"] == "fixed_conversion", units
            assert r["value"] == \
                "0.59524600808863756052417643660236319107488892183881", units
    spec = _tie_spec("2.5E+48")                    # exponent form in a spec
    assert verify_independent.compare(
        spec, worldyard.build_artifact(spec)) == []
    # ... while the same forms are refused as rates of an event
    for units in ("+1.95583", "195583E-5", "1.95583E0"):
        assert _raises_value_error(
            worldyard.resolve_input, "2026-01-09", {"observations": []}, 0,
            None, _event(units_per_successor=_rates(EUR=units))), units


def test_without_the_event_the_resolver_is_unchanged():
    """`changeover=None`, and any target before the event, give exactly the
    answer of the call without the argument, for every kind of series."""
    succ = {"observations": [{"date": "2026-01-09", "value": "1.1642"}]}
    cases = [
        ({"observations": [{"date": "2026-01-09", "value": "1.1642"}]}, 0, None),
        ({"observations": [{"date": "2026-01-05", "value": "1.1"}]}, 4, None),
        ({"observations": [{"date": "2026-01-01", "value": "1.1"}]}, 4, None),
        ({"observations": []}, 4, None),
        ({"observations": [{"date": "2026-01-09", "value": "1"}],
          "permanent_holes": ["2026-01-08"]}, 4, None),
        ({"observations": [{"date": "2026-01-02", "value": "1"}],
          "suspended_since": "2026-01-05"}, 400, None),
        ({"observations": [{"date": "2026-01-02", "value": "1"}],
          "retired_since": "2026-01-05"}, 400, None),
        ({"observations": [
            {"date": "2026-01-09", "value": "1", "rate_type": "a"},
            {"date": "2026-01-09", "value": "2", "rate_type": "b"}]}, 0, "a"),
        ({"observations": [
            {"date": "2026-01-09", "value": "1", "rate_type": "a"},
            {"date": "2026-01-09", "value": "2", "rate_type": "b"}]}, 0, None),
        ({"observations": [{"date": "2025-12-31", "value": "0.5980"}],
          "fixed_conversion": {"effective": "2026-01-01",
                               "units_per_successor": "1.95583",
                               "successor": succ}}, 4, None),
    ]
    for series, max_age, rate_type in cases:
        for target in ("2026-01-08", "2026-01-09", "2026-01-12"):
            plain = worldyard.resolve_input(target, series, max_age, rate_type)
            assert worldyard.resolve_input(target, series, max_age, rate_type,
                                           None) == plain
            assert worldyard.resolve_input(target, series, max_age, rate_type,
                                           EVENT) == plain
            assert worldyard.resolve_input(
                target, series, max_age, rate_type,
                _event(effective="2026-01-13")) == plain
        # the same series, with the event on 2026-01-09: refused from then on
        ev = _event(effective="2026-01-09")
        assert worldyard.resolve_input(
            "2026-01-08", series, max_age, rate_type, ev) == \
            worldyard.resolve_input("2026-01-08", series, max_age, rate_type)
        for target in ("2026-01-09", "2026-01-12"):
            assert worldyard.resolve_input(target, series, max_age, rate_type,
                                           ev) == FROZEN_RESULT


# --- the frozen record --------------------------------------------------------------
def test_frozen_record_of_the_exact_fixture_key_for_key():
    rec = worldyard.freeze_fx_leg(SPEC_USD, EVENT, VALUATION_DATE)
    assert rec == EXPECTED_FROZEN
    assert len(rec) == 21
    assert rec["format"] == worldyard.FROZEN_RECORD_FORMAT
    assert rec["notice"] == worldyard.FROZEN_NOTICE
    assert rec["notice"].isascii() and "\n" not in rec["notice"]
    art = worldyard.build_artifact(SPEC_USD)
    assert rec["source_artifact_hash"] == art["artifact_hash"]
    assert rec["source_input_digest"] == art["input_digest"]
    assert rec["last_fx_leg_value"] == art["value_usd"]          # verbatim
    assert [r["fixed_amount"] for r in rec["basket"]] == \
        [r["fixed_amount"] for r in art["basket"]]               # verbatim
    assert rec["event_hash"] == worldyard.sha256(EVENT)
    # deterministic, inputs untouched, self-hashed, plain JSON
    spec, event = copy.deepcopy(SPEC_USD), copy.deepcopy(EVENT)
    assert worldyard.freeze_fx_leg(spec, event, VALUATION_DATE) == rec
    assert spec == SPEC_USD and event == EVENT
    assert json.loads(json.dumps(rec)) == rec
    assert _self_hash_ok(rec, "record_hash")
    # the order of the keys of the event does not matter
    shuffled = dict(reversed(list(EVENT.items())))
    shuffled["units_per_successor"] = dict(
        reversed(list(EVENT["units_per_successor"].items())))
    assert worldyard.freeze_fx_leg(SPEC_USD, shuffled, VALUATION_DATE) == rec
    # the record does not alias its inputs
    rec["basket"][0]["units_per_successor"] = "9"
    assert EVENT["units_per_successor"]["USD"] == "1.25"


def test_frozen_value_is_the_exact_sum_rounded_once():
    """Rates that do not divide evenly: the value is the exact rational sum,
    rounded once to 50 significant digits, ties to even."""
    art = worldyard.build_artifact(SPEC_USD)
    rec = worldyard.freeze_fx_leg(SPEC_USD, EVENT_SIX, VALUATION_DATE)
    exact = _exact_frozen_sum(art, EVENT_SIX)
    assert exact == SIX_EXACT
    assert rec["final_value"] == SIX_FINAL == _round50_text(exact)
    assert rec["record_hash"] == SIX_RECORD_HASH
    # the comparison block, each number rounded once from exact values
    bridged = Fraction("0.92453125") / Fraction("1.95583")
    cmp_ = rec["comparison"]
    assert cmp_["last_fx_leg_value_bridged"] == _round50_text(bridged) == \
        "0.47270532203719137143821293261684297715036582934100"
    assert cmp_["final_minus_bridged"] == _round50_text(
        Fraction(SIX_FINAL) - Fraction(cmp_["last_fx_leg_value_bridged"])) == \
        "0.9203545248412305337286964271512355762403031634802"
    assert verify_independent.compare_frozen_record(SPEC_USD, EVENT_SIX,
                                                    rec) == []


def test_frozen_value_is_not_a_sum_of_rounded_terms():
    """On the shipped v0.3 quantities, dividing term by term at precision 50
    and adding gives ...565; the exact sum rounds to ...566. The record must
    carry the second, whatever the order of the basket."""
    spec = _load("data", "v0.3-unwpp-2026-05-15", "spec.json")
    art = worldyard.build_artifact(spec)
    rec = worldyard.freeze_fx_leg(spec, EVENT_AWKWARD, "2026-05-15")
    exact = _exact_frozen_sum(art, EVENT_AWKWARD)
    assert rec["final_value"] == \
        "24.417427777034686355393280531497846146904148905566"
    assert rec["final_value"] == _round50_text(exact)
    with decimal.localcontext() as ctx:
        ctx.prec = 50
        ctx.rounding = decimal.ROUND_HALF_EVEN
        per_term = Decimal(0)
        for r in art["basket"]:
            per_term += Decimal(r["fixed_amount"]) / Decimal(
                EVENT_AWKWARD["units_per_successor"][r["code"]])
    assert str(per_term) == \
        "24.417427777034686355393280531497846146904148905565"
    assert str(per_term) != rec["final_value"]
    assert rec["source_artifact_hash"] == art["artifact_hash"]
    assert verify_independent.compare_frozen_record(spec, EVENT_AWKWARD,
                                                    rec) == []
    # the same basket in every rotation and reversed: the same value string
    # (the rows and the source hash follow the basket; the value does not)
    n = len(spec["basket"])
    for k in range(n):
        for rev in (False, True):
            other = dict(spec, basket=spec["basket"][k:] + spec["basket"][:k])
            if rev:
                other["basket"] = other["basket"][::-1]
            r2 = worldyard.freeze_fx_leg(other, EVENT_AWKWARD, "2026-05-15")
            assert r2["final_value"] == rec["final_value"], (k, rev)
            assert [x["code"] for x in r2["basket"]] == \
                [e["code"] for e in other["basket"]]
            assert verify_independent.compare_frozen_record(
                other, EVENT_AWKWARD, r2) == []


def _tie_spec(fx_b_second):
    return {"method": "worldyard", "method_version": "v0.4", "numeraire": "USD",
            "weight_vintage": {"label": "tie-test", "basis": "population_share"},
            "basket": [
                {"code": "USD", "population": "1",
                 "fx_baseline_usd_per_unit": "0.25",
                 "fx_valuation_usd_per_unit": "0.25"},
                {"code": "EUR", "population": "3",
                 "fx_baseline_usd_per_unit": fx_b_second,
                 "fx_valuation_usd_per_unit": fx_b_second}]}


def test_ties_round_to_even():
    """Quantities 1 and 3E-49 (exact). The exact sums and their roundings:
      rates 1, 6  ->  1 + 5E-50    half-way, kept digit 0 (even): stays ...0
      rates 1, 2  ->  1 + 1.5E-49  half-way, kept digit 1 (odd): up to ...2
      rates 1, 3  ->  1 + 1E-49    fits in 50 digits exactly:       ...1
      rates 1, 60 ->  1 + 5E-51    below half-way: stays ...0
    Half-up would give ...1 in the first case; half-down ...1 in the second."""
    spec = _tie_spec("2.5E+48")
    art = worldyard.build_artifact(spec)
    assert [Fraction(r["fixed_amount"]) for r in art["basket"]] == \
        [Fraction(1), Fraction(3, 10 ** 49)]
    for rate, want in (
            ("6", "1.0000000000000000000000000000000000000000000000000"),
            ("2", "1.0000000000000000000000000000000000000000000000002"),
            ("3", "1.0000000000000000000000000000000000000000000000001"),
            ("60", "1.0000000000000000000000000000000000000000000000000")):
        ev = dict(EVENT, units_per_successor={"USD": "1", "EUR": rate})
        rec = worldyard.freeze_fx_leg(spec, ev, VALUATION_DATE)
        assert rec["final_value"] == want, (rate, rec["final_value"])
        exact = 1 + Fraction(3, 10 ** 49) / Fraction(rate)
        assert rec["final_value"] == _round50_text(exact), rate
        assert verify_independent.compare_frozen_record(spec, ev, rec) == []


def test_ties_in_the_gap_round_to_even_too():
    """One quantity of 1 at the rate 1, so final_value is 1; the last value
    is tiny, so the difference needs 51 digits:
      1 - 5E-51    half-way between 0.99..9 (odd) and 1: to 1
      1 - 1.5E-50  half-way between ...98 and ...99:     to ...98
      1 - 2.5E-50  half-way between ...97 and ...98:     to ...98
    and the neighbours just above and below a half-way point."""
    nines = "0." + "9" * 48
    for fx_v, want in (
            ("5E-51", "1.0000000000000000000000000000000000000000000000000"),
            ("1.5E-50", nines + "98"),
            ("2.5E-50", nines + "98"),
            ("5E-50", nines + "95"),             # exact with 50 digits
            ("4.9E-51", "1.0000000000000000000000000000000000000000000000000"),
            ("5.1E-51", nines + "99")):
        spec = {"method": "worldyard", "method_version": "v0.4",
                "numeraire": "USD",
                "weight_vintage": {"label": "gap-tie-test",
                                   "basis": "population_share"},
                "basket": [{"code": "USD", "population": "1",
                            "fx_baseline_usd_per_unit": "1",
                            "fx_valuation_usd_per_unit": fx_v}]}
        ev = dict(EVENT, units_per_successor={"USD": "1"})
        rec = worldyard.freeze_fx_leg(spec, ev, VALUATION_DATE)
        assert rec["final_value"] == "1"
        assert rec["comparison"]["last_fx_leg_value_bridged"] == fx_v
        assert rec["comparison"]["final_minus_bridged"] == want, fx_v
        assert want == _round50_text(1 - Fraction(fx_v)), fx_v
        assert verify_independent.compare_frozen_record(spec, ev, rec) == []


def test_the_gap_can_be_negative():
    """With USD declared at 1 the bridged value (0.92453125) exceeds the
    frozen value (0.820625): the difference is negative, and exact."""
    ev = _event(units_per_successor=_rates(USD="1"))
    rec = worldyard.freeze_fx_leg(SPEC_USD, ev, VALUATION_DATE)
    assert rec["final_value"] == "0.820625"
    assert rec["comparison"] == {
        "information_only": True, "bridge_code": "USD",
        "bridge_units_per_successor": "1",
        "last_fx_leg_value_bridged": "0.92453125",
        "final_minus_bridged": "-0.10390625"}
    assert verify_independent.compare_frozen_record(SPEC_USD, ev, rec) == []


def test_frozen_value_divides_by_the_rate_and_never_uses_an_inverse():
    """1,000,000 old units at 1.95583 per successor unit: 511291.88..., not
    the 511292 that the inverse rounded to six significant figures gives.
    And on the six-figure fixture the sum over inverse rates differs too."""
    spec = {"method": "worldyard", "method_version": "v0.4",
            "numeraire": "USD",
            "weight_vintage": {"label": "inverse-rate-test",
                               "basis": "population_share"},
            "basket": [{"code": "USD", "population": "1",
                        "fx_baseline_usd_per_unit": "0.000001",
                        "fx_valuation_usd_per_unit": "1"}]}
    ev = dict(EVENT, units_per_successor={"USD": "1.95583"})
    rec = worldyard.freeze_fx_leg(spec, ev, VALUATION_DATE)
    assert rec["basket"] == [{"code": "USD", "fixed_amount": "1E+6",
                              "units_per_successor": "1.95583"}]
    assert rec["final_value"] == \
        "511291.88119621848524667276808311560820725727696170"
    assert rec["final_value"] == _round50_text(Fraction(10 ** 11, 195583))
    assert Fraction(10 ** 6) * Fraction("0.511292") == 511292
    assert rec["comparison"]["final_minus_bridged"] == "0"
    assert verify_independent.compare_frozen_record(spec, ev, rec) == []

    def six_figures(fr):                      # fr rounded to 6 significant
        sign, q, exp = _round50_parts(fr)     # digits, half-up, as a Fraction
        digits = len(str(q))
        if digits <= 6:
            return sign * q * Fraction(10) ** exp
        cut = 10 ** (digits - 6)
        return sign * ((q + cut // 2) // cut * cut) * Fraction(10) ** exp

    art = worldyard.build_artifact(SPEC_USD)
    by_inverse = sum(
        Fraction(r["fixed_amount"]) * six_figures(
            1 / Fraction(EVENT_SIX["units_per_successor"][r["code"]]))
        for r in art["basket"])
    assert six_figures(1 / Fraction("1.95583")) == Fraction("0.511292")
    assert _round50_text(by_inverse) != SIX_FINAL
    assert worldyard.freeze_fx_leg(SPEC_USD, EVENT_SIX,
                                   VALUATION_DATE)["final_value"] == SIX_FINAL
    # reciprocal rates are other rates: the record is another record
    recip = dict(EVENT, units_per_successor={
        "USD": "0.8", "EUR": "1", "CNY": "0.1", "JPY": "0.005",
        "GBP": "1.25", "INR": "0.01"})
    r2 = worldyard.freeze_fx_leg(SPEC_USD, recip, VALUATION_DATE)
    assert r2["final_value"] == _round50_text(_exact_frozen_sum(art, recip))
    assert r2["final_value"] == "3853.221"
    assert r2["final_value"] != EXPECTED_FROZEN["final_value"]


def test_event_must_cover_exactly_the_basket_codes():
    partial = copy.deepcopy(EVENT)
    del partial["units_per_successor"]["INR"]
    extra = copy.deepcopy(EVENT)
    extra["units_per_successor"]["XYZ"] = "3"      # not in the basket
    misspelt = copy.deepcopy(EVENT)                # one missing, one extra
    misspelt["units_per_successor"]["INP"] = \
        misspelt["units_per_successor"].pop("INR")
    lower = copy.deepcopy(EVENT)                   # codes are compared exactly
    lower["units_per_successor"]["inr"] = \
        lower["units_per_successor"].pop("INR")
    bad = copy.deepcopy(EVENT)
    bad["units_per_successor"]["EUR"] = 1          # a number, not a string
    for ev in (partial, extra, misspelt, lower, bad):
        assert _raises_value_error(worldyard.freeze_fx_leg, SPEC_USD, ev,
                                   VALUATION_DATE)
        assert _raises_value_error(
            verify_independent.recompute_frozen_record, SPEC_USD, ev,
            VALUATION_DATE)
    # a basket with fewer entries than the event has rates, and the reverse
    small = dict(SPEC_USD, basket=SPEC_USD["basket"][:3])
    assert _raises_value_error(worldyard.freeze_fx_leg, small, EVENT,
                               VALUATION_DATE)
    assert _raises_value_error(verify_independent.recompute_frozen_record,
                               small, EVENT, VALUATION_DATE)


def test_declared_numbers_are_plain_decimal_strings():
    """The grammar of a declared number, through the public functions: a bad
    rate is refused everywhere, a good one is kept verbatim."""
    art = worldyard.build_artifact(SPEC_USD)
    for rate in BAD_DECLARED:
        ev = _event(units_per_successor=_rates(EUR=rate))
        assert _raises_value_error(worldyard.freeze_fx_leg, SPEC_USD, ev,
                                   VALUATION_DATE), rate
        assert _raises_value_error(
            verify_independent.recompute_frozen_record, SPEC_USD, ev,
            VALUATION_DATE), rate
        assert _raises_value_error(worldyard.redenominate, SPEC_USD, art,
                                   W_DECLARATION, rate), rate
        assert _raises_value_error(worldyard.resolve_input, "2099-12-31",
                                   {"observations": []}, 0, None, ev), rate
    for rate, value in GOOD_DECLARED:
        ev = _event(units_per_successor=_rates(EUR=rate))
        rec = worldyard.freeze_fx_leg(SPEC_USD, ev, VALUATION_DATE)
        assert rec["basket"][1]["units_per_successor"] == rate   # verbatim
        assert rec["final_value"] == _round50_text(
            Fraction("0.720625") + Fraction("0.08") / value), rate
        assert verify_independent.compare_frozen_record(SPEC_USD, ev, rec) == []
        spec_w = worldyard.redenominate(SPEC_USD, art, W_DECLARATION, rate)
        art_w = worldyard.build_artifact(spec_w)
        assert verify_independent.compare(spec_w, art_w) == []
        assert art_w["value"] == _round50_text(Fraction("0.92453125") / value)


def test_the_text_of_an_event_rate_is_part_of_the_identity():
    """"1.25" and "01.250" are two texts for one value: the frozen value is
    the same string, the event hash and the record hash are not."""
    base = worldyard.freeze_fx_leg(SPEC_USD, EVENT, VALUATION_DATE)
    seen = {base["record_hash"]}
    for text in ("01.250", "1.250", "1.25000", "0001.25"):
        ev = _event(units_per_successor=_rates(USD=text))
        rec = worldyard.freeze_fx_leg(SPEC_USD, ev, VALUATION_DATE)
        assert rec["basket"][0]["units_per_successor"] == text
        assert rec["comparison"]["bridge_units_per_successor"] == text
        assert rec["final_value"] == base["final_value"]
        assert rec["comparison"]["last_fx_leg_value_bridged"] == "0.739625"
        assert rec["event_hash"] != base["event_hash"]
        assert rec["record_hash"] not in seen
        seen.add(rec["record_hash"])
        assert verify_independent.compare_frozen_record(SPEC_USD, ev, rec) == []
        # and neither record verifies against the other event
        assert verify_independent.compare_frozen_record(SPEC_USD, EVENT,
                                                        rec) != []
        assert verify_independent.compare_frozen_record(SPEC_USD, ev,
                                                        base) != []


def test_quantities_outside_the_supported_range_are_not_frozen():
    """Exact arithmetic is done only on engine numbers x with
    1E-200 <= x < 1E+201; a spec that builds but pins a quantity outside
    that range is refused with ValueError (never a hang)."""
    for fx_b, ok in (("2.5E+199", True), ("2.5E+201", False),
                     ("2.5E-201", True), ("2.5E-203", False),
                     ("2.5E+999990", False)):
        spec = _tie_spec(fx_b)
        worldyard.build_artifact(spec)             # the artifact itself builds
        ev = dict(EVENT, units_per_successor={"USD": "1", "EUR": "2"})
        if ok:
            rec = worldyard.freeze_fx_leg(spec, ev, VALUATION_DATE)
            assert rec["final_value"] == _round50_text(_exact_frozen_sum(
                worldyard.build_artifact(spec), ev)), fx_b
            assert verify_independent.compare_frozen_record(spec, ev, rec) == []
        else:
            assert _raises_value_error(worldyard.freeze_fx_leg, spec, ev,
                                       VALUATION_DATE), fx_b
            assert _raises_value_error(
                verify_independent.recompute_frozen_record, spec, ev,
                VALUATION_DATE), fx_b


def test_negative_pinned_quantities_are_not_frozen():
    """A negative multiplier can pin a negative quantity. The artifact builds
    as it always did, but a quantity below zero is never converted."""
    spec = {"method": "worldyard", "method_version": "v0.4",
            "numeraire": "USD",
            "weight_vintage": {"label": "negative-test",
                               "basis": "population_share"},
            "basket": [
                {"code": "USD", "population": "100", "weight_multiplier": "1",
                 "fx_baseline_usd_per_unit": "1",
                 "fx_valuation_usd_per_unit": "1"},
                {"code": "EUR", "population": "10", "weight_multiplier": "-5",
                 "fx_baseline_usd_per_unit": "1",
                 "fx_valuation_usd_per_unit": "0.5"}]}
    art = worldyard.build_artifact(spec)
    assert [r["fixed_amount"] for r in art["basket"]] == ["2", "-1"]
    assert art["value_usd"] == "1.5"               # the value is positive
    ev = dict(EVENT, units_per_successor={"USD": "1", "EUR": "2"})
    assert _raises_value_error(worldyard.freeze_fx_leg, spec, ev,
                               VALUATION_DATE)
    assert _raises_value_error(verify_independent.recompute_frozen_record,
                               spec, ev, VALUATION_DATE)
    # an entry of nobody pins a quantity of zero: that is frozen, and adds 0
    zero = copy.deepcopy(SPEC_USD)
    zero["basket"].append({"code": "XXX", "population": "0",
                           "fx_baseline_usd_per_unit": "0.125",
                           "fx_valuation_usd_per_unit": "9"})
    ev = _event(units_per_successor=_rates(XXX="0.001"))
    rec = worldyard.freeze_fx_leg(zero, ev, VALUATION_DATE)
    assert rec["basket"][-1] == {"code": "XXX", "fixed_amount": "0E+3",
                                 "units_per_successor": "0.001"}
    assert rec["final_value"] == "0.800625"
    assert rec["record_hash"] != EXPECTED_FROZEN["record_hash"]
    assert verify_independent.compare_frozen_record(zero, ev, rec) == []


def test_frozen_record_on_odd_baskets():
    """One, three, five and seven entries, a repeated code (each entry uses
    the rate of its code), and a long basket: always the exact sum, rounded
    once, and the same record from the independent verifier."""
    rng = random.Random(1103)

    def spec_of(codes):
        return {"method": "worldyard", "method_version": "v0.4",
                "numeraire": "USD",
                "weight_vintage": {"label": "odd-basket-test",
                                   "basis": "population_share"},
                "basket": [{"code": c,
                            "population": str(rng.randrange(1, 10 ** 9)),
                            "fx_baseline_usd_per_unit":
                                "%d.%04d" % (rng.randrange(0, 200),
                                             rng.randrange(1, 10 ** 4)),
                            "fx_valuation_usd_per_unit":
                                "%d.%04d" % (rng.randrange(0, 200),
                                             rng.randrange(1, 10 ** 4))}
                           for c in codes]}

    def codes(n):
        return ["C%03d" % i for i in range(n)]

    for basket_codes in (["USD"], codes(3), codes(5), codes(7),
                         ["EUR", "USD", "EUR"], ["AAA"] * 4, codes(120)):
        spec = spec_of(basket_codes)
        ev = dict(EVENT, units_per_successor={
            c: "%d.%05d" % (rng.randrange(0, 2000), rng.randrange(1, 10 ** 5))
            for c in set(basket_codes)})
        art = worldyard.build_artifact(spec)
        rec = worldyard.freeze_fx_leg(spec, ev, VALUATION_DATE)
        assert len(rec["basket"]) == len(basket_codes)
        assert [r["code"] for r in rec["basket"]] == basket_codes
        assert rec["final_value"] == _round50_text(_exact_frozen_sum(art, ev))
        assert (rec["comparison"] is None) == ("USD" not in basket_codes)
        assert verify_independent.recompute_frozen_record(
            spec, ev, VALUATION_DATE) == rec
        assert verify_independent.compare_frozen_record(spec, ev, rec) == []


def test_random_baskets_three_routes_one_record():
    """Seeded random baskets with awkward quantities and rates. The frozen
    value, the bridged value, their difference and the two restated values of
    a declared numeraire are checked against exact Fractions rounded by the
    integer-only code of this file, and the independent verifier must return
    the identical objects."""
    rng = random.Random(2866)
    names = ["USD", "EUR", "CNY", "JPY", "GBP", "INR", "BRL", "ZAR", "KRW"]

    def number(lo, hi, places):
        return "%d.%0*d" % (rng.randrange(lo, hi), places,
                            rng.randrange(1, 10 ** places))

    for case in range(120):
        codes = rng.sample(names, rng.randrange(1, len(names) + 1))
        if rng.random() < 0.8 and "USD" not in codes:
            codes[0] = "USD"
        spec = {"method": "worldyard", "method_version": "v0.4",
                "numeraire": "USD",
                "weight_vintage": {"label": "random-%d" % case,
                                   "basis": "population_share"},
                "basket": [{"code": c,
                            "population": str(rng.randrange(0, 2 * 10 ** 9)),
                            "fx_baseline_usd_per_unit":
                                number(0, 3, rng.randrange(1, 9)),
                            "fx_valuation_usd_per_unit":
                                number(0, 3, rng.randrange(1, 9))}
                           for c in codes]}
        if rng.random() < 0.3:
            for e in spec["basket"]:
                e["weight_multiplier"] = number(0, 5, 3)
        spec["basket"][0]["population"] = str(rng.randrange(1, 10 ** 9))
        ev = dict(EVENT, id="random-%d" % case, units_per_successor={
            c: number(0, 2000, rng.randrange(1, 7)) for c in codes})
        art = worldyard.build_artifact(spec)
        rec = worldyard.freeze_fx_leg(spec, ev, VALUATION_DATE)
        exact = _exact_frozen_sum(art, ev)
        assert rec["final_value"] == _round50_text(exact), case
        if "USD" in codes:
            k = Fraction(ev["units_per_successor"]["USD"])
            bridged = _round50_text(Fraction(art["value_usd"]) / k)
            assert rec["comparison"]["last_fx_leg_value_bridged"] == bridged
            assert rec["comparison"]["final_minus_bridged"] == _round50_text(
                Fraction(rec["final_value"]) - Fraction(bridged)), case
            spec_w = worldyard.redenominate(
                spec, art, W_DECLARATION, ev["units_per_successor"]["USD"])
            art_w = worldyard.build_artifact(spec_w)
            assert art_w["value"] == bridged, case
            assert art_w["baseline_value"] == _round50_text(
                Fraction(art["baseline_value_usd"]) / k), case
            assert art_w["basket"] == art["basket"]
            assert verify_independent.recompute_artifact(spec_w) == art_w
        else:
            assert rec["comparison"] is None
        assert verify_independent.recompute_frozen_record(
            spec, ev, VALUATION_DATE) == rec, case
        assert _self_hash_ok(rec, "record_hash")


def test_basket_codes_must_be_strings_to_be_frozen():
    spec = copy.deepcopy(SPEC_USD)
    spec["basket"][0]["code"] = 840            # a number
    assert _raises_value_error(worldyard.freeze_fx_leg, spec, EVENT,
                               VALUATION_DATE)
    assert _raises_value_error(verify_independent.recompute_frozen_record,
                               spec, EVENT, VALUATION_DATE)
    spec["basket"][0]["code"] = ["USD"]        # not even hashable
    assert _raises_value_error(worldyard.freeze_fx_leg, spec, EVENT,
                               VALUATION_DATE)
    assert _raises_value_error(verify_independent.recompute_frozen_record,
                               spec, EVENT, VALUATION_DATE)
    spec["basket"][0]["code"] = None
    assert _raises_value_error(worldyard.freeze_fx_leg, spec, EVENT,
                               VALUATION_DATE)
    assert _raises_value_error(verify_independent.recompute_frozen_record,
                               spec, EVENT, VALUATION_DATE)


def test_valuation_date_must_precede_the_effective_date():
    for bad in ("2100-01-01", "2100-01-02", "2150-06-30", "2099-13-01",
                "2099-02-29", "20991231", "2099-12-31 ", "2099/12/31", "",
                None, 20991231, ["2099-12-31"]):
        assert _raises_value_error(worldyard.freeze_fx_leg, SPEC_USD, EVENT,
                                   bad), bad
        assert _raises_value_error(
            verify_independent.recompute_frozen_record, SPEC_USD, EVENT,
            bad), bad
    early = worldyard.freeze_fx_leg(SPEC_USD, EVENT, "2099-06-30")
    assert early["declared_valuation_date"] == "2099-06-30"
    assert early["final_value"] == "0.800625"
    assert early["record_hash"] != EXPECTED_FROZEN["record_hash"]
    # the date is a declaration: a record with another earlier date is a
    # well-formed record of its own
    assert verify_independent.compare_frozen_record(SPEC_USD, EVENT,
                                                    early) == []
    # the day before a leap-year boundary
    ev = _event(effective="2096-03-01")
    assert worldyard.freeze_fx_leg(SPEC_USD, ev, "2096-02-29")[
        "declared_valuation_date"] == "2096-02-29"
    assert _raises_value_error(worldyard.freeze_fx_leg, SPEC_USD, ev,
                               "2096-03-01")


def test_day_numbers_agree():
    """The engine and the verifier count days by different formulas; the
    differences between any two dates must be equal."""
    rng = random.Random(974)
    dates = ["0001-01-01", "0001-12-31", "1999-12-31", "2000-02-29",
             "2000-03-01", "2096-02-29", "2100-02-28", "2100-03-01",
             "2100-01-01", "2099-12-31", "9999-12-31"]
    for _ in range(400):
        y, m = rng.randrange(1, 10000), rng.randrange(1, 13)
        dates.append("%04d-%02d-%02d" % (y, m, rng.randrange(1, 29)))
    base_e = worldyard._days("2000-01-01")
    base_v = verify_independent.day_number("2000-01-01")
    for d in dates:
        assert worldyard._days(d) - base_e == \
            verify_independent.day_number(d) - base_v, d
    assert verify_independent.day_number("2000-03-01") \
        - verify_independent.day_number("2000-02-28") == 2
    assert verify_independent.day_number("2100-03-01") \
        - verify_independent.day_number("2100-02-28") == 1
    for bad in ("2100-02-29", "2099-00-10", "2099-13-01", "2099-12-32",
                "0000-01-01", "2099-1-01", "2099-12-1", "20991231",
                "2099-12-31T00", " 2099-12-31", "\uff12099-12-31",
                "2099\u201112-31", "", None, 20991231, 2099.1231):
        assert _raises_value_error(worldyard._days, bad), bad
        assert _raises_value_error(verify_independent.day_number, bad), bad


def test_no_declared_rate_for_the_old_numeraire_means_no_comparison():
    spec = copy.deepcopy(SPEC_USD)
    spec["basket"] = [e for e in spec["basket"] if e["code"] != "USD"]
    ev = copy.deepcopy(EVENT)
    del ev["units_per_successor"]["USD"]
    rec = worldyard.freeze_fx_leg(spec, ev, VALUATION_DATE)
    assert rec["comparison"] is None
    assert rec["flags"] == ["FROZEN_AT_CHANGEOVER", "NO_BRIDGE_RATE"]
    assert rec["final_value"] == \
        "0.80069444444444444444444444444444444444444444444444"
    assert rec["final_value"] == _round50_text(Fraction(1153, 1440))
    assert rec["last_fx_leg_numeraire"] == "USD"
    assert len(rec) == 21                       # the key is there, and null
    assert verify_independent.compare_frozen_record(spec, ev, rec) == []
    # inventing a comparison block for it is reported
    forged = _rehashed(dict(rec, comparison=EXPECTED_FROZEN["comparison"],
                            flags=["FROZEN_AT_CHANGEOVER"]))
    assert verify_independent.compare_frozen_record(spec, ev, forged) != []


def test_freeze_refuses_what_it_cannot_freeze():
    art = worldyard.build_artifact(SPEC_USD)
    spec_w = worldyard.redenominate(SPEC_USD, art, W_DECLARATION, "1.25")
    # a re-denominated spec: freeze the source spec instead
    assert _raises_value_error(worldyard.freeze_fx_leg, spec_w, EVENT,
                               VALUATION_DATE)
    assert _raises_value_error(verify_independent.recompute_frozen_record,
                               spec_w, EVENT, VALUATION_DATE)
    # a fresh start has no rates: that is not a successor event
    for ev in (_event(units_per_successor=KeyError),
               _event(units_per_successor={})):
        assert _raises_value_error(worldyard.freeze_fx_leg, SPEC_USD, ev,
                                   VALUATION_DATE)
        assert _raises_value_error(
            verify_independent.recompute_frozen_record, SPEC_USD, ev,
            VALUATION_DATE)
    # not a spec at all; a numeraire the rules do not accept
    for spec in (None, [SPEC_USD], "spec", dict(SPEC_USD, numeraire="W"),
                 dict(SPEC_USD, numeraire="usd"),
                 dict(SPEC_USD, method="other")):
        assert _raises_value_error(worldyard.freeze_fx_leg, spec, EVENT,
                                   VALUATION_DATE), spec
        assert _raises_value_error(
            verify_independent.recompute_frozen_record, spec, EVENT,
            VALUATION_DATE), spec


def test_the_comparison_block_depends_on_the_bridge_currency():
    """Why the block is information only: restating the last market value
    through another currency's declared rate gives another number."""
    art = worldyard.build_artifact(SPEC_USD)
    rates = {e["code"]: Fraction(e["fx_valuation_usd_per_unit"])
             for e in SPEC_USD["basket"]}
    via = {c: Fraction(art["value_usd"]) / rates[c]
           / Fraction(EVENT["units_per_successor"][c]) for c in rates}
    assert via["USD"] == Fraction("0.739625")
    assert via["CNY"] == Fraction("0.92453125")
    assert len(set(via.values())) > 1
    rec = worldyard.freeze_fx_leg(SPEC_USD, EVENT, VALUATION_DATE)
    assert Fraction(rec["comparison"]["last_fx_leg_value_bridged"]) == via["USD"]
    # the frozen value itself does not depend on the old numeraire at all
    for numeraire in ("EUR", "JPY", "XDR"):
        other = worldyard.freeze_fx_leg(dict(SPEC_USD, numeraire=numeraire),
                                        EVENT, VALUATION_DATE)
        assert other["final_value"] == rec["final_value"] == "0.800625"
        assert other["last_fx_leg_numeraire"] == numeraire
        assert (other["comparison"] is None) == (numeraire == "XDR")


# --- the independent verifier recomputes the frozen record --------------------------
def test_independent_verifier_recomputes_the_frozen_record():
    rec = worldyard.freeze_fx_leg(SPEC_USD, EVENT, VALUATION_DATE)
    assert verify_independent.recompute_frozen_record(
        SPEC_USD, EVENT, VALUATION_DATE) == rec == EXPECTED_FROZEN
    assert verify_independent.compare_frozen_record(SPEC_USD, EVENT, rec) == []
    assert verify_independent.FROZEN_RECORD_NOTICE == FROZEN_NOTICE
    # every single-field edit is reported, with or without a recomputed hash
    n = 0
    for path in _leaf_paths(rec):
        bad = _tampered(rec, path)
        assert verify_independent.compare_frozen_record(SPEC_USD, EVENT,
                                                        bad) != [], path
        if path != ("record_hash",):
            assert verify_independent.compare_frozen_record(
                SPEC_USD, EVENT, _rehashed(bad)) != [], path
        n += 1
    assert n == 42
    # an edit that also recomputes the self hash is caught by recomputation
    for field, value in (("final_value", "0.800626"),
                         ("final_value", "0.8006250"),      # a padded zero
                         ("final_value", "8.00625E-1"),     # another notation
                         ("last_fx_leg_value", "0.9245312500"),
                         ("final_value_numeraire", "USD"),
                         ("scenario", "real"),
                         ("flags", []),
                         ("flags", ["FROZEN_AT_CHANGEOVER", "NO_BRIDGE_RATE"]),
                         ("comparison", None),
                         ("notice", ""),
                         ("format", "worldyard-frozen-record-2")):
        forged = _rehashed(dict(rec, **{field: value}))
        assert _self_hash_ok(forged, "record_hash")
        diffs = verify_independent.compare_frozen_record(SPEC_USD, EVENT,
                                                         forged)
        assert [d[0] for d in diffs if d[0] == field
                or d[0].startswith(field)], (field, diffs)
    for key, value in (("final_minus_bridged", "0.062"),
                       ("final_minus_bridged", "-0.061"),
                       ("last_fx_leg_value_bridged", "0.92453125"),
                       ("bridge_code", "EUR"),
                       ("information_only", False),
                       ("information_only", 1)):
        forged = copy.deepcopy(rec)
        forged["comparison"][key] = value
        assert verify_independent.compare_frozen_record(
            SPEC_USD, EVENT, _rehashed(forged)) != [], (key, value)
    # JSON types matter: `true` is not 1 and not 1.0, although the three are
    # equal in Python. With the hash left alone only the integrity check of
    # the record can see it.
    for value in (1, 1.0):
        forged = copy.deepcopy(rec)
        forged["comparison"]["information_only"] = value
        assert forged == rec                       # equal for Python ...
        assert not _self_hash_ok(forged, "record_hash")      # ... not as JSON
        assert verify_independent.compare_frozen_record(
            SPEC_USD, EVENT, forged) != [], value
    # rows exchanged, dropped, repeated, re-quoted
    for edit in (lambda b: b.__setitem__(slice(0, 2), [b[1], b[0]]),
                 lambda b: b.pop(),
                 lambda b: b.append(dict(b[-1])),
                 lambda b: b.reverse(),
                 lambda b: b[2].__setitem__("fixed_amount", "2.80"),
                 lambda b: b[2].__setitem__("extra", "x"),
                 lambda b: b[2].pop("code")):
        forged = copy.deepcopy(rec)
        edit(forged["basket"])
        assert verify_independent.compare_frozen_record(
            SPEC_USD, EVENT, forged) != []
        assert verify_independent.compare_frozen_record(
            SPEC_USD, EVENT, _rehashed(forged)) != []
    # the record does not verify against another spec or another event
    other = copy.deepcopy(SPEC_USD)
    other["basket"][0]["population"] = "101"
    assert verify_independent.compare_frozen_record(other, EVENT, rec) != []
    noted = copy.deepcopy(SPEC_USD)                # only the provenance differs
    noted["weight_vintage"]["note"] = "another note"
    assert verify_independent.compare_frozen_record(noted, EVENT, rec) != []
    assert verify_independent.compare_frozen_record(SPEC_USD, EVENT_SIX,
                                                    rec) != []
    assert verify_independent.compare_frozen_record(
        SPEC_USD, _event(id="hypothetical-W-test-9"), rec) != []
    assert verify_independent.compare_frozen_record(
        SPEC_USD, _event(declaration={"text": "added later"}), rec) != []
    swapped_rates = _event(units_per_successor=_rates(EUR="0.8", GBP="1"))
    assert verify_independent.compare_frozen_record(SPEC_USD, swapped_rates,
                                                    rec) != []
    # removing or adding a key is reported too
    short = {k: v for k, v in rec.items() if k != "comparison"}
    assert verify_independent.compare_frozen_record(SPEC_USD, EVENT,
                                                    short) != []
    assert verify_independent.compare_frozen_record(
        SPEC_USD, EVENT, dict(rec, extra="x")) != []
    assert verify_independent.compare_frozen_record(
        SPEC_USD, EVENT, _rehashed(dict(rec, extra="x"))) != []
    no_hash = {k: v for k, v in rec.items() if k != "record_hash"}
    assert verify_independent.compare_frozen_record(SPEC_USD, EVENT,
                                                    no_hash) != []


def test_a_malformed_record_is_a_difference_not_an_exception():
    rec = worldyard.freeze_fx_leg(SPEC_USD, EVENT, VALUATION_DATE)
    for record in (None, [], [rec], "record", 7, True):
        diffs = verify_independent.compare_frozen_record(SPEC_USD, EVENT,
                                                         record)
        assert len(diffs) == 1 and diffs[0][0] == "record", record
    # the declared date: missing, malformed, or not before the event
    for date in (KeyError, None, 20991231, "", "2099-12-32", "2099-1-1",
                 "2100-01-01", "2100-01-02", "9999-12-31", ["2099-12-31"]):
        record = copy.deepcopy(rec)
        if date is KeyError:
            del record["declared_valuation_date"]
        else:
            record["declared_valuation_date"] = date
        for candidate in (record, _rehashed(record)):
            diffs = verify_independent.compare_frozen_record(
                SPEC_USD, EVENT, candidate)
            assert len(diffs) == 1, date
            assert diffs[0][0] == "declared_valuation_date", date
    # fields of the wrong type are reported, never raised
    for field, value in (("basket", "rows"), ("basket", None), ("basket", {}),
                         ("comparison", "none"), ("comparison", []),
                         ("flags", "FROZEN_AT_CHANGEOVER"), ("flags", None),
                         ("final_value", 0.800625), ("final_value", None),
                         ("record_hash", None), ("record_hash", 7),
                         ("event_hash", ["sha256"]), ("notice", {"a": 1})):
        candidates = [dict(rec, **{field: value})]
        if field != "record_hash":
            candidates.append(_rehashed(candidates[0]))
        for candidate in candidates:
            assert verify_independent.compare_frozen_record(
                SPEC_USD, EVENT, candidate) != [], (field, value)
    assert verify_independent.compare_frozen_record(SPEC_USD, EVENT, {}) != []
    # a malformed SPEC, on the other hand, is an error, as for artifacts
    assert _raises_value_error(verify_independent.compare_frozen_record,
                               dict(SPEC_USD, numeraire="W"), EVENT, rec)
    assert _raises_value_error(verify_independent.compare_frozen_record,
                               dict(SPEC_USD, method="other"), EVENT, rec)
    assert _raises_value_error(verify_independent.compare_frozen_record,
                               None, EVENT, rec)


# --- the PPP leg is not frozen ---------------------------------------------------------
def test_ppp_valued_specs_are_not_frozen():
    for vid in ("v0.2-ppp-2026-05-15", "v0.4-ppp-unwpp-2026-05-15"):
        spec = _load("data", vid, "spec.json")
        ev = dict(EVENT, units_per_successor={
            e["code"]: "2" for e in spec["basket"]})
        assert _raises_value_error(worldyard.freeze_fx_leg, spec, ev,
                                   "2026-05-15"), vid
        assert _raises_value_error(
            verify_independent.recompute_frozen_record, spec, ev,
            "2026-05-15"), vid
        assert _raises_value_error(
            verify_independent.compare_frozen_record, spec, ev,
            dict(EXPECTED_FROZEN, declared_valuation_date="2026-05-15")), vid
    for vid in ("v0.1-2026-05-15", "v0.3-unwpp-2026-05-15"):
        spec = _load("data", vid, "spec.json")
        art = _load("data", vid, "artifact.json")
        ev = dict(EVENT, units_per_successor={
            e["code"]: "2" for e in spec["basket"]})
        rec = worldyard.freeze_fx_leg(spec, ev, "2026-05-15")
        assert rec["source_artifact_hash"] == art["artifact_hash"]
        assert rec["last_fx_leg_value"] == art["value_usd"]
        assert rec["final_value"] == _round50_text(_exact_frozen_sum(art, ev))
        assert verify_independent.compare_frozen_record(spec, ev, rec) == []


def test_a_nominal_sibling_pins_the_same_quantities_as_a_ppp_vintage():
    """The pinned quantities depend only on populations, multipliers and the
    baseline rates. So the declared-rate value of a PPP vintage's basket can
    be stated by freezing a nominal spec with the same baseline."""
    spec = _load("data", "v0.4-ppp-unwpp-2026-05-15", "spec.json")
    art = _load("data", "v0.4-ppp-unwpp-2026-05-15", "artifact.json")
    sibling = {"method": "worldyard", "method_version": "v0.4",
               "numeraire": "USD",
               "weight_vintage": {"label": "nominal sibling (test)",
                                  "basis": "population_share"},
               "basket": [{"code": e["code"], "population": e["population"],
                           "fx_baseline_usd_per_unit":
                               e["fx_baseline_usd_per_unit"],
                           "fx_valuation_usd_per_unit":
                               e["fx_baseline_usd_per_unit"]}
                          for e in spec["basket"]]}
    sib = worldyard.build_artifact(sibling)
    assert [r["fixed_amount"] for r in sib["basket"]] == \
        [r["fixed_amount"] for r in art["basket"]]
    ev = dict(EVENT, units_per_successor={
        e["code"]: "2" for e in spec["basket"]})
    rec = worldyard.freeze_fx_leg(sibling, ev, "2026-05-15")
    assert [r["fixed_amount"] for r in rec["basket"]] == \
        [r["fixed_amount"] for r in art["basket"]]
    assert verify_independent.compare_frozen_record(sibling, ev, rec) == []


def test_ppp_and_population_inputs_are_resolved_without_the_event():
    """PPP factors and populations are not FX-leg inputs: resolved without
    the event, a factor observed before it stays usable within its maximum
    age (1096 days from 1 July of its reference year), then it is too old.
    The resolver cannot tell what a series measures: given the event, it
    refuses every input on or after the date, so the caller passes the event
    for FX-leg inputs only."""
    ppp_age = worldyard.DECLARED_MAX_AGE_DAYS["World Bank PA.NUS.PPP"]
    pop_age = worldyard.DECLARED_MAX_AGE_DAYS["UN World Population Prospects"]
    assert ppp_age == 1096 and pop_age == 1461
    factor = {"observations": [{"date": "2099-07-01", "value": "4"}]}
    population = {"observations": [{"date": "2099-07-11", "value": "100"}]}
    after = worldyard.resolve_input("2100-06-30", factor, ppp_age)
    assert (after["state"], after["value"], after["age_days"]) == \
        ("stale", "4", "364")
    last = worldyard.resolve_input("2102-07-02", factor, ppp_age)
    assert (last["state"], last["age_days"]) == ("stale", "1096")
    late = worldyard.resolve_input("2102-07-03", factor, ppp_age)
    assert (late["state"], late["reason"]) == ("unavailable", "TOO_OLD")
    pop = worldyard.resolve_input("2100-06-30", population, pop_age)
    assert (pop["state"], pop["value"]) == ("stale", "100")
    for series, age in ((factor, ppp_age), (population, pop_age)):
        assert worldyard.resolve_input("2100-06-30", series, age,
                                       changeover=EVENT) == FROZEN_RESULT
        # before the date the event changes nothing
        assert worldyard.resolve_input("2099-12-31", series, age,
                                       changeover=EVENT) == \
            worldyard.resolve_input("2099-12-31", series, age)


# --- nothing depends on the caller's decimal context ----------------------------
def _hostile_context():
    """A caller's decimal context that differs from the library's in every
    field that could change a result or raise."""
    ctx = decimal.getcontext()
    ctx.capitals = 0                    # would print 6e+1 instead of 6E+1
    ctx.traps[decimal.Inexact] = True   # would raise on any rounding
    ctx.traps[decimal.Rounded] = True
    ctx.Emax = 60
    ctx.Emin = -60
    ctx.prec = 7
    ctx.rounding = decimal.ROUND_UP


def test_results_do_not_depend_on_the_callers_decimal_context():
    """The bytes of an artifact are fixed by the spec alone. The engine and
    the independent verifier state every field of their decimal context, so
    the context of the calling program changes nothing."""
    spec03 = _load("data", "v0.3-unwpp-2026-05-15", "spec.json")
    art03 = _load("data", "v0.3-unwpp-2026-05-15", "artifact.json")
    # 750 / 1000 / 0.0125 = 60, which decimal writes with an exponent
    spec_exp = {
        "method": "worldyard", "method_version": "v0.4", "numeraire": "USD",
        "weight_vintage": {"label": "context-test",
                           "basis": "population_share"},
        "basket": [
            {"code": "USD", "population": "250",
             "fx_baseline_usd_per_unit": "1",
             "fx_valuation_usd_per_unit": "1"},
            {"code": "INR", "population": "750",
             "fx_baseline_usd_per_unit": "0.0125",
             "fx_valuation_usd_per_unit": "0.0128"}]}
    old_lev = {"observations": [{"date": "2025-12-31", "value": "1"}],
               "fixed_conversion": {
                   "effective": "2026-01-01",
                   "units_per_successor": "1.95583",
                   "successor": {"observations": [
                       {"date": "2026-01-09", "value": "1.1642"}]}}}

    spec_w = _spec_w("1.95583")

    def everything():
        return (worldyard.build_artifact(spec03),
                worldyard.build_artifact(spec_exp),
                verify_independent.recompute_artifact(spec03),
                verify_independent.recompute_artifact(spec_exp),
                worldyard.build_artifact(spec_w),
                verify_independent.recompute_artifact(spec_w),
                worldyard.redenominate(
                    SPEC_USD, worldyard.build_artifact(SPEC_USD),
                    W_DECLARATION, "1.95583"),
                worldyard.freeze_fx_leg(SPEC_USD, EVENT_SIX, VALUATION_DATE),
                verify_independent.recompute_frozen_record(
                    SPEC_USD, EVENT_SIX, VALUATION_DATE),
                verify_independent.compare_frozen_record(
                    SPEC_USD, EVENT, EXPECTED_FROZEN),
                worldyard.resolve_input("2100-01-01", old_lev, 4, None, EVENT),
                worldyard.resolve_input("2026-01-09", old_lev, 4),
                worldyard._ppp_valued(spec03),
                verify_independent.is_ppp_valued(spec03),
                [worldyard._round50(p, q) for p, q, _, _ in ROUNDING_TABLE],
                [verify_independent.round_once(Fraction(p, q))
                 for p, q, _, _ in ROUNDING_TABLE],
                worldyard._declared("1.95583", "rate"),
                worldyard._engine_number("6E+1", "x"),
                verify_independent.exact_published("6E+1"))

    want = everything()
    assert want[0] == art03 == want[2]
    assert want[1] == want[3]
    assert want[1]["basket"][1]["fixed_amount"] == "6E+1"   # exponent form
    assert want[4] == want[5] and want[6] == spec_w
    assert want[4]["value"] == \
        "0.47270532203719137143821293261684297715036582934100"
    assert want[7] == want[8] and want[7]["final_value"] == SIX_FINAL
    assert want[9] == [] and want[10] == FROZEN_RESULT
    assert want[11]["value"] == \
        "0.59524600808863756052417643660236319107488892183881"
    saved = decimal.getcontext().copy()
    try:
        _hostile_context()
        got = everything()
    finally:
        decimal.setcontext(saved)
    assert got == want
    # and the caller's context is left exactly as it was
    assert decimal.getcontext().prec == saved.prec
    assert decimal.getcontext().capitals == saved.capitals


# --- rate comparison (information only) ------------------------------------------
# The declared rates of the event set beside pinned market rates and PPP
# factors, as ratios. It compares; it does not grade. No column is a
# conversion rate, and a PPP factor is not an exchange rate.
#
# Pinned comparison inputs (illustrative, not real data).
MARKET = {"source": "illustrative test values, not real market rates",
          "date": "2099-12-31", "numeraire": "USD",
          "usd_per_unit": {"USD": "1", "EUR": "1.25", "CNY": "0.1",
                           "JPY": "0.00625", "GBP": "1.25", "INR": "0.0125"}}
PPP = {"source": "illustrative test values, not World Bank data",
       "reference_year": "2099",
       "lcu_per_intl_usd": {"USD": "1", "EUR": "0.8", "CNY": "4",
                            "JPY": "100", "GBP": "0.64", "INR": "25"}}

RATE_NOTICE = (
    "Information only. Hypothetical scenario: a thought experiment, not a "
    "forecast, a proposal or an offer of any currency. "
    "declared_implied_usd_per_unit is a comparison quantity derived from two "
    "declared rates; it is not a conversion rate and must not be used to "
    "convert amounts. A PPP factor is not an exchange rate: no column shows a "
    "correct rate, or that a currency is over- or undervalued.")

# declared-implied USD per unit = units_per_successor(USD) / units_per_successor(i)
# declared_over_market = implied / market        declared_over_ppp = implied * factor
EXPECTED_ROWS = {
    #       implied        /market    /ppp
    "CNY": ("0.125",      "1.25",    "0.5"),
    "EUR": ("1.25",       "1",       "1"),
    "GBP": ("1.5625",     "1.25",    "1"),
    "INR": ("0.0125",     "1",       "0.3125"),
    "JPY": ("0.00625",    "1",       "0.625"),
    "USD": ("1",          "1",       "1"),
}
RATE_RECORD_HASH = ("sha256:946bced6f1f9672d248f2faae6a050f24b4fd6f466b7bdae"
                    "5959887449299145")
RATE_ROW_KEYS = sorted([
    "code", "declared_units_per_successor", "declared_implied_usd_per_unit",
    "market_usd_per_unit", "declared_over_market", "ppp_lcu_per_intl_usd",
    "declared_over_ppp", "flags"])


def _keys(obj):
    """Every key of a JSON value, recursively."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def _both_rate_comparisons(event, market, ppp):
    """The engine's record and the independent verifier's recomputation,
    which must be equal; returns the engine's."""
    rec = worldyard.rate_comparison(event, market, ppp)
    assert verify_independent.recompute_rate_comparison(event, market,
                                                        ppp) == rec
    return rec


def test_rate_comparison_is_information_only_and_exact():
    rec = _both_rate_comparisons(EVENT, MARKET, PPP)

    assert sorted(rec) == sorted([
        "format", "kind", "information_only", "scenario", "notice",
        "event_id", "event_hash", "successor", "successor_kind", "effective",
        "market", "ppp", "rows", "record_hash"])
    assert rec["format"] == "worldyard-rate-comparison-1"
    assert rec["format"] == worldyard.RATE_COMPARISON_FORMAT
    assert rec["kind"] == "rate_comparison"
    assert rec["information_only"] is True
    assert rec["scenario"] == "hypothetical"
    assert rec["notice"] == RATE_NOTICE == worldyard.RATE_NOTICE
    assert rec["notice"] == verify_independent.RATE_COMPARISON_NOTICE
    assert "not an exchange rate" in rec["notice"].lower()
    assert "not a conversion rate" in rec["notice"].lower()
    assert rec["event_id"] == EVENT["id"]
    assert rec["event_hash"] == worldyard.sha256(EVENT) == EVENT_HASH
    assert rec["successor"] == "W" and rec["effective"] == "2100-01-01"
    assert rec["successor_kind"] == "fictional_scenario_identifier"
    # it compares; it does not grade: no audit or fairness vocabulary, and
    # no key that would present a column as a conversion or exchange rate
    assert not any(w in k.lower() for k in _keys(rec)
                   for w in ("audit", "fair", "score", "grade",
                             "conversion", "exchange"))
    # the pinned inputs are named
    assert rec["market"] == {"source": MARKET["source"], "date": "2099-12-31",
                             "numeraire": "USD"}
    assert rec["ppp"] == {"source": PPP["source"], "reference_year": "2099"}

    rows = rec["rows"]
    assert [r["code"] for r in rows] == sorted(EXPECTED_ROWS)
    for r in rows:
        c = r["code"]
        implied, over_market, over_ppp = EXPECTED_ROWS[c]
        assert sorted(r) == RATE_ROW_KEYS
        # inputs echoed verbatim ...
        assert r["declared_units_per_successor"] == EVENT["units_per_successor"][c]
        assert r["market_usd_per_unit"] == MARKET["usd_per_unit"][c]
        assert r["ppp_lcu_per_intl_usd"] == PPP["lcu_per_intl_usd"][c]
        # ... and the comparisons, exact, in the shortest form
        assert r["declared_implied_usd_per_unit"] == implied
        assert r["declared_over_market"] == over_market
        assert r["declared_over_ppp"] == over_ppp
        assert r["flags"] == []

    # deterministic, independent of input order, self-hashed, plain JSON
    shuffled = copy.deepcopy(EVENT)
    shuffled["units_per_successor"] = dict(
        reversed(list(shuffled["units_per_successor"].items())))
    market = copy.deepcopy(MARKET)
    market["usd_per_unit"] = dict(
        reversed(list(market["usd_per_unit"].items())))
    assert worldyard.rate_comparison(shuffled, market, PPP) == rec
    assert worldyard.rate_comparison(EVENT, MARKET, PPP) == rec
    assert _self_hash_ok(rec, "record_hash")
    assert rec["record_hash"] == RATE_RECORD_HASH
    assert json.loads(json.dumps(rec)) == rec


def test_rate_comparison_missing_rate_is_explicit_never_guessed():
    market = copy.deepcopy(MARKET)
    del market["usd_per_unit"]["JPY"]
    rec = _both_rate_comparisons(EVENT, market, PPP)
    jpy = [r for r in rec["rows"] if r["code"] == "JPY"][0]
    assert jpy["market_usd_per_unit"] is None
    assert jpy["declared_over_market"] is None
    assert jpy["flags"] == ["NO_MARKET_RATE"]
    # the PPP comparison for JPY is still made; the other rows are unchanged
    assert jpy["declared_over_ppp"] == "0.625"
    full = worldyard.rate_comparison(EVENT, MARKET, PPP)
    assert [r for r in rec["rows"] if r["code"] != "JPY"] == \
        [r for r in full["rows"] if r["code"] != "JPY"]
    ppp = copy.deepcopy(PPP)
    del ppp["lcu_per_intl_usd"]["CNY"]
    del ppp["lcu_per_intl_usd"]["JPY"]
    rec = _both_rate_comparisons(EVENT, market, ppp)
    by = {r["code"]: r for r in rec["rows"]}
    assert by["JPY"]["flags"] == ["NO_MARKET_RATE", "NO_PPP_FACTOR"]
    assert by["JPY"]["declared_over_ppp"] is None
    assert by["JPY"]["ppp_lcu_per_intl_usd"] is None
    assert by["JPY"]["declared_implied_usd_per_unit"] == "0.00625"
    assert by["CNY"]["flags"] == ["NO_PPP_FACTOR"]
    assert by["CNY"]["declared_over_market"] == "1.25"
    # every row keeps its eight keys, nulls included
    assert all(sorted(r) == RATE_ROW_KEYS for r in rec["rows"])
    empty = _both_rate_comparisons(
        EVENT, dict(MARKET, usd_per_unit={}), dict(PPP, lcu_per_intl_usd={}))
    assert all(r["flags"] == ["NO_MARKET_RATE", "NO_PPP_FACTOR"]
               for r in empty["rows"])
    assert [r["declared_implied_usd_per_unit"] for r in empty["rows"]] == \
        [EXPECTED_ROWS[c][0] for c in sorted(EXPECTED_ROWS)]


def test_rate_comparison_rounds_each_column_once_from_exact_values():
    rec = _both_rate_comparisons(EVENT_SIX, MARKET, PPP)
    u = {c: Fraction(v) for c, v in EVENT_SIX["units_per_successor"].items()}
    for r in rec["rows"]:
        c = r["code"]
        implied = u["USD"] / u[c]
        market = Fraction(MARKET["usd_per_unit"][c])
        factor = Fraction(PPP["lcu_per_intl_usd"][c])
        assert r["declared_implied_usd_per_unit"] == _round50_text(implied)
        assert r["declared_over_market"] == _round50_text(implied / market)
        assert r["declared_over_ppp"] == _round50_text(implied * factor)
    cny = [r for r in rec["rows"] if r["code"] == "CNY"][0]
    assert cny["declared_implied_usd_per_unit"] == \
        "0.29816436138344434162605170765766658485236074925643"
    assert cny["declared_over_market"] == \
        "2.9816436138344434162605170765766658485236074925643"
    assert cny["declared_over_ppp"] == \
        "1.1926574455337773665042068306306663394094429970257"
    # a column computed from the already rounded implied column would give
    # other last digits (the case pinned here: GBP at a market rate of 1.25
    # and a factor of 0.64)
    gbp = [r for r in rec["rows"] if r["code"] == "GBP"][0]
    implied = _round50(u["USD"] / u["GBP"])
    assert gbp["declared_implied_usd_per_unit"] == \
        "0.14213570925052506122686278642180766407709134248527"
    assert gbp["declared_over_market"] == \
        "0.11370856740042004898149022913744613126167307398821"
    assert _round50_text(implied / Fraction("1.25")) == \
        "0.11370856740042004898149022913744613126167307398822"
    assert gbp["declared_over_ppp"] == \
        "0.090966853920336039185192183309956905009338459190570"
    assert _round50_text(implied * Fraction("0.64")) == \
        "0.090966853920336039185192183309956905009338459190573"
    assert verify_independent.compare_rate_comparison(
        EVENT_SIX, MARKET, PPP, rec) == []


def test_rate_comparison_ties_round_to_even():
    """Half-way cases at the 51st significant digit, through the public
    function: the kept digit 0 stays, 1 goes up to 2, 2 stays."""
    cases = [("1." + "0" * 49 + "5", "1." + "0" * 49),        # 0 stays
             ("1." + "0" * 48 + "15", "1." + "0" * 48 + "2"),  # 1 -> 2
             ("1." + "0" * 48 + "25", "1." + "0" * 48 + "2")]  # 2 stays
    for usd, want in cases:
        assert len(usd) == 52 and len(want) == 51, (usd, want)
        event = dict(EVENT, units_per_successor={"USD": usd, "EUR": "1"})
        rec = _both_rate_comparisons(
            event, dict(MARKET, usd_per_unit={"USD": "1", "EUR": "1"}),
            dict(PPP, lcu_per_intl_usd={"USD": "1", "EUR": "1"}))
        eur, us = rec["rows"]
        assert eur["code"] == "EUR" and us["code"] == "USD"
        assert eur["declared_implied_usd_per_unit"] == want, usd
        assert eur["declared_over_market"] == want, usd
        assert eur["declared_over_ppp"] == want, usd
        assert want == _round50_text(Fraction(usd))
        assert us["declared_implied_usd_per_unit"] == "1"


def test_the_text_of_a_table_value_is_part_of_the_identity():
    """A table value is echoed verbatim: another text for the same value
    gives the same ratios and another record hash. A USD entry may be any
    text of the value 1."""
    base = worldyard.rate_comparison(EVENT, MARKET, PPP)
    for usd_text in ("1.0", "01", "1.000"):
        for eur_text in ("1.250", "01.25"):
            market = copy.deepcopy(MARKET)
            market["usd_per_unit"]["USD"] = usd_text
            market["usd_per_unit"]["EUR"] = eur_text
            rec = _both_rate_comparisons(EVENT, market, PPP)
            by = {r["code"]: r for r in rec["rows"]}
            assert by["USD"]["market_usd_per_unit"] == usd_text
            assert by["EUR"]["market_usd_per_unit"] == eur_text
            assert by["EUR"]["declared_over_market"] == "1"
            assert [r["declared_over_market"] for r in rec["rows"]] == \
                [r["declared_over_market"] for r in base["rows"]]
            assert rec["record_hash"] != base["record_hash"]
            # the published record is checked against its own inputs only
            assert verify_independent.compare_rate_comparison(
                EVENT, market, PPP, rec) == []
            assert verify_independent.compare_rate_comparison(
                EVENT, MARKET, PPP, rec) != []


BAD_TABLE_VALUES = ("0", "0.000", "-1", "+1", "1e2", "1E+2", " 1.25", "1.25 ",
                    ".5", "5.", "1_0", "1,25", "١", "１.２５",
                    "", "1.2.5", "Infinity", "NaN", "1" * 81, None, True,
                    1.25, 1, ["1.25"], {"v": "1.25"})


def test_rate_comparison_rejects_malformed_requests():
    def m(**kw):
        return dict(copy.deepcopy(MARKET), **kw)

    def p(**kw):
        return dict(copy.deepcopy(PPP), **kw)

    def m_rate(code, value):
        return m(usd_per_unit=dict(MARKET["usd_per_unit"], **{code: value}))

    def p_factor(code, value):
        return p(lcu_per_intl_usd=dict(PPP["lcu_per_intl_usd"],
                                       **{code: value}))

    no_usd = copy.deepcopy(EVENT)
    del no_usd["units_per_successor"]["USD"]
    bad = [
        (EVENT, m(numeraire="EUR"), PPP),              # the anchor is USD
        (EVENT, m(numeraire="usd"), PPP),
        (EVENT, m(numeraire=["USD"]), PPP),
        (no_usd, MARKET, PPP),                         # no declared USD rate
        (EVENT, m(date="2100-01-01"), PPP),            # not before the event
        (EVENT, m(date="2150-06-30"), PPP),
        (EVENT, m(date="2099-12-32"), PPP),
        (EVENT, m(date="2099-12-31 "), PPP),
        (EVENT, m(date=20991231), PPP),
        (EVENT, m(date=None), PPP),
        (EVENT, MARKET, p(reference_year="2100")),     # 1 July 2100 is later
        (EVENT, MARKET, p(reference_year="99")),
        (EVENT, MARKET, p(reference_year=2099)),
        (EVENT, MARKET, p(reference_year="0000")),
        (EVENT, MARKET, p(reference_year="20 9")),
        (EVENT, MARKET, p(reference_year="２０９９")),
        (EVENT, MARKET, p(reference_year="2099-07-01")),
        (EVENT, m_rate("XYZ", "1"), PPP),              # not an event code
        (EVENT, m_rate("W", "1"), PPP),                # the successor itself
        (EVENT, MARKET, p_factor("XYZ", "1")),
        (EVENT, m(usd_per_unit={1: "1"}), PPP),
        (EVENT, m(usd_per_unit=dict(MARKET["usd_per_unit"], USD="1.01")), PPP),
        (EVENT, MARKET, p(lcu_per_intl_usd=dict(PPP["lcu_per_intl_usd"],
                                                 USD="2"))),
        (EVENT, m(usd_per_unit=None), PPP),
        (EVENT, m(usd_per_unit=[["EUR", "1.25"]]), PPP),
        (EVENT, MARKET, p(lcu_per_intl_usd="4")),
        (EVENT, m(source=""), PPP),
        (EVENT, m(source=5), PPP),
        (EVENT, MARKET, p(source="")),
        (EVENT, MARKET, p(source=None)),
        (EVENT, m(note="x"), PPP),                     # unknown key
        (EVENT, {k: v for k, v in MARKET.items() if k != "date"}, PPP),
        (EVENT, MARKET, p(note="x")),
        (EVENT, MARKET, {k: v for k, v in PPP.items() if k != "source"}),
        (EVENT, None, PPP),
        (EVENT, MARKET, None),
        (EVENT, [MARKET], PPP),
        (EVENT, MARKET, "ppp"),
        (dict(EVENT, scenario="real"), MARKET, PPP),
        (dict(EVENT, successor="WLD"), MARKET, PPP),
        (dict(EVENT, units_per_successor={}), MARKET, PPP),
        (dict(EVENT, declaration={"text": {1, 2}}), MARKET, PPP),
        (None, MARKET, PPP),
        # no USD anywhere: refused as such, not by a table's USD entry
        (no_usd, {k: (v if k != "usd_per_unit" else
                      {c: r for c, r in v.items() if c != "USD"})
                  for k, v in MARKET.items()},
         {k: (v if k != "lcu_per_intl_usd" else
              {c: r for c, r in v.items() if c != "USD"})
          for k, v in PPP.items()}),
        # 1 July of the reference year ON the effective date is not before it
        (dict(EVENT, effective="2100-07-01"), MARKET,
         p(reference_year="2100")),
        (dict(EVENT, effective="2100-07-01"), m(date="2100-07-01"), PPP),
    ]
    for value in BAD_TABLE_VALUES:
        bad.append((EVENT, m_rate("EUR", value), PPP))
        bad.append((EVENT, MARKET, p_factor("CNY", value)))
    good = worldyard.rate_comparison(EVENT, MARKET, PPP)
    for args in bad:
        assert _raises_value_error(worldyard.rate_comparison, *args), args[1:]
        assert _raises_value_error(
            verify_independent.recompute_rate_comparison, *args), args[1:]
        # a malformed request is an error, never a difference
        assert _raises_value_error(
            verify_independent.compare_rate_comparison, *(args + (good,))), \
            args[1:]
    assert len(bad) == 46 + 2 * len(BAD_TABLE_VALUES)
    # the day before is accepted
    _both_rate_comparisons(dict(EVENT, effective="2100-07-02"), MARKET,
                           p(reference_year="2100"))
    _both_rate_comparisons(dict(EVENT, effective="2100-07-02"),
                           m(date="2100-07-01"), PPP)


def test_independent_verifier_recomputes_the_rate_comparison():
    for event in (EVENT, EVENT_SIX, EVENT_AWKWARD):
        rec = worldyard.rate_comparison(event, MARKET, PPP)
        assert verify_independent.recompute_rate_comparison(
            event, MARKET, PPP) == rec
        assert verify_independent.compare_rate_comparison(
            event, MARKET, PPP, rec) == []
        paths = list(_leaf_paths(rec))
        assert len(paths) == 13 + 6 * 7 + 3, len(paths)  # flags are empty
        for path in paths:
            bad = _tampered(rec, path)
            assert verify_independent.compare_rate_comparison(
                event, MARKET, PPP, bad) != [], path
            # a forger who also recomputes the record's own hash is caught
            # (re-hashing an edit of the hash alone restores the original)
            if path != ("record_hash",):
                assert verify_independent.compare_rate_comparison(
                    event, MARKET, PPP, _rehashed(bad)) != [], path
    rec = worldyard.rate_comparison(EVENT, MARKET, PPP)
    # rows exchanged, reversed, dropped, repeated; a key added or removed
    rows = rec["rows"]
    edits = [dict(rec, rows=[rows[1], rows[0]] + rows[2:]),
             dict(rec, rows=rows[::-1]),
             dict(rec, rows=rows[:-1]),
             dict(rec, rows=rows + [rows[0]]),
             dict(rec, rows=[]),
             dict(rec, note="x"),
             {k: v for k, v in rec.items() if k != "notice"},
             {k: v for k, v in rec.items() if k != "record_hash"},
             dict(rec, rows=[dict(rows[0], extra=None)] + rows[1:]),
             dict(rec, rows=[{k: v for k, v in rows[0].items()
                              if k != "flags"}] + rows[1:]),
             dict(rec, rows=[dict(rows[0], flags=["NO_MARKET_RATE"])]
                  + rows[1:]),
             dict(rec, market=dict(rec["market"], source="another source")),
             dict(rec, information_only=False),
             dict(rec, format="worldyard-rate-comparison-2")]
    for bad in edits:
        assert verify_independent.compare_rate_comparison(
            EVENT, MARKET, PPP, bad) != [], bad
        if _rehashed(bad) != rec:      # dropping the hash alone: restored
            assert verify_independent.compare_rate_comparison(
                EVENT, MARKET, PPP, _rehashed(bad)) != [], bad
    # the record of another event, or of other tables, does not verify
    six = worldyard.rate_comparison(EVENT_SIX, MARKET, PPP)
    assert verify_independent.compare_rate_comparison(
        EVENT, MARKET, PPP, six) != []
    other = copy.deepcopy(PPP)
    other["lcu_per_intl_usd"]["INR"] = "20"
    assert verify_independent.compare_rate_comparison(
        EVENT, MARKET, other, rec) != []


def test_a_malformed_rate_comparison_is_a_difference_not_an_exception():
    rec = worldyard.rate_comparison(EVENT, MARKET, PPP)
    for bad in (None, [], "record", 1, [rec]):
        diffs = verify_independent.compare_rate_comparison(
            EVENT, MARKET, PPP, bad)
        assert diffs == [("record", "an object", bad)], bad
    # JSON types: `true` written as 1, or a number instead of its string.
    # Equal in Python, other bytes: caught with the hash left alone (the
    # record's own hash no longer matches) and with it recomputed (it is then
    # not the expected hash).
    one = dict(rec, information_only=1)
    assert one == rec
    assert verify_independent.compare_rate_comparison(
        EVENT, MARKET, PPP, one) != []
    assert verify_independent.compare_rate_comparison(
        EVENT, MARKET, PPP, _rehashed(one)) != []
    rows = copy.deepcopy(rec["rows"])
    rows[0]["declared_over_market"] = 1.25
    as_number = dict(rec, rows=rows)
    assert verify_independent.compare_rate_comparison(
        EVENT, MARKET, PPP, as_number) != []
    # a record that is not JSON data is a difference, not a crash
    rows = copy.deepcopy(rec["rows"])
    rows[0]["flags"] = {"NO_MARKET_RATE"}
    diffs = verify_independent.compare_rate_comparison(
        EVENT, MARKET, PPP, dict(rec, rows=rows))
    assert diffs and diffs[0][0] == "record_hash (internal integrity)"


def test_rate_comparison_agrees_on_random_inputs():
    """Seeded random events and tables: the engine, the independent verifier
    and the test-side integer rounding give the same strings."""
    rng = random.Random(20261117)
    codes = ["USD", "EUR", "CNY", "JPY", "GBP", "INR", "AAA", "BBB"]

    def number():
        digits = str(rng.randint(1, 10 ** rng.randint(1, 30)))
        cut = rng.randint(0, len(digits))
        text = (digits[:cut] or "0") + ("." + digits[cut:] if digits[cut:]
                                        else "")
        return text if len(text) <= 80 else digits[:80]

    for _ in range(150):
        chosen = ["USD"] + rng.sample(codes[1:], rng.randint(0, 7))
        event = dict(EVENT, units_per_successor={c: number() for c in chosen})
        mt = {c: number() for c in chosen if rng.random() < 0.8}
        pt = {c: number() for c in chosen if rng.random() < 0.8}
        for t in (mt, pt):
            if "USD" in t:
                t["USD"] = rng.choice(["1", "1.0", "01"])
        market = dict(MARKET, usd_per_unit=mt)
        ppp = dict(PPP, lcu_per_intl_usd=pt)
        rec = _both_rate_comparisons(event, market, ppp)
        u = {c: Fraction(v) for c, v in event["units_per_successor"].items()}
        assert [r["code"] for r in rec["rows"]] == sorted(chosen)
        for r in rec["rows"]:
            c = r["code"]
            implied = u["USD"] / u[c]
            assert r["declared_implied_usd_per_unit"] == _round50_text(implied)
            if c in mt:
                assert r["declared_over_market"] == \
                    _round50_text(implied / Fraction(mt[c]))
            else:
                assert r["declared_over_market"] is None
                assert "NO_MARKET_RATE" in r["flags"]
            if c in pt:
                assert r["declared_over_ppp"] == \
                    _round50_text(implied * Fraction(pt[c]))
            else:
                assert r["declared_over_ppp"] is None
                assert "NO_PPP_FACTOR" in r["flags"]
        assert verify_independent.compare_rate_comparison(
            event, market, ppp, rec) == []


def test_rate_comparison_leaves_inputs_and_the_callers_context_alone():
    event, market, ppp = (copy.deepcopy(EVENT_SIX), copy.deepcopy(MARKET),
                          copy.deepcopy(PPP))
    want = worldyard.rate_comparison(event, market, ppp)
    assert (event, market, ppp) == (EVENT_SIX, MARKET, PPP)
    # no aliasing: editing the record does not edit the inputs, or v.v.
    want["market"]["source"] = "edited"
    want["rows"][0]["flags"].append("X")
    assert market == MARKET
    want = worldyard.rate_comparison(event, market, ppp)
    market["usd_per_unit"]["EUR"] = "2"
    assert want == worldyard.rate_comparison(EVENT_SIX, MARKET, PPP)
    saved = decimal.getcontext().copy()
    try:
        _hostile_context()
        got = (worldyard.rate_comparison(EVENT_SIX, MARKET, PPP),
               verify_independent.recompute_rate_comparison(
                   EVENT_SIX, MARKET, PPP))
    finally:
        decimal.setcontext(saved)
    assert got == (want, want)


def test_gap_of_the_frozen_record_is_the_weighted_mean_of_the_ratios():
    """The link between the two records: final_value / bridged value equals
    the mean of declared_over_market weighted by the realized weights at
    valuation. Both are comparisons only."""
    art = worldyard.build_artifact(SPEC_USD)
    rec = worldyard.freeze_fx_leg(SPEC_USD, EVENT, VALUATION_DATE)
    rows = {r["code"]: r for r in
            worldyard.rate_comparison(EVENT, MARKET, PPP)["rows"]}
    contrib = {r["code"]: Fraction(r["fixed_amount"])
               * Fraction(e["fx_valuation_usd_per_unit"])
               for r, e in zip(art["basket"], SPEC_USD["basket"])}
    total = sum(contrib.values())
    mean = sum(contrib[c] / total * Fraction(rows[c]["declared_over_market"])
               for c in contrib)
    assert mean == (Fraction(rec["final_value"])
                    / Fraction(rec["comparison"]["last_fx_leg_value_bridged"]))
    assert mean == Fraction("0.800625") / Fraction("0.739625")


# --- the independent verifier's command line ----------------------------------------
def _verifier_cli(words, files):
    """Run verify_independent.py with `files` (name -> JSON value, or bytes
    written as they are) in a temporary directory. In `words`, "@name" is the
    path of that file. Return (exit code, stdout)."""
    with tempfile.TemporaryDirectory() as tmp:
        paths = {}
        for name, value in files.items():
            paths[name] = os.path.join(tmp, name + ".json")
            if isinstance(value, bytes):
                with open(paths[name], "wb") as fh:
                    fh.write(value)
            else:
                with open(paths[name], "w", encoding="utf-8") as fh:
                    json.dump(value, fh, ensure_ascii=False)
        argv = [paths.get(w[1:], os.path.join(tmp, "missing.json"))
                if w.startswith("@") else w for w in words]
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "verify_independent.py")]
            + argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return proc.returncode, proc.stdout.decode("utf-8")


def test_verifier_command_line_checks_the_records():
    art = worldyard.build_artifact(SPEC_USD)
    frozen = worldyard.freeze_fx_leg(SPEC_USD, EVENT, VALUATION_DATE)
    comparison = worldyard.rate_comparison(EVENT, MARKET, PPP)
    files = {"spec": SPEC_USD, "art": art, "event": EVENT, "frozen": frozen,
             "market": MARKET, "ppp": PPP, "cmp": comparison}
    base = ["@spec", "@art"]
    with_frozen = base + ["--event", "@event", "--frozen-record", "@frozen"]
    with_cmp = base + ["--event", "@event", "--market", "@market",
                       "--ppp", "@ppp", "--rate-comparison", "@cmp"]
    everything = with_frozen + ["--market", "@market", "--ppp", "@ppp",
                                "--rate-comparison", "@cmp"]

    # without flags the output is what it always was
    code, out = _verifier_cli(base, files)
    lines = out.splitlines()
    assert code == 0 and lines[0] == "INDEPENDENT VERIFICATION: PASS", out
    assert [l.split(":")[0].strip() for l in lines[1:]] == \
        ["spec", "artifact", "input_digest", "artifact_hash", "value_usd"]
    assert lines[3] == "  input_digest  : " + SRC_INPUT_DIGEST
    assert lines[4] == "  artifact_hash : " + SRC_ARTIFACT_HASH
    assert lines[5] == "  value_usd     : 0.92453125 USD"

    code, out = _verifier_cli(with_frozen, files)
    assert code == 0, out
    assert "INDEPENDENT VERIFICATION: PASS" in out
    assert "FROZEN RECORD: PASS" in out and frozen["record_hash"] in out
    assert ("final_value   : 0.800625 W (fictional scenario identifier, "
            "not a currency)") in out
    code, out = _verifier_cli(with_cmp, files)
    assert code == 0, out
    assert "RATE COMPARISON (information only): PASS" in out
    assert comparison["record_hash"] in out
    assert "no column is a conversion rate" in out
    code, out = _verifier_cli(everything, files)
    assert code == 0 and out.count(": PASS") == 3, out

    # a differing field in any requested record: exit 1, the field listed,
    # the other checks still reported
    bad_frozen = dict(frozen, final_value="0.8")
    code, out = _verifier_cli(everything, dict(files, frozen=bad_frozen))
    assert code == 1, out
    assert "FROZEN RECORD: FAIL" in out and "field    : final_value" in out
    assert "INDEPENDENT VERIFICATION: PASS" in out
    assert "RATE COMPARISON (information only): PASS" in out
    rows = copy.deepcopy(comparison["rows"])
    rows[0]["declared_over_market"] = "1.26"
    code, out = _verifier_cli(with_cmp, dict(files, cmp=dict(comparison,
                                                              rows=rows)))
    assert code == 1 and "RATE COMPARISON (information only): FAIL" in out
    assert "rows[0].declared_over_market" in out
    code, out = _verifier_cli(with_cmp, dict(files, cmp=[comparison]))
    assert code == 1 and "field    : record" in out
    code, out = _verifier_cli(everything, dict(files, art=dict(art,
                                                               value_usd="1")))
    assert code == 1 and "INDEPENDENT VERIFICATION: FAIL" in out
    assert out.count(": PASS") == 2, out
    # the frozen record of another event
    six = worldyard.freeze_fx_leg(SPEC_USD, EVENT_SIX, VALUATION_DATE)
    code, out = _verifier_cli(with_frozen, dict(files, frozen=six))
    assert code == 1, out

    # operational errors: exit 2
    needs = [
        base + ["--frozen-record", "@frozen"],                # no --event
        base + ["--event", "@event", "--rate-comparison", "@cmp",
                "--market", "@market"],                        # no --ppp
        base + ["--event", "@event", "--market", "@market",
                "--ppp", "@ppp"],                              # nothing to check
        base + ["--event", "@event"],
        base + ["--rate-comparison", "@cmp"],
        base + ["--unknown-flag", "x"],
        with_frozen[:-1] + ["@nowhere"],                       # unreadable file
    ]
    for words in needs:
        code, out = _verifier_cli(words, files)
        assert code == 2, (words, out)
    for name in ("event", "frozen", "market", "ppp", "cmp"):
        code, out = _verifier_cli(everything, dict(files, **{name: b"{"}))
        assert code == 2 and out.startswith("ERROR"), (name, out)
    for name, value in (("event", dict(EVENT, scenario="real")),
                        ("market", dict(MARKET, numeraire="EUR")),
                        ("ppp", dict(PPP, reference_year="2100"))):
        code, out = _verifier_cli(everything, dict(files, **{name: value}))
        assert code == 2 and out.startswith("ERROR"), (name, out)
    # the frozen record is checked against the spec it was made from: a
    # declared-numeraire spec is not frozen
    spec_w = _spec_w()
    code, out = _verifier_cli(with_frozen, dict(
        files, spec=spec_w, art=worldyard.build_artifact(spec_w)))
    assert code == 2 and out.startswith("ERROR"), out


# --- the registry rule for frozen records -----------------------------------------
def _fails_registry_check(entry, spec, load, directory=None):
    import test_vintages
    try:
        test_vintages.check_frozen_warnings(entry, spec, load, directory)
    except AssertionError:
        return True
    return False


def test_frozen_record_enters_the_registry_as_a_structured_warning():
    """No shipped vintage is frozen, so data/vintages.json has no such
    warning; the rule is exercised on a registry entry built here (a
    hypothetical entry, not a real vintage)."""
    import test_vintages
    art = worldyard.build_artifact(SPEC_USD)
    rec = worldyard.freeze_fx_leg(SPEC_USD, EVENT, VALUATION_DATE)
    files = {"x/spec.json": SPEC_USD, "x/artifact.json": art,
             "x/event.json": EVENT, "x/frozen.json": rec}
    warning = {"code": "FX_LEG_FROZEN_AT_CHANGEOVER",
               "detail": "hypothetical test entry; not a real vintage",
               "scenario": "hypothetical", "event_id": EVENT["id"],
               "event_hash": rec["event_hash"], "effective": "2100-01-01",
               "record_hash": rec["record_hash"],
               "event_file": "x/event.json", "record_file": "x/frozen.json"}
    other_warning = {"code": "PPP_LABEL", "detail": "an ordinary warning"}
    entry = {"id": "x", "artifact_hash": art["artifact_hash"],
             "status": "current", "supersedes": [], "superseded_by": [],
             "warnings": [other_warning, warning]}

    def load(path):
        return copy.deepcopy(files[path])

    assert test_vintages.check_frozen_warnings(entry, SPEC_USD, load) == 1
    assert test_vintages.check_frozen_warnings(entry, SPEC_USD, load,
                                               "x") == 1
    assert test_vintages.check_frozen_warnings(
        dict(entry, warnings=[other_warning]), SPEC_USD, load) == 0

    def with_warning(**changes):
        bad = copy.deepcopy(entry)
        bad["warnings"][1].update(changes)
        return bad

    # a field that does not match the record
    for key in ("record_hash", "event_hash", "event_id", "effective",
                "scenario"):
        assert _fails_registry_check(
            with_warning(**{key: "sha256:" + "0" * 64}), SPEC_USD, load), key
    # a missing, empty, non-string or unknown field
    for key in test_vintages.FROZEN_WARNING_KEYS[1:]:
        bad = copy.deepcopy(entry)
        del bad["warnings"][1][key]
        assert _fails_registry_check(bad, SPEC_USD, load), key
        for value in ("", None, 1):
            assert _fails_registry_check(with_warning(**{key: value}),
                                         SPEC_USD, load), (key, value)
    assert _fails_registry_check(with_warning(note="x"), SPEC_USD, load)
    # file paths: repository-relative, inside the vintage's directory, and
    # never one of the vintage's own files
    for path in ("/x/frozen.json", "x/../x/frozen.json", "x//frozen.json",
                 "x\\frozen.json", "x/./frozen.json", "x/event.json"):
        assert _fails_registry_check(with_warning(record_file=path),
                                     SPEC_USD, load), path
    for path in ("y/frozen.json", "x/sub/frozen.json"):
        files[path] = rec
        assert _fails_registry_check(with_warning(record_file=path),
                                     SPEC_USD, load, "x"), path
    for own in test_vintages.VINTAGE_OWN_FILES:
        mapped = dict(files, **{"x/" + own: rec})

        def load_own(path, mapped=mapped):
            return copy.deepcopy(mapped[path])

        bad = with_warning(record_file="x/" + own)
        # a valid record, but stored as one of the vintage's own files
        assert not _fails_registry_check(bad, SPEC_USD, load_own), own
        assert _fails_registry_check(bad, SPEC_USD, load_own, "x"), own
    # the record of another artifact; the wrong spec; a second warning for
    # the same event; a record the independent verifier does not reproduce
    other = dict(entry, artifact_hash="sha256:" + "1" * 64)
    assert _fails_registry_check(other, SPEC_USD, load)
    assert _fails_registry_check(entry, dict(SPEC_USD, method="openunit"),
                                 load)
    twice = dict(entry, warnings=[warning, dict(warning)])
    assert _fails_registry_check(twice, SPEC_USD, load)
    forged = _rehashed(dict(rec, final_value="0.8"))
    files["x/forged.json"] = forged
    assert _fails_registry_check(
        with_warning(record_file="x/forged.json",
                     record_hash=forged["record_hash"]), SPEC_USD, load)
    # an event the format refuses is a failed check, not a crash
    files["x/bad_event.json"] = dict(EVENT, scenario="real")
    assert _fails_registry_check(with_warning(event_file="x/bad_event.json"),
                                 SPEC_USD, load)
    # the registry test runs the rule on every shipped entry
    import inspect
    assert "check_frozen_warnings(" in inspect.getsource(
        test_vintages.test_vintage_registry_is_consistent)
    # the shipped registry: no vintage is frozen
    reg = _load("data", "vintages.json")
    assert reg["format"] == "openunit-vintage-registry-1"
    assert not any(w["code"] == "FX_LEG_FROZEN_AT_CHANGEOVER"
                   for v in reg["vintages"] for w in v["warnings"])
    for v in reg["vintages"]:
        spec = _load("data", v["id"], "spec.json")
        assert test_vintages.check_frozen_warnings(
            v, spec, lambda p: _load(*p.split("/")), "data/" + v["id"]) == 0


# --- runner ---------------------------------------------------------------------
def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS  " + t.__name__)
        except Exception as exc:   # noqa: BLE001 -- report every failure kind
            failed += 1
            print("FAIL  %s: %s: %s" % (t.__name__, type(exc).__name__, exc))
    print("-" * 50)
    print("%d/%d PASS" % (len(tests) - failed, len(tests)))
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run() else 0)
