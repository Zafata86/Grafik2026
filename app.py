from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import uuid
from datetime import datetime, date, timedelta
import calendar
from functools import wraps

app = Flask(__name__)
app.secret_key = 'grafik-avtomatizaciya-2026'

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

MONTH_NAMES = {
    1: 'Януари', 2: 'Февруари', 3: 'Март', 4: 'Април',
    5: 'Май', 6: 'Юни', 7: 'Юли', 8: 'Август',
    9: 'Септември', 10: 'Октомври', 11: 'Ноември', 12: 'Декември'
}
DAY_NAMES = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд']

CODE_LABELS = {
    '1': 'Диспечерска (1)',
    '2': 'Нощна (2)',
    '8': 'Дневна (8)',
    '0': 'Отпуска (0)',
    'Б': 'Болничен (Б)',
    'Н': 'Неявяване (Н)',
    'П': 'Компенсация (П)',
    '':  'Почивен ден',
}

SMYANA_OPTIONS = ['А', 'Б', 'В', 'Г', 'Р', 'Д', 'Е']


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Нямате право за достъп!', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def calc_hours(schedule_for_emp):
    total = 0.0
    for e in schedule_for_emp.values():
        code = (e['code'] or '').strip()
        if code == '1':   total += 12
        elif code == '2': total += 13.143
        elif code == '8': total += 8
        elif code == '0': total += 8
        elif code == 'Б': total += 12
        elif code == 'Н': total += 8
    return round(total, 1)


def target_hours(smyana, settings):
    if not settings:
        return None
    if smyana.upper() in ('А', 'Б', 'В', 'Г'):
        return settings['hours_abvg']
    return settings['hours_rde']


BG_HOLIDAYS = [
    ('2025-01-01','Нова година'), ('2025-03-03','Ден на Освобождението'),
    ('2025-04-18','Разпети петък'), ('2025-04-19','Велика събота'),
    ('2025-04-20','Великден'), ('2025-04-21','Великденски понеделник'),
    ('2025-05-01','Ден на труда'), ('2025-05-06','Гергьовден'),
    ('2025-05-24','Ден на просвещението'), ('2025-09-06','Ден на Съединението'),
    ('2025-09-22','Ден на Независимостта'), ('2025-12-24','Бъдни вечер'),
    ('2025-12-25','Рождество Христово'), ('2025-12-26','Рождество Христово (2-ри)'),

    ('2026-01-01','Нова година'), ('2026-03-03','Ден на Освобождението'),
    ('2026-04-10','Разпети петък'), ('2026-04-11','Велика събота'),
    ('2026-04-12','Великден'), ('2026-04-13','Великденски понеделник'),
    ('2026-05-01','Ден на труда'), ('2026-05-06','Гергьовден'),
    ('2026-05-24','Ден на просвещението'), ('2026-09-06','Ден на Съединението'),
    ('2026-09-22','Ден на Независимостта'), ('2026-12-24','Бъдни вечер'),
    ('2026-12-25','Рождество Христово'), ('2026-12-26','Рождество Христово (2-ри)'),

    ('2027-01-01','Нова година'), ('2027-03-03','Ден на Освобождението'),
    ('2027-04-30','Разпети петък'), ('2027-05-01','Велика събота / Ден на труда'),
    ('2027-05-02','Великден'), ('2027-05-03','Великденски понеделник'),
    ('2027-05-06','Гергьовден'), ('2027-05-24','Ден на просвещението'),
    ('2027-09-06','Ден на Съединението'), ('2027-09-22','Ден на Независимостта'),
    ('2027-12-24','Бъдни вечер'), ('2027-12-25','Рождество Христово'),
    ('2027-12-26','Рождество Христово (2-ри)'),
]


def ensure_schema():
    """Add new columns/tables if DB was created before this version."""
    db = get_db()
    for col, dflt in [
        ('notify_minutes_before', '60'),
        ('notify_day_before',     '1'),
        ('notify_day_before_time','19:00'),
        ('notify_punch_card',     '1'),
    ]:
        try:
            db.execute(f'ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT "{dflt}"')
        except Exception:
            pass

    db.execute('''CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY, value TEXT
    )''')
    for k, v in [
        ('shift_1_start', '07:00'), ('shift_1_hours', '12'),
        ('shift_2_start', '19:00'), ('shift_2_hours', '12'),
        ('shift_8_start', '08:00'), ('shift_8_hours', '8'),
    ]:
        try:
            db.execute('INSERT INTO app_settings (key,value) VALUES (?,?)', (k, v))
        except Exception:
            pass

    db.execute('''CREATE TABLE IF NOT EXISTS holidays (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL
    )''')
    cnt = db.execute('SELECT COUNT(*) FROM holidays').fetchone()[0]
    if cnt == 0:
        for d, n in BG_HOLIDAYS:
            try:
                db.execute('INSERT INTO holidays (date,name) VALUES (?,?)', (d, n))
            except Exception:
                pass
    db.commit()
    db.close()


