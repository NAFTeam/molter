from pathlib import Path

from setuptools import find_packages
from setuptools import setup

setup(
    name="molter",
    description="Shedding a new skin on Dis-Snek's commands.",
    long_description=(Path(__file__).parent / "README.md").read_text(),
    long_description_content_type="text/markdown",
    author="Astrea49",
    url="https://github.com/Astrea49/molter",
    version="0.0.1",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=(Path(__file__).parent / "requirements.txt")
    .read_text()
    .splitlines(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
