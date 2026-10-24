"""Build an inert isolated-test bundle; no deployment or execution."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile

def main():
    repo=Path(__file__).resolve().parents[3]
    output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=False)
    artifacts=repo/'artifacts/localization_cpu_20261024'
    pairs=[(repo/'project_atlas/tools/diagnostics/localization_isolated_jetson.py','localization_isolated_jetson.py'),
           (repo/'artifacts/stage19_hall_native_A/result/result_0.db3','input.db3'),
           (repo/'artifacts/executor_benchmark_20261023/executors.py','executors.py'),
           (artifacts/'monitor.py','monitor.py'),(artifacts/'manual.py','manual.py')]
    for name in ('benchmark_localization_traffic.py','benchmark_localization_executor.py','benchmark_executor_counts.py'):
        rel='project_atlas/tools/diagnostics/'+name;pairs.append((repo/rel,rel))
    for name in ('atlas_localization_monitor.py','atlas_localization_verify_core.py','atlas_background_search_budget.py','atlas_location_check_job.py'):
        rel='project_atlas/scripts/'+name;pairs.append((repo/rel,rel))
    hashes={}
    for source,name in pairs:
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,path)
        hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    production={
        'scripts/atlas_localization_monitor.py':'cddbbc8d44a07b57c62a6ec4160cbbe9c0b02e4fe82d91ab126bafd66f68839b',
        'scripts/atlas_localization_verify_core.py':'d95828a09b174d109033c4af10fdf2f65599e1c7365ca669dff3428e6e723462',
        'scripts/atlas_location_check_ros.py':'eec177795434870f53102482a92b3dbc1ced4d3e4a90589e22e9fe4261681690',
        'scripts/atlas_status_web.py':'acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439',
        'scripts/atlas_voice_companion.py':'a88ff78df1ae2dded4f9984cdcf5e94d5335d1d12c77fd9c9131219725298870',
        'scripts/atlas_safety_status.py':'94f52bcc1d535378adf6d4f54f6d29fc52f0cd7b12b11a8da0df39117f510bd4',
        'web/v2/material.css':'ea6a213b8a7b5aa5f4777af64259a75589799ebd151e39acf4723fc6fb6368d5'}
    manifest=output/'manifest.json';manifest.write_text(json.dumps(dict(package=hashes,production=production),indent=2)+'\n')
    archive=output.with_suffix('.tar.gz')
    with tarfile.open(archive,'w:gz') as tar:
        for name in [*hashes,'manifest.json']:tar.add(output/name,arcname=name)
    print(json.dumps(dict(archive=str(archive),archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                         manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())))

if __name__=='__main__':main()
