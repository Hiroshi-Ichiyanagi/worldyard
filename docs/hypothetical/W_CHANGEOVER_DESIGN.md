# Hypothetical whole-basket changeover ("W") — design notes

Status: **decided (2026-11-17); experimental and unreleased.** These notes
explain the design of the hypothetical-scenario helpers: a whole-basket
successor event, the frozen record, a declared numeraire, and an
information-only rate comparison. The normative rules are in `SPEC.md` and
`ARTIFACT_FORMAT.md` (§10–§12); where these notes and those documents differ,
those documents decide. Everything in §3 is implemented and tested; nothing
is released.

> **Framing.** This is a *hypothetical scenario*, a thought experiment: what
> Worldyard would need if every currency in its basket were converted into one
> successor unit on one date. **"W" is a fictional scenario identifier**, not a
> currency code. Nothing here is a forecast that this will happen, a proposal
> or offer of any currency, token or service, financial advice, or a claim of
> regulatory compliance. Every number in the tests is illustrative. A
> successful verification shows only that a record reproduces from its inputs,
> not that a declared rate is authentic, right or fair.

## 0. Limits first

1. **Coverage is small.** The basket has 6 entries (USD, EUR, CNY, JPY, GBP,
   INR, with the euro area as one entry). A rate comparison built on it covers
   at most 6 declared rates out of every currency such a changeover would
   convert. The ECB reference set itself quotes 29 currencies against the euro
   (file of 2026-11-16, §8).
2. **PPP is not an exchange rate.** The World Bank says PPPs "should not be
   interpreted as equilibrium exchange rates" and cannot indicate a "correct"
   rate or an over- or undervalued currency (§8). Every PPP column is
   information only.
3. **Worldyard cannot authenticate a declaration.** It can bind the hash of an
   event and show what reference data said; it cannot show that a declared
   conversion rate is the one an authority actually published.
4. **A fresh start has no rate.** If old balances were voided or re-allocated
   instead of converted, there is nothing to freeze or compare. That needs an
   allocation rule, which is outside a measuring stick (§3.7).
5. **After the event the FX leg measures nothing new.** Its value in the
   successor unit is a constant. It never promised constant purchasing power; a
   purchasing-power reading in the successor unit would be a new, separately
   named methodology (§6).
6. **No demand evidence.** This work answers a thought experiment, not a user
   request.
7. **Scope limits stay.** Worldyard is information only: not offered as a
   benchmark for financial instruments or contracts, nor as the backing of a
   token (README, "Scope, licence and terms").
8. **Hypothetical scenarios only.** An event must say `"scenario":
   "hypothetical"` and name a fictional successor; nothing else is accepted in
   this version (§3.3).

## 1. What was measured before deciding

On the working copy, Python 3.14.9, before any change:

| check | result |
|---|---|
| `python3 -m pytest` (before this work) | 90 passed |
| 9 standalone suites | 17+4+7+6+6+8+29+9+4 = 90 PASS |
| `python3 make_vintages.py --verify` | 4/4 vintages reproduce |
| `verify_independent.py` on each `data/*/spec.json` | 4/4 PASS |

Findings that shaped the design:

- **Whole basket through the per-series rule.** Six series, each with a
  `fixed_conversion` into W: every input ends `unavailable` with
  `SUCCESSOR_UNAVAILABLE:NO_OBSERVATION`, because the successor series "USD per
  W" cannot exist once USD itself is converted. Safe, but the reason is wrong:
  nothing is missing; the leg has ended.
- **Numeraire.** `build_artifact` accepted `"numeraire": "W"` with no
  declaration, and the integer `12345`. Rebuilding the same basket with
  W-denominated rates re-pinned the unit: a `fixed_amount` of 0.25 became
  0.3125. The unit was silently re-defined instead of kept.
- **Rounding term by term is not well defined enough.** On the shipped v0.3
  quantities, dividing each quantity at precision 50 and adding gives a result
  that depends on the order of the basket and, for awkward rates, differs in
  the last digit from the exact sum rounded once (`...905565` against
  `...905566`). In 3000 random baskets the two differ in 1026, by at most 2
  units in the last place.
- **Inverse rates lose money-sized amounts.** 1,000,000 / 1.95583 =
  511291.88…; 1,000,000 × 0.511292 (the inverse to six significant figures) =
  511292.00, a difference of 0.12.
- **The caller's decimal context leaked into the bytes.** `localcontext()`
  copies the caller's context and the engine set only precision and rounding.
  With `capitals=0` a quantity printed as `6e+1` instead of `6E+1`, giving
  another `artifact_hash`; with `Inexact` trapped, a shipped vintage raised an
  exception.
