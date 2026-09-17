"""Marketing procedures — approved skills as experimental inputs, judged against the ThePlus baseline.

    KNOWN (registered) -> DECLARED (frozen into an experiment before exposure) -> EVALUATED (on read)

The Intelligent Machine owns external-skill admission, provenance, permissions and approval. This
module consumes its approved-skill-export.v1 file and refuses anything that is not a current
approval; it never re-reviews one. Nothing here executes a procedure, sends, adopts or rewrites
anything: the output is a recommendation and a skill-evaluation-result.v1 file.

Registration is KNOWN, never PROVEN. Performance is derived on read from canonical funnel events,
and only a declared, concurrent, matured, sufficiently powered comparison inside one experiment
whose declared variable is `procedure` may be called causal.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

from . import registries
from .buyer_truth import buyer_evidence
from .change_diagnosis import CHANGE_POLICY, GROUP_OF, _input_changes, _resolve
from .funnel_events import effective_events
from .segments import ATTEMPTS, _rate, _units, load_registry
from .storage import connect, init_db

CONTRACTS = Path(__file__).parent / "contracts"
EXPORT_CONTRACT = "approved-skill-export.v1"
# v2 is the result this repository emits. v1 stays published byte-for-byte: a contract version never
# changes in place, and the Intelligent Machine still reads v1 files.
RESULT_CONTRACT = "skill-evaluation-result.v2"
RESULT_CONTRACT_VERSION = "2"
RESULT_CONTRACT_V1 = "skill-evaluation-result.v1"
# Result contracts this repository VALIDATES. A document's own `contract` selects its pinned schema;
# nothing is validated against "the latest", and anything else is unsupported.
READABLE_RESULT_CONTRACTS = (RESULT_CONTRACT_V1, RESULT_CONTRACT)
REVOCATION_CONTRACT = "skill-revocation.v1"
# The exact bytes of every contract shared with the Intelligent Machine (export and revocation originate
# there, results here). A schema whose bytes changed is not that version, and validates nothing.
SCHEMA_PINS = {
    EXPORT_CONTRACT: "f6665386e89fc55ae53e292a202bc91c6619f1358b7244c6e1e53b4e75659907",
    RESULT_CONTRACT_V1: "9880e22b3611ce24e9e1ac6422eda54c9ad3e794c83300dfe121a9b92e8dd4d4",
    RESULT_CONTRACT: "0ee7e90fe96168cadc024b4d5816985a05ebf3f2a799100ca5b7febc1fab4c28",
    REVOCATION_CONTRACT: "fe5a5ea92f2154b1fdf9fe263c9aeda68daa5fd513b15ab7456362390a155e8a",
}
# The ONE directory an approved export may be imported from: the Intelligent Machine's published exports,
# where its revocation notices are written. Anything else — including a copy under the same path shape — is
# a detached copy no revocation can reach. The default is the sibling checkout, the layout both
# repositories' pin tests already assume; set AGE_SKILL_EXPORTS_DIR when the exports live elsewhere.
EXPORTS_DIR_ENV = "AGE_SKILL_EXPORTS_DIR"
DEFAULT_EXPORTS_DIR = (Path(__file__).resolve().parents[3] / "theplus-intelligent-machine" / "agentic-os"
                       / "external-skills" / "contracts" / "exports")
ROLES = ("VARIABLE", "COMMON_INPUT")

# The marketing jobs a procedure may be approved for. An export must permit at least one of them,
# or marketing experimentation as a whole, to be consumed here.
USE_CASES = ("buyer_research", "icp_scoring", "message_generation", "content", "experiment_design",
             "experiment_analysis", "campaign_planning", "revenue_operations")
MARKETING_PERMISSION = "marketing_experimentation"
# What a procedure for a job legitimately changes between arms: its own output. Anything else that
# changed is a competing variable. Campaign planning shapes every input, so it has no free output.
OUTPUT_GROUPS = {"message_generation": {"CREATIVE"}, "content": {"CREATIVE"}, "icp_scoring": {"MIX", "AUDIENCE"},
                 "campaign_planning": set()}
# Jobs whose quality is not a funnel outcome. They are judged offline, and offline is never market evidence.
OFFLINE_METRICS = {
    "buyer_research": ("evidence_precision", "unsupported_claim_rate", "valid_source_rate", "duplicate_rate",
                       "qualified_account_precision"),
    "experiment_design": ("agreement_with_governed_decisions", "missed_guardrails"),
    "experiment_analysis": ("agreement_with_governed_decisions", "false_causal_claims",
                            "unsupported_recommendations", "missed_guardrails"),
    "revenue_operations": ("agreement_with_governed_decisions", "unsupported_recommendations"),
}
# Market metrics: outcomes per matured delivered exposure, counted by the segment unit model.
MARKET_METRICS = {"reply_rate": "replies", "qualified_reply_rate": "qualified_replies", "meeting_rate": "meetings",
                  "proposal_rate": "proposals", "paid_rate": "customers"}
METRIC_ALIASES = {"meaningful_reply_rate": "qualified_reply_rate", "positive_reply_rate": "qualified_reply_rate"}
# The only primary metrics whose controlled effect is itself a revenue outcome.
REVENUE_METRICS = frozenset({"paid_rate"})
# Revenue claims (enum in skill-evaluation-result.v1): NONE_OBSERVED — no customer or payment in the
# compared units; ASSOCIATED_ONLY — revenue sits beside the procedure; ATTRIBUTED — an attribution model
# assigned it, still not causation; CAUSAL_SUPPORTED — a controlled effect on a paid outcome.
ACTIVITY_METRICS = frozenset({"messages_generated", "posts_generated", "impressions", "raw_impressions",
                              "token_volume", "messages_sent", "outreach_sent"})
PROCEDURE_POLICY = {
    "z_threshold": 1.96,
    "power_z": 0.84,                    # 80% power
    # NO_DIFFERENCE only when a gap this size would have been visible; below that power, silence is
    # an underpowered test, not evidence the procedures perform alike.
    "max_detectable_difference": 0.10,
}
RESULT_CLASSES = ("CONTROLLED_EFFECT", "DESCRIPTIVE_DIFFERENCE", "CONFOUNDED", "INSUFFICIENT_SAMPLE", "IMMATURE",
                  "NO_DIFFERENCE", "REGRESSION", "NOT_EVALUABLE")
DECISIONS = {"CONTROLLED_EFFECT": "KEEP", "REGRESSION": "REJECT", "NO_DIFFERENCE": "REJECT",
             "DESCRIPTIVE_DIFFERENCE": "ITERATE", "CONFOUNDED": "ITERATE", "INSUFFICIENT_SAMPLE": "NEED_MORE_DATA",
             "IMMATURE": "NEED_MORE_DATA", "NOT_EVALUABLE": "NEED_MORE_DATA"}
NEXT_STEP = {
    "KEEP": "Return the result file to the Intelligent Machine for human promotion review. Nothing here adopts, "
            "runs or widens the procedure.",
    "REJECT": "Keep the baseline. An improved candidate is a new version with a new hash, evaluated offline and "
              "then in a new experiment.",
    "ITERATE": "Redesign as one experiment whose declared variable is procedure, with concurrent arms and nothing "
               "else changed.",
    "NEED_MORE_DATA": "Change nothing mid-test; re-run on the evidence named in the reason.",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
UNKNOWN_VALUES = {"", "unknown", "none", "null"}


class ProcedureError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _known(value) -> bool:
    return value is not None and str(value).strip().lower() not in UNKNOWN_VALUES


def load_schema(contract: str) -> dict:
    raw = (CONTRACTS / f"{contract}.schema.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SCHEMA_PINS[contract]:
        raise ProcedureError("schema_drift", f"{contract} schema is {digest[:16]}…, not its pinned "
                             f"{SCHEMA_PINS[contract][:16]}…; nothing validates against a changed contract")
    return json.loads(raw)


_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None),
          "integer": int, "number": (int, float)}


def validate_schema(doc, schema: dict, path: str = "$") -> list[str]:
    """The JSON-Schema subset both contracts use (required, type, enum, const, properties,
    additionalProperties, items) — the same subset the Intelligent Machine validates with."""
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(isinstance(doc, _TYPES[x]) and not (x in ("integer", "number") and isinstance(doc, bool))
                   for x in types if x in _TYPES):
            return [f"{path}: expected {t}, got {type(doc).__name__}"]
    errors = []
    if "const" in schema and doc != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and doc not in schema["enum"]:
        errors.append(f"{path}: must be one of {schema['enum']}")
    if isinstance(doc, dict):
        props = schema.get("properties", {})
        errors += [f"{path}.{key}: required" for key in schema.get("required", []) if key not in doc]
        for key, value in doc.items():
            if key in props:
                errors += validate_schema(value, props[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: not permitted")
    if isinstance(doc, list) and "items" in schema:
        for i, item in enumerate(doc):
            errors += validate_schema(item, schema["items"], f"{path}[{i}]")
    return errors


# --- registration ---------------------------------------------------------------------------

def export_refusal(doc, *, today: str | None = None) -> tuple[str, str] | None:
    """Why an approved-skill-export.v1 document may not be consumed, or None. Checked in the order a
    reviewer would ask: which contract, is it approved, is it still current, what exactly is it,
    where did it come from, and may marketing use it."""
    if not isinstance(doc, dict):
        return "malformed", "an export is a JSON object"
    if doc.get("contract") != EXPORT_CONTRACT or doc.get("contract_version") != "1":
        return ("unsupported_contract", f"contract {doc.get('contract')!r} version {doc.get('contract_version')!r} "
                f"is not supported; this repository reads {EXPORT_CONTRACT} version 1")
    if doc.get("admission_status") != "APPROVED":
        return ("not_approved", f"admission_status is {doc.get('admission_status')!r}; only an APPROVED export is "
                "consumed, and admission is decided by the Intelligent Machine, not here")
    revocation = doc.get("revocation") if isinstance(doc.get("revocation"), dict) else {}
    if revocation.get("revoked") or doc.get("effective_status") not in ("ADOPTED", "FORKED"):
        return ("revoked", f"effective_status is {doc.get('effective_status')!r}; a revoked, invalidated or "
                "unadopted skill has no usable export")
    if not HEX64.fullmatch(str(doc.get("content_hash") or "")):
        return ("hash_missing", "content_hash must be a sha256 hex digest; a name alone does not identify a procedure")
    source = doc.get("source") if isinstance(doc.get("source"), dict) else {}
    missing = [f"source.{f}" for f in ("source_type", "source_commit", "license") if not _known(source.get(f))]
    if not (_known(source.get("original_repository")) or _known(source.get("original_source_url"))):
        missing.append("source.original_repository|original_source_url")
    missing += [f for f in ("skill_id", "skill_version", "approved_by", "approved_at") if not _known(doc.get(f))]
    if missing:
        return "provenance_missing", f"required provenance missing: {', '.join(missing)}"
    uses = doc.get("approved_use_cases") if isinstance(doc.get("approved_use_cases"), list) else []
    if not set(uses) & (set(USE_CASES) | {MARKETING_PERMISSION}):
        return ("use_case_not_permitted", f"approved_use_cases {uses} do not permit marketing experimentation "
                f"({MARKETING_PERMISSION} or one of {', '.join(USE_CASES)})")
    review_after = str(doc.get("review_after") or "")
    if review_after and review_after[:10] < (today or date.today().isoformat()):
        return "review_expired", f"the approval was due for review on {review_after[:10]}; export a re-reviewed version"
    errors = validate_schema(doc, load_schema(EXPORT_CONTRACT))
    if errors:
        return "schema_invalid", "; ".join(errors)
    return None


def _register(db_path: str, record: dict) -> dict:
    init_db(db_path)
    ref = record["procedure_ref"]
    with connect(db_path) as con:
        row = con.execute("SELECT content_hash FROM procedures WHERE procedure_ref = ?", (ref,)).fetchone()
    if row is not None:
        if row["content_hash"] != record["content_hash"]:
            raise ProcedureError("content_changed_without_version",
                                 f"{ref} is registered with content {row['content_hash'][:12]}, not "
                                 f"{record['content_hash'][:12]}; changed content is a new version, never the same one")
        return {"procedure_ref": ref, "inserted": False, "evidence_status": "KNOWN"}
    registries.add(db_path, "procedures", record)
    return {"procedure_ref": ref, "inserted": True, "evidence_status": "KNOWN"}


def governed_export_path(skill_id: str) -> Path:
    """Where the Intelligent Machine publishes this skill's export and, later, its revocation notice. The
    directory is resolved; the file is not, so a symlink planted at this name does not count as it."""
    return Path(os.environ.get(EXPORTS_DIR_ENV) or DEFAULT_EXPORTS_DIR).resolve() / f"{skill_id}.json"


def import_export(db_path: str, path: str, *, today: str | None = None) -> dict:
    """Register one approved skill from its export file. Deterministic: the same file lands on the
    same row, and a re-import changes nothing."""
    raw = Path(path).read_bytes()
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProcedureError("malformed", f"{path} is not JSON: {exc}") from exc
    refusal = export_refusal(doc, today=today)
    if refusal:
        raise ProcedureError(*refusal)
    # ORIGIN enforcement (closes P2 MANAGED_EXPORT_ORIGIN_ENFORCEMENT). The Intelligent Machine writes its
    # revocation notice over exactly one file; only that file imports. A copy anywhere else — even under the
    # same …/contracts/exports/<skill_id>.json shape, or a symlink to one — never receives it and is refused.
    published = Path(path).resolve()
    governed = governed_export_path(doc["skill_id"])
    if published != governed:
        raise ProcedureError("not_the_published_export",
                             f"{path} is not the governed export {governed}; import the Intelligent Machine's "
                             f"published file itself (set {EXPORTS_DIR_ENV} if its exports live elsewhere) — a copy "
                             "never receives the revocation notice written over the original")
    source = doc["source"]
    return _register(db_path, {
        "procedure_ref": f"{doc['skill_id']}@{doc['skill_version']}",
        "procedure_id": doc["skill_id"], "procedure_version": doc["skill_version"], "content_hash": doc["content_hash"],
        "source_type": source["source_type"],
        "source_ref": f"{source.get('original_repository') or source.get('original_source_url')}@{source['source_commit']}",
        "source_commit": source["source_commit"], "license": source["license"],
        "admission_ref": f"{EXPORT_CONTRACT}:{doc['skill_id']}@{doc['skill_version']}:{doc['approved_at']}",
        "admission_status": "APPROVED", "effective_status": doc["effective_status"],
        "approved_use_cases": json.dumps(sorted(doc["approved_use_cases"])),
        "permissions_json": json.dumps(doc["permissions"], sort_keys=True),
        "evaluation_refs": json.dumps(doc["evaluation_refs"]),
        "approved_by": doc["approved_by"], "approved_at": str(doc["approved_at"]),
        "review_after": str(doc.get("review_after") or ""), "introduced_at": _utc_now(),
        "import_sha256": hashlib.sha256(raw).hexdigest(), "imported_from": str(published),
    })


def internal_record(skill_dir: str, use_cases: list[str]) -> dict:
    """A ThePlus skill as the baseline procedure: its identity is its declared version and the hash
    of its SKILL.md, so an edit without a version bump is refused at registration."""
    path = Path(skill_dir) / "SKILL.md"
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    name = re.search(r"^name:\s*(\S+)", text, re.M)
    version = re.search(r"^\s+version:\s*\"?([^\"\s]+)\"?", text, re.M)
    if not name or not version:
        raise ProcedureError("version_missing", f"{path} declares no name or metadata version")
    unknown = set(use_cases) - set(USE_CASES)
    if not use_cases or unknown:
        raise ProcedureError("use_case_not_permitted", f"use cases must be among {', '.join(USE_CASES)}")
    return {
        "procedure_ref": f"theplus.{name.group(1)}@{version.group(1)}", "procedure_id": f"theplus.{name.group(1)}",
        "procedure_version": version.group(1), "content_hash": hashlib.sha256(raw).hexdigest(),
        "source_type": "theplus_internal", "source_ref": f"skills/{path.parent.name}/SKILL.md",
        "admission_status": "INTERNAL_BASELINE", "effective_status": "BASELINE",
        "approved_use_cases": json.dumps(sorted(use_cases)),
        "admission_ref": "internal: a ThePlus procedure, not an external admission",
    }


def register_internal(db_path: str, skill_dir: str, use_cases: list[str]) -> dict:
    return _register(db_path, dict(internal_record(skill_dir, use_cases), introduced_at=_utc_now()))


def retire(db_path: str, procedure_ref: str, reason: str) -> dict:
    """Stop a procedure being declared into new experiments. Its past bindings and results stay."""
    if not reason.strip():
        raise ProcedureError("reason_required", "retiring a procedure needs the reason")
    init_db(db_path)
    with connect(db_path) as con:
        updated = con.execute("UPDATE procedures SET retired_at = ?, retired_reason = ? "
                              "WHERE procedure_ref = ? AND retired_at = ''", (_utc_now(), reason.strip(), procedure_ref))
        if updated.rowcount == 0:
            exists = con.execute("SELECT 1 FROM procedures WHERE procedure_ref = ?", (procedure_ref,)).fetchone()
            raise ProcedureError("already_retired" if exists else "not_registered", f"{procedure_ref}: nothing to retire")
    return {"procedure_ref": procedure_ref, "retired": True}


def procedure_rows(db_path: str) -> dict[str, dict]:
    init_db(db_path)
    rows = {}
    for row in registries.rows(db_path, "procedures"):
        rows[row["procedure_ref"]] = dict(row, approved_use_cases=json.loads(row["approved_use_cases"] or "[]"))
    return rows


def upstream_refusal(procedure: dict, *, today: str) -> tuple[str, str] | None:
    """Why an imported approval is no longer current, or None. An import is a snapshot: since then the
    Intelligent Machine may have revoked the skill, stopped exporting it, re-scoped it or let its
    review lapse. Checked before every NEW declaration, failing closed; declarations already made
    are history and are never re-judged, and the stored procedure is never refreshed from here."""
    if procedure["admission_status"] != "APPROVED":
        return None  # a ThePlus baseline has no upstream approval to lapse
    ref, stored_review = procedure["procedure_ref"], str(procedure["review_after"] or "")
    if stored_review and stored_review[:10] < today:
        return "review_expired", f"{ref}'s approval was due for review on {stored_review[:10]}; import a re-reviewed export"
    source = str(procedure["imported_from"] or "")
    governed = governed_export_path(procedure["procedure_id"])
    if source and Path(source).resolve() != governed:
        return ("untrusted_export_origin", f"{ref} was imported from {source}, not the governed export {governed}; "
                "only that file can carry a revocation, so no new declaration is made — re-import from it")
    path = Path(source)
    if not source or not path.is_file():
        return ("upstream_export_missing", f"{ref} was imported from {source or 'an unrecorded file'}, which no longer "
                "exists; the Intelligent Machine exports only current approvals, so a missing export is not one")
    try:
        doc = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        return "upstream_approval_not_current", f"{ref}: {source} can no longer be read as an export: {exc}"
    if isinstance(doc, dict) and doc.get("contract") == REVOCATION_CONTRACT:
        try:
            errors = validate_schema(doc, load_schema(REVOCATION_CONTRACT))
        except ProcedureError as exc:
            errors = [str(exc)]
        if errors:
            return ("upstream_approval_not_current", f"{ref}: {source} holds an invalid {REVOCATION_CONTRACT} notice "
                    f"({'; '.join(errors)}), which is not an approval")
        if (doc["skill_id"], doc["skill_version"], doc["content_hash"]) == (
                procedure["procedure_id"], procedure["procedure_version"], procedure["content_hash"]):
            return "upstream_revoked", f"{ref} was {doc['status']} by the Intelligent Machine: {doc['reason']}"
        return ("upstream_approval_not_current", f"{source} now holds a {doc['status']} notice for "
                f"{doc['skill_id']}@{doc['skill_version']}; nothing there approves {ref}")
    refusal = export_refusal(doc, today=today)
    if refusal:
        code = "review_expired" if refusal[0] == "review_expired" else "upstream_approval_not_current"
        return code, f"{ref}: the upstream export no longer passes import ({refusal[0]}: {refusal[1]})"
    if (doc["skill_id"], str(doc["skill_version"])) != (procedure["procedure_id"], procedure["procedure_version"]):
        return ("upstream_identity_changed", f"{source} now exports {doc['skill_id']}@{doc['skill_version']}, not {ref}; "
                "a new version is imported as its own procedure")
    if doc["content_hash"] != procedure["content_hash"]:
        return ("upstream_content_changed", f"{ref} was approved as {procedure['content_hash'][:12]}, but the upstream "
                f"export now carries {doc['content_hash'][:12]}; changed content is a new version")
    withdrawn = set(json.loads(procedure["approved_use_cases"] or "[]")) - set(doc["approved_use_cases"])
    if withdrawn:
        return "upstream_use_case_withdrawn", f"{ref} is no longer approved for {', '.join(sorted(withdrawn))}"
    return None


# --- declaration ----------------------------------------------------------------------------

def bind(db_path: str, experiment_id: str, procedure_ref: str, role: str, *, arm: str = "",
         frozen_by: str = "operator") -> dict:
    """Declare the exact procedure version an experiment runs, before its first exposure. The
    frozen contract itself is never rewritten; the declaration is its own append-only row."""
    init_db(db_path)
    arm = arm.strip()
    if role not in ROLES:
        raise ProcedureError("invalid_role", f"role must be one of {ROLES}")
    if (role == "VARIABLE") != bool(arm):
        raise ProcedureError("arm_rule", "a VARIABLE procedure belongs to exactly one arm; a COMMON_INPUT is held "
                             "constant across every arm and names none")
    with connect(db_path) as con:
        experiment = con.execute("SELECT variable FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone()
        procedure = con.execute("SELECT * FROM procedures WHERE procedure_ref = ?", (procedure_ref,)).fetchone()
        if experiment is None:
            raise ProcedureError("experiment_not_found", f"experiment {experiment_id} not found")
        if procedure is None:
            raise ProcedureError("not_registered", f"{procedure_ref} is not a registered procedure")
        if procedure["retired_at"]:
            raise ProcedureError("retired", f"{procedure_ref} was retired: {procedure['retired_reason']}")
        if role == "VARIABLE" and experiment["variable"] != "procedure":
            raise ProcedureError("variable_not_declared",
                                 f"{experiment_id} declares variable {experiment['variable'] or 'none'!r}; a procedure "
                                 "is the experimental variable only when the frozen contract says so — otherwise "
                                 "declare it as a COMMON_INPUT")
        existing = con.execute("SELECT * FROM experiment_procedures WHERE experiment_id = ? AND arm = ? "
                               "AND procedure_id = ?", (experiment_id, arm, procedure["procedure_id"])).fetchone()
        if existing is not None:
            if (existing["procedure_ref"], existing["content_hash"], existing["role"]) == (
                    procedure_ref, procedure["content_hash"], role):
                return {"experiment_id": experiment_id, "arm": arm, "procedure_ref": procedure_ref, "inserted": False}
            raise ProcedureError("frozen_binding",
                                 f"{experiment_id}{'/' + arm if arm else ''} already declares "
                                 f"{existing['procedure_ref']} ({existing['content_hash'][:12]}, {existing['role']}); a "
                                 "different version or hash is a new experimental condition — declare it in a new experiment")
        if con.execute("SELECT 1 FROM experiment_procedures WHERE experiment_id = ? AND procedure_id = ? AND role != ?",
                       (experiment_id, procedure["procedure_id"], role)).fetchone():
            raise ProcedureError("role_conflict", "a procedure cannot be both the variable and a constant input of one experiment")
    exposed = sorted(e["occurred_at"] for e in effective_events(db_path, include_synthetic=True)
                     if e["experiment_id"] == experiment_id and e["event_type"] in ATTEMPTS)
    if exposed:
        raise ProcedureError("exposure_started",
                             f"{experiment_id} has {len(exposed)} exposure event(s) since {exposed[0][:10]}; a procedure "
                             "declared after exposure never earns credit — declare it in a new experiment before its first send")
    lapsed = upstream_refusal(dict(procedure), today=_utc_now()[:10])
    if lapsed:
        raise ProcedureError(*lapsed)
    with connect(db_path) as con:
        con.execute("""INSERT INTO experiment_procedures(experiment_id, arm, procedure_id, procedure_ref,
                         procedure_version, content_hash, role, frozen_by, frozen_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (experiment_id, arm, procedure["procedure_id"], procedure_ref, procedure["procedure_version"],
                     procedure["content_hash"], role, frozen_by, _utc_now()))
    return {"experiment_id": experiment_id, "arm": arm, "procedure_ref": procedure_ref, "inserted": True}


