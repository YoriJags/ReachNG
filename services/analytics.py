"""
services/analytics.py - Central PostHog capture helper for ReachNG.
"""
from __future__ import annotations
from typing import Any


def track(event: str, distinct_id: str = "reachng-server", **properties: Any) -> None:
    try:
        from main import get_posthog
        ph = get_posthog()
        if ph:
            ph.capture(event, distinct_id=distinct_id, properties=properties)
    except Exception:
        pass


def track_page_viewed(page: str, path: str, referrer: str = "",
                      utm_source: str | None = None,
                      utm_medium: str | None = None,
                      utm_campaign: str | None = None,
                      **extra: Any) -> None:
    track("page_viewed", page=page, path=path, referrer=referrer,
          utm_source=utm_source, utm_medium=utm_medium,
          utm_campaign=utm_campaign, **extra)


def track_vertical_lander(vertical: str, path: str, referrer: str = "",
                           utm_source: str | None = None,
                           utm_campaign: str | None = None) -> None:
    track("vertical_lander_viewed", vertical=vertical, path=path,
          referrer=referrer, utm_source=utm_source, utm_campaign=utm_campaign)


def track_contact_submitted(vertical: str, has_message: bool) -> None:
    track("contact_form_submitted", vertical=vertical, has_message=has_message)


def track_signup_page(selected_plan: str, referrer: str = "",
                      utm_source: str | None = None,
                      utm_campaign: str | None = None) -> None:
    track("signup_page_viewed", selected_plan=selected_plan,
          referrer=referrer, utm_source=utm_source, utm_campaign=utm_campaign)


def track_signup_initiated(email: str, plan: str, plan_label: str,
                            vertical: str, amount_ngn: int,
                            annual: bool, reference: str) -> None:
    track("signup_initiated", distinct_id=email,
          plan=plan, plan_label=plan_label, vertical=vertical,
          amount_ngn=amount_ngn, annual=annual, reference=reference)


def track_payment_verified(email: str | None, reference: str,
                            plan: str | None, vertical: str | None,
                            amount_ngn: int | None, annual: bool | None,
                            portal_provisioned: bool,
                            state: str = "provisioned") -> None:
    track("signup_payment_verified",
          distinct_id=email or reference,
          plan=plan, vertical=vertical, amount_ngn=amount_ngn,
          annual=annual, reference=reference,
          portal_provisioned=portal_provisioned, state=state)


def track_client_provisioned(email: str | None, reference: str,
                              plan: str, vertical: str,
                              business_name: str, amount_ngn: int | None,
                              annual: bool | None) -> None:
    track("client_provisioned",
          distinct_id=email or reference,
          plan=plan, vertical=vertical,
          business_name=business_name,
          amount_ngn=amount_ngn, annual=annual,
          reference=reference, source="paystack_webhook")


def track_waitlist_joined(email: str | None, phone: str | None,
                           position: int, vertical: str,
                           city: str | None, source: str | None,
                           enquiry_volume: str | None,
                           avg_deal_value: str | None,
                           trust_ai_draft: str | None,
                           top_pains: list | None,
                           has_pain: bool,
                           has_sample_message: bool,
                           total_on_list: int) -> None:
    track("waitlist_joined",
          distinct_id=email or phone or "reachng-server",
          position=position, vertical=vertical, city=city,
          has_phone=bool(phone), has_email=bool(email),
          has_pain=has_pain, source=source,
          enquiry_volume=enquiry_volume,
          avg_deal_value=avg_deal_value,
          trust_ai_draft=trust_ai_draft,
          top_pains=top_pains or [],
          has_sample_message=has_sample_message,
          total_on_list=total_on_list)


def track_waitlist_invite_sent(position: int, total_on_list: int) -> None:
    track("waitlist_invite_sent", distinct_id="reachng-admin",
          position=position, total_on_list=total_on_list)
