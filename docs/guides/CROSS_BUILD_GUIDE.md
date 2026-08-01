# Cross Build Guide

Nuitka Studio 3.9.3 can prepare native Windows and Linux builds from either host operating system by generating a GitHub Actions workflow.

## What Cross Build does

- A Windows `.exe` is compiled on a native `windows-latest` runner.
- A Linux executable is compiled on a native `ubuntu-latest` runner.
- The finished files are uploaded as downloadable GitHub Actions artifacts.
- Linux output is wrapped in a `.tar.gz` archive so executable permissions survive the download.

This is not local cross-compilation. Nuitka links against the selected Python runtime and native operating-system libraries, so reliable releases need a build environment for each target OS.

## Before generating the workflow

Keep all required files inside one project root folder:

```text
my-project/
├── main.py
├── requirements.txt
├── assets/
│   ├── app.ico
│   └── app.png
└── other project files
```

Resources selected in Nuitka Studio must also be inside this folder. GitHub Actions cannot access files elsewhere on your computer.

## Generate the workflow

1. Configure the normal Build, Packages, Resources, and App Identity pages.
2. Open **Cross Build**.
3. Select the project root.
4. Confirm the detected entry script, or select it directly on the Cross Build page.
5. Choose the Python version used by the project.
6. Enter the requirements filename, or leave it blank when no requirements file is needed.
7. Choose Windows, Linux, or both targets.
8. Select separate Windows and Linux icons when needed.
9. Click **Generate workflow**.

The generated file is:

```text
.github/workflows/nuitka-studio-cross-build.yml
```

## Run it on GitHub

1. Commit the generated workflow and the complete project.
2. Push the commit to a GitHub repository.
3. Open the repository **Actions** tab.
4. Select **Nuitka Studio Cross Build**.
5. Choose **Run workflow**.
6. When the jobs finish, download the Windows or Linux artifact.

The optional **build automatically when main/master is pushed** switch adds a push trigger. Leave it disabled when you only want manual builds.

When the selected requirements file already exists in the project, the generated workflow enables pip caching to speed up later runs. Each native job has a 120-minute safety timeout, and downloadable artifacts are retained for 14 days.

## Output and installers

Cross Build creates native application artifacts. It does not currently package the Windows application with Inno Setup or convert the Linux build into a Debian `.deb` package. Use the native **Installer** or **Debian package** workflow on the corresponding operating system after the application build is verified.

## Common problems

- **The entry script belongs to another application:** reselect the project root. Version 3.9.3 automatically detects the new project's entry script and removes stale project-specific paths.
- **A resource is outside the project root:** move or copy it into the repository and select it again.
- **A package is missing:** add it to `requirements.txt` and, only when Nuitka cannot detect it, add it under **Packages**.
- **The workflow is not visible:** ensure the workflow file was committed to the repository's default branch.
- **The downloaded Linux program is not executable:** extract the supplied `.tar.gz` archive instead of copying a raw file from the build log.
- **A platform-specific dependency fails:** test and configure that dependency separately for Windows and Linux.
