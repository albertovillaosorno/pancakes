# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.semantic-module-usage-rules
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Normalize static hostnames for network-security validators.

Boundary contract:
- Owns: local parsing of ordinary IP literals and legacy numeric IPv4 aliases.
- Must not: resolve DNS, call networks, classify URLs, or produce findings.
- Allows: deterministic host-to-IP candidate expansion for static
  linter evidence.
- Split when: validators need DNS, proxy, or runtime transport semantics.
- Merge when: another validator reimplements this exact static host parser.
"""

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Final

IPV4_ADDRESS_BITS: Final = 32
IPV4_OCTET_BITS: Final = 8
IPV4_OCTET_MAX: Final = 255
IPV4_MAX_PART_COUNT: Final = 4
IPV4_TWO_COMPONENT_TAIL_MAX: Final = (
    1 << (IPV4_ADDRESS_BITS - IPV4_OCTET_BITS)
) - 1
IPV4_THREE_COMPONENT_TAIL_MAX: Final = (
    1 << (IPV4_ADDRESS_BITS - (IPV4_OCTET_BITS * 2))
) - 1
IPV4_PART_LIMITS_BY_COUNT: Final[tuple[tuple[int, ...], ...]] = (
    (),
    ((1 << IPV4_ADDRESS_BITS) - 1,),
    (IPV4_OCTET_MAX, IPV4_TWO_COMPONENT_TAIL_MAX),
    (IPV4_OCTET_MAX, IPV4_OCTET_MAX, IPV4_THREE_COMPONENT_TAIL_MAX),
    (IPV4_OCTET_MAX, IPV4_OCTET_MAX, IPV4_OCTET_MAX, IPV4_OCTET_MAX),
)


def host_ip_candidates(host: str) -> tuple[IPv4Address | IPv6Address, ...]:
    """Return normalized IP candidates for ordinary host text.

    Includes inet-atonic host aliases.
    """
    normalized = host.casefold().strip("[]").rstrip(".")
    try:
        parsed_ip = ip_address(normalized)
    except ValueError:
        legacy_ipv4 = _parse_inet_atonic_ipv4(normalized)
        if legacy_ipv4 is None:
            return ()
        return (legacy_ipv4,)
    return _candidate_host_ips(parsed_ip)


def _parse_inet_atonic_ipv4(host: str) -> IPv4Address | None:
    """Return an IPv4 address for legacy numeric host aliases when present."""
    parts = host.split(".")
    if not 1 <= len(parts) <= IPV4_MAX_PART_COUNT:
        return None
    parsed_numbers: list[int] = []
    for part in parts:
        number = _parse_inet_atonic_number(part)
        if number is None:
            return None
        parsed_numbers.append(number)
    numbers = tuple(parsed_numbers)
    limits = IPV4_PART_LIMITS_BY_COUNT[len(numbers)]
    if any(
        number < 0 or number > limit
        for number, limit in zip(numbers, limits, strict=True)
    ):
        return None
    address = numbers[-1]
    for index, number in enumerate(numbers[:-1]):
        shift = IPV4_OCTET_BITS * (IPV4_MAX_PART_COUNT - 1 - index)
        address |= number << shift
    return IPv4Address(address)


def _parse_inet_atonic_number(value: str) -> int | None:
    """Return one decimal, hexadecimal, or legacy octal host number."""
    if not value:
        return None
    try:
        if value.startswith("0x"):
            return int(value, 16)
        if len(value) > 1 and value.startswith("0"):
            return int(value, 8)
        return int(value, 10)
    except ValueError:
        return None


def _candidate_host_ips(
    parsed_ip: IPv4Address | IPv6Address,
) -> tuple[IPv4Address | IPv6Address, ...]:
    """Return normalized IP forms that should share private-network policy."""
    if isinstance(parsed_ip, IPv6Address) and parsed_ip.ipv4_mapped is not None:
        return (parsed_ip, parsed_ip.ipv4_mapped)
    return (parsed_ip,)
