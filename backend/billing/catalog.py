"""Plan catalog for Stripe billing.

Amounts are in USD cents. Price lookup_keys (``<plan>_<interval>``) are the
single link between Stripe objects and app plans -- no Stripe ids are
hardcoded anywhere; the catalog is materialized in Stripe by the
``ensure_stripe_catalog`` management command.
"""

PLAN_FULL_SUPPORT = "full_support"
PLAN_FOCUS_LITE = "focus_lite"
PLAN_CHOICES = [
    (PLAN_FULL_SUPPORT, "Full Support"),
    (PLAN_FOCUS_LITE, "Focus Lite"),
]

INTERVAL_MONTHLY = "monthly"
INTERVAL_WEEKLY = "weekly"
INTERVAL_CHOICES = [
    (INTERVAL_MONTHLY, "Monthly"),
    (INTERVAL_WEEKLY, "Weekly"),
]

# Stripe recurring interval per app interval.
STRIPE_INTERVALS = {INTERVAL_MONTHLY: "month", INTERVAL_WEEKLY: "week"}

PLANS = {
    PLAN_FULL_SUPPORT: {
        "name": "Full Support",
        "amounts": {INTERVAL_MONTHLY: 75000, INTERVAL_WEEKLY: 22500},
        "featured": True,
        "badge": "Most popular",
        "tagline": "Your personal accountability partner \u2014 daily structure, coaching, and follow-through.",
        "highlights": [
            "Daily 1:1 planning with the same coach every day",
            "Panic-button support when things fall apart",
            "WhatsApp/text reminders during work hours",
        ],
        "value_note": "$4\u20136,000 value at 80% less than traditional coaching",
    },
    PLAN_FOCUS_LITE: {
        "name": "Focus Lite",
        "amounts": {INTERVAL_MONTHLY: 20000, INTERVAL_WEEKLY: 9500},
        "featured": False,
        "badge": None,
        "tagline": "A lighter starting point \u2014 weekly planning and gentle reminders.",
        "highlights": [],
        "value_note": None,
        "footnote": "Not ready for daily support? Start here \u2014 upgrade to Full Support anytime.",
    },
}


def price_lookup_key(plan, interval):
    # Brian's existing Stripe prices use display-style lookup keys, verbatim:
    # "Full Support - Monthly", "Full Support - Weekly",
    # "Focus Lite - Monthly", "Focus Lite - Weekly".
    return f"{PLANS[plan]['name']} - {interval.title()}"


def all_lookup_keys():
    return [price_lookup_key(plan, interval) for plan in PLANS for interval in STRIPE_INTERVALS]


def parse_lookup_key(key):
    """Return (plan, interval) for a known lookup key, else (None, None)."""
    for plan in PLANS:
        for interval in STRIPE_INTERVALS:
            if key == price_lookup_key(plan, interval):
                return plan, interval
    return None, None


def plan_catalog():
    """Plan catalog for the signup UI (amounts in whole dollars)."""
    return [
        {
            "id": plan,
            "name": spec["name"],
            "featured": spec.get("featured", False),
            "badge": spec.get("badge"),
            "tagline": spec.get("tagline"),
            "highlights": spec.get("highlights", []),
            "value_note": spec.get("value_note"),
            "footnote": spec.get("footnote"),
            "prices": {
                interval: {
                    "amount": spec["amounts"][interval] // 100,
                    "lookup_key": price_lookup_key(plan, interval),
                }
                for interval in STRIPE_INTERVALS
            },
        }
        for plan, spec in PLANS.items()
    ]
