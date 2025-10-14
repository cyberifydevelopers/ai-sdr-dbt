from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "user" ADD "consent_to_call" BOOL NOT NULL  DEFAULT False;
        ALTER TABLE "user" ADD "consent_updated_at" TIMESTAMPTZ;
        ALTER TABLE "user" ADD "consent_note" TEXT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "user" DROP COLUMN "consent_to_call";
        ALTER TABLE "user" DROP COLUMN "consent_updated_at";
        ALTER TABLE "user" DROP COLUMN "consent_note";"""
