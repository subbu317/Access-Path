import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Accessibility, Activity, ArrowRight, BarChart3, Check, CheckCircle2, ChevronRight,
  CircleHelp, ClipboardCheck, Clock3, Compass, ExternalLink, Flag, Footprints,
  GitBranch, Info, Layers3, LockKeyhole, Map, MapPin, Moon, Navigation, RefreshCw,
  Route, Send, Settings2, ShieldAlert, ShieldCheck, SlidersHorizontal, Sun, TriangleAlert,
  Users, X
} from 'lucide-react'
import MapView from './components/MapView.jsx'
import {
  calculateRoute, getAdminOverview, getEvaluations, getNetwork, getReports,
  moderateReport, runBenchmark, submitReport
} from './api.js'

const PROFILES = [
  { id: 'wheelchair', name: 'Wheelchair', subtitle: 'No stairs · curb limits', icon: Accessibility },
  { id: 'walker', name: 'Walker', subtitle: 'Low gradients · step-free', icon: Footprints },
  { id: 'step_free', name: 'Step-free', subtitle: 'No steps or high curbs', icon: Navigation },
  { id: 'pedestrian', name: 'Pedestrian', subtitle: 'General walkability', icon: Compass }
]
const OBSTACLES = [
  ['blocked', 'Path blocked'], ['temporary_obstruction', 'Temporary obstruction'],
  ['stairs', 'Staircase / steps'], ['missing_curb', 'Missing accessible curb'],
  ['steep_slope', 'Steep slope'], ['broken_surface', 'Damaged surface']
]
const TABS = [
  { id: 'routes', label: 'Route planner', icon: Route },
  { id: 'reports', label: 'Community reports', icon: Flag },
  { id: 'admin', label: 'Moderation', icon: ShieldCheck },
  { id: 'evaluation', label: 'Evaluation lab', icon: BarChart3 }
]
const fmt = (value, digits = 0) => value == null ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits })
const percent = value => value == null ? '—' : `${(100 * value).toFixed(0)}%`
const time = iso => iso ? new Date(iso).toLocaleString() : '—'
const safeError = e => e?.message || 'Unexpected request error'

function Status({ status }) {
  return <span className={`status-tag status-${status}`}>{status}</span>
}

function Kpi({ icon: Icon, label, value, detail }) {
  return <div className="kpi"><div className="kpi-icon"><Icon size={18}/></div><div>
    <div className="kpi-label">{label}</div><div className="kpi-value">{value}</div>
    {detail && <div className="kpi-detail">{detail}</div>}
  </div></div>
}

