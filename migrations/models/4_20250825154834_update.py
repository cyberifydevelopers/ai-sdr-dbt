from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "integration_accounts" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "crm" VARCHAR(32) NOT NULL,
    "access_token" TEXT,
    "refresh_token" TEXT,
    "expires_at" TIMESTAMPTZ,
    "instance_url" VARCHAR(255),
    "scope" VARCHAR(512),
    "external_account_id" VARCHAR(128),
    "external_account_name" VARCHAR(255),
    "metadata" JSONB,
    "label" VARCHAR(255),
    "is_active" BOOL NOT NULL  DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_integration_user_id_402211" UNIQUE ("user_id", "crm")
);
COMMENT ON TABLE "integration_accounts" IS 'A connected CRM account for a given user.';

        CREATE TABLE IF NOT EXISTS "integration_oauth_state" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "crm" VARCHAR(32) NOT NULL,
    "state" VARCHAR(128) NOT NULL UNIQUE,
    "redirect_to" VARCHAR(512),
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "integration_oauth_state" IS 'Temporary state row for OAuth ''state'' param so callbacks can identify user.';

        CREATE TABLE IF NOT EXISTS "lead_external_refs" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "crm" VARCHAR(32) NOT NULL,
    "external_id" VARCHAR(128) NOT NULL,
    "external_url" VARCHAR(512),
    "last_synced_at" TIMESTAMPTZ,
    "last_error" TEXT,
    "payload_snapshot" JSONB,
    "lead_id" INT NOT NULL REFERENCES "lead" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_lead_extern_lead_id_5073af" UNIQUE ("lead_id", "crm")
);
COMMENT ON TABLE "lead_external_refs" IS 'Mapping of our Lead → external CRM Contact/Lead ID.';

        -- IMPORTANT: create jobs BEFORE items (items has FK to jobs)
        CREATE TABLE IF NOT EXISTS "crm_sync_jobs" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "crm" VARCHAR(32) NOT NULL,
    "scope" VARCHAR(32) NOT NULL,
    "scope_ref" VARCHAR(64),
    "status" VARCHAR(16) NOT NULL  DEFAULT 'queued',
    "total" INT NOT NULL  DEFAULT 0,
    "success" INT NOT NULL  DEFAULT 0,
    "failed" INT NOT NULL  DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "finished_at" TIMESTAMPTZ,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "crm_sync_jobs" IS 'Optional: if you batch-push leads to CRMs, this tracks the job.';

        CREATE TABLE IF NOT EXISTS "crm_sync_items" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "status" VARCHAR(16) NOT NULL  DEFAULT 'queued',
    "error" TEXT,
    "job_id" INT NOT NULL REFERENCES "crm_sync_jobs" ("id") ON DELETE CASCADE,
    "lead_id" INT NOT NULL REFERENCES "lead" ("id") ON DELETE CASCADE
);
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- Drop dependents first
        DROP TABLE IF EXISTS "crm_sync_items";
        DROP TABLE IF EXISTS "crm_sync_jobs";
        DROP TABLE IF EXISTS "lead_external_refs";
        DROP TABLE IF EXISTS "integration_oauth_state";
        DROP TABLE IF EXISTS "integration_accounts";
"""
