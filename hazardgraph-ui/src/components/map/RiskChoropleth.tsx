import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet'
import L from 'leaflet'
import type { RegionRiskScore } from '@/types'
import { RegionPopup } from './RegionPopup'

interface RiskChoroplethProps {
  regions: RegionRiskScore[]
  onRegionClick: (region: RegionRiskScore) => void
}

function getScoreColor(score: number): string {
  if (score < 30) return '#10B981'
  if (score < 60) return '#F59E0B'
  if (score < 75) return '#EF4444'
  return '#7C3AED'
}

function getScoreOpacity(score: number): number {
  if (score < 30) return 0.6
  if (score < 60) return 0.65
  if (score < 75) return 0.7
  return 0.75
}

function MapBoundsSetter() {
  const map = useMap()
  useEffect(() => {
    map.fitBounds([
      [-12, 21],
      [18, 52],
    ])
  }, [map])
  return null
}

export function RiskChoropleth({ regions, onRegionClick }: RiskChoroplethProps) {
  const [geoJsonData, setGeoJsonData] = useState<Record<string, unknown> | null>(null)
  const [selectedRegion, setSelectedRegion] = useState<RegionRiskScore | null>(null)

  useEffect(() => {
    fetch('/igad_regions.geojson')
      .then((res) => res.json())
      .then((data) => setGeoJsonData(data))
      .catch((err) => console.error('Failed to load GeoJSON:', err))
  }, [])

  const regionMap = new Map<string, RegionRiskScore>()
  regions.forEach((r) => {
    regionMap.set(r.name.toLowerCase(), r)
  })

  const onEachFeature = (feature: Record<string, unknown>, layer: L.Layer) => {
    const props = feature.properties as Record<string, unknown>
    const name = (props.name as string) || ''
    const region = regionMap.get(name.toLowerCase())

    if (region) {
      const color = getScoreColor(region.score)
      const opacity = getScoreOpacity(region.score)

      const geoLayer = layer as L.Path
      geoLayer.setStyle({
        fillColor: color,
        fillOpacity: opacity,
        weight: 1,
        color: '#374151',
        opacity: 0.8,
      })

      geoLayer.on({
        mouseover: (e: L.LeafletMouseEvent) => {
          const target = e.target as L.Path
          target.setStyle({ weight: 2, color: '#F9FAFB' })
          target.bringToFront()
        },
        mouseout: (e: L.LeafletMouseEvent) => {
          const target = e.target as L.Path
          target.setStyle({ weight: 1, color: '#374151' })
        },
        click: () => {
          setSelectedRegion(region)
          onRegionClick(region)
        },
      })
    }

    if (region && region.score >= 75) {
      layer.bindTooltip(
        `<div style="font-family: Raleway, sans-serif; font-weight: 700; color: #EF4444; animation: pulse 1s infinite;">
          ${name}<br/>Score: ${region.score.toFixed(0)} ⚠
        </div>`,
        { direction: 'center', className: 'risk-critical-tooltip' },
      )
    } else if (region) {
      layer.bindTooltip(
        `<div style="font-family: Raleway, sans-serif; color: #F9FAFB;">
          ${name}<br/>Score: ${region.score.toFixed(0)}
        </div>`,
        { direction: 'center', className: 'risk-tooltip' },
      )
    }
  }

  const popupContent = selectedRegion ? (
    <RegionPopup
      region={selectedRegion}
      onViewDetails={() => onRegionClick(selectedRegion)}
    />
  ) : null

  return (
    <div className="h-full w-full overflow-hidden rounded-lg border border-border">
      <MapContainer
        center={[6, 35]}
        zoom={4}
        minZoom={3}
        maxZoom={8}
        style={{ height: '100%', width: '100%', backgroundColor: '#0A0F1E' }}
        zoomSnap={0.5}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
        />
        <MapBoundsSetter />
        {geoJsonData && (
          <GeoJSON
            key={regions.length}
            data={geoJsonData as unknown as GeoJSON.GeoJSON}
            onEachFeature={onEachFeature as never}
          />
        )}
      </MapContainer>
    </div>
  )
}