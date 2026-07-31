import { runSendOnce } from './_core.mjs'

export default async () => {
  const result = await runSendOnce()
  console.log('sendScheduled:', JSON.stringify(result))
  return new Response(JSON.stringify(result), { headers: { 'Content-Type': 'application/json' } })
}
