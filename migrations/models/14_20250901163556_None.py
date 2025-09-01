from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "user" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "email" VARCHAR(255) NOT NULL,
    "email_verified" BOOL NOT NULL  DEFAULT False,
    "password" VARCHAR(255) NOT NULL,
    "role" VARCHAR(255) NOT NULL  DEFAULT 'user',
    "profile_photo" VARCHAR(255)
);
CREATE TABLE IF NOT EXISTS "codes" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "type" VARCHAR(255) NOT NULL,
    "value" TEXT NOT NULL,
    "expires_at" DATE NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS "purchasednumber" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "phone_number" VARCHAR(20) NOT NULL,
    "friendly_name" VARCHAR(255),
    "region" VARCHAR(255),
    "postal_code" VARCHAR(20),
    "iso_country" VARCHAR(10),
    "last_month_payment" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "attached_assistant" INT,
    "vapi_phone_uuid" VARCHAR(255),
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "assistant" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "vapi_assistant_id" VARCHAR(255),
    "name" VARCHAR(255) NOT NULL,
    "provider" VARCHAR(255) NOT NULL,
    "first_message" VARCHAR(255) NOT NULL,
    "model" VARCHAR(255) NOT NULL,
    "systemPrompt" TEXT NOT NULL,
    "knowledgeBase" JSONB,
    "leadsfile" JSONB,
    "temperature" DOUBLE PRECISION,
    "maxTokens" INT,
    "transcribe_provider" VARCHAR(255),
    "transcribe_language" VARCHAR(255),
    "transcribe_model" VARCHAR(255),
    "voice_provider" VARCHAR(255),
    "voice" VARCHAR(255),
    "forwardingPhoneNumber" VARCHAR(255),
    "endCallPhrases" JSONB,
    "attached_Number" VARCHAR(255),
    "vapi_phone_uuid" VARCHAR(255),
    "draft" BOOL   DEFAULT False,
    "assistant_toggle" BOOL,
    "success_evalution" TEXT,
    "category" TEXT,
    "voice_model" TEXT,
    "languages" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "speed" DOUBLE PRECISION   DEFAULT 1,
    "stability" DOUBLE PRECISION   DEFAULT 0.5,
    "similarityBoost" DOUBLE PRECISION   DEFAULT 0.75,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "calllog" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "lead_id" INT,
    "call_started_at" TIMESTAMPTZ,
    "customer_number" VARCHAR(100),
    "customer_name" VARCHAR(100),
    "call_id" VARCHAR(1000),
    "cost" DECIMAL(10,2),
    "call_ended_at" TIMESTAMPTZ,
    "call_ended_reason" VARCHAR(100),
    "call_duration" DOUBLE PRECISION,
    "is_transferred" BOOL   DEFAULT False,
    "status" VARCHAR(100),
    "criteria_satisfied" BOOL   DEFAULT False,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "file" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "alphanumeric_id" VARCHAR(8)  UNIQUE,
    "name" VARCHAR(255) NOT NULL,
    "url" TEXT,
    "sync_enable" BOOL   DEFAULT False,
    "sync_frequency" INT,
    "is_syncing" BOOL   DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "lead" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "first_name" VARCHAR(255) NOT NULL,
    "last_name" VARCHAR(255) NOT NULL,
    "email" VARCHAR(255) NOT NULL,
    "add_date" DATE NOT NULL,
    "salesforce_id" VARCHAR(255),
    "mobile" VARCHAR(255) NOT NULL,
    "state" VARCHAR(255),
    "timezone" VARCHAR(255),
    "dnc" BOOL NOT NULL  DEFAULT False,
    "submit_for_approval" BOOL NOT NULL  DEFAULT False,
    "other_data" JSONB,
    "last_called_at" TIMESTAMPTZ,
    "call_count" INT   DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "file_id" INT REFERENCES "file" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "documents" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "file_name" VARCHAR(255) NOT NULL,
    "vapi_file_id" VARCHAR(255),
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "campaign" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "selection_mode" VARCHAR(4) NOT NULL  DEFAULT 'ALL',
    "include_lead_ids" JSONB,
    "exclude_lead_ids" JSONB,
    "timezone" VARCHAR(64) NOT NULL  DEFAULT 'America/Los_Angeles',
    "days_of_week" JSONB,
    "daily_start" VARCHAR(5),
    "daily_end" VARCHAR(5),
    "start_at" TIMESTAMPTZ,
    "end_at" TIMESTAMPTZ,
    "calls_per_minute" INT NOT NULL  DEFAULT 10,
    "parallel_calls" INT NOT NULL  DEFAULT 2,
    "retry_on_busy" BOOL NOT NULL  DEFAULT True,
    "busy_retry_delay_minutes" INT NOT NULL  DEFAULT 15,
    "max_attempts" INT NOT NULL  DEFAULT 3,
    "status" VARCHAR(9) NOT NULL  DEFAULT 'draft',
    "last_tick_at" TIMESTAMPTZ,
    "calendar_ics" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "assistant_id" INT NOT NULL REFERENCES "assistant" ("id") ON DELETE CASCADE,
    "file_id" INT NOT NULL REFERENCES "file" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
COMMENT ON COLUMN "campaign"."selection_mode" IS 'ALL: ALL\nONLY: ONLY\nSKIP: SKIP';
COMMENT ON COLUMN "campaign"."status" IS 'DRAFT: draft\nSCHEDULED: scheduled\nRUNNING: running\nPAUSED: paused\nSTOPPED: stopped\nCOMPLETED: completed';
CREATE TABLE IF NOT EXISTS "campaignleadprogress" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "status" VARCHAR(32) NOT NULL  DEFAULT 'pending',
    "attempt_count" INT NOT NULL  DEFAULT 0,
    "last_attempt_at" TIMESTAMPTZ,
    "next_attempt_at" TIMESTAMPTZ,
    "last_call_id" VARCHAR(200),
    "last_ended_reason" VARCHAR(200),
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "campaign_id" INT NOT NULL REFERENCES "campaign" ("id") ON DELETE CASCADE,
    "lead_id" INT NOT NULL REFERENCES "lead" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_campaignlea_campaig_84fb87" UNIQUE ("campaign_id", "lead_id")
);
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
CREATE TABLE IF NOT EXISTS "appointments" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "title" VARCHAR(200) NOT NULL,
    "notes" TEXT,
    "location" VARCHAR(200),
    "phone" VARCHAR(32) NOT NULL,
    "timezone" VARCHAR(64) NOT NULL,
    "start_at" TIMESTAMPTZ NOT NULL,
    "end_at" TIMESTAMPTZ NOT NULL,
    "duration_minutes" INT NOT NULL,
    "status" VARCHAR(9) NOT NULL  DEFAULT 'scheduled',
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "idx_appointment_start_a_9142e1" ON "appointments" ("start_at", "phone");
COMMENT ON COLUMN "appointments"."status" IS 'SCHEDULED: scheduled\nCANCELLED: cancelled\nCOMPLETED: completed';
COMMENT ON TABLE "appointments" IS 'Stores a single appointment with tz-aware start/end.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
