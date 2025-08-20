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
        self.available = ko.observable(true); //Can we interact with this plugin
        self.running = ko.observable(false);
        self.is_printing = ko.observable(false);
        self.is_operational = ko.observable(false);
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
        self.s_amp = ko.observable(1.0);
        self.peak = ko.observable(1);
        self.pshift = ko.observable(0.0);
        self.wave_type = ko.observable(null);
        self.e_rad = ko.observable(10.0);
        self.e_ratio = ko.observable(1.0);
        self.b_adjust = ko.observable(0);
        self.bref = ko.observable(-90.0);



        //Recording
        self.recording  = ko.observable(false);
        self.lines = ko.observable(0); //number of lines written/stored


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
            self.is_printing(self.global_settings.settings.plugins.latheengraver.is_printing());
            self.is_operational(self.global_settings.settings.plugins.latheengraver.is_operational());
            //console.log(self.settings);
            self.fetchProfileFiles();
            self.a_inc = self.settings.a_inc();
            //console.log("binding self.a_inc")
            //console.log(self.a_inc);
            var po = $('#po_span');
            var po_slider = $('#pump_offset');
            po_slider.attr("step", self.a_inc);


            

        };

        self._processStateData = function(data) {
            
            self.is_printing(data.flags.printing);
            self.is_operational(data.flags.operational);
            self.isLoading(data.flags.loading);
            
            if (self.is_printing() && !self.running()) {
              self.available(false);
            }

            if(!self.is_printing() || self.running()) {
                self.available(true);
            }

            console.log(self.available());
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
            //console.log(rosette_info);
            var maxrad = isNaN(parseFloat(rosette_info.max))
                ? rosette_info.max
                : "r max=" + parseFloat(rosette_info.max).toFixed(2);
            var minrad = isNaN(parseFloat(rosette_info.min))
                ? rosette_info.min
                : "r min=" + parseFloat(rosette_info.min).toFixed(2);
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
                margin: {
                l: 30,
                r: 30,
                b: 10,
                t: 40,
                pad: 4
                },
                title: {
                    text: maxrad+'<br>'+minrad,
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
            Plotly.newPlot(area,[trace], layout,{displayModeBar: false});

        };

        self.onDataUpdaterPluginMessage = function(plugin, data) {

            if (plugin == 'roseengine' && data.seticon == 'rec') {
                var elem = $("#recpause");
                var icon = $("i", elem);
                if (icon.hasClass("fa-pause")) {
                    icon.removeClass("fa-pause").addClass("fa-play");
                    $("#recpause").removeClass("recording-effect");
                }
            }

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

        self.parametric_rosette = function(type) {
            
            var data = {
                type: type,
                amp: self.s_amp(),
                peak: self.peak(),
                phase: self.pshift(),
                wave_type: self.wave_type(),
            }
            
            OctoPrint.simpleApiCommand("roseengine", "parametric", data)
                .done(function(response) {
                    console.log("Parametric sent");
                })
                .fail(function() {
                    console.error("Parametric failed");
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

        self.record = function(operation) {
            var data = {
                op: operation,
            }

            if (operation === "start") {
                var elem = $("#recpause");
                var icon = $("i", elem);
                if (icon.hasClass("fa-play")) {
                    icon.removeClass("fa-play").addClass("fa-pause");
                    $("#recpause").addClass("recording-effect");
                } else {
                    icon.removeClass("fa-pause").addClass("fa-play");
                    $("#recpause").removeClass("recording-effect");
                }
            }

            OctoPrint.simpleApiCommand("roseengine", "recording", data)
                .done(function(response) {
                    console.log("recording command sent");
                    if (data.op == 'trash' || data.op == 'stop') {
                        self.recording = false;
                    }
                    
                    if (data.op == 'start' || self.recording() ) {
                        self.recording = false;
                    }

                    if (data.op == 'start' || !self.recording() ) {
                        self.recording = true;
                    }

                })
                .fail(function() {
                    console.error("Jog failed");
                });


        }

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

            self.fetchProfileFiles();

        };

        self.startjob = function() {

            var data = {
                rpm: self.rpm(),
                r_amp: self.r_amp(),
                p_amp: self.p_amp(),
                forward: self.forward(),
                pump_offset: self.pump_offset(),
                pump_invert: self.pump_invert(),
                e_rad: self.e_rad(),
                e_ratio: self.e_ratio(),
                b_adjust: self.b_adjust(),
                bref: self.bref(),

            };

            OctoPrint.simpleApiCommand("roseengine", "start_job", data)
                .done(function(response) {
                    console.log("Start sent");
                    self.running(true);
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
                    self.running(false);
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
                    console.log("RPM updated.");
                })
                .fail(function() {
                    console.error("Failed to update RPM");
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
            //Make the rock controls the same size as pump
            var pump_height = $('pump').outerHeight();
            $('#rock').height(pump_height);
            console.log("pump height:"+pump_height);

        });

    }

    OCTOPRINT_VIEWMODELS.push({
        construct: RoseengineViewModel,
        dependencies: ["settingsViewModel", "filesViewModel",  "accessViewModel","loginStateViewModel"],
        elements: [ "#tab_plugin_roseengine","#settings_plugin_roseengine" ]
    });
});
