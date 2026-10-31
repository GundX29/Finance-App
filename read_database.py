
import sqlite3
from pathlib import Path

# Đường dẫn database do Flask-SQLAlchemy tạo
db_path = Path("instance") / "finance.db"

if not db_path.exists():
    print(f"Không tìm thấy database: {db_path.resolve()}")
    raise SystemExit(1)

# Kết nối database
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()


def show_tables():
    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
    """)
    print("\n=== DANH SÁCH BẢNG ===")
    for row in cursor.fetchall():
        print(row["name"])


def show_table_data(table_name):
    # Chỉ cho phép đọc các bảng đã biết
    allowed_tables = {"user", "transaction"}
    if table_name not in allowed_tables:
        print("Tên bảng không hợp lệ!")
        return

    cursor.execute(f'SELECT * FROM "{table_name}"')
    rows = cursor.fetchall()

    print(f"\n=== DỮ LIỆU BẢNG {table_name} ===")

    if not rows:
        print("Bảng chưa có dữ liệu.")
        return

    print(" | ".join(rows[0].keys()))
    print("-" * 80)

    for row in rows:
        values = []

        for key in row.keys():
            value = row[key]

            if table_name == "user" and key == "password_hash":
                value = "[ĐÃ ẨN]"

            values.append(str(value) if value is not None else "NULL")

        print(" | ".join(values))


try:
    show_tables()
    show_table_data("user")
    show_table_data("transaction")
finally:
    conn.close()