def get_holidays_set(db, year=None):
    if year:
        rows = db.execute(
            "SELECT date FROM holidays WHERE date LIKE ?", (f'{year}%',)
        ).fetchall()
    else:
        rows = db.execute('SELECT date FROM holidays').fetchall()
    return {r['date'] for r in rows}


def count_working_days(from_date, to_date, holidays_set):
    """Работни дни = пн-пт без официални празници."""
    count = 0
    current = from_date
    while current <= to_date:
        if current.weekday() < 5 and current.isoformat() not in holidays_set:
            count += 1
        current += timedelta(days=1)
    return count


def get_shift_times(db):
    rows = db.execute('SELECT key, value FROM app_settings').fetchall()
    return {r['key']: r['value'] for r in rows}


def nav_months(year, month):
    if month == 1:
        py, pm = year - 1, 12
    else:
        py, pm = year, month - 1
    if month == 12:
        ny, nm = year + 1, 1
    else:
        ny, nm = year, month + 1
    return py, pm, ny, nm


@app.context_processor
def inject_globals():
    pending = 0
    if 'user_id' in session and session.get('role') == 'admin':
        db = get_db()
        pending = db.execute(
            "SELECT COUNT(*) FROM vacation_requests WHERE status='pending'"
        ).fetchone()[0]
        db.close()
    return {'pending_count': pending, 'MONTH_NAMES': MONTH_NAMES}


# ── AUTH ───────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        db.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        flash('Грешно потребителско име или парола.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current = request.form['current_password']
        new_pw = request.form['new_password']
        confirm = request.form['confirm_password']
        if new_pw != confirm:
            flash('Новите пароли не съвпадат.', 'danger')
        elif len(new_pw) < 4:
            flash('Паролата трябва да е поне 4 символа.', 'danger')
        else:
            db = get_db()
            user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
            if not check_password_hash(user['password_hash'], current):
                flash('Грешна текуща парола.', 'danger')
                db.close()
            else:
                db.execute('UPDATE users SET password_hash=? WHERE id=?',
                           (generate_password_hash(new_pw), session['user_id']))
                db.commit()
                db.close()
                flash('Паролата е сменена успешно.', 'success')
                return redirect(url_for('dashboard'))
    return render_template('change_password.html')


# ── DASHBOARD (пълен график – само четене) ────────────────────────────────────

@app.route('/dashboard')
@app.route('/dashboard/<int:year>/<int:month>')
@login_required
def dashboard(year=None, month=None):
    today = date.today()
    year = year or today.year
    month = month or today.month

    db = get_db()
    employees = db.execute(
        'SELECT * FROM users ORDER BY CAST(tab_number AS INTEGER)'
    ).fetchall()
    entries_raw = db.execute(
        'SELECT * FROM schedule_entries WHERE year=? AND month=?', (year, month)
    ).fetchall()
    settings = db.execute(
        'SELECT * FROM month_settings WHERE year=? AND month=?', (year, month)
    ).fetchone()
    db.close()

    schedule = {}
    for e in entries_raw:
        schedule.setdefault(e['employee_id'], {})[e['day']] = e

    days_in_month = calendar.monthrange(year, month)[1]
    day_info = [(d, date(year, month, d).weekday()) for d in range(1, days_in_month + 1)]
    hours = {emp['id']: calc_hours(schedule.get(emp['id'], {})) for emp in employees}
    py, pm, ny, nm = nav_months(year, month)

    return render_template('dashboard.html',
        employees=employees, schedule=schedule, year=year, month=month,
        month_name=MONTH_NAMES[month], days_in_month=days_in_month,
        day_info=day_info, DAY_NAMES=DAY_NAMES, settings=settings,
        today=today, hours=hours, target_hours=target_hours,
        py=py, pm=pm, ny=ny, nm=nm
    )


# ── МОЯ СМЯНА ─────────────────────────────────────────────────────────────────

