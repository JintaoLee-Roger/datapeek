"""Run with your scientific Python environment to create demo data."""
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parent
x = np.linspace(0, 12 * np.pi, 4000)
np.save(root / 'signal.npy', np.sin(x) * np.exp(-x / 60))
t = np.linspace(-3, 3, 256)
a, b = np.meshgrid(t, t)
np.save(root / 'matrix.npy', np.sin(a * 5) * np.cos(b * 4) * np.exp(-(a*a + b*b) / 8))
np.savetxt(root / 'custom_signal.csv', np.sin(x), delimiter=',')
print(f'Created signal.npy, matrix.npy and custom_signal.csv in {root}')
