"""Retail customer invoices with FEFO stock deduction."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import TypedDict

from config.database import get_connection

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


class CustomerCartItem(TypedDict):
    medicine_id: int
    quantity: int


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def create_customer_invoice(
    shop_id: int,
    customer_name: str,
    customer_phone: str,
    customer_address: str,
    cart_items: list[CustomerCartItem],
) -> int:
    """Create a retail bill and deduct its quantities in FEFO order atomically."""
    if shop_id <= 0:
        raise ValueError("Shop ID must be a positive integer.")
    customer_name = customer_name.strip()
    customer_phone = customer_phone.strip()
    customer_address = customer_address.strip()
    if not customer_name or len(customer_name) > 200:
        raise ValueError("Customer name must contain 1 to 200 characters.")
    if len(customer_phone) > 30 or len(customer_address) > 500:
        raise ValueError("Customer contact details are too long.")
    if not cart_items:
        raise ValueError("Add at least one medicine to the bill.")
    for item in cart_items:
        medicine_id = item.get("medicine_id")
        quantity = item.get("quantity")
        if isinstance(medicine_id, bool) or not isinstance(medicine_id, int) or medicine_id <= 0:
            raise ValueError("Choose a valid medicine for every bill row.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Each medicine quantity must be a positive whole number.")

    connection = get_connection()
    cursor = None
    try:
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO customer_invoices
                (shop_id, customer_name, customer_phone, customer_address)
            VALUES (%s, %s, %s, %s)
            """,
            (
                shop_id,
                customer_name,
                customer_phone or None,
                customer_address or None,
            ),
        )
        invoice_id = int(cursor.lastrowid)
        subtotal = Decimal("0.00")
        total_discount = Decimal("0.00")
        total_tax = Decimal("0.00")
        grand_total = Decimal("0.00")

        for item in cart_items:
            cursor.execute(
                """
                SELECT b.batch_id, b.batch_number, b.manufacturing_date, b.expiry_date,
                       b.quantity, b.mrp, b.gst_percent, b.discount_percent,
                       m.brand_name
                FROM inventory_batches AS b
                INNER JOIN medicines AS m ON m.medicine_id = b.medicine_id
                WHERE b.medicine_id = %s
                  AND m.shop_id = %s
                  AND b.expiry_date >= CURRENT_DATE
                  AND b.quantity > 0
                ORDER BY b.expiry_date, b.batch_id
                FOR UPDATE
                """,
                (item["medicine_id"], shop_id),
            )
            batches = cursor.fetchall()
            available = sum(int(batch["quantity"]) for batch in batches)
            requested = item["quantity"]
            if available < requested:
                raise ValueError(
                    f"Insufficient non-expired stock for medicine "
                    f"{item['medicine_id']}: requested {requested}, available {available}."
                )

            remaining = requested
            for batch in batches:
                if remaining == 0:
                    break
                quantity = min(remaining, int(batch["quantity"]))
                mrp = _money(Decimal(batch["mrp"]))
                discount_percent = Decimal(batch["discount_percent"])
                gst_percent = Decimal(batch["gst_percent"])
                discount_per_unit = _money(mrp * discount_percent / HUNDRED)
                discounted_unit = mrp - discount_per_unit
                tax_per_unit = _money(discounted_unit * gst_percent / HUNDRED)
                final_unit = discounted_unit + tax_per_unit
                line_subtotal = mrp * quantity
                line_discount = discount_per_unit * quantity
                line_tax = tax_per_unit * quantity
                line_total = final_unit * quantity

                cursor.execute(
                    """
                    UPDATE inventory_batches
                    SET quantity = quantity - %s
                    WHERE batch_id = %s AND quantity >= %s
                    """,
                    (quantity, batch["batch_id"], quantity),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"Stock changed while processing batch {batch['batch_id']}."
                    )
                cursor.execute(
                    """
                    INSERT INTO customer_sale_items
                        (
                            invoice_id, batch_id, quantity_sold, mrp,
                            discount_percent, gst_percent, unit_price,
                            tax_amount, final_unit_price, line_total
                        )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        invoice_id,
                        batch["batch_id"],
                        quantity,
                        mrp,
                        discount_percent,
                        gst_percent,
                        discounted_unit,
                        tax_per_unit,
                        final_unit,
                        line_total,
                    ),
                )
                subtotal += line_subtotal
                total_discount += line_discount
                total_tax += line_tax
                grand_total += line_total
                remaining -= quantity

        subtotal = _money(subtotal)
        total_discount = _money(total_discount)
        total_tax = _money(total_tax)
        grand_total = _money(grand_total)
        cursor.execute(
            """
            UPDATE customer_invoices
            SET subtotal = %s, total_discount = %s, total_tax = %s, total_amount = %s
            WHERE invoice_id = %s AND shop_id = %s
            """,
            (subtotal, total_discount, total_tax, grand_total, invoice_id, shop_id),
        )
        connection.commit()
        return invoice_id
    except Exception:
        if connection.is_connected():
            connection.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def get_customer_invoice(invoice_id: int, shop_id: int) -> dict[str, object]:
    """Load a customer invoice and its persisted bill lines for printing."""
    if invoice_id <= 0 or shop_id <= 0:
        raise ValueError("Invoice ID and shop ID must be positive integers.")
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT invoice_id, customer_name, customer_phone, customer_address,
                       sale_date, subtotal, total_discount, total_tax, total_amount
                FROM customer_invoices
                WHERE invoice_id = %s AND shop_id = %s
                """,
                (invoice_id, shop_id),
            )
            invoice = cursor.fetchone()
            if invoice is None:
                raise ValueError(f"Invoice {invoice_id} was not found.")
            cursor.execute(
                """
                SELECT m.brand_name, b.batch_number, b.manufacturing_date,
                       b.expiry_date, si.quantity_sold, si.mrp,
                       si.discount_percent, si.gst_percent, si.unit_price,
                       si.tax_amount, si.final_unit_price, si.line_total
                FROM customer_sale_items AS si
                INNER JOIN inventory_batches AS b ON b.batch_id = si.batch_id
                INNER JOIN medicines AS m ON m.medicine_id = b.medicine_id
                WHERE si.invoice_id = %s
                ORDER BY si.item_id
                """,
                (invoice_id,),
            )
            invoice["items"] = list(cursor.fetchall())
            return invoice
        finally:
            cursor.close()
    finally:
        connection.close()
