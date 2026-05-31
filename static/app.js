// ── Константи ────────────────────────────────────────────────────────────────

const HOURS_MAP = { '1': 12, '2': 13.143, '8': 8, '0': 8, 'Б': 0, 'Н': 8, 'П': 0 };
const COLOR_MAP = {
  '1': 'cell-1', '2': 'cell-2', '8': 'cell-8',
  '0': 'cell-approved', 'Б': 'cell-sick', 'Н': 'cell-n', 'П': 'cell-p',
};
const ALL_CELL_CLASSES = [
  'cell-1','cell-2','cell-8','cell-approved','cell-planned',
  'cell-sick','cell-n','cell-p','cell-weekend-bg',
];

// Клавиши → код (поддържа и кирилица)
const KEY_MAP = {
  '1':'1', '2':'2', '8':'8', '0':'0',
  'b':'Б', 'B':'Б', 'б':'Б', 'Б':'Б',
  'n':'Н', 'N':'Н', 'н':'Н', 'Н':'Н',
  'p':'П', 'P':'П', 'п':'П', 'П':'П',
};

// ── Глобално состояние ───────────────────────────────────────────────────────

let activeCell = null;        // текущо активна клетка
let copiedRowData = null;     // копиран ред { empId, codes:{day:code} }
const editModal = new bootstrap.Modal(document.getElementById('editModal'));

// ── Помощни функции ──────────────────────────────────────────────────────────

function allEditableCells() {
  return Array.from(document.querySelectorAll('.sched-editable'));
}

function setActive(cell) {
  if (activeCell) activeCell.classList.remove('cell-active');
  activeCell = cell;
  if (cell) {
    cell.classList.add('cell-active');
    cell.focus({ preventScroll: false });
    cell.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }
}

function applyCodeToCell(cell, code, originalCode) {
  ALL_CELL_CLASSES.forEach(c => cell.classList.remove(c));
  if (code && COLOR_MAP[code]) {
    cell.classList.add(COLOR_MAP[code]);
  } else if (!code && cell.dataset.weekend === 'true') {
    cell.classList.add('cell-weekend-bg');
  }
  cell.dataset.code = code;
  if (code === 'Б') {
    if (originalCode) {
      cell.dataset.originalCode = originalCode;
      cell.innerHTML = 'Б<sup class="orig-sup">' + originalCode + '</sup>';
    } else {
      delete cell.dataset.originalCode;
      cell.textContent = '';
    }
  } else {
    delete cell.dataset.originalCode;
    cell.textContent = code;
  }
  recalcRow(cell.closest('tr'));
}

