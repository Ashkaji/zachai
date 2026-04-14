import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone
from fastapi_test_app import client, ADMIN_PAYLOAD, MANAGER_PAYLOAD, MANAGER_OTHER_PAYLOAD, TRANSCRIPTEUR_PAYLOAD, EXPERT_PAYLOAD
import main

# --- Data Factories ---

def create_membership_row(id=1, manager_id="manager-1", member_id="user-1"):
    row = MagicMock()
    row.id = id
    row.manager_id = manager_id
    row.member_id = member_id
    row.created_at = datetime.now(timezone.utc)
    return row

# --- API Tests: Story 16.2 IAM Perimeter Mapping ---

@pytest.mark.asyncio
async def test_post_membership_admin_success(mock_db):
    """[P1] Admin creates new membership core functionality."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    # Mock: No existing membership for this member
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = res
    
    response = client.post("/v1/iam/memberships", json={
        "manager_id": "manager-1",
        "member_id": "user-1"
    })
    
    assert response.status_code == 201
    data = response.json()
    assert data["manager_id"] == "manager-1"
    assert data["member_id"] == "user-1"
    assert "id" in data

@pytest.mark.asyncio
async def test_post_membership_forbidden_non_admin(mock_db):
    """[P0] Security: Non-Admin attempts to create membership."""
    main.app.dependency_overrides[main.get_current_user] = lambda: MANAGER_PAYLOAD
    
    response = client.post("/v1/iam/memberships", json={
        "manager_id": "manager-1",
        "member_id": "user-1"
    })
    
    assert response.status_code == 403
    assert "Admin role required" in response.json()["detail"]["error"]

@pytest.mark.asyncio
async def test_post_membership_conflict_member_assigned_elsewhere(mock_db):
    """[P0] Integrity: Member already belongs to another manager."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    # Mock: Member already exists under a DIFFERENT manager
    existing = create_membership_row(manager_id="other-manager", member_id="user-1")
    res = MagicMock()
    res.scalar_one_or_none.return_value = existing
    mock_db.execute.return_value = res
    
    response = client.post("/v1/iam/memberships", json={
        "manager_id": "manager-1",
        "member_id": "user-1"
    })
    
    assert response.status_code == 409
    assert "already belongs to another manager" in response.json()["detail"]["error"]

@pytest.mark.asyncio
async def test_post_membership_idempotent_same_pair(mock_db):
    """[P2] Robustness: Idempotent POST (same pair)."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    # Mock: Membership already exists for SAME pair
    existing = create_membership_row(id=10, manager_id="manager-1", member_id="user-1")
    res = MagicMock()
    res.scalar_one_or_none.return_value = existing
    mock_db.execute.return_value = res
    
    response = client.post("/v1/iam/memberships", json={
        "manager_id": "manager-1",
        "member_id": "user-1"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 10

@pytest.mark.asyncio
async def test_post_membership_invalid_same_ids(mock_db):
    """[P2] Validation: manager_id == member_id (400)."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    response = client.post("/v1/iam/memberships", json={
        "manager_id": "same-id",
        "member_id": "same-id"
    })
    
    assert response.status_code == 400
    assert "must be different" in response.json()["detail"]["error"]

@pytest.mark.asyncio
async def test_get_memberships_admin_visibility(mock_db):
    """[P1] Admin lists memberships for any manager."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    res = MagicMock()
    res.scalars.return_value.all.return_value = [create_membership_row(manager_id="manager-1")]
    mock_db.execute.return_value = res
    
    response = client.get("/v1/iam/memberships/manager-1")
    
    assert response.status_code == 200
    assert len(response.json()) == 1

@pytest.mark.asyncio
async def test_get_memberships_manager_own_perimeter(mock_db):
    """[P1] Manager lists own perimeter."""
    # Payload has sub="user-123"
    main.app.dependency_overrides[main.get_current_user] = lambda: MANAGER_PAYLOAD
    
    res = MagicMock()
    res.scalars.return_value.all.return_value = [create_membership_row(manager_id="user-123")]
    mock_db.execute.return_value = res
    
    response = client.get("/v1/iam/memberships/user-123")
    
    assert response.status_code == 200
    assert len(response.json()) == 1

@pytest.mark.asyncio
async def test_get_memberships_manager_forbidden_other_perimeter(mock_db):
    """[P0] Privacy: Manager attempts to list another's perimeter."""
    # Payload has sub="user-123"
    main.app.dependency_overrides[main.get_current_user] = lambda: MANAGER_PAYLOAD
    
    response = client.get("/v1/iam/memberships/other-manager")
    
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]["error"]

@pytest.mark.asyncio
async def test_delete_membership_admin_success(mock_db):
    """[P1] Admin deletes membership."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    res = MagicMock()
    res.rowcount = 1
    mock_db.execute.return_value = res
    
    response = client.delete("/v1/iam/memberships/manager-1/user-1")
    
    assert response.status_code == 204

@pytest.mark.asyncio
async def test_delete_membership_not_found(mock_db):
    """[P2] Error Handling: Delete non-existent membership (404)."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    res = MagicMock()
    res.rowcount = 0
    mock_db.execute.return_value = res
    
    response = client.delete("/v1/iam/memberships/manager-1/user-missing")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]["error"]
