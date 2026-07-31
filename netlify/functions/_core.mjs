import { getStore } from '@netlify/blobs'
import crypto from 'node:crypto'
import nodemailer from 'nodemailer'

export const STORE_NAME = 'email-automator'
export const DAILY_LIMIT = 15
export const GAP_MINUTES = 30
export const LOCK_MINUTES = 5

// ================= Blob storage =================

export async function store() {
  return getStore({ name: STORE_NAME })
}

export async function getJson(key, fallback = null) {
  try {
    const s = await store()
    const raw = await s.get(key)
    if (!raw) return fallback
    return JSON.parse(raw)
  } catch {
    return fallback
  }
}

export async function setJson(key, value) {
  const s = await store()
  await s.set(key, JSON.stringify(value))
}

// ================= PIN =================

export function hashPin(pin, salt) {
  return crypto.createHash('sha256').update(salt + ':' + pin).digest('hex')
}

export function createPinMeta(pin) {
  const salt = crypto.randomBytes(16).toString('hex')
  return { salt, hash: hashPin(pin, salt) }
}

export async function checkPin(pin) {
  const meta = await getJson('meta')
  if (!meta?.hash) return false
  return hashPin(pin, meta.salt) === meta.hash
}

// ================= CSV =================

function parseLine(line) {
  const out = []
  let cur = ''
  let inQ = false
  for (let i = 0; i < line.length; i++) {
    const c = line[i]
    if (inQ) {
      if (c === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++ } else inQ = false
      } else cur += c
    } else if (c === '"') inQ = true
    else if (c === ',') { out.push(cur); cur = '' }
    else cur += c
  }
  out.push(cur)
  return out.map((s) => s.trim())
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function parseCsv(text) {
  const lines = String(text || '').replace(/\r/g, '').split('\n').filter((l) => l.trim() !== '')
  if (lines.length === 0) return { items: [], error: 'CSV khali hai' }
  const header = parseLine(lines[0])
  let nameIdx = header.findIndex((h) => h.toLowerCase() === 'name')
  let emailIdx = header.findIndex((h) => h.toLowerCase() === 'email')
  if (nameIdx === -1) nameIdx = 0
  if (emailIdx === -1) emailIdx = Math.min(1, header.length - 1)
  const items = []
  const seen = new Set()
  for (let i = 1; i < lines.length; i++) {
    const cells = parseLine(lines[i])
    const email = (cells[emailIdx] || '').toLowerCase()
    if (!EMAIL_RE.test(email) || seen.has(email)) continue
    seen.add(email)
    const name = (nameIdx < cells.length ? cells[nameIdx] : '') || email.split('@')[0]
    items.push({ name, email, status: 'pending', error: '', sentAt: '' })
  }
  return { items, error: items.length ? '' : 'CSV me koi valid email nahi mila (name,email headers check karo)' }
}

// ================= Email =================

export function replaceName(text, name) {
  return String(text || '').split('{name}').join(name || '')
}

export function isHtml(text) {
  return /<[a-z][\s\S]*>/i.test(text)
}

export async function sendMail(settings, to, subject, body) {
  const transporter = nodemailer.createTransport({
    host: settings.host || 'smtp.gmail.com',
    port: Number(settings.port) || 465,
    secure: settings.secure !== undefined ? !!settings.secure : (Number(settings.port) || 465) === 465,
    auth: { user: settings.user, pass: settings.pass },
  })
  const mail = {
    from: `"${settings.fromName || settings.user}" <${settings.user}>`,
    to,
    subject,
    headers: { 'List-Unsubscribe': `<mailto:${settings.user}?subject=unsubscribe>` },
  }
  if (isHtml(body)) mail.html = body
  else mail.text = body
  return transporter.sendMail(mail)
}

// ================= Core send rules (har run me ek email) =================

export function todayUTC() {
  return new Date().toISOString().slice(0, 10)
}

export async function runSendOnce() {
  const settings = await getJson('settings')
  if (!settings || !settings.user || !settings.pass) return { status: 'no-settings' }

  const queue = await getJson('queue', { items: [] })
  if (!queue.items.length) return { status: 'empty' }
  if (queue.paused) return { status: 'paused' }

  // concurrency lock (scheduled + cron-ping ek saath na chalein)
  const lock = await getJson('lock')
  if (lock && Date.now() - lock.t < LOCK_MINUTES * 60 * 1000) return { status: 'locked' }
  await setJson('lock', { t: Date.now() })

  const today = todayUTC()
  let daily = await getJson('daily', { date: today, count: 0, lastSentAt: '' })
  if (daily.date !== today) daily = { date: today, count: 0, lastSentAt: '' }

  if (daily.count >= DAILY_LIMIT) return { status: 'daily-limit', count: daily.count }

  if (daily.lastSentAt) {
    const elapsed = Date.now() - new Date(daily.lastSentAt).getTime()
    const waitMs = GAP_MINUTES * 60 * 1000 - elapsed
    if (waitMs > 0) return { status: 'gap', waitMin: Math.ceil(waitMs / 60000) }
  }

  const idx = queue.items.findIndex((i) => i.status === 'pending')
  if (idx === -1) return { status: 'done' }

  const item = queue.items[idx]
  try {
    await sendMail(settings, item.email, replaceName(settings.subject, item.name), replaceName(settings.body, item.name))
    item.status = 'sent'
    item.error = ''
    item.sentAt = new Date().toISOString()
    daily.count += 1
    daily.lastSentAt = new Date().toISOString()
    await setJson('queue', queue)
    await setJson('daily', daily)
    return { status: 'sent', to: item.email, count: daily.count }
  } catch (err) {
    item.status = 'failed'
    item.error = err?.message || 'send failed'
    await setJson('queue', queue)
    return { status: 'failed', to: item.email, error: item.error }
  }
}
