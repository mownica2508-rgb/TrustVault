const form = document.querySelector('#auth-form');
const message = document.querySelector('#message');
const nameWrap = document.querySelector('#name-wrap');
const fullName = document.querySelector('#full-name');
const password = document.querySelector('#password');
const formTitle = document.querySelector('#form-title');
const formHint = document.querySelector('#form-hint');
const submitButton = document.querySelector('#submit-button');
const authView = document.querySelector('#auth-view');
const workspace = document.querySelector('#documents-panel');
const accountPanel = document.querySelector('#account-panel');
const documentRows = document.querySelector('#document-rows');
const sharedRows = document.querySelector('#shared-rows');
const sharingStatusRows = document.querySelector('#sharing-status-rows');
const previewDialog = document.querySelector('#preview-dialog');
const previewFrame = document.querySelector('#preview-frame');
const shareDialog = document.querySelector('#share-dialog');
const versionsDialog = document.querySelector('#versions-dialog');
const shareMessage = document.querySelector('#share-message');
const shareExpiryMode = document.querySelector('#share-expiry-mode');
const shareExpiryFields = document.querySelector('#share-expiry-fields');
const shareExpiryInput = document.querySelector('#share-expires-at');
const uploadFile = document.querySelector('#upload-file');
const tokenKey = 'trustvault_access_token';

let mode = 'login';
let sharingDocument = null;
let previewObjectUrl = null;
let ownedDocuments = [];
let sharedDocuments = [];
let sharingStatus = [];

function showMessage(text, success = false) {
  message.textContent = text;
  message.classList.toggle('success', success);
}

function showDocumentMessage(text, success = false) {
  const target = document.querySelector('#workspace-message');
  target.textContent = text;
  target.classList.toggle('success', success);
  target.classList.toggle('visible', Boolean(text));
}

function syncShareExpiryFields() {
  const dateBased = shareExpiryMode.value === 'expires';
  shareExpiryFields.classList.toggle('hidden', !dateBased);
  shareExpiryInput.required = dateBased;
  if (!dateBased) shareExpiryInput.value = '';
}

function setMode(nextMode) {
  mode = nextMode;
  const registering = mode === 'register';
  document.querySelector('#login-tab').classList.toggle('active', !registering);
  document.querySelector('#register-tab').classList.toggle('active', registering);
  nameWrap.classList.toggle('hidden', !registering);
  fullName.required = registering;
  password.autocomplete = registering ? 'new-password' : 'current-password';
  formTitle.textContent = registering ? 'Create your account' : 'Welcome back';
  formHint.textContent = registering ? 'Set up your private workspace account.' : 'Sign in to continue to your workspace.';
  submitButton.textContent = registering ? 'Create account' : 'Sign in';
  showMessage('');
}

