# Worldyard (formerly openunit) — Artifact & Spec Format

**Format standard version `worldyard-artifact-3`** (succeeds
`worldyard-artifact-2` and `openunit-artifact-1`). This document fixes the
on-disk and on-the-wire byte layout precisely enough for an independent
implementation to reproduce Worldyard hashes exactly. The authoritative encoder
is `worldyard.canonical`; the normative behavior is the text of this document
plus `SPEC.md`. Sections 1–8 are the format; section 9 states conformance and
names the minimal third-party verifier; sections 10, 11 and 12 define the
event object, the frozen record and the information-only rate comparison of a
hypothetical scenario.

**What changed from `worldyard-artifact-2`:**

1. **The numeraire has a rule** (§4). A numeraire that is not declared must be
   exactly three upper-case ASCII letters. `-2` accepted any value.
2. **A numeraire can be declared** (§4.1, §6.1), for hypothetical scenarios
   only: a fictional scenario identifier such as `"W"`, which can never have
   the shape of a currency code. An artifact with a declared numeraire
   restates the two values of its source artifact (`baseline_value`, `value`
   instead of `baseline_value_usd`, `value_usd`) and keeps every basket row.
3. **The decimal context is stated in full** (§1), and the new numbers are
   exact rationals rounded once (§1.1).
4. **Three objects for a hypothetical scenario** are defined next to the
   artifact: the whole-basket successor event (§10), the frozen record
   (§11, its own format name `worldyard-frozen-record-1`) and the
   information-only rate comparison (§12, `worldyard-rate-comparison-1`).
   None of them changes any artifact.

Every conforming `worldyard-artifact-2` spec and artifact whose numeraire is
three upper-case ASCII letters, or absent, is a `worldyard-artifact-3` spec
and artifact with the same bytes and the same hashes. That includes every
shipped vintage. A `-2` spec with any other numeraire value is not a `-3`
spec; its `-2` artifact still verifies with a `-2` verifier. A `-2` verifier
reports an artifact with a declared numeraire as a mismatch (§9).

**What changed from `openunit-artifact-1`** (in `-2`): only the `method` field.
It may be `"worldyard"` as well as `"openunit"`, and the artifact copies it
from the spec (§4, §6). Every conforming `openunit-artifact-1` spec (method
`"openunit"` or absent) and artifact is a `-2` and a `-3` spec and artifact
with the same bytes and the same hashes. The reverse does not hold: a `-1`
verifier expects `"openunit"` and reports a `"worldyard"` artifact as a
mismatch (§9).

> **Hypothetical scenarios.** The declared numeraire exists for thought
> experiments. "W" in the examples is a fictional scenario identifier, not a
> currency code. Nothing in this format is a forecast, a proposal or an offer
> of any currency. A successful verification shows only that an artifact
> reproduces from its spec; it does not show that a declared rate is
> authentic, right or fair.

## 1. Numbers are strings

Every numeric quantity in a spec and in an artifact is a JSON **string** holding
an exact decimal literal (e.g. `"0.985630795110700089…"`). Numbers are never
JSON numbers and are never built from floats. Implementations must use an exact
decimal type (Python `decimal.Decimal`) with **precision 50** and rounding
**ROUND_HALF_EVEN**, inside a context that does not leak to the caller and
takes nothing from the caller. Every field of that context is fixed:

| field | value |
|---|---|
| precision | 50 significant digits |
| rounding | `ROUND_HALF_EVEN` |
| `Emin`, `Emax` | −999999, 999999 |
| `capitals` | 1 (an exponent is written with an upper-case `E`) |
| `clamp` | 0 |
| flags | none set |
| traps | `InvalidOperation`, `DivisionByZero`, `Overflow` (an operation that raises one of them produces no artifact) |

In Python: `decimal.Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999,
Emax=999999, capitals=1, clamp=0, flags=[], traps=[InvalidOperation,
DivisionByZero, Overflow])`, used as a local context. Apart from precision and
rounding these are the values of Python's default context, so every artifact
built under the default context has the bytes it always had; what the full
statement removes is the dependence on a caller who changed that context (with
`capitals=0` a quantity would be written `6e+1` instead of `6E+1`, which is
another hash).

A decimal is written as Python's `str()` writes a `Decimal` under that
context: plain notation, and scientific notation when the exponent is positive
or the value is below 1E-6 (`"6E+1"`, `"5E-9"`).

### 1.1 Exact values, rounded once

The fields of §6–§7 are computed step by step, each operation rounded to
precision 50 as above. The numbers of a declared-numeraire artifact (§6.1) and
of a frozen record (§11) are defined differently: each is an **exact
rational** expression over decimal strings, rounded **once** at the end.