@app.route('/my-schedule')
@app.route('/my-schedule/<int:year>/<int:month>')
@login_required
def my_schedule(year=None, month=None):
    today = date.today()
    year = year or today.year
    month = month or today.month

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    entries_raw = db.execute(
        'SELECT * FROM schedule_entries WHERE employee_id=? AND year=? AND month=?',
        (session['user_id'], year, month)
    ).fetchall()
    vac_requests = db.execute(
        '''SELECT vr.*, u2.name as appr_name
           FROM vacation_requests vr
           LEFT JOIN users u2 ON vr.approved_by = u2.id
           WHERE vr.employee_id=?
           ORDER BY vr.requested_at DESC LIMIT 30''',
        (session['user_id'],)
    ).fetchall()
    settings = db.execute(
        'SELECT * FROM month_settings WHERE year=? AND month=?', (year, month)
    ).fetchone()
    db.close()

    schedule = {e['day']: e for e in entries_raw}
    days_in_month = calendar.monthrange(year, month)[1]
    day_info = [(d, date(year, month, d).weekday()) for d in range(1, days_in_month + 1)]
    my_hours = calc_hours(schedule)
    py, pm, ny, nm = nav_months(year, month)

    return render_template('my_schedule.html',
        user=user, schedule=schedule, year=year, month=month,
        month_name=MONTH_NAMES[month], days_in_month=days_in_month,
        day_info=day_info, DAY_NAMES=DAY_NAMES, settings=settings,
        today=today, my_hours=my_hours, vac_requests=vac_requests,
        target_hours=target_hours, py=py, pm=pm, ny=ny, nm=nm
    )


# ── ЗАЯВКА ЗА ОТПУСКА ────────────────────────────────────────────────────────

@app.route('/request-vacation', methods=['GET', 'POST'])
@login_required
def request_vacation():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    holidays_set = get_holidays_set(db)

    if request.method == 'POST':
        date_from_str = request.form['date_from']
        date_to_str = request.form['date_to']
        comment = request.form.get('comment', '').strip()

        from_date = datetime.strptime(date_from_str, '%Y-%m-%d').date()
        to_date = datetime.strptime(date_to_str, '%Y-%m-%d').date()

        if from_date > to_date:
            flash('Началната дата трябва да е преди крайната.', 'danger')
        else:
            # Проверка за почивни/празнични дни
            bad_days = []
            current = from_date
            while current <= to_date:
                if current.weekday() >= 5:
                    names = ['Пн','Вт','Ср','Чт','Пт','Сб','Нд']
                    bad_days.append(f'{current.strftime("%d.%m")} ({names[current.weekday()]})')
                elif current.isoformat() in holidays_set:
                    bad_days.append(f'{current.strftime("%d.%m")} (празник)')
                current += timedelta(days=1)

            if bad_days:
                flash(
                    'Периодът включва почивни/празнични дни: '
                    + ', '.join(bad_days[:5])
                    + (f' и още {len(bad_days)-5}...' if len(bad_days) > 5 else '')
                    + '. Моля изберете само работни дни.',
                    'danger'
                )
            else:
                days_count = count_working_days(from_date, to_date, holidays_set)
                if days_count == 0:
                    flash('Няма работни дни в избрания период.', 'danger')
                elif user['vacation_days_remaining'] < days_count:
                    flash(
                        f'Нямате достатъчно дни отпуска. '
                        f'Оставащи: {user["vacation_days_remaining"]}, нужни: {days_count}.', 'danger'
                    )
                else:
                    overlap = db.execute(
                        '''SELECT date_from, date_to FROM vacation_requests
                           WHERE employee_id=? AND status IN ('pending','approved')
                           AND date_from <= ? AND date_to >= ?''',
                        (session['user_id'], date_to_str, date_from_str)
                    ).fetchone()
                    if overlap:
                        flash(
                            f'Вече имате активна заявка за отпуска, която се застъпва с избрания период '
                            f'({overlap["date_from"]} – {overlap["date_to"]}). '
                            f'Анулирайте я преди да подадете нова.',
                            'danger'
                        )
                    else:
                        db.execute(
                            '''INSERT INTO vacation_requests
                               (employee_id, date_from, date_to, days_count, status, requested_at, comment)
                               VALUES (?, ?, ?, ?, 'pending', ?, ?)''',
                            (session['user_id'], date_from_str, date_to_str, days_count,
                             datetime.now().isoformat(), comment)
                        )
                        current = from_date
                        while current <= to_date:
                            if current.weekday() < 5 and current.isoformat() not in holidays_set:
                                db.execute(
                                    '''INSERT OR REPLACE INTO schedule_entries
                                       (employee_id, year, month, day, code, leave_status)
                                       VALUES (?, ?, ?, ?, '0', 'planned')''',
                                    (session['user_id'], current.year, current.month, current.day)
                                )
                            current += timedelta(days=1)
                        db.commit()
                        db.close()
                        flash(f'Заявката е изпратена ({days_count} работни дни). Очаква одобрение.', 'success')
                        return redirect(url_for('my_schedule'))

    # Holidays list for flatpickr (current + next year)
    today = date.today()
    holiday_dates = sorted(holidays_set)
    db.close()
    return render_template('request_vacation.html', user=user,
                           holiday_dates=holiday_dates)


