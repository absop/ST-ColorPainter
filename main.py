import sublime
import sublime_plugin

import re
import os
import json

from . import profile


DEFAULT_COLOE_SCHEME = "Monokai.sublime-color-scheme"


class Loger:
    debug = False

    def print(*args):
        if Loger.debug:
            print("[Tincter:]", *args)


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
        TinctViewsManager.tinct_view(self.view)


class TincterClearViewCommand(TincterCommand):
    def run(self, edit):
        self.log_command()
        TinctViewsManager.clear_view(self.view)


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
        self.selection_points = []
        self.color_table_selection = {}
        self.color_table_full_text = {}
        self.scheme_rules_full_text = []
        self.scheme_rules_selection = []
        self.get_color_regexs(color_modes)

    def get_color_regexs(self, color_modes):
        regexs = []
        for clmd in color_modes:
            if clmd in profile.color_regexs:
                regex = profile.color_regexs[clmd]
                regexs.append(regex)

        regex = r"(" + "|".join(regexs) + r")"
        self.regex = re.compile(regex)
        # Loger.print("color regexs:", regex)

    def update_color_modes(self, color_modes):
        self.get_color_regexs(color_modes)
        self.reload()

    def reload(self):
        self.clear_all()
        self.on_load()

    def clear_selection(self):
        Loger.print("clear selection:", self.color_table_selection)
        for key, regions, scope in self.color_table_selection.values():
            self.view.erase_regions(key)
        self.color_table_selection = {}
        self.scheme_rules_selection = []

    def clear_all(self):
        self.clear_selection()
        self.selection_points = []

        for key, regions, scope in self.color_table_full_text.values():
            self.view.erase_regions(key)
        self.color_table_full_text = {}
        self.scheme_rules_full_text = []

    def find_colors_with_region(self, region):
        conten = self.view.substr(region)
        matches = self.regex.finditer(conten)
        b = region.begin()
        for match in matches:
            l, r = match.span()
            region = sublime.Region(l + b, r + b)
            yield (region, match.group())

    def find_colors_with_points(self, points):
        for pt in points:
            line = self.view.line(pt)
            l = max(pt - 32, line.begin())
            r = min(pt + 32, line.end())
            region = sublime.Region(l, r)
            line = self.view.substr(region)
            match = self.regex.search(line)
            if match is not None:
                r = l + match.span()[1]
                l = l + match.span()[0]
                if r < pt or l > pt:
                    continue
                region = sublime.Region(l, r)
                yield (region, match.group())

    def rebuild_scheme_rules(self, bg_full_text, bg_selection):
        Loger.print("rebuild color scheme...")

        # TODO: make colors displayed more clearly.
        for rule in self.scheme_rules_full_text:
            rule["background"] = bg_full_text
            pass
        for rule in self.scheme_rules_selection:
            rule["background"] = bg_selection
            pass

    def change_gutter_icon(self, gutter_icon):
        style = TinctViewsManager.style_full_text
        for key, regions, scope in self.color_table_full_text.values():
            self.view.erase_regions(key)
            self.view.add_regions(key, regions,
                scope=scope,
                icon=gutter_icon,
                flags=style)

    def store_colors(self, color_table, pairs):
        for region, color in pairs:
            if color not in color_table:
                key, scope = profile._color_key_scope()
                color_table[color] = (key, [], scope)
            color_table[color][1].append(region)

    def make_rules_and_add_regions(self, make_rule, color_table, rules, style):
        for color in color_table:
            key, regions, scope = color_table[color]
            rules.append(make_rule(key, scope, color))

        TinctViewsManager.write_scheme()

        gutter_icon = TinctViewsManager.gutter_icon
        for key, regions, scope in color_table.values():
            self.view.add_regions(key, regions,
                scope=scope,
                icon=gutter_icon,
                flags=style)

    def tinct_full_text(self):
        rules = self.scheme_rules_full_text
        style = TinctViewsManager.style_full_text
        make_rule = TinctViewsManager.make_rule_full_text
        color_table = self.color_table_full_text

        region = sublime.Region(0, self.view.size())
        pairs = self.find_colors_with_region(region)
        self.store_colors(color_table, pairs)
        self.make_rules_and_add_regions(make_rule, color_table, rules, style)

    def tinct_selection(self):
        points = [s.a for s in self.view.sel()]
        if points == self.selection_points:
            return

        self.clear_selection()
        self.selection_points = points

        rules = self.scheme_rules_selection
        style = TinctViewsManager.style_selection
        make_rule = TinctViewsManager.make_rule_selection
        color_table = self.color_table_selection

        pairs = self.find_colors_with_points(points)
        self.store_colors(color_table, pairs)
        self.make_rules_and_add_regions(make_rule, color_table, rules, style)

    def on_load(self):
        self.tinct_full_text()

    def on_selection_modified(self):
        self.tinct_selection()

    def on_modified(self):
        pass

    def on_activated(self):
        pass

    def on_post_save(self):
        pass


