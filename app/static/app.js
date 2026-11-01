const form = document.querySelector('#auth-form');
const message = document.querySelector('#message');
const nameWrap = document.querySelector('#name-wrap');
const fullName = document.querySelector('#full-name');
const password = document.querySelector('#password');
const title = document.querySelector('#form-title');
const hint = document.querySelector('#form-hint');
const submitButton = document.querySelector('#submit-button');
const accountPanel = document.querySelector('#account-panel');
let mode = 'login';

function showMessage(text, isSuccess = false) {
  message.textContent = text;
  message.classList.toggle('success', isSuccess);
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

async function loadAccount() {
  const token = sessionStorage.getItem('trustvault_access_token');
  if (!token) return;
  try {
    const response = await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new Error('Your session expired. Please sign in again.');
    const user = await response.json();
    document.querySelector('#account-name').textContent = user.full_name;
    document.querySelector('#account-email').textContent = `${user.email} · ${user.role}`;
    accountPanel.classList.remove('hidden');
    form.classList.add('hidden');
    document.querySelector('.tabs').classList.add('hidden');
    title.textContent = 'You are signed in';
    hint.textContent = 'Your account is ready. Document features arrive in the next project phase.';
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
    if (!response.ok) throw new Error(result.detail || 'The request could not be completed.');
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

loadAccount();
