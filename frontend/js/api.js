// ── Genre map ────────────────────────────────────────────────────────────────
const GENRE_NAMES = {
  'act':'Action & Adventure','ani':'Animation','cmf':'Comedy','cmy':'Comedy',
  'crm':'Crime','doc':'Documentary','drm':'Drama','eur':'European','fnt':'Fantasy',
  'fml':'Family','hst':'History','hrr':'Horror','kds':'Kids & Family',
  'msc':'Music & Musical','mys':'Mystery & Thriller','trl':'Thriller','nws':'News',
  'ppl':'People & Celebrities','rlt':'Reality TV','rly':'Reality TV','rmn':'Romance','rma':'Romance','scf':'Science Fiction',
  'spt':'Sport','war':'War & Military','wsn':'Western','tv':'TV Movie',
};
function formatGenre(c) { const t=c.trim(); return GENRE_NAMES[t.toLowerCase()]||t; }
const GENRE_EMOJI = {
  'action & adventure':'⚔️','animation':'🎨','comedy':'😄','crime':'🔫',
  'documentary':'📽️','drama':'🎭','european':'🌍','fantasy':'🧙',
  'family':'👨\u200d👩\u200d👧','history':'📜','horror':'👻','kids & family':'🧸',
  'music & musical':'🎵','mystery & thriller':'🕵️','thriller':'🗡️','news':'📰',
  'people & celebrities':'⭐','reality tv':'📺','romance':'❤️',
  'science fiction':'🚀','sport':'🏆','war & military':'🎖️','western':'🤠',
};
function genreEmoji(displayName) { return GENRE_EMOJI[displayName.toLowerCase()] || '🎬'; }

// utility functions
function goHome(){
  // close any open overlays first
  if(typeof closeModalDirect === 'function') closeModalDirect();
  if(typeof closeActorModalDirect === 'function') closeActorModalDirect();
  // switch to "all" view — use setView if available, fall back to clicking the tab
  if(typeof setView === 'function'){
    const tab = document.querySelector('.nav-tab[data-view="all"]');
    setView('all', tab);
  } else {
    const tab = document.querySelector('.nav-tab[data-view="all"]');
    if(tab) tab.click();
  }
  // clear all filters after the view switches
  if(typeof clearAllFilters === 'function') clearAllFilters();
}

// ── API layer ────────────────────────────────────────────────────────────────
// lightweight toast utility used by multiple modules
let _toastTimer = null;
function showToast(msg, duration = 2800) {
  let t = document.getElementById('appToast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'appToast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove('show'), duration);
}

// helper for global loader overlay
function showGlobalLoader() {
  const el = document.getElementById('globalLoader');
  if (el) el.classList.remove('hidden');
}
function hideGlobalLoader() {
  const el = document.getElementById('globalLoader');
  if (el) el.classList.add('hidden');
}

// API layer with optional loader flag (pass {loader:true} as fourth arg)
async function api(method, path, body, opts={}) {
  if (opts.loader) showGlobalLoader();
  const fetchOpts = { method, headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin' };
  if (body) fetchOpts.body = JSON.stringify(body);
  try {
    const res  = await fetch(path, fetchOpts);
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) { showAuth(); return null; }
    if (res.status === 405) {
      console.warn(`405 Method Not Allowed on ${method} ${path}`);
      return null;
    }
    return data;
  } finally {
    if (opts.loader) hideGlobalLoader();
  }
}

// ── Header search engine ──────────────────────────────────────────────────────
// Widget-instance-based: the same HTML snippet is embedded in the main header,
// the title detail back-bar, and the actor back-bar. All functions receive the
// triggering element and navigate to the right .header-search container via
// .closest(), so there are never conflicts between instances.
const SEARCH_PAGE_SIZE = 10;
let _searchTimer   = null;
let _searchQuery   = '';
let _searchBatch   = [];
let _searchTotal   = 0;
let _searchShowing = 0;
let _actorBatch    = []; // TMDB person results for the current query
let _activeWidget  = null; // the .header-search div currently in use

