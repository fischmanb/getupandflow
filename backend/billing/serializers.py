from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .catalog import INTERVAL_CHOICES, PLAN_CHOICES, PLANS
from .models import Subscription

FLOW_PAYMENT_METHOD_UPDATE = "payment_method_update"
FLOW_SUBSCRIPTION_UPDATE = "subscription_update"
FLOW_SUBSCRIPTION_CANCEL = "subscription_cancel"
FLOW_CHOICES = [
    FLOW_PAYMENT_METHOD_UPDATE,
    FLOW_SUBSCRIPTION_UPDATE,
    FLOW_SUBSCRIPTION_CANCEL,
]


class CheckoutSerializer(serializers.Serializer):
    email = serializers.EmailField()
    # User.first_name/last_name cap at 150; keep the whole name under that.
    full_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)
    plan = serializers.ChoiceField(choices=PLAN_CHOICES)
    interval = serializers.ChoiceField(choices=INTERVAL_CHOICES)

    def validate_password(self, value):
        validate_password(value)
        return value


class PortalSerializer(serializers.Serializer):
    flow = serializers.ChoiceField(
        choices=FLOW_CHOICES, allow_null=True, required=False, default=None
    )


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "plan",
            "plan_name",
            "interval",
            "price_lookup_key",
            "status",
            "amount",
            "current_period_end",
            "cancel_at_period_end",
            "card_brand",
            "card_last4",
        ]

    def get_plan_name(self, obj) -> str:
        spec = PLANS.get(obj.plan)
        return spec["name"] if spec else obj.plan

    def get_amount(self, obj) -> int | None:
        """Price in whole dollars for the current plan/interval, if known."""
        spec = PLANS.get(obj.plan)
        if not spec or obj.interval not in spec["amounts"]:
            return None
        return spec["amounts"][obj.interval] // 100
