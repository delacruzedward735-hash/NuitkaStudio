# Publishing Nuitka Studio on GitHub

## Create the repository

Create a new public repository named `Nuitka-Studio` under `delacruzedward735-hash`. Do not initialize it with another README, license, or `.gitignore` because those files already exist in this project.

## Push the source

From the extracted project folder:

```bash
git init
git add .
git commit -m "Open-source Nuitka Studio 3.9.3"
git branch -M main
git remote add origin https://github.com/delacruzedward735-hash/Nuitka-Studio.git
git push -u origin main
```

## Recommended repository settings

- Enable **Issues**.
- Enable **Discussions** for questions and community support when desired.
- Enable **Private vulnerability reporting** under Security settings.
- Enable Dependabot alerts and security updates.
- Protect `main` and require the **Tests** workflow before merging.
- Prevent force pushes and branch deletion on `main`.
- Add repository topics such as `python`, `nuitka`, `compiler`, `packaging`, `windows`, `linux`, `customtkinter`, and `developer-tools`.
- Set the project website to `https://myportfoliohub.online`.

## First release

1. Confirm the GitHub Actions test workflow passes.
2. Test the source on Windows and Linux.
3. Build and verify the Windows and Linux applications.
4. Complete Windows install, upgrade, and uninstall tests.
5. Complete Debian install, upgrade, and removal tests.
6. Create a tag:

   ```bash
   git tag -a v3.9.3 -m "Nuitka Studio 3.9.3"
   git push origin v3.9.3
   ```

7. Create a GitHub Release from the tag and attach tested binaries, installers, checksums, and release notes.

Do not commit `.venv`, build output, logs, private settings, signing keys, or confidential payment details.