- **`decimal.Decimal()` accepts more than a decimal literal**: `' 1.25'`,
  `'+1.25'`, `'1_000.5'`, `'1E+2'`, full-width and Arabic-Indic digits.
- **The bridged value depends on the bridge.** In the test fixture, the last
  market value 0.92453125 USD is 0.739625 W when restated through the declared
  rate of USD, EUR, JPY or INR, and 0.92453125 W through CNY or GBP.

## 2. The decisions in brief

| topic | decision |
|---|---|
| arithmetic of every new number | exact rationals on the verbatim strings; one rounding to 50 significant digits, ties to even; divide by the declared rate, never multiply by an inverse (§3.1) |
| decimal context | one fully specified context for every computation, old and new; no shipped byte changes (§3.1) |
| quotation | old units per ONE successor unit, kept verbatim; the other direction is not accepted and not inverted (§3.2) |
| declared numbers | plain decimal strings only (§3.2) |
| the event | a strict object, hypothetical scenarios only, fictional successor identifier that cannot look like a currency code (§3.3) |
| resolver | no new state: `unavailable`, reason `FX_LEG_FROZEN_AT_CHANGEOVER`, as rule 0, on and after the effective date; precedence over every per-series rule (§3.4) |
| `effective` | a civil date, inclusive, no time of day, no time zone (§3.4) |
| numeraire | three upper-case letters keep the old rules; anything else must be declared; a declared numeraire restates the published values and leaves the basket untouched; format `worldyard-artifact-3` (§3.5) |
| frozen record | `worldyard-frozen-record-1`; binds the source artifact, the event and the declared valuation date; `final_value` is the value of the unit after the event; the gap to the last market value is reported as information only (§3.6) |
| fresh start | refused: an event without rates is not a successor event (§3.7) |
| PPP leg | not frozen, not continued, not re-denominated (§3.8) |
| rate comparison | `worldyard-rate-comparison-1`; ratios only; USD anchor; never a conversion rate (§3.9) |
| registry | a frozen record would enter as a structured warning on its vintage; the shipped registry is unchanged (§3.10) |
| independent verifier | recomputes artifacts, frozen records and rate comparisons by its own route (§3.11) |
| external proofs of anchors | format decided, nothing built (§6) |

## 3. Specification and reasons

Notation: `Q(s)` is the exact rational value of the decimal string `s`.
`R50(x)` is the exact rational `x` rounded once to 50 significant digits, ties
to even.

### 3.1 Arithmetic

Every number introduced by this work is `R50` of an exact rational expression
over verbatim strings. Nothing is rounded on the way.

- The engine keeps numerators and denominators as integers
  (`Decimal.as_integer_ratio()`), reduces the final fraction `p/q`, and writes
  `str(Decimal(p) / Decimal(q))` under the fixed context below. The independent
  verifier uses `fractions.Fraction`. The two routes give identical strings
  (20,000 random fractions and 400 random baskets).
- An exact result below 1E+50 is written in its shortest form (`1281/1600`
  gives `0.800625`); a result that needed rounding has 50 digits, and so has
  an exact result of 1E+50 or more, which is written with a 50-digit
  coefficient and an exponent; values below 1E-6 use exponent notation, as
  elsewhere in the format (`5E-9`).
- Numbers read back from an artifact (`fixed_amount`, `value_usd`,
  `baseline_value_usd`) must be zero or satisfy 1E-200 ≤ x < 1E+201 to be used
  in exact arithmetic; otherwise `ValueError`.
- One decimal context for every computation of the engine and of the verifier:
  precision 50, `ROUND_HALF_EVEN`, `Emin=-999999`, `Emax=999999`, `capitals=1`,
  `clamp=0`, no flags, traps `InvalidOperation`, `DivisionByZero`, `Overflow`.
  Every field is given, so nothing is inherited from the caller. Under the
  default context this changes no byte of any shipped artifact.

| exact value | `R50` | note |
|---|---|---|
| 1281/1600 | `0.800625` | exact |
| (10^50+5)/10^50 | `1.0000000000000000000000000000000000000000000000000` | half-way, kept digit even: stays |
| (10^50+15)/10^50 | `1.0000000000000000000000000000000000000000000000002` | half-way, kept digit odd: up |
| (10^51+51)/10^51 | `1.0000000000000000000000000000000000000000000000001` | just above half-way |
| 2/3 | `0.66666666666666666666666666666666666666666666666667` | |
| -61/1000 | `-0.061` | a difference can be negative |

