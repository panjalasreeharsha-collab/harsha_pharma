"""Command-line interface for medical stock and dispatch billing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from mysql.connector import Error as MySQLConnectorError

from services.billing_service import CartItem, process_dispatch_bill
from services.inventory_service import (
    add_batch_stock,
    add_medicine,
    get_stock_levels,
    set_medicine_category,
)


def _read_positive_integer(prompt: str) -> int:
    while True:
        try:
            value = int(input(prompt).strip())
            if value <= 0:
                raise ValueError
            return value
        except ValueError:
            print("Enter a positive whole number.")


def _read_price(prompt: str) -> Decimal:
    while True:
        try:
            value = Decimal(input(prompt).strip())
            if not value.is_finite() or value < 0:
                raise InvalidOperation
            return value.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            print("Enter a valid non-negative amount.")


def _add_medicine() -> None:
    medicine_category = input("Category (standard/generic): ").strip().lower()
    medicine_id = add_medicine(
        input("Brand name: ").strip(),
        input("Generic name: ").strip(),
        input("Manufacturer: ").strip(),
        input("Unit type (tablet, syrup, etc.): ").strip(),
        medicine_category,
    )
    print(
        f"Medicine added with ID {medicine_id} "
        f"(category: {medicine_category})."
    )


def _set_category() -> None:
    medicine_id = _read_positive_integer("Medicine ID: ")
    category = input("Category (standard/generic): ").strip().lower()
    set_medicine_category(medicine_id, category)
    print(f"Medicine {medicine_id} category updated to {category}.")


def _add_stock() -> None:
    medicine_id = _read_positive_integer("Medicine ID: ")
    batch_number = input("Batch number: ").strip()
    expiry_date = date.fromisoformat(input("Expiry date (YYYY-MM-DD): ").strip())
    quantity = _read_positive_integer("Quantity: ")
    mrp = _read_price("Selling rate / MRP per unit: ")
    purchase_price = _read_price("Purchase price per unit: ")
    batch_id = add_batch_stock(
        medicine_id, batch_number, expiry_date, quantity, mrp, purchase_price
    )
    print(f"Stock batch added with ID {batch_id}.")


def _view_stock() -> None:
    stock_levels = get_stock_levels()
    if not stock_levels:
        print("No medicines found.")
        return

    print(
        f"{'Medicine ID':>11}  {'Medicine':<24} {'Category':<9} {'Batch':<16} "
        f"{'Expiry':<12} {'Qty':>8} {'MRP':>10} Status"
    )
    for row in stock_levels:
        batch_number = row["batch_number"] or "-"
        expiry = row["expiry_date"].isoformat() if row["expiry_date"] else "-"
        quantity = row["quantity"] if row["quantity"] is not None else "-"
        mrp = f"{row['mrp']:.2f}" if row["mrp"] is not None else "-"
        status = "EXPIRED" if row["is_expired"] else "OK"
        print(
            f"{row['medicine_id']:>11}  {row['brand_name']:<24} "
            f"{(row['medicine_category'] or 'UNSET'):<9} "
            f"{batch_number:<16} {expiry:<12} {quantity:>8} {mrp:>10} {status}"
        )


def _issue_bill() -> None:
    shop_name = input("Medical shop name: ").strip()
    cart_items: list[CartItem] = []
    while True:
        try:
            medicine_id = int(
                input("Medicine ID (0 to finish adding items): ").strip()
            )
        except ValueError:
            print("Enter a positive whole number, or 0 to finish.")
            continue
        if medicine_id == 0:
            if cart_items:
                break
            print("Add at least one medicine before finishing the cart.")
            continue
        if medicine_id < 0:
            print("Enter a positive medicine ID.")
            continue
        cart_items.append(
            {
                "medicine_id": medicine_id,
                "quantity": _read_positive_integer("Quantity: "),
            }
        )
        if input("Add another medicine? [y/N]: ").strip().lower() != "y":
            break
    process_dispatch_bill(shop_name, cart_items)


def main() -> None:
    menu = {
        "1": ("Add medicine", _add_medicine),
        "2": ("Add batch stock", _add_stock),
        "3": ("View stock levels", _view_stock),
        "4": ("Issue dispatch bill", _issue_bill),
        "5": ("Set medicine category", _set_category),
    }

    while True:
        print("\nMedical Stock Dispatch and Billing")
        for key, (label, _) in menu.items():
            print(f"{key}. {label}")
        print("0. Exit")
        choice = input("Select an option: ").strip()

        if choice == "0":
            print("Goodbye.")
            return
        action = menu.get(choice)
        if action is None:
            print("Invalid option. Choose 0–5.")
            continue
        try:
            action[1]()
        except (ValueError, RuntimeError, MySQLConnectorError) as exc:
            print(f"Error: {exc}")


if __name__ == "__main__":
    main()
