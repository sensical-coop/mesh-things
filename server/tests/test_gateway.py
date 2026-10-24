"""The proxy's routing, and its agreement with what the app mounts."""
import re
from pathlib import Path

import pytest

from common.gateway import public_base_url

ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = ROOT / "Caddyfile"
READINGS_URLCONF = ROOT / "server/api/api_project/urls_readings.py"
REGISTRY_URLS = ROOT / "server/api/registry/urls.py"

def _caddyfile() -> str:
    return CADDYFILE.read_text()

def test_caddyfile_exists_where_this_test_expects_it():
    # If the file moves, the agreement checks below would silently pass on an
    # empty read - fail loudly instead.
    assert CADDYFILE.is_file(), f"Caddyfile not found at {CADDYFILE}"

def test_readings_are_routed_to_their_own_upstream():
    """The whole point of two roles: read traffic must not reach the process that owns the
    catalog and the keys."""
    assert re.search(r"handle /readings/\*\s*\{\s*reverse_proxy readings-api:8091", _caddyfile())

def test_everything_else_falls_through_to_the_registry_role():
    assert re.search(r"handle\s*\{\s*reverse_proxy registry-api:8090", _caddyfile())

def test_nothing_is_stripped_from_the_path():
    """`handle_path` would strip a prefix, which is what the app paths used to compensate for."""
    assert "handle_path" not in _caddyfile()

def test_the_readings_role_owns_exactly_the_segment_caddy_forwards():
    """Caddy routes on `/readings/`, so the readings urlconf has to mount that same segment -
    it is not stripped on the way in."""
    assert 'path("readings/"' in READINGS_URLCONF.read_text()

def test_no_registry_route_shadows_the_readings_segment():
    """A registry route starting with `readings` would be unreachable: Caddy sends anything
    under /readings/ to the other role."""
    segments = set(re.findall(r'path\("([^"/<]*)', REGISTRY_URLS.read_text()))

    assert "readings" not in segments

def test_public_base_url_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("GATEWAY__PUBLIC_URL", "https://api.example.com/")
    assert public_base_url() == "https://api.example.com"  # trailing slash stripped

def test_public_base_url_has_no_path_prefix():
    """Paths are served at the root now, so the schema's `servers` entry is a bare origin."""
    assert "/management" not in public_base_url()
    assert "/data" not in public_base_url()


@pytest.mark.parametrize("gone", ["/management", "/data"])
def test_the_old_prefixes_are_not_referenced_anywhere_in_the_proxy(gone):
    assert gone not in _caddyfile()
