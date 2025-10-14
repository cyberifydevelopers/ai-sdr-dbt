from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_appointment_origin_941394";
        ALTER TABLE "appointments" DROP CONSTRAINT IF EXISTS "fk_appointm_lead_132d2bd0";
        ALTER TABLE "appointments" DROP COLUMN "lead_id";
        ALTER TABLE "appointments" DROP COLUMN "origin";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "appointments" ADD "lead_id" INT;
        ALTER TABLE "appointments" ADD "origin" VARCHAR(32);
        ALTER TABLE "appointments" ADD CONSTRAINT "fk_appointm_lead_132d2bd0" FOREIGN KEY ("lead_id") REFERENCES "lead" ("id") ON DELETE CASCADE;
        CREATE INDEX "idx_appointment_origin_941394" ON "appointments" ("origin");"""