function ControlPanel({ network, startId, endId, setStartId, setEndId, pickMode, setPickMode,
  profile, setProfile, risk, setRisk, algorithm, setAlgorithm, routeLoading, result,
  refreshAll, refreshing, swapPoints }) {
  return <aside className="panel control-panel">
    <div className="eyebrow"><span className="eyebrow-bar"/> THE ROUTE ENGINE <span className="eyebrow-sub">01 / PLAN</span></div>
    <h1>Find a path.<br/><em>Know the unknowns.</em></h1>
    <p className="section-copy">Personalized pedestrian routing with evidence-aware trade-offs, not false accessibility promises.</p>
    <div className="panel-label">YOUR JOURNEY <span>Click a map node or choose below</span></div>
    <div className="journey-box">
      <div className="journey-row">
        <div className="journey-point from">A</div>
        <div className="journey-selector"><label htmlFor="start">STARTING POINT</label>
          <select id="start" value={startId} onChange={e => setStartId(e.target.value)}>
            {(network?.nodes || []).map(n => <option key={n.id} value={n.id}>{n.label}</option>)}
          </select></div>
        <button className={`pick-point ${pickMode === 'start' ? 'active' : ''}`} onClick={() => setPickMode('start')} title="Click a node on the map to set your starting point" aria-label="Select starting point on the map"><MapPin size={17}/></button>
      </div>
      <div className="journey-dots"><i/><i/><i/></div>
      <div className="journey-row">
        <div className="journey-point to">B</div>
        <div className="journey-selector"><label htmlFor="destination">DESTINATION</label>
          <select id="destination" value={endId} onChange={e => setEndId(e.target.value)}>
            {(network?.nodes || []).map(n => <option key={n.id} value={n.id}>{n.label}</option>)}
          </select></div>
        <button className={`pick-point ${pickMode === 'end' ? 'active' : ''}`} onClick={() => setPickMode('end')} title="Click a node on the map to set your destination" aria-label="Select destination on the map"><MapPin size={17}/></button>
      </div>
    </div>
    <div className="helper-row"><button className="text-action" onClick={swapPoints}><RefreshCw size={13}/> Swap points</button>
      <span>{network?.nodes?.length || 0} mapped nodes</span></div>
    <div className="panel-label space-top">MOBILITY PROFILE <span>Hard constraints apply</span></div>
    <div className="profile-options">
      {PROFILES.map(({ id, name, subtitle, icon: Icon }) => (
        <button type="button" key={id} className={`profile-option ${profile === id ? 'selected' : ''}`}
          aria-pressed={profile === id} onClick={() => setProfile(id)}>
          <span className="profile-icon"><Icon size={19}/></span><span className="profile-text"><strong>{name}</strong><small>{subtitle}</small></span>
          <span className="selection-radio">{profile === id && <Check size={13}/>}</span>
        </button>
      ))}
    </div>
    <div className="panel-label space-top">UNCERTAINTY AVERSION <span>{risk}%</span></div>
    <div className="range-wrapper"><input aria-label="Uncertainty aversion" type="range" min="0" max="100" step="5" value={risk} onChange={e => setRisk(Number(e.target.value))}/>
      <div className="range-ends"><span>Shorter</span><span>Prefer evidence</span></div></div>
    <div className="select-flex"><label htmlFor="algorithm">SEARCH ENGINE</label>
      <select id="algorithm" value={algorithm} onChange={e => setAlgorithm(e.target.value)}><option value="astar">A* · informed search</option><option value="dijkstra">Dijkstra · exact search</option></select></div>
    <button className="primary-button" onClick={refreshAll} disabled={refreshing}>
      {refreshing ? <RefreshCw size={17} className="spin"/> : <Route size={17}/>} {refreshing ? 'Refreshing network…' : 'Refresh live conditions'} <ArrowRight size={16}/>
    </button>
    <div className="routing-state"><span className={`little-pulse ${routeLoading ? 'busy' : ''}`}/>
      {routeLoading ? 'Computing graph routes…' : result ? `Calculated in ${fmt(result.computation_ms, 2)} ms` : 'Awaiting route calculation'}</div>
  </aside>
}