# ── ADMIN: РЕДАКЦИЯ НА ГРАФИКА ────────────────────────────────────────────────

@app.route('/admin/schedule')
@app.route('/admin/schedule/<int:year>/<int:month>')
@admin_required
def admin_schedule(year=None, month=None):
    today = date.today()
    year = year or today.year
    month = month or today.month

    db = get_db()
    employees = db.execute(
        'SELECT * FROM users ORDER BY CAST(tab_number AS INTEGER)'
    ).fetchall()
    entries_raw = db.execute(
        'SELECT * FROM schedule_entries WHERE year=? AND month=?', (year, month)
    ).fetchall()
    settings = db.execute(
        'SELECT * FROM month_settings WHERE year=? AND month=?', (year, month)
    ).fetchone()
    db.close()

    schedule = {}
    for e in entries_raw:
        schedule.setdefault(e['employee_id'], {})[e['day']] = e

    days_in_month = calendar.monthrange(year, month)[1]
    day_info = [(d, date(year, month, d).weekday()) for d in range(1, days_in_month + 1)]
    hours = {emp['id']: calc_hours(schedule.get(emp['id'], {})) for emp in employees}
    py, pm, ny, nm = nav_months(year, month)

    return render_template('admin/schedule_edit.html',
        employees=employees, schedule=schedule, year=year, month=month,
        month_name=MONTH_NAMES[month], days_in_month=days_in_month,
        day_info=day_info, DAY_NAMES=DAY_NAMES, settings=settings,
        today=today, hours=hours, target_hours=target_hours,
        CODE_LABELS=CODE_LABELS, SMYANA_OPTIONS=SMYANA_OPTIONS,
        py=py, pm=pm, ny=ny, nm=nm
    )


