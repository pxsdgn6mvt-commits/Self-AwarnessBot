"""Tests for /api/services endpoint in server.py — verifies working_days in response."""
from unittest.mock import patch

import pytest


def test_api_services_includes_working_days():
    """Response from /api/services must contain 'working_days' as a list."""
    import server

    fake_response = {
        "categories": [{"id": 1, "name": "Nails", "items": []}],
        "working_days": [1, 2, 3, 4, 5],
    }

    with server.app.test_client() as client:
        with patch.object(server, "_run", return_value=fake_response):
            resp = client.get("/api/services?tenant_id=1")

    assert resp.status_code == 200
    data = resp.get_json()
    assert "working_days" in data, "Response must contain 'working_days' key"
    assert isinstance(data["working_days"], list), "'working_days' must be a list"
    assert data["working_days"] == [1, 2, 3, 4, 5]
