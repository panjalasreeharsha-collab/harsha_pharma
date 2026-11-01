# Medical Stock Dispatch and Billing

A Python application backed by MySQL, with a local CLI and an authenticated
browser interface. Dispatches consume unexpired inventory batches in First
Expired, First Out (FEFO) order. Invoice creation, sale-item insertion, and
stock deduction are committed or rolled back together.

## Setup

1. Create the database named by `MYSQL_DATABASE` in `.env`, if it does not
   already exist. Run `sql/schema.sql` against that database (the MySQL user
   needs permission to create tables):

   ```sh
   mysql -u your_mysql_user -p --database=your_database_name < sql/schema.sql
   ```

   Replace the user and database placeholders with your MySQL values.

2. Create and activate a virtual environment, then install dependencies:

   ```sh
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and set the MySQL connection values. To use
   the web app, also set a randomly generated `FLASK_SECRET_KEY`. Do not
   commit `.env`; shop owners create their own accounts on the signup page.
4. For an existing database without the category/discount columns, run
   `sql/migrations/001_add_medicine_categories_and_discounts.sql` once.
   Then run `sql/migrations/002_add_shop_accounts.sql` once to enable
   independent shop accounts. The first shop to sign up claims existing
   unassigned medicines and invoices; subsequent shops only see their own
   records. Existing sale items retain their recorded rate and receive no
   retroactive discount.
5. To use the local CLI, run `python app.py --help` to list the available
   commands. For example:

   ```sh
   python app.py view-stock
   ```

   Use `python app.py add-medicine`, `python app.py add-stock`,
   `python app.py set-category`, and `python app.py issue-bill` for the other
   operations. Each command prompts for your shop email and password. Create
   the account first through the signup page. To run that page locally, start
   the development server with `flask --app web_app run` and open
   `http://127.0.0.1:5000`.

## Deploy as a Render web service

The CLI in `app.py` is interactive and is not a web server. The Render web
service uses the Flask WSGI application in `web_app.py` instead.

- Connect this repository to Render as a **Web Service**.
- Set the build command to `pip install -r requirements.txt`.
- Set the start command to:

  ```sh
  gunicorn web_app:app --bind 0.0.0.0:$PORT
  ```

- In Render's environment settings, configure `MYSQL_HOST`, `MYSQL_PORT`,
  `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, and `FLASK_SECRET_KEY`.
  Use the connection details from your hosted MySQL provider; do not upload
  `database.env` or `.env`.
- If Render asks for a root directory, use the repository root containing
  `render.yaml`, `requirements.txt`, and `web_app.py`.
- Set the health check path to `/healthz`. It checks that MySQL is reachable.
- Make sure the configured remote database already has the tables from
  `sql/schema.sql` (or both required migrations for an existing database) and
  accepts connections from Render.

Each pharmacy signs in with its own email and password. Passwords are stored
as hashes, shop inventory and invoices are isolated by account, and forms use
CSRF protection. Use the service over HTTPS.

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
