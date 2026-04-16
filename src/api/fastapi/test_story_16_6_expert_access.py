import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime, timezone
import os

# We import main from the current directory
import main
from main import app, AudioFileStatus

client = TestClient(app)

EXPERT_PAYLOAD = {
    "sub": "user-456",
    "realm_access": {"roles": ["Expert"]},
    "preferred_username": "expert-user",
}

def test_expert_tasks_includes_label_studio_fields(mock_db):
    """
    Story 16.6: GET /v1/expert/tasks must include label_studio_project_id 
    and computed label_studio_url.
    """
    ts = datetime(2026, 4, 1, tzinfo=timezone.utc)
    
    # Mock data
    gse = MagicMock()
    gse.source = "label_studio"
    gse.weight = "high"
    gse.created_at = ts
    
    asg = MagicMock()
    asg.transcripteur_id = "user-456"
    asg.assigned_at = ts
    
    af = MagicMock()
    af.id = 11
    af.filename = "expert.wav"
    af.status = AudioFileStatus.TRANSCRIBED
    
    proj = MagicMock()
    proj.id = 3
    proj.name = "Expert Project"
    proj.label_studio_project_id = 42 # New field from Story 2.2
    
    mr = MagicMock()
    mr.all.return_value = [(gse, af, proj, asg)]
    mock_db.execute.return_value = mr

    with patch("main.decode_token", return_value=EXPERT_PAYLOAD):
        response = client.get(
            "/v1/expert/tasks",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    task = data[0]
    
    # These should fail initially
    assert "label_studio_project_id" in task
    assert task["label_studio_project_id"] == 42
    assert "label_studio_url" in task
    # Default LABEL_STUDIO_PUBLIC_URL is http://localhost:8090
    assert task["label_studio_url"] == "http://localhost:8090"
