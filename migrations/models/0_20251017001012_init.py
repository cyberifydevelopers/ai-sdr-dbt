from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "user" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "email" VARCHAR(255) NOT NULL,
    "email_verified" BOOL NOT NULL  DEFAULT False,
    "password" VARCHAR(255) NOT NULL,
    "role" VARCHAR(255) NOT NULL  DEFAULT 'user',
    "profile_photo" VARCHAR(255),
    "twilio_account_sid" VARCHAR(64),
    "twilio_auth_token" VARCHAR(64),
    "webhook_token" VARCHAR(64) NOT NULL UNIQUE,
    "balance_cents" INT NOT NULL  DEFAULT 0,
    "bonus_cents" INT NOT NULL  DEFAULT 0,
    "currency" VARCHAR(8) NOT NULL  DEFAULT 'USD',
    "stripe_customer_id" VARCHAR(64),
    "per_minute_cents" INT NOT NULL  DEFAULT 10,
    "consent_to_call" BOOL NOT NULL  DEFAULT False,
    "consent_note" TEXT,
    "consent_updated_at" TIMESTAMPTZ
);
COMMENT ON COLUMN "user"."consent_to_call" IS 'User asserts they have consent to call uploaded leads';
COMMENT ON COLUMN "user"."consent_note" IS 'Optional context/description for consent';
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
    "call_ended_at" TIMESTAMPTZ,
    "call_duration" DOUBLE PRECISION,
    "customer_number" VARCHAR(100),
    "customer_name" VARCHAR(100),
    "call_id" VARCHAR(1000),
    "cost" DECIMAL(10,2),
    "call_ended_reason" VARCHAR(100),
    "is_transferred" BOOL   DEFAULT False,
    "criteria_satisfied" BOOL   DEFAULT False,
    "status" VARCHAR(50),
    "summary" TEXT,
    "transcript" TEXT,
    "analysis" JSONB,
    "recording_url" VARCHAR(500),
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_calllog_status_3d5ea2" ON "calllog" ("status");
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
    "last_called_at" TIMESTAMPTZ,
    "call_count" INT   DEFAULT 0,
    "other_data" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "origin" VARCHAR(32) NOT NULL  DEFAULT 'CSV',
    "origin_meta" VARCHAR(64),
    "file_id" INT REFERENCES "file" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_lead_salesfo_6e832f" ON "lead" ("salesforce_id");
CREATE INDEX IF NOT EXISTS "idx_lead_origin_346893" ON "lead" ("origin");
CREATE INDEX IF NOT EXISTS "idx_lead_file_id_a7e90f" ON "lead" ("file_id", "origin");
CREATE TABLE IF NOT EXISTS "documents" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "file_name" VARCHAR(255) NOT NULL,
    "vapi_file_id" VARCHAR(255),
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "campaign" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "selection_mode" VARCHAR(4) NOT NULL  DEFAULT 'ALL',
    "include_lead_ids" JSONB,
    "exclude_lead_ids" JSONB,
    "timezone" VARCHAR(64) NOT NULL  DEFAULT 'America/Los_Angeles',
    "days_of_week" JSONB,
    "daily_start" VARCHAR(5),
    "daily_end" VARCHAR(5),
    "start_at" TIMESTAMPTZ,
    "end_at" TIMESTAMPTZ,
    "calls_per_minute" INT NOT NULL  DEFAULT 10,
    "parallel_calls" INT NOT NULL  DEFAULT 2,
    "retry_on_busy" BOOL NOT NULL  DEFAULT True,
    "busy_retry_delay_minutes" INT NOT NULL  DEFAULT 15,
    "max_attempts" INT NOT NULL  DEFAULT 3,
    "status" VARCHAR(9) NOT NULL  DEFAULT 'draft',
    "last_tick_at" TIMESTAMPTZ,
    "calendar_ics" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "assistant_id" INT NOT NULL REFERENCES "assistant" ("id") ON DELETE CASCADE,
    "file_id" INT NOT NULL REFERENCES "file" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
