"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-21

Eingefrorener Stand des Anfangsschemas als explizite Tabellendefinitionen.

Urspruenglich rief diese Migration `Base.metadata.create_all()` auf, erzeugte also das Schema
aus den *jeweils aktuellen* Modellen. Das haette jede spaetere Modellaenderung bereits in 0001
einfliessen lassen: Auf einer Neuinstallation waere dann ein anderes Schema entstanden als auf
bestehenden Installationen, und nachfolgende Migrationen haetten dort kollidiert. Deshalb wurde
0001 am 2026-09-22 per Alembic-Autogenerate gegen eine leere Datenbank in genau den Stand
ueberfuehrt, den bestehende Installationen bereits haben (inkl. der dort vorhandenen Maengel an
einigen Zeitstempel-Spalten - diese behebt Migration 0003 fuer alle Installationen gleich).

Aenderungen am Schema gehoeren ab jetzt ausschliesslich in neue Migrationen.
"""
import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table('tenants',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('default_language', sa.String(length=10), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ai_model_configs',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.Enum('ollama_local', 'external_api', name='ai_provider'), nullable=False),
    sa.Column('chat_model_name', sa.String(length=200), nullable=False),
    sa.Column('embedding_model_name', sa.String(length=200), nullable=False),
    sa.Column('external_api_endpoint', sa.String(length=500), nullable=True),
    sa.Column('external_api_key_encrypted', sa.Text(), nullable=True),
    sa.Column('caution_level', sa.Enum('vorsichtig', 'normal', 'mutig', name='ai_caution_level'), nullable=False),
    sa.Column('min_exemplars_fast_path', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_model_configs_tenant_id'), 'ai_model_configs', ['tenant_id'], unique=True)
    op.create_table('categories',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('is_restricted', sa.Boolean(), nullable=False),
    sa.Column('is_system_default', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_categories_tenant_id'), 'categories', ['tenant_id'], unique=False)
    op.create_table('import_sources',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.Enum('nas_watch_folder', 'client_agent', name='import_source_type'), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_scanned_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_import_sources_tenant_id'), 'import_sources', ['tenant_id'], unique=False)
    op.create_table('tags',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_tag_tenant_name')
    )
    op.create_index(op.f('ix_tags_tenant_id'), 'tags', ['tenant_id'], unique=False)
    op.create_table('users',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=False),
    sa.Column('role', sa.Enum('admin', 'member', name='user_role'), nullable=False),
    sa.Column('locale', sa.String(length=10), nullable=False),
    sa.Column('notification_channels', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    comment='email ist pro Tenant eindeutig - siehe Datenmodell 3.2'
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)
    op.create_table('category_access',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('category_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('can_view', sa.Boolean(), nullable=False),
    sa.Column('can_edit', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('category_id', 'user_id', name='uq_category_access_user')
    )
    op.create_index(op.f('ix_category_access_category_id'), 'category_access', ['category_id'], unique=False)
    op.create_index(op.f('ix_category_access_tenant_id'), 'category_access', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_category_access_user_id'), 'category_access', ['user_id'], unique=False)
    op.create_table('documents',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('owner_user_id', sa.UUID(), nullable=False),
    sa.Column('category_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('ocr_text', sa.Text(), nullable=False),
    sa.Column('ocr_language', sa.String(length=10), nullable=False),
    sa.Column('ocr_status', sa.Enum('pending', 'done', 'failed', name='ocr_status'), nullable=False),
    sa.Column('classification_status', sa.Enum('pending', 'auto_assigned', 'needs_review', 'confirmed', name='classification_status'), nullable=False),
    sa.Column('classification_confidence', sa.Numeric(), nullable=True),
    sa.Column('classification_stage', sa.Enum('embedding', 'llm', 'manual', 'chat', name='classification_stage'), nullable=True),
    sa.Column('extraction_status', sa.Enum('pending', 'done', 'failed', name='extraction_status'), nullable=False),
    sa.Column('source', sa.Enum('photo_app', 'upload', 'nas_scan_folder', 'client_agent', 'email', name='document_source'), nullable=False),
    sa.Column('document_date', sa.Date(), nullable=True),
    sa.Column('issuer', sa.String(length=300), nullable=True),
    sa.Column('amount', sa.Numeric(), nullable=True),
    sa.Column('original_present', sa.Enum('ja', 'nein', 'unbekannt', name='original_present'), nullable=False),
    sa.Column('original_location', sa.String(length=300), nullable=True),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_documents_category_id'), 'documents', ['category_id'], unique=False)
    op.create_index(op.f('ix_documents_owner_user_id'), 'documents', ['owner_user_id'], unique=False)
    op.create_index(op.f('ix_documents_tenant_id'), 'documents', ['tenant_id'], unique=False)
    op.create_table('notifications',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.Enum('new_document', 'wiedervorlage_due', 'wiedervorlage_vorschlag', 'needs_review', name='notification_type'), nullable=False),
    sa.Column('channel', sa.Enum('in_app', 'email', 'push', name='notification_channel'), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('status', sa.Enum('unread', 'read', 'sent', 'failed', name='notification_status'), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default='now()', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_tenant_id'), 'notifications', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_table('push_subscriptions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('endpoint', sa.String(length=1000), nullable=False),
    sa.Column('keys', postgresql.JSONB(astext_type=Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default='now()', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_push_subscriptions_user_id'), 'push_subscriptions', ['user_id'], unique=False)
    op.create_table('refresh_tokens',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=255), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.create_table('retention_rules',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('category_id', sa.UUID(), nullable=True),
    sa.Column('retention_period_months', sa.Integer(), nullable=True),
    sa.Column('requires_original', sa.Boolean(), nullable=False),
    sa.Column('notify_before_days', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_retention_rules_tenant_id'), 'retention_rules', ['tenant_id'], unique=False)
    op.create_table('category_exemplars',
    sa.Column('category_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=True),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=False),
    sa.Column('created_via', sa.Enum('auto_high_confidence', 'llm_confirmed', 'manual_feedback', 'chat_correction', name='exemplar_source'), nullable=False),
    sa.Column('confirmed_by_user_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default='now()', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['confirmed_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_category_exemplars_category_id'), 'category_exemplars', ['category_id'], unique=False)
    op.create_table('chat_sessions',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('scope_document_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['scope_document_id'], ['documents.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_sessions_tenant_id'), 'chat_sessions', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_chat_sessions_user_id'), 'chat_sessions', ['user_id'], unique=False)
    op.create_table('classification_events',
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('previous_category_id', sa.UUID(), nullable=True),
    sa.Column('new_category_id', sa.UUID(), nullable=True),
    sa.Column('stage', sa.Enum('embedding', 'llm', 'manual', 'chat', name='classification_event_stage'), nullable=False),
    sa.Column('confidence', sa.Numeric(), nullable=True),
    sa.Column('triggered_by_user_id', sa.UUID(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default='now()', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['new_category_id'], ['categories.id'], ),
    sa.ForeignKeyConstraint(['previous_category_id'], ['categories.id'], ),
    sa.ForeignKeyConstraint(['triggered_by_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_classification_events_document_id'), 'classification_events', ['document_id'], unique=False)
    op.create_table('document_access_overrides',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('can_view', sa.Boolean(), nullable=False),
    sa.Column('can_edit', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id', 'user_id', name='uq_doc_access_user')
    )
    op.create_index(op.f('ix_document_access_overrides_document_id'), 'document_access_overrides', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_access_overrides_tenant_id'), 'document_access_overrides', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_document_access_overrides_user_id'), 'document_access_overrides', ['user_id'], unique=False)
    op.create_table('document_files',
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('file_path', sa.String(length=1000), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('checksum', sa.String(length=128), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_files_document_id'), 'document_files', ['document_id'], unique=False)
    op.create_table('document_tags',
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('tag_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('document_id', 'tag_id')
    )
    op.create_table('wiedervorlagen',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('type', sa.Enum('retention', 'custom', name='wiedervorlage_type'), nullable=False),
    sa.Column('source', sa.Enum('manual', 'ai_suggested', 'retention_rule', name='wiedervorlage_source'), nullable=False),
    sa.Column('status', sa.Enum('vorgeschlagen', 'offen', 'erledigt', 'verworfen', name='wiedervorlage_status'), nullable=False),
    sa.Column('confidence', sa.Numeric(), nullable=True),
    sa.Column('source_snippet', sa.Text(), nullable=True),
    sa.Column('recurrence', sa.Enum('none', 'monthly', 'yearly', 'custom_months', name='wiedervorlage_recurrence'), nullable=False),
    sa.Column('recurrence_interval_months', sa.Integer(), nullable=True),
    sa.Column('assigned_user_id', sa.UUID(), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('reminder_lead_days', sa.Integer(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('completed_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['assigned_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['completed_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_wiedervorlagen_document_id'), 'wiedervorlagen', ['document_id'], unique=False)
    op.create_index(op.f('ix_wiedervorlagen_tenant_id'), 'wiedervorlagen', ['tenant_id'], unique=False)
    op.create_table('chat_messages',
    sa.Column('chat_session_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.Enum('user', 'assistant', 'tool', name='chat_message_role'), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('tool_calls', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('tool_results', postgresql.JSONB(astext_type=Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default='now()', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['chat_session_id'], ['chat_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_messages_chat_session_id'), 'chat_messages', ['chat_session_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_chat_messages_chat_session_id'), table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_index(op.f('ix_wiedervorlagen_tenant_id'), table_name='wiedervorlagen')
    op.drop_index(op.f('ix_wiedervorlagen_document_id'), table_name='wiedervorlagen')
    op.drop_table('wiedervorlagen')
    op.drop_table('document_tags')
    op.drop_index(op.f('ix_document_files_document_id'), table_name='document_files')
    op.drop_table('document_files')
    op.drop_index(op.f('ix_document_access_overrides_user_id'), table_name='document_access_overrides')
    op.drop_index(op.f('ix_document_access_overrides_tenant_id'), table_name='document_access_overrides')
    op.drop_index(op.f('ix_document_access_overrides_document_id'), table_name='document_access_overrides')
    op.drop_table('document_access_overrides')
    op.drop_index(op.f('ix_classification_events_document_id'), table_name='classification_events')
    op.drop_table('classification_events')
    op.drop_index(op.f('ix_chat_sessions_user_id'), table_name='chat_sessions')
    op.drop_index(op.f('ix_chat_sessions_tenant_id'), table_name='chat_sessions')
    op.drop_table('chat_sessions')
    op.drop_index(op.f('ix_category_exemplars_category_id'), table_name='category_exemplars')
    op.drop_table('category_exemplars')
    op.drop_index(op.f('ix_retention_rules_tenant_id'), table_name='retention_rules')
    op.drop_table('retention_rules')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_token_hash'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index(op.f('ix_push_subscriptions_user_id'), table_name='push_subscriptions')
    op.drop_table('push_subscriptions')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_tenant_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_documents_tenant_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_owner_user_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_category_id'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_category_access_user_id'), table_name='category_access')
    op.drop_index(op.f('ix_category_access_tenant_id'), table_name='category_access')
    op.drop_index(op.f('ix_category_access_category_id'), table_name='category_access')
    op.drop_table('category_access')
    op.drop_index(op.f('ix_users_tenant_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_tags_tenant_id'), table_name='tags')
    op.drop_table('tags')
    op.drop_index(op.f('ix_import_sources_tenant_id'), table_name='import_sources')
    op.drop_table('import_sources')
    op.drop_index(op.f('ix_categories_tenant_id'), table_name='categories')
    op.drop_table('categories')
    op.drop_index(op.f('ix_ai_model_configs_tenant_id'), table_name='ai_model_configs')
    op.drop_table('ai_model_configs')
    op.drop_table('tenants')