def bindings(db_path: str) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        return [dict(r) for r in con.execute("SELECT * FROM experiment_procedures ORDER BY frozen_at, experiment_id, arm")]


def lineage(event: dict, declared: list[dict]) -> list[dict]:
    """The procedures an event ran under: only those its own experiment declared for its arm, or for
    every arm, on or before the day it happened. Being active at the same time links nothing."""
    return [b for b in declared if b["experiment_id"] == event["experiment_id"] and b["arm"] in ("", event["arm"])
            and event["occurred_at"][:10] >= b["frozen_at"][:10]]


# --- evaluation -----------------------------------------------------------------------------

def _side_procedure(declared: list[dict], procedures: dict, experiment_id: str, arm: str, use_case: str):
    if arm:
        found = [b for b in declared if b["experiment_id"] == experiment_id and b["arm"] == arm and b["role"] == "VARIABLE"]
    else:
        found = [b for b in declared if b["experiment_id"] == experiment_id and b["role"] == "COMMON_INPUT"
                 and use_case in procedures.get(b["procedure_ref"], {}).get("approved_use_cases", [])]
    if len(found) != 1:
        return None, ("no procedure was declared" if not found else f"{len(found)} procedures were declared")
    binding = found[0]
    return {**procedures[binding["procedure_ref"]], "binding": binding}, ""


