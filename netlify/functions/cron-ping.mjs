import { runSendOnce } from './_core.mjs'

// External cron (cron-job.org / UptimeRobot) is URL hit karta hai
// jab Netlify scheduled function 30-min pe free plan pe na chale.
export default async () => {
  const result = await runSendOnce()
  return new Response(JSON.stringify(result), { headers: { 'Content-Type': 'application/json' } })
}
