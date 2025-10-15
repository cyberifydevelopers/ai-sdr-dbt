from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "call_details" ALTER COLUMN "summary" TYPE TEXT USING "summary"::TEXT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "call_details" ALTER COLUMN "summary" TYPE JSONB USING "summary"::JSONB;"""
