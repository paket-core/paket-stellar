"""Install paket-stellar package"""
from setuptools import setup

setup(
    name='paket-stellar',
    description='Stellar operations for the PAKET project',
    version='1.0.0',
    url='https://github.com/paket-core/paket-stellar',
    license='GNU GPL',
    packages=['paket_stellar'],
    install_requires=[
        'requests==2.20.0'
    ],
    test_suite='tests',
    zip_safe=False)
