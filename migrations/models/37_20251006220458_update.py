from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "call_details" ADD "interest_confidence" DOUBLE PRECISION;
        ALTER TABLE "call_details" ADD "interest_status" VARCHAR(32);
        CREATE  INDEX "idx_call_detail_user_id_02534a" ON "call_details" ("user_id", "interest_status");
        CREATE INDEX "idx_call_detail_interes_4a10d4" ON "call_details" ("interest_status");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_call_detail_interes_4a10d4";
        DROP INDEX IF EXISTS "idx_call_detail_user_id_02534a";
        ALTER TABLE "call_details" DROP COLUMN "interest_confidence";
        ALTER TABLE "call_details" DROP COLUMN "interest_status";"""
