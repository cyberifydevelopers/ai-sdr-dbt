from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "calendar_accounts" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "provider" VARCHAR(32) NOT NULL,
    "external_account_id" VARCHAR(128) NOT NULL,
    "external_email" VARCHAR(255),
    "access_token" TEXT NOT NULL,
    "refresh_token" TEXT,
    "scope" TEXT,
    "expires_at" TIMESTAMPTZ,
    "primary_calendar_id" VARCHAR(128),
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_calendar_ac_user_id_e63f83" UNIQUE ("user_id", "provider", "external_account_id")
);
CREATE INDEX IF NOT EXISTS "idx_calendar_ac_user_id_b86c83" ON "calendar_accounts" ("user_id", "provider");
        CREATE TABLE IF NOT EXISTS "appointment_external_links" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "provider" VARCHAR(32) NOT NULL,
    "external_event_id" VARCHAR(128) NOT NULL,
    "external_calendar_id" VARCHAR(128),
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "account_id" UUID NOT NULL REFERENCES "calendar_accounts" ("id") ON DELETE CASCADE,
    "appointment_id" UUID NOT NULL REFERENCES "appointments" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_appointment_provide_bac3df" UNIQUE ("provider", "external_event_id")
);
CREATE INDEX IF NOT EXISTS "idx_appointment_account_c82d40" ON "appointment_external_links" ("account_id", "external_event_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "appointment_external_links";
        DROP TABLE IF EXISTS "calendar_accounts";"""
