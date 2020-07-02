import os
from setuptools import setup

try:
    README = open(os.path.join(os.path.dirname(__file__), "README.md")).read()
except:
    README = ""

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name="django-fieldsignals",
    version="0.6.0",
    packages=["fieldsignals", "fieldsignals.tests"],
    include_package_data=True,
    test_suite="fieldsignals.tests.test_signals",
    description="Django fieldsignals simply makes it easy to tell when the fields on your model have changed.",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/craigds/django-fieldsignals",
    author="Craig de Stigter",
    author_email="craig.ds@gmail.com",
    classifiers=[
        "Environment :: Web Environment",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
)
