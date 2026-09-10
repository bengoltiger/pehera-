# PEHRA — Dataset Links (Organized by System/Source)

Each block below is one system/organization with every relevant link grouped together — so you can copy-paste one whole block when you need that source, instead of hunting across categories.

---

## 1. IMD — India Meteorological Department
*Rainfall, weather observations, forecasts, warnings, radar*

- Main portal (Mausam): https://mausam.imd.gov.in/
- API platform (JSON access to rainfall/nowcast/warnings): https://api.imd.gov.in/
- MausamGram (village-level hyperlocal forecast): https://mausamgram.imd.gov.in/
- IMD Geospatial portal: https://imdgeospatial.imd.gov.in/
- Historical sub-divisional rainfall 1901–2017 (CSV): https://data.gov.in/resource/sub-divisional-monthly-rainfall-1901-2017

**Access:** Mostly free; API needs registration for a key.

---

## 2. MOSDAC — Meteorological & Oceanographic Satellite Data Archival Centre (ISRO)
*Satellite cloud, moisture, rainfall, river discharge, soil moisture*

- Main portal: https://mosdac.gov.in/
- Open Data (no order needed — cloud, rainfall, water vapour, river discharge, soil moisture): https://mosdac.gov.in/node/940/8
- Data Download API documentation: https://mosdac.gov.in/node/2070
- FAQ / how to order data: https://mosdac.gov.in/faq-page

**Access:** Free registration; "Open Data" section needs no order, rest needs a data request.

---

## 3. VEDAS — ISRO Earth Observation Visualization Platform

- Portal: https://vedas.sac.gov.in

**Access:** Free registration.

---

## 4. Bhoonidhi — ISRO EO Satellite Data Procurement

- Portal: https://bhoonidhi.nrsc.gov.in

**Access:** Free/paid depending on the product ordered.

---

## 5. Bhuvan — ISRO/NRSC National Geoportal
*DEM, land use/land cover, hydrology, disaster layers*

- Main portal: https://bhuvan.nrsc.gov.in
- Thematic services (LULC 50K/250K, request form): https://bhuvan-app1.nrsc.gov.in/thematic
- Free data download: https://bhuvan-app3.nrsc.gov.in/data/download/index.php

**Access:** Free registration; some layers need an MoU/request form stating research purpose.

---

## 6. NRSC — National Remote Sensing Centre

- River Basin Atlas (basin boundaries, drainage reports): https://www.nrsc.gov.in/KR_Atlas_RiverBasin

**Access:** Free.

---

## 7. India-WRIS — Water Resources Information System (CWC + ISRO)
*River water level, discharge, reservoir storage, rainfall dashboards*

- Portal: https://indiawris.gov.in

**Access:** Free, public web portal, no login needed to view dashboards.

---

## 8. CWC — Central Water Commission

