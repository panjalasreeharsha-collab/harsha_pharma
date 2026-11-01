"""Authenticated Flask web application for medical stock dispatch."""

from __future__ import annotations

import hmac
import os
import re
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable
from urllib.parse import urlsplit

import mysql.connector
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    Response,
    url_for,
)

from services.account_service import authenticate_shop, create_shop_account
from services.billing_service import get_invoice_receipt, process_dispatch_bill
from services.customer_billing_service import (
    create_customer_invoice,
    get_customer_invoice,
)
from services.inventory_service import (
    add_batch_stock,
    add_medicine,
    get_stock_levels,
    set_medicine_category,
)


def _required_setting(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name} must be set in the environment before starting the web app."
        )
    return value


app = Flask(__name__)
app.config.update(
    SECRET_KEY=_required_setting("FLASK_SECRET_KEY"),
    MAX_CONTENT_LENGTH=64 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("RENDER", "").lower() == "true",
)

def _shop_id() -> int:
    shop_id = session.get("shop_id")
    if isinstance(shop_id, bool) or not isinstance(shop_id, int) or shop_id <= 0:
        abort(401)
    return shop_id


def _safe_next_url(value: str) -> str | None:
    parsed = urlsplit(value)
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
        or "\\" in value
        or parsed.fragment
    ):
        return None
    return value


@app.before_request
def protect_application() -> Response | None:
    """Require an account session and a valid token for every form submission."""
    public_endpoints = {"healthz", "login", "signup", "static"}
    if request.endpoint not in public_endpoints and "shop_id" not in session:
        return redirect(url_for("login", next=request.full_path))

    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        submitted_token = request.form.get("csrf_token", "")
        session_token = session.get("_csrf_token", "")
        if not session_token or not hmac.compare_digest(
            submitted_token, session_token
        ):
            abort(400, description="The form expired. Reload the page and try again.")


@app.context_processor
def provide_csrf_token() -> dict[str, Callable[[], str]]:
    def csrf_token() -> str:
        token = session.get("_csrf_token")
        if token is None:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    return {
        "csrf_token": csrf_token,
        "current_shop_name": lambda: session.get("shop_name", ""),
    }


@app.errorhandler(401)
def authentication_required(_error: object) -> tuple[str, int]:
    return "Sign in to access this page.", 401


@app.errorhandler(400)
def bad_request(error: object) -> tuple[str, int]:
    description = getattr(error, "description", "Invalid request.")
    return render_template("error.html", message=description), 400


@app.errorhandler(503)
def service_unavailable(error: object) -> tuple[str, int]:
    description = getattr(
        error, "description", "The service is temporarily unavailable."
    )
    return render_template("error.html", message=description), 503


@app.errorhandler(500)
def internal_server_error(_error: object) -> tuple[str, int]:
    app.logger.exception("Unhandled error while processing a web request")
    return render_template(
        "error.html", message="An unexpected error occurred. Check the server logs."
    ), 500


def _handle_operation(action: Callable[[], object], success_message: str) -> None:
    try:
        action()
        flash(success_message, "success")
    except ValueError as exc:
        flash(str(exc), "error")
    except mysql.connector.Error:
        app.logger.exception("Database operation failed")
        flash("The database operation failed. Check the server logs.", "error")
    except RuntimeError as exc:
        app.logger.exception("Application operation failed")
        flash(str(exc), "error")


@app.get("/healthz")
def healthz() -> Response | tuple[str, int]:
    """Provide an unauthenticated database-aware health check for Render."""
    from config.database import get_connection

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        return "ok", 200
    except mysql.connector.Error:
        app.logger.exception("Database health check failed")
        return "database unavailable", 503
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