def _where(experiment_id: str, arm: str) -> str:
    return f"{experiment_id}/{arm}" if arm else experiment_id


def evaluate(db_path: str, *, experiment_id: str, candidate_arm: str, baseline_arm: str, use_case: str,
             baseline_experiment_id: str = "", as_of: str | None = None) -> dict:
    """Did the candidate procedure outperform the baseline, under what evidence, and may it be called
    the cause? Deterministic, computed on read, and writes nothing."""
    from .marketing_engineer import linked_events

    init_db(db_path)
    as_of = (as_of or date.today().isoformat())[:10]
    baseline_experiment_id = baseline_experiment_id or experiment_id
    with connect(db_path) as con:
        experiments = {r["experiment_id"]: dict(r) for r in con.execute(
            "SELECT experiment_id, variable, primary_metric, minimum_sample FROM experiments WHERE experiment_id IN (?, ?)",
            (experiment_id, baseline_experiment_id))}
    procedures, declared = procedure_rows(db_path), bindings(db_path)
    r = {"as_of": as_of, "use_case": use_case, "experiment_id": experiment_id,
         "baseline_experiment_id": baseline_experiment_id, "candidate": {"arm": candidate_arm, "procedure": None},
         "baseline": {"arm": baseline_arm, "procedure": None}, "evidence_class": "OBSERVATIONAL_MARKET_RESULT",
         "primary_metric": None, "sample": {}, "maturity": {}, "metric": {}, "confounders": [],
         "competing_variables": [], "revenue": {},
         "money_graph": {}, "authority": "RECOMMENDATION_ONLY", "market_validation": False}

    def done(label: str, reason: str = "") -> dict:
        decision = DECISIONS[label]
        if decision == "KEEP":
            # The same non-compensatory gate as every other experiment: a controlled win earns
            # KEEP only under a resolved trust policy. The evidence class is unchanged; only the
            # decision is withheld — pending trust means wait, a breach means a person looks.
            from .registry import trust_verdict

            trust = trust_verdict(db_path, experiment_id)
            if not trust.passed:
                decision = "NEED_MORE_DATA" if trust.pending else "ITERATE"
                reason = "; ".join(filter(None, [reason, "trust gate not satisfied: " + ", ".join(trust.reasons)]))
        r.update(result_class=label, reason=reason, decision=decision,
                 market_validation=label == "CONTROLLED_EFFECT")
        r["next_step"] = NEXT_STEP[r["decision"]]
        r["unsupported_claims"] = _unsupported(r)
        return r

    for exp in {experiment_id, baseline_experiment_id} - set(experiments):
        return done("NOT_EVALUABLE", f"experiment {exp} not found")
    for side, exp, arm in (("candidate", experiment_id, candidate_arm), ("baseline", baseline_experiment_id, baseline_arm)):
        procedure, problem = _side_procedure(declared, procedures, exp, arm, use_case)
        if procedure is None:
            return done("NOT_EVALUABLE", f"{problem} for the {side} {_where(exp, arm)} before exposure; a procedure's "
                        "part in an outcome is never inferred from timing")
        if use_case not in procedure["approved_use_cases"]:
            return done("NOT_EVALUABLE", f"{procedure['procedure_ref']} is not approved for {use_case}")
        r[side]["procedure"] = procedure
    cand, base = r["candidate"]["procedure"], r["baseline"]["procedure"]
    if (cand["procedure_ref"], cand["content_hash"]) == (base["procedure_ref"], base["content_hash"]):
        return done("NOT_EVALUABLE", "the candidate and the baseline are the same procedure version")
    if (experiment_id == baseline_experiment_id and experiments[experiment_id]["variable"] == "procedure"
            and cand["binding"]["role"] == base["binding"]["role"] == "VARIABLE"):
        r["evidence_class"] = "CONTROLLED_MARKET_EXPERIMENT"
    controlled = r["evidence_class"] == "CONTROLLED_MARKET_EXPERIMENT"

    raw_metric = experiments[experiment_id]["primary_metric"]
    if raw_metric in ACTIVITY_METRICS:
        return done("NOT_EVALUABLE", f"{raw_metric} counts activity; more activity is not better growth")
    if use_case in OFFLINE_METRICS:
        return done("NOT_EVALUABLE", f"{use_case} is judged offline ({', '.join(OFFLINE_METRICS[use_case])}), and an "
                    "offline evaluation is never market or revenue evidence")
    metric = METRIC_ALIASES.get(raw_metric, raw_metric)
    if metric not in MARKET_METRICS:
        return done("NOT_EVALUABLE", f"the preregistered primary metric {raw_metric!r} is not a market outcome this "
                    f"evaluator measures ({', '.join(MARKET_METRICS)})")
    r["primary_metric"] = metric

    events = linked_events(db_path)
    registry = load_registry(db_path)
    creatives = {row["creative_id"]: row for row in registries.rows(db_path, "creatives")}
    exposures, by_unit, _ = _units(events)
    windows, spans = {}, {}
    for side, exp, arm in (("baseline", baseline_experiment_id, baseline_arm), ("candidate", experiment_id, candidate_arm)):
        windows[side] = _resolve(side, {"start": "0001-01-01", "end": as_of, "experiment_id": exp, "arm": arm}, events,
                                 exposures, by_unit, registry, creatives, buyer_evidence(db_path), as_of)
        spans[side] = sorted(first["occurred_at"][:10] for (_, e), first in exposures.items()
                             if e == exp and (not arm or first["arm"] == arm) and first["occurred_at"][:10] <= as_of)
        w = windows[side]
        r["sample"][side] = {"exposures": w["exposures"], "delivered": w["delivered"], "matured": w["matured"]}
        r["maturity"][side] = {"state": w["maturity"], "matures_between": w["matures_between"]}
        r["money_graph"][side] = w["campaigns"]
    for side, exp, arm in (("candidate", experiment_id, candidate_arm), ("baseline", baseline_experiment_id, baseline_arm)):
        if not windows[side]["exposures"]:
            synthetic = sum(1 for e in effective_events(db_path, include_synthetic=True)
                            if e["provenance"] == "synthetic_fixture" and e["experiment_id"] == exp
                            and (not arm or e["arm"] == arm) and e["event_type"] in ATTEMPTS)
            return done("NOT_EVALUABLE", f"the {side} {_where(exp, arm)} has no market exposure"
                        + (f"; its {synthetic} synthetic fixture exposure(s) never count as market evidence" if synthetic else ""))
        if not windows[side]["delivered"]:
            return done("NOT_EVALUABLE", f"the {side} {_where(exp, arm)} has no delivered exposure: every attempt "
                        "bounced or was undeliverable, so no rate has a denominator")
    immature = [s for s in ("candidate", "baseline") if not windows[s]["matured"]]
    if immature:
        return done("IMMATURE", "; ".join(
            f"no {s} exposure is past the {CHANGE_POLICY['response_window_days']}-day response window "
            f"(they mature {windows[s]['matures_between'][0]}..{windows[s]['matures_between'][-1]})" for s in immature))

    breaking, notes = [], []
    allowed = OUTPUT_GROUPS.get(use_case, set())
    # Campaign ids differ by construction, and so does the experiment id of an observational
    # comparison (disclosed below as observational); every other recorded input must match.
    inherent = {"campaign"} | (set() if controlled else {"experiment"})
    for dimension, change in _input_changes(windows["baseline"], windows["candidate"]).items():
        if change["changed"] and dimension not in inherent and GROUP_OF.get(dimension) not in allowed:
            breaking.append(f"{dimension} differs between the sides: {change['baseline']} vs {change['comparison']}")
    if not (spans["candidate"][0] <= spans["baseline"][-1] and spans["baseline"][0] <= spans["candidate"][-1]):
        breaking.append(f"the sides were not concurrent: baseline {spans['baseline'][0]}..{spans['baseline'][-1]}, "
                        f"candidate {spans['candidate'][0]}..{spans['candidate'][-1]}")
    for side in ("candidate", "baseline"):
        binding = r[side]["procedure"]["binding"]
        early = [d for d in spans[side] if d < binding["frozen_at"][:10]]
        if early:
            breaking.append(f"{len(early)} {side} exposure(s) predate the procedure's declaration on {binding['frozen_at'][:10]}")
        exp, arm = (experiment_id, candidate_arm) if side == "candidate" else (baseline_experiment_id, baseline_arm)
        recorded = {(e["metadata"] or {}).get("procedure_ref") for e in events
                    if e["experiment_id"] == exp and (not arm or e["arm"] == arm)} - {None, "", binding["procedure_ref"]}
        if recorded:
            breaking.append(f"{side} events record a competing procedure: {', '.join(sorted(recorded))}")
        if windows[side]["maturity"] == "PARTIALLY_MATURE":
            notes.append(f"{side}: {windows[side]['matured']} of {windows[side]['delivered']} delivered exposures have "
                         "matured; only those are in the denominator")
    if baseline_experiment_id != experiment_id:
        base_metric = experiments[baseline_experiment_id]["primary_metric"]
        if METRIC_ALIASES.get(base_metric, base_metric) != metric:
            breaking.append(f"the baseline experiment preregistered {base_metric}, not {raw_metric}")
    if not controlled:
        notes.append("observational: the procedure was not the declared variable of concurrent arms in one experiment")
    r["confounders"] = breaking + notes
    r["competing_variables"] = breaking

    counts = {side: windows[side]["cohort"]["counts"] for side in ("baseline", "candidate")}
    n_b, n_c = windows["baseline"]["matured"], windows["candidate"]["matured"]
    k_b, k_c = counts["baseline"][MARKET_METRICS[metric]], counts["candidate"][MARKET_METRICS[metric]]
    diff = k_c / n_c - k_b / n_b
    pooled = (k_b + k_c) / (n_b + n_c)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_b + 1 / n_c))
    z = diff / se if se else 0.0
    r["metric"] = {"baseline": _rate(k_b, n_b), "candidate": _rate(k_c, n_c), "delta": diff, "z": round(z, 2),
                   "minimum_detectable_difference": (PROCEDURE_POLICY["z_threshold"] + PROCEDURE_POLICY["power_z"]) * se if se else None}
    revenue = {side: {"customers": counts[side]["customers"], "observed_revenue_pence": counts[side]["observed_revenue_pence"]}
               for side in ("baseline", "candidate")}
    observed = any(v["customers"] or v["observed_revenue_pence"] for v in revenue.values())
    r["revenue"] = {**revenue, "class": "REVENUE_OUTCOME" if observed else None,
                    "claim": "NONE_OBSERVED" if not observed else "ASSOCIATED_ONLY"}

    if breaking:
        return done("CONFOUNDED", "; ".join(breaking))
    minimum = experiments[experiment_id]["minimum_sample"]
    if min(n_b, n_c) < CHANGE_POLICY["min_rate_denominator"] or n_b + n_c < minimum:
        return done("INSUFFICIENT_SAMPLE", f"matured delivered exposures: baseline {n_b}, candidate {n_c}; each side needs "
                    f"{CHANGE_POLICY['min_rate_denominator']} and the experiment preregistered {minimum}")
    if k_b + k_c == 0:
        return done("INSUFFICIENT_SAMPLE", f"no {MARKET_METRICS[metric].replace('_', ' ')} on either side; a difference "
                    "cannot be observed between two zeros")
    if abs(z) < PROCEDURE_POLICY["z_threshold"]:
        mdd = r["metric"]["minimum_detectable_difference"]
        if mdd > PROCEDURE_POLICY["max_detectable_difference"]:
            return done("INSUFFICIENT_SAMPLE", f"underpowered: at this sample only a gap of {mdd:.0%} or more would be "
                        f"visible, above the {PROCEDURE_POLICY['max_detectable_difference']:.0%} policy line")
        return done("NO_DIFFERENCE", f"no {metric} difference beyond z {PROCEDURE_POLICY['z_threshold']} at a sample "
                    f"able to see a {mdd:.0%} gap; the baseline is retained")
    if not controlled:
        return done("DESCRIPTIVE_DIFFERENCE", f"{metric} {'higher' if diff > 0 else 'lower'} for the candidate "
                    f"(z {z:.2f}), observed without a controlled design")
    if diff > 0 and r["revenue"]["claim"] == "ASSOCIATED_ONLY" and metric in REVENUE_METRICS:
        r["revenue"]["claim"] = "CAUSAL_SUPPORTED"
    return done("CONTROLLED_EFFECT" if diff > 0 else "REGRESSION",
                f"within {experiment_id}, whose declared variable is procedure, the candidate's {metric} was "
                f"{'higher' if diff > 0 else 'lower'} than the baseline's (z {z:.2f})")


