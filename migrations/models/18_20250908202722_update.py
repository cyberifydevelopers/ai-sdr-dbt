from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "chat_thread";
        DROP TABLE IF EXISTS "chat_message";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
