# Configure Ko-fi and GCash donations

Nuitka Studio 3.9.3 includes a **Donate** page in the left navigation. Donation details are read from `assets/donation_config.json` and bundled into Windows and Linux builds.

## 1. Add your Ko-fi link

Open `assets/donation_config.json` and set the complete public page URL:

```json
"kofi_url": "https://ko-fi.com/yourname"
```

## 2. Add your public GCash details

Set the recipient name and mobile number that supporters should verify before sending:

```json
"gcash_account_name": "Your GCash display name",
"gcash_number": "09XXXXXXXXX"
```

The application masks the number on screen but the **Copy GCash number** button copies the complete configured value.

## 3. Add the GCash QR image

Save your receiving QR image inside the `assets` folder, for example:

```text
assets/gcash-qr.png
```

Then set:

```json
"gcash_qr_image": "gcash-qr.png"
```

Use only a receiving QR intended for public donations. Never add an OTP, MPIN, password, recovery code, or private identity document.

## 4. Rebuild Nuitka Studio

On Linux, run `./build_gui_linux.sh` or `./build_gui_deb.sh`. On Windows, run `build_gui_exe.bat` or the professional installer builder. The existing build scripts already bundle the complete `assets` folder.
