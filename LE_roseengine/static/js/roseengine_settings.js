$(function() {
    function RoseengineSettingsHook(parameters) {
        var settingsVm = parameters[0];

        this.onSettingsShown = function() {
            var plugin = settingsVm.settings.plugins.roseengine;

            // Ensure axis_rules is an observableArray
            if (!ko.isObservable(plugin.axis_rules)) {
                plugin.axis_rules = ko.observableArray(plugin.axis_rules || []);
            }

            // Always (re)attach functions when dialog opens
            plugin.addAxisRule = function () {
                var f = $("#axis_first").val();
                var t = $("#axis_second").val();
                var sg = $("#axis_sign").val();
                if (!f || !t || !sg) return;
                plugin.axis_rules.push({ first: f, second: t, sign: sg });
            };

            plugin.removeAxisRule = function (rule) {
                plugin.axis_rules.remove(rule);
            };
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: RoseengineSettingsHook,
        dependencies: ["settingsViewModel"],
        elements: [] // No DOM binding!
    });
});