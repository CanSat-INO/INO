import { useEffect, useState } from 'react'

type BenchEvent = {
  kind: string
  role?: string
  wall_ns?: number
  capture_id?: number
  snapshot_id?: string
  state?: string
  detail?: unknown
  sensors?: Record<string, unknown>
  images?: { left?: string; right?: string }
}

function imagePath(value: string | undefined) {
  return value && /^\/api\/virtual\/image\?id=[1-9][0-9]*&side=(left|right)$/.test(value)
    ? value : undefined
}

export default function VirtualBench() {
  const [events, setEvents] = useState<BenchEvent[]>([])
  const [session, setSession] = useState('')
  const [status, setStatus] = useState('受信待ち')
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function refresh() {
      try {
        const response = await fetch('/api/virtual/events', {
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
        })
        if (!response.ok) throw new Error('HTTP ' + response.status)
        const data: unknown = await response.json()
        if (!Array.isArray(data)) throw new Error('イベント形式が不正です')
        setEvents(data.filter(event => event && typeof event.kind === 'string'))
        setSession(response.headers.get('X-INO-Session') ?? '')
        setStatus(response.headers.get('X-INO-Live') === '1'
          ? 'ライブ更新中 · 読取専用' : '停止または更新待ち · 保存データを表示中')
      } catch (error) {
        if (!controller.signal.aborted) setStatus('受信できません · ' + String(error))
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, 1500)
      }
    }
    void refresh()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [])

  const recent = [...events].reverse()
  const telemetry = recent.find(event => event.kind === 'telemetry')
  const state = recent.find(event => event.kind === 'module_status' || event.kind === 'deployment')
  const transfer = recent.find(event => event.kind === 'image_transfer')
  const capture = recent.find(event => event.kind === 'capture_complete' && event.capture_id === transfer?.capture_id)
  const errors = recent.filter(event => event.kind === 'error').slice(0, 10)
  return (
    <main style={{ maxWidth: '72rem', margin: 'auto', padding: '1rem', overflow: 'auto', maxHeight: '100vh' }}>
      <h1>CanSat INØ 仮想地上局</h1>
      <p role="status">{status}</p>
      <section>
        <h2>テレメトリと仮想センサー</h2>
        <pre>{telemetry ? JSON.stringify(telemetry.sensors, null, 2) : '未受信'}</pre>
        <h2>ミッション・モジュール状態</h2>
        <pre>{state ? JSON.stringify(state, null, 2) : '状態イベントなし'}</pre>
      </section>
      <section>
        <h2>ステレオ画像</h2>
        <p>Capture ID {transfer?.capture_id ?? '未受信'} ／ 取得時刻（シミュレーション 秒_ナノ秒） {capture?.snapshot_id ?? '未記録'}</p>
        {(['left', 'right'] as const).map(side => {
          const src = imagePath(transfer?.images?.[side])
          return (
            <figure key={session + side} style={{ display: 'inline-block', margin: '0.5rem', maxWidth: 'min(100%, 30rem)' }}>
              {src ? <img src={src} alt={side === 'left' ? '左カメラ画像' : '右カメラ画像'} style={{ maxWidth: '100%' }} /> : '未受信'}
              <figcaption>{side === 'left' ? '左カメラ' : '右カメラ'}</figcaption>
            </figure>
          )
        })}
      </section>
      <section>
        <h2>異常イベント</h2>
        {errors.length ? <ul>{errors.map((event, index) => <li key={event.wall_ns ?? index}>{event.role} {String(event.detail ?? '')}</li>)}</ul> : <p>異常イベントなし</p>}
      </section>
    </main>
  )
}
