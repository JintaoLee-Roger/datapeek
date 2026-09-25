"""Create a small synthetic volume for a first DataPeek preview.

Run: python examples/create_sample.py sample.npy
Axes are (iline, xline, time). Existing files are never overwritten.
"""
import argparse
from pathlib import Path
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', type=Path, default=Path('sample.npy'))
    args = parser.parse_args()
    if args.output.suffix.lower() != '.npy':
        parser.error('Output must have a .npy suffix.')
    i, x, t = np.ogrid[:48, :64, :128]
    center = 48 + 9 * np.sin(x / 12) + i / 4
    phase = (t - center) / 3
    data = ((1 - 2 * phase**2) * np.exp(-phase**2)).astype('float32')
    try:
        with args.output.open('xb') as stream:
            np.save(stream, data, allow_pickle=False)
    except FileExistsError:
        parser.error(f'File already exists: {args.output}')
    print(f'Created {args.output}: shape={data.shape}, dtype={data.dtype}')


if __name__ == '__main__':
    main()