def _unsupported(r: dict) -> list[str]:
    cand = (r["candidate"]["procedure"] or {}).get("procedure_ref", "the candidate procedure")
    claims = ["Registration or admission shows the procedure is effective.",
              "An offline evaluation shows market demand or revenue impact."]
    if r["result_class"] in ("CONTROLLED_EFFECT", "REGRESSION"):
        claims.append(f"{cand} has the same effect outside {r['experiment_id']} or on other buyers.")
    else:
        claims.append(f"{cand} caused any difference from the baseline.")
    if r["revenue"].get("claim") == "ASSOCIATED_ONLY":
        claims.append(f"{cand} caused the revenue observed alongside it.")
    return claims


def _pct(rate: dict) -> str:
    if not rate or rate.get("value") is None:
        return "not derivable (zero denominator)" if rate else "—"
    return f"{rate['numerator']}/{rate['denominator']} = {rate['value']:.1%}"


def render_report(r: dict) -> str:
    cand, base = r["candidate"]["procedure"] or {}, r["baseline"]["procedure"] or {}
    m, s = r["metric"], r["sample"]
    lines = ["PROCEDURE PERFORMANCE  [DERIVED from canonical funnel events · RECOMMENDATION ONLY · not causal unless CONTROLLED_EFFECT]",
             f"Procedure:          {cand.get('procedure_id', '—')}",
             f"Version:            {cand.get('procedure_version', '—')}",
             f"Hash:               {cand.get('content_hash', '—')}",
             f"Use case:           {r['use_case']}",
             f"Experiment:         {r['experiment_id']}" + (f" (baseline in {r['baseline_experiment_id']})"
                                                           if r["baseline_experiment_id"] != r["experiment_id"] else ""),
             f"Baseline:           {base.get('procedure_ref', '—')} [{r['baseline']['arm'] or 'all arms'}]",
             f"Candidate:          {cand.get('procedure_ref', '—')} [{r['candidate']['arm'] or 'all arms'}]",
             "",
             f"Evidence class:     {r['evidence_class']}",
             "Sample:             " + ("; ".join(f"{k} {v['delivered']} delivered, {v['matured']} matured" for k, v in s.items()) or "—"),
             "Maturity:           " + ("; ".join(f"{k} {v['state']}" for k, v in r["maturity"].items()) or "—"),
             "",
             f"Primary metric:     {r['primary_metric'] or '—'}",
             f"Baseline result:    {_pct(m.get('baseline'))}",
             f"Candidate result:   {_pct(m.get('candidate'))}"]
    if m:
        mdd = m["minimum_detectable_difference"]
        lines.append(f"Delta:              {m['delta']:+.1%} (z {m['z']}"
                     + (f"; smallest visible gap {mdd:.0%})" if mdd is not None else ")"))
    else:
        lines.append("Delta:              —")
    lines += ["", "Confounders:"] + [f"  - {c}" for c in r["confounders"] or ["none recorded"]]
    lines += ["Unsupported claims:"] + [f"  - {c}" for c in r["unsupported_claims"]]
    if r["revenue"]:
        lines.append(f"Revenue:            {r['revenue']['claim']} — candidate {r['revenue']['candidate']['customers']} "
                     f"customer(s), baseline {r['revenue']['baseline']['customers']}")
    for side, campaigns in r["money_graph"].items():
        for campaign in campaigns:
            lines.append(f"Money graph:        age marketing-engineer money-graph --campaign-id {campaign}  ({side})")
    lines += ["", f"Result:             {r['result_class']} — {r['reason']}",
              f"Decision:           {r['decision']}",
              f"Next step:          {r['next_step']}",
              "Authority:          RECOMMENDATION_ONLY — nothing here sends, adopts, rewrites or runs a procedure."]
    return "\n".join(lines)


