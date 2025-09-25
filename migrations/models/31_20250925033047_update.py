from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "user" ADD "balance_cents" INT NOT NULL  DEFAULT 0;
        ALTER TABLE "user" ADD "stripe_customer_id" VARCHAR(64);
        ALTER TABLE "user" ADD "bonus_cents" INT NOT NULL  DEFAULT 0;
        ALTER TABLE "user" ADD "currency" VARCHAR(8) NOT NULL  DEFAULT 'USD';
        ALTER TABLE "user" ADD "per_minute_cents" INT NOT NULL  DEFAULT 10;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "user" DROP COLUMN "balance_cents";
        ALTER TABLE "user" DROP COLUMN "stripe_customer_id";
        ALTER TABLE "user" DROP COLUMN "bonus_cents";
        ALTER TABLE "user" DROP COLUMN "currency";
        ALTER TABLE "user" DROP COLUMN "per_minute_cents";"""
