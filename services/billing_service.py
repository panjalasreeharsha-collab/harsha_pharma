"""FEFO dispatch billing with atomic inventory and invoice updates."""

from __future__ import annotations

import sys
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import TypedDict

from config.database import get_connection


class CartItem(TypedDict):
    """A requested medicine quantity, keyed by catalogue ID."""

    medicine_id: int
    quantity: int


class ReceiptWriteError(RuntimeError):
    """Raised when a committed invoice cannot be saved as a receipt."""


CENT = Decimal("0.01")
RECEIPTS_DIRECTORY = Path(__file__).resolve().parents[1] / "receipts"


def _print_receipt(receipt: str) -> None:
    try:
        print(receipt, end="")
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_receipt = receipt.encode(encoding, errors="backslashreplace").decode(
            encoding
        )
        sys.stdout.write(safe_receipt)


def _validate_cart(shop_name: str, cart_items: list[CartItem]) -> None:
    if not shop_name.strip():
        raise ValueError("Shop name must not be empty.")
    if not cart_items:
        raise ValueError("The cart must contain at least one item.")
    for item in cart_items:
        medicine_id = item.get("medicine_id")
        quantity = item.get("quantity")
        if isinstance(medicine_id, bool) or not isinstance(medicine_id, int):
            raise ValueError("Each medicine_id must be an integer.")
        if medicine_id <= 0:
            raise ValueError("Each medicine_id must be a positive integer.")
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise ValueError("Each quantity must be an integer.")
        if quantity <= 0:
            raise ValueError("Each quantity must be greater than zero.")


def _format_receipt(
    invoice_id: int,
    sale_date: datetime | date,
    shop_name: str,
    lines: list[dict[str, object]],
    total: Decimal,
) -> str:
    date_text = (
        sale_date.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(sale_date, datetime)
        else sale_date.strftime("%Y-%m-%d")
    )
    output = [
        "=" * 104,
        "MEDICAL STOCK DISPATCH RECEIPT".center(104),
        "=" * 104,
        f"Invoice ID : {invoice_id}",
        f"Date       : {date_text}",
        f"Shop Name  : {shop_name}",
        "-" * 104,
        f"{'Item':<24} {'Batch':<14} {'Qty':>7} {'MRP':>10} "
        f"{'Discount':>11} {'Rate':>11} {'Amount':>12}",
        "-" * 104,
    ]

    for line in lines:
        output.append(
            f"{str(line['brand_name'])[:24]:<24} "
            f"{str(line['batch_number'])[:14]:<14} "
            f"{int(line['quantity_sold']):>7} "
            f"{Decimal(line['mrp']):>10.2f} "
            f"{Decimal(line['discount_percent']):>10.2f}% "
            f"{Decimal(line['unit_price']):>11.2f} "
            f"{Decimal(line['line_total']):>12.2f}"
        )

    output.extend(
        [
            "-" * 104,
            f"{'GRAND TOTAL':>91} {total:>12.2f}",
            "=" * 104,
        ]
    )
    return "\n".join(output) + "\n"


