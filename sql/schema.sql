-- Run this file against the database configured by MYSQL_DATABASE in .env.

CREATE TABLE IF NOT EXISTS medicines (
    medicine_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    brand_name VARCHAR(150) NOT NULL,
    generic_name VARCHAR(150) NOT NULL,
    manufacturer VARCHAR(150) NOT NULL,
    unit_type VARCHAR(50) NOT NULL,
    medicine_category ENUM('standard', 'generic') NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (medicine_id),
    KEY idx_medicines_brand_name (brand_name),
    CONSTRAINT chk_medicines_brand_name CHECK (CHAR_LENGTH(TRIM(brand_name)) > 0),
    CONSTRAINT chk_medicines_unit_type CHECK (CHAR_LENGTH(TRIM(unit_type)) > 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS inventory_batches (
    batch_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    medicine_id BIGINT UNSIGNED NOT NULL,
    batch_number VARCHAR(100) NOT NULL,
    expiry_date DATE NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    mrp DECIMAL(12, 2) NOT NULL,
    purchase_price DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id),
    KEY idx_batches_fefo (medicine_id, expiry_date, batch_id),
    CONSTRAINT fk_batches_medicine
        FOREIGN KEY (medicine_id) REFERENCES medicines (medicine_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_batches_mrp CHECK (mrp >= 0),
    CONSTRAINT chk_batches_purchase_price CHECK (purchase_price >= 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sales_invoices (
    invoice_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    shop_name VARCHAR(200) NOT NULL,
    sale_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    PRIMARY KEY (invoice_id),
    KEY idx_invoices_sale_date (sale_date),
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
