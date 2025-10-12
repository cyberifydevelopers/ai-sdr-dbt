from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "payments" ADD "fee_cents" INT NOT NULL  DEFAULT 0;
        ALTER TABLE "payments" ADD "net_cents" INT NOT NULL  DEFAULT 0;
        ALTER TABLE "payments" ADD "stripe_balance_txn_id" VARCHAR(128);
        CREATE INDEX "idx_account_tra_stripe__da892f" ON "account_transactions" ("stripe_payment_intent_id");
        CREATE INDEX "idx_account_tra_kind_f52543" ON "account_transactions" ("kind");
        CREATE INDEX "idx_account_tra_currenc_7f8deb" ON "account_transactions" ("currency");
        CREATE INDEX "idx_account_tra_user_id_123038" ON "account_transactions" ("user_id");
        CREATE INDEX "idx_notificatio_kind_6da9e0" ON "notifications" ("kind");
        CREATE INDEX "idx_notificatio_user_id_daa173" ON "notifications" ("user_id");
        CREATE INDEX "idx_payments_stripe__e68757" ON "payments" ("stripe_balance_txn_id");
        CREATE INDEX "idx_payments_stripe__a1eff2" ON "payments" ("stripe_checkout_session_id");
        CREATE INDEX "idx_payments_currenc_3d9b8a" ON "payments" ("currency");
        CREATE INDEX "idx_payments_user_id_e10631" ON "payments" ("user_id");
        CREATE INDEX "idx_payments_status_c133d1" ON "payments" ("status");
        CREATE INDEX "idx_pricing_set_updated_e2932c" ON "pricing_settings" ("updated_by_user_id");
        CREATE INDEX "idx_pricing_set_currenc_b3c25d" ON "pricing_settings" ("currency");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_account_tra_user_id_123038";
        DROP INDEX IF EXISTS "idx_account_tra_currenc_7f8deb";
        DROP INDEX IF EXISTS "idx_account_tra_kind_f52543";
        DROP INDEX IF EXISTS "idx_account_tra_stripe__da892f";
        DROP INDEX IF EXISTS "idx_pricing_set_currenc_b3c25d";
        DROP INDEX IF EXISTS "idx_pricing_set_updated_e2932c";
        DROP INDEX IF EXISTS "idx_notificatio_user_id_daa173";
        DROP INDEX IF EXISTS "idx_notificatio_kind_6da9e0";
        DROP INDEX IF EXISTS "idx_payments_status_c133d1";
        DROP INDEX IF EXISTS "idx_payments_user_id_e10631";
        DROP INDEX IF EXISTS "idx_payments_currenc_3d9b8a";
        DROP INDEX IF EXISTS "idx_payments_stripe__a1eff2";
        DROP INDEX IF EXISTS "idx_payments_stripe__e68757";
        ALTER TABLE "payments" DROP COLUMN "fee_cents";
        ALTER TABLE "payments" DROP COLUMN "net_cents";
        ALTER TABLE "payments" DROP COLUMN "stripe_balance_txn_id";"""
