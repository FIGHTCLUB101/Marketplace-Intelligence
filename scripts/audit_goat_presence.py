"""One-off diagnostic: for each platform, print is_goat row counts and a
sample of product names, to check whether the near-zero GOAT Life presence
on Swiggy/Zepto (found during Sprint 4 planning) is real or a scraper bug.
"""
from db_connection import get_connection

with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT platform, is_goat, COUNT(*)
            FROM shelf_snapshots GROUP BY platform, is_goat ORDER BY platform, is_goat
        """)
        print("--- is_goat counts by platform ---")
        for row in cur.fetchall():
            print(row)

        print("\n--- sample product_names containing 'goat' (any platform, case-insensitive) ---")
        cur.execute("""
            SELECT DISTINCT platform, product_name FROM shelf_snapshots
            WHERE product_name ILIKE '%goat%' LIMIT 20
        """)
        for row in cur.fetchall():
            print(row)

        print("\n--- sample product_names, Swiggy, is_goat=false (first 15) ---")
        cur.execute("""
            SELECT DISTINCT product_name FROM shelf_snapshots
            WHERE platform = 'swiggy' LIMIT 15
        """)
        for row in cur.fetchall():
            print(row)
