# Fonts

Arabic screenshot labels use Noto Naskh Arabic (SIL Open Font License 1.1).

The font file is not shipped in this repository. If you want the label tests
and annotation tools to draw Arabic text:

- download Noto Naskh Arabic from Google Fonts and put
  `NotoNaskhArabic-Regular.ttf` in this folder, or
- install a system package such as `fonts-noto-core` (Debian/Ubuntu), or
- set `SF_ARABIC_FONT` (or `SF_AT_FONT`) to a `.ttf` / `.otf` you already have.

Image-comparison tests and Arabic-label tests **skip cleanly** when the font
or optional reference images are absent. They do not fail a fresh clone.
