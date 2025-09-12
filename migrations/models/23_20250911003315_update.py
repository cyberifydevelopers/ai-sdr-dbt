from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "form_submissions" ADD "user_id" INT;
        ALTER TABLE "form_submissions" ADD CONSTRAINT "fk_form_sub_user_be980056" FOREIGN KEY ("user_id") REFERENCES "user" ("id") ON DELETE CASCADE;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "form_submissions" DROP CONSTRAINT IF EXISTS "fk_form_sub_user_be980056";
        ALTER TABLE "form_submissions" DROP COLUMN "user_id";"""
