const form = document.querySelector('#auth-form');
const message = document.querySelector('#message');
const nameWrap = document.querySelector('#name-wrap');
const fullName = document.querySelector('#full-name');
const password = document.querySelector('#password');
const title = document.querySelector('#form-title');
const hint = document.querySelector('#form-hint');
const submitButton = document.querySelector('#submit-button');
const accountPanel = document.querySelector('#account-panel');
const documentsPanel = document.querySelector('#documents-panel');
const documentRows = document.querySelector('#document-rows');
const documentMessage = document.querySelector('#document-message');
const previewDialog = document.querySelector('#preview-dialog');
const previewFrame = document.querySelector('#preview-frame');
const shareDialog = document.querySelector('#share-dialog');
const shareMessage = document.querySelector('#share-message');
let sharingDocument = null;
let previewObjectUrl = null;
let mode = 'login';

function showMessage(text, isSuccess = false) {
  message.textContent = text;
  message.classList.toggle('success', isSuccess);
}

function showDocumentMessage(text, isSuccess = false) {
  documentMessage.textContent = text;
  documentMessage.classList.toggle('success', isSuccess);
}

function setMode(nextMode) {
  mode = nextMode;
  const registering = mode === 'register';
  document.querySelector('#login-tab').classList.toggle('active', !registering);
  document.querySelector('#register-tab').classList.toggle('active', registering);
  nameWrap.classList.toggle('hidden', !registering);
  fullName.required = registering;
  password.autocomplete = registering ? 'new-password' : 'current-password';
  title.textContent = registering ? 'Create your account' : 'Welcome back';
  hint.textContent = registering ? 'Set up your private workspace account.' : 'Sign in to continue to your workspace.';
  submitButton.textContent = registering ? 'Create account' : 'Sign in';
  showMessage('');
}

