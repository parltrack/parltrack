from setuptools import setup, find_packages
import sys, os

version = '0.1'

setup(name='parltrack',
      version=version,
      description="A parliamentary tracking software package",
      long_description="""\
Track procedures and stages in parliamentary work""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='parliament tracking legislation legislative mongodb flask',
      author='Stefan Marsirske, Friedrich Lindenberg',
      author_email='',
      url='',
      license='AGPLv3',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
