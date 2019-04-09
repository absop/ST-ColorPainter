import os
import sublime
from .sublime_css_colors import sublime_css_colors

scheme_data = {
    "name": "Tincter",
    "author": "https://github.com/absop",
    "variables": {},
    "globals": {},
    "rules": []
}


STYLE_SELECTION = sublime.DRAW_NO_OUTLINE|sublime.HIDE_ON_MINIMAP
STYLE_FULL_TEXT = sublime.DRAW_NO_OUTLINE|sublime.DRAW_EMPTY_AS_OVERWRITE


def identify_style(style):
    if style == "text":
        return STYLE_FULL_TEXT
    if style == "fill":
        return STYLE_SELECTION


sep = r",\s?"

rgb255 = r"(?:[01]?[0-9]?[0-9]|2(?:[0-4][0-9]|5[0-5]))"
rgb_values = sep.join([rgb255, rgb255, rgb255])

pec  = r"(?:[0-9]?[0-9]|100)%"
hsl360 = r"(?:[0-2]?[0-9]?[0-9]|3[0-5][0-9]|360)"
hsl_values = sep.join([hsl360, pec, pec])

alpah_channel =  sep + r"(?:0?\.[0-9]+|1\.0?)"


color_regexs = {
    "hex8": r"#[0-9a-fA-F]{8}\b",
    "hex6": r"#[0-9a-fA-F]{6}\b",
    "hex4": r"#[0-9a-fA-F]{4}\b",
    "hex3": r"#[0-9a-fA-F]{3}\b",
    "rgb": r"rgb\(" + rgb_values + r"\)",
    "hsl": r"hsl\(" + hsl_values + r"\)",
    "rgba": r"rgba\(" + rgb_values + alpah_channel + r"\)",
    "hsla": r"hsla\(" + hsl_values + alpah_channel + r"\)",
    "css_named": r"\b(?:" + r"|".join(sublime_css_colors) + r")\b"
}


color_identify_number = 0


def _color_key_scope():
    global color_identify_number
    color_id = str(color_identify_number)
    key = "tincter_color_" + color_id
    scope = color_id + ".color.tincter"
    color_identify_number += 1
    return (key, scope)


def _color_scheme_cache_dir(relative=True):
    leaf = "User/Color Schemes/{}".format(__package__)
    branch = "Packages" if relative else sublime.packages_path()
    return os.path.join(branch, leaf).replace("\\", "/")


def _color_scheme_cache_path(color_scheme):
    extname = "sublime-color-scheme"
    dirname = _color_scheme_cache_dir(relative=False)
    filename = os.path.basename(color_scheme).replace("tmTheme", extname)
    return dirname + "/" + filename