function _widget(el) { return el.closest('.header-search'); }
function _wi(sel)    { return _activeWidget ? _activeWidget.querySelector(sel) : null; }

function hsDebounced(input) {
  clearTimeout(_searchTimer);
  const q = input.value.trim();
  if (!q) { _closeDrop(_widget(input)); return; }
  _activeWidget = _widget(input);
  _searchTimer = setTimeout(() => runSearch(q, 0), 220);
}

function hsFocus(input) {
  if (input.value.trim() && _searchBatch.length) {
    _activeWidget = _widget(input);
    _openDrop(_activeWidget);
  }
}

function hsKeydown(e, input) {
  if (e.key === 'Escape') { _closeDrop(_widget(input)); input.blur(); }
}

function hsShowMore(btn) { _activeWidget = _widget(btn); searchShowMore(); }

function _openDrop(w) {
  if (!w) return;
  const drop = w.querySelector('.hs-dropdown');
  const inp  = w.querySelector('.hs-input');
  const rect = inp.getBoundingClientRect();
  const minW = 320;
  const desiredW = Math.max(minW, rect.width);
  // Ensure the dropdown doesn't overflow the right edge of the viewport
  const availRight = window.innerWidth - rect.left - 8;
  const actualW = Math.min(desiredW, availRight);
  // Adjust left so dropdown never clips right edge
  const dropLeft = Math.min(rect.left, window.innerWidth - actualW - 8);
  drop.style.top       = rect.bottom + 'px';
  drop.style.left      = Math.max(4, dropLeft) + 'px';
  drop.style.width     = actualW + 'px';
  drop.style.right     = '';
  drop.style.transform = 'none';
  drop.style.maxHeight = Math.max(200, window.innerHeight - rect.bottom - 12) + 'px';
  drop.classList.add('open');
}
function _closeDrop(w) { if (w) w.querySelector('.hs-dropdown').classList.remove('open'); }
function openSearchDropdown()  { _openDrop(_activeWidget); }
function closeSearchDropdown() {
  document.querySelectorAll('.hs-dropdown.open').forEach(d => d.classList.remove('open'));
}

async function runSearch(q, offset) {
  _searchQuery = q;
  if (offset === 0) {
    _searchBatch   = [];
    _searchShowing = 0;
    _searchTotal   = 0;
    _actorBatch    = [];
    setSearchContent('<div class="search-loading">Searching…</div>');
    const mb = _wi('.hs-more-btn'); if (mb) mb.style.display = 'none';
    openSearchDropdown();
    // Parallel actor search via TMDB person endpoint — results used only to
    // enrich title results with cast info, NOT shown as a separate people section
    const capturedQ  = q;
    const capturedW  = _activeWidget;
    api('GET', `/api/tmdb/search?${new URLSearchParams({ query: q, type: 'person' })}`, null, {loader:false})
      .then(data => {
        if (capturedQ !== _searchQuery) return; // stale
        // Store actor batch for potential future use but do NOT display person section
        _actorBatch = (data?.results || [])
          .sort((a, b) => (b.popularity || 0) - (a.popularity || 0))
          .slice(0, 4);
        // No longer appending actor section to dropdown
      });
  }
  const fetchLimit = SEARCH_PAGE_SIZE * 2;
  const qs = new URLSearchParams({ search: q, limit: fetchLimit, offset });
  const data = await api('GET', `/api/titles?${qs}`);
  if (!data || q !== _searchQuery) return; // stale — discard
  const incoming = data.titles || [];
  const raw = offset === 0 ? incoming : _searchBatch.concat(incoming);
  // Deduplicate by title+year+type, merging platforms into one entry
  const seen = new Map();
  for (const t of raw) {
    const key = `${(t.title||'').toLowerCase()}|${t.release_year}|${t.content_type}`;
    if (seen.has(key)) {
      const ex = seen.get(key);
      if (t.platform && !ex.platform.split(', ').includes(t.platform))
        ex.platform = ex.platform ? ex.platform + ', ' + t.platform : t.platform;
    } else {
      seen.set(key, { ...t });
    }
  }
  _searchBatch = [...seen.values()];
  _searchTotal = data.total;
  renderSearchPage(offset === 0 ? 0 : _searchShowing);
}