COMMENT ON COLUMN "campaign"."selection_mode" IS 'ALL: ALL\nONLY: ONLY\nSKIP: SKIP';
COMMENT ON COLUMN "campaign"."status" IS 'DRAFT: draft\nSCHEDULED: scheduled\nRUNNING: running\nPAUSED: paused\nSTOPPED: stopped\nCOMPLETED: completed';
CREATE TABLE IF NOT EXISTS "campaignleadprogress" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "status" VARCHAR(32) NOT NULL  DEFAULT 'pending',
    "attempt_count" INT NOT NULL  DEFAULT 0,
    "last_attempt_at" TIMESTAMPTZ,
    "next_attempt_at" TIMESTAMPTZ,
    "last_call_id" VARCHAR(200),
    "last_ended_reason" VARCHAR(200),
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "campaign_id" INT NOT NULL REFERENCES "campaign" ("id") ON DELETE CASCADE,
    "lead_id" INT NOT NULL REFERENCES "lead" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_campaignlea_campaig_84fb87" UNIQUE ("campaign_id", "lead_id")
);
CREATE TABLE IF NOT EXISTS "integration_accounts" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "crm" VARCHAR(32) NOT NULL,
    "access_token" TEXT,
    "refresh_token" TEXT,
    "expires_at" TIMESTAMPTZ,
    "instance_url" VARCHAR(255),
    "scope" VARCHAR(512),
    "external_account_id" VARCHAR(128),
    "external_account_name" VARCHAR(255),
    "metadata" JSONB,
    "label" VARCHAR(255),
    "is_active" BOOL NOT NULL  DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_integration_user_id_402211" UNIQUE ("user_id", "crm")
);
COMMENT ON TABLE "integration_accounts" IS 'A connected CRM account for a given user.';
CREATE TABLE IF NOT EXISTS "integration_oauth_state" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "crm" VARCHAR(32) NOT NULL,
    "state" VARCHAR(128) NOT NULL UNIQUE,
    "redirect_to" VARCHAR(512),
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "integration_oauth_state" IS 'Temporary state row for OAuth ''state'' param so callbacks can identify user.';
CREATE TABLE IF NOT EXISTS "lead_external_refs" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "crm" VARCHAR(32) NOT NULL,
    "external_id" VARCHAR(128) NOT NULL,
    "external_url" VARCHAR(512),
    "last_synced_at" TIMESTAMPTZ,
    "last_error" TEXT,
    "payload_snapshot" JSONB,
    "lead_id" INT NOT NULL REFERENCES "lead" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_lead_extern_lead_id_5073af" UNIQUE ("lead_id", "crm")
);
COMMENT ON TABLE "lead_external_refs" IS 'Mapping of our Lead → external CRM Contact/Lead ID.';
CREATE TABLE IF NOT EXISTS "crm_sync_jobs" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "crm" VARCHAR(32) NOT NULL,
    "scope" VARCHAR(32) NOT NULL,
    "scope_ref" VARCHAR(64),
    "status" VARCHAR(16) NOT NULL  DEFAULT 'queued',
    "total" INT NOT NULL  DEFAULT 0,
    "success" INT NOT NULL  DEFAULT 0,
    "failed" INT NOT NULL  DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "finished_at" TIMESTAMPTZ,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "crm_sync_jobs" IS 'Optional: if you batch-push leads to CRMs, this tracks the job.';
CREATE TABLE IF NOT EXISTS "crm_sync_items" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "status" VARCHAR(16) NOT NULL  DEFAULT 'queued',
    "error" TEXT,
    "job_id" INT NOT NULL REFERENCES "crm_sync_jobs" ("id") ON DELETE CASCADE,
    "lead_id" INT NOT NULL REFERENCES "lead" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "appointments" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "assistant_id" VARCHAR(191),
    "source_call_id" VARCHAR(191),
    "source_transcript_id" VARCHAR(191),
    "title" VARCHAR(200) NOT NULL,
    "notes" TEXT,
    "phone" VARCHAR(32) NOT NULL,
    "location" VARCHAR(200),
    "timezone" VARCHAR(64) NOT NULL,
    "start_at" TIMESTAMPTZ NOT NULL,
    "end_at" TIMESTAMPTZ NOT NULL,
    "duration_minutes" INT NOT NULL,
    "status" VARCHAR(16) NOT NULL,
    "extraction_version" VARCHAR(32),
    "extraction_confidence" DOUBLE PRECISION,
    "extraction_raw" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_appointment_user_id_9aa4d2" UNIQUE ("user_id", "source_call_id")
);
CREATE INDEX IF NOT EXISTS "idx_appointment_source__762418" ON "appointments" ("source_call_id");
CREATE  INDEX "idx_appointment_user_id_6586e5" ON "appointments" ("user_id", "start_at");
CREATE  INDEX "idx_appointment_user_id_439b6d" ON "appointments" ("user_id", "phone");
CREATE  INDEX "idx_appointment_user_id_9aa4d2" ON "appointments" ("user_id", "source_call_id");
COMMENT ON COLUMN "appointments"."status" IS 'BOOKED: Booked\nFOLLOW_UP_NEEDED: Follow-up Needed';
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
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_form_submis_email_f27ec4" ON "form_submissions" ("email");
CREATE INDEX IF NOT EXISTS "idx_form_submis_phone_eaca5c" ON "form_submissions" ("phone");
COMMENT ON COLUMN "form_submissions"."status" IS 'UNBOOKED: unbooked\nBOOKED: booked\nCANCELLED: cancelled';
COMMENT ON TABLE "form_submissions" IS 'Stores raw form submissions + structured fields if available';
CREATE TABLE IF NOT EXISTS "facebook_integrations" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "fb_user_id" VARCHAR(64) NOT NULL,
    "user_access_token" TEXT NOT NULL,
    "token_expires_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_facebook_in_fb_user_78176f" ON "facebook_integrations" ("fb_user_id");
