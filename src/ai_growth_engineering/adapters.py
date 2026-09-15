"""Marketing adapters: one contract, one mapping specification per platform, one implementation.

An adapter turns a platform's own records into canonical funnel events and nothing more. It never
decides attribution, never guesses lineage, and never emits an event its mapping does not declare.
Stripe is the only implementation, because revenue is the event the Marketing Engineer could not
yet observe. The other five are specifications; each opens when real source data exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Protocol

from .funnel_events import EventError, record_event


@dataclass(frozen=True)
class Mapping:
    external_record: str
    canonical_event: str | None  # None: deliberately not mapped, and the reason is in `unsupported`
    identity_fields: str
    provenance: str
    idempotency_key: str
    value_semantics: str
    unsupported: str
    implemented: bool = False


@dataclass(frozen=True)
class PlatformSpec:
    platform: str
    status: str  # "reference_implemented" or "specified"
    mappings: tuple[Mapping, ...]


PER_DAY_AD_ROW = "one row per ad per day; quantity = the day's count; no buyer identity (aggregate)"
MAJOR_UNITS = "decimal in the ad account's currency, major units -> integer pence; account currency required"

SPECS: dict[str, PlatformSpec] = {spec.platform: spec for spec in (
    PlatformSpec("stripe", "reference_implemented", (
        Mapping("event payment_intent.succeeded", "payment_received",
                "payment_intent.metadata.company, else expanded customer.metadata.company; stripe customer id "
                "as person_id when no company; campaign_id / experiment_id / creative_id / arm only from "
                "payment_intent.metadata",
                "platform_export when livemode is true; synthetic_fixture in test mode",
                "stripe | payment_intent.id | payment_received (the Stripe event id is ignored, so a "
                "redelivered or re-sent event collapses to one payment)",
                "amount_received: integer minor units, already pence for two-decimal currencies; currency "
                "upper-cased",
                "zero- and three-decimal currencies refused; amount_received of 0 refused; payment and customer "
                "metadata naming different companies -> company left blank and flagged ambiguous; lineage is "
                "never read from email domains or customer names", implemented=True),
        Mapping("event charge.succeeded", None, "-", "-", "-", "-",
                "a second view of the same money as payment_intent.succeeded: mapping both double-counts revenue"),
        Mapping("event invoice.paid", None, "-", "-", "-", "-",
                "the invoice's payment intent already emits payment_intent.succeeded: mapping both double-counts"),
        Mapping("event charge.refunded (each refund object)", "refund", "as the original payment",
                "platform_export when livemode is true", "stripe | refund.id | refund",
                "refund.amount, integer minor units",
                "specified, not implemented: opens with the first real refund"),
        Mapping("event customer.subscription.created / .deleted", "recurring_revenue_started",
                "customer id, subscription.metadata lineage", "platform_export when livemode is true",
                "stripe | subscription.id | recurring_revenue_started (or _cancelled)",
                "plan amount x quantity per interval, minor units",
                "specified, not implemented: no recurring offer is sold yet; cancellation maps to "
                "recurring_revenue_cancelled"),
    )),
    PlatformSpec("meta_ads", "specified", (
        Mapping("Insights row, level=ad, time_increment=1: impressions", "impression",
                "campaign_id -> campaign_id, adset_id -> audience_id, ad_id -> creative_id", "platform_export",
                "meta_ads | ad_id | date_start | impression", PER_DAY_AD_ROW,
                "reach and frequency are window metrics, not additive across days: kept for creative "
                "intelligence, never events"),
        Mapping("Insights row: inline_link_clicks", "click", "as impressions", "platform_export",
                "meta_ads | ad_id | date_start | click", PER_DAY_AD_ROW,
                "`clicks` (all clicks) includes profile and reaction clicks: not mapped"),
        Mapping("Insights row: spend", "spend_recorded", "campaign_id, adset_id, ad_id", "platform_export",
                "meta_ads | ad_id | date_start | spend_recorded", MAJOR_UNITS,
                "a day with no row is unrecorded spend, never £0"),
        Mapping("Lead Ads form submission (leadgen webhook)", "lead_created",
                "leadgen_id, ad_id -> creative_id, company from the form's own field", "platform_export",
                "meta_ads | leadgen_id | lead_created", "no value",
                "form contact fields are personal data and stay out of the public repository"),
        Mapping("Insights row: actions[lead] / conversions", None, "-", "-", "-", "-",
                "platform-attributed and modelled counts with no buyer: the lead is observed from the form "
                "submission or the CRM, not the ad platform's tally"),
    )),
    PlatformSpec("google_ads", "specified", (
        Mapping("GAQL ad_group_ad by segments.date: metrics.impressions", "impression",
                "campaign.id -> campaign_id, ad_group.id -> audience_id, ad_group_ad.ad.id -> creative_id",
                "platform_export", "google_ads | customer_id | ad_id | segments.date | impression",
                PER_DAY_AD_ROW, "search impression share and top-of-page rates are not events"),
        Mapping("GAQL ad_group_ad by segments.date: metrics.clicks", "click", "as impressions", "platform_export",
                "google_ads | customer_id | ad_id | segments.date | click", PER_DAY_AD_ROW,
                "invalid clicks are already removed by the platform and are not recoverable"),
        Mapping("GAQL ad_group_ad by segments.date: metrics.cost_micros", "spend_recorded",
                "campaign.id, ad_group.id, ad id", "platform_export",
                "google_ads | customer_id | ad_id | segments.date | spend_recorded",
                "micros / 10,000 = pence for two-decimal currencies; customer.currency_code required",
                "a day with no row is unrecorded spend, never £0"),
        Mapping("metrics.conversions / conversions_value", None, "-", "-", "-", "-",
                "fractional, modelled and attribution-window dependent: not an observation of a buyer"),
        Mapping("click_view.gclid", None, "-", "-", "-", "-",
                "an identity key that joins a click to a GA4 or CRM lead; not an event by itself"),
    )),
    PlatformSpec("linkedin_ads", "specified", (
        Mapping("adAnalytics pivot=CREATIVE, timeGranularity=DAILY: impressions", "impression",
                "sponsoredCampaign URN -> campaign_id, sponsoredCreative URN -> creative_id", "platform_export",
                "linkedin_ads | creative URN | date | impression", PER_DAY_AD_ROW,
                "approximate member reach and frequency are not events"),
        Mapping("adAnalytics: landingPageClicks", "click", "as impressions", "platform_export",
                "linkedin_ads | creative URN | date | click", PER_DAY_AD_ROW,
                "`clicks` includes company-page and social clicks: not mapped"),
        Mapping("adAnalytics: costInLocalCurrency", "spend_recorded", "campaign and creative URNs", "platform_export",
                "linkedin_ads | creative URN | date | spend_recorded", MAJOR_UNITS,
                "a day with no row is unrecorded spend, never £0"),
        Mapping("Lead Gen Form response", "lead_created",
                "response id, creative URN -> creative_id, company from the form's own field", "platform_export",
                "linkedin_ads | response id | lead_created", "no value",
                "form contact fields are personal data and stay out of the public repository"),
        Mapping("adAnalytics: oneClickLeads / externalWebsiteConversions", None, "-", "-", "-", "-",
                "counts without a buyer, attributed by the platform: the form response is the observation"),
    )),
    PlatformSpec("ga4", "specified", (
        Mapping("BigQuery export event page_view on a registered landing page", "landing_page_view",
                "utm_campaign -> campaign_id, utm_content -> creative_id; user_pseudo_id kept as metadata",
                "platform_export", "ga4 | user_pseudo_id | event_timestamp | event_name", "quantity 1, no value",
                "pages that are not registered landing pages are not mapped"),
        Mapping("BigQuery export event generate_lead", "lead_created",
                "company or person id sent as an event parameter by ThePlus's own form; utm lineage as page_view",
                "platform_export", "ga4 | user_pseudo_id | event_timestamp | generate_lead", "no value",
                "user_pseudo_id alone is a device cookie, not a buyer: without a company or person id the lead is refused"),
        Mapping("Data API aggregated report", None, "-", "-", "-", "-",
                "sampled and thresholded aggregates: raw export events only"),
        Mapping("event purchase", None, "-", "-", "-", "-",
                "revenue arrives from Stripe; counting GA4 purchase as well double-counts it"),
    )),
    PlatformSpec("highlevel", "specified", (
        Mapping("webhook ContactCreate", "lead_created",
                "contact.id, companyName, attributionSource utmCampaign -> campaign_id, utmContent -> creative_id",
                "platform_export", "highlevel | contact.id | lead_created", "no value",
                "the raw contact is ingested, never HighLevel's own lead score or tags"),
        Mapping("webhook AppointmentCreate", "meeting_booked", "appointment id, contact id -> company via the contact",
                "platform_export", "highlevel | appointment.id | meeting_booked", "no value",
                "a cancelled or no-show appointment is not meeting_held"),
        Mapping("webhook OpportunityStatusUpdate status=won", "customer_won", "opportunity.id, contact company",
                "platform_export", "highlevel | opportunity.id | customer_won", "no value",
                "monetary value on the opportunity is a forecast, not revenue"),
        Mapping("webhook OpportunityStageUpdate", None, "-", "-", "-", "-",
                "stage names are the account's own interpretation: mapped only through an operator-declared "
                "stage map, and an unmapped stage is refused, never guessed"),
        Mapping("webhook InvoicePaid", None, "-", "-", "-", "-",
                "the same money arrives through Stripe; mapping both double-counts revenue"),
    )),
)}


class AdapterRejection(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ContractViolation(ValueError):
    """An adapter emitted an event its own mapping specification does not implement."""


class MarketingAdapter(Protocol):
    spec: PlatformSpec

    def map_record(self, record: dict) -> list[dict]:
        """Canonical event values for one external record, or raise AdapterRejection."""


def ingest(db_path: str, adapter: MarketingAdapter, records: Iterable[dict]) -> dict:
    """Run records through an adapter. A rejected record is reported with its reason, never silently
    dropped; an event outside the adapter's implemented mappings stops the run."""
    implemented = {m.canonical_event for m in adapter.spec.mappings if m.implemented and m.canonical_event}
    inserted = already_present = 0
    rejected: list[dict] = []
    for record in records:
        ref = str(record.get("id") or "") if isinstance(record, dict) else ""
        try:
            batch = adapter.map_record(record)
        except AdapterRejection as exc:
            rejected.append({"record": ref, "code": exc.code, "reason": str(exc)})
            continue
        for values in batch:
            if values.get("event_type") not in implemented:
                raise ContractViolation(f"{adapter.spec.platform} emitted {values.get('event_type')!r}, "
                                        f"which its specification does not implement")
            try:
                result = record_event(db_path, values)
            except EventError as exc:
                rejected.append({"record": ref, "code": exc.code, "reason": str(exc)})
                continue
            inserted += result["inserted"]
            already_present += not result["inserted"]
    return {"platform": adapter.spec.platform, "inserted": inserted, "already_present": already_present,
            "rejected": rejected}


