"""
Импорт на график за Юни 2026 от Excel файла.
Кодове: 1, 2, 8, 0, Б, Н, П  →  запазени директно
НП (Неплатен/Неявяване-Принудително) → Н
Всичко останало (празно) → пропуснато (почивен ден)
"""
import openpyxl
import sqlite3
import os

EXCEL = r'C:\Users\zafat\Documents\ГРАФИК 2026.xlsx'
DB    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')
SHEET = 'юни'
YEAR  = 2026
MONTH = 6
DAYS  = 30

# Приемливи кодове от приложението
VALID = {'1','2','8','0','Б','Н','П'}

def normalize(v):
    if v is None:
        return ''
    s = str(v).strip()
    s_up = s.upper()
    if s_up in VALID:
        return s_up
    if s_up == 'НП':
        return 'Н'
    return ''   # почивен ден или неразпознато → пропуска

wb = openpyxl.load_workbook(EXCEL, data_only=True)
ws = wb[SHEET]

# Събери редовете на служителите (col A = tab_number, col B = name, col C = smyana, col D..AG = дни)
employees_excel = []
for row in ws.iter_rows(min_row=9, max_row=111, min_col=1, max_col=3+DAYS, values_only=True):
    tab = str(row[0]).strip() if row[0] else ''
    try:
        int(tab)
    except ValueError:
        continue
    name   = str(row[1]).strip() if row[1] else ''
    smyana = str(row[2]).strip().upper() if row[2] else ''
    codes  = {day+1: normalize(row[3+day]) for day in range(DAYS)}
    employees_excel.append({'tab': tab, 'name': name, 'smyana': smyana, 'codes': codes})

print(f'Прочетени от Excel: {len(employees_excel)} служители')

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Изтрий съществуващите записи за юни 2026
cur.execute(
    'DELETE FROM schedule_entries WHERE year=? AND month=?',
    (YEAR, MONTH)
)
deleted = cur.rowcount
print(f'Изтрити стари записи: {deleted}')

# Задай норма часове за месеца (176 ч. за двете групи)
cur.execute(
    'INSERT OR REPLACE INTO month_settings (year, month, hours_abvg, hours_rde) VALUES (?,?,?,?)',
    (YEAR, MONTH, 176, 176)
)

inserted = 0
skipped_emp = 0
unknown_codes = {}

for emp_data in employees_excel:
    row_db = cur.execute(
        'SELECT id FROM users WHERE tab_number=?', (emp_data['tab'],)
    ).fetchone()

    if not row_db:
        print(f'  !! Не намерен в БД: таб {emp_data["tab"]} – {emp_data["name"]}')
        skipped_emp += 1
        continue

    emp_id = row_db['id']

    for day, code in emp_data['codes'].items():
        if not code:
            continue   # почивен ден – не записваме
        leave_status = 'approved' if code == '0' else 'normal'
        cur.execute(
            '''INSERT INTO schedule_entries
               (employee_id, year, month, day, code, leave_status)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (emp_id, YEAR, MONTH, day, code, leave_status)
        )
        inserted += 1

conn.commit()
conn.close()

print(f'\nРезултат:')
print(f'  Импортирани записи:  {inserted}')
print(f'  Пропуснати служители (не в БД): {skipped_emp}')
print(f'\nГрафикът за Юни 2026 е нанесен успешно!')