# --- result contract ------------------------------------------------------------------------

def result_document(r: dict, *, generated_at: str | None = None) -> dict:
    cand, base = r["candidate"]["procedure"], r["baseline"]["procedure"]
    if cand is None or base is None:
        raise ProcedureError("no_procedure_identity", "nothing to return: the evaluation named no declared procedure")
    return {
        "contract_version": RESULT_CONTRACT_VERSION, "contract": RESULT_CONTRACT, "skill_id": cand["procedure_id"],
        "skill_version": cand["procedure_version"], "content_hash": cand["content_hash"],
        "evaluation_type": "MARKET_EVALUATION", "evidence_class": r["evidence_class"], "result_class": r["result_class"],
        "use_case": r["use_case"],
        "baseline": {"procedure_ref": base["procedure_ref"], "content_hash": base["content_hash"],
                     "source_ref": base["source_ref"]},
        "experiment_id": r["experiment_id"],
        "metrics": {"primary_metric": r["primary_metric"], **{k: v for k, v in r["metric"].items()}},
        "sample": r["sample"], "maturity": r["maturity"], "revenue": r["revenue"] or {"claim": "NONE_OBSERVED"},
        "confounders": r["confounders"], "competing_variables": r["competing_variables"],
        # The evaluator reads effective events, which exclude synthetic fixtures by construction.
        "includes_synthetic": False, "unsupported_claims": r["unsupported_claims"],
        "market_validation": r["market_validation"], "decision": r["decision"], "authority": "RECOMMENDATION_ONLY",
        "generated_at": generated_at or _utc_now(), "generated_by": "ai-growth-engineering",
    }