Why not round each term at precision 50 as the artifact builder does: the
result then depends on the order of operations (§1), so a second
implementation would have to copy a sequence of operations instead of a
definition. Why 50 significant digits and ties to even: it is the precision
and the tie rule of every other number in the format. Why no rounding to a
sub-unit: the successor has none in the scenario, and the euro rules keep
payment rounding (to the cent, half-way up) for "monetary amounts to be paid
or accounted for" while leaving "a higher degree of accuracy for intermediate
computations" untouched (Regulation 1103/97, Article 5 and recital 11). A
frozen value is a measurement, not a payment.

### 3.2 Quotation and declared numbers

`units_per_successor[code]` is the number of units of the old currency equal
to **one** unit of the successor: the direction of Worldyard's per-series
`fixed_conversion` (BGN 1.95583 = EUR 1) and of the euro's conversion rates,
"adopted as one euro expressed in terms of each of the national currencies"
(Regulation 1103/97, Article 4(1)). The string is kept verbatim and old-unit
amounts are divided by it. "Inverse rates derived from the conversion rates
shall not be used" (Article 4(3)); the library never forms one. A declaration
made in the other direction cannot be expressed in this version; it is neither
accepted nor inverted. An authority's own wording can be kept, verbatim, in
the event's optional `declaration` object.

A **declared number** (a rate of an event, `units_of_old_per_new`, a value of
a market or PPP table) must be a plain decimal string: 1 to 80 ASCII
characters from `0123456789.`, at most one `.`, a digit first and last, and a
value greater than zero. No sign, exponent, space or underscore, and no digits
of other scripts. The text is kept as given; no number of significant figures
is required.

### 3.3 The whole-basket successor event

```json
{
  "event": "whole_basket_successor",
  "id": "hypothetical-W-test-1",
  "scenario": "hypothetical",
  "successor": "W",
  "successor_kind": "fictional_scenario_identifier",
  "effective": "2100-01-01",
  "units_per_successor": {"USD": "1.25", "EUR": "1", "CNY": "10",
                          "JPY": "200", "GBP": "0.8", "INR": "100"}
}
```

- Required keys as shown; optional `declaration` (an object, free-form,
  hashed, never interpreted). Any other key is an error.
- `scenario` must be `"hypothetical"` and `successor_kind` must be
  `"fictional_scenario_identifier"`.
- `successor` is a *fictional identifier*: 1 to 16 ASCII letters and digits,
  at least one letter, and not exactly three letters. Every alphabetic code in
  the current ISO 4217 list is exactly three upper-case letters (§8), so such
  an identifier cannot be taken for one.
- `units_per_successor`: a non-empty object; no key equals the successor;
  every value is a declared number.
- `event_hash` is the SHA-256 of the canonical event (the encoding of
  `ARTIFACT_FORMAT.md` §2), so the order of keys does not matter and every
  rate, the date and the optional declaration are bound.
- Coverage is checked against a basket: the set of basket codes must equal
  the set of declared codes. A missing code and a code outside the basket are
  both errors. Partial succession stays under the per-series rule.
- Malformed input raises `ValueError`.

### 3.4 The resolver: rule 0, and what `effective` means

`resolve_input(target, series, max_age_days=0, rate_type=None,
changeover=None)`. With an event supplied and a target on or after its
`effective` date, every FX-leg input resolves to

```json
{"state": "unavailable", "value": null, "observation_date": null,
 "age_days": null, "rate_type": null, "flags": [],
 "reason": "FX_LEG_FROZEN_AT_CHANGEOVER"}
```

This is **rule 0**. It is applied after the resolver's own validation of its
arguments and before rule 1, and it takes precedence over a per-series
`fixed_conversion`, permanent holes, suspension, retirement and observations.
Before the date, and without an event, nothing changes. A malformed event is
an error even when the target is before the event.

There is no new state. A state that carried a value would have to be an
exchange rate between two old currencies derived from the declared rates,
which the euro precedent declines to define ("no inverse rates nor bilateral
rates between the currencies ... will be defined", Regulation 2866/98, recital
5). A state without a value is `unavailable` under another name. A reason code
keeps the documented contract, and `SPEC.md` already says that a basket with
an unavailable input produces no artifact.

The event is passed for FX-leg inputs only (an exchange rate of a basket
currency against the numeraire), not for population or PPP inputs (§3.8).

`effective` is a civil date `YYYY-MM-DD` in the proleptic Gregorian calendar,
like every date in the library, and it is inclusive: a target is before the
event if and only if it is earlier than `effective`. There is no time of day
and no time zone. The date is taken as written in the declaration (the euro's
rates took "effect at 0.00 on 1 January 1999 (local time)", §8), and an
observation belongs to the date its publisher gives it.

