from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "lead" ALTER COLUMN "origin" SET DEFAULT 'CSV';
        CREATE INDEX "idx_lead_file_id_a7e90f" ON "lead" ("file_id", "origin");
        CREATE INDEX "idx_lead_salesfo_6e832f" ON "lead" ("salesforce_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_lead_salesfo_6e832f";
        DROP INDEX IF EXISTS "idx_lead_file_id_a7e90f";
        ALTER TABLE "lead" ALTER COLUMN "origin" SET DEFAULT 'form';"""
