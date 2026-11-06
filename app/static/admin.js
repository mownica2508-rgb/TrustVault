const tokenKey = 'trustvault_access_token';
const rows = document.querySelector('#activity-rows');
const alertBox = document.querySelector('#admin-alert');
const pageSize = 25;
let pageOffset = 0;
let totalRows = 0;
let currentAdminId = null;

function authHeaders() {
  return { Authorization: `Bearer ${sessionStorage.getItem(tokenKey) || ''}` };
}

async function requestJson(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('Authorization', authHeaders().Authorization);
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    let detail = 'Could not load administrator activity.';
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch (_) { /* Keep the default error. */ }
    if (response.status === 401) {
      sessionStorage.removeItem(tokenKey);
      window.location.assign('/');
    }
    throw new Error(detail);
  }
  return response.json();
}

function showAlert(text, isError = false) {
  alertBox.textContent = text;
  alertBox.classList.toggle('visible', Boolean(text));
  alertBox.classList.toggle('error', isError);
}

function setText(selector, value) {
  document.querySelector(selector).textContent = value;
}

function formatDate(value, options = {}) {
  return new Intl.DateTimeFormat(undefined, options).format(new Date(value));
}

function renderChart(points) {
  const chart = document.querySelector('#activity-chart');
  chart.replaceChildren();
  const max = Math.max(1, ...points.map(point => point.count));
  for (const point of points) {
    const column = document.createElement('div');
    column.className = 'chart-column';
    const value = document.createElement('span');
    value.className = 'chart-value';
    value.textContent = String(point.count);
    const track = document.createElement('div');
    track.className = 'chart-track';
    const bar = document.createElement('div');
    bar.className = 'chart-bar';
    bar.style.height = `${point.count ? Math.max(8, (point.count / max) * 100) : 3}%`;
    bar.title = `${point.count} event${point.count === 1 ? '' : 's'}`;
    track.append(bar);
    const label = document.createElement('span');
    label.className = 'chart-label';
    label.textContent = formatDate(`${point.date}T12:00:00`, { weekday: 'short' });
    column.append(value, track, label);
    chart.append(column);
  }
}

async function loadOverview() {
  const [summary, integrity] = await Promise.all([
    requestJson('/api/admin/overview'),
    requestJson('/api/admin/audit-integrity'),
  ]);
  setText('#metric-users', summary.total_users.toLocaleString());
  setText('#metric-documents', summary.total_documents.toLocaleString());
  setText('#metric-shares', summary.active_shares.toLocaleString());
  setText('#metric-events', summary.events_last_7_days.toLocaleString());
  setText('#metric-denied', summary.denied_last_7_days.toLocaleString());
  setText('#pulse-denied', summary.denied_last_7_days.toLocaleString());
  renderChart(summary.daily_events);
  const alertList = document.querySelector('#security-alerts');
  alertList.replaceChildren();
  if (!summary.security_alerts.length) {
    const quiet = document.createElement('p');
    quiet.textContent = 'No account has reached the unusual-denial threshold in the last hour.';
    alertList.append(quiet);
  } else {
    for (const alert of summary.security_alerts) {
      const item = document.createElement('article');
      item.className = 'security-alert-item';
      const title = document.createElement('strong');
      title.textContent = `${alert.denied_count} denied requests in the last hour`;
      const actor = document.createElement('small');
      actor.textContent = `${alert.name} · ${alert.email}`;
      item.append(title, actor);
      alertList.append(item);
    }
  }
  const integrityTitle = !integrity.valid
    ? 'Audit chain integrity problem'
    : integrity.legacy_unsealed_events
      ? 'New audit chain verified'
      : 'Audit chain verified';
  setText('#audit-integrity-title', integrityTitle);
  setText('#audit-integrity-detail', `${integrity.sealed_events} sealed events checked · ${integrity.legacy_unsealed_events} older unsealed events`);
  document.querySelector('#audit-integrity-title').classList.toggle('integrity-failed', !integrity.valid);
}

function queryString() {
  const params = new URLSearchParams({ limit: String(pageSize), offset: String(pageOffset) });
  const search = document.querySelector('#activity-search').value.trim();
  const action = document.querySelector('#activity-action').value;
  const outcome = document.querySelector('#activity-outcome').value;
  const from = document.querySelector('#activity-from').value;
  const to = document.querySelector('#activity-to').value;
  if (search) params.set('search', search);
  if (action) params.set('action', action);
  if (outcome) params.set('outcome', outcome);
  if (from) params.set('date_from', `${from}T00:00:00`);
  if (to) params.set('date_to', `${to}T23:59:59`);
  return params.toString();
}

