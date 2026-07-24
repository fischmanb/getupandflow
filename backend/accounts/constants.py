ROLE_ADMIN = "Admin"
ROLE_COACH = "Coach"
ROLE_CLIENT = "Client"

ROLE_NAMES = [ROLE_ADMIN, ROLE_COACH, ROLE_CLIENT]

# Bump when the Terms of Service / Privacy Policy substantively change so new
# signups record which version they accepted.
TERMS_VERSION = "2026-07-24"

# Company policy (Brian, 2026-07-24): clients are EST-only for now, so every
# coach works US Eastern hours by default regardless of where they live.
DEFAULT_WORKING_TIMEZONE = "America/New_York"
