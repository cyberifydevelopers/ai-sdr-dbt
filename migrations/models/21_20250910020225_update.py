from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "form_submissions" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "first_name" VARCHAR(100),
    "last_name" VARCHAR(100),
    "email" VARCHAR(255),
    "phone" VARCHAR(50),
    "booking_time" TIMESTAMPTZ,
    "additional_details" JSONB,
    "raw_data" JSONB,
    "status" VARCHAR(9) NOT NULL  DEFAULT 'unbooked',
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "idx_form_submis_email_f27ec4" ON "form_submissions" ("email");
CREATE INDEX IF NOT EXISTS "idx_form_submis_phone_eaca5c" ON "form_submissions" ("phone");
COMMENT ON COLUMN "form_submissions"."status" IS 'UNBOOKED: unbooked\nBOOKED: booked\nCANCELLED: cancelled';
COMMENT ON TABLE "form_submissions" IS 'Stores raw form submissions + structured fields if available';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "form_submissions";"""