function RouteCards({ result, activeRoute, setActiveRoute, loading, startName, endName }) {
  const [showSegments, setShowSegments] = useState(false)
  const selected = result?.routes?.[activeRoute]
  return <div className="route-results">
    <div className="results-heading"><div><div className="eyebrow">02 / THE RECOMMENDATION</div>
      <h2>Routes, with the trade-offs.</h2></div><div className="route-compare-meta"><GitBranch size={15}/> {result?.routes?.length || 0} feasible alternatives</div></div>
    {!result ? <div className="empty-results"><RefreshCw size={19} className={loading ? 'spin' : ''}/> {loading ? 'Computing routes…' : 'Choose two distinct nodes to calculate a route.'}</div> : <>
      <div className="route-card-grid">
        {result.routes.map((route, index) => <button key={route.id} onClick={() => { setActiveRoute(index); setShowSegments(false) }}
          aria-pressed={activeRoute === index} className={`route-card ${activeRoute === index ? 'active' : ''}`}>
          <div className="route-card-top"><span className={`route-number route-n${index}`}>{String(index+1).padStart(2,'0')}</span>
            <span className="route-name">{route.label}</span>{index === 0 && <span className="recommended">RECOMMENDED</span>}{activeRoute === index && <CheckCircle2 size={17} className="chosen-check"/>}</div>
          <strong className="route-distance">{fmt(route.distance_m)} <small>m</small></strong>
          <div className="confidence-meter"><div className="meter-track"><div style={{ width: percent(route.confidence) }} /></div><span>{percent(route.confidence)} evidence score</span></div>
          <div className="route-card-bottom"><span><ShieldCheck size={14}/> {percent(route.verified_coverage)} verified</span>
            <span><TriangleAlert size={14}/> {route.uncertain_segments} uncertain</span></div>
        </button>)}
      </div>
      {selected ? <div className="explanation-card">
        <div className="explanation-title"><Info size={17}/> WHY THIS ROUTE?</div>
        <p>{activeRoute === 0 ? result.explanation : `This alternative covers ${fmt(selected.distance_m)} m with ${percent(selected.verified_coverage)} distance-based verified-data coverage and ${selected.uncertain_segments} flagged segments. Compare its evidence with the preferred route before deciding.`}</p>
        <div className="metric-pills"><span><Route size={14}/> {fmt(selected.distance_m)} m</span><span><ShieldAlert size={14}/> {selected.unsuitable_segments} confirmed barriers</span>
          <span><Activity size={14}/> {fmt(result.computation_ms, 2)} ms</span></div>
        <button className="text-action segments-toggle" aria-expanded={showSegments} onClick={() => setShowSegments(x => !x)}><Layers3 size={15}/> {showSegments ? 'Hide' : 'Inspect'} segment evidence <ChevronRight size={15} className={showSegments ? 'rotate' : ''}/></button>
        {showSegments && <div className="segment-list">{selected.segments.map((segment, index) => <div className="segment" key={`${segment.edge_id}-${index}`}>
          <span className="segment-index">{index+1}</span><div><strong>{segment.name}</strong><small>{segment.edge_id} · {fmt(segment.distance_m)} m · {segment.verification} · {segment.survey_age_days == null ? "age unknown" : `${fmt(segment.survey_age_days)} days old`}</small>
            {segment.warnings.length > 0 && <div className="segment-warnings"><TriangleAlert size={12}/>{segment.warnings.join(' · ')}</div>}</div><span className="segment-confidence">{percent(segment.confidence)}</span>
        </div>)}</div>}
      </div> : <div className="empty-results alert"><ShieldAlert size={18}/> No path satisfies the confirmed hard barriers for this profile. Try other endpoints or another mobility profile.</div>}
      {result.shortest && selected && <div className="comparison-note"><div><span className="muted">DISTANCE-ONLY BASELINE</span><strong>{fmt(result.shortest.distance_m)} m</strong><span>{result.shortest.unsuitable_segments} unsuitable segments</span></div><ArrowRight size={18}/><div><span className="muted">ACCESSPATH PREFERRED</span><strong>{fmt(selected.distance_m)} m</strong><span>{selected.unsuitable_segments} unsuitable segments</span></div></div>}
      <p className="micro-disclaimer">Route confidence is a heuristic evidence score—not a field-calibrated safety probability. No route is certified accessible.</p>
    </>}
  </div>
}

