from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "call_blocklist" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "phone_number" VARCHAR(32) NOT NULL,
    "reason" VARCHAR(255),
    "blocked_until" TIMESTAMPTZ,
    "hit_count" INT NOT NULL  DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "uid_call_blockl_phone_n_c5c6d7" UNIQUE ("phone_number")
);
CREATE INDEX IF NOT EXISTS "idx_call_blockl_phone_n_c5c6d7" ON "call_blocklist" ("phone_number");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "call_blocklist";"""
