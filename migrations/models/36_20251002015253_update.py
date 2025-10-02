from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "call_details" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "call_id" VARCHAR(191),
    "assistant_id" VARCHAR(191),
    "phone_number_id" VARCHAR(191),
    "customer_number" VARCHAR(64),
    "customer_name" VARCHAR(191),
    "status" VARCHAR(64),
    "started_at" TIMESTAMPTZ,
    "ended_at" TIMESTAMPTZ,
    "duration" INT,
    "cost" DOUBLE PRECISION,
    "ended_reason" VARCHAR(128),
    "is_transferred" BOOL,
    "criteria_satisfied" BOOL,
    "success_evaluation_status" VARCHAR(64),
    "summary" JSONB,
    "transcript" JSONB,
    "analysis" JSONB,
    "recording_url" VARCHAR(500),
    "vapi_created_at" TIMESTAMPTZ,
    "vapi_updated_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "last_synced_at" TIMESTAMPTZ,
    "call_log_id" INT REFERENCES "calllog" ("id") ON DELETE SET NULL,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_call_detail_call_id_566c8a" ON "call_details" ("call_id");
CREATE INDEX IF NOT EXISTS "idx_call_detail_custome_81b870" ON "call_details" ("customer_number");
CREATE INDEX IF NOT EXISTS "idx_call_detail_status_6721ac" ON "call_details" ("status");
CREATE INDEX IF NOT EXISTS "idx_call_detail_success_d92b1e" ON "call_details" ("success_evaluation_status");
CREATE  INDEX "idx_call_detail_user_id_4baaa7" ON "call_details" ("user_id", "call_id");
CREATE  INDEX "idx_call_detail_user_id_b923dc" ON "call_details" ("user_id", "status");
CREATE  INDEX "idx_call_detail_user_id_7dd8a9" ON "call_details" ("user_id", "success_evaluation_status");
COMMENT ON TABLE "call_details" IS 'Per-user VAPI-enriched call snapshot.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "call_details";"""
