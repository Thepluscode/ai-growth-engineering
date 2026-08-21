"""Registries — where accumulated research becomes software memory rather than chat history.

Twelve structurally similar registries are declared as field lists rather than hand-written
modules. Together with the specialised customer-evidence and experiment registries, they
form the fourteen memories required by the Digital Marketing architecture. The schema is the
interface, and the repeated tables are generated from it.

Adding a registry means adding one entry here. Nothing else changes.
"""
from __future__ import annotations

from .storage import connect

# name -> (primary key field, required fields, optional fields)
REGISTRIES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "offers": (
        "offer_id",
        ("buyer", "problem", "outcome"),
        ("trigger", "price_pence", "margin_rate", "proof", "cta", "qualification_criteria"),
    ),
    "creatives": (
        "creative_id",
        ("buyer", "problem", "hook"),
        (
            "awareness", "angle", "format", "proof", "cta", "experiment_id",
            "spend_pence", "qualified_leads", "opportunities", "revenue_pence",
        ),
    ),
    "channels": (
        "channel_id",
        ("name",),
        ("kind", "status", "owner", "notes"),
    ),
    "proof": (
        "proof_id",
        ("claim", "evidence_id"),
        ("kind", "strength", "source_url", "usable_publicly"),
    ),
    "competitor_patterns": (
        "pattern_id",
        ("competitor", "pattern"),
        ("surface", "offer", "cta", "source_url", "confidence"),
    ),
    "claims": (
        "claim_id",
        ("statement", "evidence_id"),
        ("status", "approved_by", "reviewed_at"),
    ),
    "partners": (
        "partner_id",
        ("name",),
        ("kind", "terms", "attributed_revenue_pence", "status"),
    ),
    "attribution": (
        "attribution_id",
        ("source", "revenue_pence"),
        (
            "experiment_id", "channel_id", "creative_id", "content_id", "profile_id",
            "conversation_funnel_id", "audience_segment_id", "offer_id", "customer",
            "touchpoint_path", "recorded_at",
        ),
    ),
    "social_profiles": (
        "profile_id",
        ("platform", "audience", "positioning", "bio_promise", "primary_cta"),
        (
            "pinned_content", "proof_elements", "link_destination", "dm_path",
            "profile_visits", "link_clicks", "dm_starts", "qualified_leads",
            "customers", "revenue_pence", "experiment_id",
        ),
    ),
    "conversation_funnels": (
        "conversation_funnel_id",
        ("platform", "content_id", "primary_cta"),
        (
            "engagement_trigger", "dm_path", "qualification_criteria",
            "capture_destination", "offer_id", "content_views", "profile_visits",
            "dm_starts", "owned_contacts", "qualified_leads", "opportunities",
            "customers", "revenue_pence", "experiment_id",
        ),
    ),
    "audience_ownership": (
        "audience_segment_id",
        ("platform", "audience"),
        (
            "qualified_social_interactions", "owned_contacts", "capture_destination",
            "customers", "revenue_pence", "experiment_id",
        ),
    ),
    "voc": (
        "voc_id",
        ("source", "problem"),
        (
            "person", "audience", "trigger", "fear", "desired_outcome", "objection",
            "exact_language", "commercial_intent", "confidence", "evidence_id",
        ),
    ),
    "economics": (
        "economics_id",
        ("scope",),
        (
            "channel_id", "experiment_id", "period", "revenue_pence", "cogs_pence",
            "fulfilment_pence", "commissions_pence", "media_spend_pence",
            "delivery_cost_pence", "sales_cost_pence", "customers",
            "contribution_profit_pence", "cac_pence", "ltv_pence", "verdict",
        ),
    ),
    "angles": (
        "angle_id",
        ("audience", "problem", "current_belief", "contrarian_belief"),
        (
            "emotional_driver", "logical_driver", "mechanism", "proof", "hook",
            "offer_id", "cta", "experiment_id", "evidence_id", "integrity_status",
            "qualified_conversions", "opportunities", "revenue_pence",
        ),
    ),
    "belief_shifts": (
        "belief_shift_id",
        ("audience", "current_belief", "new_belief"),
        ("objection", "evidence_id", "action_that_follows", "angle_id"),
    ),
    "drivers": (
        "driver_id",
        ("audience", "kind", "driver"),
        ("evidence_id", "voc_id", "verbatim", "strength"),
    ),
    "scarcity_claims": (
        "scarcity_claim_id",
        ("statement", "verification"),
        ("capacity", "committed", "expiry", "status", "claim_id"),
    ),
    "value_ladders": (
        "value_ladder_id",
        ("buyer", "entry_offer_id", "core_offer_id"),
        (
            "premium_offer_id", "recurring_offer_id", "expansion_offer_id", "status", "notes",
        ),
    ),
}

