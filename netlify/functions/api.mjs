import { getJson, setJson, createPinMeta, checkPin, parseCsv, sendMail, replaceName } from './_core.mjs'

export default async (req) => {
  if (req.method === 'GET') {
    const meta = await getJson('meta')
    return json({ hasPin: Boolean(meta?.hash) })
  }

  let body = {}
  try {
    body = await req.json()
  } catch {
    /* ignore */
  }
  const action = body.action

  try {
    switch (action) {
      case 'setPin': {
        const meta = await getJson('meta')
        if (meta?.hash) return json({ error: 'PIN pehle se set hai — login karke changePin use karo' })
        if (!body.pin || String(body.pin).length < 4) return json({ error: 'PIN kam se kam 4 characters ka rakho' })
        await setJson('meta', createPinMeta(String(body.pin)))
        return json({ ok: true })
      }

      case 'login': {
        if (!(await checkPin(body.pin))) return json({ error: 'Galat PIN' }, 401)
        return json({ ok: true })
      }

      case 'changePin': {
        if (!(await checkPin(body.pin))) return json({ error: 'Galat PIN' }, 401)
        if (!body.newPin || String(body.newPin).length < 4) return json({ error: 'Naya PIN kam se kam 4 characters' })
        await setJson('meta', createPinMeta(String(body.newPin)))
        return json({ ok: true })
      }

      case 'saveSettings': {
        if (!(await checkPin(body.pin))) return json({ error: 'Galat PIN' }, 401)
        const s = {
          host: String(body.host || '').trim() || 'smtp.gmail.com',
          port: Number(body.port) || 465,
          secure: body.secure !== undefined ? !!body.secure : Number(body.port) === 465,
          user: String(body.user || '').trim(),
          pass: String(body.pass || ''),
          fromName: String(body.fromName || '').trim(),
          subject: String(body.subject || ''),
          body: String(body.body || ''),
        }
        if (!s.user || !s.pass) return json({ error: 'Email aur password dono zaroori hain' })
        await setJson('settings', s)
        return json({ ok: true })
      }

      case 'getSettings': {
        if (!(await checkPin(body.pin))) return json({ error: 'Galat PIN' }, 401)
        return json({ settings: (await getJson('settings')) || {} })
      }

      case 'uploadCsv': {
        if (!(await checkPin(body.pin))) return json({ error: 'Galat PIN' }, 401)
        const { items, error } = parseCsv(body.csv)
        if (error) return json({ error })
        await setJson('draft', { items })
        return json({ ok: true, count: items.length, preview: items.slice(0, 5) })
      }

      case 'start': {
        if (!(await checkPin(body.pin))) return json({ error: 'Galat PIN' }, 401)
        const draft = (await getJson('draft')) || { items: [] }
        if (!draft.items.length) return json({ error: 'Pehle CSV upload karo' })
        await setJson('queue', { items: draft.items, paused: false })
        await setJson('draft', { items: [] })
        return json({ ok: true, count: draft.items.length })
      }

      case 'pause':
      case 'resume': {
        if (!(await checkPin(body.pin))) return json({ error: 'Galat PIN' }, 401)
        const queue = (await getJson('queue')) || { items: [] }
        queue.paused = action === 'pause'
        await setJson('queue', queue)
        return json({ ok: true, paused: queue.paused })
      }

      case 'status': {
        if (!(await checkPin(body.pin))) return json({ error: 'Galat PIN' }, 401)
        const settings = (await getJson('settings')) || {}
        const queue = (await getJson('queue')) || { items: [] }
        const draft = (await getJson('draft')) || { items: [] }
        const daily = (await getJson('daily')) || { date: new Date().toISOString().slice(0, 10), count: 0 }
        return json({
          settings: { exists: !!(settings.user && settings.pass) },
          queue,
          draftCount: draft.items.length,
          daily,
        })
      }

      case 'testSend': {
        if (!(await checkPin(body.pin))) return json({ error: 'Galat PIN' }, 401)
        const settings = await getJson('settings')
        if (!settings || !settings.user || !settings.pass) return json({ error: 'Pehle settings save karo' })
        try {
          await sendMail(settings, settings.user, replaceName(settings.subject, 'Test'), replaceName(settings.body, 'Test'))
          return json({ ok: true, message: 'Test email bhej di gayi (aapke hi email pe)' })
        } catch (err) {
          return json({ error: 'Send fail: ' + (err?.message || err) })
        }
      }

      default:
        return json({ error: 'Unknown action' })
    }
  } catch (err) {
    return json({ error: err?.message || 'Server error' })
  }
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
