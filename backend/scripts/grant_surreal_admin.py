"""Grant the web admin role to an existing user through the deployment console."""

import argparse
from datetime import datetime, timezone

from surrealdb import RecordID

from database.surreal_connection import connect_surreal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Email of a user who has already signed in")
    email = parser.parse_args().email.strip()
    with connect_surreal("auth_schema") as connection, connection.begin_transaction() as transaction:
        users = transaction.query(
            "SELECT VALUE id FROM users WHERE email = $email AND is_active = true LIMIT 2",
            {"email": email},
        ).execute()[0]
        if len(users) != 1:
            parser.exit(1, "Se necesita una única cuenta activa con ese correo.\n")
        user = users[0].id
        transaction.query("DEFINE TABLE IF NOT EXISTS roles SCHEMALESS").execute()
        transaction.query("DEFINE TABLE IF NOT EXISTS user_roles SCHEMALESS").execute()
        roles = transaction.query("SELECT VALUE id FROM roles WHERE name = 'admin' LIMIT 2").execute()[0]
        if len(roles) > 1:
            parser.exit(1, "Hay más de un rol admin. Revisa los roles de la base.\n")
        role = roles[0] if roles else RecordID("roles", "admin")
        transaction.query(
            "UPSERT $role SET name = 'admin' RETURN NONE",
            {"role": role},
        ).execute()
        transaction.query(
            "UPSERT $grant SET user_id = $user, role_id = $role, "
            "assigned_at = assigned_at ?? $now RETURN NONE",
            {
                "grant": RecordID("user_roles", [user, role.id]),
                "user": user,
                "role": role.id,
                "now": datetime.now(timezone.utc).isoformat(),
            },
        ).execute()
    print("Rol admin asignado.")


if __name__ == "__main__":
    main()
