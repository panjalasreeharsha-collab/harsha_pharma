-- Run this file against the database configured by MYSQL_DATABASE in .env.

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

CREATE TABLE IF NOT EXISTS medicines (
    medicine_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    shop_id BIGINT UNSIGNED NOT NULL,
    brand_name VARCHAR(150) NOT NULL,
    generic_name VARCHAR(150) NOT NULL,
    manufacturer VARCHAR(150) NOT NULL,
    unit_type VARCHAR(50) NOT NULL,
    medicine_category ENUM('standard', 'generic') NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (medicine_id),
    KEY idx_medicines_shop (shop_id),
    KEY idx_medicines_brand_name (brand_name),
    CONSTRAINT fk_medicines_shop
        FOREIGN KEY (shop_id) REFERENCES shops (shop_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_medicines_brand_name CHECK (CHAR_LENGTH(TRIM(brand_name)) > 0),
    CONSTRAINT chk_medicines_unit_type CHECK (CHAR_LENGTH(TRIM(unit_type)) > 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS inventory_batches (
    batch_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    medicine_id BIGINT UNSIGNED NOT NULL,
    batch_number VARCHAR(100) NOT NULL,
    manufacturing_date DATE NULL,
    expiry_date DATE NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    mrp DECIMAL(12, 2) NOT NULL,
    purchase_price DECIMAL(12, 2) NOT NULL,
    gst_percent DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    discount_percent DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id),
    KEY idx_batches_fefo (medicine_id, expiry_date, batch_id),
    CONSTRAINT fk_batches_medicine
        FOREIGN KEY (medicine_id) REFERENCES medicines (medicine_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_batches_mrp CHECK (mrp >= 0),
    CONSTRAINT chk_batches_purchase_price CHECK (purchase_price >= 0),
    CONSTRAINT chk_batches_gst CHECK (gst_percent >= 0 AND gst_percent <= 100),
    CONSTRAINT chk_batches_discount CHECK (discount_percent >= 0 AND discount_percent <= 100)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sales_invoices (
    invoice_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    shop_id BIGINT UNSIGNED NOT NULL,
    shop_name VARCHAR(200) NOT NULL,
    sale_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    PRIMARY KEY (invoice_id),
    KEY idx_invoices_shop_date (shop_id, sale_date),
    KEY idx_invoices_sale_date (sale_date),
    CONSTRAINT fk_invoices_shop
        FOREIGN KEY (shop_id) REFERENCES shops (shop_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_invoices_total CHECK (total_amount >= 0),
    CONSTRAINT chk_invoices_shop_name CHECK (CHAR_LENGTH(TRIM(shop_name)) > 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sale_items (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    invoice_id BIGINT UNSIGNED NOT NULL,
    batch_id BIGINT UNSIGNED NOT NULL,
    quantity_sold INT UNSIGNED NOT NULL,
    mrp DECIMAL(12, 2) NOT NULL,
    discount_percent DECIMAL(5, 2) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (item_id),
    KEY idx_sale_items_invoice (invoice_id),
    KEY idx_sale_items_batch (batch_id),
    CONSTRAINT fk_sale_items_invoice
        FOREIGN KEY (invoice_id) REFERENCES sales_invoices (invoice_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_sale_items_batch
        FOREIGN KEY (batch_id) REFERENCES inventory_batches (batch_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_sale_items_quantity CHECK (quantity_sold > 0),
    CONSTRAINT chk_sale_items_mrp CHECK (mrp >= 0),
    CONSTRAINT chk_sale_items_discount CHECK (discount_percent >= 0 AND discount_percent <= 100),
    CONSTRAINT chk_sale_items_unit_price CHECK (unit_price >= 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS customer_invoices (
    invoice_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    shop_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(200) NOT NULL,
    customer_phone VARCHAR(30) NULL,
    customer_address VARCHAR(500) NULL,
    sale_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    subtotal DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    total_discount DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    total_tax DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    total_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    PRIMARY KEY (invoice_id),
    KEY idx_customer_invoices_shop_date (shop_id, sale_date),
    CONSTRAINT fk_customer_invoices_shop
        FOREIGN KEY (shop_id) REFERENCES shops (shop_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS customer_sale_items (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    invoice_id BIGINT UNSIGNED NOT NULL,
    batch_id BIGINT UNSIGNED NOT NULL,
    quantity_sold INT UNSIGNED NOT NULL,
    mrp DECIMAL(12, 2) NOT NULL,
    discount_percent DECIMAL(5, 2) NOT NULL,
    gst_percent DECIMAL(5, 2) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    tax_amount DECIMAL(12, 2) NOT NULL,
    final_unit_price DECIMAL(12, 2) NOT NULL,
    line_total DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (item_id),
    KEY idx_customer_sale_items_invoice (invoice_id),
    KEY idx_customer_sale_items_batch (batch_id),
    CONSTRAINT fk_customer_sale_items_invoice
        FOREIGN KEY (invoice_id) REFERENCES customer_invoices (invoice_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_customer_sale_items_batch
        FOREIGN KEY (batch_id) REFERENCES inventory_batches (batch_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;