def validate_result(doc) -> list[str]:
    """The document's own contract selects its pinned schema, then the claims a result may not make
    whatever its fields say.

    v1 records neither competing variables nor synthetic exposure, and its revenue is an open object.
    Nothing absent is inferred: a v1 document can still carry a descriptive or offline result, but
    never a causal class, market validation or KEEP, because the evidence those need is not in it."""
    contract = doc.get("contract") if isinstance(doc, dict) else None
    if contract not in READABLE_RESULT_CONTRACTS:
        return [f"contract {contract!r} is not supported; this repository validates "
                f"{' and '.join(READABLE_RESULT_CONTRACTS)}"]
    try:
        errors = validate_schema(doc, load_schema(contract))
    except ProcedureError as exc:
        return [str(exc)]
    if errors:
        return errors
    v1 = contract == RESULT_CONTRACT_V1
    offline = doc["evaluation_type"] == "OFFLINE_EVAL"
    if offline != (doc["evidence_class"] == "OFFLINE_EVAL"):
        errors.append("evaluation_type and evidence_class disagree about whether this was offline")
    if not HEX64.fullmatch(doc["content_hash"]):
        errors.append("content_hash must be a sha256 hex digest")
    controlled = doc["evidence_class"] == "CONTROLLED_MARKET_EXPERIMENT"
    if doc["result_class"] in ("CONTROLLED_EFFECT", "REGRESSION"):
        if v1:
            errors.append(f"{doc['result_class']}: {RESULT_CONTRACT_V1} records neither competing variables nor "
                          f"synthetic exposure, so a causal class cannot be shown from it; publish {RESULT_CONTRACT}")
        else:
            errors += [f"{doc['result_class']}: {gap}" for gap in _controlled_evidence_gaps(doc)]
    claim = (doc.get("revenue") or {}).get("claim")  # v1's revenue is open: no claim is not NONE_OBSERVED
    if claim == "CAUSAL_SUPPORTED":
        if doc["result_class"] != "CONTROLLED_EFFECT":
            errors.append(f"revenue CAUSAL_SUPPORTED needs a CONTROLLED_EFFECT, not {doc['result_class']}")
        if doc["metrics"].get("primary_metric") not in REVENUE_METRICS:
            errors.append("revenue CAUSAL_SUPPORTED needs a paid outcome as the primary metric")
    if claim not in (None, "NONE_OBSERVED") and offline:
        errors.append(f"revenue {claim}: an offline evaluation observes no revenue")
    if doc["market_validation"]:
        if v1:
            errors.append(f"market_validation: {RESULT_CONTRACT_V1} does not record whether synthetic data was included")
        elif offline or doc["includes_synthetic"]:
            errors.append("market_validation: offline benchmarks and synthetic fixtures never validate the market")
        if not (controlled and doc["result_class"] == "CONTROLLED_EFFECT"):
            errors.append("market_validation needs a controlled market effect; offline or observational evidence never validates demand")
    if doc["decision"] == "KEEP" and not (controlled and doc["result_class"] == "CONTROLLED_EFFECT"):
        errors.append("KEEP needs a CONTROLLED_EFFECT from a controlled market experiment")
    return errors


