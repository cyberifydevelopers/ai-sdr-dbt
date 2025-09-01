from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
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
        DROP TABLE IF EXISTS "appointments";"""
