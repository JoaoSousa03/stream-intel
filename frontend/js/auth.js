// ── Auth ─────────────────────────────────────────────────────────────────────
function showAuth() {
  document.getElementById('authScreen').classList.remove('hidden');
  document.getElementById('appLayout').style.display = 'none';
}
function hideAuth() {
  document.getElementById('authScreen').classList.add('hidden');
  document.getElementById('appLayout').style.display = 'flex';
}

async function doLogin() {
  const username = document.getElementById('authUsername').value.trim();
  const password = document.getElementById('authPassword').value.trim();
  const btn      = document.getElementById('authBtn');
  const err      = document.getElementById('authError');
  if (!username || !password) { err.textContent = 'Please enter username and password.'; return; }
  btn.disabled = true; btn.textContent = 'Signing in…'; err.textContent = '';
  showGlobalLoader();
  const data = await fetch('/api/auth/login', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    credentials: 'same-origin', body: JSON.stringify({username, password})
  }).then(r => r.json()).catch(() => ({}));
  hideGlobalLoader();
  btn.disabled = false; btn.textContent = 'Sign In';
  if (data.ok) {
    hideAuth();
    document.getElementById('usernameDisplay').textContent = data.username;
    const initial = document.getElementById('headerAvatarInitial');
    if (initial) initial.textContent = (data.username || '?')[0].toUpperCase();
    await loadApp();
  } else {
    err.textContent = data.error || 'Login failed.';
  }
}

async function doGoogleLogin() {
  const btn = document.getElementById('googleBtn');
  const err = document.getElementById('authError');
  btn.disabled = true;
  btn.textContent = 'Redirecting to Google…';
  err.textContent = '';
  
  try {
    showGlobalLoader();
    const response = await fetch('/api/auth/google-init');
    const data = await response.json();
    hideGlobalLoader();
    if (data.auth_url) {
      window.location.href = data.auth_url;
    } else {
      err.textContent = data.error || 'Failed to initiate Google login.';
      btn.disabled = false;
      btn.textContent = 'Sign in with Google';
    }
  } catch (e) {
    err.textContent = 'Failed to initiate Google login.';
    btn.disabled = false;
    btn.textContent = 'Sign in with Google';
  }
}

// Clean up query params after Google OAuth
function checkOAuthToken() {
  const params = new URLSearchParams(window.location.search);
  if (params.has('token')) {
    params.delete('token');
    const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
    window.history.replaceState({}, document.title, newUrl);
  }
}

async function doLogout() {
  showGlobalLoader();
  await api('POST', '/api/auth/logout', null, {loader:true});
  hideGlobalLoader();
  showAuth();
  allTitles = []; libraryMap = {};
  document.getElementById('log').innerHTML = '<div class="log-line" style="color:var(--muted)">Waiting to run…</div>';
}

// Allow Enter key on login form
document.getElementById('authPassword').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
document.getElementById('authUsername').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });

// ── Google account setup overlay ─────────────────────────────────────────────
function openSetupOverlay(suggestedUsername) {
  document.getElementById('setupScreen').classList.remove('hidden');
  const input = document.getElementById('setupUsernameInput');
  if (input) {
    input.value = suggestedUsername || '';
    setTimeout(() => input.focus(), 60);
  }
}

async function onSetupPicChange(event) {
  const file = event.target.files[0];
  if (!file || !file.type.startsWith('image/')) return;
  const dataUrl = await _resizeImage(file, 400);
  const img = document.getElementById('setupAvatarImg');
  const svg = document.querySelector('#setupAvatarEl svg');
  img.src = dataUrl;
  img.style.display = 'block';
  if (svg) svg.style.display = 'none';
}

async function submitSetup() {
  const input  = document.getElementById('setupUsernameInput');
  const errEl  = document.getElementById('setupError');
  const btn    = document.getElementById('setupSubmitBtn');
  const username = (input.value || '').trim();

  errEl.textContent = '';
  if (!username) { errEl.textContent = 'Please enter a username.'; return; }
  if (username.length < 3) { errEl.textContent = 'Must be at least 3 characters.'; return; }
  if (username.length > 30) { errEl.textContent = 'Must be 30 characters or fewer.'; return; }

  btn.disabled = true; btn.textContent = 'Saving…';

  const body = { username };
  const img = document.getElementById('setupAvatarImg');
  if (img && img.style.display !== 'none' && img.src.startsWith('data:')) {
    body.profile_pic = img.src;
  }

  const res = await api('POST', '/api/profile', body).catch(() => null);
  btn.disabled = false; btn.textContent = 'Get started →';

  if (res?.ok) {
    document.getElementById('setupScreen').classList.add('hidden');
    document.getElementById('usernameDisplay').textContent = username;
    const initial = document.getElementById('headerAvatarInitial');
    if (initial) initial.textContent = username[0].toUpperCase();
    if (body.profile_pic && typeof loadHeaderAvatar === 'function') loadHeaderAvatar();
    showGlobalLoader();
    await loadApp();
  } else {
    errEl.textContent = res?.error || 'Could not save. Please try again.';
  }
}

// Run cleanup & load on page load
window.addEventListener('DOMContentLoaded', checkOAuthToken);
