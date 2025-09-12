from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "form_submissions";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