const actionLabels = {
  upload: 'Uploaded document', view: 'Previewed document', download: 'Downloaded document',
  metadata_read: 'Opened document details', metadata_update: 'Updated document details',
  file_replace: 'Replaced document file', delete: 'Deleted document',
  version_list: 'Viewed version history', version_download: 'Downloaded file version',
  version_restore: 'Restored file version',
  permission_granted: 'Granted document access', permission_updated: 'Changed access level',
  permission_revoked: 'Revoked document access', grant_permission: 'Tried to share document',
  account_disabled: 'Disabled account', account_enabled: 'Re-enabled account',
  list_permissions: 'Viewed sharing list', admin_access: 'Tried to open admin console',
};

function appendDetails(row, details) {
  const detailRow = document.createElement('tr');
  detailRow.className = 'details-row';
  const cell = document.createElement('td');
  cell.colSpan = 6;
  const content = document.createElement('pre');
  content.textContent = details;
  cell.append(content);
  detailRow.append(cell);
  row.after(detailRow);
}

function renderEvent(event) {
  const row = document.createElement('tr');
  const actionCell = document.createElement('td');
  actionCell.className = 'event-action';
  const glyph = document.createElement('span');
  glyph.className = `event-glyph ${event.outcome === 'denied' ? 'glyph-denied' : 'glyph-allowed'}`;
  glyph.textContent = event.outcome === 'denied' ? '!' : '↗';
  const actionText = document.createElement('span');
  actionText.textContent = actionLabels[event.action] || event.action.replaceAll('_', ' ');
  actionCell.append(glyph, actionText);

  const actorCell = document.createElement('td');
  const actorName = document.createElement('strong');
  actorName.textContent = event.actor_name || 'Unknown account';
  const actorEmail = document.createElement('small');
  actorEmail.textContent = event.actor_email || 'Account no longer available';
  actorCell.append(actorName, actorEmail);

  const documentCell = document.createElement('td');
  const documentName = document.createElement('strong');
  documentName.textContent = event.document_title || (event.document_id ? `Document #${event.document_id}` : '—');
  documentCell.append(documentName);

  const resultCell = document.createElement('td');
  const pill = document.createElement('span');
  pill.className = `result-pill ${event.outcome === 'denied' ? 'blocked' : 'allowed'}`;
  pill.textContent = event.outcome === 'denied' ? 'DENIED' : 'ALLOWED';
  resultCell.append(pill);

  const whenCell = document.createElement('td');
  whenCell.className = 'event-time';
  whenCell.textContent = formatDate(event.created_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  const moreCell = document.createElement('td');
  if (event.details) {
    const more = document.createElement('button');
    more.type = 'button';
    more.className = 'more-button';
    more.textContent = '•••';
    more.setAttribute('aria-label', 'Show event details');
    more.title = 'Show event details';
    more.addEventListener('click', () => {
      const next = row.nextElementSibling;
      if (next?.classList.contains('details-row')) next.remove();
      else appendDetails(row, event.details);
    });
    moreCell.append(more);
  }
  row.append(actionCell, actorCell, documentCell, resultCell, whenCell, moreCell);
  return row;
}

async function loadActivity() {
  rows.replaceChildren();
  const loading = document.createElement('tr');
  const loadingCell = document.createElement('td');
  loadingCell.colSpan = 6;
  loadingCell.className = 'activity-empty';
  loadingCell.textContent = 'Loading the audit trail…';
  loading.append(loadingCell);
  rows.append(loading);
  const data = await requestJson(`/api/admin/activity?${queryString()}`);
  totalRows = data.total;
  rows.replaceChildren();
  if (!data.items.length) {
    const empty = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 6;
    cell.className = 'activity-empty';
    cell.textContent = 'No audit events match these filters.';
    empty.append(cell);
    rows.append(empty);
  } else {
    for (const event of data.items) rows.append(renderEvent(event));
  }
  const page = Math.floor(pageOffset / pageSize) + 1;
  const lastPage = Math.max(1, Math.ceil(totalRows / pageSize));
  setText('#result-count', `${totalRows.toLocaleString()} event${totalRows === 1 ? '' : 's'}`);
  setText('#page-label', `Page ${page} of ${lastPage}`);
  document.querySelector('#previous-page').disabled = pageOffset === 0;
  document.querySelector('#next-page').disabled = pageOffset + pageSize >= totalRows;
}

async function loadUsers() {
  const rows = document.querySelector('#user-rows');
  rows.replaceChildren();
  const search = document.querySelector('#users-search').value.trim();
  const params = new URLSearchParams({ limit: '200' });
  if (search) params.set('search', search);
  const users = await requestJson(`/api/admin/users?${params.toString()}`);
  if (!users.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 5;
    cell.className = 'activity-empty';
    cell.textContent = 'No accounts match this search.';
    row.append(cell);
    rows.append(row);
    return;
  }
  for (const user of users) {
    const row = document.createElement('tr');
    const account = document.createElement('td');
    const name = document.createElement('strong');
    name.textContent = user.full_name;
    const email = document.createElement('small');
    email.textContent = user.email;
    account.append(name, email);
    const role = document.createElement('td');
    role.textContent = user.role === 'admin' ? 'Administrator' : 'Member';
    const state = document.createElement('td');
    const pill = document.createElement('span');
    pill.className = `result-pill ${user.is_active ? 'allowed' : 'blocked'}`;
    pill.textContent = user.is_active ? 'ACTIVE' : 'DISABLED';
    state.append(pill);
    const created = document.createElement('td');
    created.textContent = formatDate(user.created_at, { year: 'numeric', month: 'short', day: 'numeric' });
    const action = document.createElement('td');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'user-status-button';
    button.textContent = user.is_active ? 'Disable' : 'Re-enable';
    button.disabled = user.id === currentAdminId && user.is_active;
    button.addEventListener('click', async () => {
      const next = !user.is_active;
      const message = next
        ? `Disable ${user.full_name}? Their active shares will be revoked and will not return if the account is re-enabled.`
        : `Re-enable ${user.full_name}? Previously revoked shares will stay revoked.`;
      if (!window.confirm(message)) return;
      try {
        await requestJson(`/api/admin/users/${user.id}/status`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ is_active: next }),
        });
        showAlert(next ? 'Account disabled and related shares revoked.' : 'Account re-enabled; previous shares remain revoked.');
        await Promise.all([loadUsers(), loadOverview(), loadActivity()]);
      } catch (error) { showAlert(error.message, true); }
    });
    action.append(button);
    row.append(account, role, state, created, action);
    rows.append(row);
  }
}