# Currencies whose minor unit is not a hundredth: their amounts are not pence.
NON_TWO_DECIMAL = frozenset({
    "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga", "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof",
    "xpf", "bhd", "jod", "kwd", "omr", "tnd",
})
DUPLICATE_VIEWS = frozenset({"charge.succeeded", "invoice.paid"})
LINEAGE_KEYS = ("campaign_id", "experiment_id", "creative_id", "arm")


def _stripe_company(intent: dict) -> tuple[str, str]:
    own = str((intent.get("metadata") or {}).get("company") or "").strip()
    customer = intent.get("customer")
    theirs = str(((customer.get("metadata") or {}) if isinstance(customer, dict) else {}).get("company") or "").strip()
    if own and theirs and own.lower() != theirs.lower():
        return "", "ambiguous: payment and customer metadata name different companies"
    if own:
        return own, "payment_intent.metadata.company"
    if theirs:
        return theirs, "customer.metadata.company"
    return "", "unknown: no company in payment or customer metadata"


class StripeAdapter:
    spec = SPECS["stripe"]

    def map_record(self, record: dict) -> list[dict]:
        if not isinstance(record, dict) or record.get("object") != "event":
            raise AdapterRejection("not_a_stripe_event", "expected a Stripe event object")
        kind = record.get("type")
        if kind in DUPLICATE_VIEWS:
            raise AdapterRejection("duplicate_view", f"{kind} is the same money as payment_intent.succeeded")
        if kind != "payment_intent.succeeded":
            raise AdapterRejection("not_implemented", f"{kind} is not implemented in the reference adapter")
        intent = (record.get("data") or {}).get("object") or {}
        intent_id = str(intent.get("id") or "")
        if not intent_id.startswith("pi_"):
            raise AdapterRejection("payment_intent_missing", "the event carries no payment intent id")
        currency = str(intent.get("currency") or "").lower()
        if len(currency) != 3:
            raise AdapterRejection("currency_missing", f"{intent_id} has no ISO currency")
        if currency in NON_TWO_DECIMAL:
            raise AdapterRejection("currency_exponent_unsupported",
                                   f"{currency.upper()} amounts are not hundredths, so they are not pence")
        amount = intent.get("amount_received")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise AdapterRejection("amount_not_received", f"{intent_id} received no money")
        created = record.get("created")
        if isinstance(created, bool) or not isinstance(created, int):
            raise AdapterRejection("created_missing", f"{intent_id} has no event timestamp")
        customer = intent.get("customer")
        customer_id = str(customer.get("id") if isinstance(customer, dict) else customer or "")
        company, lineage = _stripe_company(intent)
        metadata = intent.get("metadata") or {}
        return [{
            "event_type": "payment_received",
            "occurred_at": datetime.fromtimestamp(created, timezone.utc).isoformat(timespec="seconds"),
            "source": "stripe", "source_record_id": intent_id,
            "company": company, "person_id": "" if company else customer_id,
            **{key: str(metadata.get(key) or "") for key in LINEAGE_KEYS},
            "value_pence": amount, "currency": currency.upper(),
            "provenance": "platform_export" if record.get("livemode") is True else "synthetic_fixture",
            "metadata": {"stripe_event_id": str(record.get("id") or ""), "stripe_customer": customer_id,
                         "livemode": record.get("livemode") is True, "company_lineage": lineage},
        }]


def render_specs(platform: str = "") -> str:
    lines = []
    for spec in SPECS.values():
        if platform and spec.platform != platform:
            continue
        lines.append(f"{spec.platform}  [{spec.status}]")
        for m in spec.mappings:
            lines.append(f"  {m.external_record}\n    -> {m.canonical_event or 'NOT MAPPED'}"
                         + ("  (implemented)" if m.implemented else ""))
            if m.canonical_event:
                lines += [f"    identity: {m.identity_fields}", f"    provenance: {m.provenance}",
                          f"    idempotency: {m.idempotency_key}", f"    value: {m.value_semantics}"]
            lines.append(f"    unsupported / ambiguous: {m.unsupported}")
    return "\n".join(lines)