class TinctViewsManager(sublime_plugin.EventListener):
    ignored_views = {}
    tincted_views = {}
    gutter_icon = "circle"
    gutter_icons = {"", "dot", "circle", "bookmark"}
    color_scheme = ""
    file_types = []
    color_modes = []
    syntax_specific = []
    style_full_text = profile.STYLE_FULL_TEXT
    style_selection = profile.STYLE_SELECTION
    make_rule_full_text = None
    make_rule_selection = None

    @classmethod
    def _tinct_view(cls, view, color_modes):
        if not color_modes:
            sublime.error_message("\tNot work in current file\n"
                                  "because no color_modes was added!")
            return

        view_listener = TincterViewEventListener(view, color_modes)
        view_listener.on_load()
        cls.tincted_views[view.view_id] = view_listener

        color_modes = "+".join(color_modes)
        filename = view.file_name() or "untitled"
        log = ["_tinct_view:", filename, color_modes]
        Loger.print("\n\t".join(log))

    @classmethod
    def _load_view(cls, view):
        if view.view_id in cls.ignored_views:
            view_listener = cls.ignored_views.pop(view.view_id)
            view_listener.on_load()
            cls.tincted_views[view.view_id] = view_listener
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

    @classmethod
    def update_gutter_icon(cls, gutter_icon):
        if gutter_icon in cls.gutter_icons:
            cls.gutter_icon = gutter_icon
            for view_listener in cls.tincted_views.values():
                view_listener.change_gutter_icon(gutter_icon)

    @classmethod
    def update_file_types(cls, file_types):
        cls.file_types = file_types
        pass

    @classmethod
    def update_color_modes(cls, color_modes):
        hexs = [cm for cm in color_modes if cm.startswith("hex")]
        color_modes = [cm for cm in color_modes if cm not in hexs]
        hexs.sort(reverse=True)
        cls.color_modes = hexs + color_modes
        pass

    @classmethod
    def update_color_scheme(cls, color_scheme):
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
    def update_syntax_specific(cls, syntax_specific):
        cls.syntax_specific = syntax_specific
        pass

    @classmethod
    def write_scheme(cls):
        scheme_rules = []
        for view_listener in cls.tincted_views.values():
            scheme_rules.extend(view_listener.scheme_rules_full_text)
            scheme_rules.extend(view_listener.scheme_rules_selection)
        if scheme_rules:
            cls.cswriter.write_color_scheme(scheme_rules)

    def on_load(self, view):
        TinctViewsManager.load_view(view)

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
        if view.view_id in self.tincted_views:
            view_listener = self.tincted_views[view.view_id]
            view_listener.on_post_save()

    def on_close(self, view):
        if view.view_id in self.tincted_views:
            self.tincted_views.pop(view.view_id)
        elif view.view_id in self.ignored_views:
            self.ignored_views.pop(view.view_id)


settings = {}
preferences = {}


def load_plugin(cls):
    def _reload_settings():
        highlight_style = settings.get("highlight_style", {})
        style_full_text = highlight_style.get("full_text", "text")
        style_selection = highlight_style.get("selection", "fill")

        cls.style_full_text = profile.identify_style(style_full_text)
        cls.style_selection = profile.identify_style(style_selection)
        cls.update_gutter_icon(settings.get("gutter_icon", "circle"))
        cls.update_file_types(settings.get("file_types", []))
        cls.update_syntax_specific(settings.get("syntax_specific", {}))
        cls.update_color_modes(settings.get("color_modes", []))

    def _load_color_scheme():
        color_scheme = preferences.get("color_scheme", DEFAULT_COLOE_SCHEME)
        if color_scheme != cls.color_scheme:
            cls.update_color_scheme(color_scheme)

    global settings
    global preferences
    settings = sublime.load_settings("Tincter.sublime-settings")
    preferences = sublime.load_settings("Preferences.sublime-settings")

    _reload_settings()
    _load_color_scheme()

    settings.add_on_change("highlight_style", _reload_settings)
    preferences.add_on_change("color_scheme", _load_color_scheme)


def plugin_loaded():
    profile.color_identify_number = 0
    os.makedirs(profile._color_scheme_cache_dir(relative=False), exist_ok=True)

    load_plugin(TinctViewsManager)
    view = sublime.active_window().active_view()
    TinctViewsManager.load_view(view)

def plugin_unloaded():
    settings.clear_on_change("highlight_style")
    preferences.clear_on_change("color_scheme")
    TinctViewsManager.clear_all()
