import { test } from 'node:test'
import assert from 'node:assert/strict'
import { api, downloadPdf } from '../src/lib/api.ts'
import { invalidateAuthRequests } from '../src/lib/authEpoch.ts'

test('late unauthorized responses from the previous account do not sign out the current account', async () => {
  const originalFetch = globalThis.fetch
  const originalWindow = globalThis.window
  let resolveResponse
  let expired = 0
  globalThis.window = { dispatchEvent: () => { expired += 1 } }
  globalThis.fetch = () => new Promise(resolve => { resolveResponse = resolve })
  try {
    const request = api('/businesses')
    invalidateAuthRequests()
    resolveResponse(new Response(JSON.stringify({ detail: { message: 'Session expired' } }), { status: 401 }))
    await assert.rejects(request)
    assert.equal(expired, 0)
    const current = api('/businesses')
    resolveResponse(new Response(JSON.stringify({ detail: { message: 'Session expired' } }), { status: 401 }))
    await assert.rejects(current)
    assert.equal(expired, 1)
    const pdf = downloadPdf('business', null)
    invalidateAuthRequests()
    resolveResponse(new Response('{}', { status: 401 }))
    await assert.rejects(pdf)
    assert.equal(expired, 1)
  } finally {
    globalThis.fetch = originalFetch
    if (originalWindow === undefined) delete globalThis.window
    else globalThis.window = originalWindow
  }
})
