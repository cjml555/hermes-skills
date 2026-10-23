#!/usr/bin/env node
// Readiness probe for a running Hermes desktop dev instance.
//
// Gates on the DOM actually being mounted, because a bound CDP port and a
// served index.html both appear seconds before the real tree renders.
//
//   node scripts/dom-ready-probe.mjs [port] [timeoutSeconds]
//
// Exits 0 and prints the mounted JSON summary, or exits 1 on timeout.

const port = Number(process.argv[2] || 9222)
const timeoutS = Number(process.argv[3] || 120)

const sleep = ms => new Promise(r => setTimeout(r, ms))

async function fetchTarget() {
  const res = await fetch(`http://127.0.0.1:${port}/json/list`)
  const targets = await res.json()
  return (
    targets.find(t => t.type === 'page' && /5174|localhost|127\.0\.0\.1/.test(t.url)) ||
    targets.find(t => t.type === 'page') ||
    null
  )
}

function evaluate(page, expression) {
  const ws = new WebSocket(page.webSocketDebuggerUrl)
  const pending = new Map()
  let id = 0
  const ready = new Promise(r => { ws.onopen = r })
  ws.onmessage = e => {
    const m = JSON.parse(e.data)
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) }
  }
  return ready.then(() => {
    const p = new Promise(res => {
      const i = ++id
      pending.set(i, res)
      ws.send(JSON.stringify({ id: i, method: 'Runtime.evaluate', params: { expression, returnByValue: true, awaitPromise: true } }))
    })
    return p.then(r => {
      ws.close()
      return r.result?.result?.value
    })
  })
}

const EXPR = `JSON.stringify({
  mounted: document.readyState === 'complete' && (document.getElementById('root')?.childElementCount ?? 0) > 0,
  title: document.title,
  rootChildren: document.getElementById('root')?.childElementCount ?? 0,
  bodyTextLen: document.body.innerText.trim().length,
  bodyHead: document.body.innerText.trim().slice(0, 300),
  slots: Array.from(document.querySelectorAll('[data-slot]')).slice(0, 20).map(n => n.getAttribute('data-slot')),
  bg: getComputedStyle(document.body).backgroundColor
})`

const deadline = Date.now() + timeoutS * 1000
let last = null

while (Date.now() < deadline) {
  try {
    const page = await fetchTarget()
    if (page) {
      const raw = await evaluate(page, EXPR)
      if (raw) {
        last = JSON.parse(raw)
        if (last.mounted) {
          console.log(JSON.stringify(last, null, 2))
          process.exit(0)
        }
      }
    } else {
      last = { mounted: false, reason: 'no page target yet' }
    }
  } catch (err) {
    last = { mounted: false, reason: String(err.message || err) }
  }
  await sleep(5000)
}

console.log('TIMEOUT — not mounted within ' + timeoutS + 's')
console.log(JSON.stringify(last, null, 2))
process.exit(1)
