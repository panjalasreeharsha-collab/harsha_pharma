-- Run against the configured application database after migration 001.
-- Existing medicines and invoices stay unassigned until the first shop signs up.
-- That first account claims all legacy rows in the same transaction.

CREATE TABLE IF NOT EXISTS shops (
    shop_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    shop_name VARCHAR(200) NOT NULL,
    owner_name VARCHAR(150) NOT NULL,
    email VARCHAR(254) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (shop_id),
    UNIQUE KEY uq_shops_email (email),
    CONSTRAINT chk_shops_name CHECK (CHAR_LENGTH(TRIM(shop_name)) > 0),
    CONSTRAINT chk_shops_owner CHECK (CHAR_LENGTH(TRIM(owner_name)) > 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS tenant_bootstrap (
    singleton_id TINYINT UNSIGNED NOT NULL,
    legacy_claimed BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (singleton_id),
    CONSTRAINT chk_tenant_bootstrap_singleton CHECK (singleton_id = 1)
) ENGINE=InnoDB;

INSERT IGNORE INTO tenant_bootstrap (singleton_id, legacy_claimed) VALUES (1, FALSE);

ALTER TABLE medicines
    ADD COLUMN shop_id BIGINT UNSIGNED NULL,
    ADD KEY idx_medicines_shop (shop_id),
    ADD CONSTRAINT fk_medicines_shop
        FOREIGN KEY (shop_id) REFERENCES shops (shop_id)
        ON UPDATE CASCADE ON DELETE RESTRICT;

ALTER TABLE sales_invoices
    ADD COLUMN shop_id BIGINT UNSIGNED NULL,
    ADD KEY idx_invoices_shop_date (shop_id, sale_date),
    ADD CONSTRAINT fk_invoices_shop
        FOREIGN KEY (shop_id) REFERENCES shops (shop_id)
        ON UPDATE CASCADE ON DELETE RESTRICT;
