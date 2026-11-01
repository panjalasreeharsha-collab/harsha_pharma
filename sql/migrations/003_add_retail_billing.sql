-- Run once against the existing application database after migrations 001 and 002.

ALTER TABLE inventory_batches
    ADD COLUMN manufacturing_date DATE NULL,
    ADD COLUMN gst_percent DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    ADD COLUMN discount_percent DECIMAL(5, 2) NOT NULL DEFAULT 0.00;

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