- Main site: https://cwc.gov.in
- Hydro-Meteorological Data Dissemination Policy (what's open vs restricted): https://cwc.gov.in/sites/default/files/hddp2013.pdf

**Access:** Free.

---

## 9. CGWB — Central Ground Water Board

- Groundwater data access: https://cgwb.gov.in/old_website/GW-data-access.html

**Access:** Free, links through to India-WRIS.

---

## 10. NASA GPM / GES DISC
*Global half-hourly satellite rainfall (IMERG), since 2000, ~10 km resolution*

- GPM data directory: https://gpm.nasa.gov/data/directory
- GES DISC (search/download/subset by area and date): https://disc.gsfc.nasa.gov/
- Earthdata login (required to download): https://urs.earthdata.nasa.gov/
- Giovanni (visual analysis, no coding, subset by watershed): https://giovanni.gsfc.nasa.gov/giovanni/
- IMERG on Google Earth Engine (for coding pipelines): https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07

**Access:** Free, needs a NASA Earthdata account.

---

## 11. Copernicus Data Space Ecosystem (ESA)
*Sentinel-1 SAR, Sentinel-2 optical — flood extent ground truth*

- Main portal: https://dataspace.copernicus.eu/
- Copernicus Browser (visual search/download): https://browser.dataspace.copernicus.eu/
- Copernicus Climate Data Store (ERA5 reanalysis, historical training features): https://cds.climate.copernicus.eu/
- GloFAS — Global Flood Awareness System (forecasted river discharge, validation reference): https://global-flood.emergency.copernicus.eu/
- Copernicus EMS Rapid Mapping (on-demand flood extent during declared disasters): https://emergency.copernicus.eu/mapping/list-of-activations-rapid
- Copernicus GLO-30 DEM (30m global elevation): https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model
- Copernicus Global Land Cover Service: https://land.copernicus.eu/global/

**Access:** Free registration.

---

## 12. Alaska Satellite Facility (ASF)
*Easiest way to search/download Sentinel-1 SAR for flood mapping*

- Portal: https://search.asf.alaska.edu/

**Access:** Free, needs NASA Earthdata login (same one as GES DISC).

---

## 13. UN-SPIDER
*Ready-made open-source flood mapping pipeline*

- Radar-based Flood Mapping notebook (full Sentinel-1 → flood mask pipeline): https://github.com/UN-SPIDER/radar-based-flood-mapping

**Access:** Free, open source.

---

## 14. USGS
*Global elevation and satellite imagery*

- EarthExplorer (SRTM 30m DEM, Landsat): https://earthexplorer.usgs.gov/
- SRTM mission info page: https://www2.jpl.nasa.gov/srtm/

**Access:** Free registration.

---

## 15. OpenTopography
*Easy clip-and-download DEM, alternative to EarthExplorer*

- Portal: https://opentopography.org/

**Access:** Free registration.

---

## 16. ISRIC — SoilGrids
*Global soil type, texture, hydraulic conductivity, 250m resolution*

- Portal: https://soilgrids.org/

**Access:** Free, REST/WCS API, no login.

---

## 17. NBSS&LUP — National Bureau of Soil Survey & Land Use Planning (India)

- Portal: https://www.nbsslup.in/

**Access:** Reports free; raw data usually via request.

---

## 18. ESA WorldCover
*10m global land cover, for impervious surface / runoff features*

- Portal: https://esa-worldcover.org/en

**Access:** Free direct download.

---

## 19. OpenStreetMap
*Roads, bridges, buildings, hospitals, police stations, schools*

- Main site: https://www.openstreetmap.org/
- Geofabrik (pre-extracted India regional download): https://download.geofabrik.de/asia/india.html
- Overpass API (query specific features, e.g. "hospitals in district X"): https://overpass-api.de/
- HOT OSM Export Tool (custom area export): https://export.hotosm.org/

**Access:** Free, fully open.

---

## 20. ECMWF
*Short-range forecast data (for the 1–6 hour forecast layer)*

- Open Data portal: https://www.ecmwf.int/en/forecasts/datasets/open-data

**Access:** Free.

---

## 21. NOAA
*Global forecast model (GFS) — fallback if IMD forecast granularity is insufficient*

- GFS product page: https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast

**Access:** Free.

---

## 22. NDMA — National Disaster Management Authority (India)
*Historical flood/disaster event records*

- Portal: https://ndma.gov.in/

**Access:** Free, reports.

---

## 23. NDEM — National Database for Emergency Management (ISRO)

- Portal: https://ndem.nrsc.gov.in/login.php

**Access:** Registration restricted to authorized agencies — not open to individual students without institutional backing.

---

## 24. EM-DAT — International Disaster Database
*Cross-check historical flood event dates/impact globally*

- Portal: https://www.emdat.be/

**Access:** Free registration.

---

## 25. Dartmouth Flood Observatory
*Global flood event archive with approximate extents*

- Portal: https://floodobservatory.colorado.edu/

**Access:** Free.

---

## Quick-start priority (for your hackathon MVP)

**No-login-hassle, start today:**
1. IMD → https://api.imd.gov.in/
2. MOSDAC Open Data → https://mosdac.gov.in/node/940/8
3. India-WRIS → https://indiawris.gov.in
4. OpenStreetMap / Geofabrik → https://download.geofabrik.de/asia/india.html
5. ISRIC SoilGrids → https://soilgrids.org/
6. OpenTopography (DEM) → https://opentopography.org/

**Free but needs one-time account setup (do this early):**
7. NASA Earthdata (unlocks GES DISC + ASF) → https://urs.earthdata.nasa.gov/
8. Copernicus Data Space (Sentinel-1/2) → https://dataspace.copernicus.eu/

**Registration-gated / MoU-based — mention as "production roadmap," not "already integrated":**
9. Bhuvan thematic layers → https://bhuvan-app1.nrsc.gov.in/thematic
10. NDEM → https://ndem.nrsc.gov.in/login.php