COMMENT ON TABLE "facebook_integrations" IS 'Stores the long-lived user access token per platform user.';
CREATE TABLE IF NOT EXISTS "facebook_pages" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "page_id" VARCHAR(64) NOT NULL,
    "name" VARCHAR(255),
    "page_access_token" TEXT NOT NULL,
    "subscribed" BOOL NOT NULL  DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_facebook_pa_page_id_d31aeb" ON "facebook_pages" ("page_id");
COMMENT ON TABLE "facebook_pages" IS 'Stores connected Pages and their page access tokens (needed to read leads & subscribe webhooks).';
CREATE TABLE IF NOT EXISTS "message_jobs" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "from_number" VARCHAR(32),
    "status" VARCHAR(24) NOT NULL  DEFAULT 'running',
    "total" INT NOT NULL  DEFAULT 0,
    "sent" INT NOT NULL  DEFAULT 0,
    "failed" INT NOT NULL  DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "assistant_id" INT REFERENCES "assistant" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "message_records" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "to_number" VARCHAR(32) NOT NULL,
    "from_number" VARCHAR(32) NOT NULL,
    "body" TEXT NOT NULL,
    "sid" VARCHAR(255),
    "success" BOOL NOT NULL  DEFAULT False,
    "error" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "appointment_id" UUID REFERENCES "appointments" ("id") ON DELETE CASCADE,
    "assistant_id" INT REFERENCES "assistant" ("id") ON DELETE CASCADE,
    "job_id" UUID NOT NULL REFERENCES "message_jobs" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_message_rec_user_id_b23ffe" ON "message_records" ("user_id", "created_at");
CREATE INDEX IF NOT EXISTS "idx_message_rec_job_id_122e7c" ON "message_records" ("job_id", "created_at");
CREATE TABLE IF NOT EXISTS "call_blocklist" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "phone_number" VARCHAR(32) NOT NULL,
    "reason" VARCHAR(255),
    "blocked_until" TIMESTAMPTZ,
    "hit_count" INT NOT NULL  DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "uid_call_blockl_phone_n_c5c6d7" UNIQUE ("phone_number")
);
CREATE INDEX IF NOT EXISTS "idx_call_blockl_phone_n_c5c6d7" ON "call_blocklist" ("phone_number");
CREATE TABLE IF NOT EXISTS "account_transactions" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "amount_cents" INT NOT NULL,
    "currency" VARCHAR(8) NOT NULL  DEFAULT 'USD',
    "kind" VARCHAR(32) NOT NULL,
    "description" VARCHAR(255),
    "stripe_payment_intent_id" VARCHAR(128),
    "metadata" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_account_tra_currenc_7f8deb" ON "account_transactions" ("currency");
CREATE INDEX IF NOT EXISTS "idx_account_tra_kind_f52543" ON "account_transactions" ("kind");
CREATE INDEX IF NOT EXISTS "idx_account_tra_stripe__da892f" ON "account_transactions" ("stripe_payment_intent_id");
CREATE INDEX IF NOT EXISTS "idx_account_tra_user_id_123038" ON "account_transactions" ("user_id");
COMMENT ON TABLE "account_transactions" IS 'Wallet-style ledger.';
CREATE TABLE IF NOT EXISTS "notifications" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "kind" VARCHAR(32) NOT NULL,
    "title" VARCHAR(128) NOT NULL,
    "body" VARCHAR(512),
    "data" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT REFERENCES "user" ("id") ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS "idx_notificatio_kind_6da9e0" ON "notifications" ("kind");
CREATE INDEX IF NOT EXISTS "idx_notificatio_user_id_daa173" ON "notifications" ("user_id");
COMMENT ON TABLE "notifications" IS 'Admin/user notifications (e.g. payment_received, pricing_updated).';
CREATE TABLE IF NOT EXISTS "payments" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "amount_cents" INT NOT NULL,
    "fee_cents" INT NOT NULL  DEFAULT 0,
    "net_cents" INT NOT NULL  DEFAULT 0,
    "currency" VARCHAR(8) NOT NULL  DEFAULT 'USD',
    "status" VARCHAR(32) NOT NULL  DEFAULT 'succeeded',
    "stripe_payment_intent_id" VARCHAR(128) NOT NULL UNIQUE,
    "stripe_checkout_session_id" VARCHAR(128),
    "stripe_balance_txn_id" VARCHAR(128),
    "metadata" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_payments_currenc_3d9b8a" ON "payments" ("currency");
