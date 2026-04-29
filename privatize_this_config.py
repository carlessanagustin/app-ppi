"""Configuration constants for PII/PHI/PCI detection and anonymization."""

from typing import Literal, get_args

ModelName = Literal[
    "nvidia/gliner-PII",
    "urchade/gliner_multi_pii-v1",
    "knowledgator/gliner-pii-base-v1.0",
    "gretelai/gretel-gliner-bi-large-v1.0",
]

SUPPORTED_MODELS: list[str] = list(get_args(ModelName))

DEFAULT_MODEL = "nvidia/gliner-PII"
DEFAULT_THRESHOLD = 0.7
PII_LABELS = [
    "medical_record_number",
    "date_of_birth",
    "ssn",
    "date",
    "first_name",
    "email",
    "last_name",
    "customer_id",
    "employee_id",
    "name",
    "street_address",
    "phone_number",
    "ipv4",
    "credit_card_number",
    "license_plate",
    "address",
    "user_name",
    "device_identifier",
    "bank_routing_number",
    "date_time",
    "company_name",
    "unique_identifier",
    "biometric_identifier",
    "account_number",
    "city",
    "certificate_license_number",
    "time",
    "postcode",
    "vehicle_identifier",
    "coordinate",
    "country",
    "api_key",
    "ipv6",
    "password",
    "health_plan_beneficiary_number",
    "national_id",
    "tax_id",
    "url",
    "state",
    "swift_bic",
    "cvv",
    "pin",
]
