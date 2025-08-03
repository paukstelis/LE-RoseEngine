/*
 * View model for LE-RoseEngine
 *
* Author: Paul Paukstelis
 * License: AGPLv3
 */
$(function() {
    function RoseengineViewModel(parameters) {
        var self = this;
        self.global_settings = parameters[1];
        self.radii_rock = [];
        self.angles_rock = [];
        self.radii_pump = [];
        self.angles_pump = [];
        self.rpm = ko.observable(3);
        self.amp = ko.observable(1);
        self.start_coord = [0,0,0];
        self.forward = ko.observable(true);

        tab = document.getElementById("tab_plugin_roseengine_link");
        tab.innerHTML = tab.innerHTML.replaceAll("Roseengine Plugin", "Rose Engine");
        // assign the injected parameters, e.g.:
        // self.loginStateViewModel = parameters[0];
        // self.settingsViewModel = parameters[1];

        // TODO: Implement your plugin's view model here.
        // Fetch the list of .svg files from the uploads/rosette directory
        self.fetchProfileFiles = function() {
            OctoPrint.files.listForLocation("local/rosette", false)
                .done(function(data) {
                    var rosettes = data.children;
                    console.log(rosettes);
                    rosettes.sort((a,b) => { return a.name.localeCompare(b.name) });
                    self.rosettes = rosettes;
                    populateFileSelector(rosettes, "#rosette_file_select", "machinecode");
                })
                .fail(function() {
                    console.error("Failed to fetch svg files.");
                });
        };

        function populateFileSelector(files, elem, type) {
            var fileSelector = $(elem);
            fileSelector.empty();
            fileSelector.append($("<option>").text("Select file").attr("value", ""));
            files.forEach(function(file, i) {
                var option = $("<option>")
                    .text(file.display)
                    .attr("value", file.name)
                    .attr("download",file.refs.download)
                    .attr("path",file.path)
                    .attr("index", i);
                fileSelector.append(option);
            });
        }

        self.onBeforeBinding = function () {
            self.settings = self.global_settings.settings.plugins.roseengine;
            //console.log(self.global_settings);
            self.fetchProfileFiles();
            self.smooth_points = self.settings.smooth_points;
            self.tool_length = self.settings.tool_length;
            self.increment = self.settings.increment;

        };

        $("#rosette_file_select").on("change", function () {
            var filePath = $("#rosette_file_select option:selected").attr("path");
            self.name = $("#rosette_file_select option:selected").attr("value");
            if (!filePath) return;

            self.load_rosette(filePath);
            
        });

        self.createPolarPlot  = function() {
            var trace = {
                r: self.radii_rock,
                theta: self.angles_rock,
                mode: 'lines',
                name: 'Scan Profile',
                type: 'scatterpolar',
                line: {
                    color: 'blue',
                    width: 2
                }

            };

            var layout = {
                title: 'Rosette',
                polar: {
                    radialaxis: {
                      visible: false,
                      autorange: true,
                      showline: false, // Hides the axis line
                      zeroline: false
                    },
                    angularaxis: {
                      showline: false, // Hides the axis line
                      zeroline: false,
                      rotation: 180,
                      direction: "clockwise"
                    }
                }
            };

            //Make a plot
            Plotly.newPlot('plotarea',[trace], layout);

        };

        self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin == 'roseengine' && data.type == 'graph') {
                self.radii_rock = data.radii;
                self.angles_rock = data.angles;
                this.createPolarPlot();
            }
        };

        self.send_error_messasge = function(message) {
            var data = {
                message: message
            };

            OctoPrint.simpleApiCommand("latheengraver", "send_error_message", data)
                .done(function(response) {
                    console.log("Error message sent");
                })
                .fail(function() {
                    console.error("Error message not sent");
                });
        };

        self.jog = function(dir) {
            

            var data = {
                direction: dir,
            };

            OctoPrint.simpleApiCommand("roseengine", "jog", data)
                .done(function(response) {
                    console.log("File info transmitted");
                })
                .fail(function() {
                    console.error("File info not transmitted");
                });

        };

        self.load_rosette = function(filePath) {
            var data = {
                filepath: filePath,
                type: "rock"
            };

            OctoPrint.simpleApiCommand("roseengine", "load_rosette", data)
                .done(function(response) {
                    console.log("File info transmitted");
                })
                .fail(function() {
                    console.error("File info not transmitted");
                });

        };

        self.startjob = function() {

            var data = {
                rpm: self.rpm(),
                amp: self.amp(),
                forward: self.forward(),
            };

            OctoPrint.simpleApiCommand("roseengine", "start_job", data)
                .done(function(response) {
                    console.log("GCode written successfully.");
                })
                .fail(function() {
                    console.error("Failed to write GCode.");
                });

        };

        self.stopjob = function() {

            var data = {
                stop: true
            };

            OctoPrint.simpleApiCommand("roseengine", "stop_job", data)
                .done(function(response) {
                    console.log("GCode written successfully.");
                })
                .fail(function() {
                    console.error("Failed to write GCode.");
                });

        };

        self.gotostart = function() {

            var data = {
                reset: true
            };

            OctoPrint.simpleApiCommand("roseengine", "goto_start", data)
                .done(function(response) {
                    console.log("GCode written successfully.");
                })
                .fail(function() {
                    console.error("Failed to write GCode.");
                });

        };

    }

    /* view model class, parameters for constructor, container to bind to
     * Please see http://docs.octoprint.org/en/master/plugins/viewmodels.html#registering-custom-viewmodels for more details
     * and a full list of the available options.
     */
    OCTOPRINT_VIEWMODELS.push({
        construct: RoseengineViewModel,
        // ViewModels your plugin depends on, e.g. loginStateViewModel, settingsViewModel, ...
        dependencies: ["filesViewModel", "settingsViewModel", "accessViewModel","loginStateViewModel"],
        // Elements to bind to, e.g. #settings_plugin_roseengine, #tab_plugin_roseengine, ...
        elements: [ "#tab_plugin_roseengine","#settings_plugin_roseengine" ]
    });
});
