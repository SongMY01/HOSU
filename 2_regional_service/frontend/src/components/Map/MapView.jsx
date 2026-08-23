import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, ZoomControl, useMap } from 'react-leaflet';
import RegionMarkers from './RegionMarkers';
import ShelterMarkers from './ShelterMarkers';
import MapLegend from './MapLegend';
import styles from './MapView.module.css';

/** Helper: focus map on a given lat/lon with animation */
function FlyTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (target) {
      map.flyTo([target.lat, target.lon], target.zoom ?? 11, { animate: true, duration: 0.8 });
    }
  }, [target, map]);
  return null;
}

export default function MapView({ regions, shelters, showShelters, onSelectRegion, flyTarget, summary }) {
  return (
    <div className={styles.wrap}>
      <MapContainer
        center={[36.25, 128.8]}
        zoom={9}
        zoomControl={false}
        attributionControl={false}
        style={{ width: '100%', height: '100%' }}
      >
        <ZoomControl position="topright" />
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          attribution="&copy; OpenStreetMap &copy; CARTO"
          subdomains="abcd"
          maxZoom={18}
        />
        <RegionMarkers regions={regions} onSelect={onSelectRegion} summary={summary} />
        {showShelters && <ShelterMarkers shelters={shelters} />}
        {flyTarget && <FlyTo target={flyTarget} />}
      </MapContainer>
      <MapLegend summary={summary} />
    </div>
  );
}
