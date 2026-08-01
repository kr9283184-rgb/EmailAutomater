const API = '/api'
const LS_USER = 'ea_smtp_user'
const LS_PASS = 'ea_smtp_pass'
let pin = null
let pollTimer = null
let limits = { daily: 100, gapMinutes: 5 }
let wasComplete = false
let hadQueue = false

const $ = (id) => document.getElementById(id)

async function call(body) {
  const res = await fetch(API, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...(pin ? { pin } : {}), ...body }),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || 'Something went wrong')
  return data
}

function toast(text, ok = true) {
  const t = $('toast')
  t.textContent = text
  t.className = ok ? 'ok' : 'bad'
  t.style.display = 'block'
  clearTimeout(t._timer)
  t._timer = setTimeout(() => (t.style.display = 'none'), 3500)
}

function setMsg(el, text, ok) {
  el.textContent = text || ''
  el.className = 'msg ' + (ok ? 'ok' : 'bad')
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
}

// ============ LOCK ============
async function init() {
  const res = await fetch(API)
  const d = await res.json().catch(() => ({}))
  const hasPin = !!d.hasPin
  $('lockBtn').textContent = hasPin ? 'Login' : 'Set PIN'
  $('lockHint').textContent = hasPin
    ? 'Enter your PIN to continue'
    : 'First launch — choose a PIN (only you will know it)'
  $('pinInput').focus()
}

async function doLock() {
  const value = $('pinInput').value
  if (value.length < 4) { setMsg($('lockMsg'), 'PIN must be at least 4 characters', false); return }
  try {
    const hasPin = await fetch(API).then((r) => r.json()).then((d) => !!d.hasPin)
    if (!hasPin) {
      await call({ action: 'setPin', pin: value })
      setMsg($('lockMsg'), 'PIN set! Enter it again to log in', true)
      $('lockBtn').textContent = 'Login'
    } else {
      await call({ action: 'login', pin: value })
      pin = value
      $('lockScreen').hidden = true
      $('app').hidden = false
      loadAll()
      syncCreds()
      pollTimer = setInterval(loadStatus, 10000)
      if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission().catch(() => {})
      }
    }
  } catch (e) {
    setMsg($('lockMsg'), e.message, false)
  }
  $('pinInput').value = ''
}

$('lockBtn').addEventListener('click', doLock)
$('pinInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') doLock() })
$('logoutBtn').addEventListener('click', () => {
  pin = null
  clearInterval(pollTimer)
  $('app').hidden = true
  $('lockScreen').hidden = false
  $('pinInput').focus()
})

// ============ NAV ============
document.querySelectorAll('.nav-item').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach((b) => b.classList.remove('active'))
    document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'))
    btn.classList.add('active')
    $('panel-' + btn.dataset.panel).classList.add('active')
  })
})

// ============ SETTINGS ============
function syncCreds() {
  const user = localStorage.getItem(LS_USER) || ''
  const pass = localStorage.getItem(LS_PASS) || ''
  if (!user || !pass || !pin) return
  call({ action: 'setCreds', smtpUser: user, smtpPass: pass })
    .then(() => loadStatus())
    .catch(() => {})
}

function loadLocalCreds() {
  const user = localStorage.getItem(LS_USER)
  const pass = localStorage.getItem(LS_PASS)
  if (user) $('fUser').value = user
  if (pass) $('fPass').value = pass
}

async function saveSettings() {
  try {
    const d = await call({
      action: 'saveSettings',
      host: $('fHost').value, port: $('fPort').value, secure: $('fSecure').checked,
      user: $('fUser').value, pass: $('fPass').value, fromName: $('fFrom').value,
      subject: $('fSubject').value, body: $('fBody').value,
    })
    if ($('fUser').value && $('fPass').value) {
      localStorage.setItem(LS_USER, $('fUser').value.trim())
      localStorage.setItem(LS_PASS, $('fPass').value)
    }
    setMsg($('settingsMsg'), 'Settings + template saved', true)
    showSpam(d.spam)
    updatePreview()
    loadStatus()
  } catch (e) { setMsg($('settingsMsg'), e.message, false) }
}

function showSpam(spam) {
  if (!spam) { $('spamRow').hidden = true; return }
  $('spamRow').hidden = false
  $('spamScore').textContent = `${spam.score}/100`
  const issues = spam.issues?.length ? ' — ' + spam.issues.join('; ') : ''
  if (spam.score >= 50) { setMsg($('settingsMsg'), `Spam score ${spam.score}. Start will be blocked.${issues}`, false) }
  else if (spam.score >= 30) { setMsg($('settingsMsg'), `Spam score ${spam.score}. Consider fixing:${issues}`, true) }
  $('settingsMsg').className = 'msg ' + (spam.score >= 50 ? 'bad' : spam.score >= 30 ? 'warn' : 'ok')
}
$('saveSettingsBtn').addEventListener('click', saveSettings)
$('saveTemplateBtn').addEventListener('click', saveSettings)

