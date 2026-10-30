# Medical Stock Dispatch and Billing

A Python CLI backed by MySQL. Dispatches consume unexpired inventory batches in
First Expired, First Out (FEFO) order. Invoice creation, sale-item insertion,
and stock deduction are committed or rolled back together.

## Setup

1. Create the database named by `MYSQL_DATABASE` in `.env`, if it does not
   already exist. Run `sql/schema.sql` against that database (the MySQL user
   needs permission to create tables):

   ```sh
   mysql -u root -p --database=medical_dispatch < sql/schema.sql
   ```

   Replace `medical_dispatch` with the value of `MYSQL_DATABASE`.

2. Create and activate a virtual environment, then install dependencies:

   ```sh
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and set the MySQL connection values. Do not
   commit `.env`.
4. For an existing database, run
   `sql/migrations/001_add_medicine_categories_and_discounts.sql` once. Use CLI
   option 5 to categorize every existing medicine as standard or generic;
   dispatch is blocked for medicines that are not categorized. Once all
   medicines have a category, the optional `ALTER TABLE` statement at the end
   of the migration can be run to enforce the category in MySQL as well.
   Existing sale items retain their recorded rate and receive no retroactive
   discount.
5. Start the CLI:

   ```sh
   python app.py
   ```

## Dispatch behavior

- Add medicines before adding their stock batches.
- Dispatch cart entries use `{"medicine_id": 1, "quantity": 10}`.
- Every medicine must be categorized as standard (30% off batch MRP) or generic
  (70% off batch MRP). This applies to all unit types.
- The receipt shows batch MRP, discount percentage, discounted rate, and line
  amount. Sale items retain MRP and discount snapshots for invoice history.
- If a requested quantity spans batches, separate receipt lines are created
  using each batch's MRP and the medicine's discount.
- Expired batches are excluded from dispatch and availability totals.
- Receipts are printed and saved as `receipts/invoice_<invoice_id>.txt`.
- If stock is insufficient, the invoice, sale lines, and all stock changes for
  that dispatch are rolled back.

For application code, call
`services.billing_service.process_dispatch_bill(shop_name, cart_items)`.
