import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseCsv, hashPin, createPinMeta, replaceName, isHtml, todayUTC, DAILY_LIMIT, GAP_MINUTES } from '../netlify/functions/_core.mjs'

test('parseCsv: name/email headers, dedupe, invalid skip, quoted fields', () => {
  const r = parseCsv('Name,Email\n"Kumar, Raj",k@x.com\nSita,s@x.com\nbad,notanemail\nDup,k@x.com\n\nx,ABC@B.COM\n')
  assert.equal(r.error, '')
  assert.equal(r.items.length, 3)
  assert.equal(r.items[0].name, 'Kumar, Raj')
  assert.equal(r.items[0].status, 'pending')
  assert.equal(r.items[1].email, 's@x.com')
  assert.equal(r.items[2].name, 'x')
  assert.equal(r.items[2].email, 'abc@b.com')
})

test('parseCsv: empty and invalid', () => {
  assert.equal(parseCsv('').error, 'CSV khali hai')
  const r = parseCsv('name,email\ngarbage\n')
  assert.ok(r.error.includes('valid email'))
})

test('parseCsv: fallback columns when headers unknown (pehli row header hoti hai)', () => {
  const r = parseCsv('Ravi,ravi@x.com\nPooja,pooja@x.com\n')
  assert.equal(r.items.length, 1)
  assert.equal(r.items[0].email, 'pooja@x.com')
  assert.equal(r.items[0].name, 'Pooja')
})

test('pin: hash matches python format sha256(salt:pin), meta roundtrip', () => {
  const meta = createPinMeta('1234')
  assert.ok(meta.salt)
  assert.equal(meta.hash, hashPin('1234', meta.salt))
  assert.notEqual(meta.hash, hashPin('4321', meta.salt))
  assert.notEqual(meta.hash, hashPin('1234', 'different-salt'))
  // cross-check with known value (same algorithm as previous python/java versions)
  assert.equal(hashPin('1234', 'saltsalt'), '24a2c917aede3beaee28f105ea2efc48da57b93bc0dc6259f6c91dc235a30391')
})

test('replaceName: sirf {name} badalta hai', () => {
  assert.equal(replaceName('Hi {name}, kaise ho {name}?', 'Ravi'), 'Hi Ravi, kaise ho Ravi?')
  assert.equal(replaceName('No placeholder', 'Ravi'), 'No placeholder')
  assert.equal(replaceName('Hi {name}', ''), 'Hi ')
})

test('isHtml detection', () => {
  assert.ok(isHtml('<p>Hello</p>'))
  assert.ok(!isHtml('plain text with < less than'))
  assert.ok(!isHtml('simple'))
})

test('constants', () => {
  assert.equal(DAILY_LIMIT, 15)
  assert.equal(GAP_MINUTES, 30)
  assert.match(todayUTC(), /^\d{4}-\d{2}-\d{2}$/)
})
