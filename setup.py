from setuptools import setup, find_packages

setup(
    name='pyfwup',
    version='0.1.3',
    url='https://github.com/usb-tools/pyfwupd',
    license='BSD',
    entry_points={
        'console_scripts': [
            'microprog = fwup_utils.microprog:main',
        ],
    },
    author='Katherine J. Temkin',
    author_email='k@ktemkin.com',
    tests_require=[''],
    install_requires=['pyusb', 'tqdm'],
    description='Python library for programming various USB bootloaders',
    long_description=
    'pyfwup (Python Firmware Uploader) is a set of libraries meant to facilitate uploading firmware to various '
    'devices directly from python.',
    packages=find_packages(),
    include_package_data=True,
    platforms='any',
    classifiers = [
        'Programming Language :: Python',
        'Development Status :: 1 - Planning',
        'Natural Language :: English',
        'Environment :: Console',
        'Environment :: Plugins',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Topic :: Scientific/Engineering',
        'Topic :: Security',
        ],
    extras_require={}
)