function ReportsPanel({ network, reports, selectedEdge, setSelectedEdge, refreshAll, setError, setNotice }) {
  const [type, setType] = useState('blocked')
  const [severity, setSeverity] = useState('2')
  const [description, setDescription] = useState('')
  const [days, setDays] = useState(7)
  const [sending, setSending] = useState(false)
  const [filter, setFilter] = useState('all')
  const edges = network?.edges || []
  const chosen = edges.find(edge => edge.id === selectedEdge)
  const visible = filter === 'all' ? reports : reports.filter(report => report.status === filter)
  async function send(e) {
    e.preventDefault()
    setSending(true)
    setError('')
    try {
      await submitReport({ edge_id: selectedEdge, obstacle_type: type, severity: Number(severity),
        description: description.trim(), expires_in_days: Number(days) })
      setDescription('')
      setNotice('Report submitted for moderation. Until verified, it is an uncertainty signal, not a confirmed obstruction.')
      await refreshAll()
    } catch (err) { setError(safeError(err)) }
    finally { setSending(false) }
  }
  return <aside className="panel control-panel reports-panel">
    <div className="eyebrow"><span className="eyebrow-bar"/> COMMUNITY INTELLIGENCE <span className="eyebrow-sub">01 / REPORT</span></div>
    <h1>Make the map<br/><em>more honest.</em></h1>
    <p className="section-copy">Tap any map segment to report an obstacle. Verified reports immediately change the graph's feasible routes.</p>
    <form onSubmit={send} className="report-form">
      <label>PATH SEGMENT<select value={selectedEdge} onChange={e => setSelectedEdge(e.target.value)} required>
        {edges.map(edge => <option key={edge.id} value={edge.id}>{edge.id} · {edge.name}</option>)}</select></label>
      {chosen && <div className="selected-edge-facts"><MapPin size={15}/> {fmt(chosen.distance_m)} m · {chosen.verification} · {chosen.reports.filter(r => r.status === 'verified').length} active verified report(s)</div>}
      <label>OBSTACLE TYPE<select value={type} onChange={e => setType(e.target.value)}>{OBSTACLES.map(([value, text]) => <option value={value} key={value}>{text}</option>)}</select></label>
      <div className="split-fields"><label>SEVERITY<select value={severity} onChange={e => setSeverity(e.target.value)}><option value="1">Low</option><option value="2">Medium</option><option value="3">High</option></select></label>
        <label>EXPIRES AFTER<select value={days} onChange={e => setDays(e.target.value)}><option value={1}>1 day</option><option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option></select></label></div>
      <label>DESCRIPTION<textarea value={description} onChange={e => setDescription(e.target.value)} required minLength={8} maxLength={500} rows={4} placeholder="What did you observe? Provide details that a reviewer can check."/></label>
      <button className="primary-button" disabled={sending || !selectedEdge || description.trim().length < 8}><Send size={16}/>{sending ? 'Submitting…' : 'Submit for review'} <ArrowRight size={16}/></button>
    </form>
    <div className="policy-note"><TriangleAlert size={16}/> Community reports are unverified until reviewed. Do not rely on this demo for travel decisions.</div>
    <div className="report-filter"><strong>COMMUNITY FEED</strong><select aria-label="Filter community reports" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All statuses</option><option value="pending">Pending</option><option value="reviewed">Reviewed</option><option value="verified">Verified</option><option value="resolved">Resolved</option><option value="expired">Expired</option></select></div>
    <div className="feed-items">{visible.length ? visible.map(report => <div className="feed-item" key={report.id}>
      <div className="feed-head"><strong>#{report.id} · {report.obstacle_type.replaceAll('_', ' ')}</strong><Status status={report.status}/></div>
      <p>{report.description}</p><div className="feed-footer"><button onClick={() => setSelectedEdge(report.edge_id)} className="text-action">{report.edge_id} · view segment</button><span>{time(report.created_at)}</span></div>
    </div>) : <p className="muted">No reports match this filter.</p>}</div>
  </aside>
}

