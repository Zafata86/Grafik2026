import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    tab_number              TEXT    UNIQUE NOT NULL,
    name                    TEXT    NOT NULL,
    smyana                  TEXT,
    username                TEXT    UNIQUE NOT NULL,
    password_hash           TEXT    NOT NULL,
    role                    TEXT    DEFAULT 'employee',
    vacation_days_total     INTEGER DEFAULT 20,
    vacation_days_remaining INTEGER DEFAULT 20
);

CREATE TABLE IF NOT EXISTS schedule_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL,
    day         INTEGER NOT NULL,
    code        TEXT    DEFAULT '',
    leave_status TEXT   DEFAULT 'normal',
    FOREIGN KEY (employee_id) REFERENCES users(id),
    UNIQUE(employee_id, year, month, day)
);

CREATE TABLE IF NOT EXISTS vacation_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    date_from   TEXT    NOT NULL,
    date_to     TEXT    NOT NULL,
    days_count  INTEGER NOT NULL,
    status      TEXT    DEFAULT 'pending',
    requested_at TEXT,
    approved_by INTEGER,
    approved_at TEXT,
    comment     TEXT    DEFAULT '',
    FOREIGN KEY (employee_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS month_settings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    year       INTEGER NOT NULL,
    month      INTEGER NOT NULL,
    hours_abvg INTEGER DEFAULT 160,
    hours_rde  INTEGER DEFAULT 160,
    UNIQUE(year, month)
);
'''

# Администратори (имат достъп до редакция)
ADMINS = [
    ('389',  'Даниел Маринов Динев',   'Р', 'daniel',  'Admin2026', 'admin'),
    ('5252', 'Михаил Зафиров Зафиров', 'Д', 'mihail',  'Admin2026', 'admin'),
    ('4413', 'Илияна Рускова Зафирова','Д', 'iliyana', 'Admin2026', 'admin'),
]

# Служители (потребителско = табелен номер, парола = табелен номер)
EMPLOYEES = [
    ('14',   'Ивелин Димитров Петков',      'Д'),
    ('404',  'Цветомир Светославов Минков', 'Е'),
    ('557',  'Иван Христов Иванов',         'В'),
    ('561',  'Динко Петров Динев',          'А'),
    ('753',  'Антон Найденов Тончев',       'Е'),
    ('995',  'Радослав Петров Баев',        'Е'),
    ('1104', 'Стоян Добрев Желев',          'Б'),
    ('1507', 'Владимир Йорданов Зафиров',   'Р'),
    ('1593', 'Николай Илиев Димитров',      'Д'),
    ('2333', 'Димитър Атанасов Димитров',   'Д'),
    ('2417', 'Станимир Иванов Желязков',    'Д'),
    ('2580', 'Георги Мирчев Георгиев',      'Е'),
    ('2583', 'Мирослав Димов Мънчев',       'Е'),
    ('2613', 'Стоян Сотиров Киров',         'Е'),
    ('2778', 'Владимир Красимиров Ангелов', 'Е'),
    ('3233', 'Дончо Дичев Донев',           'Е'),
    ('3818', 'Живко Динчев Пашов',          'Г'),
    ('4396', 'Милен Димитров Минчев',       'Б'),
    ('4515', 'Дамян Димитров Димов',        'Д'),
    ('4589', 'Антон Бинев Иванов',          'Е'),
    ('4777', 'Красимир Динков Кръстев',     'Д'),
    ('5043', 'Валентин Петков Петров',      'В'),
    ('5065', 'Пламен Митев Митев',          'А'),
    ('5098', 'Ивелин Георгиев Георгиев',    'Д'),
]


def init():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript(SCHEMA)

    for tab, name, smyana, username, password, role in ADMINS:
        try:
            c.execute(
                '''INSERT INTO users
                   (tab_number, name, smyana, username, password_hash, role,
                    vacation_days_total, vacation_days_remaining)
                   VALUES (?, ?, ?, ?, ?, ?, 20, 20)''',
                (tab, name, smyana, username, generate_password_hash(password), role)
            )
        except sqlite3.IntegrityError:
            pass

    for tab, name, smyana in EMPLOYEES:
        try:
            c.execute(
                '''INSERT INTO users
                   (tab_number, name, smyana, username, password_hash, role,
                    vacation_days_total, vacation_days_remaining)
                   VALUES (?, ?, ?, ?, ?, 'employee', 20, 20)''',
                (tab, name, smyana, tab, generate_password_hash(tab))
            )
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()

    print('-' * 50)
    print('  База данни инициализирана успешно!')
    print('-' * 50)
    print()
    print('  АДМИНИСТРАТОРИ:')
    print('  Потребител: daniel   | Парола: Admin2026')
    print('  Потребител: mihail   | Парола: Admin2026')
    print('  Потребител: iliyana  | Парола: Admin2026')
    print()
    print('  СЛУЖИТЕЛИ:')
    print('  Потребителско = табелен номер')
    print('  Парола        = табелен номер')
    print()
    print('  Препоръчително е всеки да смени паролата!')
    print('-' * 50)


if __name__ == '__main__':
    init()
