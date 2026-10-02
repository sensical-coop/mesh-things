"""Which remote broker hosts a source may connect to.

EMQX makes the connection from inside this deployment, so a source pointing at
loopback, link-local or an internal service name would reach infrastructure that is
not meant to be reachable from outside (SSRF).
"""
import ipaddress
import socket

from django.conf import settings

# Names that always mean this machine, whatever DNS says.
_LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


def parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The address `host` spells, including legacy IPv4 forms such as `127.1` or `2130706433`."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    # inet_aton accepts the shorthand, decimal and hex forms other resolvers also honour.
    if all(c in "0123456789abcdefxABCDEFX." for c in host):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            return None
    return None


def _address_refusal(address) -> str | None:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.is_loopback or address.is_unspecified:
        return "A source cannot point at this machine."
    if address.is_link_local or address.is_multicast or address.is_reserved:
        return "A source cannot point at a link-local, multicast or reserved address."
    # Carrier-grade NAT (100.64.0.0/10) is not `is_private`, but is just as internal.
    shared = isinstance(address, ipaddress.IPv4Address) and address in ipaddress.ip_network("100.64.0.0/10")
    if (address.is_private or shared) and not settings.SOURCES_ALLOW_PRIVATE_BROKERS:
        return "A source cannot point at a private network address."
    return None


def resolve(host: str) -> list[str]:
    """Every address `host` resolves to, or none when it does not resolve right now."""
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
    except (OSError, UnicodeError):
        return []


def refusal(host: str) -> str | None:
    """Why a source may not connect to `host`, or None if it may."""
    name = host.strip("[]").rstrip(".").lower()
    address = parse_ip(name)
    if address is not None:
        return _address_refusal(address)
    if name in _LOCAL_NAMES or name.endswith(".localhost"):
        return "A source cannot point at this machine."
    # A name without a dot is a service on EMQX's own network, such as `emqx` or `kafka`.
    if "." not in name:
        return "A source needs a fully qualified broker hostname."
    # A public name can still resolve to an internal address. One that does not resolve
    # yet is accepted: the bridge then reports `disconnected` until it does.
    for resolved in resolve(name):
        reason = _address_refusal(ipaddress.ip_address(resolved.split("%")[0]))
        if reason is not None:
            return f"{name} resolves to {resolved}. {reason}"
    return None


def _normalised(host: str) -> str:
    return host.strip("[]").rstrip(".").lower()


def _addresses(name: str) -> set[str]:
    address = parse_ip(name)
    return {str(address)} if address is not None else set(resolve(name))


def is_own_broker(host: str, own_hosts) -> bool:
    """Whether `host` names one of `own_hosts`, by name or by any address they share.

    Comparing addresses also catches a raw IP, or another DNS name for the same broker.
    """
    name = _normalised(host)
    own = {_normalised(h) for h in own_hosts if h}
    if name in own:
        return True
    addresses = _addresses(name)
    return bool(addresses) and any(addresses & _addresses(h) for h in own)
