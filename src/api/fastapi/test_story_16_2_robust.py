import pytest
from sqlalchemy import select
from main import ManagerMembership
from fastapi_test_app import client, ADMIN_PAYLOAD, MANAGER_PAYLOAD
import main

@pytest.mark.asyncio
async def test_post_membership_integrity_conflict(real_db):
    """
    [P0] Robustness: Verify that a database IntegrityError 
    (member already assigned to another manager) is correctly 
    mapped to a 409 Conflict by the API.
    """
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    # Setup: Create an existing membership directly in DB
    m1 = ManagerMembership(manager_id="manager-alpha", member_id="user-unique-1")
    real_db.add(m1)
    await real_db.commit()

    # Act: Attempt to create another membership for the SAME member via API
    response = client.post("/v1/iam/memberships", json={
        "manager_id": "manager-beta",
        "member_id": "user-unique-1"
    })
    
    # Assert: Should be 409 Conflict (not 500 or 201)
    assert response.status_code == 409
    assert "already belongs to another manager" in response.json()["error"]

@pytest.mark.asyncio
async def test_post_membership_idempotent_real_db(real_db):
    """
    [P2] Robustness: Verify idempotent behavior with a real DB.
    """
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    # Setup
    m1 = ManagerMembership(manager_id="m1", member_id="u1")
    real_db.add(m1)
    await real_db.commit()

    # Act: POST same pair again
    response = client.post("/v1/iam/memberships", json={
        "manager_id": "m1",
        "member_id": "u1"
    })
    
    # Assert: Should be 200 OK (idempotent)
    assert response.status_code == 200
    assert response.json()["member_id"] == "u1"

@pytest.mark.asyncio
async def test_delete_membership_real_db_success(real_db):
    """[P1] Verify DELETE actually removes from DB."""
    main.app.dependency_overrides[main.get_current_user] = lambda: ADMIN_PAYLOAD
    
    # Setup
    m1 = ManagerMembership(manager_id="m1", member_id="u1")
    real_db.add(m1)
    await real_db.commit()

    # Act
    response = client.delete("/v1/iam/memberships/m1/u1")
    
    # Assert
    assert response.status_code == 204
    
    # Verify DB state
    stmt = select(ManagerMembership).where(ManagerMembership.member_id == "u1")
    res = await real_db.execute(stmt)
    assert res.scalar_one_or_none() is None
