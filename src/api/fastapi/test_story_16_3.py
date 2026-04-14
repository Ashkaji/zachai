import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi_test_app import client, ADMIN_PAYLOAD, MANAGER_PAYLOAD, MANAGER_OTHER_PAYLOAD
import main
from sqlalchemy import select
from main import ManagerMembership

@pytest.mark.asyncio
async def test_post_user_admin_success(mock_db):
    """Admin can create any user with any role."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    with patch("main.keycloak_admin.create_keycloak_user", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = "new-uuid"
        
        response = client.post("/v1/iam/users", json={
            "username": "test-user",
            "email": "test@example.com",
            "firstName": "Test",
            "lastName": "User",
            "role": "Manager"
        })
        
        assert response.status_code == 201
        assert response.json()["id"] == "new-uuid"
        mock_create.assert_called_once()
        # Admin doesn't create ManagerMembership entries (they are the root)
        mock_db.add.assert_not_called()

@pytest.mark.asyncio
async def test_post_user_manager_success(mock_db):
    """Manager can create a Transcripteur and it adds to their scope."""
    main.app.dependency_overrides[main.get_current_user] = lambda: MANAGER_PAYLOAD
    
    with patch("main.keycloak_admin.create_keycloak_user", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = "member-uuid"
        
        response = client.post("/v1/iam/users", json={
            "username": "team-member",
            "email": "team@example.com",
            "firstName": "Team",
            "lastName": "Member",
            "role": "Transcripteur"
        })
        
        assert response.status_code == 201
        assert response.json()["id"] == "member-uuid"
        
        # Verify ManagerMembership persistence
        mock_db.add.assert_called_once()
        membership = mock_db.add.call_args[0][0]
        assert isinstance(membership, ManagerMembership)
        assert membership.manager_id == MANAGER_PAYLOAD["sub"]
        assert membership.member_id == "member-uuid"

@pytest.mark.asyncio
async def test_post_user_manager_forbidden_escalation(mock_db):
    """Manager cannot create another Manager or Admin."""
    main.app.dependency_overrides[main.get_current_user] = lambda: MANAGER_PAYLOAD
    
    for forbidden_role in ["Admin", "Manager"]:
        response = client.post("/v1/iam/users", json={
            "username": "sneaky",
            "email": "sneaky@hack.com",
            "firstName": "Sneaky",
            "lastName": "User",
            "role": forbidden_role
        })
        assert response.status_code == 403
        assert "cannot create users with role" in response.json()["error"]

@pytest.mark.asyncio
async def test_patch_user_admin_success(mock_db):
    """Admin can disable any user."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    with patch("main.keycloak_admin.update_keycloak_user", new_callable=AsyncMock) as mock_update:
        response = client.patch("/v1/iam/users/any-uuid", json={"enabled": False})
        
        assert response.status_code == 204
        mock_update.assert_called_once_with("any-uuid", {"enabled": False})

@pytest.mark.asyncio
async def test_patch_user_manager_success(mock_db):
    """Manager can update a user in their scope."""
    main.app.dependency_overrides[main.get_current_user] = lambda: MANAGER_PAYLOAD
    
    # Mock: User is in manager's scope
    res = MagicMock()
    res.scalar_one_or_none.return_value = ManagerMembership(manager_id=MANAGER_PAYLOAD["sub"], member_id="member-uuid")
    mock_db.execute.return_value = res
    
    with patch("main.keycloak_admin.update_keycloak_user", new_callable=AsyncMock) as mock_update:
        response = client.patch("/v1/iam/users/member-uuid", json={"enabled": False})
        
        assert response.status_code == 204
        mock_update.assert_called_once_with("member-uuid", {"enabled": False})

@pytest.mark.asyncio
async def test_patch_user_manager_forbidden_outside_scope(mock_db):
    """Manager cannot update a user NOT in their scope."""
    main.app.dependency_overrides[main.get_current_user] = lambda: MANAGER_PAYLOAD
    
    # Mock: User is NOT in manager's scope
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = res
    
    response = client.patch("/v1/iam/users/stranger-uuid", json={"enabled": False})
    
    assert response.status_code == 403
    assert "outside your scope" in response.json()["error"]

@pytest.mark.asyncio
async def test_patch_user_not_found(mock_db):
    """PATCH returns 404 if user doesn't exist in Keycloak."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    from fastapi import HTTPException
    with patch("main.keycloak_admin.update_keycloak_user", new_callable=AsyncMock) as mock_update:
        mock_update.side_effect = HTTPException(status_code=404, detail={"error": "User not found"})
        
        response = client.patch("/v1/iam/users/missing-uuid", json={"enabled": True})
        
        assert response.status_code == 404