@app.route('/admin/schedule/cell', methods=['POST'])
@admin_required
def admin_schedule_cell():
    data = request.json
    emp_id = int(data['employee_id'])
    year = int(data['year'])
    month = int(data['month'])
    day = int(data['day'])
    code = data.get('code', '').strip()

    db = get_db()
    if code == '2':
        conflict = db.execute(
            '''SELECT u.name FROM schedule_entries se
               JOIN users u ON se.employee_id = u.id
               WHERE se.employee_id != ? AND se.year=? AND se.month=? AND se.day=? AND se.code='2' ''',
            (emp_id, year, month, day)
        ).fetchone()
        if conflict:
            db.close()
            return jsonify({'ok': False, 'conflict': True,
                            'msg': f'Нощна смяна на {day}-ти вече е заета от {conflict["name"]}!'})

    if code == '':
        db.execute(
            'DELETE FROM schedule_entries WHERE employee_id=? AND year=? AND month=? AND day=?',
            (emp_id, year, month, day)
        )
    else:
        leave_status = 'approved' if code == '0' else 'normal'
        db.execute(
            '''INSERT OR REPLACE INTO schedule_entries
               (employee_id, year, month, day, code, leave_status)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (emp_id, year, month, day, code, leave_status)
        )
    db.commit()
    db.close()
    return jsonify({'ok': True})


@app.route('/admin/schedule/hours', methods=['POST'])
@admin_required
def admin_schedule_hours():
    year = int(request.form['year'])
    month = int(request.form['month'])
    hours_abvg = int(request.form.get('hours_abvg', 160))
    hours_rde = int(request.form.get('hours_rde', 160))
    db = get_db()
    db.execute(
        'INSERT OR REPLACE INTO month_settings (year, month, hours_abvg, hours_rde) VALUES (?,?,?,?)',
        (year, month, hours_abvg, hours_rde)
    )
    db.commit()
    db.close()
    flash('Часовете за месеца са запазени.', 'success')
    return redirect(url_for('admin_schedule', year=year, month=month))


# ── ADMIN: ОТПУСКИ ────────────────────────────────────────────────────────────

@app.route('/admin/vacations')
@admin_required
def admin_vacations():
    db = get_db()
    requests = db.execute(
        '''SELECT vr.*, u.name as emp_name, u.tab_number, u2.name as appr_name
           FROM vacation_requests vr
           JOIN users u ON vr.employee_id = u.id
           LEFT JOIN users u2 ON vr.approved_by = u2.id
           ORDER BY CASE vr.status WHEN 'pending' THEN 0 ELSE 1 END,
                    vr.requested_at DESC'''
    ).fetchall()
    db.close()
    return render_template('admin/vacations.html', requests=requests)


@app.route('/admin/vacations/<int:req_id>/<action>', methods=['POST'])
@admin_required
def handle_vacation(req_id, action):
    if action not in ('approve', 'reject'):
        return redirect(url_for('admin_vacations'))

    db = get_db()
    req = db.execute('SELECT * FROM vacation_requests WHERE id=?', (req_id,)).fetchone()

    if req and req['status'] == 'pending':
        status = 'approved' if action == 'approve' else 'rejected'
        db.execute(
            'UPDATE vacation_requests SET status=?, approved_by=?, approved_at=? WHERE id=?',
            (status, session['user_id'], datetime.now().isoformat(), req_id)
        )

        from_date = datetime.strptime(req['date_from'], '%Y-%m-%d').date()
        to_date = datetime.strptime(req['date_to'], '%Y-%m-%d').date()
        current = from_date

        if action == 'approve':
            while current <= to_date:
                db.execute(
                    '''INSERT OR REPLACE INTO schedule_entries
                       (employee_id, year, month, day, code, leave_status)
                       VALUES (?, ?, ?, ?, '0', 'approved')''',
                    (req['employee_id'], current.year, current.month, current.day)
                )
                current += timedelta(days=1)
            db.execute(
                'UPDATE users SET vacation_days_remaining = vacation_days_remaining - ? WHERE id=?',
                (req['days_count'], req['employee_id'])
            )
            flash('Отпуската е одобрена.', 'success')
        else:
            while current <= to_date:
                db.execute(
                    '''DELETE FROM schedule_entries
                       WHERE employee_id=? AND year=? AND month=? AND day=?
                         AND leave_status='planned' ''',
                    (req['employee_id'], current.year, current.month, current.day)
                )
                current += timedelta(days=1)
            flash('Отпуската е отхвърлена.', 'warning')

        db.commit()
    db.close()
    return redirect(url_for('admin_vacations'))


# ── ADMIN: СЛУЖИТЕЛИ ──────────────────────────────────────────────────────────

@app.route('/admin/employees')
@admin_required
def admin_employees():
    db = get_db()
    employees = db.execute(
        'SELECT * FROM users ORDER BY CAST(tab_number AS INTEGER)'
    ).fetchall()
    db.close()
    return render_template('admin/employees.html',
                           employees=employees, SMYANA_OPTIONS=SMYANA_OPTIONS)


@app.route('/admin/employees/add', methods=['POST'])
@admin_required
def add_employee():
    tab = request.form['tab_number'].strip()
    name = request.form['name'].strip()
    smyana = request.form['smyana'].strip().upper()
    username = request.form['username'].strip()
    password = request.form['password']
    role = request.form.get('role', 'employee')
    vac_total = int(request.form.get('vacation_days_total', 20))

    db = get_db()
    try:
        db.execute(
            '''INSERT INTO users
               (tab_number, name, smyana, username, password_hash, role,
                vacation_days_total, vacation_days_remaining)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (tab, name, smyana, username,
             generate_password_hash(password), role, vac_total, vac_total)
        )
        db.commit()
        flash(f'Служителят {name} е добавен.', 'success')
    except sqlite3.IntegrityError as e:
        flash(f'Грешка: {e}', 'danger')
    db.close()
    return redirect(url_for('admin_employees'))


@app.route('/admin/employees/<int:emp_id>/edit', methods=['POST'])
@admin_required
def edit_employee(emp_id):
    name = request.form['name'].strip()
    smyana = request.form['smyana'].strip().upper()
    role = request.form.get('role', 'employee')
    vac_total = int(request.form.get('vacation_days_total', 20))
    vac_remaining = int(request.form.get('vacation_days_remaining', 20))

    db = get_db()
    db.execute(
        '''UPDATE users SET name=?, smyana=?, role=?,
           vacation_days_total=?, vacation_days_remaining=? WHERE id=?''',
        (name, smyana, role, vac_total, vac_remaining, emp_id)
    )
    pw = request.form.get('password', '').strip()
    if pw:
        db.execute(
            'UPDATE users SET password_hash=? WHERE id=?',
            (generate_password_hash(pw), emp_id)
        )
    db.commit()
    db.close()
    flash('Данните са обновени.', 'success')
    return redirect(url_for('admin_employees'))


