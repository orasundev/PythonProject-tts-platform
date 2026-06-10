"""Initial schema — all tables

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enums ─────────────────────────────────────────────────────────────
    # op.execute("CREATE TYPE org_status_enum AS ENUM ('active', 'suspended')")
    # op.execute("CREATE TYPE user_role_enum AS ENUM ('owner', 'admin', 'member')")
    # op.execute("CREATE TYPE usage_status_enum AS ENUM ('success', 'error')")
    # op.execute("CREATE TYPE job_status_enum AS ENUM ('pending', 'processing', 'completed', 'failed')")

    # op.execute("CREATE TYPE IF NOT EXISTS org_status_enum AS ENUM ('active', 'suspended')")
    # op.execute("CREATE TYPE IF NOT EXISTS user_role_enum AS ENUM ('owner', 'admin', 'member')")
    # op.execute("CREATE TYPE IF NOT EXISTS usage_status_enum AS ENUM ('success', 'error')")
    # op.execute("CREATE TYPE IF NOT EXISTS job_status_enum AS ENUM ('pending', 'processing', 'completed', 'failed')")

    op.execute("""
    DO $$ BEGIN
        CREATE TYPE org_status_enum AS ENUM ('active', 'suspended');
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """)
    op.execute("""
    DO $$ BEGIN
        CREATE TYPE user_role_enum AS ENUM ('owner', 'admin', 'member');
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """)
    op.execute("""
    DO $$ BEGIN
        CREATE TYPE usage_status_enum AS ENUM ('success', 'error');
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """)
    op.execute("""
    DO $$ BEGIN
        CREATE TYPE job_status_enum AS ENUM ('pending', 'processing', 'completed', 'failed');
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """)



    # ── organisations ─────────────────────────────────────────────────────
    op.create_table(
        "organisations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("logo_url", sa.Text, nullable=True),
        sa.Column("status", sa.Enum("active", "suspended", name="org_status_enum"), nullable=False, server_default="active"),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("subscription_status", sa.String(50), nullable=False, server_default="free"),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chars_used_this_period", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_organisations_slug", "organisations", ["slug"], unique=True)

    # ── users ─────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", sa.Enum("owner", "admin", "member", name="user_role_enum"), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_email_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_superadmin", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("email_verification_token", sa.String(255), nullable=True),
        sa.Column("email_verification_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_reset_token", sa.String(255), nullable=True),
        sa.Column("password_reset_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_organisation_id", "users", ["organisation_id"])

    # ── plans ─────────────────────────────────────────────────────────────
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("monthly_char_limit", sa.Integer, nullable=False),
        sa.Column("max_api_keys", sa.Integer, nullable=False),
        sa.Column("allows_ssml", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("allows_all_voices", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("allows_webhooks", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("allows_priority_queue", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("file_retention_days", sa.Integer, nullable=False, server_default="7"),
        sa.Column("price_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("stripe_price_id", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_plans_name", "plans", ["name"], unique=True)

    # Seed default plans
    # op.execute("""
    #     INSERT INTO plans (id, name, monthly_char_limit, max_api_keys, allows_ssml,
    #         allows_all_voices, allows_webhooks, allows_priority_queue,
    #         file_retention_days, price_cents, description)
    #     VALUES
    #         (gen_random_uuid(), 'free',     10000,  1,  false, false, false, false,  7, 0,
    #          '10,000 chars/month, 3 voices, 1 API key'),
    #         (gen_random_uuid(), 'pro',      500000, 10, true,  true,  false, false,  30, 2900,
    #          '500,000 chars/month, all voices, SSML, 10 API keys — $29/month'),
    #         (gen_random_uuid(), 'business', -1,     50, true,  true,  true,  true,   90, 9900,
    #          'Unlimited chars, all voices, SSML, webhooks, priority queue — $99/month')
    # """)

    op.execute("""
    DO $$ BEGIN
        CREATE TYPE org_status_enum AS ENUM ('active', 'suspended');
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """)
    op.execute("""
    DO $$ BEGIN
        CREATE TYPE user_role_enum AS ENUM ('owner', 'admin', 'member');
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """)
    op.execute("""
    DO $$ BEGIN
        CREATE TYPE usage_status_enum AS ENUM ('success', 'error');
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """)
    op.execute("""
    DO $$ BEGIN
        CREATE TYPE job_status_enum AS ENUM ('pending', 'processing', 'completed', 'failed');
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """)

    # ── api_keys ──────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("hashed_secret", sa.String(64), nullable=False),
        sa.Column("environment", sa.String(10), nullable=False, server_default="live"),
        sa.Column("scopes", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_hashed_secret", "api_keys", ["hashed_secret"], unique=True)
    op.create_index("ix_api_keys_organisation_id", "api_keys", ["organisation_id"])
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])

    # ── usage_logs ────────────────────────────────────────────────────────
    op.create_table(
        "usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True),
        sa.Column("voice", sa.String(100), nullable=False),
        sa.Column("character_count", sa.Integer, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.Enum("success", "error", name="usage_status_enum"), nullable=False),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usage_logs_organisation_id", "usage_logs", ["organisation_id"])
    op.create_index("ix_usage_logs_user_id", "usage_logs", ["user_id"])
    op.create_index("ix_usage_logs_created_at", "usage_logs", ["created_at"])

    # ── generated_files ───────────────────────────────────────────────────
    op.create_table(
        "generated_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("s3_key", sa.String(512), nullable=False),
        sa.Column("voice", sa.String(100), nullable=False),
        sa.Column("character_count", sa.Integer, nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("output_format", sa.String(10), nullable=False, server_default="mp3"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_generated_files_organisation_id", "generated_files", ["organisation_id"])
    op.create_index("ix_generated_files_user_id", "generated_files", ["user_id"])
    op.create_index("ix_generated_files_created_at", "generated_files", ["created_at"])
    op.create_index("ix_generated_files_expires_at", "generated_files", ["expires_at"])

    # ── invitations ───────────────────────────────────────────────────────
    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("owner", "admin", "member", name="user_role_enum"), nullable=False),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_invitations_token", "invitations", ["token"], unique=True)
    op.create_index("ix_invitations_email", "invitations", ["email"])
    op.create_index("ix_invitations_organisation_id", "invitations", ["organisation_id"])

    # ── webhooks ──────────────────────────────────────────────────────────
    op.create_table(
        "webhooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("secret", sa.String(64), nullable=False),
        sa.Column("events", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("failure_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_webhooks_organisation_id", "webhooks", ["organisation_id"])

    # ── jobs ──────────────────────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum("pending", "processing", "completed", "failed", name="job_status_enum"), nullable=False, server_default="pending"),
        sa.Column("result_s3_key", sa.String(512), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_jobs_organisation_id", "jobs", ["organisation_id"])
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("webhooks")
    op.drop_table("invitations")
    op.drop_table("generated_files")
    op.drop_table("usage_logs")
    op.drop_table("api_keys")
    op.drop_table("plans")
    op.drop_table("users")
    op.drop_table("organisations")
    op.execute("DROP TYPE IF EXISTS job_status_enum")
    op.execute("DROP TYPE IF EXISTS usage_status_enum")
    op.execute("DROP TYPE IF EXISTS user_role_enum")
    op.execute("DROP TYPE IF EXISTS org_status_enum")
