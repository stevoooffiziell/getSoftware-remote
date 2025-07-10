from DatabaseManager import DatabaseManager

if __name__ == '__main__':
    try:
        db = DatabaseManager()
        print("Database connection successful!")

        # Testabfrage
        cursor = db.conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {db.table_name}")
        count = cursor.fetchone()[0]
        print(f"Table {db.table_name} contains {count} records")

    except Exception as e:
        print(f"Database test failed: {str(e)}")