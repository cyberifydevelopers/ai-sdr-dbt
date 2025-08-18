from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "user" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "email" VARCHAR(255) NOT NULL,
    "email_verified" BOOL NOT NULL  DEFAULT False,
    "password" VARCHAR(255) NOT NULL,
    "role" VARCHAR(255) NOT NULL  DEFAULT 'user'
);
CREATE TABLE IF NOT EXISTS "codes" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "type" VARCHAR(255) NOT NULL,
    "value" TEXT NOT NULL,
    "expires_at" DATE NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS "purchasednumber" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "phone_number" VARCHAR(20) NOT NULL,
    "friendly_name" VARCHAR(255),
    "region" VARCHAR(255),
    "postal_code" VARCHAR(20),
    "iso_country" VARCHAR(10),
    "last_month_payment" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "attached_assistant" INT,
    "vapi_phone_uuid" VARCHAR(255),
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "assistant" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "vapi_assistant_id" VARCHAR(255),
    "name" VARCHAR(255) NOT NULL,
    "provider" VARCHAR(255) NOT NULL,
    "first_message" VARCHAR(255) NOT NULL,
    "model" VARCHAR(255) NOT NULL,
    "systemPrompt" TEXT NOT NULL,
    "knowledgeBase" JSONB,
    "leadsfile" JSONB,
    "temperature" DOUBLE PRECISION,
    "maxTokens" INT,
    "transcribe_provider" VARCHAR(255),
    "transcribe_language" VARCHAR(255),
    "transcribe_model" VARCHAR(255),
    "voice_provider" VARCHAR(255),
    "voice" VARCHAR(255),
    "forwardingPhoneNumber" VARCHAR(255),
    "endCallPhrases" JSONB,
    "attached_Number" VARCHAR(255),
    "vapi_phone_uuid" VARCHAR(255),
    "draft" BOOL   DEFAULT False,
    "assistant_toggle" BOOL,
    "success_evalution" TEXT,
    "category" TEXT,
    "voice_model" TEXT,
    "languages" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "speed" DOUBLE PRECISION   DEFAULT 1,
    "stability" DOUBLE PRECISION   DEFAULT 0.5,
    "similarityBoost" DOUBLE PRECISION   DEFAULT 0.75,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "calllog" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "lead_id" INT,
    "call_started_at" TIMESTAMPTZ,
    "customer_number" VARCHAR(100),
    "customer_name" VARCHAR(100),
    "call_id" VARCHAR(1000),
    "cost" DECIMAL(10,2),
    "call_ended_at" TIMESTAMPTZ,
    "call_ended_reason" VARCHAR(100),
    "call_duration" DOUBLE PRECISION,
    "is_transferred" BOOL   DEFAULT False,
    "status" VARCHAR(100),
    "criteria_satisfied" BOOL   DEFAULT False,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "file" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "alphanumeric_id" VARCHAR(8)  UNIQUE,
    "name" VARCHAR(255) NOT NULL,
    "url" TEXT,
    "sync_enable" BOOL   DEFAULT False,
    "sync_frequency" INT,
    "is_syncing" BOOL   DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "lead" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "first_name" VARCHAR(255) NOT NULL,
    "last_name" VARCHAR(255) NOT NULL,
    "email" VARCHAR(255) NOT NULL,
    "add_date" DATE NOT NULL,
    "salesforce_id" VARCHAR(255),
    "mobile" VARCHAR(255) NOT NULL,
    "state" VARCHAR(255),
    "timezone" VARCHAR(255),
    "dnc" BOOL NOT NULL  DEFAULT False,
    "submit_for_approval" BOOL NOT NULL  DEFAULT False,
    "other_data" JSONB,
    "last_called_at" TIMESTAMPTZ,
    "call_count" INT   DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "file_id" INT REFERENCES "file" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "documents" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "file_name" VARCHAR(255) NOT NULL,
    "vapi_file_id" VARCHAR(255),
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
