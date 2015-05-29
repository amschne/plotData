try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

config = {
    'description': 'Plot serial data received via the USB port.  Designed for '
                   'use with Arduino microcontrollers.',
    'author': 'Adam Schneider',
    'url': 'URL to get it at.',
    'download_url': 'Where to download it.',
    'author_email': 'amschne@umich.edu',
    'version': '0.1',
    'install_requires': ['nose', 'pyserial', 'numpy', 'pyqtgraph'],
    'packages': ['plotData'],
    'scripts': [],
    'name': 'plotData'
}

setup(**config)