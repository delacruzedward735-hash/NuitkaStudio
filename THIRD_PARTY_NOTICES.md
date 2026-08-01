# Third-Party Notices

Nuitka Studio is distributed under the MIT License. It relies on or integrates with third-party software that remains under its own license. This file is a practical notice, not a replacement for the license files supplied by each upstream project.

## Python dependencies

| Dependency | Purpose | Upstream license |
|---|---|---|
| CustomTkinter | Modern Tkinter widgets | MIT |
| darkdetect | System appearance detection | BSD-3-Clause |
| packaging | Version and requirement utilities | Apache-2.0 OR BSD-2-Clause |
| Nuitka | Python compiler invoked by the application | AGPL-3.0 with Nuitka runtime exception terms |
| ordered-set | Ordered set support used by Nuitka | MIT |
| zstandard | Compression support used by Nuitka | BSD-3-Clause |
| Pillow | Image loading and scaling | MIT-CMU |

The pinned dependency versions are listed in `requirements.txt`. Review the installed packages' own metadata and license files when redistributing a bundled application or offline dependency archive.

## External build and packaging tools

Nuitka Studio can call tools that are installed separately, including Python, Tk, GCC, Clang, Microsoft Visual C++ Build Tools, Inno Setup, Git, GitHub Actions, `dpkg-deb`, `patchelf`, and `ccache`. Their licenses and redistribution terms are not changed by the Nuitka Studio license.

## Names and trademarks

Python, GitHub, Windows, Linux, Debian, Ubuntu, Linux Mint, Inno Setup, Nuitka, and other names are used only to describe compatibility or integration. All trademarks belong to their respective owners. No affiliation or endorsement is implied.

## Contributor responsibility

Contributors must identify copied or adapted third-party code and preserve any required copyright, license, and attribution notices. Do not submit code from a source whose license is unknown or incompatible with this repository.