function AdminScreen({ adminKey, setAdminKey, adminUnlocked, setAdminUnlocked, reports, overview,
  setOverview, refreshAll, setError, setNotice }) {
  const [notes, setNotes] = useState({})
  const [busy, setBusy] = useState(null)
  const [unlocking, setUnlocking] = useState(false)
  async function unlock(e) {
    e.preventDefault()
    setUnlocking(true)
    try { const data = await getAdminOverview(adminKey); setOverview(data); setAdminUnlocked(true); setError('') }
    catch (err) { setAdminUnlocked(false); setError(safeError(err)) }
    finally { setUnlocking(false) }
  }
  async function takeAction(report, action) {
    setBusy(report.id)
    try {
      await moderateReport(report.id, action, notes[report.id] || '', adminKey)
      setNotice(`Report #${report.id}: ${action} recorded. Active network revision updated.`)
      await refreshAll()
      setOverview(await getAdminOverview(adminKey))
    } catch (err) { setError(safeError(err)) }
    finally { setBusy(null) }
  }
  const actionable = reports.filter(r => ['pending', 'reviewed', 'verified'].includes(r.status))
  return <section className="standalone-screen">
    <div className="screen-header"><div><div className="eyebrow">03 / ADMIN WORKSPACE</div><h1>Moderation <em>command center.</em></h1><p>Change confidence and traversability only after an explicit review decision.</p></div><ShieldCheck size={42} className="section-hero-icon"/></div>
    <div className="admin-layout"><div className="glass-card admin-auth">
      <div className="card-title"><LockKeyhole size={20}/> LOCAL DEMO ACCESS</div>
      <p>This demo uses a key header for local testing, not production authentication. Set <code>ACCESSPATH_ADMIN_KEY</code> for your machine.</p>
      <form className="admin-login" onSubmit={unlock}><input type="password" autoComplete="off" aria-label="Admin demo key" placeholder="Demo key: demo-admin-key" value={adminKey} onChange={e => {setAdminKey(e.target.value);setAdminUnlocked(false)}}/>
        <button className="primary-button" disabled={unlocking || !adminKey}>{unlocking ? 'Checking…' : 'Unlock dashboard'}</button></form>
      {adminUnlocked && <div className="success-line"><CheckCircle2 size={17}/> Moderation unlocked for this session</div>}
      <div className="mini-warning"><Info size={16}/> Never deploy the bundled demo key or expose moderation publicly without real authentication and rate limiting.</div>
    </div>
    <div className="glass-card admin-stats"><div className="card-title"><Activity size={19}/> NETWORK HEALTH</div>
      {adminUnlocked && overview ? <><div className="stats-duo"><div><strong>{overview.anonymous_route_requests}</strong><small>Anonymous routing tests</small></div><div><strong>{reports.length}</strong><small>Community reports</small></div></div>
        <div className="status-counter-row">{Object.entries(overview.status_counts).map(([key, count]) => <span key={key}><Status status={key}/> {count}</span>)}</div></>
        : <div className="locked-content"><LockKeyhole size={27}/><span>Unlock to view moderation statistics</span></div>}
    </div></div>
    {adminUnlocked ? <div className="dashboard-columns"><div className="glass-card moderation-queue"><div className="card-title"><ClipboardCheck size={19}/> ACTIVE REPORT QUEUE <span className="count-chip">{actionable.length}</span></div>
      {actionable.length ? actionable.map(report => <div className="mod-item" key={report.id}>
        <div className="mod-top"><div><strong>#{report.id} · {report.obstacle_type.replaceAll('_',' ')}</strong><small>{report.edge_id} · severity {report.severity} · {time(report.created_at)}</small></div><Status status={report.status}/></div>
        <p>{report.description}</p><input aria-label={`Moderation note for report ${report.id}`} placeholder="Reviewer note (optional)" value={notes[report.id] || ''} onChange={e => setNotes(s => ({...s, [report.id]:e.target.value}))}/>
        <div className="mod-actions">{report.status === 'pending' && <button disabled={busy === report.id} onClick={() => takeAction(report,'review')}>Mark reviewed</button>}
          {['pending','reviewed'].includes(report.status) && <><button disabled={busy === report.id} className="positive" onClick={() => takeAction(report,'verify')}>Verify</button><button disabled={busy === report.id} onClick={() => takeAction(report,'reject')}>Reject</button></>}
          {report.status === 'verified' && <button disabled={busy === report.id} className="positive" onClick={() => takeAction(report,'resolve')}>Mark resolved</button>}
          <button disabled={busy === report.id} onClick={() => takeAction(report,'expire')}>Expire</button></div>
      </div>) : <div className="empty-results"><CheckCircle2 size={19}/> No reports require action.</div>}
    </div><div className="glass-card audit-list"><div className="card-title"><Clock3 size={19}/> AUDIT TRAIL</div>
      {overview?.audit?.length ? overview.audit.map(row => <div className="audit-item" key={row.id}><span className="audit-icon"><Check size={14}/></span><div><strong>#{row.report_id} · {row.action}</strong><small>{row.note || 'No reviewer note'} · {time(row.occurred_at)}</small></div></div>) : <p className="muted">Moderation actions will appear here.</p>}
    </div></div> : <div className="locked-large"><LockKeyhole size={28}/> Enter your local admin key to moderate community reports.</div>}
  </section>
}

function EvaluationScreen({ latestRun, adminKey, refreshEvaluations, setError, setNotice }) {
  const [running, setRunning] = useState(false)
  async function run() {
    setRunning(true)
    try {
      const result = await runBenchmark(adminKey)
      await refreshEvaluations()
      setNotice(`Evaluation #${result.id} computed and saved to SQLite.`)
    } catch (err) { setError(safeError(err)) }
    finally { setRunning(false) }
  }
  const results = latestRun?.results
  const calibration = results?.confidence_calibration
  return <section className="standalone-screen">
    <div className="screen-header"><div><div className="eyebrow">04 / SCIENTIFIC EVALUATION</div><h1>Measure the <em>difference.</em></h1><p>Real algorithm runs, synthetic ground-truth simulations, and reproducible scores.</p></div><BarChart3 size={42} className="section-hero-icon"/></div>
    <div className="benchmark-header glass-card"><div><strong>AccessPath vs distance-only Dijkstra</strong><p>12 origin–destination pairs × 4 mobility profiles. Metrics are computed from the current graph, never hardcoded.</p></div>
      <button className="primary-button" disabled={running || !adminKey} onClick={run}><Activity size={17}/>{running ? 'Running benchmark…' : 'Run benchmark'}<ArrowRight size={16}/></button></div>
    {!adminKey && <p className="helper-hint"><Info size={15}/> Enter the local demo key in Moderation before running a benchmark.</p>}
    {results ? <>
      <div className="evaluation-kpis"><Kpi icon={GitBranch} label="Tested scenarios" value={`${results.feasible_cases} / ${results.case_count}`} detail="Feasible graph pairs"/>
        <Kpi icon={ShieldAlert} label="Barriers avoided" value={fmt(results.confirmed_obstacles_avoided)} detail="Summed across test cases"/>
        <Kpi icon={Route} label="Distance overhead" value={`${fmt(results.mean_distance_overhead_pct, 1)}%`} detail="Compared with shortest route"/>
        <Kpi icon={Activity} label="Search time" value={`${fmt(results.mean_route_compute_ms, 2)} ms`} detail="Average local computation"/></div>
      <div className="dashboard-columns"><div className="glass-card benchmark-detail"><div className="card-title"><SlidersHorizontal size={19}/> ROUTE QUALITY</div>
        <div className="metric-line"><span>Shortest baseline unsuitable edges</span><strong>{fmt(results.mean_shortest_unsuitable, 3)}</strong></div>
        <div className="metric-line"><span>AccessPath unsuitable edges</span><strong>{fmt(results.mean_accesspath_unsuitable, 3)}</strong></div>
        <div className="metric-line"><span>Mean verified-data coverage</span><strong>{percent(results.mean_verified_coverage)}</strong></div>
        <div className="metric-line"><span>Data revision evaluated</span><strong>#{results.network_revision}</strong></div>
        <h3>Example case results</h3>
        <div className="table-scroller"><table><thead><tr><th>Profile / journey</th><th>Baseline</th><th>AccessPath</th><th>Avoided</th></tr></thead>
          <tbody>{results.cases.filter(c => c.feasible).slice(0, 12).map((c, i) => <tr key={i}>
            <td>{c.profile}<small>{c.from} → {c.to}</small></td><td>{fmt(c.shortest_m)} m</td><td>{fmt(c.selected_m)} m</td><td>{c.confirmed_obstacles_avoided}</td>
          </tr>)}</tbody></table></div>
      </div><div className="glass-card calibration-detail"><div className="card-title"><Activity size={19}/> CONFIDENCE CALIBRATION</div>
        <p>Predicted path evidence scores compared against independently generated synthetic edge outcomes.</p>
        <div className="calibration-top"><div><small>BRIER SCORE ↓</small><strong>{fmt(calibration.brier_score, 4)}</strong></div><div><small>EXPECTED CALIBRATION ERROR ↓</small><strong>{fmt(calibration.expected_calibration_error, 4)}</strong></div></div>
        <div className="calibration-chart"><div className="chart-legend"><span className="pred-legend"/> Predicted <span className="actual-legend"/> Observed</div>
          {calibration.bins.map(bin => <div className="chart-row" key={bin.range}><span>{bin.range}</span><div className="bar-pair"><div className="bar predicted" style={{width: percent(bin.predicted)}}/><div className="bar observed" style={{width: percent(bin.observed)}}/></div><small>n={bin.count}</small></div>)}
        </div><div className="calibration-note"><TriangleAlert size={17}/>{calibration.disclaimer}</div>
        <div className="metric-line"><span>Synthetic outcomes generated</span><strong>{fmt(calibration.synthetic_outcomes)}</strong></div>
      </div></div><div className="eval-footer">Evaluation #{latestRun.id} · {time(latestRun.created_at)} · Deterministic RNG seed in source · No real field accuracy claims.</div>
    </> : <div className="locked-large"><BarChart3 size={30}/> No saved evaluation yet. Run the benchmark to calculate and persist your results.</div>}
  </section>
}

export default function App() {
  const [tab, setTab] = useState('routes')
  const [theme, setTheme] = useState(() => localStorage.getItem('accesspath-theme') || 'dark')
  const [network, setNetwork] = useState(null)
  const [reports, setReports] = useState([])
  const [evaluations, setEvaluations] = useState([])
  const [startId, setStartId] = useState('N1')
  const [endId, setEndId] = useState('N5')
  const [profile, setProfile] = useState('wheelchair')
  const [risk, setRisk] = useState(70)
  const [algorithm, setAlgorithm] = useState('astar')
  const [pickMode, setPickMode] = useState('end')
  const [activeRoute, setActiveRoute] = useState(0)
  const [routeLoading, setRouteLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [result, setResult] = useState(null)
  const [selectedEdge, setSelectedEdge] = useState('E01')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [adminKey, setAdminKey] = useState('')
  const [adminUnlocked, setAdminUnlocked] = useState(false)
  const [overview, setOverview] = useState(null)

  useEffect(() => { localStorage.setItem('accesspath-theme', theme); document.documentElement.dataset.theme = theme }, [theme])
  const refreshEvaluations = useCallback(async () => { const data = await getEvaluations(); setEvaluations(data.runs) }, [])
  const refreshAll = useCallback(async () => {
    setRefreshing(true)
    try {
      const [net, rep, evals] = await Promise.all([getNetwork(), getReports(), getEvaluations()])
      setNetwork(net); setReports(rep.reports); setEvaluations(evals.runs)
      setError('')
    } catch (err) { setError(`Backend unavailable: ${safeError(err)}. Start FastAPI on port 8000.`) }
    finally { setRefreshing(false) }
  }, [])
  useEffect(() => { refreshAll() }, [refreshAll])
  useEffect(() => {
    if (!network || !network.nodes?.some(n => n.id === startId) || !network.nodes?.some(n => n.id === endId)) return
    if (startId === endId) { setResult(null); setRouteLoading(false); return }
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      setRouteLoading(true)
      try {
        const computed = await calculateRoute({ start_id: startId, end_id: endId, profile,
          algorithm, risk_aversion: risk, alternatives: 3 }, controller.signal)
        if (!controller.signal.aborted) { setResult(computed); setActiveRoute(0); setError('') }
      } catch (err) { if (!controller.signal.aborted) { setResult(null); setError(safeError(err)) } }
      finally { if (!controller.signal.aborted) setRouteLoading(false) }
    }, 160)
    return () => { clearTimeout(timer); controller.abort() }
  }, [network, startId, endId, profile, risk, algorithm])

  const pickNode = useCallback((id) => {
    if (pickMode === 'start') { setStartId(id); setPickMode('end') }
    else { setEndId(id); setPickMode('start') }
  }, [pickMode])
  const pickEdge = useCallback((id) => { setSelectedEdge(id); setTab('reports') }, [])
  const startName = useMemo(() => network?.nodes.find(n => n.id === startId)?.label || '—', [network, startId])
  const endName = useMemo(() => network?.nodes.find(n => n.id === endId)?.label || '—', [network, endId])
  return <div className={`app-shell theme-${theme}`}>
    <nav className="side-nav" aria-label="Primary navigation"><div className="brand-lockup"><span className="brand-mark"><Route size={24}/></span><span><strong>ACCESS<span>PATH</span></strong><small>ROUTING INTELLIGENCE</small></span></div>
      <div className="nav-group-label">WORKSPACE</div><div className="nav-items">{TABS.map(({id,label,icon:Icon}) => <button key={id} className={`nav-item ${tab === id ? 'nav-active' : ''}`} onClick={() => setTab(id)} aria-current={tab === id ? 'page' : undefined}>
        <Icon size={19}/><span>{label}</span>{tab === id && <span className="active-pin"/>}</button>)}</div>
      <div className="nav-bottom"><div className="dataset-card"><div className="dataset-symbol"><Layers3 size={17}/></div><strong>Demo dataset</strong><p>20 fictional junctions · 37 paths</p><span><span className="dataset-live"/> SYNTHETIC · LOCAL</span></div>
        <button className="theme-switch" onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}><span>{theme === 'dark' ? <Moon size={18}/> : <Sun size={18}/>} {theme === 'dark' ? 'Dark mode' : 'Light mode'}</span><span className="theme-toggle"><i/></span></button>
        <div className="version-label">v1.0.0 · OPEN SOURCE DEMO</div></div></nav>
    <div className="main-column"><header className="topbar"><div className="breadcrumb">WORKSPACE <ChevronRight size={14}/> <strong>{TABS.find(t => t.id === tab)?.label.toUpperCase()}</strong></div>
      <div className="topbar-actions"><span className="header-chip"><span className="little-pulse"/> LOCAL ENGINE</span>
        <a className="geojson-link" href="/api/network.geojson" target="_blank" rel="noreferrer" title="Export live graph as GeoJSON"><ExternalLink size={15}/> GeoJSON</a>
        <button className="header-theme" aria-label="Toggle color theme" title="Toggle color theme" onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={18}/> : <Moon size={18}/>}</button></div></header>
      {error && <div className="toast toast-error" role="alert"><TriangleAlert size={18}/><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={16}/></button></div>}
      {notice && <div className="toast toast-success" role="status"><CheckCircle2 size={18}/><span>{notice}</span><button aria-label="Dismiss message" onClick={() => setNotice('')}><X size={16}/></button></div>}
      {tab === 'routes' || tab === 'reports' ? <main className="split-workspace">
        {tab === 'routes' ? <ControlPanel network={network} startId={startId} endId={endId} setStartId={setStartId} setEndId={setEndId}
          pickMode={pickMode} setPickMode={setPickMode} profile={profile} setProfile={setProfile}
          risk={risk} setRisk={setRisk} algorithm={algorithm} setAlgorithm={setAlgorithm}
          routeLoading={routeLoading} result={result} refreshAll={refreshAll} refreshing={refreshing}
          swapPoints={() => {setStartId(endId);setEndId(startId)}}/> : <ReportsPanel network={network} reports={reports}
          selectedEdge={selectedEdge} setSelectedEdge={setSelectedEdge} refreshAll={refreshAll} setError={setError} setNotice={setNotice}/>}
        <div className="content-panel"><div className="map-card"><div className="map-toolbar"><div><strong>DEMO CITY NETWORK</strong><span>Every line is illustrative, not a mapped real street</span></div><div className="map-toolbar-right"><span><span className="live-pulse"/> DYNAMIC GRAPH</span><span>20 NODES / 37 EDGES</span></div></div>
          <MapView network={network} routes={result} activeRoute={activeRoute} startId={startId} endId={endId} pickMode={pickMode} onPickNode={pickNode} onPickEdge={pickEdge} theme={theme}/></div>
          <div className="under-map">{tab === 'routes' ? <RouteCards result={result} activeRoute={activeRoute} setActiveRoute={setActiveRoute} loading={routeLoading} startName={startName} endName={endName}/> : <div className="reports-under-map"><div className="eyebrow">LIVE MODERATION PIPELINE</div><h2>Report → Review → Verify → Reroute</h2><p>Pending reports reduce evidence confidence; verified obstacles enforce mobility-specific restrictions. Resolved or expired reports stop affecting routing. Click a segment to preselect it in the report form.</p>
            <div className="flow-steps"><span><Flag size={17}/> 1. Submit</span><ArrowRight size={17}/><span><ClipboardCheck size={17}/> 2. Moderate</span><ArrowRight size={17}/><span><GitBranch size={17}/> 3. Recalculate</span></div></div>}</div>
        </div></main> : tab === 'admin' ? <AdminScreen adminKey={adminKey} setAdminKey={setAdminKey} adminUnlocked={adminUnlocked} setAdminUnlocked={setAdminUnlocked} reports={reports} overview={overview} setOverview={setOverview} refreshAll={refreshAll} setError={setError} setNotice={setNotice}/> : <EvaluationScreen latestRun={evaluations[0]} adminKey={adminKey} refreshEvaluations={refreshEvaluations} setError={setError} setNotice={setNotice}/>}
      <footer className="app-footer"><span><TriangleAlert size={13}/> RESEARCH PROTOTYPE — NOT SAFETY-CERTIFIED NAVIGATION</span><span>Synthetic GeoJSON · No OSM tiles or real-world accessibility claims</span></footer>
    </div>
  </div>
}