async function testSend() {
  try {
    await saveSettings()
    const d = await call({ action: 'testSend' })
    toast(d.message || 'OK')
  } catch (e) { toast(e.message, false) }
}
$('testBtn').addEventListener('click', testSend)

$('changePinBtn').addEventListener('click', async () => {
  const np = $('newPin').value
  if (np.length < 4) { toast('New PIN must be at least 4 characters', false); return }
  try {
    await call({ action: 'changePin', newPin: np })
    $('newPin').value = ''
    toast('PIN changed')
  } catch (e) { toast(e.message, false) }
})

// ============ TEMPLATE ============
function updatePreview() {
  const subj = $('fSubject').value.split('{name}').join('Test')
  const body = $('fBody').value.split('{name}').join('Test')
  $('previewBox').textContent = body.trim() ? `To: test@example.com\nSubject: ${subj}\n\n${body}` : ''
}
$('previewBtn').addEventListener('click', updatePreview)

// ============ CSV ============
const drop = $('fileDrop')
drop.addEventListener('click', () => $('csvFile').click())
$('csvFile').addEventListener('change', (e) => { if (e.target.files[0]) uploadCsv(e.target.files[0]) })
drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.style.borderColor = 'var(--accent)' })
drop.addEventListener('dragleave', () => (drop.style.borderColor = ''))
drop.addEventListener('drop', (e) => {
  e.preventDefault(); drop.style.borderColor = ''
  if (e.dataTransfer.files[0]) uploadCsv(e.dataTransfer.files[0])
})

async function uploadCsv(file) {
  if (!file.name.toLowerCase().endsWith('.csv')) { toast('Choose a CSV file', false); return }
  const text = await file.text()
  try {
    const d = await call({ action: 'uploadCsv', csv: text })
    setMsg($('csvMsg'), `CSV parsed: ${d.count} recipients ready. Press Start to launch.`, true)
    loadStatus()
  } catch (e) { setMsg($('csvMsg'), e.message, false) }
}

$('startBtn').addEventListener('click', async () => {
  try {
    const d = await call({ action: 'start' })
    if (d.spamWarning) {
      toast(`Started, but spam score ${d.spamWarning.score}: ${(d.spamWarning.issues || []).join('; ')}`, false)
    } else {
      toast(`${d.count} emails queued — one every ${limits.gapMinutes} min, max ${limits.daily}/day`)
    }
    loadStatus()
  } catch (e) { toast(e.message, false) }
})

$('pauseBtn').addEventListener('click', async () => {
  try {
    const d = await call({ action: $('pauseBtn').textContent === 'Pause' ? 'pause' : 'resume' })
    toast(d.paused ? 'Paused — sending stopped' : 'Resumed — next email in ~5 min')
    loadStatus()
  } catch (e) { toast(e.message, false) }
})

$('clearCsvBtn').addEventListener('click', async () => {
  try {
    await call({ action: 'uploadCsv', csv: 'name,email\n' })
    setMsg($('csvMsg'), 'CSV cleared', true)
    loadStatus()
  } catch (e) { toast(e.message, false) }
})

// ============ STATUS / DASHBOARD ============
function badge(status) {
  return `<span class="badge ${status}">${status}</span>`
}

function setPill(el, text, cls) {
  el.textContent = text
  el.className = 'pill ' + cls
}

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const notes = [880, 1108.7, 1318.5]
    notes.forEach((freq, i) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.type = 'sine'
      osc.frequency.value = freq
      const t = ctx.currentTime + i * 0.18
      gain.gain.setValueAtTime(0.001, t)
      gain.gain.exponentialRampToValueAtTime(0.3, t + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.16)
      osc.start(t)
      osc.stop(t + 0.18)
    })
  } catch (e) { /* audio blocked — ignore */ }
}

