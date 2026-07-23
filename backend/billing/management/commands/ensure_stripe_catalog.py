"""Idempotently ensure the Stripe catalog and Customer Portal configuration.

Safe to run repeatedly: prices are matched by lookup_key, products by
metadata (or via an existing price), and the portal configuration id is
stored in the PortalConfiguration singleton. Nothing is ever duplicated.
"""

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from stripe import InvalidRequestError

from billing.views import sget
from billing.catalog import PLANS, STRIPE_INTERVALS, all_lookup_keys, price_lookup_key
from billing.models import PortalConfiguration

PRODUCT_METADATA_KEY = "guaf_plan"


class Command(BaseCommand):
    help = (
        "Ensure the Stripe Products, recurring Prices (by lookup_key) and the "
        "Customer Portal configuration exist. Idempotent; reuses existing objects."
    )

    def handle(self, *args, **options):
        if not settings.STRIPE_SECRET_KEY:
            raise CommandError("STRIPE_SECRET_KEY is not configured.")
        stripe.api_key = settings.STRIPE_SECRET_KEY

        existing_prices = {}
        price_list = stripe.Price.list(lookup_keys=all_lookup_keys(), limit=100)
        for price in price_list["data"]:
            existing_prices[price["lookup_key"]] = price

        products_by_plan = {}
        product_list = stripe.Product.list(active=True, limit=100)
        for product in product_list["data"]:
            plan = sget(sget(product, "metadata"), PRODUCT_METADATA_KEY)
            if plan in PLANS and plan not in products_by_plan:
                products_by_plan[plan] = product["id"]

        price_ids_by_product = {}
        for plan, spec in PLANS.items():
            product_id = products_by_plan.get(plan)
            if product_id is None:
                # Fall back to the product behind an existing price for this plan.
                for interval in STRIPE_INTERVALS:
                    price = existing_prices.get(price_lookup_key(plan, interval))
                    if price:
                        product_id = price["product"]
                        break
            if product_id is None:
                product = stripe.Product.create(
                    name=spec["name"], metadata={PRODUCT_METADATA_KEY: plan}
                )
                product_id = product["id"]
                self.stdout.write(f"Created product {spec['name']} ({product_id})")
            else:
                self.stdout.write(f"Reusing product for {spec['name']} ({product_id})")

            plan_price_ids = []
            for interval, amount in spec["amounts"].items():
                key = price_lookup_key(plan, interval)
                price = existing_prices.get(key)
                if price is None:
                    price = stripe.Price.create(
                        product=product_id,
                        currency="usd",
                        unit_amount=amount,
                        recurring={"interval": STRIPE_INTERVALS[interval]},
                        lookup_key=key,
                    )
                    self.stdout.write(f"Created price {key} ({price['id']})")
                else:
                    self.stdout.write(f"Reusing price {key} ({price['id']})")
                    if sget(price, "unit_amount") != amount:
                        self.stderr.write(
                            f"WARNING: price {key} has unit_amount "
                            f"{sget(price, 'unit_amount')}, expected {amount}. Stripe "
                            "prices are immutable; correct this manually if unintended."
                        )
                plan_price_ids.append(price["id"])
            price_ids_by_product[product_id] = plan_price_ids

        self._ensure_portal_configuration(price_ids_by_product)
        self.stdout.write(self.style.SUCCESS("Stripe catalog is in sync."))

    def _ensure_portal_configuration(self, price_ids_by_product):
        features = {
            "payment_method_update": {"enabled": True},
            "subscription_update": {
                "enabled": True,
                "default_allowed_updates": ["price"],
                "products": [
                    {"product": product_id, "prices": price_ids}
                    for product_id, price_ids in price_ids_by_product.items()
                ],
            },
            "subscription_cancel": {"enabled": True, "mode": "at_period_end"},
        }
        config = PortalConfiguration.load()
        if config.stripe_configuration_id:
            try:
                stripe.billing_portal.Configuration.modify(
                    config.stripe_configuration_id, features=features
                )
                self.stdout.write(
                    f"Updated portal configuration {config.stripe_configuration_id}"
                )
                return
            except InvalidRequestError:
                self.stderr.write(
                    "Stored portal configuration is missing in Stripe; creating a new one."
                )
        created = stripe.billing_portal.Configuration.create(
            business_profile={"headline": "Get Up and Flow"},
            features=features,
            default_return_url=f"{settings.APP_BASE_URL}/app",
        )
        config.stripe_configuration_id = created["id"]
        config.save()
        self.stdout.write(f"Created portal configuration {created['id']}")