async function apiRequest(url, options = {}) {
  const token = sessionStorage.getItem(tokenKey);
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    sessionStorage.removeItem(tokenKey);
    window.location.reload();
    throw new Error('Your session expired. Please sign in again.');
  }
  if (!response.ok) {
    let detail = 'The request could not be completed.';
    try {
      const body = await response.json();
      detail = typeof body.detail === 'string' ? body.detail : detail;
    } catch (_) { /* Keep the generic message when the response is not JSON. */ }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  const contentType = response.headers.get('content-type') || '';
  return contentType.includes('application/json') ? response.json() : response;
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileKind(item) {
  if (item.content_type === 'application/pdf') return 'PDF';
  if (item.content_type === 'text/plain') return 'TXT';
  return 'DOCX';
}

function addActionButton(container, label, onClick, className = '') {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  if (className) button.className = className;
  button.addEventListener('click', onClick);
  container.append(button);
  return button;
}

async function previewDocument(item) {
  try {
    const response = await apiRequest(`/api/documents/${item.id}/view`);
    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = URL.createObjectURL(await response.blob());
    previewFrame.src = previewObjectUrl;
    document.querySelector('#preview-title').textContent = item.title;
    previewDialog.showModal();
  } catch (error) {
    showDocumentMessage(error.message);
  }
}

async function openShareDialog(item) {
  sharingDocument = item;
  document.querySelector('#share-document-name').textContent = `Choose a registered person to share “${item.title}” with.`;
  document.querySelector('#share-email').value = '';
  document.querySelector('#share-access').value = 'read';
  shareExpiryMode.value = 'until-revoked';
  shareExpiryInput.value = '';
  shareExpiryInput.min = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  syncShareExpiryFields();
  shareMessage.textContent = '';
  shareMessage.classList.remove('success');
  document.querySelector('#share-suggestions').replaceChildren();
  shareDialog.showModal();
  await Promise.all([loadGrants(), loadShareSuggestions()]);
}

async function openVersionHistory(item, isOwner) {
  const list = document.querySelector('#versions-list');
  document.querySelector('#versions-document-name').textContent = `${item.title} · earlier file versions`;
  list.replaceChildren();
  versionsDialog.showModal();
  try {
    const versions = await apiRequest(`/api/documents/${item.id}/versions`);
    if (!versions.length) {
      list.textContent = 'No saved versions are available.';
      return;
    }
    for (const version of versions) {
      const row = document.createElement('article');
      row.className = 'version-row';
      const info = document.createElement('div');
      const title = document.createElement('strong');
      title.textContent = `Version ${version.version_number}${version.is_current ? ' · CURRENT' : ''}`;
      const meta = document.createElement('small');
      const when = new Date(version.created_at).toLocaleString();
      meta.textContent = `${version.original_filename} · ${formatSize(version.size_bytes)} · ${when}${version.uploaded_by_name ? ` · ${version.uploaded_by_name}` : ''}`;
      info.append(title, meta);
      const actions = document.createElement('div');
      actions.className = 'version-actions';
      addActionButton(actions, 'Download', async () => {
        try {
          const response = await apiRequest(`/api/documents/${item.id}/versions/${version.id}/download`);
          const url = URL.createObjectURL(await response.blob());
          const link = document.createElement('a');
          link.href = url;
          link.download = version.original_filename;
          document.body.append(link);
          link.click();
          link.remove();
          window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (error) { showDocumentMessage(error.message); }
      });
      if (isOwner && !version.is_current) {
        addActionButton(actions, 'Restore', async () => {
          if (!window.confirm(`Restore version ${version.version_number}? The current file will remain available in history.`)) return;
          try {
            await apiRequest(`/api/documents/${item.id}/versions/${version.id}/restore`, { method: 'POST' });
            versionsDialog.close();
            showDocumentMessage('Version restored. The previous current file is still in history.', true);
            await refreshCollections(true);
          } catch (error) { showDocumentMessage(error.message); }
        });
      }
      row.append(info, actions);
      list.append(row);
    }
  } catch (error) {
    list.textContent = error.message;
  }
}

function renderDocument(item, shared = false) {
  const row = document.createElement('tr');
  const nameCell = document.createElement('td');
  const fileLine = document.createElement('div');
  fileLine.className = 'table-file-line';
  const fileIcon = document.createElement('span');
  fileIcon.className = `table-file-icon file-${fileKind(item).toLowerCase()}`;
  fileIcon.textContent = fileKind(item);
  const fileCopy = document.createElement('span');
  const displayTitle = document.createElement('strong');
  displayTitle.textContent = item.title;
  const filename = document.createElement('small');
  filename.textContent = item.original_filename;
  fileCopy.append(displayTitle, filename);
  fileLine.append(fileIcon, fileCopy);
  nameCell.append(fileLine);

  const dateCell = document.createElement('td');
  dateCell.className = 'date-cell';
  dateCell.textContent = new Date(item.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  const actionCell = document.createElement('td');
  const actions = document.createElement('div');
  actions.className = 'row-actions';

  if (['application/pdf', 'text/plain'].includes(item.content_type)) {
    addActionButton(actions, 'Preview', () => previewDocument(item));
  }
  addActionButton(actions, 'Download', async () => {
    try {
      const response = await apiRequest(`/api/documents/${item.id}/download`);
      const objectUrl = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = item.original_filename;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (error) {
      showDocumentMessage(error.message);
    }
  });
  addActionButton(actions, 'Versions', () => openVersionHistory(item, !shared));

  const canEdit = !shared || item.access_level === 'edit';
  if (canEdit) {
    addActionButton(actions, 'Edit details', async () => {
      const nextTitle = window.prompt('Document title:', item.title);
      if (nextTitle === null) return;
      const nextCategory = window.prompt('Category (leave blank to clear):', item.category || '');
      if (nextCategory === null) return;
      try {
        await apiRequest(`/api/documents/${item.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: nextTitle, category: nextCategory || null }),
        });
        showDocumentMessage('Document details updated.', true);
        await refreshCollections(true);
      } catch (error) {
        showDocumentMessage(error.message);
      }
    });

    const replaceInput = document.createElement('input');
    replaceInput.type = 'file';
    replaceInput.accept = '.pdf,.docx,.txt';
    replaceInput.className = 'hidden-file-input';
    replaceInput.addEventListener('change', async () => {
      const replacement = replaceInput.files?.[0];
      if (!replacement) return;
      const data = new FormData();
      data.append('file', replacement);
      try {
        await apiRequest(`/api/documents/${item.id}/file`, { method: 'PUT', body: data });
        showDocumentMessage('Document file replaced.', true);
        await refreshCollections(true);
      } catch (error) {
        showDocumentMessage(error.message);
      } finally {
        replaceInput.value = '';
      }
    });
    actions.append(replaceInput);
    addActionButton(actions, 'Replace', () => replaceInput.click());
  }

  if (!shared) {
    addActionButton(actions, 'Share', () => openShareDialog(item));
    addActionButton(actions, 'Delete', async () => {
      if (!window.confirm(`Delete “${item.title}”? This cannot be undone.`)) return;
      try {
        await apiRequest(`/api/documents/${item.id}`, { method: 'DELETE' });
        showDocumentMessage('Document deleted.', true);
        await refreshCollections(true);
      } catch (error) {
        showDocumentMessage(error.message);
      }
    }, 'danger');
  }

  actionCell.append(actions);
  if (shared) {
    const ownerCell = document.createElement('td');
    ownerCell.className = 'owner-cell';
    ownerCell.textContent = item.owner_name;
    const accessCell = document.createElement('td');
    const access = document.createElement('span');
    access.className = `access-pill access-${item.access_level}`;
    access.textContent = item.access_level.toUpperCase();
    accessCell.append(access);
    row.append(nameCell, ownerCell, accessCell, dateCell, actionCell);
  } else {
    const categoryCell = document.createElement('td');
    categoryCell.textContent = item.category || 'Uncategorized';
    const sizeCell = document.createElement('td');
    sizeCell.className = 'size-cell';
    sizeCell.textContent = formatSize(item.size_bytes);
    row.append(nameCell, categoryCell, dateCell, sizeCell, actionCell);
  }
  return row;
}

function searchParams(formSelector) {
  const formElement = document.querySelector(formSelector);
  const params = new URLSearchParams();
  for (const input of formElement.querySelectorAll('input')) {
    const value = input.value.trim();
    if (!value) continue;
    const id = input.id;
    if (id.endsWith('filter-name')) params.set('name', value);
    else if (id.endsWith('filter-owner')) params.set('owner', value);
    else if (id.endsWith('filter-category')) params.set('category', value);
    else if (id.endsWith('filter-from')) params.set('date_from', value);
    else if (id.endsWith('filter-to')) params.set('date_to', value);
  }
  params.set('limit', '100');
  return params;
}

function renderOverview() {
  document.querySelector('#overview-document-count').textContent = String(ownedDocuments.length);
  document.querySelector('#overview-shared-count').textContent = String(sharedDocuments.length);
  document.querySelector('#nav-document-count').textContent = String(ownedDocuments.length);
  document.querySelector('#nav-shared-count').textContent = String(sharedDocuments.length);
  const sharedByMe = sharingStatus.filter(item => item.active_share_count > 0).length;
  document.querySelector('#nav-sharing-count').textContent = String(sharedByMe);
  document.querySelector('#overview-owned-share-count').textContent = String(
    sharingStatus.reduce((total, item) => total + item.active_share_count, 0),
  );
  const recent = document.querySelector('#overview-recent');
  const empty = document.querySelector('#overview-empty');
  recent.replaceChildren();
  const items = [...ownedDocuments].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 4);
  empty.classList.toggle('hidden', items.length > 0);
  recent.classList.toggle('hidden', items.length === 0);
  for (const item of items) {
    const card = document.createElement('article');
    card.className = 'recent-card';
    const icon = document.createElement('span');
    icon.className = `recent-file-icon file-${fileKind(item).toLowerCase()}`;
    icon.textContent = fileKind(item);
    const category = document.createElement('small');
    category.textContent = item.category || 'UNCATEGORIZED';
    const heading = document.createElement('strong');
    heading.textContent = item.title;
    const filename = document.createElement('span');
    filename.className = 'recent-filename';
    filename.textContent = item.original_filename;
    const meta = document.createElement('span');
    meta.className = 'recent-meta';
    meta.textContent = `${new Date(item.created_at).toLocaleDateString()} · ${formatSize(item.size_bytes)}`;
    const open = document.createElement('button');
    open.type = 'button';
    open.textContent = 'Open in library →';
    open.addEventListener('click', () => {
      switchWorkspaceView('documents');
      document.querySelector('#filter-name').value = item.title;
      loadDocuments();
    });
    card.append(icon, category, heading, filename, meta, open);
    recent.append(card);
  }
}

function switchWorkspaceView(viewName) {
  const views = {
    overview: ['#overview-view', 'Overview'],
    documents: ['#my-documents-view', 'My documents'],
    sharing: ['#sharing-status-view', 'Shared by me'],
    shared: ['#shared-documents-view', 'Shared with me'],
  };
  const [selector, label] = views[viewName] || views.overview;
  for (const [name, [viewSelector]] of Object.entries(views)) {
    document.querySelector(viewSelector).classList.toggle('hidden', name !== viewName);
  }
  for (const navItem of document.querySelectorAll('[data-workspace-view]')) {
    navItem.classList.toggle('active', navItem.dataset.workspaceView === viewName);
  }
  document.querySelector('#breadcrumb-current').textContent = label;
  showDocumentMessage('');
  if (viewName === 'documents') loadDocuments();
  if (viewName === 'sharing') loadSharingStatus();
  if (viewName === 'shared') loadSharedDocuments();
  if (viewName === 'overview') refreshCollections(true);
}

async function loadDocuments() {
  try {
    const params = searchParams('#search-form');
    const docs = await apiRequest(`/api/documents?${params.toString()}`);
    if (!hasActiveFilters('#search-form')) ownedDocuments = docs;
    document.querySelector('#document-count').textContent = String(docs.length);
    documentRows.replaceChildren();
    if (!docs.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 5;
      cell.className = 'empty-state';
      cell.textContent = 'No documents match these filters. Upload a new file or clear your search.';
      row.append(cell);
      documentRows.append(row);
    } else {
      for (const item of docs) documentRows.append(renderDocument(item));
    }
    renderOverview();
  } catch (error) {
    showDocumentMessage(error.message);
  }
}

async function loadSharedDocuments() {
  try {
    const params = searchParams('#shared-search-form');
    const docs = await apiRequest(`/api/documents/shared?${params.toString()}`);
    if (!hasActiveFilters('#shared-search-form')) sharedDocuments = docs;
    document.querySelector('#shared-count').textContent = String(docs.length);
    sharedRows.replaceChildren();
    const emptyState = document.querySelector('#shared-empty');
    const tableWrap = document.querySelector('#shared-table-wrap');
    emptyState.classList.toggle('hidden', docs.length > 0 || hasActiveSharedFilters());
    tableWrap.classList.toggle('hidden', docs.length === 0 && !hasActiveSharedFilters());
    if (!docs.length) {
      if (hasActiveSharedFilters()) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 5;
        cell.className = 'empty-state';
        cell.textContent = 'No shared documents match these filters.';
        row.append(cell);
        sharedRows.append(row);
      }
    } else {
      for (const item of docs) sharedRows.append(renderDocument(item, true));
    }
    renderOverview();
  } catch (error) {
    showDocumentMessage(error.message);
  }
}

function renderSharingStatus(item) {
  const row = document.createElement('tr');
  const documentCell = document.createElement('td');
  const fileLine = document.createElement('div');
  fileLine.className = 'table-file-line';
  const icon = document.createElement('span');
  icon.className = `table-file-icon file-${fileKind(item).toLowerCase()}`;
  icon.textContent = fileKind(item);
  const copy = document.createElement('span');
  const name = document.createElement('strong');
  name.textContent = item.title;
  const filename = document.createElement('small');
  filename.textContent = item.original_filename;
  copy.append(name, filename);
  fileLine.append(icon, copy);
  documentCell.append(fileLine);

  const statusCell = document.createElement('td');
  const status = document.createElement('span');
  const isShared = item.active_share_count > 0;
  status.className = `sharing-state ${isShared ? 'state-shared' : 'state-private'}`;
  status.textContent = isShared ? `SHARED · ${item.active_share_count}` : 'PRIVATE';
  statusCell.append(status);

  const peopleCell = document.createElement('td');
  if (!isShared) {
    peopleCell.className = 'no-recipients';
    peopleCell.textContent = 'Only you';
  } else {
    const recipients = document.createElement('div');
    recipients.className = 'sharing-recipients';
    for (const person of item.recipients.slice(0, 2)) {
      const badge = document.createElement('span');
      const until = person.expires_at ? ` · until ${new Date(person.expires_at).toLocaleString()}` : '';
      badge.title = `${person.email} · ${person.access_level.toUpperCase()}${until}`;
      badge.textContent = `${person.full_name} · ${person.access_level.toUpperCase()}`;
      recipients.append(badge);
    }
    if (item.recipients.length > 2) {
      const more = document.createElement('span');
      more.className = 'recipient-more';
      more.textContent = `+${item.recipients.length - 2} more`;
      recipients.append(more);
    }
    peopleCell.append(recipients);
  }

  const updated = document.createElement('td');
  updated.className = 'date-cell';
  updated.textContent = new Date(item.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  const actions = document.createElement('td');
  const manage = document.createElement('button');
  manage.type = 'button';
  manage.className = 'manage-share-button';
  manage.textContent = isShared ? 'Manage access' : 'Share';
  manage.addEventListener('click', () => openShareDialog(item));
  actions.append(manage);
  row.append(documentCell, statusCell, peopleCell, updated, actions);
  return row;
}

async function loadSharingStatus() {
  try {
    sharingStatus = await apiRequest('/api/documents/sharing-status');
    document.querySelector('#sharing-document-count').textContent = String(sharingStatus.length);
    const empty = document.querySelector('#sharing-empty');
    const table = document.querySelector('#sharing-table-wrap');
    empty.classList.toggle('hidden', sharingStatus.length > 0);
    table.classList.toggle('hidden', sharingStatus.length === 0);
    sharingStatusRows.replaceChildren();
    for (const item of sharingStatus) sharingStatusRows.append(renderSharingStatus(item));
    renderOverview();
  } catch (error) {
    showDocumentMessage(error.message);
  }
}

function hasActiveSharedFilters() {
  return hasActiveFilters('#shared-search-form');
}

function hasActiveFilters(formSelector) {
  return [...document.querySelector(formSelector).querySelectorAll('input')].some(input => input.value.trim());
}

async function refreshCollections(clearFilters = false) {
  const myForm = document.querySelector('#search-form');
  const sharedForm = document.querySelector('#shared-search-form');
  if (clearFilters) {
    myForm.reset();
    sharedForm.reset();
  }
  await Promise.all([loadDocuments(), loadSharedDocuments(), loadSharingStatus()]);
}

async function loadGrants() {
  const container = document.querySelector('#share-grants');
  container.replaceChildren();
  try {
    const grants = await apiRequest(`/api/documents/${sharingDocument.id}/permissions`);
    if (!grants.length) {
      container.textContent = 'No one has access yet.';
      return;
    }
    for (const grant of grants) {
      const row = document.createElement('div');
      row.className = 'grant-row';
      const person = document.createElement('span');
      const expiryText = grant.expires_at ? ` · until ${new Date(grant.expires_at).toLocaleString()}` : '';
      person.textContent = `${grant.recipient_name} · ${grant.recipient_email} · ${grant.access_level.toUpperCase()}${expiryText}`;
      const revoke = document.createElement('button');
      revoke.type = 'button';
      revoke.className = 'revoke-button';
      revoke.textContent = 'Revoke';
      revoke.addEventListener('click', async () => {
        try {
          await apiRequest(`/api/documents/${sharingDocument.id}/permissions/${grant.id}`, { method: 'DELETE' });
          shareMessage.textContent = 'Access revoked. They can no longer open this document.';
          shareMessage.classList.add('success');
          await refreshCollections(true);
          await loadGrants();
        } catch (error) {
          shareMessage.textContent = error.message;
          shareMessage.classList.remove('success');
        }
      });
      row.append(person, revoke);
      container.append(row);
    }
  } catch (error) {
    shareMessage.textContent = error.message;
  }
}

function renderShareSuggestions(items) {
  const container = document.querySelector('#share-suggestions');
  container.replaceChildren();
  if (!items.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = 'No pending suggestions. Try generating suggestions after you have shared documents in this category.';
    container.append(empty);
    return;
  }
  for (const item of items) {
    const card = document.createElement('article');
    card.className = 'suggestion-card';
    const identity = document.createElement('div');
    const name = document.createElement('strong');
    name.textContent = item.recipient_name;
    const email = document.createElement('span');
    email.className = 'muted';
    email.textContent = item.recipient_email;
    const rationale = document.createElement('p');
    rationale.textContent = item.rationale;
    identity.append(name, email, rationale);

    const actions = document.createElement('div');
    actions.className = 'suggestion-actions';
    const access = document.createElement('select');
    access.setAttribute('aria-label', `Permission for ${item.recipient_name}`);
    access.innerHTML = '<option value="read">Read</option><option value="edit">Edit</option>';
    const approve = document.createElement('button');
    approve.type = 'button';
    approve.className = 'primary';
    approve.textContent = 'Approve';
    approve.addEventListener('click', () => decideShareSuggestion(item, 'approve', access.value));
    const dismiss = document.createElement('button');
    dismiss.type = 'button';
    dismiss.className = 'secondary';
    dismiss.textContent = 'Dismiss';
    dismiss.addEventListener('click', () => decideShareSuggestion(item, 'dismiss', 'read'));
    actions.append(access, approve, dismiss);
    card.append(identity, actions);
    container.append(card);
  }
}

async function loadShareSuggestions() {
  const container = document.querySelector('#share-suggestions');
  try {
    const items = await apiRequest(`/api/documents/${sharingDocument.id}/sharing-suggestions`);
    renderShareSuggestions(items);
  } catch (error) {
    container.textContent = error.message;
  }
}

async function decideShareSuggestion(item, decision, accessLevel) {
  try {
    await apiRequest(`/api/documents/${sharingDocument.id}/sharing-suggestions/${item.id}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, access_level: accessLevel }),
    });
    shareMessage.textContent = decision === 'approve'
      ? 'Suggestion approved. Access is now active.'
      : 'Suggestion dismissed. No access was granted.';
    shareMessage.classList.add('success');
    if (decision === 'approve') await refreshCollections(true);
    await Promise.all([loadGrants(), loadShareSuggestions()]);
  } catch (error) {
    shareMessage.textContent = error.message;
    shareMessage.classList.remove('success');
  }
}

async function loadAccount() {
  if (!sessionStorage.getItem(tokenKey)) return;
  try {
    const user = await apiRequest('/api/auth/me');
    document.querySelector('#account-name').textContent = user.full_name;
    document.querySelector('#account-email').textContent = `${user.email} · ${user.role}`;
    document.querySelector('#account-avatar').textContent = user.full_name.trim().charAt(0).toUpperCase() || 'U';
    document.querySelector('#welcome-name').textContent = user.full_name.trim().split(/\s+/)[0] || 'there';
    document.querySelector('#admin-link').classList.toggle('hidden', user.role !== 'admin');
    document.querySelector('#admin-top-link').classList.toggle('hidden', user.role !== 'admin');
    authView.classList.add('hidden');
    workspace.classList.remove('hidden');
    switchWorkspaceView('overview');
  } catch (error) {
    sessionStorage.removeItem(tokenKey);
    showMessage(error.message);
  }
}

document.querySelector('#login-tab').addEventListener('click', () => setMode('login'));
document.querySelector('#register-tab').addEventListener('click', () => setMode('register'));
document.querySelector('#logout-button').addEventListener('click', () => {
  sessionStorage.removeItem(tokenKey);
  window.location.reload();
});
document.querySelector('#mobile-logout').addEventListener('click', () => {
  sessionStorage.removeItem(tokenKey);
  window.location.reload();
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  showMessage('');
  submitButton.disabled = true;
  try {
    const payload = { email: document.querySelector('#email').value, password: password.value };
    if (mode === 'register') payload.full_name = fullName.value;
    const response = await fetch(`/api/auth/${mode}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Check the form and try again.');
    if (mode === 'register') {
      setMode('login');
      showMessage('Account created. Sign in with your new credentials.', true);
      password.value = '';
      return;
    }
    sessionStorage.setItem(tokenKey, result.access_token);
    await loadAccount();
  } catch (error) {
    showMessage(error.message);
  } finally {
    submitButton.disabled = false;
  }
});

document.querySelectorAll('[data-workspace-view]').forEach(button => {
  button.addEventListener('click', () => switchWorkspaceView(button.dataset.workspaceView));
});
document.querySelectorAll('[data-open-view]').forEach(button => {
  button.addEventListener('click', () => switchWorkspaceView(button.dataset.openView));
});
document.querySelector('#topbar-upload').addEventListener('click', () => {
  switchWorkspaceView('documents');
  uploadFile.click();
});
document.querySelector('#page-upload').addEventListener('click', () => uploadFile.click());
document.querySelector('#upload-file').addEventListener('change', () => {
  const file = uploadFile.files?.[0];
  document.querySelector('#selected-file-name').textContent = file ? file.name : 'Choose a file to upload';
});

document.querySelector('#upload-form').addEventListener('submit', async event => {
  event.preventDefault();
  const uploadForm = event.currentTarget;
  const uploadButton = document.querySelector('#upload-button');
  uploadButton.disabled = true;
  showDocumentMessage('');
  try {
    await apiRequest('/api/documents', { method: 'POST', body: new FormData(uploadForm) });
    uploadForm.reset();
    document.querySelector('#selected-file-name').textContent = 'Choose a file to upload';
    showDocumentMessage('Document added to your private library.', true);
    await refreshCollections(true);
  } catch (error) {
    showDocumentMessage(error.message);
  } finally {
    uploadButton.disabled = false;
  }
});

document.querySelector('#search-form').addEventListener('submit', async event => {
  event.preventDefault();
  showDocumentMessage('');
  await loadDocuments();
});
document.querySelector('#clear-search').addEventListener('click', async () => {
  document.querySelector('#search-form').reset();
  showDocumentMessage('');
  await loadDocuments();
});
document.querySelector('#shared-search-form').addEventListener('submit', async event => {
  event.preventDefault();
  await loadSharedDocuments();
});
document.querySelector('#clear-shared-search').addEventListener('click', async () => {
  document.querySelector('#shared-search-form').reset();
  await loadSharedDocuments();
});

document.querySelector('#share-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.querySelector('#share-submit');
  button.disabled = true;
  shareMessage.textContent = '';
  shareMessage.classList.remove('success');
  try {
    await apiRequest(`/api/documents/${sharingDocument.id}/permissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: document.querySelector('#share-email').value,
        access_level: document.querySelector('#share-access').value,
        expires_at: shareExpiryMode.value === 'expires' && shareExpiryInput.value
          ? new Date(shareExpiryInput.value).toISOString()
          : null,
      }),
    });
    shareMessage.textContent = 'Access granted. The recipient will see this in Shared with me.';
    shareMessage.classList.add('success');
    document.querySelector('#share-email').value = '';
    await refreshCollections(true);
    await loadGrants();
  } catch (error) {
    shareMessage.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
document.querySelector('#suggest-people').addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  shareMessage.textContent = '';
  try {
    const items = await apiRequest(`/api/documents/${sharingDocument.id}/sharing-suggestions`, { method: 'POST' });
    renderShareSuggestions(items);
    shareMessage.textContent = items.length
      ? `${items.length} owner-reviewed suggestion${items.length === 1 ? '' : 's'} ready.`
      : 'No new suggestions. Share a document with people in this category first.';
    shareMessage.classList.add('success');
  } catch (error) {
    shareMessage.textContent = error.message;
    shareMessage.classList.remove('success');
  } finally {
    button.disabled = false;
  }
});
shareExpiryMode.addEventListener('change', syncShareExpiryFields);
document.querySelector('#close-share').addEventListener('click', () => shareDialog.close());
document.querySelector('#close-versions').addEventListener('click', () => versionsDialog.close());
document.querySelector('#close-preview').addEventListener('click', () => previewDialog.close());
previewDialog.addEventListener('close', () => {
  previewFrame.removeAttribute('src');
  if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
  previewObjectUrl = null;
});

loadAccount();
