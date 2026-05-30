import sqlite3, os
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT u.tab_number, u.name,
           GROUP_CONCAT(se.day || ':' || se.code ORDER BY se.day) as sched
    FROM schedule_entries se
    JOIN users u ON se.employee_id = u.id
    WHERE se.year=2026 AND se.month=6
    GROUP BY u.id
    ORDER BY CAST(u.tab_number AS INTEGER)
""").fetchall()
for r in rows:
    print(r['tab_number'], r['name'][:25], '|', r['sched'])
ms = conn.execute("SELECT * FROM month_settings WHERE year=2026 AND month=6").fetchone()
print('\nНорма юни 2026: АБВГ=%s ч.  РДЕ=%s ч.' % (ms['hours_abvg'], ms['hours_rde']))
total = conn.execute("SELECT COUNT(*) FROM schedule_entries WHERE year=2026 AND month=6").fetchone()[0]
print('Общо записи:', total)
conn.close()
