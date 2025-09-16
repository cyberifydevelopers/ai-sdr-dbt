from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
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
COMMENT ON TABLE "facebook_pages" IS 'Stores connected Pages and their page access tokens (needed to read leads & subscribe webhooks).';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "facebook_pages";
        DROP TABLE IF EXISTS "facebook_integrations";"""
