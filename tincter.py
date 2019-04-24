import sublime
import sublime_plugin

import re
import os
import json

from . import profile


DEFAULT_COLOR_SCHEME = "Monokai.sublime-color-scheme"


class Loger:
    debug = False

    def print(*args):
        if Loger.debug:
            print("[Tincter:]", *args)

    def error(errmsg):
        sublime.error_message(errmsg)


class TincterToggleLogCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        Loger.debug = not Loger.debug


class TincterCommand(sublime_plugin.TextCommand):
    def log_command(self):
        filename = self.view.file_name() or "untitled"
        Loger.print("{}:".format(self.name()), filename)


class TincterTinctViewCommand(TincterCommand):
    def run(self, edit):
        self.log_command()
        TincterViewsManager.tinct_view(self.view)


class TincterClearViewCommand(TincterCommand):
    def run(self, edit):
        self.log_command()
        TincterViewsManager.clear_view(self.view)


class ColorSchemeWriter(object):
    def __init__(self, color_scheme):
        view = sublime.active_window().active_view()
        view.settings().set("color_scheme", color_scheme)

        self.bg_selection = view.style()["background"]
        self.bg_full_text = self.nearest_color(self.bg_selection)
        self.abspath = profile._color_scheme_cache_path(color_scheme)

    def nearest_color(self, color):
        b = int(color[5:7], 16)
        b += 1 - 2 * (b == 255)
        return color[:-2] + "%02x" % b

    # TODO: make colors displayed more clearly.
    def make_rule(self, style):
        def rules(key, scope, color):
            return {"name": key, "scope": scope,
                    # "font_style": "bold",
                    "background": bgcolor, "foreground": color }

        bgcolor = self.bg_full_text
        if style == profile.STYLE_SELECTION:
            bgcolor = self.bg_selection
        return rules

    def write_color_scheme(self, rules):
        profile.scheme_data["rules"] = rules
        with open(self.abspath, "w") as file:
            file.write(json.dumps(profile.scheme_data))

        entry = ["write_color_scheme:", self.abspath]
        Loger.print("\n\t".join(entry))


