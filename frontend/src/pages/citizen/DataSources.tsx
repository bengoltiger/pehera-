/**
 * Data sources — every real-world dataset considered for PEHRA, grouped by
 * system, with access notes and their production roadmap.
 *
 * Honesty note (stated on-screen): NONE of these feeds is connected to the
 * running prototype. The backend's provider registry serves deterministic
 * simulated providers; this page documents what a production build would
 * plug into the existing provider adapter interface.
 */
import { Database, ExternalLink, Landmark, Radar, Satellite, ShieldAlert, TreePine, Truck, Waves } from 'lucide-react'
import type { ReactNode } from 'react'
import { Chip, Panel, StatusPip } from '../../components/ui'

interface SourceLink {
  label: string
  url: string
}
interface Source {
  name: string
  blurb: string
  access: string
  links: SourceLink[]
  roadmap: 'today' | 'account' | 'gated'
}
interface Group {
  title: string
  icon: ReactNode
  sources: Source[]
}

const GROUPS: Group[] = [
  {
    title: 'India — weather & hydrology (government)',
    icon: <Landmark size={14} aria-hidden />,
    sources: [
      {
        name: 'IMD — India Meteorological Department',
        blurb: 'Rainfall, weather observations, forecasts, warnings, radar. MausamGram gives village-level hyperlocal forecasts.',
        access: 'Mostly free; API needs registration for a key.',
        links: [
          { label: 'Mausam portal', url: 'https://mausam.imd.gov.in/' },
          { label: 'API platform (JSON)', url: 'https://api.imd.gov.in/' },
          { label: 'MausamGram (village level)', url: 'https://mausamgram.imd.gov.in/' },
          { label: 'IMD Geospatial portal', url: 'https://imdgeospatial.imd.gov.in/' },
          { label: 'Historical rainfall 1901–2017 (CSV)', url: 'https://data.gov.in/resource/sub-divisional-monthly-rainfall-1901-2017' },
        ],
        roadmap: 'today',
      },
      {
        name: 'MOSDAC — ISRO satellite data',
        blurb: 'Satellite cloud, moisture, rainfall, river discharge, soil moisture. The "Open Data" section needs no order.',
        access: 'Free registration; Open Data needs no order, the rest needs a data request.',
        links: [
          { label: 'Main portal', url: 'https://mosdac.gov.in/' },
          { label: 'Open Data (no order)', url: 'https://mosdac.gov.in/node/940/8' },
          { label: 'Download API docs', url: 'https://mosdac.gov.in/node/2070' },
        ],
        roadmap: 'today',
      },
      {
        name: 'India-WRIS (CWC + ISRO)',
        blurb: 'River water level, discharge, reservoir storage, rainfall dashboards — public, no login to view.',
        access: 'Free public web portal.',
        links: [{ label: 'Portal', url: 'https://indiawris.gov.in' }],
        roadmap: 'today',
      },
      {
        name: 'CWC — Central Water Commission',
        blurb: 'Gauge data and the Hydro-Meteorological Data Dissemination Policy (what is open vs restricted).',
        access: 'Free.',
        links: [
          { label: 'Main site', url: 'https://cwc.gov.in' },
          { label: 'Data policy', url: 'https://cwc.gov.in/sites/default/files/hddp2013.pdf' },
        ],
        roadmap: 'today',
      },
      {
        name: 'CGWB — Central Ground Water Board',
        blurb: 'Groundwater data access, linking through to India-WRIS.',
        access: 'Free.',
        links: [{ label: 'Data access', url: 'https://cgwb.gov.in/old_website/GW-data-access.html' }],
        roadmap: 'today',
      },
      {
        name: 'VEDAS / Bhoonidhi / Bhuvan / NRSC (ISRO ecosystem)',
        blurb: 'Earth-observation visualisation, satellite data procurement, national geoportal (DEM, LULC, hydrology, disaster layers), and the River Basin Atlas.',
        access: 'Free registration; some Bhuvan layers need an MoU/request form. NDEM is restricted to authorised agencies.',
        links: [
          { label: 'VEDAS portal', url: 'https://vedas.sac.gov.in' },
          { label: 'Bhoonidhi', url: 'https://bhoonidhi.nrsc.gov.in' },
          { label: 'Bhuvan geoportal', url: 'https://bhuvan.nrsc.gov.in' },
          { label: 'Bhuvan thematic services', url: 'https://bhuvan-app1.nrsc.gov.in/thematic' },
          { label: 'NRSC River Basin Atlas', url: 'https://www.nrsc.gov.in/KR_Atlas_RiverBasin' },
          { label: 'NDEM (restricted)', url: 'https://ndem.nrsc.gov.in/login.php' },
        ],
        roadmap: 'gated',
      },
      {
        name: 'NDMA & EM-DAT & Dartmouth Flood Observatory',
        blurb: 'Historical flood/disaster event records for validation and scenario realism: national (NDMA), international (EM-DAT), global river events (Dartmouth).',
        access: 'Free; EM-DAT needs registration.',
        links: [
          { label: 'NDMA', url: 'https://ndma.gov.in/' },
          { label: 'EM-DAT', url: 'https://www.emdat.be/' },
          { label: 'Dartmouth Flood Observatory', url: 'https://floodobservatory.colorado.edu/' },
        ],
        roadmap: 'today',
      },
    ],
  },
  {
    title: 'Satellite & space (global)',
    icon: <Satellite size={14} aria-hidden />,
    sources: [
      {
        name: 'NASA GPM / GES DISC (IMERG)',
        blurb: 'Global half-hourly satellite rainfall since 2000 at ~10 km. Giovanni allows no-code watershed subsetting.',
        access: 'Free with a NASA Earthdata account.',
        links: [
          { label: 'GPM data directory', url: 'https://gpm.nasa.gov/data/directory' },
          { label: 'GES DISC', url: 'https://disc.gsfc.nasa.gov/' },
          { label: 'Earthdata login', url: 'https://urs.earthdata.nasa.gov/' },
          { label: 'Giovanni', url: 'https://giovanni.gsfc.nasa.gov/giovanni/' },
          { label: 'IMERG on Earth Engine', url: 'https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07' },
        ],
        roadmap: 'account',
      },
      {
        name: 'Copernicus Data Space (ESA)',
        blurb: 'Sentinel-1 SAR + Sentinel-2 optical for flood extent, ERA5 reanalysis for training features, GloFAS river-discharge forecasts, GLO-30 DEM, global land cover.',
        access: 'Free registration; EMS Rapid Mapping runs on declared disasters.',
        links: [
          { label: 'Data Space', url: 'https://dataspace.copernicus.eu/' },
          { label: 'Copernicus Browser', url: 'https://browser.dataspace.copernicus.eu/' },
          { label: 'Climate Data Store (ERA5)', url: 'https://cds.climate.copernicus.eu/' },
          { label: 'GloFAS', url: 'https://global-flood.emergency.copernicus.eu/' },
          { label: 'EMS Rapid Mapping', url: 'https://emergency.copernicus.eu/mapping/list-of-activations-rapid' },
          { label: 'GLO-30 DEM', url: 'https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model' },
        ],
        roadmap: 'account',
      },
      {
        name: 'Alaska Satellite Facility (ASF)',
        blurb: 'Easiest search/download path for Sentinel-1 SAR flood mapping.',
        access: 'Free with NASA Earthdata login (same as GES DISC).',
        links: [{ label: 'ASF search', url: 'https://search.asf.alaska.edu/' }],
        roadmap: 'account',
      },
      {
        name: 'UN-SPIDER open-source flood mapping',
        blurb: 'Ready-made Sentinel-1 → flood-mask notebook pipeline to learn from and adapt.',
        access: 'Free, open source.',
        links: [{ label: 'Radar-based flood mapping', url: 'https://github.com/UN-SPIDER/radar-based-flood-mapping' }],
        roadmap: 'today',
      },
      {
        name: 'USGS EarthExplorer / SRTM',
        blurb: 'Global 30 m elevation (SRTM) and Landsat imagery.',
        access: 'Free registration.',
        links: [
          { label: 'EarthExplorer', url: 'https://earthexplorer.usgs.gov/' },
          { label: 'SRTM mission', url: 'https://www2.jpl.nasa.gov/srtm/' },
        ],
        roadmap: 'account',
      },
    ],
  },
  {
    title: 'Forecast models',
    icon: <Radar size={14} aria-hidden />,
    sources: [
      {
        name: 'ECMWF Open Data',
        blurb: 'Short-range forecast data for the 1–6 hour forecast layer PEHRA nowcasts on.',
        access: 'Free.',
        links: [{ label: 'Open Data portal', url: 'https://www.ecmwf.int/en/forecasts/datasets/open-data' }],
        roadmap: 'today',
      },
      {
        name: 'NOAA GFS',
        blurb: 'Global forecast model — fallback if IMD forecast granularity is insufficient.',
        access: 'Free.',
        links: [{ label: 'GFS product page', url: 'https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast' }],
        roadmap: 'today',
      },
    ],
  },
  {
    title: 'Terrain, soil & land cover',
    icon: <TreePine size={14} aria-hidden />,
    sources: [
      {
        name: 'OpenTopography',
        blurb: 'Clip-and-download DEMs — the low-friction alternative to EarthExplorer.',
        access: 'Free registration.',
        links: [{ label: 'Portal', url: 'https://opentopography.org/' }],
        roadmap: 'today',
      },
      {
        name: 'ISRIC SoilGrids',
        blurb: 'Global soil type, texture and hydraulic conductivity at 250 m — feeds the runoff/soil-moisture features.',
        access: 'Free, REST/WCS API, no login.',
        links: [{ label: 'Portal', url: 'https://soilgrids.org/' }],
        roadmap: 'today',
      },
      {
        name: 'ESA WorldCover',
        blurb: '10 m global land cover for impervious-surface / runoff features.',
        access: 'Free direct download.',
        links: [{ label: 'Portal', url: 'https://esa-worldcover.org/en' }],
        roadmap: 'today',
      },
      {
        name: 'NBSS&LUP (India)',
        blurb: 'National soil survey reports; raw data usually by request.',
        access: 'Reports free.',
        links: [{ label: 'Portal', url: 'https://www.nbsslup.in/' }],
        roadmap: 'gated',
      },
    ],
  },
  {
    title: 'Infrastructure & exposure',
    icon: <Truck size={14} aria-hidden />,
    sources: [
      {
        name: 'OpenStreetMap + Geofabrik + Overpass',
        blurb: 'Roads, bridges, buildings, hospitals, schools, police stations. Geofabrik serves pre-extracted India regions; Overpass queries specific features.',
        access: 'Free, fully open.',
        links: [
          { label: 'OSM', url: 'https://www.openstreetmap.org/' },
          { label: 'Geofabrik India', url: 'https://download.geofabrik.de/asia/india.html' },
          { label: 'Overpass API', url: 'https://overpass-api.de/' },
          { label: 'HOT export tool', url: 'https://export.hotosm.org/' },
        ],
        roadmap: 'today',
      },
    ],
  },
]

