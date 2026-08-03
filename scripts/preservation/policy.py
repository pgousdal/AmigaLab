"""Explicit licensing and export policy checks."""

LICENSE_PROFILES = frozenset({"redistributable", "local-only", "commercial", "personal-backup", "unknown"})
MEDIA_CLASSIFICATIONS = frozenset({"open-collection", "public-domain", "freeware", "shareware", "commercial", "licensed-distribution", "personal-backup", "unknown"})


def validate_license_profile(profile: str) -> str:
    if profile not in LICENSE_PROFILES:
        raise ValueError(f"unknown license profile: {profile}")
    return profile


def export_allowed(profile: str, explicit: bool = False) -> bool:
    validate_license_profile(profile)
    return profile == "redistributable" and explicit
