"""Bundle a built VSIX with user documentation and examples for offline sharing."""
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parents[1]
    version = json.loads((root / 'package.json').read_text())['version']
    name = f'datapeek-{version}'
    vsix = root / f'{name}.vsix'
    if not vsix.is_file():
        raise SystemExit('Run npm run package before creating the sharing bundle.')
    output = root / 'build' / f'{name}-share.zip'
    output.parent.mkdir(exist_ok=True)
    files = [vsix, root / 'README.md', root / 'README.zh-CN.md',
             root / 'LICENSE', root / 'media/icon.png', root / 'python/requirements.txt']
    files += sorted((root / 'docs').rglob('*.md'))
    files += sorted((root / 'docs').rglob('*.png'))
    files += sorted((root / 'docs').rglob('*.json'))
    files += sorted((root / 'examples').rglob('*.py'))
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, Path(name) / file.relative_to(root))
    print(output)


if __name__ == '__main__':
    main()
