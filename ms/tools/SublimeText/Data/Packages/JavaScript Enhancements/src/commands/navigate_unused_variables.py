import sublime, sublime_plugin
from .navigate_regions import JavascriptEnhancementsNavigateRegionsCommand

class JavascriptEnhancementsNavigateUnusedVariablesCommand(JavascriptEnhancementsNavigateRegionsCommand, sublime_plugin.TextCommand):
  region_keys = ["javascript_enhancements_unused_variable"]