async function saveCell(cell, code) {
  const prevCode = cell.dataset.code || '';
  const payload = {
    employee_id: parseInt(cell.dataset.empId),
    year:  parseInt(cell.dataset.year),
    month: parseInt(cell.dataset.month),
    day:   parseInt(cell.dataset.day),
    code,
  };
  if (code === 'Б') {
    payload.original_code = prevCode;
  }
  const resp = await fetch('/admin/schedule/cell', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await resp.json();
  if (data.conflict) {
    alert(data.msg);
    return false;
  }
  applyCodeToCell(cell, code, code === 'Б' ? prevCode : null);
  return true;
}

const hoursToastEl = document.getElementById('hoursToast');
const hoursToastInst = hoursToastEl ? new bootstrap.Toast(hoursToastEl, { delay: 4000 }) : null;

function recalcRow(row) {
  let total = 0;
  row.querySelectorAll('.sched-editable').forEach(cell => {
    const c = cell.dataset.code || '';
    if (c === 'Б') {
      const orig = cell.dataset.originalCode || '';
      total += HOURS_MAP[orig] || 0;
    } else if (HOURS_MAP[c] !== undefined) {
      total += HOURS_MAP[c];
    }
  });
  total = Math.round(total * 10) / 10;

  const hCell = row.querySelector('.hours-cell');
  if (!hCell) return;
  const target = parseInt(hCell.dataset.target) || 0;
  const disp = total % 1 === 0 ? String(total) : total.toFixed(1);
  hCell.innerHTML = disp + (target ? `<br><small class="fw-normal text-muted">/${target}</small>` : '');

  const wasBelow = hCell.classList.contains('hours-danger-bg');
  hCell.classList.remove('text-danger', 'text-success', 'hours-danger-bg');

  if (target) {
    if (total < target) {
      hCell.classList.add('text-danger', 'hours-danger-bg');
      if (!wasBelow && hoursToastInst) {
        const empName = hCell.dataset.empName || '';
        const deficit = Math.round((target - total) * 10) / 10;
        document.getElementById('hoursToastName').textContent = empName;
        document.getElementById('hoursToastMsg').textContent =
          `часовете паднаха под нормата (${total} / ${target} ч., липсват ${deficit} ч.)`;
        hoursToastInst.show();
      }
    } else {
      hCell.classList.add('text-success');
    }
  }
}

// ── Навигация ─────────────────────────────────────────────────────────────────

function navigate(cell, dir) {
  const cells = allEditableCells();
  const idx = cells.indexOf(cell);
  if (idx === -1) return;

  const days = parseInt(cell.closest('table').querySelector('.col-day') ?
    cell.closest('table').querySelectorAll('.col-day').length : 31);

  let next = null;
  if (dir === 'right')  next = cells[idx + 1];
  if (dir === 'left')   next = cells[idx - 1];
  if (dir === 'down')   next = cells[idx + days];
  if (dir === 'up')     next = cells[idx - days];
  if (next) setActive(next);
}

// ── Клик на клетка ────────────────────────────────────────────────────────────

document.querySelectorAll('.sched-editable').forEach(cell => {
  cell.setAttribute('tabindex', '-1');

  cell.addEventListener('click', (e) => {
    e.stopPropagation();
    setActive(cell);
  });

  cell.addEventListener('dblclick', () => {
    setActive(cell);
    openEditModal(cell);
  });
});

// ── Клавиатурни преки пътища ──────────────────────────────────────────────────

document.addEventListener('keydown', async (e) => {
  if (!activeCell) return;

  // Навигация
  if (e.key === 'ArrowRight') { e.preventDefault(); navigate(activeCell, 'right'); return; }
  if (e.key === 'ArrowLeft')  { e.preventDefault(); navigate(activeCell, 'left');  return; }
  if (e.key === 'ArrowDown')  { e.preventDefault(); navigate(activeCell, 'down');  return; }
  if (e.key === 'ArrowUp')    { e.preventDefault(); navigate(activeCell, 'up');    return; }
  if (e.key === 'Tab') {
    e.preventDefault();
    navigate(activeCell, e.shiftKey ? 'left' : 'right');
    return;
  }

  // Отваря модал
  if (e.key === 'Enter' || e.key === 'F2') {
    e.preventDefault();
    openEditModal(activeCell);
    return;
  }

  // Изтриване
  if (e.key === 'Delete' || e.key === 'Backspace') {
    e.preventDefault();
    saveCell(activeCell, '');
    return;
  }

  // Директен код
  if (KEY_MAP[e.key] !== undefined) {
    e.preventDefault();
    const cell = activeCell;
    const ok = await saveCell(cell, KEY_MAP[e.key]);
    if (ok) navigate(cell, 'right');
    return;
  }
});

// При клик извън таблицата → махни активна
document.addEventListener('click', (e) => {
  if (!e.target.closest('.schedule-table')) {
    if (activeCell) activeCell.classList.remove('cell-active');
    activeCell = null;
  }
});

// ── Модален прозорец ──────────────────────────────────────────────────────────

function openEditModal(cell) {
  document.getElementById('modal-name').textContent = cell.dataset.empName;
  document.getElementById('modal-date').textContent =
    `${cell.dataset.day}.${String(cell.dataset.month).padStart(2,'0')}.${cell.dataset.year}`;
  document.getElementById('modal-code').value = cell.dataset.code || '';
  editModal.show();
}

document.getElementById('modal-save').addEventListener('click', async () => {
  if (!activeCell) return;
  const code = document.getElementById('modal-code').value;
  document.getElementById('modal-saving').classList.remove('d-none');
  document.getElementById('modal-save').disabled = true;
  try {
    const ok = await saveCell(activeCell, code);
    if (ok) editModal.hide();
  } finally {
    document.getElementById('modal-saving').classList.add('d-none');
    document.getElementById('modal-save').disabled = false;
  }
});

document.getElementById('editModal').addEventListener('hidden.bs.modal', () => {
  // Keep active cell selected after modal close
});

// ── Копиране / Поставяне на ред ───────────────────────────────────────────────

const copyToast = document.getElementById('copyToast');
const toastInst = copyToast ? new bootstrap.Toast(copyToast, { delay: 3000 }) : null;

document.querySelectorAll('.btn-copy-row').forEach(btn => {
  btn.addEventListener('click', () => {
    const row = btn.closest('tr');
    const empId = row.dataset.empId;
    const codes = {};
    row.querySelectorAll('.sched-editable').forEach(cell => {
      codes[cell.dataset.day] = cell.dataset.code || '';
    });
    copiedRowData = { empId, codes };

    // Show paste buttons
    document.querySelectorAll('.btn-paste-row').forEach(pb => {
      pb.closest('tr').dataset.empId !== empId
        ? pb.classList.remove('d-none')
        : pb.classList.add('d-none');
    });

    if (toastInst) {
      document.getElementById('copyToastName').textContent =
        btn.dataset.empName || 'Ред';
      toastInst.show();
    }
  });
});

document.querySelectorAll('.btn-paste-row').forEach(btn => {
  btn.addEventListener('click', async () => {
    if (!copiedRowData) return;
    const targetRow = btn.closest('tr');
    const targetEmpId = parseInt(targetRow.dataset.empId);
    const year  = parseInt(btn.dataset.year);
    const month = parseInt(btn.dataset.month);

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

    try {
      const resp = await fetch('/admin/schedule/paste-row', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_emp_id: targetEmpId,
          year, month,
          codes: copiedRowData.codes,
        }),
      });

      const data = await resp.json();
      if (data.ok) {
        if (data.skipped && data.skipped.length > 0) {
          alert('Внимание: Следните дни не са поставени (нощна смяна вече заета):\nДен ' + data.skipped.join(', ден '));
          location.reload();
        } else {
          targetRow.querySelectorAll('.sched-editable').forEach(cell => {
            const newCode = copiedRowData.codes[cell.dataset.day] || '';
            applyCodeToCell(cell, newCode);
          });
          btn.classList.add('d-none');
        }
      }
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-clipboard-check"></i>';
    }
  });
});
