"""
Integration test for DELETE /admin/users/{user_id} endpoint.
Validates backend logic with full mock isolation — no production DB touched.
"""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient


def _make_user(uid, name, email, cpf, balance=0.0, is_active=True):
    from app.auth.models import User
    u = User()
    u.id = uid
    u.name = name
    u.email = email
    u.cpf_cnpj = cpf
    u.is_active = is_active
    u.hashed_password = "x"
    u.balance = balance
    return u


def _db_mock_for_delete(target_user):
    """DB mock: resolves target on User query, returns 0 orphans on cascade deletes."""
    db = MagicMock()

    def query_side(model):
        from app.auth.models import User
        q = MagicMock()
        if model is User:
            q.filter.return_value.first.return_value = target_user
        else:
            q.filter.return_value.delete.return_value = 0
            q.filter.return_value.first.return_value = None
        return q

    db.query.side_effect = query_side
    db.delete = MagicMock()
    db.commit = MagicMock()
    return db


class TestAdminDeleteUser:

    def test_delete_existing_user_returns_200(self):
        from app.main import app
        from app.auth.dependencies import get_current_user
        from app.core.database import get_db

        admin = _make_user("admin-001", "Admin", "biocodetechnology@gmail.com", "35060268870", 10.0)
        target = _make_user("target-999", "Fake Test Delete", "fake@example.com", "11111111111")
        db = _db_mock_for_delete(target)

        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                resp = client.delete(f"/admin/users/{target.id}")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["deleted"]["user_id"] == target.id
        assert body["deleted"]["name"] == target.name
        db.delete.assert_called_once_with(target)
        db.commit.assert_called_once()

    def test_delete_nonexistent_user_returns_404(self):
        from app.main import app
        from app.auth.dependencies import get_current_user
        from app.core.database import get_db

        admin = _make_user("admin-001", "Admin", "biocodetechnology@gmail.com", "35060268870", 10.0)
        db = MagicMock()

        def query_side(model):
            q = MagicMock()
            q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = query_side

        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                resp = client.delete("/admin/users/nonexistent-id-000")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 404

    def test_delete_self_returns_400(self):
        from app.main import app
        from app.auth.dependencies import get_current_user
        from app.core.database import get_db

        admin = _make_user("admin-001", "Admin", "biocodetechnology@gmail.com", "35060268870", 10.0)
        db = _db_mock_for_delete(admin)  # target IS the admin itself

        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                resp = client.delete(f"/admin/users/{admin.id}")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 400

    def test_non_admin_cannot_delete(self):
        from app.main import app
        from app.auth.dependencies import get_current_user
        from app.core.database import get_db

        non_admin = _make_user("user-999", "Regular User", "regular@example.com", "99999999999")
        target = _make_user("target-999", "Fake Test Delete", "fake@example.com", "11111111111")
        db = _db_mock_for_delete(target)

        app.dependency_overrides[get_current_user] = lambda: non_admin
        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                resp = client.delete(f"/admin/users/{target.id}")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 403