### 3.5 Numeraire: format `worldyard-artifact-3`

1. `numeraire` must be a string. Absent still means `"USD"`.
2. **Undeclared numeraire** (the spec has neither `numeraire_declaration` nor
   `numeraire_conversion`): it must be exactly three upper-case ASCII letters.
   Everything else is as in `worldyard-artifact-2`: same fields, same bytes,
   same hashes. The engine does not check that a three-letter code is an
   assigned currency code.
3. **Declared numeraire** (either key present; both are then required):
   - `numeraire_declaration`: exactly `{"code", "kind", "scenario"}` with
     `kind` = `"fictional_scenario_identifier"`, `scenario` =
     `"hypothetical"`, `code` a fictional identifier equal to `numeraire`.
   - `numeraire_conversion`: exactly `{"from", "units_of_old_per_new",
     "source_artifact_hash", "source_input_digest"}`. `from` is the old
     numeraire (three upper-case letters); `units_of_old_per_new` is a
     declared number, old-numeraire units per one unit of the new numeraire;
     the hashes are those of the source artifact.
   - The *source spec* is the spec without the two keys and with `numeraire`
     set to `from`. Its artifact is built by the undeclared rules; its
     `artifact_hash` and `input_digest` must equal the two hashes, otherwise
     the spec is rejected. A PPP-valued source spec is rejected (§3.8).
   - The artifact has `method`, `method_version`, `weight_vintage_label`,
     `weight_basis` and `basket` exactly as the source artifact; `numeraire`;
     the two objects copied from the spec; and

     ```
     baseline_value = R50( Q(source.baseline_value_usd) / Q(units_of_old_per_new) )
     value          = R50( Q(source.value_usd)          / Q(units_of_old_per_new) )
     ```

     It has no `baseline_value_usd` and no `value_usd`. `input_digest` is the
     hash of the declared spec; `artifact_hash` as always.
4. `redenominate(spec, artifact, declaration, units_of_old_per_new)` returns
   the declared spec for a source spec and its artifact. It refuses a spec
   that already has a declared numeraire, a spec without an explicit
   `numeraire`, a PPP-valued spec, a source whose values cannot be restated
   (negative or outside the supported range), and an artifact that does not
   reproduce from the spec. The input is not changed.

What this means: a declared numeraire **restates the published values and
nothing else**. The spec's rate fields stay in the old numeraire, under their
truthful names; the rows of the artifact (quantities and weights, which do not
depend on a numeraire) are identical; each value field is the published value
divided once by one declared rate. That is "re-denomination" in the sense of
the euro rules: "changing the unit in which the amount ... is stated" without
"altering any other term" (Regulation 974/98, Article 1). A spec that only
renames its numeraire, with or without the declaration, is rejected: without
the conversion its values would still be values in the old numeraire.

Because the source artifact is rebuilt and compared on every build, the basket
of a declared spec cannot be edited without changing the two hashes it
carries, and anyone can check from the declared spec alone that it restates
the source artifact whose hashes it carries. A successful verification shows
that the artifact restates the source artifact whose hashes the spec carries.
It does not show that this source is a particular published artifact: compare
`source_artifact_hash` with the published `artifact_hash`, obtained
elsewhere.

Compatibility: every `worldyard-artifact-2` spec and artifact whose numeraire
is three upper-case letters, or absent, is a `worldyard-artifact-3` spec and
artifact with the same bytes and hashes. That includes every shipped vintage.
A `-2` spec with any other numeraire value is no longer accepted; its artifact
still verifies with a `-2` verifier. A `-2` verifier reports a declared
artifact as a mismatch. Two limits remain and are stated plainly: an invented
three-letter code used without a declaration cannot be detected, and an
undeclared non-USD numeraire still gets value fields named `*_usd`.

### 3.6 The frozen record: `worldyard-frozen-record-1`

`freeze_fx_leg(spec, event, valuation_date)` returns:

| key | content |
|---|---|
| `format` | `"worldyard-frozen-record-1"` |
| `kind` | `"frozen_fx_leg"` |
| `state` | `"frozen_at_changeover"` |
| `flags` | sorted; always `FROZEN_AT_CHANGEOVER`; `NO_BRIDGE_RATE` when `comparison` is null |
| `scenario` | from the event |
| `notice` | the fixed text below |
| `event_id`, `event_hash` | the event's id; the hash of the whole event |
| `successor`, `successor_kind`, `effective` | from the event |
| `source_artifact_hash`, `source_input_digest` | of the artifact built from the spec |
| `declared_valuation_date` | the argument, verbatim |
| `last_fx_leg_value`, `last_fx_leg_numeraire` | the artifact's `value_usd`, verbatim, and its numeraire |
| `basket` | per basket entry, in basket order: `code`, `fixed_amount` (verbatim), `units_per_successor` (verbatim) |
| `final_value` | `R50( Σ Q(fixed_amount_i) / Q(units_per_successor_i) )` |
| `final_value_numeraire` | the successor |
| `comparison` | see below, or null |
| `record_hash` | SHA-256 of the canonical record without this key |

