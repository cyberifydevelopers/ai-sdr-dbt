from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "message_jobs" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "from_number" VARCHAR(32),
    "status" VARCHAR(24) NOT NULL  DEFAULT 'running',
    "total" INT NOT NULL  DEFAULT 0,
    "sent" INT NOT NULL  DEFAULT 0,
    "failed" INT NOT NULL  DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "assistant_id" INT REFERENCES "assistant" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
        CREATE TABLE IF NOT EXISTS "message_records" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "to_number" VARCHAR(32) NOT NULL,
    "from_number" VARCHAR(32) NOT NULL,
    "body" TEXT NOT NULL,
    "sid" VARCHAR(255),
    "success" BOOL NOT NULL  DEFAULT False,
    "error" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "appointment_id" UUID REFERENCES "appointments" ("id") ON DELETE CASCADE,
    "assistant_id" INT REFERENCES "assistant" ("id") ON DELETE CASCADE,
    "job_id" UUID NOT NULL REFERENCES "message_jobs" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_message_rec_user_id_b23ffe" ON "message_records" ("user_id", "created_at");
CREATE INDEX IF NOT EXISTS "idx_message_rec_job_id_122e7c" ON "message_records" ("job_id", "created_at");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "message_records";
        DROP TABLE IF EXISTS "message_jobs";"""
