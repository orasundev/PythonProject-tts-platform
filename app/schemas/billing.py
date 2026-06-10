from pydantic import BaseModel


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class BillingPortalResponse(BaseModel):
    portal_url: str


class PlanOut(BaseModel):
    name: str
    monthly_char_limit: int
    max_api_keys: int
    allows_ssml: bool
    allows_all_voices: bool
    allows_webhooks: bool
    allows_priority_queue: bool
    file_retention_days: int
    price_cents: int

    model_config = {"from_attributes": True}