# ── АНУЛИРАНЕ / ПРОМЯНА НА ОТПУСКА ──────────────────────────────────────────

@app.route('/vacation/<int:req_id>/cancel', methods=['POST'])
@login_required
def cancel_vacation(req_id):
    db = get_db()
    req = db.execute('SELECT * FROM vacation_requests WHERE id=?', (req_id,)).fetchone()

    is_own_pending = (req and req['employee_id'] == session['user_id']
                      and req['status'] == 'pending')
    is_admin = session.get('role') == 'admin'

    if req and (is_own_pending or is_admin) and req['status'] in ('pending', 'approved'):
        db.execute("UPDATE vacation_requests SET status='cancelled' WHERE id=?", (req_id,))
        from_date = datetime.strptime(req['date_from'], '%Y-%m-%d').date()
        to_date   = datetime.strptime(req['date_to'],   '%Y-%m-%d').date()
        current = from_date
        while current <= to_date:
            db.execute(
                "DELETE FROM schedule_entries WHERE employee_id=? AND year=? AND month=? AND day=? AND code='0'",
                (req['employee_id'], current.year, current.month, current.day)
            )
            current += timedelta(days=1)
        if req['status'] == 'approved':
            db.execute(
                'UPDATE users SET vacation_days_remaining = vacation_days_remaining + ? WHERE id=?',
                (req['days_count'], req['employee_id'])
            )
        db.commit()
        flash('Отпуската е анулирана.', 'info')
    else:
        flash('Нямате право или отпуската не може да се анулира.', 'danger')

    db.close()
    return redirect(url_for('admin_vacations') if is_admin else url_for('my_schedule'))


@app.route('/admin/vacation/<int:req_id>/modify', methods=['POST'])
@admin_required
def modify_vacation(req_id):
    db = get_db()
    req = db.execute('SELECT * FROM vacation_requests WHERE id=?', (req_id,)).fetchone()

    if not req or req['status'] not in ('pending', 'approved'):
        flash('Не може да се промени тази заявка.', 'danger')
        db.close()
        return redirect(url_for('admin_vacations'))

    new_from_str = request.form['date_from']
    new_to_str   = request.form['date_to']
    new_from = datetime.strptime(new_from_str, '%Y-%m-%d').date()
    new_to   = datetime.strptime(new_to_str,   '%Y-%m-%d').date()

    if new_from > new_to:
        flash('Невалидни дати.', 'danger')
        db.close()
        return redirect(url_for('admin_vacations'))

    holidays_set = get_holidays_set(db)

    # Премахни стари записи в графика
    old_from = datetime.strptime(req['date_from'], '%Y-%m-%d').date()
    old_to   = datetime.strptime(req['date_to'],   '%Y-%m-%d').date()
    current = old_from
    while current <= old_to:
        db.execute(
            "DELETE FROM schedule_entries WHERE employee_id=? AND year=? AND month=? AND day=? AND code='0'",
            (req['employee_id'], current.year, current.month, current.day)
        )
        current += timedelta(days=1)

    # Върни стари дни ако отпуската е одобрена
    if req['status'] == 'approved':
        db.execute(
            'UPDATE users SET vacation_days_remaining = vacation_days_remaining + ? WHERE id=?',
            (req['days_count'], req['employee_id'])
        )

    new_days = count_working_days(new_from, new_to, holidays_set)
    new_status = req['status']

    # Добави нови записи
    current = new_from
    while current <= new_to:
        if current.weekday() < 5 and current.isoformat() not in holidays_set:
            db.execute(
                '''INSERT OR REPLACE INTO schedule_entries
                   (employee_id, year, month, day, code, leave_status)
                   VALUES (?, ?, ?, ?, '0', ?)''',
                (req['employee_id'], current.year, current.month, current.day,
                 'approved' if new_status == 'approved' else 'planned')
            )
        current += timedelta(days=1)

    if req['status'] == 'approved':
        db.execute(
            'UPDATE users SET vacation_days_remaining = vacation_days_remaining - ? WHERE id=?',
            (new_days, req['employee_id'])
        )

    db.execute(
        '''UPDATE vacation_requests SET date_from=?, date_to=?, days_count=? WHERE id=?''',
        (new_from_str, new_to_str, new_days, req_id)
    )
    db.commit()
    db.close()
    flash(f'Отпуската е променена ({new_days} работни дни).', 'success')
    return redirect(url_for('admin_vacations'))


