"""Command-line interface for medical stock and dispatch billing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from getpass import getpass

import typer
from mysql.connector import Error as MySQLConnectorError

from services.account_service import authenticate_shop
from services.billing_service import CartItem, process_dispatch_bill
from services.inventory_service import (
    add_batch_stock,
    add_medicine,
    get_stock_levels,
    set_medicine_category,
)

# Expose the app attribute for deployment and CLI entrypoints
app = typer.Typer(help="Medical Stock Dispatch and Billing CLI")


def _authenticate_cli_shop() -> int:
    email = typer.prompt("Shop email")
    password = getpass("Password: ")
    account = authenticate_shop(email, password)
    if account is None:
        typer.echo("Email or password is incorrect.", err=True)
        raise typer.Exit(code=1)
    return int(account["shop_id"])


def _read_positive_integer(prompt: str) -> int:
    while True:
        try:
            value = int(input(prompt).strip())
            if value <= 0:
                raise ValueError
            return value
        except ValueError:
            typer.echo("Enter a positive whole number.")


def _read_price(prompt: str) -> Decimal:
    while True:
        try:
            value = Decimal(input(prompt).strip())
            if not value.is_finite() or value < 0:
                raise InvalidOperation
            return value.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            typer.echo("Enter a valid non-negative amount.")


@app.command("add-medicine")
def _add_medicine() -> None:
    """Add a new medicine to the inventory."""
    try:
        shop_id = _authenticate_cli_shop()
        medicine_category = input("Category (standard/generic): ").strip().lower()
        medicine_id = add_medicine(
            shop_id,
            input("Brand name: ").strip(),
            input("Generic name: ").strip(),
            input("Manufacturer: ").strip(),
            input("Unit type (tablet, syrup, etc.): ").strip(),
            medicine_category,
        )
        typer.echo(
            f"Medicine added with ID {medicine_id} "
            f"(category: {medicine_category})."
        )
    except (ValueError, RuntimeError, MySQLConnectorError) as exc:
        typer.echo(f"Error: {exc}")


@app.command("set-category")
def _set_category() -> None:
    """Update the category of an existing medicine."""
    try:
        shop_id = _authenticate_cli_shop()
        medicine_id = _read_positive_integer("Medicine ID: ")
        category = input("Category (standard/generic): ").strip().lower()
        set_medicine_category(shop_id, medicine_id, category)
        typer.echo(f"Medicine {medicine_id} category updated to {category}.")
    except (ValueError, RuntimeError, MySQLConnectorError) as exc:
        typer.echo(f"Error: {exc}")


@app.command("add-stock")
def _add_stock() -> None:
    """Add a new stock batch for a medicine."""
    try:
        shop_id = _authenticate_cli_shop()
        medicine_id = _read_positive_integer("Medicine ID: ")
        batch_number = input("Batch number: ").strip()
        manufacturing_date_text = input(
            "Manufacturing date (YYYY-MM-DD, blank if unknown): "
        ).strip()
        manufacturing_date = (
            date.fromisoformat(manufacturing_date_text)
            if manufacturing_date_text
            else None
        )
        expiry_date = date.fromisoformat(input("Expiry date (YYYY-MM-DD): ").strip())
        quantity = _read_positive_integer("Quantity: ")
        mrp = _read_price("Selling rate / MRP per unit: ")
        purchase_price = _read_price("Purchase price per unit: ")
        gst_percent = _read_price("GST percentage: ")
        discount_percent = _read_price("Discount percentage: ")
        batch_id = add_batch_stock(
            shop_id,
            medicine_id,
            batch_number,
            expiry_date,
            quantity,
            mrp,
            purchase_price,
            manufacturing_date,
            gst_percent,
            discount_percent,
        )
        typer.echo(f"Stock batch added with ID {batch_id}.")
    except (ValueError, RuntimeError, MySQLConnectorError) as exc:
        typer.echo(f"Error: {exc}")


@app.command("view-stock")
def _view_stock() -> None:
    """View current stock levels and batch details."""
    try:
        shop_id = _authenticate_cli_shop()
        stock_levels = get_stock_levels(shop_id)
        if not stock_levels:
            typer.echo("No medicines found.")
            return

        typer.echo(
            f"{'Medicine ID':>11}  {'Medicine':<24} {'Category':<9} {'Batch':<16} "
            f"{'MFD':<12} {'Expiry':<12} {'Qty':>8} {'MRP':>10} "
            f"{'GST':>7} {'Disc':>7} Status"
        )
        for row in stock_levels:
            batch_number = row["batch_number"] or "-"
            mfd = row["manufacturing_date"].isoformat() if row["manufacturing_date"] else "-"
            expiry = row["expiry_date"].isoformat() if row["expiry_date"] else "-"
            quantity = row["quantity"] if row["quantity"] is not None else "-"
            mrp = f"{row['mrp']:.2f}" if row["mrp"] is not None else "-"
            gst = f"{row['gst_percent']:.2f}" if row["gst_percent"] is not None else "-"
            discount = f"{row['discount_percent']:.2f}" if row["discount_percent"] is not None else "-"
            status = "EXPIRED" if row["is_expired"] else "OK"
            typer.echo(
                f"{row['medicine_id']:>11}  {row['brand_name']:<24} "
                f"{(row['medicine_category'] or 'UNSET'):<9} "
                f"{batch_number:<16} {mfd:<12} {expiry:<12} {quantity:>8} "
                f"{mrp:>10} {gst:>7} {discount:>7} {status}"
            )
    except (ValueError, RuntimeError, MySQLConnectorError) as exc:
        typer.echo(f"Error: {exc}")


@app.command("issue-bill")
def _issue_bill() -> None:
    """Process a dispatch bill for a medical shop."""
    try:
        shop_id = _authenticate_cli_shop()
        shop_name = input("Medical shop name to bill: ").strip()
        cart_items: list[CartItem] = []
        while True:
            try:
                medicine_id = int(
                    input("Medicine ID (0 to finish adding items): ").strip()
                )
            except ValueError:
                typer.echo("Enter a positive whole number, or 0 to finish.")
                continue
            if medicine_id == 0:
                if cart_items:
                    break
                typer.echo("Add at least one medicine before finishing the cart.")
                continue
            if medicine_id < 0:
                typer.echo("Enter a positive medicine ID.")
                continue
            cart_items.append(
                {
                    "medicine_id": medicine_id,
                    "quantity": _read_positive_integer("Quantity: "),
                }
            )
            if input("Add another medicine? [y/N]: ").strip().lower() != "y":
                break
        process_dispatch_bill(shop_id, shop_name, cart_items)
        typer.echo("Dispatch bill successfully processed.")
    except (ValueError, RuntimeError, MySQLConnectorError) as exc:
        typer.echo(f"Error: {exc}")


@app.callback()
def main() -> None:
    """Medical Stock Dispatch and Billing Management System."""
    pass


if __name__ == "__main__":
    app()