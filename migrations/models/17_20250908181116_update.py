from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "user" ADD "twilio_auth_token" VARCHAR(64);
        ALTER TABLE "user" ADD "twilio_account_sid" VARCHAR(64);
        CREATE TABLE IF NOT EXISTS "chat_message" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "text" TEXT,
    "attachments" JSONB,
    "read_by_user" BOOL NOT NULL  DEFAULT False,
    "read_by_admin" BOOL NOT NULL  DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "sender_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "thread_id" INT NOT NULL REFERENCES "chat_thread" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_chat_messag_thread__e7bc15" ON "chat_message" ("thread_id", "created_at");
COMMENT ON TABLE "chat_message" IS 'Messages inside a thread.';
        CREATE TABLE IF NOT EXISTS "chat_thread" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "admin_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_chat_thread_user_id_291e5d" UNIQUE ("user_id", "admin_id")
);
CREATE INDEX IF NOT EXISTS "idx_chat_thread_user_id_22cfc2" ON "chat_thread" ("user_id");
CREATE INDEX IF NOT EXISTS "idx_chat_thread_admin_i_602cb1" ON "chat_thread" ("admin_id");
COMMENT ON TABLE "chat_thread" IS 'One thread per (user, admin) pair.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "user" DROP COLUMN "twilio_auth_token";
        ALTER TABLE "user" DROP COLUMN "twilio_account_sid";
        DROP TABLE IF EXISTS "chat_message";
        DROP TABLE IF EXISTS "chat_thread";"""
