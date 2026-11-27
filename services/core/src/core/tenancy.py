"""Klant (tenant) bepalen uit het subdomein van de aanvraag."""

from __future__ import annotations

import re

SLUG_PATTERN = r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$"
# Subdomeinen die nooit een klant zijn.
RESERVED_SLUGS = frozenset(
    {"www", "api", "app", "admin", "auth", "login", "static", "assets", "mail", "status", "hub"}
)


def valid_slug(slug: str) -> bool:
    return (
        bool(re.fullmatch(SLUG_PATTERN, slug)) and "--" not in slug and slug not in RESERVED_SLUGS
    )


def slug_from_host(host: str | None, base_domain: str) -> str | None:
    """``acme.myworkhub.nl`` met basisdomein ``myworkhub.nl`` geeft ``acme``.

    Geeft ``None`` als de host geen subdomein van het basisdomein is (bijv. het
    basisdomein zelf, ``localhost`` of een IP-adres) of als het subdomein geen
    geldige klantnaam is.
    """
    if not host or not base_domain:
        return None
    hostname = host.strip().lower()
    if hostname.startswith("["):  # IPv6
        return None
    hostname = hostname.rsplit(":", 1)[0].rstrip(".")
    suffix = "." + base_domain.lower().strip(".")
    if not hostname.endswith(suffix):
        return None
    sub = hostname[: -len(suffix)]
    if "." in sub or not valid_slug(sub):
        return None
    return sub