# ── ADMIN: УПРАВЛЕНИЕ НА ПРАЗНИЦИ ────────────────────────────────────────────

@app.route('/admin/holidays')
@admin_required
def admin_holidays():
    db = get_db()
    holidays = db.execute('SELECT * FROM holidays ORDER BY date').fetchall()
    db.close()
    return render_template('admin/holidays.html', holidays=holidays)


@app.route('/admin/holidays/add', methods=['POST'])
@admin_required
def add_holiday():
    d = request.form['date'].strip()
    name = request.form['name'].strip()
    db = get_db()
    try:
        db.execute('INSERT INTO holidays (date, name) VALUES (?, ?)', (d, name))
        db.commit()
        flash(f'Добавен: {d} – {name}', 'success')
    except Exception:
        flash('Датата вече съществува.', 'danger')
    db.close()
    return redirect(url_for('admin_holidays'))


@app.route('/admin/holidays/<int:hid>/delete', methods=['POST'])
@admin_required
def delete_holiday(hid):
    db = get_db()
    db.execute('DELETE FROM holidays WHERE id=?', (hid,))
    db.commit()
    db.close()
    flash('Празникът е изтрит.', 'info')
    return redirect(url_for('admin_holidays'))


@app.route('/api/holidays')
@login_required
def api_holidays():
    db = get_db()
    holidays = db.execute('SELECT date FROM holidays').fetchall()
    db.close()
    return jsonify([r['date'] for r in holidays])


# ── НАСТРОЙКИ НА ПОТРЕБИТЕЛЯ ─────────────────────────────────────────────────

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def user_settings():
    db = get_db()
    if request.method == 'POST':
        db.execute(
            '''UPDATE users SET
               notify_minutes_before=?,
               notify_day_before=?,
               notify_day_before_time=?,
               notify_punch_card=?
               WHERE id=?''',
            (
                request.form.get('notify_minutes_before', '60'),
                '1' if request.form.get('notify_day_before') else '0',
                request.form.get('notify_day_before_time', '19:00'),
                '1' if request.form.get('notify_punch_card') else '0',
                session['user_id'],
            )
        )
        db.commit()
        db.close()
        flash('Настройките са запазени.', 'success')
        return redirect(url_for('user_settings'))

    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    shift_times = get_shift_times(db)
    db.close()
    return render_template('settings.html', user=user, shift_times=shift_times)


# ── ADMIN: ВРЕМЕНА НА СМЕНИТЕ ─────────────────────────────────────────────────

@app.route('/admin/shift-times', methods=['POST'])
@admin_required
def admin_shift_times():
    db = get_db()
    for key in ['shift_1_start', 'shift_1_hours',
                'shift_2_start', 'shift_2_hours',
                'shift_8_start', 'shift_8_hours']:
        val = request.form.get(key, '')
        if val:
            db.execute('INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)',
                       (key, val))
    db.commit()
    db.close()
    flash('Времената на смените са запазени.', 'success')
    return redirect(url_for('user_settings'))


# ── ICS КАЛЕНДАРЕН ЕКСПОРТ ────────────────────────────────────────────────────