async function loadStatus() {
  if (!pin) return
  try {
    const d = await call({ action: 'status' })
    const items = d.queue?.items || []
    const sent = items.filter((i) => i.status === 'sent').length
    const failed = items.filter((i) => i.status === 'failed').length
    const pending = items.length - sent - failed
    const today = d.daily?.count || 0
    const dailyLimit = d.limits?.daily || 100
    const gap = d.limits?.gapMinutes || 5
    limits = d.limits || limits
    const paused = !!d.queue?.paused

    // credentials banner
    const credsPill = $('credsPill')
    if (credsPill) {
      credsPill.hidden = !!d.credsLoaded
      credsPill.textContent = 'SMTP credentials not loaded — log in again or re-save settings'
    }

    // completion notification + beep
    const processed = sent + failed
    if (items.length > 0 && processed === items.length && !wasComplete && hadQueue) {
      beep()
      toast(`Campaign complete — ${processed}/${items.length} emails processed`, true)
      try {
        if ('Notification' in window && Notification.permission === 'granted') {
          new Notification('Email Automator', { body: `Campaign complete — ${processed}/${items.length} emails processed` })
        }
      } catch (e) { /* ignore */ }
    }
    if (items.length > 0) hadQueue = true
    wasComplete = items.length > 0 && processed === items.length

    $('statTotal').textContent = items.length
    $('statSent').textContent = sent
    $('statPending').textContent = pending
    $('statFailed').textContent = failed

    $('todayCount').textContent = `${today} / ${dailyLimit}`
    $('todayBar').style.width = Math.min(100, (today / dailyLimit) * 100) + '%'
    $('todayInfo').textContent = today >= dailyLimit
      ? 'Daily limit reached — resumes automatically tomorrow (queue is saved)'
      : `One email every ${gap} minutes, max ${dailyLimit} per day`

    $('queueProgress').textContent = items.length ? `${sent + failed} / ${items.length}` : '—'
    $('queueBar').style.width = items.length ? ((sent + failed) / items.length) * 100 + '%' : '0%'
    $('queueCount').textContent = items.length

    let pillText, pillCls
    if (!items.length) { pillText = 'No queue'; pillCls = 'idle' }
    else if (paused) { pillText = 'Paused'; pillCls = 'paused' }
    else if (sent + failed >= items.length) { pillText = 'Complete'; pillCls = 'done' }
    else if (pending > 0) { pillText = 'Active'; pillCls = 'active' }
    else { pillText = 'Idle'; pillCls = 'idle' }
    setPill($('workerPill'), pillText, pillCls)
    $('queueInfo').textContent = pillText

    $('todayChip').textContent = `${today}/${dailyLimit}${paused ? ' • paused' : ''}`
    $('pausedChip').textContent = paused ? 'Yes' : 'No'
    $('pauseBtn').textContent = paused ? 'Resume' : 'Pause'
    $('pauseBtn').disabled = !items.length

    $('csvCount').textContent = d.draftCount
    $('startBtn').disabled = !d.draftCount
    $('antiSpamInfo').textContent =
      `Anti-spam: content scoring (blocks ${50}+), plain-text + HTML parts, ` +
      `max ${d.limits?.domainLimit || 100}/day per recipient domain, ` +
      `sends only between ${d.limits?.windowStart ?? 8}:00 and ${d.limits?.windowEnd ?? 21}:00 ` +
      `(${d.limits?.tz || 'Europe/Brussels'})`

    // status breakdown
    const total = items.length || 1
    const row = (label, cls, n) => `
      <div class="stack-row">
        <span class="muted">${label}</span>
        <div class="bar ${cls}"><div style="width:${(n / total) * 100}%"></div></div>
        <b>${n}</b>
      </div>`
    $('stack').innerHTML = row('Sent', 'sent', sent) + row('Pending', 'pending', pending) + row('Failed', 'failed', failed)

    // activity log
    const logs = d.logs || []
    $('logList').innerHTML = logs.length
      ? logs.map((l) => `<li><span class="t">${esc(l.t)}</span><span class="${l.ok ? 'ok' : 'bad'}">${l.ok ? '✓' : '✗'}</span><span class="d">${esc(l.detail || l.kind)}</span></li>`).join('')
      : '<li class="muted">No activity yet</li>'

    // recipients table
    const body = $('statusBody')
    body.innerHTML = items.length
      ? items.map((i) => `<tr><td>${esc(i.name)}</td><td>${esc(i.email)}</td><td>${badge(i.status)}</td><td>${esc(i.sentAt || '')}</td><td class="err">${esc(i.error || '')}</td></tr>`).join('')
      : `<tr><td colspan="5" class="muted">No queue yet — upload a CSV and press Start</td></tr>`
    $('tableInfo').textContent = items.length ? `total ${items.length} | sent ${sent} | pending ${pending} | failed ${failed}` : ''
  } catch (e) {
    /* ignore polling errors */
  }
}

async function loadAll() {
  try {
    const d = await call({ action: 'getSettings' })
    const s = d.settings || {}
    if (s.host) $('fHost').value = s.host
    if (s.port) $('fPort').value = s.port
    $('fSecure').checked = s.secure !== undefined ? !!s.secure : Number(s.port) === 465
    loadLocalCreds()
    if (d.user && !localStorage.getItem(LS_USER)) $('fUser').value = d.user
    if (s.fromName) $('fFrom').value = s.fromName
    if (s.subject) $('fSubject').value = s.subject
    if (s.body) $('fBody').value = s.body
    updatePreview()
    showSpam(d.spam)
  } catch (e) { /* ignore */ }
  loadStatus()
}

init()
