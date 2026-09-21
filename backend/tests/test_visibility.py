"""homedms/core/visibility.py - prueft nur, dass die SQL-Ausdruecke korrekt aufgebaut/kompilierbar
sind (keine DB noetig). Das tatsaechliche Zugriffsverhalten (Owner/Admin/CategoryAccess/
DocumentAccessOverride-Zusammenspiel) braucht Integrationstests gegen eine echte DB
(siehe README.md "Tests") und ist hier bewusst nicht abgedeckt.
"""
import uuid

from sqlalchemy import true
from sqlalchemy.dialects import postgresql

from homedms.core.visibility import editable_documents_expr, visible_documents_expr
from homedms.models.tenant import User, UserRole


def _user(role: UserRole) -> User:
    return User(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="test@example.com",
        password_hash="x",
        display_name="Test",
        role=role,
    )


def test_admin_sees_everything():
    admin = _user(UserRole.admin)
    expr = visible_documents_expr(admin)
    # Fuer Admins ist der Ausdruck ein reines "true" - kein Subquery-Aufbau noetig.
    assert str(expr) == str(true())


def test_member_expression_compiles_to_sql():
    member = _user(UserRole.member)
    for expr in (visible_documents_expr(member), editable_documents_expr(member)):
        compiled = str(expr.compile(dialect=postgresql.dialect()))
        assert "document_access_overrides" in compiled
        assert "category_access" in compiled
        assert "categories" in compiled
