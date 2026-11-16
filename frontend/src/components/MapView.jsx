import { useEffect, useRef } from 'react'
import L from 'leaflet'

// A standalone Leaflet surface with a synthetic, OSM-compatible GeoJSON network.
// No OSM tiles are requested: the coordinates do not describe real streets.
export default function MapView({ network, routes, activeRoute, startId, endId,
  pickMode, onPickNode, onPickEdge, theme }) {
  const holder = useRef(null)
  const map = useRef(null)
  const layers = useRef(null)
  const callbacks = useRef({ onPickNode, onPickEdge })
  callbacks.current = { onPickNode, onPickEdge }

  useEffect(() => {
    if (!holder.current || map.current) return
    const leaflet = L.map(holder.current, {
      zoomControl: false, attributionControl: false, preferCanvas: true,
      scrollWheelZoom: true, minZoom: 13, maxZoom: 21
    })
    L.control.zoom({ position: 'bottomright' }).addTo(leaflet)
    leaflet.setView([0.0192, 0.0211], 17)
    map.current = leaflet
    layers.current = L.featureGroup().addTo(leaflet)
    const refresh = () => leaflet.invalidateSize()
    const observer = new ResizeObserver(refresh)
    observer.observe(holder.current)
    return () => {
      observer.disconnect()
      leaflet.remove()
      map.current = null
      layers.current = null
    }
  }, [])

  useEffect(() => {
    if (!map.current || !layers.current || !network?.nodes?.length) return
    const leaflet = map.current
    const group = layers.current
    group.clearLayers()
    const startNode = network.nodes.find(n => n.id === startId)
    const endNode = network.nodes.find(n => n.id === endId)
    const routesList = routes?.routes || []
    const chosenRoute = routesList[activeRoute] || null
    const selectedIds = new Set(chosenRoute?.edge_ids || [])
    const issueColors = {
      verified: '#8497aa', community: '#9da6b2', unverified: '#eab46d'
    }

    for (const edge of network.edges) {
      const verifiedBlock = edge.reports.some(r => r.status === 'verified' &&
        ['blocked', 'temporary_obstruction', 'stairs', 'missing_curb', 'steep_slope', 'broken_surface'].includes(r.obstacle_type))
      const isStair = edge.stairs > 0
      const color = verifiedBlock || isStair ? '#ec7d7b' : issueColors[edge.verification]
      const line = L.polyline(edge.coordinates.map(([lng, lat]) => [lat, lng]), {
        color, weight: verifiedBlock ? 4.5 : 3.3, opacity: 0.62,
        dashArray: (edge.verification === 'unverified' || verifiedBlock) ? '6 7' : null
      }).addTo(group)
      line.bindTooltip(`<strong>${edge.name}</strong><br/>${edge.distance_m} m · ${edge.verification}${verifiedBlock ? '<br/>Active verified report' : ''}`, { sticky: true })
      line.on('click', () => callbacks.current.onPickEdge(edge.id))
    }

    routesList.forEach((route, index) => {
      if (index === activeRoute) return
      const color = index % 2 ? '#b497e6' : '#70a3cd'
      L.polyline(route.coordinates.map(([lng, lat]) => [lat, lng]), {
        color, weight: 5, opacity: 0.40, lineCap: 'round', lineJoin: 'round'
      }).addTo(group).bindTooltip(`${route.label} · ${route.distance_m} m`)
    })

    if (chosenRoute) {
      L.polyline(chosenRoute.coordinates.map(([lng, lat]) => [lat, lng]), {
        color: theme === 'dark' ? '#051c23' : '#effdf8', weight: 12, opacity: 0.92,
        lineCap: 'round', lineJoin: 'round'
      }).addTo(group)
      L.polyline(chosenRoute.coordinates.map(([lng, lat]) => [lat, lng]), {
        color: '#32d4b1', weight: 7, opacity: 1, lineCap: 'round', lineJoin: 'round'
      }).addTo(group).bindTooltip(`${chosenRoute.label} · ${chosenRoute.distance_m} m`)
      for (const segment of chosenRoute.segments) {
        if (!segment.warnings.length) continue
        L.polyline(segment.coordinates.map(([lng, lat]) => [lat, lng]), {
          color: '#f4b45f', weight: 8, opacity: 1, dashArray: '4 9', lineCap: 'butt'
        }).addTo(group).bindTooltip(`Uncertain · ${segment.name}\n${segment.warnings.join(', ')}`)
      }
    }

    for (const node of network.nodes) {
      const isStart = node.id === startId
      const isEnd = node.id === endId
      const marker = L.circleMarker([node.lat, node.lon], {
        radius: isStart || isEnd ? 11 : 6,
        fillColor: isStart ? '#2cd9ae' : isEnd ? '#f9b86a' : '#d9e4f1',
        color: '#172435', weight: isStart || isEnd ? 3 : 2, fillOpacity: 1
      }).addTo(group)
      marker.bindTooltip(`${node.label} · ${node.id}${isStart ? ' · START' : isEnd ? ' · DESTINATION' : ''}`)
      marker.on('click', () => callbacks.current.onPickNode(node.id))
      if (isStart || isEnd) {
        L.marker([node.lat, node.lon], {
          icon: L.divIcon({ className: 'location-label', html: `<span>${isStart ? 'A' : 'B'}</span>`, iconSize: [22, 22], iconAnchor: [11, 36] }),
          interactive: false
        }).addTo(group)
      }
    }
    // Focus on the full fictional network once, but retain the user's own pan/zoom after reroutes.
    if (!leaflet._accesspathFitted) {
      leaflet.fitBounds(L.latLngBounds(network.nodes.map(n => [n.lat, n.lon])), { padding: [44, 44] })
      leaflet._accesspathFitted = true
    }
  }, [network, routes, activeRoute, startId, endId, theme])

  return (
    <div className={`map-stage ${theme}`}>
      <div className="map-background-grid" aria-hidden="true" />
      <div ref={holder} className="leaflet-map" role="region" aria-label="Interactive synthetic pathway network; use the accessible start and destination selectors as a keyboard alternative" />
      <div className="map-floater top-left"><span className="live-pulse" /> LIVE NETWORK <strong>REV {network?.network_revision || '—'}</strong></div>
      <div className="map-floater top-right">SELECTING <strong>{pickMode === 'start' ? 'START' : 'DESTINATION'}</strong></div>
      <div className="map-scale-key" aria-label="Map line legend">
        <span><i className="line-dot preferred"/> Preferred</span>
        <span><i className="line-dot unknown"/> Uncertain</span>
        <span><i className="line-dot blocked"/> Hazard</span>
      </div>
      <div className="synthetic-map-note">FICTIONAL TEST NETWORK · NOT A REAL-WORLD MAP</div>
    </div>
  )
}