function renderSearchPage(startIdx) {
  const slice = _searchBatch.slice(startIdx, startIdx + SEARCH_PAGE_SIZE);
  _searchShowing = startIdx + slice.length;

  if (!slice.length) {
    setSearchContent(`<div class="search-no-results">No results for "<em>${_esc(_searchQuery)}</em>"</div>`);
    const mb = _wi('.hs-more-btn'); if (mb) mb.style.display = 'none';
    if (_actorBatch.length) _appendActorResults(_activeWidget);
    return;
  }

  // Use class names sr-p-N / sr-a-N so they're scoped inside each widget
  const html = slice.map((t, i) => {
    const idx  = startIdx + i;
    const icon = t.content_type === 'movie' ? '🎬' : '📺';
    return `<div class="search-result-item" data-sidx="${idx}" onclick="searchResultClick(this)">
      <div class="sr-poster sr-p-${idx}">${icon}</div>
      <div class="sr-info">
        <div class="sr-title">${_esc(t.title)}</div>
        <div class="sr-meta">${t.release_year || '—'} · ${t.content_type === 'movie' ? 'Movie' : 'TV Show'} · ${_fmtPlat(t.platform)}</div>
        <div class="sr-actors sr-a-${idx}">Loading cast…</div>
      </div>
    </div>`;
  }).join('');

  const results = _wi('.hs-results');
  if (!results) return;
  if (startIdx > 0) {
    // Insert before actor section so people always stay at the bottom
    const actSec = results.querySelector('.sr-actors-section');
    if (actSec) actSec.insertAdjacentHTML('beforebegin', html);
    else        results.insertAdjacentHTML('beforeend', html);
  } else {
    results.innerHTML = html;
    // Actors no longer appended to results
  }

  const hasMore = _searchTotal > _searchShowing || _searchBatch.length > _searchShowing;
  const mb = _wi('.hs-more-btn'); if (mb) mb.style.display = hasMore ? 'block' : 'none';

  // Capture widget now — async callbacks run after _activeWidget may have changed
  const capturedWidget = _activeWidget;
  slice.forEach((t, i) => _loadSearchMedia(t, startIdx + i, capturedWidget));
}

async function _loadSearchMedia(t, idx, widget) {
  if (!widget || typeof fetchPosterUrl !== 'function') return;
  const mt = t.content_type === 'movie' ? 'movie' : 'tv';

  const imgs = await fetchPosterUrl(t.title, t.release_year, t.content_type);
  const posterEl = widget.querySelector(`.sr-p-${idx}`);
  if (posterEl && imgs?.poster) posterEl.innerHTML = `<img src="${imgs.poster}" alt="" loading="lazy">`;

  let tmdbId = imgs?.tmdb_id;
  if (!tmdbId) {
    const sq = new URLSearchParams({ query: t.title, type: mt });
    if (t.release_year) sq.set('year', t.release_year);
    const res = await api('GET', `/api/tmdb/search?${sq}`);
    tmdbId = res?.results?.[0]?.id;
  }

  const actEl = widget.querySelector(`.sr-a-${idx}`);
  if (!tmdbId) { if (actEl) actEl.textContent = ''; return; }

  const cacheKey = `${mt}::${tmdbId}`;
  const credits = (typeof tmdbCache !== 'undefined' && tmdbCache[cacheKey])
    ? tmdbCache[cacheKey]
    : await api('GET', `/api/tmdb/${mt}/${tmdbId}/credits`);

  const names = (credits?.cast || []).slice(0, 3).map(a => a.name);
  if (actEl) actEl.textContent = names.length ? names.join(' · ') : '';
}

