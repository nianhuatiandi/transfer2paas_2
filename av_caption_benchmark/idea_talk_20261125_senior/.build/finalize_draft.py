from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import re
import xml.etree.ElementTree as ET

build = Path(__file__).resolve().parent
candidate = build / 'candidate.pptx'
final = build.parent / 'output' / '细粒度运动音视频Bench_师兄讨论稿_v1.pptx'
assert not final.exists(), 'Use a new final filename rather than overwriting a delivery.'
ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
fixed = 0
slide_count = table_count = notes_count = 0
latin, east_asian = set(), set()
with ZipFile(candidate) as source, ZipFile(final, 'w') as target:
    for info in source.infolist():
        data = source.read(info.filename)
        if re.fullmatch(r'ppt/slides/slide\d+\.xml', info.filename):
            slide_count += 1
            # A native media action has no relationship target. Omit the optional
            # empty r:id attribute while preserving ppaction://media and its media.
            data, count = re.subn(rb'(<a:hlinkClick) r:id=""( action="ppaction://media")', rb'\1\2', data)
            fixed += count
            root = ET.fromstring(data)
            table_count += len(root.findall('.//a:tbl', ns))
            latin.update(e.get('typeface') for e in root.findall('.//a:latin', ns))
            east_asian.update(e.get('typeface') for e in root.findall('.//a:ea', ns))
        if re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml', info.filename):
            notes_count += 1
        target.writestr(info, data)
assert slide_count == notes_count == 14
assert table_count == 8
assert latin == {'Times New Roman'}
assert east_asian == {'宋体'}
with ZipFile(final) as package:
    assert package.testzip() is None
    movie = package.read('ppt/media/media1.mp4')
    assert b'vide' in movie and b'soun' in movie, 'Expected video and audio handlers.'
report = {
    'slide_count': slide_count,
    'speaker_note_count': notes_count,
    'native_table_count': table_count,
    'latin_fonts': sorted(latin),
    'east_asian_fonts': sorted(east_asian),
    'embedded_video_with_audio_handler': True,
    'empty_media_relationship_attributes_removed': fixed,
    'sha256': hashlib.sha256(final.read_bytes()).hexdigest(),
    'final_file': str(final),
    'artifact_tool_import_check': 'unavailable; native PowerPoint open and render used',
}
(build / 'final_checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k != 'final_file'}, ensure_ascii=True))