class TincterViewEventListener(object):
    def __init__(self, view, color_modes):
        self.view = view
        no = str(view.view_id)
        self.key_prefix = "tincter" + no + "_"
        self.color_number = 0
        self.selection_points = []
        self.keys_selection = {}
        self.keys_full_text = {}
        self.scheme_rules_full_text = []
        self.scheme_rules_selection = []
        self.get_color_regexs(color_modes)

    def get_color_regexs(self, color_modes):
        regexs = []
        for mode in color_modes:
            if mode in profile.color_regexs:
                regex = profile.color_regexs[mode]
                regexs.append(regex)

        regex = r"(" + "|".join(regexs) + r")"
        self.regex = re.compile(regex)

    def change_color_modes(self, color_modes):
        self.get_color_regexs(color_modes)
        self.reload()

    def rebuild_scheme_rules(self, bg_full_text, bg_selection):
        filename = self.view.file_name() or "untitled"
        entry = ["rebuild color scheme...", filename]
        Loger.print("\n\t".join(entry))

        # TODO: make colors displayed more clearly.
        for rule in self.scheme_rules_full_text:
            rule["background"] = bg_full_text
            pass
        for rule in self.scheme_rules_selection:
            rule["background"] = bg_selection
            pass

    def change_gutter_icon(self, gutter_icon):
        style = TincterViewsManager.style_full_text
        for row in self.keys_full_text:
            for key in self.keys_full_text[row]:
                regions = self.view.get_regions(key)
                self.view.erase_regions(key)
                self.view.add_regions(key, regions,
                    scope=key,
                    icon=gutter_icon,
                    flags=style)

    def reload(self):
        self.clear_all()
        self.on_load()

    def clear_selection(self):
        Loger.print("erase selection:", self.keys_selection)

        for key in self.keys_selection:
            self.view.erase_regions(key)
        self.keys_selection = {}
        self.scheme_rules_selection = []

    def clear_all(self):
        self.clear_selection()
        self.selection_points = []

        for row in self.keys_full_text:
            for key in self.keys_full_text[row]:
                self.view.erase_regions(key)
        self.color_number = 0
        self.keys_full_text = {}
        self.scheme_rules_full_text = []

    def get_new_colors_in_region(self, region):
        key_regions = []
        make_rule_full_text = TincterViewsManager.make_rule_full_text
        make_rule_selection = TincterViewsManager.make_rule_selection
        conten = self.view.substr(region)
        b = region.begin()
        for match in self.regex.finditer(conten):
            l, r = match.span()
            region = sublime.Region(l + b, r + b)
            row, col = self.view.rowcol(region.a)
            color = match.group()
            key = self.key_prefix + str(self.color_number)
            key_s = key + "s"
            self.color_number += 1
            rule_full_text = make_rule_full_text(key, key, color)
            rule_selection = make_rule_selection(key_s, key_s, color)
            self.scheme_rules_full_text.append(rule_full_text)
            self.scheme_rules_selection.append(rule_selection)

            key_regions.append((key, [region]))
            if row not in self.keys_full_text:
                self.keys_full_text[row] = []
            self.keys_full_text[row].append(key)

        return key_regions

    def tinct_regions(self, regions):
        key_regions = []
        for region in regions:
            key_regions.extend(self.get_new_colors_in_region(region))
        if len(key_regions) > 0:
            TincterViewsManager.write_scheme()
            gutter_icon = TincterViewsManager.gutter_icon
            style = TincterViewsManager.style_full_text
            for key, regions in key_regions:
                self.view.add_regions(key, regions,
                    scope=key,
                    icon=gutter_icon,
                    flags=style)

    def tinct_full_text(self):
        region = sublime.Region(0, self.view.size())
        self.tinct_regions([region])

    def tinct_selection(self):
        points = [s.a for s in self.view.sel()]
        if points == self.selection_points:
            return
        self.selection_points = points

        new_selection = {}
        gutter_icon = TincterViewsManager.gutter_icon
        style = TincterViewsManager.style_selection
        for pt in points:
            row, col = self.view.rowcol(pt)
            if row in self.keys_full_text:
                for key in self.keys_full_text[row]:
                    regions = self.view.get_regions(key)
                    key_s = key + "s"
                    if not regions:
                        regions = self.view.get_regions(key_s)
                    if regions and regions[0].a <= pt and regions[0].b >= pt:
                        color = self.view.substr(regions[0])
                        new_selection[key_s] = color
                        if key_s not in self.keys_selection:
                            Loger.print("new selection:", key_s, color)
                            self.view.erase_regions(key)
                            self.view.add_regions(key_s, regions,
                                scope=key_s,
                                icon=gutter_icon,
                                flags=style)
                        break

        style = TincterViewsManager.style_full_text
        for key in self.keys_selection:
            if key not in new_selection:
                regions = self.view.get_regions(key)
                self.view.erase_regions(key)
                key = key[:-1]
                self.view.add_regions(key, regions,
                    scope=key,
                    icon=gutter_icon,
                    flags=style)
        self.keys_selection = new_selection


    def modified_regions(self):
        rows = set()
        for sel in self.view.sel():
            row, col = self.view.rowcol(sel.a)
            if row not in rows:
                if row in self.keys_full_text:
                    Loger.print("erase color by:", row)
                    for key in self.keys_full_text.pop(row):
                        # regions = self.view.get_regions(key + "s")
                        self.view.erase_regions(key)
                        self.view.erase_regions(key + "s")
                rows.add(row)
                yield self.view.line(sel.a)

    def on_load(self):
        self.tinct_full_text()

    def on_selection_modified(self):
        self.tinct_selection()

    def on_modified(self):
        # TODO: too much!
        self.tinct_regions(self.modified_regions())
        # self.reload()
        # self.on_selection_modified()

    def on_activated(self):
        pass


