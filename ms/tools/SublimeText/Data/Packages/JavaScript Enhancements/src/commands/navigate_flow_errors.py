import sublime, sublime_plugin
from .navigate_regions import JavascriptEnhancementsNavigateRegionsCommand

class JavascriptEnhancementsNavigateFlowErrorsCommand(JavascriptEnhancementsNavigateRegionsCommand, sublime_plugin.TextCommand):
  region_keys = ["javascript_enhancements_flow_error", "javascript_enhancements_flow_warning"]