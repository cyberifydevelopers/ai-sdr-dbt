from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "appointments";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