def _controlled_evidence_gaps(doc: dict) -> list[str]:
    """The evaluator's own controlled-effect requirements, re-checked on the document itself, so a
    hand-edited or foreign result cannot carry a causal class the evidence in it does not support."""
    gaps = []
    if doc["evidence_class"] != "CONTROLLED_MARKET_EXPERIMENT":
        gaps.append("only a CONTROLLED_MARKET_EXPERIMENT can earn it")
    if not doc["experiment_id"]:
        gaps.append("needs the experiment id")
    base = doc["baseline"]
    if not (base.get("procedure_ref") and HEX64.fullmatch(str(base.get("content_hash") or ""))) \
            or base.get("content_hash") == doc["content_hash"]:
        gaps.append("needs exact, distinct candidate and baseline procedure identities")
    if doc["includes_synthetic"]:
        gaps.append("synthetic fixtures are not market exposure")
    if doc["competing_variables"]:
        gaps.append(f"unresolved competing variables: {'; '.join(doc['competing_variables'])}")
    minimum = CHANGE_POLICY["min_rate_denominator"]
    for side in ("baseline", "candidate"):
        sample = doc["sample"].get(side)
        matured = sample.get("matured") if isinstance(sample, dict) else None
        if not isinstance(matured, int) or isinstance(matured, bool) or matured < minimum:
            gaps.append(f"needs {minimum}+ matured {side} exposures in the sample")
        state = doc["maturity"].get(side)
        if not (isinstance(state, dict) and state.get("state") in ("MATURE", "PARTIALLY_MATURE")):
            gaps.append(f"needs matured {side} outcomes")
    metrics = doc["metrics"]
    z, delta = metrics.get("z"), metrics.get("delta")
    if metrics.get("primary_metric") not in MARKET_METRICS:
        gaps.append("needs a preregistered market outcome as the primary metric")
    if (not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (z, delta))
            or abs(z) < PROCEDURE_POLICY["z_threshold"] or (delta > 0) != (doc["result_class"] == "CONTROLLED_EFFECT")):
        gaps.append(f"needs a primary-metric difference beyond z {PROCEDURE_POLICY['z_threshold']} in its direction")
    return gaps
