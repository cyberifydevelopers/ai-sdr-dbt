from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "appointments" ALTER COLUMN "status" SET DEFAULT 'scheduled';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "appointments" ALTER COLUMN "status" DROP DEFAULT;"""
