from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "notifications" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "kind" VARCHAR(32) NOT NULL,
    "title" VARCHAR(128) NOT NULL,
    "body" VARCHAR(512),
    "data" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT REFERENCES "user" ("id") ON DELETE SET NULL
);
COMMENT ON TABLE "notifications" IS 'Admin notifications (e.g. payment_received, pricing_updated).';
        CREATE TABLE IF NOT EXISTS "payments" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "amount_cents" INT NOT NULL,
    "currency" VARCHAR(8) NOT NULL  DEFAULT 'USD',
    "status" VARCHAR(32) NOT NULL  DEFAULT 'succeeded',
    "stripe_payment_intent_id" VARCHAR(128) NOT NULL UNIQUE,
    "stripe_checkout_session_id" VARCHAR(128),
    "metadata" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "payments" IS 'Stripe se aane wali har successful payment ka source of truth.';
        CREATE TABLE IF NOT EXISTS "pricing_settings" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "currency" VARCHAR(8) NOT NULL  DEFAULT 'USD',
    "call_cents_per_second" INT NOT NULL  DEFAULT 0,
    "text_cents_per_message" INT NOT NULL  DEFAULT 0,
    "updated_by_user_id" INT,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE "pricing_settings" IS 'Admin-set global fixed pricing (latest row active).';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "pricing_settings";
        DROP TABLE IF EXISTS "notifications";
        DROP TABLE IF EXISTS "payments";"""
