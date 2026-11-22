"""Extract the font file the vendor app uploads to the controller (command 0x03).

The file belongs to the vendor and is therefore not part of this project. If you need it,
extract it from your own copy of the "RGB Switcher" Android app (APK):

    .venv/bin/python tools/extract_vendor_fonts.py path/to/RGB_Switcher.apk

It is written to ko5g/assets/fonts_color.bin (ignored by git).
"""
import os
import sys
import zipfile

DEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ko5g", "assets", "fonts_color.bin")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    with zipfile.ZipFile(sys.argv[1]) as z:
        try:
            data = z.read("assets/fonts/color.bin")
        except KeyError:
            sys.exit("assets/fonts/color.bin not found in this APK")
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    with open(DEST, "wb") as f:
        f.write(data)
    print(f"wrote {DEST} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