CREATE INDEX IF NOT EXISTS "idx_payments_status_c133d1" ON "payments" ("status");
CREATE INDEX IF NOT EXISTS "idx_payments_stripe__a1eff2" ON "payments" ("stripe_checkout_session_id");
CREATE INDEX IF NOT EXISTS "idx_payments_stripe__e68757" ON "payments" ("stripe_balance_txn_id");
CREATE INDEX IF NOT EXISTS "idx_payments_user_id_e10631" ON "payments" ("user_id");
COMMENT ON TABLE "payments" IS 'Source of truth for successful Stripe payments.';
CREATE TABLE IF NOT EXISTS "pricing_settings" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "currency" VARCHAR(8) NOT NULL  DEFAULT 'USD',
    "call_millicents_per_second" INT NOT NULL  DEFAULT 0,
    "text_cents_per_message" INT NOT NULL  DEFAULT 0,
    "updated_by_user_id" INT,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "idx_pricing_set_currenc_b3c25d" ON "pricing_settings" ("currency");
CREATE INDEX IF NOT EXISTS "idx_pricing_set_updated_e2932c" ON "pricing_settings" ("updated_by_user_id");
COMMENT ON TABLE "pricing_settings" IS 'Admin-set global pricing (latest row is active).';
CREATE TABLE IF NOT EXISTS "calendar_accounts" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "provider" VARCHAR(32) NOT NULL,
    "external_account_id" VARCHAR(512) NOT NULL,
    "external_email" VARCHAR(320),
    "external_org_id" VARCHAR(512),
    "access_token" TEXT NOT NULL,
    "refresh_token" TEXT,
    "scope" TEXT,
    "expires_at" TIMESTAMPTZ,
    "primary_calendar_id" VARCHAR(512),
    "webhook_id" VARCHAR(256),
    "webhook_signing_key" VARCHAR(512),
    "api_version" VARCHAR(64),
    "metadata" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_calendar_ac_user_id_e63f83" UNIQUE ("user_id", "provider", "external_account_id")
);
CREATE INDEX IF NOT EXISTS "idx_calendar_ac_user_id_b86c83" ON "calendar_accounts" ("user_id", "provider");
CREATE INDEX IF NOT EXISTS "idx_calendar_ac_provide_484134" ON "calendar_accounts" ("provider", "external_account_id");
CREATE INDEX IF NOT EXISTS "idx_calendar_ac_provide_b9869f" ON "calendar_accounts" ("provider", "external_org_id");
CREATE INDEX IF NOT EXISTS "idx_calendar_ac_provide_748ee7" ON "calendar_accounts" ("provider", "webhook_id");
CREATE TABLE IF NOT EXISTS "appointment_external_links" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "provider" VARCHAR(32) NOT NULL,
    "external_event_id" VARCHAR(128) NOT NULL,
    "external_calendar_id" VARCHAR(128),
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "account_id" UUID NOT NULL REFERENCES "calendar_accounts" ("id") ON DELETE CASCADE,
    "appointment_id" UUID NOT NULL REFERENCES "appointments" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_appointment_provide_bac3df" UNIQUE ("provider", "external_event_id")
);
CREATE INDEX IF NOT EXISTS "idx_appointment_account_c82d40" ON "appointment_external_links" ("account_id", "external_event_id");
CREATE TABLE IF NOT EXISTS "call_details" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "call_id" VARCHAR(191),
    "assistant_id" VARCHAR(191),
    "phone_number_id" VARCHAR(191),
    "customer_number" VARCHAR(64),
    "customer_name" VARCHAR(191),
    "status" VARCHAR(50),
    "started_at" TIMESTAMPTZ,
    "ended_at" TIMESTAMPTZ,
    "duration" INT,
    "cost" DOUBLE PRECISION,
    "ended_reason" VARCHAR(128),
    "is_transferred" BOOL,
    "criteria_satisfied" BOOL,
    "summary" TEXT,
    "transcript" TEXT,
    "analysis" JSONB,
    "recording_url" VARCHAR(500),
    "vapi_created_at" TIMESTAMPTZ,
    "vapi_updated_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "last_synced_at" TIMESTAMPTZ,
    "call_log_id" INT REFERENCES "calllog" ("id") ON DELETE SET NULL,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_call_detail_call_id_566c8a" ON "call_details" ("call_id");
CREATE INDEX IF NOT EXISTS "idx_call_detail_custome_81b870" ON "call_details" ("customer_number");
CREATE INDEX IF NOT EXISTS "idx_call_detail_status_6721ac" ON "call_details" ("status");
CREATE  INDEX "idx_call_detail_user_id_4baaa7" ON "call_details" ("user_id", "call_id");
CREATE  INDEX "idx_call_detail_user_id_b923dc" ON "call_details" ("user_id", "status");
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
        """
