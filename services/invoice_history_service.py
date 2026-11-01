"""Shop-scoped history of retail and pharmacy-dispatch invoices."""

from __future__ import annotations

from config.database import get_connection


def get_invoice_history(shop_id: int) -> list[dict[str, object]]:
    """Return all invoice types for one shop, newest first."""
    if shop_id <= 0:
        raise ValueError("Shop ID must be a positive integer.")

    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT invoice_type, invoice_id, sale_date, billed_to, total_amount
                FROM (
                    SELECT
                        'Shop dispatch' AS invoice_type,
                        invoice_id,
                        sale_date,
                        shop_name AS billed_to,
                        total_amount
                    FROM sales_invoices
                    WHERE shop_id = %s

                    UNION ALL

                    SELECT
                        'Customer sale' AS invoice_type,
                        invoice_id,
                        sale_date,
                        customer_name AS billed_to,
                        total_amount
                    FROM customer_invoices
                    WHERE shop_id = %s
                ) AS invoices
                ORDER BY sale_date DESC, invoice_id DESC
                """,
                (shop_id, shop_id),
            )
            return list(cursor.fetchall())
        finally:
            cursor.close()
    finally:
        connection.close()
