"""Deduplicate, prune, validate, and audit Blender GLBs without mesh compression."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import csv
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'apps/frontend/public/models'
CLI = ['npx', '--yes', '@gltf-transform/cli@4.5.1']


def process(path):
    before = path.stat().st_size
    with tempfile.TemporaryDirectory(prefix='warehouse-glb-') as folder:
        deduped = Path(folder) / path.name
        pruned = Path(folder) / ('ready-' + path.name)
        for args in [('dedup', path, deduped), ('prune', deduped, pruned)]:
            subprocess.run([*CLI, *map(str, args)], check=True, capture_output=True, text=True)
        validation = subprocess.run([*CLI, 'validate', str(pruned), '--format', 'csv'], check=True, capture_output=True, text=True)
        issues = list(csv.DictReader(validation.stdout.strip().splitlines()))
        if any(int(issue.get('severity', 0)) <= 1 for issue in issues):
            raise RuntimeError(validation.stdout + validation.stderr)
        data = pruned.read_bytes()
        document = json.loads(data[20:20 + struct.unpack_from('<I', data, 12)[0]])
        assert len(document['scenes']) == 1 and len(document['scenes'][0]['nodes']) == 1, 'Exactly one export root required'
        assert not document.get('cameras') and not document.get('images'), 'Self-contained geometry-only palette expected'
        assert not document.get('extensionsRequired'), 'No external decoders required'
        root = document['nodes'][document['scenes'][0]['nodes'][0]]
        assert root.get('translation', [0, 0, 0]) == [0, 0, 0]
        assert root.get('rotation', [0, 0, 0, 1]) == [0, 0, 0, 1]
        assert root.get('scale', [1, 1, 1]) == [1, 1, 1]
        path.write_bytes(data)
    triangles = sum(document['accessors'][p['indices']]['count'] // 3 for m in document['meshes'] for p in m['primitives'])
    return {'file': str(path.relative_to(ROOT)), 'bytes': len(data), 'bytes_before_optimization': before,
            'triangles': triangles, 'materials': len(document.get('materials', [])),
            'primitives': sum(len(m['primitives']) for m in document['meshes']),
            'validation': {'errors': 0, 'warnings': 0}, 'root': root['name']}


if __name__ == '__main__':
    files = sorted(MODELS.rglob('*.glb'))
    assert len(files) == 8, f'Expected the complete eight-model set, found {len(files)}'
    with ThreadPoolExecutor(max_workers=4) as pool:
        report = list(pool.map(process, files))
    result = {'tool': '@gltf-transform/cli@4.5.1', 'assets': report, 'total_bytes': sum(item['bytes'] for item in report)}
    (ROOT / 'assets/blender/asset-report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
