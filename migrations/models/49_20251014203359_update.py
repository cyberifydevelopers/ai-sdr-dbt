from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_call_detail_interes_4a10d4";
        DROP INDEX IF EXISTS "idx_call_detail_success_d92b1e";
        DROP INDEX IF EXISTS "idx_call_detail_user_id_02534a";
        DROP INDEX IF EXISTS "idx_call_detail_user_id_7dd8a9";
        ALTER TABLE "calllog" ADD "transcript" JSONB;
        ALTER TABLE "calllog" ADD "recording_url" VARCHAR(500);
        ALTER TABLE "calllog" ADD "analysis" JSONB;
        ALTER TABLE "calllog" ADD "summary" TEXT;
        ALTER TABLE "calllog" ALTER COLUMN "status" TYPE VARCHAR(50) USING "status"::VARCHAR(50);
        ALTER TABLE "call_details" DROP COLUMN "success_evaluation_status";
        ALTER TABLE "call_details" DROP COLUMN "interest_confidence";
        ALTER TABLE "call_details" DROP COLUMN "interest_status";
        ALTER TABLE "call_details" ALTER COLUMN "status" TYPE VARCHAR(50) USING "status"::VARCHAR(50);
        CREATE INDEX "idx_calllog_status_3d5ea2" ON "calllog" ("status");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_calllog_status_3d5ea2";
        ALTER TABLE "calllog" DROP COLUMN "transcript";
        ALTER TABLE "calllog" DROP COLUMN "recording_url";
        ALTER TABLE "calllog" DROP COLUMN "analysis";
        ALTER TABLE "calllog" DROP COLUMN "summary";
        ALTER TABLE "calllog" ALTER COLUMN "status" TYPE VARCHAR(100) USING "status"::VARCHAR(100);
        ALTER TABLE "call_details" ADD "success_evaluation_status" VARCHAR(64);
        ALTER TABLE "call_details" ADD "interest_confidence" DOUBLE PRECISION;
        ALTER TABLE "call_details" ADD "interest_status" VARCHAR(32);
        ALTER TABLE "call_details" ALTER COLUMN "status" TYPE VARCHAR(64) USING "status"::VARCHAR(64);
        CREATE  INDEX "idx_call_detail_user_id_7dd8a9" ON "call_details" ("user_id", "success_evaluation_status");
        CREATE  INDEX "idx_call_detail_user_id_02534a" ON "call_details" ("user_id", "interest_status");
        CREATE INDEX "idx_call_detail_success_d92b1e" ON "call_details" ("success_evaluation_status");
        CREATE INDEX "idx_call_detail_interes_4a10d4" ON "call_details" ("interest_status");"""
