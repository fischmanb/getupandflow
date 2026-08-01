"""triggers.yaml loader + schema validation — the SINGLE SOURCE OF TRUTH.

Ported verbatim (behaviour-for-behaviour) from the ratified reference
`aegis2/guaf/loader.py` so the production surface reads the SAME trigger ids,
tiers, confidence thresholds, SLA numbers, business-hour definition, and
cluster-upgrade rule the grading engine does. `escalations/triggers.yaml`
(ratified Brian Fischman + Bruce Parsons MD, 2026-08-01) is the only place any
of those numbers live; this module parses it ONCE (memoised per resolved path)
and hands the rest of the app a validated `TriggerSpec`. NOTHING here hardcodes
a threshold, an hour, or a rule — every such number is read off the object this
loader returns (brief: "SLA hours/rules read from one constants module
mirroring triggers.yaml; no heuristics or magic numbers").

Fail-closed (policy.fail_closed): an absent or invalid file raises
`TriggerSpecError`, which the ingest endpoint turns into a hard refusal — the
grader must not admit a transcript when the doctrine cannot be loaded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# The packaged spec — committed in this app, header carries its graph lineage.
DEFAULT_TRIGGERS_PATH = Path(__file__).resolve().parent / "triggers.yaml"

VALID_TIERS = frozenset({1, 2, 3})
VALID_DETECTIONS = frozenset({"single_utterance", "pattern"})

# Parse the numeric hours out of an SLA response string ("12h", "24h",
# "72h from trend-threshold crossing"). The number is the YAML's, never ours.
_HOURS = re.compile(r"(\d+)\s*h\b")
# Pull the IANA zone out of the business-hours definition prose so the timezone,
# too, is read from the YAML rather than hardcoded here.
_TZ = re.compile(r"\b([A-Za-z]+/[A-Za-z_]+)\b")
# Parse the cluster-upgrade rule prose into its three numbers: the minimum
# distinct count, the tier it fires ON, and the tier it escalates TO.
_CLUSTER = re.compile(
    r">=\s*(\d+)\s+distinct\s+tier-?\s*(\d+).*?escalate.*?as\s+tier\s+(\d+)",
    re.IGNORECASE | re.DOTALL,
)


class TriggerSpecError(ValueError):
    """triggers.yaml is absent, unparseable, or fails schema validation. The
    fail-closed signal (policy.fail_closed) — ingest must refuse the transcript
    when this is raised."""


@dataclass(frozen=True)
class Trigger:
    id: str
    tier: int                    # 1|2|3 — RATIFIED convention: 1 = most severe
    detection: str               # "single_utterance" | "pattern"
    confidence_threshold: float  # grader escalates at/above this
    evidence: str
    source: str = ""
    tier_basis: str = ""


@dataclass(frozen=True)
class SLA:
    hours: int
    clock: str                   # "calendar" | "business_hours"
    raw: str                     # the YAML response string, verbatim


@dataclass(frozen=True)
class ClusterUpgrade:
    min_distinct: int            # >= this many distinct flags...
    from_tier: int               # ...of this tier in one session...
    to_tier: int                 # ...escalate as this tier


@dataclass(frozen=True)
class Policy:
    grading_bias: str
    ungraded_session_is_a_finding: bool
    fail_closed: bool
    tier1_push: str
    business_hours_tz: str
    business_hours_definition: str
    slas: dict[int, SLA]         # tier -> SLA
    cluster_upgrade: ClusterUpgrade


@dataclass(frozen=True)
class TriggerSpec:
    version: int
    ratified_by: tuple[str, ...]
    ratified_at: str
    triggers: tuple[Trigger, ...]
    policy: Policy
    by_id: dict[str, Trigger]

    def triggers_for_tier(self, tier: int) -> tuple[Trigger, ...]:
        return tuple(t for t in self.triggers if t.tier == tier)

    def sla_for_tier(self, tier: int) -> SLA:
        return self.policy.slas[tier]


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise TriggerSpecError(msg)


def _parse_hours(raw: str, where: str) -> int:
    m = _HOURS.search(str(raw))
    _require(m is not None, f"{where}: no 'Nh' hours in response {raw!r}")
    return int(m.group(1))


def _parse_policy(pol: dict) -> Policy:
    _require(isinstance(pol, dict), "policy: must be a mapping")

    bh = pol.get("business_hours") or {}
    definition = str(bh.get("definition", ""))
    tzm = _TZ.search(definition)
    _require(tzm is not None,
             "policy.business_hours.definition: no IANA timezone (Area/Location) "
             f"found in {definition!r}")
    tz = tzm.group(1)

    raw_slas = pol.get("slas") or {}
    _require(isinstance(raw_slas, dict) and raw_slas, "policy.slas: missing")
    slas: dict[int, SLA] = {}
    for key, val in raw_slas.items():
        km = re.fullmatch(r"tier(\d+)", str(key))
        _require(km is not None, f"policy.slas: bad tier key {key!r}")
        tier = int(km.group(1))
        _require(tier in VALID_TIERS, f"policy.slas: tier {tier} out of {sorted(VALID_TIERS)}")
        _require(isinstance(val, dict), f"policy.slas.{key}: must be a mapping")
        raw = str(val.get("response", ""))
        clock = str(val.get("clock", ""))
        _require(clock in ("calendar", "business_hours"),
                 f"policy.slas.{key}.clock: {clock!r} not calendar|business_hours")
        slas[tier] = SLA(hours=_parse_hours(raw, f"policy.slas.{key}"),
                         clock=clock, raw=raw)
    for tier in VALID_TIERS:
        _require(tier in slas, f"policy.slas: no SLA for tier {tier}")

    cu = pol.get("cluster_upgrade") or {}
    rule = str(cu.get("rule", ""))
    cm = _CLUSTER.search(rule)
    _require(cm is not None,
             f"policy.cluster_upgrade.rule: unparseable {rule!r} — expected "
             "'>=N distinct tier-X ... escalate as tier Y'")
    cluster = ClusterUpgrade(min_distinct=int(cm.group(1)),
                             from_tier=int(cm.group(2)),
                             to_tier=int(cm.group(3)))
    _require(cluster.from_tier in VALID_TIERS and cluster.to_tier in VALID_TIERS,
             f"policy.cluster_upgrade.rule: tiers out of range in {rule!r}")

    return Policy(
        grading_bias=str(pol.get("grading_bias", "")),
        ungraded_session_is_a_finding=bool(pol.get("ungraded_session_is_a_finding", False)),
        fail_closed=bool(pol.get("fail_closed", False)),
        tier1_push=str(pol.get("tier1_push", "")),
        business_hours_tz=tz,
        business_hours_definition=definition,
        slas=slas,
        cluster_upgrade=cluster,
    )


def _parse_triggers(raw: object) -> tuple[Trigger, ...]:
    _require(isinstance(raw, list) and raw, "triggers: must be a non-empty list")
    out: list[Trigger] = []
    seen: set[str] = set()
    for i, t in enumerate(raw):
        where = f"triggers[{i}]"
        _require(isinstance(t, dict), f"{where}: must be a mapping")
        tid = t.get("id")
        _require(isinstance(tid, str) and tid, f"{where}: id missing")
        _require(tid not in seen, f"triggers: duplicate id {tid!r}")
        seen.add(tid)

        tier = t.get("tier")
        _require(tier in VALID_TIERS,
                 f"{where} ({tid}): tier {tier!r} not in {sorted(VALID_TIERS)}")

        detection = t.get("detection")
        _require(detection in VALID_DETECTIONS,
                 f"{where} ({tid}): detection {detection!r} not in "
                 f"{sorted(VALID_DETECTIONS)}")

        thr = t.get("confidence_threshold")
        _require(isinstance(thr, (int, float)) and 0.0 < float(thr) <= 1.0,
                 f"{where} ({tid}): confidence_threshold {thr!r} not in (0, 1]")

        out.append(Trigger(
            id=tid, tier=int(tier), detection=str(detection),
            confidence_threshold=float(thr),
            evidence=str(t.get("evidence", "")),
            source=str(t.get("source", "")),
            tier_basis=str(t.get("tier_basis", "")),
        ))
    return tuple(out)


def parse_spec(doc: object) -> TriggerSpec:
    """Validate an already-loaded YAML document into a TriggerSpec. Split from
    file IO so tests can drive validation on synthetic dicts without a file."""
    _require(isinstance(doc, dict), "triggers.yaml: top level must be a mapping")
    triggers = _parse_triggers(doc.get("triggers"))
    policy = _parse_policy(doc.get("policy") or {})
    ratified_by = tuple(str(x) for x in (doc.get("ratified_by") or ()))
    return TriggerSpec(
        version=int(doc.get("version", 0)),
        ratified_by=ratified_by,
        ratified_at=str(doc.get("ratified_at", "")),
        triggers=triggers,
        policy=policy,
        by_id={t.id: t for t in triggers},
    )


_CACHE: dict[str, TriggerSpec] = {}


def load_triggers(path: str | Path | None = None, *, reload: bool = False
                  ) -> TriggerSpec:
    """Load + validate triggers.yaml (default: the packaged spec). Memoised per
    resolved path; pass reload=True to force a re-read. Raises TriggerSpecError
    on an absent, unparseable, or schema-invalid file — the fail-closed signal.
    """
    p = Path(path) if path is not None else DEFAULT_TRIGGERS_PATH
    key = str(p.resolve()) if p.exists() else str(p)
    if not reload and key in _CACHE:
        return _CACHE[key]
    if not p.exists():
        raise TriggerSpecError(f"triggers.yaml absent at {p} — fail closed")
    try:
        doc = yaml.safe_load(p.read_text())
    except yaml.YAMLError as exc:
        raise TriggerSpecError(f"triggers.yaml at {p} is unparseable: {exc}") from exc
    spec = parse_spec(doc)
    _CACHE[key] = spec
    return spec
