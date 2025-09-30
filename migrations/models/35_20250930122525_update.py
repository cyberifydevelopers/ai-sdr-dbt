from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "calendar_accounts" ADD "external_org_id" VARCHAR(512);
        ALTER TABLE "calendar_accounts" ADD "webhook_signing_key" VARCHAR(512);
        ALTER TABLE "calendar_accounts" ADD "api_version" VARCHAR(64);
        ALTER TABLE "calendar_accounts" ADD "metadata" JSONB;
        ALTER TABLE "calendar_accounts" ADD "webhook_id" VARCHAR(256);
        ALTER TABLE "calendar_accounts" ALTER COLUMN "external_account_id" TYPE VARCHAR(512) USING "external_account_id"::VARCHAR(512);
        ALTER TABLE "calendar_accounts" ALTER COLUMN "external_email" TYPE VARCHAR(320) USING "external_email"::VARCHAR(320);
        ALTER TABLE "calendar_accounts" ALTER COLUMN "primary_calendar_id" TYPE VARCHAR(512) USING "primary_calendar_id"::VARCHAR(512);
        CREATE INDEX "idx_calendar_ac_provide_748ee7" ON "calendar_accounts" ("provider", "webhook_id");
        CREATE INDEX "idx_calendar_ac_provide_b9869f" ON "calendar_accounts" ("provider", "external_org_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_calendar_ac_provide_b9869f";
        DROP INDEX IF EXISTS "idx_calendar_ac_provide_748ee7";
        ALTER TABLE "calendar_accounts" DROP COLUMN "external_org_id";
        ALTER TABLE "calendar_accounts" DROP COLUMN "webhook_signing_key";
        ALTER TABLE "calendar_accounts" DROP COLUMN "api_version";
        ALTER TABLE "calendar_accounts" DROP COLUMN "metadata";
        ALTER TABLE "calendar_accounts" DROP COLUMN "webhook_id";
        ALTER TABLE "calendar_accounts" ALTER COLUMN "external_account_id" TYPE VARCHAR(128) USING "external_account_id"::VARCHAR(128);
        ALTER TABLE "calendar_accounts" ALTER COLUMN "external_email" TYPE VARCHAR(255) USING "external_email"::VARCHAR(255);
        ALTER TABLE "calendar_accounts" ALTER COLUMN "primary_calendar_id" TYPE VARCHAR(128) USING "primary_calendar_id"::VARCHAR(128);"""
