import pytest
from pydantic import ValidationError
from main import ManagerMembershipCreate, get_roles

class TestIAMUnit:
    """[P0] Unit tests for IAM models and utilities"""

    def test_manager_membership_create_valid(self):
        """[P1] Should create valid Pydantic model with minimum and maximum length bounds"""
        m = ManagerMembershipCreate(manager_id="m1", member_id="u1")
        assert m.manager_id == "m1"
        assert m.member_id == "u1"
        
        # Max length boundary (255)
        long_id = "a" * 255
        m2 = ManagerMembershipCreate(manager_id=long_id, member_id=long_id)
        assert len(m2.manager_id) == 255

    def test_manager_membership_create_invalid_ids(self):
        """[P1] Should reject empty strings or oversized IDs"""
        with pytest.raises(ValidationError):
            ManagerMembershipCreate(manager_id="", member_id="u1")
        with pytest.raises(ValidationError):
            ManagerMembershipCreate(manager_id="m1", member_id="")
        with pytest.raises(ValidationError):
            ManagerMembershipCreate(manager_id="a" * 256, member_id="u1")

    def test_get_roles_admin_check(self):
        """[P0] Verify role extraction logic for Admin"""
        payload = {"realm_access": {"roles": ["Admin", "some_other_role"]}}
        roles = get_roles(payload)
        assert "Admin" in roles
        assert len(roles) == 2

    def test_get_roles_manager_check(self):
        """[P0] Verify role extraction logic for Manager"""
        payload = {"realm_access": {"roles": ["Manager"]}}
        roles = get_roles(payload)
        assert "Manager" in roles

    def test_get_roles_missing_realm_access(self):
        """[P2] Verify resilience when realm_access is missing"""
        assert get_roles({}) == []
