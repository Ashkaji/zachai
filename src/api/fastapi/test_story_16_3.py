import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi_test_app import client, ADMIN_PAYLOAD, MANAGER_PAYLOAD, MANAGER_OTHER_PAYLOAD
import main

# --- Mocking Keycloak Admin Calls ---
# Since these routes will likely use keycloak_admin.py or similar, 
# we mock the underlying logic that talks to Keycloak.

@pytest.fixture
def mock_keycloak_admin():
    with patch("main.KeycloakAdmin", autospec=True) as mock:
        yield mock

@pytest.mark.asyncio
async def test_post_user_admin_success(mock_db):
    """[P1] Admin can create any user."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    with patch("main.create_keycloak_user", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {"id": "new-user-uuid", "username": "test-user"}
        
        response = client.post("/v1/iam/users", json={
            "username": "test-user",
            "email": "test@example.com",
            "role": "Transcripteur"
        })
        
        assert response.status_code == 201
        assert response.json()["id"] == "new-user-uuid"
        mock_create.assert_called_once()

@pytest.mark.asyncio
async def test_post_user_manager_success_with_perimeter(mock_db):
    """[P1] Manager can create a user (automatically added to their perimeter)."""
    # Manager payload sub="user-123"
    main.app.dependency_overrides[main.get_current_user] = lambda: MANAGER_PAYLOAD
    
    with patch("main.create_keycloak_user", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {"id": "new-user-uuid", "username": "team-member"}
        
        # Mock: Membership creation success
        mock_db.execute.return_value = MagicMock() 
        
        response = client.post("/v1/iam/users", json={
            "username": "team-member",
            "email": "team@example.com",
            "role": "Transcripteur"
        })
        
        assert response.status_code == 201
        # Verify that the user is now linked to this manager
        # (This will be implemented in the route logic)

@pytest.mark.asyncio
async def test_post_user_forbidden_role_escalation(mock_db):
    """[P0] Security: Manager cannot create an Admin."""
    main.app.dependency_overrides[main.get_current_user] = lambda: MANAGER_PAYLOAD
    
    response = client.post("/v1/iam/users", json={
        "username": "sneaky-admin",
        "email": "admin@hack.com",
        "role": "Admin"
    })
    
    assert response.status_code == 403
    assert "cannot assign Admin role" in response.json()["error"]

@pytest.mark.asyncio
async def test_put_user_status_admin(mock_db):
    """[P1] Admin can disable any user."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    with patch("main.update_keycloak_user_status", new_callable=AsyncMock) as mock_update:
        response = client.put("/v1/iam/users/some-uuid/status", json={"enabled": False})
        
        assert response.status_code == 200
        mock_update.assert_called_once_with("some-uuid", False)

@pytest.mark.asyncio
async def test_put_user_status_manager_own_perimeter(mock_db):
    """[P1] Manager can disable user in their own perimeter."""
    main.app.dependency_overrides[main.get_current_user] = lambda: MANAGER_PAYLOAD
    
    # Mock: User IS in manager's perimeter
    from main import ManagerMembership
    res = MagicMock()
    res.scalar_one_or_none.return_value = ManagerMembership(manager_id="user-123", member_id="member-uuid")
    mock_db.execute.return_value = res
    
    with patch("main.update_keycloak_user_status", new_callable=AsyncMock) as mock_update:
        response = client.put("/v1/iam/users/member-uuid/status", json={"enabled": False})
        
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_put_user_status_manager_forbidden_outside_perimeter(mock_db):
    """[P0] Security: Manager cannot disable user outside their perimeter."""
    main.app.dependency_overrides[main.get_current_user] = lambda: MANAGER_PAYLOAD
    
    # Mock: User IS NOT in manager's perimeter
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = res
    
    response = client.put("/v1/iam/users/stranger-uuid/status", json={"enabled": False})
    
    assert response.status_code == 403
    assert "outside your perimeter" in response.json()["error"]

@pytest.mark.asyncio
async def test_put_user_roles_admin_only(mock_db):
    """[P1] Only Admin can update roles."""
    main.app.dependency_overrides[main.get_current_user] = lambda: MANAGER_PAYLOAD
    
    response = client.put("/v1/iam/users/some-uuid/roles", json={"role": "Expert"})
    
    assert response.status_code == 403
    assert "Admin role required" in response.json()["error"]