const ROADMAP_CHIP: Record<Source['roadmap'], { tone: 'good' | 'info' | 'warn'; label: string }> = {
  today: { tone: 'good', label: 'START TODAY' },
  account: { tone: 'info', label: 'ONE-TIME ACCOUNT' },
  gated: { tone: 'warn', label: 'REGISTRATION / MOU' },
}

export function SourceCard({ s }: { s: Source }) {
  const chip = ROADMAP_CHIP[s.roadmap]
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-ink-700 bg-ink-900 p-3">
      <div className="flex flex-wrap items-center justify-between gap-1.5">
        <h3 className="font-head text-sm font-semibold text-ink-100">{s.name}</h3>
        <Chip tone={chip.tone}>{chip.label}</Chip>
      </div>
      <p className="text-xs leading-relaxed text-ink-400">{s.blurb}</p>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {s.links.map((l) => (
          <a
            key={l.url}
            href={l.url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 font-mono text-[10px] text-accent-bright hover:underline"
          >
            <ExternalLink size={9} aria-hidden />
            {l.label}
          </a>
        ))}
      </div>
      <p className="font-mono text-[9px] text-ink-500 uppercase">Access: {s.access}</p>
    </div>
  )
}

export default function DataSources() {
  return (
    <div className="flex flex-col gap-3 p-3 pb-6">
      <Panel
        title="Dataset Resources"
        icon={<Database size={14} className="text-accent-bright" />}
        subtitle="Production data roadmap for the PEHRA provider layer"
      >
        <div className="flex items-start gap-2 rounded-md border border-moderate/40 bg-moderate/10 p-2.5 text-xs leading-relaxed text-moderate">
          <ShieldAlert size={14} className="mt-0.5 shrink-0" aria-hidden />
          <span>
            <strong>Status:</strong> none of these feeds is connected to the running prototype. The backend provider
            registry currently serves <strong>deterministic simulated providers</strong> (see the status pills on every
            screen). Each entry below is what a production build plugs into the existing provider adapter interface —
            no engine changes required.
          </span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <StatusPip tone="warn" label="PROTOTYPE: SIMULATED PROVIDERS" />
          <StatusPip tone="good" label="ADAPTER INTERFACE: READY" />
        </div>
      </Panel>

      {GROUPS.map((g) => (
        <section key={g.title} className="flex flex-col gap-2">
          <h2 className="flex items-center gap-2 font-head text-xs font-bold tracking-wide text-accent-bright uppercase">
            {g.icon}
            {g.title}
          </h2>
          <div className="flex flex-col gap-2">
            {g.sources.map((s) => (
              <SourceCard key={s.name} s={s} />
            ))}
          </div>
        </section>
      ))}

      <Panel title="Quick-start priority" subtitle="What to wire first, in order of friction" dense>
        <ol className="list-decimal space-y-1.5 p-4 pl-8 text-xs leading-relaxed text-ink-300">
          <li>
            <strong className="text-ink-100">No-login, start today:</strong> IMD API · MOSDAC Open Data · India-WRIS ·
            OSM/Geofabrik · SoilGrids · OpenTopography DEM
          </li>
          <li>
            <strong className="text-ink-100">Free, one-time account (do early):</strong> NASA Earthdata (unlocks GES
            DISC + ASF) · Copernicus Data Space (Sentinel-1/2)
          </li>
          <li>
            <strong className="text-ink-100">Registration / MoU-gated:</strong> Bhuvan thematic layers · NDEM — cite
            as production roadmap, never as "already integrated".
          </li>
        </ol>
      </Panel>

      <p className="flex items-center gap-1.5 font-mono text-[9px] text-ink-500 uppercase">
        <Waves size={10} aria-hidden />
        Compiled from the team's dataset survey — PEHRA docs, September 2026
      </p>
    </div>
  )
}
