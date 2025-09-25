from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "account_transactions" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "amount_cents" INT NOT NULL,
    "currency" VARCHAR(8) NOT NULL  DEFAULT 'USD',
    "kind" VARCHAR(32) NOT NULL,
    "description" VARCHAR(255),
    "stripe_payment_intent_id" VARCHAR(128),
    "metadata" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "account_transactions";"""