- `Q(s)` is the exact rational value of the decimal string `s`.
- `R50(x)` is the exact rational `x` rounded once to 50 significant digits,
  ties to even, and written as `str(Decimal(p) / Decimal(q))` for integers
  `p`, `q > 0` with `x = p / q`, under the context above. The string depends
  only on the value `x`, not on how the fraction is written. An exact value
  below 1E+50 is written in its shortest form; an exact value of 1E+50 or
  more is written with a 50-digit coefficient and an exponent, as `str()`
  writes such a quotient.

| exact value | `R50` | note |
|---|---|---|
| 1281/1600 | `0.800625` | exact: the shortest form |
| 6400/100 | `64` | an exact integer below 1E+50 has no exponent |
| 10^50 | `1.0000000000000000000000000000000000000000000000000E+50` | exact, 1E+50 or more: a 50-digit coefficient and an exponent |
| (10^50+5)/10^50 | `1.0000000000000000000000000000000000000000000000000` | half-way, kept digit even: stays |
| (10^50+15)/10^50 | `1.0000000000000000000000000000000000000000000000002` | half-way, kept digit odd: up |
| (10^51+51)/10^51 | `1.0000000000000000000000000000000000000000000000001` | just above half-way |
| 2/3 | `0.66666666666666666666666666666666666666666666666667` | 50 digits |
| -61/1000 | `-0.061` | |
| 5/10^9 | `5E-9` | |
| 0 | `0` | |

Two kinds of strings enter such an expression:

- A **declared number** (a declared rate) is kept verbatim in what is hashed,
  so its form is restricted to a plain decimal string: 1 to 80 characters,
  only the ASCII digits `0`–`9` and at most one `.`, a digit first and a digit
  last, and a value greater than zero. No sign, no exponent, no space, no
  `_`, no digits of other scripts, no `.5`, no `5.`. Leading and trailing
  zeros are allowed and kept: `"01.250"` is another text for the value of
  `"1.25"`, and another text gives another hash.
- A **number read back from an artifact** (`fixed_amount`, `value_usd`,
  `baseline_value_usd`, written by the rules of §6–§7) must be finite and
  `≥ 0`, and, unless it is zero, satisfy 1E-200 ≤ x < 1E+201. Outside that
  range, or below zero, the expression is not evaluated and nothing is
  produced.

A value in old units is always **divided** by the declared rate. An inverse
rate is never formed: 1,000,000 / 1.95583 = 511291.88…, while 1,000,000 ×
0.511292 (the inverse to six significant figures) = 511292.00.

## 2. Canonical encoding (used for all hashing)

A value is canonicalized as UTF-8 bytes of:

```python
json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
```

That is: keys sorted lexicographically, no insignificant whitespace, non-ASCII
emitted literally (not `\uXXXX`). **Hashing always uses this canonical form**,
regardless of how the file is pretty-printed on disk.

An object with a repeated key is not a valid spec, artifact, event, table or
record. Python's `json` module keeps the last of the repeated values and
another reader may keep the first, so one file could be read two ways; the
reference verifier refuses such a file (exit 2) and so does the CLI.