`comparison`, present when the source numeraire has a declared rate:

| key | content |
|---|---|
| `information_only` | `true` |
| `bridge_code`, `bridge_units_per_successor` | the source numeraire and its declared rate, verbatim |
| `last_fx_leg_value_bridged` | `R50( Q(last_fx_leg_value) / Q(bridge rate) )` |
| `final_minus_bridged` | `R50( Q(final_value) − Q(last_fx_leg_value_bridged) )` |

Notice (fixed, part of the format):

> Hypothetical scenario record: a thought experiment, not a forecast, a proposal or an offer of any currency. final_value is the pinned basket quantities divided by the declared rates; it does not show that the rates are authentic, right or fair. The comparison block is information only and depends on the bridge currency.

Rules and reasons:

- **The quantities** are the `fixed_amount` strings of the artifact built from
  the spec, verbatim: the published pinned quantities. They are not recomputed
  from unrounded weights. An artifact verifies only if it equals the build of
  its spec, so these are the strings of the published artifact.
- **The valuation date** is required and must be strictly before `effective`.
  It is a declaration by the caller: the engine reads no dates when it builds,
  so it can check the order of the two dates and nothing more. That the
  spec's valuation rates are the observations of that date is the publisher's
  statement in `SOURCES.md`, as for every vintage; that no later artifact
  exists is a registry matter (§3.10). Hence the name `declared_…`.
- **Refused** (`ValueError`): a spec with a declared numeraire (freeze its
  source spec); a PPP-valued spec; an event that does not cover exactly the
  basket codes; basket codes that are not strings; quantities outside the
  supported range.
- **Which value is the value of the unit after the event:** `final_value`. It
  is fixed by the pinned quantities and the declared rates alone and does not
  depend on the old numeraire or on any market rate.
- **The gap is reported, as information only.** `last_fx_leg_value_bridged`
  restates the last market value through the declared rate of the old
  numeraire only. It equals, byte for byte, the `value` of the same artifact
  re-denominated at that rate (§3.5). It depends on the bridge currency (§1),
  which is why it is information only. The two numbers differ when the
  declared rates are not proportional to the last market rates. In the euro
  changeover they could not differ: the conversion rates were the basket's
  last official market rates (Regulation 2866/98, recital 3). Without the
  block, a reader holding the re-denominated last artifact and the frozen
  record would see two values in the successor unit and no explanation.
- **What is bound:** the source artifact and, through its digest, the spec;
  the last FX-leg value; the event with every rate, the date and any
  `declaration`; the quantities and rates actually used; the declared
  valuation date. Binding a hash does not authenticate a declaration.

### 3.7 A fresh start

An event without rates is not a successor event and is refused. Worldyard
already has the truthful tool for a series that stops: `retired_since`
resolves to `unavailable` with `SOURCE_RETIRED`.

### 3.8 The PPP leg

A PPP-valued spec (recognised exactly as `SPEC.md` §2.3 describes) is refused
by `freeze_fx_leg`, by `redenominate` and by the declared-numeraire build. Its
value is in international dollars, not an amount of a converting currency, so
no declared conversion rate applies to it.

- PPP factors and populations are not FX-leg inputs; they are resolved without
  the event. A factor observed before the event stays usable with the old-unit
  quantities within its maximum age, then becomes `TOO_OLD`.
- A factor restated in the successor unit is not defined in this version. A
  factor is quoted in local units per international dollar, so carrying it
  back to old units would need a multiplication by the declared rate; the
  per-series `fixed_conversion` rule divides, which is right for a rate
  quoted in the numeraire per unit and wrong for the factor as published
  (measured: 0.4 successor units per international dollar at 10 old units
  per successor resolves to 0.04 instead of 4). Whether such series would
  exist is unknowable.
- The declared-rate value of a PPP vintage's *basket* can still be stated: the
  pinned quantities depend only on populations, multipliers and the baseline
  rates, so a nominal spec with the same baseline pins the same quantities
  (checked on v0.4), and that spec can be frozen.
- A PPP-valued spec that does not record its factors cannot be recognised.

### 3.9 Rate comparison: `worldyard-rate-comparison-1`

