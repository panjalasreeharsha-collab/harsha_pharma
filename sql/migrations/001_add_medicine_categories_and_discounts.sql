-- Run this migration against the existing database configured by MYSQL_DATABASE.

-- Existing medicines remain uncategorized until an operator assigns their type.
ALTER TABLE medicines
    ADD COLUMN medicine_category ENUM('standard', 'generic') NULL;

-- Preserve historical invoice rates as their recorded MRP with no retroactive discount.
ALTER TABLE sale_items
    ADD COLUMN mrp DECIMAL(12, 2) NULL,
    ADD COLUMN discount_percent DECIMAL(5, 2) NULL;

UPDATE sale_items
SET mrp = unit_price,
    discount_percent = 0.00;

ALTER TABLE sale_items
    MODIFY COLUMN mrp DECIMAL(12, 2) NOT NULL,
    MODIFY COLUMN discount_percent DECIMAL(5, 2) NOT NULL;

-- After setting every existing medicine's category in the CLI, make the
-- category mandatory in the existing database by running:
-- ALTER TABLE medicines
--     MODIFY COLUMN medicine_category ENUM('standard', 'generic') NOT NULL;
