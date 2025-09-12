from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_appointment_start_a_9142e1";
        ALTER TABLE "appointments" ADD "user_id" INT;
        ALTER TABLE "appointments" ADD CONSTRAINT "fk_appointm_user_0d796e64" FOREIGN KEY ("user_id") REFERENCES "user" ("id") ON DELETE CASCADE;
        CREATE INDEX "idx_appointment_user_id_6586e5" ON "appointments" ("user_id", "start_at");
        CREATE INDEX "idx_appointment_user_id_439b6d" ON "appointments" ("user_id", "phone");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_appointment_user_id_439b6d";
        DROP INDEX IF EXISTS "idx_appointment_user_id_6586e5";
        ALTER TABLE "appointments" DROP CONSTRAINT IF EXISTS "fk_appointm_user_0d796e64";
        ALTER TABLE "appointments" DROP COLUMN "user_id";
        CREATE INDEX "idx_appointment_start_a_9142e1" ON "appointments" ("start_at", "phone");"""
