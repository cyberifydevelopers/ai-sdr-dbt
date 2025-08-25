from tortoise import BaseDBAsyncClient

async def upgrade(db: BaseDBAsyncClient) -> str:
    return r"""
DO $$
BEGIN
    -- Create "campaign" if missing
    IF to_regclass('campaign') IS NULL THEN
        CREATE TABLE "campaign" (
            "id" SERIAL PRIMARY KEY,
            "user_id" INT NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
            "name" VARCHAR(255) NOT NULL,

            "file_id" INT NOT NULL REFERENCES "file"("id") ON DELETE CASCADE,
            "selection_mode" VARCHAR(8) NOT NULL DEFAULT 'ALL',
            "include_lead_ids" JSONB NULL,
            "exclude_lead_ids" JSONB NULL,

            "assistant_id" INT NOT NULL REFERENCES "assistant"("id") ON DELETE CASCADE,

            "timezone" VARCHAR(64) NOT NULL DEFAULT 'America/Los_Angeles',
            "days_of_week" JSONB NULL,
            "daily_start" VARCHAR(5) NULL,
            "daily_end"   VARCHAR(5) NULL,
            "start_at" TIMESTAMPTZ NULL,
            "end_at"   TIMESTAMPTZ NULL,

            "calls_per_minute" INT NOT NULL DEFAULT 10,
            "parallel_calls"   INT NOT NULL DEFAULT 2,

            "retry_on_busy" BOOLEAN NOT NULL DEFAULT TRUE,
            "busy_retry_delay_minutes" INT NOT NULL DEFAULT 15,
            "max_attempts" INT NOT NULL DEFAULT 3,

            "status" VARCHAR(16) NOT NULL DEFAULT 'draft',
            "last_tick_at" TIMESTAMPTZ NULL,
            "calendar_ics" TEXT NULL,

            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    END IF;

    -- Create "campaignleadprogress" if missing
    IF to_regclass('campaignleadprogress') IS NULL THEN
        CREATE TABLE "campaignleadprogress" (
            "id" SERIAL PRIMARY KEY,
            "campaign_id" INT NOT NULL REFERENCES "campaign"("id") ON DELETE CASCADE,
            "lead_id"     INT NOT NULL REFERENCES "lead"("id") ON DELETE CASCADE,

            "status" VARCHAR(32) NOT NULL DEFAULT 'pending',
            "attempt_count" INT NOT NULL DEFAULT 0,
            "last_attempt_at" TIMESTAMPTZ NULL,
            "next_attempt_at" TIMESTAMPTZ NULL,

            "last_call_id" VARCHAR(200) NULL,
            "last_ended_reason" VARCHAR(200) NULL,

            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    END IF;

    -- Clean up any legacy index/constraint names from older attempts
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uid_campaignlea_campaig_84fb87'
          AND conrelid = 'campaignleadprogress'::regclass
    ) THEN
        ALTER TABLE "campaignleadprogress"
        DROP CONSTRAINT "uid_campaignlea_campaig_84fb87";
    END IF;
    DROP INDEX IF EXISTS "uid_campaignlea_campaig_84fb87";

    -- Ensure correct unique constraint on (campaign_id, lead_id)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uid_campaignleadprogress_campaign_id_lead_id'
          AND conrelid = 'campaignleadprogress'::regclass
    ) THEN
        ALTER TABLE "campaignleadprogress"
        ADD CONSTRAINT "uid_campaignleadprogress_campaign_id_lead_id"
        UNIQUE ("campaign_id","lead_id");
    END IF;
END$$;
"""

async def downgrade(db: BaseDBAsyncClient) -> str:
    return r"""
DROP TABLE IF EXISTS "campaignleadprogress" CASCADE;
DROP TABLE IF EXISTS "campaign" CASCADE;
"""
