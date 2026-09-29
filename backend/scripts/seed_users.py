"""Seed demo auth users (admin / operator)."""

from app.services.auth_users import DEMO_USERS, ensure_demo_users


def main() -> None:
    users = ensure_demo_users()
    print("demo users ready:")
    for u in users:
        pwd = next(d["password"] for d in DEMO_USERS if d["username"] == u["username"])
        print(f"  {u['username']} / {pwd}  role={u['role']}  id={u['id']}")


if __name__ == "__main__":
    main()