@app.route("/signup", methods=["GET", "POST"])
def signup() -> str | Response:
    if "shop_id" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        try:
            account = create_shop_account(
                request.form.get("shop_name", ""),
                request.form.get("owner_name", ""),
                request.form.get("email", ""),
                request.form.get("password", ""),
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("signup.html")
        except mysql.connector.Error:
            app.logger.exception("Shop signup failed")
            flash("We could not create the account. Check the email and try again.", "error")
            return render_template("signup.html")
        except RuntimeError as exc:
            app.logger.exception("Shop signup is not configured")
            abort(503, description=str(exc))

        session.clear()
        session["shop_id"] = account["shop_id"]
        session["shop_name"] = account["shop_name"]
        session["email"] = account["email"]
        flash("Your shop account is ready.", "success")
        return redirect(url_for("index"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login() -> str | Response:
    if "shop_id" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        try:
            account = authenticate_shop(
                request.form.get("email", ""),
                request.form.get("password", ""),
            )
        except mysql.connector.Error:
            app.logger.exception("Shop sign-in failed")
            abort(503, description="Could not reach the account database.")
        if account is None:
            flash("Email or password is incorrect.", "error")
            return render_template("login.html"), 401

        next_url = _safe_next_url(
            request.form.get("next", "") or session.get("next_url", "")
        )
        session.clear()
        session["shop_id"] = account["shop_id"]
        session["shop_name"] = account["shop_name"]
        session["email"] = account["email"]
        if next_url is not None:
            return redirect(next_url)
        return redirect(url_for("index"))

    next_url = _safe_next_url(request.args.get("next", ""))
    if next_url is not None:
        session["next_url"] = next_url
    return render_template("login.html")


@app.post("/logout")
def logout() -> Response:
    session.clear()
    flash("You have signed out.", "success")
    return redirect(url_for("login"))


@app.get("/")
def index() -> str:
    try:
        stock_levels = get_stock_levels(_shop_id())
    except mysql.connector.Error:
        app.logger.exception("Could not load inventory")
        abort(503, description="Database unavailable. Check the server logs.")
    return render_template("index.html", stock_levels=stock_levels)


@app.route("/medicines/new", methods=["GET", "POST"])
def medicine_create() -> str:
    if request.method == "POST":
        def create() -> int:
            return add_medicine(
                _shop_id(),
                request.form.get("brand_name", ""),
                request.form.get("generic_name", ""),
                request.form.get("manufacturer", ""),
                request.form.get("unit_type", ""),
                request.form.get("medicine_category", ""),
            )

        _handle_operation(create, "Medicine added.")
        return redirect(url_for("index"))
    return render_template("medicine_form.html")


@app.route("/stock/new", methods=["GET", "POST"])
def stock_create() -> str:
    if request.method == "POST":
        def create() -> int:
            try:
                expiry_date = date.fromisoformat(request.form.get("expiry_date", ""))
                quantity = int(request.form.get("quantity", ""))
                mrp = Decimal(request.form.get("mrp", ""))
                purchase_price = Decimal(request.form.get("purchase_price", ""))
                manufacturing_date_text = request.form.get("manufacturing_date", "")
                manufacturing_date = (
                    date.fromisoformat(manufacturing_date_text)
                    if manufacturing_date_text
                    else None
                )
                gst_percent = Decimal(request.form.get("gst_percent", ""))
                discount_percent = Decimal(request.form.get("discount_percent", ""))
                medicine_id = int(request.form.get("medicine_id", ""))
            except (InvalidOperation, ValueError):
                raise ValueError("Enter valid medicine, dates, quantity, and prices.")
            if any(
                not value.is_finite()
                for value in (mrp, purchase_price, gst_percent, discount_percent)
            ):
                raise ValueError("Prices and percentages must be finite numbers.")
            return add_batch_stock(
                _shop_id(),
                medicine_id,
                request.form.get("batch_number", ""),
                expiry_date,
                quantity,
                mrp,
                purchase_price,
                manufacturing_date,
                gst_percent,
                discount_percent,
            )

        _handle_operation(create, "Stock batch added.")
        return redirect(url_for("index"))

    try:
        stock_levels = get_stock_levels(_shop_id())
    except mysql.connector.Error:
        app.logger.exception("Could not load medicines for stock entry")
        abort(503, description="Database unavailable. Check the server logs.")
    medicines = {int(row["medicine_id"]): row for row in stock_levels}
    return render_template("stock_form.html", medicines=medicines.values())


@app.route("/medicines/category", methods=["GET", "POST"])
def category_update() -> str:
    if request.method == "POST":
        def update() -> None:
            try:
                medicine_id = int(request.form.get("medicine_id", ""))
            except ValueError:
                raise ValueError("Enter a valid medicine ID.")
            set_medicine_category(
                _shop_id(), medicine_id, request.form.get("medicine_category", "")
            )

        _handle_operation(update, "Medicine category updated.")
        return redirect(url_for("index"))

    try:
        stock_levels = get_stock_levels(_shop_id())
    except mysql.connector.Error:
        app.logger.exception("Could not load medicines for category update")
        abort(503, description="Database unavailable. Check the server logs.")
    medicines = {int(row["medicine_id"]): row for row in stock_levels}
    return render_template("category_form.html", medicines=medicines.values())


@app.route("/dispatch", methods=["GET", "POST"])
def dispatch() -> str:
    try:
        stock_levels = get_stock_levels(_shop_id())
    except mysql.connector.Error:
        app.logger.exception("Could not load medicines for dispatch")
        abort(503, description="Database unavailable. Check the server logs.")

    medicines = {
        int(row["medicine_id"]): row
        for row in stock_levels
        if row["medicine_category"] in {"standard", "generic"}
    }

    if request.method == "POST":
        def create_bill() -> str:
            medicine_ids = request.form.getlist("medicine_id")
            quantities = request.form.getlist("quantity")
            if len(medicine_ids) != len(quantities):
                raise ValueError("Each medicine must have a matching quantity.")

            cart_items = []
            for medicine_id_text, quantity_text in zip(medicine_ids, quantities):
                if not medicine_id_text and not quantity_text:
                    continue
                try:
                    cart_items.append(
                        {
                            "medicine_id": int(medicine_id_text),
                            "quantity": int(quantity_text),
                        }
                    )
                except ValueError:
                    raise ValueError("Enter a valid medicine ID and whole quantity.")

            receipt = process_dispatch_bill(
                _shop_id(), request.form.get("shop_name", ""), cart_items
            )
            match = re.search(r"^Invoice ID : (\d+)$", receipt, re.MULTILINE)
            if match is None:
                raise RuntimeError("The generated receipt did not contain an invoice ID.")
            return match.group(1)

        try:
            invoice_id = create_bill()
            return redirect(url_for("invoice_view", invoice_id=invoice_id))
        except ValueError as exc:
            flash(str(exc), "error")
        except mysql.connector.Error:
            app.logger.exception("Could not process dispatch bill")
            flash("The dispatch failed because of a database error.", "error")
        except RuntimeError as exc:
            app.logger.exception("Could not create dispatch receipt")
            flash(str(exc), "error")

    return render_template("dispatch_form.html", medicines=medicines.values())


@app.route("/sales/new", methods=["GET", "POST"])
def customer_sale() -> str | Response:
    try:
        stock_levels = get_stock_levels(_shop_id())
    except mysql.connector.Error:
        app.logger.exception("Could not load medicines for customer billing")
        abort(503, description="Database unavailable. Check the server logs.")

    medicines = {
        int(row["medicine_id"]): row
        for row in stock_levels
        if row["batch_id"] is not None
        and int(row["quantity"]) > 0
        and not row["is_expired"]
    }

    if request.method == "POST":
        try:
            medicine_ids = request.form.getlist("medicine_id")
            quantities = request.form.getlist("quantity")
            if len(medicine_ids) != len(quantities):
                raise ValueError("Each medicine must have a matching quantity.")
            cart_items = []
            for medicine_id_text, quantity_text in zip(medicine_ids, quantities):
                if not medicine_id_text and not quantity_text:
                    continue
                try:
                    cart_items.append(
                        {
                            "medicine_id": int(medicine_id_text),
                            "quantity": int(quantity_text),
                        }
                    )
                except ValueError as exc:
                    raise ValueError(
                        "Choose a medicine and enter a whole-number quantity."
                    ) from exc
            invoice_id = create_customer_invoice(
                _shop_id(),
                request.form.get("customer_name", ""),
                request.form.get("customer_phone", ""),
                request.form.get("customer_address", ""),
                cart_items,
            )
            return redirect(url_for("customer_invoice_view", invoice_id=invoice_id))
        except ValueError as exc:
            flash(str(exc), "error")
        except mysql.connector.Error:
            app.logger.exception("Could not create customer invoice")
            flash("The customer bill failed because of a database error.", "error")
        except RuntimeError as exc:
            app.logger.exception("Could not complete customer sale")
            flash(str(exc), "error")

    return render_template("customer_sale_form.html", medicines=medicines.values())


@app.get("/invoices/<int:invoice_id>")
def invoice_view(invoice_id: int) -> str:
    try:
        receipt = get_invoice_receipt(invoice_id, _shop_id())
    except ValueError:
        abort(404)
    except mysql.connector.Error:
        app.logger.exception("Could not load invoice %s", invoice_id)
        abort(503, description="Database unavailable. Check the server logs.")
    return render_template("receipt.html", receipt=receipt)


@app.get("/customer-invoices/<int:invoice_id>")
def customer_invoice_view(invoice_id: int) -> str:
    try:
        invoice = get_customer_invoice(invoice_id, _shop_id())
    except ValueError:
        abort(404)
    except mysql.connector.Error:
        app.logger.exception("Could not load customer invoice %s", invoice_id)
        abort(503, description="Database unavailable. Check the server logs.")
    return render_template("customer_receipt.html", invoice=invoice)
