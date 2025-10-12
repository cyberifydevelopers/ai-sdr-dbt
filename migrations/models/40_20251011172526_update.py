from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "pricing_settings" RENAME COLUMN "call_cents_per_second" TO "call_millicents_per_second";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "pricing_settings" RENAME COLUMN "call_millicents_per_second" TO "call_cents_per_second";"""