`rate_comparison(event, market, ppp)` compares; it does not grade.

- `market`: exactly `{"source", "date", "numeraire", "usd_per_unit"}`;
  `numeraire` must be `"USD"`, which must be a declared code of the event;
  `date` strictly before `effective`.
- `ppp`: exactly `{"source", "reference_year", "lcu_per_intl_usd"}`; 1 July of
  the reference year (the observation date `SPEC.md` gives annual series)
  strictly before `effective`.
- Table keys must be event codes; values are declared numbers; a `USD` entry
  must equal 1. A code missing from a table is not an error.
- The caller resolves every input under "Data states and fallbacks" first, as
  for `build_artifact`; an input that resolved `unavailable` is left out.

The record has `format`, `kind` = `"rate_comparison"`, `information_only` =
`true`, `scenario`, `notice`, `event_id`, `event_hash`, `successor`,
`successor_kind`, `effective`, `market` (source, date, numeraire), `ppp`
(source, reference year), `rows`, `record_hash`. One row per event code,
sorted by code:

| key | content |
|---|---|
| `declared_units_per_successor` | verbatim |
| `declared_implied_usd_per_unit` | `R50( Q(u_USD) / Q(u_code) )` |
| `market_usd_per_unit` | verbatim, or null |
| `declared_over_market` | `R50( Q(u_USD) / Q(u_code) / Q(market) )`, or null |
| `ppp_lcu_per_intl_usd` | verbatim, or null |
| `declared_over_ppp` | `R50( Q(u_USD) / Q(u_code) × Q(factor) )`, or null |
| `flags` | `NO_MARKET_RATE`, `NO_PPP_FACTOR` |

Notice (fixed, part of the format):

> Information only. Hypothetical scenario: a thought experiment, not a forecast, a proposal or an offer of any currency. declared_implied_usd_per_unit is a comparison quantity derived from two declared rates; it is not a conversion rate and must not be used to convert amounts. A PPP factor is not an exchange rate: no column shows a correct rate, or that a currency is over- or undervalued.

Reasons: USD is the numeraire of every rate field in the library, and the
field names say so. A ratio is one exact-friendly number; a percentage would
say the same. `declared_over_ppp` is the price level index (PPP divided by an
exchange rate) computed with the declared-implied rate instead of a market
rate; the notice says what it does not show. The implied column is never a
conversion rate: "Bilateral conversion rates between national currency units
are not defined and cannot be used" in the precedent (§8). No key uses audit,
fairness, score or grade vocabulary. The record is self-hashed and is not
anchored by the function.

The gap of the frozen record and this table are linked when the spec's
numeraire is USD and the market table holds the spec's valuation rates:
`final_value` divided by the bridged value equals the mean of
`declared_over_market` weighted by the valuation contributions (`fixed_amount`
× `fx_valuation_usd_per_unit`); exactly where no value involved was rounded,
to about 50 digits otherwise or with the published, rounded weights.

### 3.10 The registry

`data/vintages.json` is unchanged: no shipped vintage is frozen, and a
hypothetical entry on a real vintage would be a false statement about it.

If a real event were ever recorded, a frozen record would enter the registry
as a structured warning on its vintage's entry, which the append-only rule
already allows ("an existing entry may only gain `superseded_by` links and
warnings"):

```json
{"code": "FX_LEG_FROZEN_AT_CHANGEOVER", "detail": "...",
 "scenario": "...", "event_id": "...", "event_hash": "sha256:...",
 "effective": "YYYY-MM-DD", "record_hash": "sha256:...",
 "event_file": "data/<vintage>/...", "record_file": "data/<vintage>/..."}
```

The event and the record are new files in the vintage's directory; the
vintage's own files stay byte-identical; `status` keeps describing
supersession only. The consistency check (`test_vintages.py`, run on every
entry of the shipped registry) requires exactly these nine keys, each a
non-empty string; at most one such warning per event; both files directly
inside the vintage's directory and neither of them one of its own files; the
record's hash, scenario, event id, event hash and date equal to the
warning's; its `source_artifact_hash` equal to the entry's `artifact_hash`;
and the independent verifier reproducing the record. "The last artifact
before the event" is this registry statement, not something the engine can
know.

### 3.11 The independent verifier

`verify_independent.py` recomputes, without importing the engine: artifacts
under the numeraire rules, frozen records (`recompute_frozen_record`,
`compare_frozen_record`) and rate comparisons (`recompute_rate_comparison`,
`compare_rate_comparison`). A malformed spec or event is an error; anything
wrong with a published record is reported as a difference, field by field,
including a missing or extra key and a valuation date that is not before the
event. Because every number is defined as the rounding of an exact value, the
verifier can use a different route (`fractions`) and must still agree byte for
byte.

On the command line the artifact check always runs, and optional flags check
the two records: `--event E.json --frozen-record R.json`, and `--event E.json
--market M.json --ppp P.json --rate-comparison C.json`. The exit status is 0
iff every requested check passes, 1 if any field differs, 2 on an operational
error (including a flag without the flags it needs, a file in which an object
has a repeated key, and an input too malformed to compute with; such an input
ends with one ERROR line, not a traceback). Without flags the output is what
it always was.

Numbers in an event's free-form `declaration` are hashed as Python's `json`
module writes them, so they are best given as strings; NaN and the
infinities are not JSON, and an event that holds one is refused wherever it
is hashed.

For display only, the CLI (`build`, `show`), the demo and the verifier print
the unit of a declared-numeraire artifact as "W (fictional scenario
identifier, not a currency)".