async function loadDashboard() {
  showAlert('');
  try {
    const user = await requestJson('/api/auth/me');
    if (user.role !== 'admin') {
      showAlert('This page is for administrators. Sign in with the admin account to view activity.', true);
      document.querySelector('#admin-identity').textContent = `${user.full_name} · member`;
      rows.replaceChildren();
      return;
    }
    currentAdminId = user.id;
    setText('#admin-identity', `${user.full_name} · administrator`);
    setText('#admin-first-name', user.full_name.split(/\s+/)[0]);
    await Promise.all([loadOverview(), loadActivity(), loadUsers()]);
  } catch (error) {
    showAlert(error.message, true);
  }
}

document.querySelector('#activity-filters').addEventListener('submit', async event => {
  event.preventDefault();
  pageOffset = 0;
  try { await loadActivity(); } catch (error) { showAlert(error.message, true); }
});
document.querySelector('#clear-activity-filters').addEventListener('click', async () => {
  document.querySelector('#activity-filters').reset();
  pageOffset = 0;
  try { await loadActivity(); } catch (error) { showAlert(error.message, true); }
});
document.querySelector('#users-filter').addEventListener('submit', async event => {
  event.preventDefault();
  try { await loadUsers(); } catch (error) { showAlert(error.message, true); }
});
document.querySelector('#clear-users-search').addEventListener('click', async () => {
  document.querySelector('#users-search').value = '';
  try { await loadUsers(); } catch (error) { showAlert(error.message, true); }
});
document.querySelector('#previous-page').addEventListener('click', async () => {
  pageOffset = Math.max(0, pageOffset - pageSize);
  try { await loadActivity(); } catch (error) { showAlert(error.message, true); }
});
document.querySelector('#next-page').addEventListener('click', async () => {
  if (pageOffset + pageSize < totalRows) pageOffset += pageSize;
  try { await loadActivity(); } catch (error) { showAlert(error.message, true); }
});
document.querySelector('#refresh-dashboard').addEventListener('click', loadDashboard);
document.querySelector('#admin-logout').addEventListener('click', () => {
  sessionStorage.removeItem(tokenKey);
  window.location.assign('/');
});

if (!sessionStorage.getItem(tokenKey)) window.location.assign('/');
else loadDashboard();
