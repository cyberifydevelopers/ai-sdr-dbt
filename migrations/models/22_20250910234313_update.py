from tortoise import BaseDBAsyncClient
import uuid


async def upgrade(db: BaseDBAsyncClient) -> str:
    # Step 1: Add column as nullable
    await db.execute_script('ALTER TABLE "user" ADD COLUMN "webhook_token" VARCHAR(64);')

    # Step 2: Backfill existing users with random tokens
    rows = await db.execute_query('SELECT id FROM "user";')
    for row in rows[1]:
        token = uuid.uuid4().hex
        await db.execute_script(
            f"UPDATE \"user\" SET webhook_token='{token}' WHERE id={row['id']};"
        )

    # Step 3: Enforce NOT NULL + UNIQUE constraint
    return """
        ALTER TABLE "user" ALTER COLUMN "webhook_token" SET NOT NULL;
        CREATE UNIQUE INDEX "uid_user_webhook_453520" ON "user" ("webhook_token");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uid_user_webhook_453520";
        ALTER TABLE "user" DROP COLUMN "webhook_token";
    """
