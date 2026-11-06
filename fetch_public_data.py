"""Fetch public fixtures and record provenance, not model answers."""
import csv,hashlib,json
from pathlib import Path
import httpx
ROOT=Path(__file__).parent
URL='https://raw.githubusercontent.com/vega/vega-datasets/main/data/seattle-weather.csv'
def fetch():
    folder=ROOT/'fixtures';folder.mkdir(exist_ok=True)
    raw=httpx.get(URL,timeout=30).raise_for_status().content
    (folder/'weather.csv').write_bytes(raw)
    metadata={'source':URL,'publisher':'Vega datasets / NOAA','downloaded':'2026-11-06','sha256':hashlib.sha256(raw).hexdigest(),'transformation':'None','catalog':'https://vega.github.io/vega-datasets/','license_metadata':'U.S. Government Dataset (other-pd), per Vega datapackage metadata','original_source':'https://www.ncdc.noaa.gov/cdo-web/datatools/records'}
    (folder/'weather.provenance.json').write_text(json.dumps(metadata,indent=2))
    print(json.dumps(metadata))
if __name__=='__main__':fetch()
