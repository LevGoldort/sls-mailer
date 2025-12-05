# OpenDyslexic Font Installation

The OpenDyslexic font files are required for the dyslexia-friendly font feature in the accessibility toolbar.

## Download Instructions

1. Visit: https://opendyslexic.org/
2. Download the latest version (v2.0 or later)
3. Extract the following files to this directory:
   - `OpenDyslexic-Regular.woff2`
   - `OpenDyslexic-Bold.woff2`

## Alternative Download

You can also download from GitHub:
https://github.com/antijingoist/opendyslexic/releases

## License

OpenDyslexic is licensed under the SIL Open Font License (OFL)
This means it is free to use for both personal and commercial purposes.

## Converting to WOFF2

If you download TTF/OTF files, convert them to WOFF2 for better web performance:

### Online Tool:
- https://cloudconvert.com/ttf-to-woff2

### Command Line (if you have fonttools installed):
```bash
pyftsubset OpenDyslexic-Regular.ttf --output-file=OpenDyslexic-Regular.woff2 --flavor=woff2
pyftsubset OpenDyslexic-Bold.ttf --output-file=OpenDyslexic-Bold.woff2 --flavor=woff2
```

## Required Files

After downloading, you should have:
- `OpenDyslexic-Regular.woff2` (~50KB)
- `OpenDyslexic-Bold.woff2` (~50KB)
- `OpenDyslexic-LICENSE.txt` (copy from download)

## Testing

The accessibility toolbar will still work without these fonts, but the "Dyslexia Support" feature will fall back to the system font until the OpenDyslexic files are added.