async function apiRequest(url, options = {}) {
  const token = sessionStorage.getItem('trustvault_access_token');
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    sessionStorage.removeItem('trustvault_access_token');
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

function addActionButton(container, label, onClick, className = '') {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  if (className) button.className = className;
  button.addEventListener('click', onClick);
  container.append(button);
  return button;
}

function renderDocument(documentItem, shared = false) {
  const row = document.createElement('tr');
  const nameCell = document.createElement('td');
  const displayTitle = document.createElement('span');
  displayTitle.className = 'doc-title';
  displayTitle.textContent = documentItem.title;
  const filename = document.createElement('span');
  filename.className = 'doc-filename';
  filename.textContent = shared ? `${documentItem.original_filename} · shared by ${documentItem.owner_name}` : documentItem.original_filename;
  nameCell.append(displayTitle, filename);

  const categoryCell = document.createElement('td');
  categoryCell.textContent = documentItem.category || 'Uncategorized';
  const dateCell = document.createElement('td');
  dateCell.className = 'date-cell';
  dateCell.textContent = new Date(documentItem.created_at).toLocaleDateString();
  const sizeCell = document.createElement('td');
  sizeCell.className = 'size-cell';
  sizeCell.textContent = formatSize(documentItem.size_bytes);
  const actionCell = document.createElement('td');
  const actions = document.createElement('div');
  actions.className = 'row-actions';

  if (['application/pdf', 'text/plain'].includes(documentItem.content_type)) {
    addActionButton(actions, 'Preview', async () => {
      try {
        const response = await apiRequest(`/api/documents/${documentItem.id}/view`);
        const blob = await response.blob();
        if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
        previewObjectUrl = URL.createObjectURL(blob);
        previewFrame.src = previewObjectUrl;
        document.querySelector('#preview-title').textContent = documentItem.title;
        previewDialog.showModal();
      } catch (error) {
        showDocumentMessage(error.message);
      }
    });
  }

  addActionButton(actions, 'Download', async () => {
    try {
      const response = await apiRequest(`/api/documents/${documentItem.id}/download`);
      const objectUrl = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = documentItem.original_filename;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (error) {
      showDocumentMessage(error.message);
    }
  });

  const canEdit = !shared || documentItem.access_level === 'edit';
  if (canEdit) addActionButton(actions, 'Edit details', async () => {
    const nextTitle = window.prompt('Document title:', documentItem.title);
    if (nextTitle === null) return;
    const nextCategory = window.prompt('Category (leave blank to clear):', documentItem.category || '');
    if (nextCategory === null) return;
    try {
      await apiRequest(`/api/documents/${documentItem.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: nextTitle, category: nextCategory || null }),
      });
      showDocumentMessage('Document details updated.', true);
      await loadDocuments();
    } catch (error) {
      showDocumentMessage(error.message);
    }
  });

  if (canEdit) {
    const replaceInput = document.createElement('input');
    replaceInput.type = 'file';
    replaceInput.accept = '.pdf,.docx,.txt';
    replaceInput.addEventListener('change', async () => {
      const replacement = replaceInput.files?.[0];
      if (!replacement) return;
      const data = new FormData();
      data.append('file', replacement);
      try {
        await apiRequest(`/api/documents/${documentItem.id}/file`, { method: 'PUT', body: data });
        showDocumentMessage('Document file replaced.', true);
        await loadDocuments();
        await loadSharedDocuments();
      } catch (error) {
        showDocumentMessage(error.message);
      } finally {
        replaceInput.value = '';
      }
    });
    actions.append(replaceInput);
    addActionButton(actions, 'Replace file', () => replaceInput.click());
  }

  if (!shared) addActionButton(actions, 'Share', async () => {
    sharingDocument = documentItem;
    document.querySelector('#share-title').textContent = 'Share document';
    document.querySelector('#share-document-name').textContent = `People you name can receive Read or Edit access to “${documentItem.title}”.`;
    document.querySelector('#share-email').value = '';
    document.querySelector('#share-access').value = 'read';
    shareMessage.textContent = '';
    shareDialog.showModal();
    await loadGrants();
  });

  if (!shared) addActionButton(actions, 'Delete', async () => {
    if (!window.confirm(`Delete “${documentItem.title}”? This cannot be undone.`)) return;
    try {
      await apiRequest(`/api/documents/${documentItem.id}`, { method: 'DELETE' });
      showDocumentMessage('Document deleted.', true);
      await loadDocuments();
    } catch (error) {
      showDocumentMessage(error.message);
    }
  }, 'danger');

  actionCell.append(actions);
  if (shared) {
    const ownerCell = document.createElement('td');
    ownerCell.textContent = documentItem.owner_name;
    const accessCell = document.createElement('td');
    const access = document.createElement('span');
    access.className = 'access-pill';
    access.textContent = documentItem.access_level.toUpperCase();
    accessCell.append(access);
    row.append(nameCell, ownerCell, accessCell, dateCell, actionCell);
  } else {
    row.append(nameCell, categoryCell, dateCell, sizeCell, actionCell);
  }
  return row;
}

function searchParams() {
  const params = new URLSearchParams();
  const filters = [
    ['name', '#filter-name'], ['owner', '#filter-owner'], ['category', '#filter-category'],
    ['date_from', '#filter-from'], ['date_to', '#filter-to'],
  ];
  for (const [key, selector] of filters) {
    const value = document.querySelector(selector).value.trim();
    if (value) params.set(key, value);
  }
  return params;
}

async function loadDocuments() {
  try {
    const params = searchParams();
    const docs = await apiRequest(`/api/documents?${params.toString()}`);
    document.querySelector('#document-count').textContent = `${docs.length} ${docs.length === 1 ? 'file' : 'files'}`;
    documentRows.replaceChildren();
    if (docs.length === 0) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 5;
      cell.className = 'empty-state';
      cell.textContent = 'No documents match these filters.';
      row.append(cell);
      documentRows.append(row);
      return;
    }
    for (const documentItem of docs) documentRows.append(renderDocument(documentItem));
  } catch (error) {
    showDocumentMessage(error.message);
  }
}

async function loadSharedDocuments() {
  const rows = document.querySelector('#shared-rows');
  try {
    const params = searchParams();
    const docs = await apiRequest(`/api/documents/shared?${params.toString()}`);
    document.querySelector('#shared-count').textContent = `${docs.length} ${docs.length === 1 ? 'file' : 'files'}`;
    rows.replaceChildren();
    if (!docs.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 5;
      cell.className = 'empty-state';
      cell.textContent = 'No documents match these filters or have been shared with you.';
      row.append(cell);
      rows.append(row);
      return;
    }
    for (const item of docs) {
      const row = renderDocument(item, true);
      rows.append(row);
    }
  } catch (error) {
    showDocumentMessage(error.message);
  }
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
      person.textContent = `${grant.recipient_name} · ${grant.recipient_email} · ${grant.access_level.toUpperCase()}`;
      const revoke = document.createElement('button');
      revoke.type = 'button';
      revoke.className = 'revoke-button';
      revoke.textContent = 'Revoke';
      revoke.addEventListener('click', async () => {
        try {
          await apiRequest(`/api/documents/${sharingDocument.id}/permissions/${grant.id}`, { method: 'DELETE' });
          shareMessage.textContent = 'Access revoked. They can no longer open this document.';
          shareMessage.classList.add('success');
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

async function loadAccount() {
  const token = sessionStorage.getItem('trustvault_access_token');
  if (!token) return;
  try {
    const user = await apiRequest('/api/auth/me');
    document.querySelector('#account-name').textContent = user.full_name;
    document.querySelector('#account-email').textContent = `${user.email} · ${user.role}`;
    accountPanel.classList.remove('hidden');
    documentsPanel.classList.remove('hidden');
    form.classList.add('hidden');
    document.querySelector('.tabs').classList.add('hidden');
    title.textContent = 'Your workspace';
    hint.textContent = 'Manage your files and documents shared with you.';
    await Promise.all([loadDocuments(), loadSharedDocuments()]);
  } catch (error) {
    sessionStorage.removeItem('trustvault_access_token');
    showMessage(error.message);
  }
}

document.querySelector('#login-tab').addEventListener('click', () => setMode('login'));
document.querySelector('#register-tab').addEventListener('click', () => setMode('register'));
document.querySelector('#logout-button').addEventListener('click', () => {
  sessionStorage.removeItem('trustvault_access_token');
  window.location.reload();
});

form.addEventListener('submit', async (event) => {
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
    sessionStorage.setItem('trustvault_access_token', result.access_token);
    await loadAccount();
  } catch (error) {
    showMessage(error.message);
  } finally {
    submitButton.disabled = false;
  }
});

document.querySelector('#upload-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const uploadForm = event.currentTarget;
  const uploadButton = document.querySelector('#upload-button');
  const formData = new FormData(uploadForm);
  uploadButton.disabled = true;
  showDocumentMessage('');
  try {
    await apiRequest('/api/documents', { method: 'POST', body: formData });
    uploadForm.reset();
    showDocumentMessage('Document uploaded to private storage.', true);
    await loadDocuments();
  } catch (error) {
    showDocumentMessage(error.message);
  } finally {
    uploadButton.disabled = false;
  }
});

document.querySelector('#search-form').addEventListener('submit', (event) => {
  event.preventDefault();
  showDocumentMessage('');
  loadDocuments();
  loadSharedDocuments();
});
document.querySelector('#clear-search').addEventListener('click', () => {
  document.querySelector('#search-form').reset();
  showDocumentMessage('');
  loadDocuments();
  loadSharedDocuments();
});
document.querySelector('#close-preview').addEventListener('click', () => previewDialog.close());
previewDialog.addEventListener('close', () => {
  previewFrame.removeAttribute('src');
  if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
  previewObjectUrl = null;
});

document.querySelector('#share-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = document.querySelector('#share-submit');
  button.disabled = true;
  shareMessage.textContent = '';
  shareMessage.classList.remove('success');
  try {
    await apiRequest(`/api/documents/${sharingDocument.id}/permissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: document.querySelector('#share-email').value, access_level: document.querySelector('#share-access').value }),
    });
    shareMessage.textContent = 'Access granted. The recipient will see it in “Shared with me”.';
    shareMessage.classList.add('success');
    document.querySelector('#share-email').value = '';
    await loadGrants();
  } catch (error) {
    shareMessage.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
document.querySelector('#close-share').addEventListener('click', () => shareDialog.close());

loadAccount();
