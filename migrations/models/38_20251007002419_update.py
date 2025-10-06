from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "appointments" ADD "email" VARCHAR(320);
        CREATE TABLE IF NOT EXISTS "email_credentials" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "provider" VARCHAR(64),
    "api_key" VARCHAR(255),
    "smtp_host" VARCHAR(255),
    "smtp_port" INT,
    "smtp_username" VARCHAR(255),
    "smtp_password" VARCHAR(255),
    "smtp_use_tls" BOOL NOT NULL  DEFAULT True,
    "from_email" VARCHAR(320),
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_email_crede_user_id_46cb4f" ON "email_credentials" ("user_id", "provider");
COMMENT ON TABLE "email_credentials" IS 'Per-user SMTP (or API) credentials.';
        CREATE TABLE IF NOT EXISTS "email_jobs" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "from_email" VARCHAR(320),
    "subject_template" VARCHAR(255),
    "status" VARCHAR(24) NOT NULL  DEFAULT 'running',
    "total" INT NOT NULL  DEFAULT 0,
    "sent" INT NOT NULL  DEFAULT 0,
    "failed" INT NOT NULL  DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "assistant_id" INT REFERENCES "assistant" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "email_jobs" IS 'Mirrors MessageJob (SMS) — tracks bulk email runs and daemon ticks.';
        CREATE TABLE IF NOT EXISTS "email_records" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "to_email" VARCHAR(320) NOT NULL,
    "from_email" VARCHAR(320),
    "subject" VARCHAR(255),
    "body" TEXT NOT NULL,
    "provider_message_id" VARCHAR(255),
    "success" BOOL NOT NULL  DEFAULT False,
    "error" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "appointment_id" UUID REFERENCES "appointments" ("id") ON DELETE CASCADE,
    "assistant_id" INT REFERENCES "assistant" ("id") ON DELETE CASCADE,
    "job_id" UUID REFERENCES "email_jobs" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_email_recor_user_id_49db87" ON "email_records" ("user_id", "created_at");
CREATE INDEX IF NOT EXISTS "idx_email_recor_job_id_05de70" ON "email_records" ("job_id", "created_at");
COMMENT ON TABLE "email_records" IS 'Each email attempt/result with full audit.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "appointments" DROP COLUMN "email";
        DROP TABLE IF EXISTS "email_records";
        DROP TABLE IF EXISTS "email_credentials";
        DROP TABLE IF EXISTS "email_jobs";"""