class TincterViewsManager(sublime_plugin.EventListener):
    ignored_views = {}
    tincted_views = {}
    color_modes = ["hex8", "hex6", "hex4", "hex3",
                    "hsl", "hsla", "rgb", "rgba", "css_named"]
    supported_color_modes = tuple(color_modes)
    gutter_icon = "circle"
    supported_gutter_icons = {"", "dot", "circle", "bookmark"}

    color_scheme = ""
    file_types = []
    syntax_specific = []
    style_full_text = profile.STYLE_FULL_TEXT
    style_selection = profile.STYLE_SELECTION
    make_rule_full_text = None
    make_rule_selection = None

    @classmethod
    def _tinct_view(cls, view, color_modes):
        if not color_modes:
            Loger.error(profile.error_color_modes_missing)
            return
        filename = view.file_name() or "untitled"
        log = ["_tinct_view:", filename, "+".join(color_modes)]
        Loger.print("\n\t".join(log))

        view_listener = TincterViewEventListener(view, color_modes)
        cls.tincted_views[view.view_id] = view_listener
        cls.tincted_views[view.view_id].on_load()


    @classmethod
    def _load_view(cls, view):
        if view.view_id in cls.ignored_views:
            view_listener = cls.ignored_views.pop(view.view_id)
            cls.tincted_views[view.view_id] = view_listener
            cls.tincted_views[view.view_id].on_load()
            return

        filename = view.file_name()
        color_modes = cls.color_modes

        if filename:
            name, ext = os.path.splitext(filename)
            ext = ext.lstrip(".")
            if ext in cls.syntax_specific:
                rmv = cls.syntax_specific[ext]
                color_modes = [cm for cm in color_modes if cm not in rmv]
            elif ext not in cls.file_types:
                return
        cls._tinct_view(view, color_modes)

    @classmethod
    def tinct_view(cls, view):
        if view.view_id not in cls.tincted_views:
            cls._load_view(view)
        if view.view_id not in cls.tincted_views:
            cls._tinct_view(view, cls.color_modes)

    @classmethod
    def load_view(cls, view):
        # ignore views such as console, commands panel...
        views = sublime.active_window().views()
        if view.size() < 4 or view not in views:
            return
        if view.view_id not in cls.ignored_views:
            cls._load_view(view)

    @classmethod
    def clear_view(cls, view):
        if view.view_id in cls.tincted_views:
            view_listener = cls.tincted_views.pop(view.view_id)
            view_listener.clear_all()
            cls.ignored_views[view.view_id] = view_listener

    @classmethod
    def clear_all(cls):
        for view_listener in cls.tincted_views.values():
            view_listener.clear_all()
        cls.ignored_views = cls.tincted_views
        cls.tincted_views = {}

    @classmethod
    def clear_and_restart(cls):
        for view_listener in cls.tincted_views.values():
            view_listener.clear_all()
        for view_listener in cls.ignored_views.values():
            view_listener.clear_all()
        cls.tincted_views = {}
        cls.ignored_views = {}
        for window in sublime.windows():
            for view in window.views():
                cls.load_view(view)

    @classmethod
    def update_color_modes(cls, color_modes):
        if color_modes == cls.color_modes:
            return
        unsupported_color_modes = []
        other_color_modes, hex_color_modes = [], []
        for color_mode in color_modes:
            if color_mode in cls.supported_color_modes:
                if color_mode.startswith("hex"):
                    hex_color_modes.append(color_mode)
                else:
                    other_color_modes.append(color_mode)
            else:
                unsupported_color_modes.append(color_mode)
        hex_color_modes.sort(reverse=True)
        color_modes = hex_color_modes + other_color_modes

        if color_modes != cls.color_modes:
            cls.color_modes = color_modes
            cls.clear_and_restart()

    @classmethod
    def update_gutter_icon(cls, gutter_icon):
        if gutter_icon not in cls.supported_gutter_icons:
            Loger.error(profile.error_gutter_icon.format(gutter_icon))
            return
        if gutter_icon != cls.gutter_icon:
            Loger.print("change gutter_icon form \"{}\" to \"{}\"".format(
                cls.gutter_icon, gutter_icon))
            cls.gutter_icon = gutter_icon
            for view_listener in cls.tincted_views.values():
                view_listener.change_gutter_icon(gutter_icon)

    @classmethod
    def update_color_scheme(cls, color_scheme):
        if color_scheme == cls.color_scheme:
            return
        cls.cswriter = ColorSchemeWriter(color_scheme)
        cls.make_rule_full_text = cls.cswriter.make_rule(cls.style_full_text)
        cls.make_rule_selection = cls.cswriter.make_rule(cls.style_selection)
        cls.color_scheme = color_scheme

        bg_full_text = cls.cswriter.bg_full_text
        bg_selection = cls.cswriter.bg_selection
        for view_listener in cls.tincted_views.values():
            view_listener.rebuild_scheme_rules(bg_full_text, bg_selection)
        cls.write_scheme()

    @classmethod
    def write_scheme(cls):
        scheme_rules = []
        for view_listener in cls.tincted_views.values():
            scheme_rules.extend(view_listener.scheme_rules_full_text)
            scheme_rules.extend(view_listener.scheme_rules_selection)
        if scheme_rules:
            cls.cswriter.write_color_scheme(scheme_rules)

    def on_load(self, view):
        TincterViewsManager.load_view(view)

    def on_modified(self, view):
        if view.view_id in self.tincted_views:
            view_listener = self.tincted_views[view.view_id]
            view_listener.on_modified()

    def on_selection_modified(self, view):
        if view.view_id in self.tincted_views:
            if self.style_selection == self.style_full_text:
                return
            view_listener = self.tincted_views[view.view_id]
            view_listener.on_selection_modified()

    def on_activated(self, view):
        if view.view_id in self.tincted_views:
            view_listener = self.tincted_views[view.view_id]
            view_listener.on_activated()
        else:
            self.on_load(view)

    def on_post_save(self, view):
        self.on_activated(view)

    def on_close(self, view):
        if view.view_id in self.tincted_views:
            self.tincted_views.pop(view.view_id)
        elif view.view_id in self.ignored_views:
            self.ignored_views.pop(view.view_id)