@app.route('/my-schedule/export/<int:year>/<int:month>.ics')
@login_required
def export_ics(year, month):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    entries_raw = db.execute(
        'SELECT * FROM schedule_entries WHERE employee_id=? AND year=? AND month=?',
        (session['user_id'], year, month)
    ).fetchall()
    shift_times = get_shift_times(db)
    db.close()

    schedule = {e['day']: e for e in entries_raw}

    notify_before = int(user['notify_minutes_before'] or 60)
    day_before = str(user['notify_day_before'] or '1') == '1'
    day_before_time = user['notify_day_before_time'] or '19:00'
    punch_card = str(user['notify_punch_card'] or '1') == '1'

    CODE_NAMES = {
        '1': 'Диспечерска смяна', '2': 'Нощна смяна',
        '8': 'Дневна смяна', 'Б': 'Болничен', 'Н': 'Неявяване',
    }

    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Graf Avtomatizaciya//BG',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        f'X-WR-CALNAME:График - {user["name"]}',
        'X-WR-TIMEZONE:Europe/Sofia',
    ]

    for day in sorted(schedule.keys()):
        entry = schedule[day]
        code = (entry['code'] or '').strip()
        if not code or code in ('0', 'П', ''):
            continue

        key_start = f'shift_{code}_start'
        key_hours = f'shift_{code}_hours'
        if key_start not in shift_times:
            continue

        try:
            sh, sm_v = map(int, shift_times[key_start].split(':'))
            duration_h = float(shift_times[key_hours])
        except Exception:
            sh, sm_v, duration_h = 8, 0, 8.0

        shift_start = datetime(year, month, day, sh, sm_v)
        shift_end = shift_start + timedelta(hours=duration_h)
        code_name = CODE_NAMES.get(code, code)

        dtstart = shift_start.strftime('%Y%m%dT%H%M%S')
        dtend = shift_end.strftime('%Y%m%dT%H%M%S')
        uid_val = str(uuid.uuid4())

        lines += [
            'BEGIN:VEVENT',
            f'UID:{uid_val}',
            f'DTSTART:{dtstart}',
            f'DTEND:{dtend}',
            f'SUMMARY:Работа - {code_name}',
            f'DESCRIPTION:у-к Автоматизация\\n{MONTH_NAMES[month]} {year}',
        ]

        if notify_before > 0:
            lines += [
                'BEGIN:VALARM',
                'ACTION:DISPLAY',
                f'TRIGGER:-PT{notify_before}M',
                f'DESCRIPTION:Работа след {notify_before} мин.!',
                'END:VALARM',
            ]

        if punch_card:
            lines += [
                'BEGIN:VALARM',
                'ACTION:DISPLAY',
                'TRIGGER:PT0M',
                'DESCRIPTION:Не забравяй да удариш картата!',
                'END:VALARM',
            ]

        if day_before:
            try:
                dbh, dbm_v = map(int, day_before_time.split(':'))
            except Exception:
                dbh, dbm_v = 19, 0
            prev_day = shift_start.replace(hour=dbh, minute=dbm_v) - timedelta(days=1)
            diff_min = int((shift_start - prev_day).total_seconds() / 60)
            if diff_min > 0:
                lines += [
                    'BEGIN:VALARM',
                    'ACTION:DISPLAY',
                    f'TRIGGER:-PT{diff_min}M',
                    f'DESCRIPTION:Утре работиш - {code_name}!',
                    'END:VALARM',
                ]

        lines.append('END:VEVENT')

    lines.append('END:VCALENDAR')
    content = '\r\n'.join(lines) + '\r\n'

    return Response(
        content,
        mimetype='text/calendar; charset=utf-8',
        headers={
            'Content-Disposition':
                f'attachment; filename="grafik_{year}_{month:02d}.ics"'
        }
    )


# ── ADMIN: ПОСТАВЯНЕ НА РЕД ───────────────────────────────────────────────────

@app.route('/admin/schedule/paste-row', methods=['POST'])
@admin_required
def admin_paste_row():
    data = request.json
    target_emp_id = int(data['target_emp_id'])
    year = int(data['year'])
    month = int(data['month'])
    codes = data['codes']  # {day: code}

    db = get_db()
    skipped = []
    for day_str, code in codes.items():
        day = int(day_str)
        if code == '2':
            conflict = db.execute(
                '''SELECT u.name FROM schedule_entries se
                   JOIN users u ON se.employee_id = u.id
                   WHERE se.employee_id != ? AND se.year=? AND se.month=? AND se.day=? AND se.code='2' ''',
                (target_emp_id, year, month, day)
            ).fetchone()
            if conflict:
                skipped.append(f'{day} ({conflict["name"]})')
                continue
        if code == '':
            db.execute(
                'DELETE FROM schedule_entries WHERE employee_id=? AND year=? AND month=? AND day=?',
                (target_emp_id, year, month, day)
            )
        else:
            leave_status = 'approved' if code == '0' else 'normal'
            db.execute(
                '''INSERT OR REPLACE INTO schedule_entries
                   (employee_id, year, month, day, code, leave_status)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (target_emp_id, year, month, day, code, leave_status)
            )
    db.commit()
    db.close()
    return jsonify({'ok': True, 'skipped': skipped})


if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print('ГРЕШКА: Базата данни не съществува. Стартирайте init_db.py първо.')
    else:
        ensure_schema()
        app.run(debug=True, host='0.0.0.0', port=5000)
