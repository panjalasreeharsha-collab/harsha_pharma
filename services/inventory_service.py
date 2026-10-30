"""Medicine catalogue and inventory operations."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from config.database import get_connection

MedicineCategory = Literal["standard", "generic"]


def add_medicine(
    brand_name: str,
    generic_name: str,
    manufacturer: str,
    unit_type: str,
    medicine_category: MedicineCategory,
) -> int:
    """Add a medicine to the catalogue and return its generated ID."""
    values = (brand_name, generic_name, manufacturer, unit_type)
    if any(not value.strip() for value in values):
        raise ValueError("Medicine fields must not be empty.")
    medicine_category = medicine_category.strip().lower()
    if medicine_category not in ("standard", "generic"):
        raise ValueError("Medicine category must be 'standard' or 'generic'.")

    connection = get_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO medicines
                    (brand_name, generic_name, manufacturer, unit_type, medicine_category)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (*values, medicine_category),
            )
            medicine_id = int(cursor.lastrowid)
            connection.commit()
            return medicine_id
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def set_medicine_category(
    medicine_id: int,
    medicine_category: MedicineCategory,
) -> None:
    """Set or update a medicine's standard/generic billing category."""
    if medicine_id <= 0:
        raise ValueError("Medicine ID must be a positive integer.")
    medicine_category = medicine_category.strip().lower()
    if medicine_category not in ("standard", "generic"):
        raise ValueError("Medicine category must be 'standard' or 'generic'.")

    connection = get_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT medicine_id FROM medicines WHERE medicine_id = %s",
                (medicine_id,),
            )
            if cursor.fetchone() is None:
                raise ValueError(f"Medicine ID {medicine_id} was not found.")
            cursor.execute(
                "UPDATE medicines SET medicine_category = %s WHERE medicine_id = %s",
                (medicine_category, medicine_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def add_batch_stock(
    medicine_id: int,
    batch_number: str,
    expiry_date: date,
    quantity: int,
    mrp: Decimal,
    purchase_price: Decimal,
) -> int:
    """Add a batch for a medicine and return the generated batch ID."""
    if medicine_id <= 0:
        raise ValueError("Medicine ID must be a positive integer.")
    if not batch_number.strip():
        raise ValueError("Batch number must not be empty.")
    if quantity <= 0:
        raise ValueError("Batch quantity must be greater than zero.")
    if mrp < 0 or purchase_price < 0:
        raise ValueError("Prices cannot be negative.")

    connection = get_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO inventory_batches
                    (medicine_id, batch_number, expiry_date, quantity, mrp, purchase_price)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    medicine_id,
                    batch_number,
                    expiry_date,
                    quantity,
                    mrp,
                    purchase_price,
                ),
            )
            batch_id = int(cursor.lastrowid)
            connection.commit()
            return batch_id
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def get_stock_levels() -> list[dict[str, object]]:
    """Return all batches, including expired and depleted stock for visibility."""
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT
                    m.medicine_id,
                    m.brand_name,
                    m.generic_name,
                    m.unit_type,
                    m.medicine_category,
                    b.batch_id,
                    b.batch_number,
                    b.expiry_date,
                    b.quantity,
                    b.mrp,
                    (b.expiry_date < CURRENT_DATE) AS is_expired
                FROM medicines AS m
                LEFT JOIN inventory_batches AS b ON b.medicine_id = m.medicine_id
                ORDER BY m.brand_name, b.expiry_date, b.batch_number
                """
            )
            return list(cursor.fetchall())
        finally:
            cursor.close()
    finally:
        connection.close()


def check_stock_availability(medicine_id: int) -> int:
    """Return available units in non-expired batches for a medicine."""
    if medicine_id <= 0:
        raise ValueError("Medicine ID must be a positive integer.")

    connection = get_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM inventory_batches
                WHERE medicine_id = %s
                  AND expiry_date >= CURRENT_DATE
                  AND quantity > 0
                """,
                (medicine_id,),
            )
            return int(cursor.fetchone()[0])
        finally:
            cursor.close()
    finally:
        connection.close()
