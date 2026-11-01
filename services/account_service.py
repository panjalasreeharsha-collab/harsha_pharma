"""Shop registration and password authentication."""

from __future__ import annotations

import re

from werkzeug.security import check_password_hash, generate_password_hash

from config.database import get_connection

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 12


def create_shop_account(
    shop_name: str,
    owner_name: str,
    email: str,
    password: str,
) -> dict[str, object]:
    """Create one shop-owner account and claim unassigned legacy records once."""
    shop_name = shop_name.strip()
    owner_name = owner_name.strip()
    email = email.strip().lower()
    if not shop_name or len(shop_name) > 200:
        raise ValueError("Shop name must contain 1 to 200 characters.")
    if not owner_name or len(owner_name) > 150:
        raise ValueError("Owner name must contain 1 to 150 characters.")
    if len(email) > 254 or not _EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(password) > 256:
        raise ValueError("Password must be no more than 256 characters long.")

    password_hash = generate_password_hash(password)
    connection = get_connection()
    try:
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT legacy_claimed
                FROM tenant_bootstrap
                WHERE singleton_id = 1
                FOR UPDATE
                """
            )
            bootstrap = cursor.fetchone()
            if bootstrap is None:
                raise RuntimeError(
                    "Shop-account database migration is incomplete. "
                    "Apply migration 002 before registering."
                )

            try:
                cursor.execute(
                    """
                    INSERT INTO shops (shop_name, owner_name, email, password_hash)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (shop_name, owner_name, email, password_hash),
                )
            except Exception as exc:
                if getattr(exc, "errno", None) == 1062:
                    raise ValueError(
                        "An account with that email address already exists."
                    ) from exc
                raise

            shop_id = int(cursor.lastrowid)
            if not bootstrap["legacy_claimed"]:
                for table in ("medicines", "sales_invoices"):
                    cursor.execute(
                        f"UPDATE {table} SET shop_id = %s WHERE shop_id IS NULL",
                        (shop_id,),
                    )
                cursor.execute(
                    """
                    UPDATE tenant_bootstrap
                    SET legacy_claimed = TRUE
                    WHERE singleton_id = 1
                    """
                )

            connection.commit()
            return {"shop_id": shop_id, "shop_name": shop_name, "email": email}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def authenticate_shop(email: str, password: str) -> dict[str, object] | None:
    """Verify credentials and return the associated shop, if credentials match."""
    normalized_email = email.strip().lower()
    if len(password) > 256:
        return None
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT shop_id, shop_name, email, password_hash
                FROM shops
                WHERE email = %s
                """,
                (normalized_email,),
            )
            account = cursor.fetchone()
            if account is None or not check_password_hash(
                account["password_hash"], password
            ):
                return None
            return {
                "shop_id": int(account["shop_id"]),
                "shop_name": account["shop_name"],
                "email": account["email"],
            }
        finally:
            cursor.close()
    finally:
        connection.close()