function searchResultClick(el) {
  const idx = parseInt(el.dataset.sidx, 10);
  const t   = _searchBatch[idx];
  if (!t) return;
  document.querySelectorAll('.hs-input').forEach(inp => inp.value = '');
  closeSearchDropdown();
  _searchBatch = []; _searchShowing = 0; _actorBatch = [];
  if (typeof titleKey === 'function' && typeof cardDataStore !== 'undefined') {
    const tk = titleKey(t);
    if (!cardDataStore[tk]) cardDataStore[tk] = t;
    openModal(tk);
  } else {
    openModal(t);
  }
}

function searchShowMore() {
  if (_searchBatch.length > _searchShowing)   renderSearchPage(_searchShowing);
  else if (_searchTotal > _searchBatch.length) runSearch(_searchQuery, _searchBatch.length);
  else { const mb = _wi('.hs-more-btn'); if (mb) mb.style.display = 'none'; }
}

function setSearchContent(html) {
  const r = _wi('.hs-results'); if (r) r.innerHTML = html;
}

// ── Actor section in search dropdown ─────────────────────────────────────────
function _appendActorResults(w) {
  const widget = w || _activeWidget;
  if (!widget || !_actorBatch.length) return;
  const results = widget.querySelector('.hs-results');
  if (!results) return;
  // Remove any existing actor section
  results.querySelector('.sr-actors-section')?.remove();
  const TMDB_BASE_IMG = 'https://image.tmdb.org/t/p';
  const html = _actorBatch.map((p, i) => {
    const photo    = p.profile_path
      ? `<img src="${TMDB_BASE_IMG}/w92${p.profile_path}" alt="" loading="lazy">`
      : '🎭';
    const knownFor = (p.known_for || []).slice(0, 2)
      .map(k => _esc(k.title || k.name || '')).filter(Boolean).join(', ');
    const dept = _esc(p.known_for_department || 'Acting');
    return `<div class="search-result-item sr-actor-item" data-actor-idx="${i}" onclick="searchPersonClick(this)">
      <div class="sr-poster sr-actor-ph">${photo}</div>
      <div class="sr-info">
        <div class="sr-title">${_esc(p.name)}</div>
        <div class="sr-meta">${dept}${knownFor ? ' · ' + knownFor : ''}</div>
      </div>
    </div>`;
  }).join('');
  const section = document.createElement('div');
  section.className = 'sr-actors-section';
  section.innerHTML = `<div class="sr-section-label">People</div>${html}`;
  results.appendChild(section);
}

function searchPersonClick(el) {
  const idx = parseInt(el.dataset.actorIdx, 10);
  const p   = _actorBatch[idx];
  if (!p) return;
  document.querySelectorAll('.hs-input').forEach(inp => inp.value = '');
  closeSearchDropdown();
  _searchBatch = []; _searchShowing = 0; _actorBatch = [];
  if (typeof openActorModal === 'function') openActorModal(p.id, p.name, '');
}

// Fallback escape/format helpers (library.js loads after api.js)
function _esc(s)     { return typeof escHtml        === 'function' ? escHtml(s)      : String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function _fmtPlat(p) { return typeof formatPlatform === 'function' ? formatPlatform(p) : (p || ''); }

// Close all dropdowns when clicking outside any search widget
document.addEventListener('click', function(e) {
  if (!e.target.closest('.header-search')) closeSearchDropdown();
}, true);
// On touch/mouse devices, blur focused buttons/cards after click so they don't stay highlighted
document.addEventListener('click', function(e) {
  const el = e.target.closest('button, [role="button"], .card, .cast-card, .catalog-person-chip, .flo-card');
  if (el && typeof el.blur === 'function') el.blur();
}, { passive: true });