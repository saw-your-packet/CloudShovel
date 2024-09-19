from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="cloudshovel",
    version="1.0.0",
    author="Eduard Agavriloae",
    author_email="eduard.agavriloae@hacktodef.com",
    description="A tool for digging secrets in public AMIs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/saw-your-packet/CloudShovel",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Operating System :: OS Independent",
        "Topic :: Security",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.6",
    install_requires=[
        "boto3",
        "colorama",
    ],
    entry_points={
        "console_scripts": [
            "cloudshovel=cloudshovel.main:main",
        ],
    },
    include_package_data=True,
    keywords="aws ami secrets cloudshovel cloudquarry"
)