settings = {}
preferences = {}


def load_plugin(plugin):
    def _reload_settings():
        highlight_style = settings.get("highlight_style", {})
        style_full_text = highlight_style.get("full_text", "text")
        style_selection = highlight_style.get("selection", "fill")

        plugin.file_types = settings.get("file_types", [])
        plugin.syntax_specific = settings.get("syntax_specific", {})
        plugin.style_full_text = profile.identify_style(style_full_text)
        plugin.style_selection = profile.identify_style(style_selection)
        plugin.update_color_modes(settings.get("color_modes", []))
        plugin.update_gutter_icon(settings.get("gutter_icon", "circle"))

    def _reload_color_scheme():
        color_scheme = preferences.get("color_scheme", DEFAULT_COLOR_SCHEME)
        plugin.update_color_scheme(color_scheme)

    global settings
    global preferences
    settings = sublime.load_settings("Tincter.sublime-settings")
    preferences = sublime.load_settings("Preferences.sublime-settings")

    _reload_color_scheme()
    _reload_settings()

    settings.add_on_change("highlight_style", _reload_settings)
    preferences.add_on_change("color_scheme", _reload_color_scheme)


def plugin_loaded():
    os.makedirs(profile._color_scheme_cache_dir(relative=False), exist_ok=True)

    load_plugin(TincterViewsManager)
    view = sublime.active_window().active_view()
    TincterViewsManager.load_view(view)

def plugin_unloaded():
    settings.clear_on_change("highlight_style")
    preferences.clear_on_change("color_scheme")
    TincterViewsManager.clear_all()