## 4. Worked examples

All inputs are illustrative. Fixture: populations 100, 100, 350, 25, 25, 400;
pinned quantities USD 0.1, EUR 0.08, CNY 2.8, JPY 3.125, GBP 0.02, INR 32; the
last market value 0.92453125 USD; the event of §3.3.

1. **Frozen value.**
   0.1/1.25 + 0.08/1 + 2.8/10 + 3.125/200 + 0.02/0.8 + 32/100
   = 0.08 + 0.08 + 0.28 + 0.015625 + 0.025 + 0.32 = **0.800625 W**.
2. **Declared numeraire W at 1 W = 1.25 USD.** Baseline 1/1.25 = **0.8 W**;
   value 0.92453125/1.25 = **0.739625 W**; every row unchanged.
3. **The gap.** Bridged value 0.739625 W; `final_minus_bridged` = 0.061. The
   declared rates imply CNY = 1.25/10 = 0.125 USD (market 0.1) and GBP =
   1.25/0.8 = 1.5625 USD (market 1.25); the other four agree with the market.
4. **Rates that do not divide evenly** (the digits of the 1998 euro rates,
   used only as realistic six-figure numbers): USD 1.95583, EUR 0.787564, CNY
   6.55957, JPY 166.386, GBP 13.7603, INR 40.3399. The exact sum is
   324998693014926737430846021869425 / 233298442807885135774037893098282, and
   the record carries
   `1.3930598468784219051669093597680785533906689928212`.
5. **Rate comparison** for the fixture (market USD per unit: EUR 1.25, CNY
   0.1, JPY 0.00625, GBP 1.25, INR 0.0125; PPP factors EUR 0.8, CNY 4, JPY
   100, GBP 0.64, INR 25):

   | code | implied | over market | over PPP |
   |---|---|---|---|
   | CNY | 0.125 | 1.25 | 0.5 |
   | EUR | 1.25 | 1 | 1 |
   | GBP | 1.5625 | 1.25 | 1 |
   | INR | 0.0125 | 1 | 0.3125 |
   | JPY | 0.00625 | 1 | 0.625 |
   | USD | 1 | 1 | 1 |

## 5. Tests

`test_changeover.py` (standalone and pytest, like the other suites) pins the
behaviour with exact expected values, computed with fractions and compared as
strings or fractions, never as floats. It includes: the whole frozen record of
the fixture, key for key, with its hash; the six-figure-rate value against its
exact fraction; a case on the shipped v0.3 quantities where rounding term by
term gives another last digit; ties (half-way cases through the public
functions); the event validation matrix; the resolver on and around the date,
and its precedence over per-series rules; the declared-numeraire artifact with
its value readout and hashes, and the rejection of a relabelled spec; the
refusal of PPP-valued specs; every single-field edit of a record being
reported by the independent verifier; independence from the caller's decimal
context, and a caller's context left exactly as it was; the rate comparison rows, its ties, a case where a column computed
from an already rounded column would differ in the last digits, malformed
requests and tampered records; seeded random inputs checked three ways (the
engine, the independent verifier, and an integer-only rounding in the tests);
the registry rule on an entry built in the test; and the verifier's command
line through a subprocess, including files with a repeated key and inputs
that used to end in a traceback. The suite runs standalone, so `make verify` and the
CI step without pytest run it too.

## 6. Deferred

- **Anchoring with proofs that do not depend on one chain.** Nothing changes
  in `anchor.py`. Decided for a later step: the `external_proof` slot, which
  is outside the commitment, may hold one proof or a list of proofs, each with
  a `type` (`ots`, `txid`, `rfc3161`); because the slot is outside the
  commitment the record version does not change. `verify_anchor` keeps
  checking the commitment only, and the independent verifier does not check
  proofs: verifying one needs external trust roots and tools. Anchoring a
  frozen record or a rate comparison needs a typed subject in a new anchor
  version; until then a record file can be timestamped with an external tool
  exactly as an `artifact.json` can. No proof was produced.
