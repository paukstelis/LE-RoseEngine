/*
 * View model for LE-RoseEngine
 *
* Author: Paul Paukstelis
 * License: AGPLv3
 */
$(function() {
    function RoseengineViewModel(parameters) {
        var self = this;
        self.global_settings = parameters[0];
        self.radii_rock = [];
        self.angles_rock = [];
        self.radii_pump = [];
        self.angles_pump = [];
        self.rpm = ko.observable(2);
        self.r_amp = ko.observable(1);
        self.p_amp = ko.observable(1);
        self.forward = ko.observable(true);
        self.dist = ko.observable(1.0);
        self.distances = ko.observableArray([.1, 1, 5, 10, 30, 60, 90]);
        self.a_inc = ko.observable(0.5);
        self.bf_threshold = ko.observable(80);
        self.ms_threshold = ko.observable(10);
        self.chunk = ko.observable(5);

        self.pump_offset = ko.observable(0.0);
        self.rock_offset = ko.observable(0);
        self.pump_invert = ko.observable(0);

        self.phase_offset = ko.observable(0);

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
                    populateFileSelector(rosettes, "#rock_file_select", "machinecode");
                    populateFileSelector(rosettes, "#pump_file_select", "machinecode");

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
            console.log(self.settings);
            self.fetchProfileFiles();
            self.a_inc = self.settings.a_inc();
            console.log("binding self.a_inc")
            console.log(self.a_inc);
            var po = $('#po_span');
            var po_slider = $('#pump_offset');
            po_slider.attr("step", self.a_inc);
            

        };

        $("#rock_file_select").on("change", function () {
            var filePath = $("#rock_file_select option:selected").attr("path");
            self.name = $("#rock_file_select option:selected").attr("value");
            if (!filePath) return;

            self.load_rosette(filePath,"rock");
            
        });

        $("#pump_file_select").on("change", function () {
            var filePath = $("#pump_file_select option:selected").attr("path");
            self.name = $("#pump_file_select option:selected").attr("value");
            if (!filePath) return;

            self.load_rosette(filePath,"pump");
            
        });

        $("#rpm").on("change", function() {

            self.update_rpm();

        });

        self.special_warning = function(a,b) {
            var area = b+'area';
            if (a === "off") {
                $('#'+area).removeClass("shadow-effect");
            }
            else {
                $('#'+area).addClass("shadow-effect");
            }
        }
        
        self.distClicked = function(distance) {
            console.log(distance);
            self.dist(parseFloat(distance));
        };

        self.createPolarPlot  = function(type,rosette_info) {
            var radii = null;
            var theta = null;
            var color = null;
            var area = null;
            console.log(rosette_info);
            var maxrad = rosette_info.max.toFixed(2);
            var minrad = rosette_info.min.toFixed(2);

            if (type === "rock") {
                radii = self.radii_rock;
                theta = self.theta_rock;
                color = 'blue';
                area = 'rockarea';
            }
            
            if (type === "pump") {
                radii = self.radii_pump;
                theta = self.theta_pump;
                color = 'green';
                area = 'pumparea';
            }
            
            var trace = {
                r: radii,
                theta: theta,
                mode: 'lines+markers',
                name: 'Rosette',
                type: 'scatterpolar',
                line: {
                    color: color,
                    width: 2
                },
                marker: {
                    size: 2,
                }

            };

            var layout = {
                autosize: true,
                title: {
                    text: 'r max='+maxrad+'<br>'+'r min='+minrad+'<br>'+type,
                    font: {
                        size: 12
                    },
                },
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
                },

            };

            //Make a plot
            Plotly.newPlot(area,[trace], layout);

        };

        self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin == 'roseengine' && data.type == 'rock') {
                self.radii_rock = data.radii;
                self.angles_rock = data.angles;
                self.special = data.special;
                var rosette_info = {
                    max: data.maxrad,
                    min: data.minrad,
                };
                this.createPolarPlot(data.type, rosette_info);
                if (self.special) {
                    self.special_warning("on","rock");
                }
                else { self.special_warning("off","rock"); }
                
            }

            if (plugin == 'roseengine' && data.type == 'pump') {
                self.radii_pump = data.radii;
                self.angles_pump = data.angles;
                self.special = data.special;
                var rosette_info = {
                    max: data.maxrad,
                    min: data.minrad,
                };
                this.createPolarPlot(data.type, rosette_info);
                if (self.special) {
                    self.special_warning("on","pump");
                }
                else { self.special_warning("off","pump"); }
            }

            if (plugin == 'roseengine' && data.func == 'refresh') {
                self.fetchProfileFiles();
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

        self.re_jog = function(dir) {
            
            var data = {
                direction: dir,
                dist: self.dist(),
            };

            OctoPrint.simpleApiCommand("roseengine", "jog", data)
                .done(function(response) {
                    console.log("Jog sent");
                })
                .fail(function() {
                    console.error("Jog failed");
                });

        };

        self.load_rosette = function(filePath, type) {
            var data = {
                filepath: filePath,
                type: type
            };

            OctoPrint.simpleApiCommand("roseengine", "load_rosette", data)
                .done(function(response) {
                    console.log("File info transmitted");
                })
                .fail(function() {
                    console.error("File info not transmitted");
                });

        };

        self.clear_rosette = function(type) {
            
            var data = {
                type: type,
            };

            OctoPrint.simpleApiCommand("roseengine", "clear", data)
                .done(function(response) {
                    console.log("File info transmitted");
                    var toclear = '#'+type+'area';
                    $(toclear).empty();
                })
                .fail(function() {
                    console.error("clear failed");
                });

        };

        self.startjob = function() {

            var data = {
                rpm: self.rpm(),
                r_amp: self.r_amp(),
                p_amp: self.p_amp(),
                forward: self.forward(),
                pump_offset: self.pump_offset(),
                pump_invert: self.pump_invert(),

            };

            OctoPrint.simpleApiCommand("roseengine", "start_job", data)
                .done(function(response) {
                    console.log("Start sent");
                })
                .fail(function() {
                    console.error("Start failed");
                });

        };

        self.stopjob = function() {

            var data = {
                stop: true
            };

            OctoPrint.simpleApiCommand("roseengine", "stop_job", data)
                .done(function(response) {
                    console.log("Stop sent");
                })
                .fail(function() {
                    console.error("Stop failed");
                });

        };

        self.gotostart = function() {

            var data = {
                reset: true
            };

            OctoPrint.simpleApiCommand("roseengine", "goto_start", data)
                .done(function(response) {
                    console.log("Reset sent");
                })
                .fail(function() {
                    console.error("Reset failed.");
                });

        };

        self.update_rpm = function()  {
            var data = {
                rpm: self.rpm()
            };

            OctoPrint.simpleApiCommand("roseengine", "update_rpm", data)
                .done(function(response) {
                    console.log("GCode written successfully.");
                })
                .fail(function() {
                    console.error("Failed to write GCode.");
                });


        };

        self.keyIsDown = function (data, event) {
            var button = undefined;
            var visualizeClick = true;
            var simulateTouch = false;

            switch (event.which) {
                case 37: // left arrow key
                    button = $("#ctrl-xdown");
                    simulateTouch = false;
                    break;
                case 38: // up arrow key
                    button = $("#ctrl-zdown");
                    simulateTouch = false;
                    break;
                case 39: // right arrow key
                    button = $("#ctrl-xup");
                    simulateTouch = false;
                    break;
                case 40: // down arrow key
                    button = $("#ctrl-zup");
                    simulateTouch = false;
                    break;
                case 50: // number 2
                case 98: // numpad 2
                    // Distance 0.1
                    button = $("#ctrl-distance-0");
                    simulateTouch = false;
                    break;
                case 51: // number 3
                case 99: // numpad 3
                    // Distance 1
                    button = $("#ctrl-distance-1");
                    simulateTouch = false;
                    break;
                case 52: // number 4
                case 100: // numpad 4
                    // Distance 5
                    button = $("#ctrl-distance-2");
                    simulateTouch = false;
                    break;
                case 53: // number 5
                case 101: // numpad 5
                    // Distance 10
                    button = $("#ctrl-distance-3");
                    simulateTouch = false;
                    break;
                case 54: // number 6
                case 102: // numpad 6
                    // Distance 50
                    button = $("#ctrl-distance-4");
                    simulateTouch = false;
                    break;
                case 55: // number 7
                case 103: // numpad 7
                    // Distance 100
                    button = $("#ctrl-distance-5");
                    simulateTouch = false;
                    break;

                default:
                    event.preventDefault();
                    return false;
            }
            console.log(button);
            if (button === undefined) {
                return false;
            } else {
                event.preventDefault();
                if (visualizeClick) {
                    button.addClass("active");
                    setTimeout(function () {
                        button.removeClass("active");
                    }, 150);
                }
                if (simulateTouch) {
                    console.log("pushing button");
                    button.mousedown();
                    setTimeout(function () {
                        button.mouseup();
                    }, 150);
                } else {
                    button.click();
                }
            }
                
            

        };

        $(document).ready(function() {
            $(this).keydown(function(e) {
                if (OctoPrint.coreui.selectedTab != undefined &&
                        OctoPrint.coreui.selectedTab == "#tab_plugin_roseengine" &&
                        OctoPrint.coreui.browserTabVisible && $(":focus").length == 0) {
                    self.keyIsDown(undefined, e);
                    
                }
            });
            //Clear on page reload
            self.clear_rosette("pump");
            self.clear_rosette("rock");

        });

    }

    OCTOPRINT_VIEWMODELS.push({
        construct: RoseengineViewModel,
        dependencies: ["settingsViewModel", "filesViewModel",  "accessViewModel","loginStateViewModel"],
        elements: [ "#tab_plugin_roseengine","#settings_plugin_roseengine" ]
    });
});