# Architecture names -> physical tables. Evidence and experiments retain specialised
# validation interfaces; the other eight use the generic add/rows interface below.
REGISTRY_TABLES = {
    "customer_evidence": "evidence",
    "voc": "voc",
    "angles": "angles",
    "belief_shifts": "belief_shifts",
    "drivers": "drivers",
    "scarcity_claims": "scarcity_claims",
    "economics": "economics",
    "offers": "offers",
    "proof_inventory": "proof",
    "creatives": "creatives",
    "channels": "channels",
    "experiments": "experiments",
    "competitor_patterns": "competitor_patterns",
    "claims": "claims",
    "partners": "partners",
    "revenue_attribution": "attribution",
    "social_profile_surfaces": "social_profiles",
    "conversation_funnels": "conversation_funnels",
    "audience_ownership": "audience_ownership",
    "value_ladders": "value_ladders",
}

# Fields whose name ends in these suffixes are stored as integers, so money and counts
# cannot drift into floats one call site at a time.
INT_SUFFIXES = (
    "_pence", "_leads", "_visits", "_clicks", "_starts", "_views", "_contacts",
    "_interactions", "opportunities", "customers",
    # A scarcity capacity stored as text would compare as a string, so "10" < "2"
    # and a false limit could pass the gate that exists to catch it.
    "capacity", "committed", "_conversions",
)


def _column_type(field: str) -> str:
    if field.endswith(INT_SUFFIXES):
        return "INTEGER"
    if field.endswith("_rate") or field == "confidence":
        return "REAL"
    return "TEXT"


def _optional_column(field: str) -> str:
    kind = _column_type(field)
    if kind == "REAL":
        return kind
    default = "0" if kind == "INTEGER" else "''"
    return f"{kind} NOT NULL DEFAULT {default}"


def schema_sql() -> str:
    statements = []
    for table, (pk, required, optional) in REGISTRIES.items():
        columns = [f"{pk} TEXT PRIMARY KEY"]
        columns += [f"{f} {_column_type(f)} NOT NULL" for f in required]
        columns += [f"{f} {_optional_column(f)}" for f in optional]
        columns.append("created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        statements.append(
            f"CREATE TABLE IF NOT EXISTS {table} (\n    " + ",\n    ".join(columns) + "\n);"
        )
    return "\n\n".join(statements)


def migrate_columns(con) -> list[str]:
    """Add newly declared optional fields to existing generated registry tables."""
    added = []
    for table, (_, _, optional) in REGISTRIES.items():
        existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        for name in optional:
            if name not in existing:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {_optional_column(name)}")
                added.append(f"{table}.{name}")
    return added


def fields(registry: str) -> tuple[str, ...]:
    pk, required, optional = REGISTRIES[registry]
    return (pk,) + required + optional


def add(db_path: str, registry: str, record: dict) -> None:
    """Insert one record. Unknown fields and missing required fields are errors, not
    silent drops — a registry that quietly discards what it was given is worse than none."""
    if registry not in REGISTRIES:
        raise ValueError(f"unknown registry {registry!r}; known: {sorted(REGISTRIES)}")
    pk, required, _ = REGISTRIES[registry]
    allowed = set(fields(registry))
    unknown = set(record) - allowed
    if unknown:
        raise ValueError(f"{registry}: unknown fields {sorted(unknown)}")
    for name in (pk,) + required:
        if not str(record.get(name, "")).strip():
            raise ValueError(f"{registry}: {name} is required")
    columns = [f for f in fields(registry) if f in record]
    placeholders = ", ".join("?" for _ in columns)
    with connect(db_path) as con:
        con.execute(
            f"INSERT INTO {registry}({', '.join(columns)}) VALUES ({placeholders})",
            tuple(record[c] for c in columns),
        )


def rows(db_path: str, registry: str) -> list[dict]:
    if registry not in REGISTRIES:
        raise ValueError(f"unknown registry {registry!r}")
    with connect(db_path) as con:
        cur = con.execute(f"SELECT * FROM {registry} ORDER BY rowid")
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]
