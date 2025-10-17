from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "appointments" ALTER COLUMN "duration_minutes" TYPE DOUBLE PRECISION USING "duration_minutes"::DOUBLE PRECISION;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "appointments" ALTER COLUMN "duration_minutes" TYPE INT USING "duration_minutes"::INT;"""
