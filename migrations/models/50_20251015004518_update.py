from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "calllog" ALTER COLUMN "transcript" TYPE TEXT USING "transcript"::TEXT;
        ALTER TABLE "call_details" ALTER COLUMN "transcript" TYPE TEXT USING "transcript"::TEXT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "calllog" ALTER COLUMN "transcript" TYPE JSONB USING "transcript"::JSONB;
        ALTER TABLE "call_details" ALTER COLUMN "transcript" TYPE JSONB USING "transcript"::JSONB;"""