- **A price-level leg** changes the methodology and would be a separately
  named index; successive PPP vintages are not an inflation index.
- **A fuller basket** is a policy and value choice (`SPEC.md` §8, §10).
- The other quotation direction; events and numeraires that are not
  hypothetical; a basket-level resolver; `worldyard` subcommands for the new
  records (the independent verifier has flags for them, §3.11); per-row
  converted amounts in the frozen record; a factor series restated in the
  successor unit (§3.8).
- Found on the way and left as it is: a legacy spec that carries a JSON number
  or `true` instead of a string is read differently by the engine and by the
  verifier (they then disagree, or the engine refuses the spec).

## 7. README wording (suggestion only; not applied)

> Hypothetical-scenario helpers (a whole-basket successor event, a frozen
> record, a declared numeraire, a rate comparison) are experimental. "W" in the
> examples and tests is a fictional scenario identifier. They are not forecasts
> or proposals, and Worldyard does not issue currency or tokens, accept
> deposits, settle or redeem anything, recommend financial decisions, or
> certify regulatory compliance. A rate comparison is information only; a PPP
> factor is not an exchange rate. Successful verification shows only that a
> record reproduces from its inputs, not that a declared rate is authentic,
> right or fair.

Avoid "audit", "fair rate", "proof of value", "guaranteed", "100%" and
"perfect" in names, badges and examples.

## 8. Sources (read 2026-11-17)

| source | what it supports |
|---|---|
| Council Regulation (EC) No 1103/97, <https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:31997R1103> (read in full) | Article 2(1): ECU to euro one to one. Article 4: rates as one euro in national units, six significant figures, never rounded or truncated, no inverse rates, conversion between national units through the euro. Article 5: rounding of amounts to be paid or accounted for. Recitals 6, 10, 11. |
| Council Regulation (EC) No 2866/98, <https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:31998R2866> (read in full) | The eleven rates ("1 euro = 40,3399 Belgian francs ..."); recital 3: the rates are the ECU's exchange rates of 31 December 1998; recital 5: no inverse or bilateral rates are defined. |
| Council Regulation (EC) No 974/98, <https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:31998R0974> (Articles 1, 3, 14 and recitals) | "Redenominate" changes the unit in which an amount is stated and no other term; the euro is substituted at the conversion rate. |
| European Commission, "Converting to the euro", <https://economy-finance.ec.europa.eu/euro/enlargement-euro-area/adoption-fixed-euro-conversion-rate/converting-euro_en> | Six significant figures; no rounding or truncating of the rate; bilateral rates are not defined and cannot be used. |
| ECB, "Determination of the euro conversion rates", 31 December 1998, <https://www.ecb.europa.eu/press/pr/date/1998/html/pr981231_2.en.html> | Effect "at 0.00 on 1 January 1999 (local time)"; the rates were the final official ECU exchange rates. |
| ECB, Bulgaria changeover, <https://www.ecb.europa.eu/euro/changeover/bulgaria/html/index.en.html> | "BGN 1.95583 = EUR 1"; joined on 1 January 2026. |
| ECB, daily euro reference rates, <https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml> (reference date 2026-11-16) | 29 currencies quoted against the euro. |
| World Bank, ICP FAQ, <https://www.worldbank.org/en/programs/icp/faq> | PPPs are not equilibrium exchange rates and cannot indicate a "correct" rate or an over- or undervalued currency; a price level index is the ratio of a PPP to a market exchange rate. |
| ISO 4217 list one, maintenance agency file dated 2026-09-17, <https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml> | 178 distinct alphabetic codes, each exactly three upper-case letters. |
| RFC 3161, <https://www.rfc-editor.org/rfc/rfc3161.txt> (abstract, introduction, token definition) | What a time-stamp token asserts; used only for the deferred anchoring item. |

Not verified: the IMF's SDR valuation rule could be read only through a
summarising tool (the page refused a direct download), and the text of the ISO
4217 standard itself was not available; no decision depends on either. The
behaviour of Python's `decimal` module was measured, not taken from its
documentation.

## 9. Distribution

Nothing in these notes is released. There is no `worldyard` project on PyPI,
and the PyPI project named `openunit` is an unrelated one (both checked on
2026-11-17). Any change of README wording, and any release or package
upload of this work, is a separate decision of the maintainer.
