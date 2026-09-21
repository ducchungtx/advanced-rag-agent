"""Unit tests cho RBAC role → where."""

from app.services.auth.rbac import normalize_role, role_to_where


def test_citizen_only_public():
    assert role_to_where("citizen") == {"audience": {"$in": ["public"]}}


def test_staff_includes_internal():
    assert role_to_where("staff") == {
        "audience": {"$in": ["public", "internal"]},
    }


def test_unknown_role_defaults_citizen():
    assert normalize_role("hacker") == "citizen"
    assert role_to_where(None) == {"audience": {"$in": ["public"]}}