A number in free-form provenance (the extra keys of a spec, §4, and an
event's `declaration`, §10) is hashed as Python's `json` module writes it:
`1e22` is written `1e+22`, and `1` and `1.0` are different bytes, which
another language may not reproduce. Give such numbers as strings.

Files under `data/` are written pretty-printed (`indent=2`, `ensure_ascii=False`,
trailing newline) for human review. The pretty bytes are **not** what gets
hashed — the canonical bytes are. This is why a vintage can be reformatted for
reading without affecting its `artifact_hash`, and why `make_vintages.py
--verify` compares the pretty bytes it regenerates (to catch accidental edits)
while `verify_artifact` independently recomputes the canonical hashes.

## 3. Hashes

Both hashes are SHA-256 over canonical bytes, rendered lowercase hex with a
`sha256:` prefix:

- `input_digest  = "sha256:" + sha256(canonical(spec)).hexdigest()`
- `artifact_hash = "sha256:" + sha256(canonical(core)).hexdigest()`, where
  `core` is the artifact object **with the `artifact_hash` key removed**.

## 4. Spec object

| key | type | required | notes |
|---|---|---|---|
| `method` | string | yes | `"worldyard"`, or `"openunit"` (every spec written before the rename). An absent `method` is read as `"openunit"`, as `-1` implementations did; any other value is rejected (no artifact) |
| `method_version` | string | no | defaults to `"v0"`; e.g. `"v0.1"`, `"v0.2"` |
| `numeraire` | string | no | defaults to `"USD"`. Unless it is declared (§4.1) it must be exactly three upper-case ASCII letters; any other value is rejected (no artifact). PPP vintages (v0.2, v0.4) keep `"USD"` and their value is read as international dollars (`SPEC.md` §2.3) |
| `numeraire_declaration`, `numeraire_conversion` | objects | no | both or neither; they declare the numeraire (§4.1) |
| `weight_vintage` | object | yes | must contain `label` (string) and `basis` (string); any other keys are free-form provenance |
| `basket` | array | yes | one or more entries (§5) |
| *(any other keys)* | — | no | permitted; **included in `input_digest`** |

Because every extra key is hashed, descriptive fields such as `provenance`,
`disclaimer`, `note`, `rounding`, or raw `source_*` rates are part of the
spec's identity. Changing any of them changes `input_digest`.

The numeraire rule checks a shape, not a list: the format does not know which
three-letter codes are assigned currency codes. An undeclared numeraire other
than `"USD"` keeps the field names `baseline_value_usd` and `value_usd` (§6);
the rate fields of §5 are "numeraire per 1 unit" whatever their names say.

### 4.1 Declared numeraire (hypothetical scenarios only)

A spec that contains `numeraire_declaration` or `numeraire_conversion` has a
**declared numeraire**. Both keys are then required, and:

| key | rule |
|---|---|
| `numeraire` | required, and equal to `numeraire_declaration.code` |
| `numeraire_declaration` | an object with exactly the keys `code`, `kind`, `scenario`; `kind` is `"fictional_scenario_identifier"`; `scenario` is `"hypothetical"`; `code` is a fictional identifier |
| `numeraire_conversion` | an object with exactly the keys `from`, `units_of_old_per_new`, `source_artifact_hash`, `source_input_digest` |
| `numeraire_conversion.from` | the old numeraire: exactly three upper-case ASCII letters |
| `numeraire_conversion.units_of_old_per_new` | a declared number (§1.1): units of the old numeraire equal to **one** unit of the new one |
| `numeraire_conversion.source_artifact_hash`, `.source_input_digest` | `"sha256:"` and 64 lower-case hexadecimal characters: the two hashes of the source artifact |

A **fictional identifier** is a string of 1 to 16 ASCII letters and digits with
at least one letter that is **not exactly three letters** (in any case):
`"W"`, `"w"`, `"W1"`, `"WX"`, `"World2100"`, `"A1B"` qualify; `"WLD"`,
`"wld"`, `"USD"`, `"840"`, `"W-1"`, `""` do not. A fictional identifier can
therefore never have the shape of an undeclared numeraire, and a three-letter
numeraire can never be declared fictional.

The **source spec** of a declared spec is the same object without the two keys
and with `numeraire` set to `numeraire_conversion.from`. It is an ordinary spec
with an undeclared numeraire. A declared spec is accepted only if

- the source spec is not PPP-valued (every basket entry records
  `ppp_factor_lcu_per_intl_usd` and its `fx_valuation_usd_per_unit` equals
  1 / that factor exactly, `SPEC.md` §2.3): the value of such a spec is in
  international dollars, not an amount of a converting currency;
- the artifact built from the source spec per §6 has exactly the
  `artifact_hash` and the `input_digest` that `numeraire_conversion` carries.

Otherwise no artifact is produced. So a spec that only renames its numeraire,
with or without the declaration, is rejected; and the basket, the rates or the
provenance of a declared spec cannot be edited without changing the two
hashes it carries. The binding is to whatever source spec the declared spec
itself describes: which published artifact that source is, the spec cannot
show (§6.1). The rate fields of the basket entries (§5) are not
re-expressed: they stay in the old numeraire, under their names.

## 5. Basket entry (spec)

| key | type | required | notes |
|---|---|---|---|
| `code` | string | yes | currency / economy code, e.g. `"INR"` |
| `name` | string | no | defaults to `code` |
| `population` | string | yes | exact decimal headcount, `> 0` overall |
| `fx_baseline_usd_per_unit` | string | yes | numeraire per 1 unit at the weight vintage; `> 0` |
| `fx_valuation_usd_per_unit` | string | yes | numeraire per 1 unit on the valuation leg; `> 0` |
| `weight_multiplier` | string | no | defaults to `"1"`; see §2.2 of `SPEC.md` |
| *(any other keys)* | — | no | permitted; hashed as part of the spec |

## 6. Artifact object

Built deterministically from a spec. This section is the artifact of a spec
with an undeclared numeraire; §6.1 is the artifact of a declared one.

| key | type | notes |
|---|---|---|
| `method` | string | copied from the spec (`"openunit"` if the spec has none) |
| `method_version` | string | copied from the spec (default `"v0"`) |
| `numeraire` | string | copied from the spec (default `"USD"`); three upper-case ASCII letters (§4); for PPP vintages read as international dollars |
| `weight_vintage_label` | string | `spec.weight_vintage.label` |
| `weight_basis` | string | `spec.weight_vintage.basis` |
| `baseline_value_usd` | string | `= 1` by construction |
| `value_usd` | string | value of 1 unit on the valuation leg |
| `basket` | array | per-entry rows (§7) |
| `input_digest` | string | `sha256:` of the spec |
| `artifact_hash` | string | `sha256:` of the artifact minus this field |

The artifact intentionally does **not** echo the spec's free-form provenance;
provenance is bound to the artifact transitively through `input_digest`.

### 6.1 Artifact with a declared numeraire

Let `source` be the artifact of the source spec (§4.1), built per §6–§7, and
`k = Q(numeraire_conversion.units_of_old_per_new)`.

| key | value |
|---|---|
| `method`, `method_version`, `weight_vintage_label`, `weight_basis` | as in `source` |
| `numeraire` | the declared code |
| `numeraire_declaration`, `numeraire_conversion` | copied from the spec |
| `baseline_value` | `R50( Q(source.baseline_value_usd) / k )` |
| `value` | `R50( Q(source.value_usd) / k )` |
| `basket` | `source.basket`, unchanged (§7) |
| `input_digest` | `sha256:` of the declared spec |
| `artifact_hash` | `sha256:` of the artifact minus this field |

There is no `baseline_value_usd` and no `value_usd` in such an artifact, and no
other key. The two source values must be usable exactly (§1.1: not negative,
inside the supported range); otherwise no artifact is produced.

A declared numeraire **restates the published values and nothing else**: each
value field is the source's published string divided once by one declared
rate, and the rows (quantities and weights, none of which depends on a
numeraire) are the source's rows. The unit is the same basket. Anyone can
check from the declared spec alone that it restates the source artifact whose
hashes it carries: remove the two keys, restore the old numeraire, rebuild,
compare the two hashes. A successful verification shows that the artifact
restates the source artifact whose hashes the spec carries. It does not show
that this source is a particular published artifact: compare
`source_artifact_hash` with the published `artifact_hash`, obtained
elsewhere.

## 7. Basket row (artifact)

Always present:

| key | notes |
|---|---|
| `code` | from the spec entry |
| `name` | from the spec entry (defaults to `code`) |
| `population_share` | pure headcount share `population_i / Σ population` |
| `fixed_amount` | pinned quantity `effective_weight_i / fx_baseline_i` |
| `realized_weight_at_pin` | `= effective_weight_i` (and `= population_share` when no multipliers) |
| `realized_weight_at_valuation` | realized share at the valuation leg |

Present **only when at least one basket entry carries `weight_multiplier`**:

| key | notes |
|---|---|
| `weight_multiplier` | the entry's multiplier (`"1"` if it set one) |
| `effective_weight` | `(population_i · m_i) / Σ (population_j · m_j)` |

This conditional emission is the backward-compatibility rule: with no
multipliers anywhere, the two extra keys are absent and the artifact bytes match
plain openunit v0 exactly. (The same holds across the rename: a spec whose
`method` is `"openunit"` gives the artifact it always gave.)

## 8. Worked reference

The bundled illustrative v0 sample (`sample_input.json`) must always produce:

```
input_digest : sha256:9e5c721b2131fe92059f05d702668d2bcb428afab3a27b1e79da9e578a1ef055
artifact_hash: sha256:433d5e9560f8dcf928c6d2aff9c48ecb9eba558d19fc8eff191056f3f18356bd
```

The real `v0.1-2026-05-15` vintage must produce
`artifact_hash sha256:1e615cf7…9a3a`, the real-PPP `v0.2-ppp-2026-05-15`
vintage (World Bank `PA.NUS.PPP`, 2024) `sha256:566c95c1…b97a`, and the
UN-primary-file `v0.3-unwpp-2026-05-15` vintage `sha256:0fe13c83…b7af` (all
three with method `"openunit"`), and the corrected PPP vintage
`v0.4-ppp-unwpp-2026-05-15` (method `"worldyard"`) `sha256:d0fa4776…e175`.
Every bundled vintage is reproduced byte-for-byte by `test_vintages.py`. (A spec's
optional `supersedes` key, like every other extra key, is hashed as part of the
spec per §4; it changes no artifact field.)

A declared numeraire, on illustrative inputs (the fixture `SPEC_USD` of
`test_changeover.py`; none of its numbers is real data): the source artifact
has `baseline_value_usd` `"1.000000"`, `value_usd` `"0.92453125"` and
`artifact_hash sha256:1718ce9d…3189`. Declared as `"W"` at
`units_of_old_per_new` `"1.25"`, the artifact has `baseline_value` `"0.8"`,
`value` `"0.739625"`, the same six basket rows, `input_digest
sha256:676c6dda…7115` and `artifact_hash sha256:482f2276…9892`.

## 9. Conformance and the reference verifier

An implementation **conforms** to `worldyard-artifact-3` iff, for every spec it
accepts, it produces an artifact identical — byte for byte under the canonical
encoding (§2) — to one built per §§1–8 and `SPEC.md`, and computes the same
`input_digest` and `artifact_hash`. Concretely, a conforming implementation:

1. parses every numeric field as an exact decimal at precision 50,
   `ROUND_HALF_EVEN`, never as a float, under the fully stated context of §1,
   whatever the caller's own decimal context is;
2. hashes only the canonical bytes — keys sorted, `separators=(",", ":")`,
   `ensure_ascii=False`, UTF-8 (§2–3);
3. emits exactly the artifact fields of §6–7, including the conditional
   `weight_multiplier` / `effective_weight` pair **iff** at least one basket
   entry carries a multiplier (the backward-compatibility rule);
4. enforces the input domain of `SPEC.md` ("Input domain"): every `population`
   `≥ 0`, total population `> 0`, total effective weight `> 0`, every FX rate
   `> 0`; otherwise it produces no artifact;
5. copies `method` from the spec, reading an absent one as `"openunit"`, and
   produces no artifact for a `method` other than `"openunit"` or
   `"worldyard"` (§4, §6);
6. produces no artifact for an undeclared numeraire that is not exactly three
   upper-case ASCII letters (§4);
7. for a declared numeraire, enforces §4.1 (both keys, their exact key sets,
   the fictional identifier, the declared number, the binding to the source
   artifact, no PPP-valued source) and emits exactly the fields of §6.1, the
   two values as `R50` of exact quotients (§1.1), never through an inverse
   rate.

An implementation that also produces frozen records or rate comparisons
conforms for them iff each record is identical, under the canonical
encoding, to one built per §10–§12, and nothing is produced where those
sections say so.

**Minimal third-party verifier.** `verify_independent.py` (bundled) is a second
implementation of this standard written from `SPEC.md` and this document alone —
it never imports `worldyard`, `openunit`, `cli`, or `anchor`, and uses only the standard
library. It re-derives every field and both hashes from a spec and compares them
against a published artifact (`python3 verify_independent.py spec.json
artifact.json`, exit 0 iff every field matches); it also recomputes a frozen
record (§11) and a rate comparison (§12), as a library and from the command
line (`--event E.json --frozen-record R.json`; `--event E.json --market
M.json --ppp P.json --rate-comparison C.json`; exit 0 iff every requested
check passes, 1 if a field differs, 2 on an operational error). It is both the
conformance oracle for this standard and the tool a third party can run to check a published
value without trusting the Worldyard engine. `test_independent.py`,
`test_properties.py`, `test_compat.py` and `test_changeover.py` cross-validate
the engine against it. For the exact values of §1.1 the two take different
routes (the engine multiplies out integer numerators and denominators; the
verifier uses `fractions.Fraction`) and must still agree byte for byte.
The `openunit-artifact-1` verifier shipped with release 0.3.0 still
passes every vintage built before the rename; on a `"worldyard"` vintage it
reports two differing fields, `method` and `artifact_hash` (checked
2026-10-26). The `worldyard-artifact-2` verifier shipped with release 0.4.0
passes every shipped vintage; on the declared-numeraire example of §8 it
reports seven differing fields (checked 2026-11-17).

**Versioning.** This is `worldyard-artifact-3`. It increments
`worldyard-artifact-2` because it changes the input domain (the numeraire
rule of §4) and adds a field set (§6.1), even though no artifact of a shipped
vintage changes; `-2` incremented `openunit-artifact-1` for the `method`
value. A future revision that changes the byte layout, the field set, the
hashing, or the input domain in a hash-affecting way increments the standard
version again (`-4`, …); changes that do not affect any byte (documentation,
new optional descriptive spec keys, which are already hashed transparently per
§4) stay within `-3`.

## 10. Whole-basket successor event (hypothetical scenarios only)

An **event** is a JSON object that declares, for a thought experiment, that
every currency of a basket is converted into one successor unit on one date
(`SPEC.md`, "Whole-basket successor event"). It is an input, like a spec; it
is not part of any artifact of §6. It is validated strictly:

| key | required | rule |
|---|---|---|
| `event` | yes | exactly `"whole_basket_successor"` |
| `id` | yes | a non-empty string |
| `scenario` | yes | exactly `"hypothetical"` |
| `successor` | yes | a fictional identifier (§4.1) |
| `successor_kind` | yes | exactly `"fictional_scenario_identifier"` |
| `effective` | yes | a date `YYYY-MM-DD` (proleptic Gregorian, a real calendar date): the first date on which the event applies |
| `units_per_successor` | yes | a non-empty object. Each key is a non-empty string, an old currency code, and none equals `successor`. Each value is a declared number (§1.1): the units of that currency equal to **one** unit of the successor |
| `declaration` | no | an object; free-form provenance (an authority's wording, a source, the hash of a document). It is hashed with the event and never interpreted |

Any other key, a missing required key, a value of another type or an object
that is not a JSON object is an error: no result is produced. In particular
an event without rates is not a successor event, and the opposite quotation
(successor units per old unit) has no key: it is neither accepted nor
inverted.

`event_hash = "sha256:" + sha256(canonical(event)).hexdigest()` with the
encoding of §2. The order of the keys therefore does not matter, and every
rate text, the date, the identifiers and the optional `declaration` are bound
by the hash. Binding a text does not authenticate it. Give numbers inside
`declaration` as strings: a JSON number is hashed as Python's `json` module
writes it (§2). NaN and the infinities are not JSON: an event whose
`declaration` holds one, or holds anything else that is not JSON data, is
refused wherever the event is hashed (no record is produced).

The example of `SPEC.md` (illustrative values) has `event_hash
sha256:ff43b2b3…0c17`.

## 11. Frozen record (`worldyard-frozen-record-1`; hypothetical scenarios only)

After a whole-basket successor event every pinned quantity is a fixed amount
of the successor unit, so the value of the basket in that unit is a constant.
The **frozen record** states that constant and everything it was computed
from. It is built from three inputs: a spec, an event (§10) and a valuation
date.

Preconditions (otherwise no record is produced):

- the event is well formed (§10);
- the valuation date is a date `YYYY-MM-DD` strictly before `effective`. It
  is a **declaration** by whoever makes the record: building an artifact
  reads no dates, so only the order of the two dates can be checked;
- the spec has an undeclared numeraire (a declared-numeraire spec is not
  frozen; its source spec is) and builds an artifact per §6;
- the spec is not PPP-valued (§4.1): the value of such a spec is in
  international dollars, and no declared conversion rate applies to it;
- every basket `code` is a string, and the set of basket codes **equals** the
  set of keys of `units_per_successor`: a code without a rate and a rate
  without a code are both errors. A code may occur in several basket entries;
  each entry then uses the rate of its code;
- every `fixed_amount`, and `value_usd` when the comparison is made, is
  usable exactly (§1.1: not negative, inside the supported range).

Let `artifact` be the artifact of the spec, `u[c]` the declared rate text of
code `c`, and `N` the artifact's numeraire. The record has exactly these 21
keys:

| key | value |
|---|---|
| `format` | `"worldyard-frozen-record-1"` |
| `kind` | `"frozen_fx_leg"` |
| `state` | `"frozen_at_changeover"` |
| `flags` | sorted array: always `"FROZEN_AT_CHANGEOVER"`, plus `"NO_BRIDGE_RATE"` when `comparison` is null |
| `scenario` | `event.scenario` |
| `notice` | the fixed text below |
| `event_id` | `event.id` |
| `event_hash` | the hash of the event (§10) |
| `successor`, `successor_kind`, `effective` | copied from the event |
| `source_artifact_hash`, `source_input_digest` | `artifact.artifact_hash`, `artifact.input_digest` |
| `declared_valuation_date` | the valuation date, verbatim |
| `last_fx_leg_value` | `artifact.value_usd`, verbatim |
| `last_fx_leg_numeraire` | `N` |
| `basket` | one object per basket row, in basket order: `{"code", "fixed_amount", "units_per_successor"}` — the row's code, its `fixed_amount` verbatim, and `u[code]` verbatim |
| `final_value` | `R50( Σ_i Q(fixed_amount_i) / Q(u[code_i]) )` |
| `final_value_numeraire` | `event.successor` |
| `comparison` | the object below when `N` is a key of `units_per_successor`, otherwise `null` |
| `record_hash` | `"sha256:" + sha256(canonical(record without this key)).hexdigest()` |

`comparison`:

| key | value |
|---|---|
| `information_only` | `true` |
| `bridge_code` | `N` |
| `bridge_units_per_successor` | `u[N]`, verbatim |
| `last_fx_leg_value_bridged` | `R50( Q(last_fx_leg_value) / Q(u[N]) )` |
| `final_minus_bridged` | `R50( Q(final_value) − Q(last_fx_leg_value_bridged) )`, computed from the two strings of the record |

The notice is one line of ASCII, part of the format and hashed with the
record:

> Hypothetical scenario record: a thought experiment, not a forecast, a proposal or an offer of any currency. final_value is the pinned basket quantities divided by the declared rates; it does not show that the rates are authentic, right or fair. The comparison block is information only and depends on the bridge currency.

Rules of the arithmetic (§1.1):

- The quantities are the artifact's `fixed_amount` **strings**, the published
  pinned quantities, already rounded to 50 digits. They are not recomputed
  from unrounded weights.
- `final_value` is the exact sum of the exact quotients, rounded once. It is
  not a sum of rounded terms, so it does not depend on the order of the
  basket, and no term is multiplied by an inverse rate.
- `final_value` is the value of the unit after the event: it is fixed by the
  pinned quantities and the declared rates alone and depends neither on the
  old numeraire nor on any market rate.
- `last_fx_leg_value_bridged` restates the last value through the declared
  rate of the old numeraire **only**. It is, byte for byte, the `value` of the
  same artifact with the successor declared as numeraire at that rate (§6.1).
  It depends on which currency is the bridge; that is why the block is
  information only. The two numbers differ whenever the declared rates are
  not proportional to the last valuation rates, and `final_minus_bridged` may
  be negative.

What a record binds: the source artifact and, through its digest, the spec;
the last value of the FX leg, verbatim; the event, with every rate text, the
date, the identifiers and any `declaration`; the quantities and rates
actually used, row by row; the declared valuation date. What it does not
show: that a declared rate is authentic, right or fair, that the valuation
date is the date of the spec's rates, or that no later artifact exists.

Worked reference (illustrative inputs: the fixture of `test_changeover.py`,
whose pinned quantities are 0.1, 0.08, 2.8, 3.125, 0.02 and 32, with the event
of `SPEC.md` and the valuation date `2099-12-31`):

```
final_value               = 0.1/1.25 + 0.08/1 + 2.8/10 + 3.125/200 + 0.02/0.8 + 32/100
                          = "0.800625"
last_fx_leg_value_bridged = 0.92453125 / 1.25 = "0.739625"
final_minus_bridged       = "0.061"
record_hash               = sha256:046a68629bc2a04c9bc67c4e9acb729ea4d6588c24c8258c8154878769124e15
```

With rates that do not divide evenly (USD 1.95583, EUR 0.787564, CNY 6.55957,
JPY 166.386, GBP 13.7603, INR 40.3399; the digits of the 1998 euro conversion
rates, used only as realistic six-figure numbers) the exact sum is
324998693014926737430846021869425 / 233298442807885135774037893098282 and
`final_value` is `"1.3930598468784219051669093597680785533906689928212"`.

**Verifying a record.** A record reproduces iff recomputing it from the spec,
the event and its own `declared_valuation_date` gives the identical object
and its `record_hash` is the hash of the rest. `verify_independent.py` does
this without the engine (`compare_frozen_record(spec, event, record)`, an
empty list iff the record reproduces): a malformed spec or event is an error;
anything wrong with the record — not an object, a date that is missing,
malformed or not before the event, a wrong hash, any differing, missing or
extra field — is reported as a difference.

## 12. Rate comparison (`worldyard-rate-comparison-1`; hypothetical scenarios only; information only)

A **rate comparison** sets the declared rates of a whole-basket successor
event (§10) beside pinned market rates and PPP factors, as ratios. It
compares; it does not grade. Its implied column is a comparison quantity,
**not a conversion rate**, and must not be used to convert amounts: in the
euro precedent, conversion rates between two old currencies were "not
defined" and could not be used (`SPEC.md`, "Whole-basket successor event").
A PPP factor is not an exchange rate. No column shows a correct rate, or
that a currency is over- or undervalued.

It is built from three inputs: an event (§10) and two tables.

| input | rule |
|---|---|
| event | well formed (§10), and `"USD"` is one of its codes: USD is the numeraire of every rate field of this format, so it is the anchor of the comparison |
| `market` | exactly `{"source", "date", "numeraire", "usd_per_unit"}`. `source` a non-empty string; `numeraire` exactly `"USD"`; `date` a date `YYYY-MM-DD` strictly before `effective`; `usd_per_unit` an object |
| `ppp` | exactly `{"source", "reference_year", "lcu_per_intl_usd"}`. `source` a non-empty string; `reference_year` a string of four ASCII digits whose 1 July (the observation date of an annual series, `SPEC.md` "Data states and fallbacks") is strictly before `effective`; `lcu_per_intl_usd` an object |

In both tables every key is a code of the event and every value is a
declared number (§1.1), kept verbatim; a `"USD"` entry, if present, must
have the value 1 (any text of it, e.g. `"1"` or `"1.0"`). A code of the event
that a table does not list is not an error: that comparison is `null` and
flagged. The tables hold **pinned** values: whoever makes the record
resolves each input under `SPEC.md` "Data states and fallbacks" first, as for
a spec, and leaves out an input that resolved `unavailable`. Anything else
is an error: no record is produced.

The record has exactly these 14 keys:

| key | value |
|---|---|
| `format` | `"worldyard-rate-comparison-1"` |
| `kind` | `"rate_comparison"` |
| `information_only` | `true` |
| `scenario` | `event.scenario` |
| `notice` | the fixed text below |
| `event_id` | `event.id` |
| `event_hash` | the hash of the event (§10) |
| `successor`, `successor_kind`, `effective` | copied from the event |
| `market` | `{"source", "date", "numeraire"}` copied from the market table |
| `ppp` | `{"source", "reference_year"}` copied from the PPP table |
| `rows` | one object per code of the event, sorted by code (below) |
| `record_hash` | `"sha256:" + sha256(canonical(record without this key)).hexdigest()` |

Each row has exactly these 8 keys, with `u` the event's
`units_per_successor`, `m` the market table and `f` the PPP table:

| key | value |
|---|---|
| `code` | the code |
| `declared_units_per_successor` | `u[code]`, verbatim |
| `declared_implied_usd_per_unit` | `R50( Q(u[USD]) / Q(u[code]) )` |
| `market_usd_per_unit` | `m[code]` verbatim, or `null` |
| `declared_over_market` | `R50( Q(u[USD]) / Q(u[code]) / Q(m[code]) )`, or `null` |
| `ppp_lcu_per_intl_usd` | `f[code]` verbatim, or `null` |
| `declared_over_ppp` | `R50( Q(u[USD]) / Q(u[code]) × Q(f[code]) )`, or `null` |
| `flags` | sorted array: `"NO_MARKET_RATE"` when `m` has no entry for the code, `"NO_PPP_FACTOR"` when `f` has none |

Rules of the arithmetic (§1.1): each column is computed from the exact
values of the verbatim strings and rounded **once**; no column is computed
from another, already rounded one, and no inverse rate is formed. A ratio is
declared ÷ reference: 1 means the declared rates imply the reference figure
exactly. The PPP-implied international dollars per unit is `1 / f[code]`, so
`declared_over_ppp` is the implied rate times the factor: the price level
index (a PPP divided by an exchange rate; United States = 1) computed with
the declared-implied rate instead of a market rate.

The notice is one line of ASCII, part of the format and hashed with the
record:

> Information only. Hypothetical scenario: a thought experiment, not a forecast, a proposal or an offer of any currency. declared_implied_usd_per_unit is a comparison quantity derived from two declared rates; it is not a conversion rate and must not be used to convert amounts. A PPP factor is not an exchange rate: no column shows a correct rate, or that a currency is over- or undervalued.

What a record binds: the event (its hash covers every declared rate), the
names and dates of the two pinned tables and, row by row, every value used.
It is self-hashed; it is not anchored. What it does not show: that a declared
rate, a market rate or a PPP factor is authentic, right or fair.

Worked reference (illustrative inputs: the event of `SPEC.md`; market USD
per unit EUR 1.25, CNY 0.1, JPY 0.00625, GBP 1.25, INR 0.0125, USD 1, dated
`2099-12-31`; PPP factors EUR 0.8, CNY 4, JPY 100, GBP 0.64, INR 25, USD 1,
reference year `2099`; the two `source` texts of `test_changeover.py`):

| code | implied | over market | over PPP |
|---|---|---|---|
| CNY | `0.125` | `1.25` | `0.5` |
| EUR | `1.25` | `1` | `1` |
| GBP | `1.5625` | `1.25` | `1` |
| INR | `0.0125` | `1` | `0.3125` |
| JPY | `0.00625` | `1` | `0.625` |
| USD | `1` | `1` | `1` |

`record_hash sha256:946bced6f1f9672d248f2faae6a050f24b4fd6f466b7bdae5959887449299145`.
With the six-figure rates of §11 the CNY row reads
`0.29816436138344434162605170765766658485236074925643`,
`2.9816436138344434162605170765766658485236074925643` and
`1.1926574455337773665042068306306663394094429970257`.

The link to the frozen record (§11), when the spec's numeraire is USD and the
market table holds the spec's valuation rates: `final_value` divided by
`last_fx_leg_value_bridged` equals the mean of `declared_over_market`
weighted by the valuation contributions `Q(fixed_amount_i) ×
Q(fx_valuation_usd_per_unit_i)` of the source artifact's rows (exactly where
no value involved was rounded, as in the example: 0.800625 / 0.739625; with
the published, rounded `realized_weight_at_valuation` strings, to about 50
digits). Both are comparisons only.

**Verifying a record.** A record reproduces iff recomputing it from the
event and the two tables gives the identical object and its `record_hash` is
the hash of the rest. `verify_independent.py` does this without the engine
(`compare_rate_comparison(event, market, ppp, record)`, an empty list iff the
record reproduces): a malformed event or table is an error; anything wrong
with the record — not an object, a wrong hash, any differing, missing or
extra field — is reported as a difference.

