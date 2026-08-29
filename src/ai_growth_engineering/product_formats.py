"""Choose the smallest delivery format justified by the problem's behaviour."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProductFormat(str, Enum):
    STATIC_ASSET = "static_asset"
    INTERACTIVE_TOOL = "interactive_tool"
    MANUAL_SERVICE = "manual_service"
    SOFTWARE = "software"
    SUBSCRIPTION_SOFTWARE = "subscription_software"


@dataclass(frozen=True)
class ProductFormatSignals:
    recurring_problem: bool = False
    new_data_changes_answer: bool = False
    saved_state_required: bool = False
    automation_improves_value: bool = False
    integration_increases_value: bool = False
    ongoing_value: bool = False


def choose_product_format(signals: ProductFormatSignals) -> ProductFormat:
    dynamic = sum((
        signals.new_data_changes_answer,
        signals.saved_state_required,
        signals.automation_improves_value,
        signals.integration_increases_value,
    ))
    if signals.recurring_problem and signals.ongoing_value and dynamic >= 3:
        return ProductFormat.SUBSCRIPTION_SOFTWARE
    if signals.recurring_problem and dynamic >= 3:
        return ProductFormat.SOFTWARE
    if (not signals.recurring_problem and signals.automation_improves_value
            and (signals.new_data_changes_answer or signals.saved_state_required)):
        return ProductFormat.INTERACTIVE_TOOL
    if signals.recurring_problem and signals.ongoing_value:
        return ProductFormat.MANUAL_SERVICE
    return ProductFormat.STATIC_ASSET