def process_dispatch_bill(
    shop_id: int,
    shop_name: str,
    cart_items: list[CartItem],
) -> str:
    """Deduct stock in FEFO order, create an invoice, then print/save its receipt.

    Each cart item has ``medicine_id`` and ``quantity`` keys. Standard medicine
    receives 30% off batch MRP; generic medicine receives 70% off.
    """
    if shop_id <= 0:
        raise ValueError("Shop ID must be a positive integer.")
    _validate_cart(shop_name, cart_items)

    connection = get_connection()
    cursor = None
    try:
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO sales_invoices (shop_id, shop_name, sale_date, total_amount)
            VALUES (%s, %s, CURRENT_TIMESTAMP, %s)
            """,
            (shop_id, shop_name.strip(), Decimal("0.00")),
        )
        invoice_id = int(cursor.lastrowid)

        receipt_lines: list[dict[str, object]] = []
        grand_total = Decimal("0.00")

        for item in cart_items:
            cursor.execute(
                """
                SELECT medicine_category
                FROM medicines
                WHERE medicine_id = %s AND shop_id = %s
                """,
                (item["medicine_id"], shop_id),
            )
            medicine = cursor.fetchone()
            if medicine is None:
                raise ValueError(f"Medicine ID {item['medicine_id']} was not found.")
            medicine_category = medicine["medicine_category"]
            if medicine_category not in ("standard", "generic"):
                raise ValueError(
                    f"Medicine ID {item['medicine_id']} has no valid standard/"
                    "generic category. Set its category before dispatch."
                )
            discount_percent = (
                Decimal("30.00")
                if medicine_category == "standard"
                else Decimal("70.00")
            )

            requested_quantity = item["quantity"]
            cursor.execute(
                """
                SELECT
                    b.batch_id,
                    b.batch_number,
                    b.expiry_date,
                    b.quantity,
                    b.mrp,
                    m.brand_name
                FROM inventory_batches AS b
                INNER JOIN medicines AS m ON m.medicine_id = b.medicine_id
                WHERE b.medicine_id = %s
                  AND b.expiry_date >= CURRENT_DATE
                  AND b.quantity > 0
                  AND m.shop_id = %s
                ORDER BY b.expiry_date ASC, b.batch_id ASC
                FOR UPDATE
                """,
                (item["medicine_id"], shop_id),
            )
            batches = cursor.fetchall()

            available_quantity = sum(int(batch["quantity"]) for batch in batches)
            if available_quantity < requested_quantity:
                raise ValueError(
                    f"Insufficient non-expired stock for medicine "
                    f"{item['medicine_id']}: requested {requested_quantity}, "
                    f"available {available_quantity}."
                )

            remaining_quantity = requested_quantity
            for batch in batches:
                if remaining_quantity == 0:
                    break

                quantity_taken = min(int(batch["quantity"]), remaining_quantity)
                mrp = Decimal(batch["mrp"]).quantize(CENT, rounding=ROUND_HALF_UP)
                unit_price = (
                    mrp * (Decimal("100.00") - discount_percent) / Decimal("100.00")
                ).quantize(CENT, rounding=ROUND_HALF_UP)
                line_total = (unit_price * quantity_taken).quantize(
                    CENT, rounding=ROUND_HALF_UP
                )

                cursor.execute(
                    """
                    UPDATE inventory_batches
                    SET quantity = quantity - %s
                    WHERE batch_id = %s AND quantity >= %s
                    """,
                    (quantity_taken, batch["batch_id"], quantity_taken),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"Stock changed while processing batch {batch['batch_id']}."
                    )

                cursor.execute(
                    """
                    INSERT INTO sale_items
                        (
                            invoice_id,
                            batch_id,
                            quantity_sold,
                            mrp,
                            discount_percent,
                            unit_price
                        )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        invoice_id,
                        batch["batch_id"],
                        quantity_taken,
                        mrp,
                        discount_percent,
                        unit_price,
                    ),
                )
                receipt_lines.append(
                    {
                        "brand_name": batch["brand_name"],
                        "batch_number": batch["batch_number"],
                        "quantity_sold": quantity_taken,
                        "mrp": mrp,
                        "discount_percent": discount_percent,
                        "unit_price": unit_price,
                        "line_total": line_total,
                    }
                )
                grand_total += line_total
                remaining_quantity -= quantity_taken

        grand_total = grand_total.quantize(CENT, rounding=ROUND_HALF_UP)
        cursor.execute(
            "UPDATE sales_invoices SET total_amount = %s WHERE invoice_id = %s",
            (grand_total, invoice_id),
        )
        cursor.execute(
            "SELECT sale_date FROM sales_invoices WHERE invoice_id = %s",
            (invoice_id,),
        )
        sale_date = cursor.fetchone()["sale_date"]
        connection.commit()
    except Exception:
        if connection.is_connected():
            connection.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()

    receipt = _format_receipt(
        invoice_id, sale_date, shop_name.strip(), receipt_lines, grand_total
    )
    receipt_path = RECEIPTS_DIRECTORY / f"invoice_{invoice_id}.txt"
    try:
        RECEIPTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(receipt, encoding="utf-8")
    except OSError as exc:
        raise ReceiptWriteError(
            f"Invoice {invoice_id} was committed, but its receipt could not be "
            f"saved to {receipt_path}: {exc}"
        ) from exc

    _print_receipt(receipt)
    print(f"Receipt saved: receipts/invoice_{invoice_id}.txt")
    return receipt


def get_invoice_receipt(invoice_id: int, shop_id: int) -> str:
    """Rebuild a committed invoice receipt from its persisted database records."""
    if invoice_id <= 0 or shop_id <= 0:
        raise ValueError("Invoice ID and shop ID must be positive integers.")

    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT invoice_id, shop_name, sale_date, total_amount
                FROM sales_invoices
                WHERE invoice_id = %s AND shop_id = %s
                """,
                (invoice_id, shop_id),
            )
            invoice = cursor.fetchone()
            if invoice is None:
                raise ValueError(f"Invoice {invoice_id} was not found.")

            cursor.execute(
                """
                SELECT
                    m.brand_name,
                    b.batch_number,
                    si.quantity_sold,
                    si.mrp,
                    si.discount_percent,
                    si.unit_price,
                    (si.quantity_sold * si.unit_price) AS line_total
                FROM sale_items AS si
                INNER JOIN inventory_batches AS b ON b.batch_id = si.batch_id
                INNER JOIN medicines AS m ON m.medicine_id = b.medicine_id
                WHERE si.invoice_id = %s
                ORDER BY si.item_id
                """,
                (invoice_id,),
            )
            lines = list(cursor.fetchall())
            if not lines:
                raise ValueError(f"Invoice {invoice_id} has no sale items.")

            return _format_receipt(
                int(invoice["invoice_id"]),
                invoice["sale_date"],
                invoice["shop_name"],
                lines,
                Decimal(invoice["total_amount"]),
            )
        finally:
            cursor.close()
    finally:
        connection.close()
