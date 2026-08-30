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
        self.files = parameters[1];
        self.available = ko.observable(true);
        self.running = ko.observable(false);
        self.is_printing = ko.observable(false);
        self.is_operational = ko.observable(false);
        self.radii_rock = [];
        self.angles_rock = [];
        self.radii_pump = [];
        self.angles_pump = [];
        self.rpm = ko.observable(2);
        self.r_amp = ko.observable(1.0);
        self.p_amp = ko.observable(1.0);
        self.forward = ko.observable(true);
        self.dist = ko.observable(1.0);
        self.distances = ko.observableArray([.1, .2, .5, 1, 5, 10, 20, 30, 60, 90]);
        self.a_inc = ko.observable(0.5);
        self.bf_threshold = ko.observable(80);
        self.ms_threshold = ko.observable(10);
        self.chunk = ko.observable(5);

        self.need_reset = ko.observable(false);

        self.pump_offset = ko.observable(0.0);
        self.rock_offset = ko.observable(0);
        self.pump_invert = ko.observable(0);

        self.phase_offset = ko.observable(0);
        self.ecc_offset = ko.observable(0.0);
        self.s_amp = ko.observable(1.0);
        self.peak = ko.observable(1);
        self.pshift = ko.observable(0.0);
        self.wave_type = ko.observable(null);
        self.default_radius = ko.observable(20.0);
        self.e_rad = ko.observable(10.0);
        self.e_ratio = ko.observable(1.0);
        self.b_adjust = ko.observable(0);
        self.bref = ko.observable(-90.0);
        self.moveb = ko.observable(false);

        self.stages = ko.observableArray([]);
        self.geo_stages = ko.observable(2);
        self.geo_points = ko.observable(6000);
        self.saved_geos = ko.observableArray([]);
        self.radial_depth = ko.observable(0.0);
        self.target_radius = ko.observable(0.0);

        self.mm_rev = ko.observable(1.0);
        self.curve_stepdown = ko.observable(0.0);
        self.curvilinear = ko.observable(false);
        self.clutch = ko.observable(true);
        //self.curve_dir = ko.observable(1);
        self.curve_start = ko.observable(0);
        self.curve_stop = ko.observable(0);
        self.recip = ko.observable(true);
        self.helical = ko.observable(0.0);

        self.curve_retract = ko.observable(0.0);
        self.curve_retract_extra = ko.observable(0.0);
        self.r_radius = 0;
        self.r_stage = 0;
        self.r_phase = false;
        self.r_phase_v = 0;

        //Recording
        self.recording  = ko.observable(false);
        self.lines = ko.observable(0);
        self.relative_return = ko.observable(false);
        self.wm = false;

        //laser
        self.laser_base = ko.observable(200);
        self.laser_feed = ko.observable(200);
        self.laser_mode = ko.observable(0);

        //experimental
        self.exp = ko.observable(false);
        self.gcode_geo = ko.observable(false);

        tab = document.getElementById("tab_plugin_roseengine_link");
        tab.innerHTML = tab.innerHTML.replaceAll("Roseengine Plugin", "Rose Engine");

        self.fetchProfileFiles = function() {
            OctoPrint.files.listForLocation("local/scans", false)
                .done(function(data) {
                    var scans = data.children || [];
                    scans = scans.filter(function(f) {
                        return typeof f.name === "string" && f.name.startsWith("X");
                    });
                    populateFileSelector(scans, "#scan_pump_select", "machinecode");
                })
                .fail(function() {
                    console.error("Failed to fetch scan files");
                });
        };

        self.fetchCurveFiles = function() {
            OctoPrint.files.listForLocation("local/scans", false)
                .done(function(data) {
                    var scans = data.children || [];
                    scans = scans.filter(function(f) {
                        return typeof f.name === "string" && (f.name.endsWith("svg") || f.name.endsWith("dxf"));
                    });
                    populateFileSelector(scans, "#curve_select", "machinecode");
                })
                .fail(function() {
                    console.error("Failed to fetch scan files");
                });
        };

        self.fetchRosetteFiles = function() {
            OctoPrint.files.listForLocation("local/rosette", false)
                .done(function(data) {
                    var rosettes = data.children;
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
            fileSelector.append($("<option>").text("Select file").attr("value", "None"));
            files.forEach(function(file, i) {
                var option = $("<option>")
                    .text(file.display)
                    .attr("value", file.name)
                    .attr("download", file.refs.download)
                    .attr("path", file.path)
                    .attr("index", i);
                fileSelector.append(option);
            });
        }

        self.fetchSavedGeos = function() {
            OctoPrint.files.listForLocation("local/rosette", false)
                .done(function(data) {
                    var children = data && data.children ? data.children : [];
                    var savedFile = children.find(function(f) {
                        return f.name === "saved_geos.json";
                    });
                    if (!savedFile) {
                        console.log("No saved_geos.json found in uploads/rosette");
                        self.saved_geos([]);
                        return;
                    }

                    var downloadUrl = savedFile.refs && savedFile.refs.download;
                    if (!downloadUrl) {
                        console.log("Saved file has no download ref");
                        self.saved_geos([]);
                        return;
                    }

                    $.getJSON(downloadUrl)
                        .done(function(data) {
                            if (!Array.isArray(data)) {
                                console.log("saved_geos.json not an array");
                                data = [];
                            }
                            self.saved_geos(data);
                            var sel = $("#saved_geo_select");
                            if (sel.length) {
                                sel.empty();
                                sel.append($("<option>").text("Select saved geometric").attr("value",""));
                                data.forEach(function(entry, i) {
                                    var label = entry.timestamp ? entry.timestamp : ("entry " + i);
                                    sel.append($("<option>").text(label).attr("value", i));
                                });
                            }
                        })
                        .fail(function() {
                            console.log("Failed to download saved_geos.json");
                            self.saved_geos([]);
                        });
                })
                .fail(function() {
                    console.log("Failed to list uploads/rosette");
                    self.saved_geos([]);
                });
        };

        self.loadSavedGeo = function(index) {
            var idx = parseInt(index, 10);
            if (isNaN(idx)) return;
            var entry = self.saved_geos()[idx];
            if (!entry || !Array.isArray(entry.stages)) {
                console.error("Invalid saved geo entry");
                return;
            }

            var numStages = entry.stages.length;
            try {
                if (ko.isObservable(self.geo_stages)) {
                    self.geo_stages(numStages);
                }

                var current = self.stages() || [];
                if (current.length !== numStages) {
                    var stagesArr = [];
                    for (var i = 0; i < numStages; i++) {
                        stagesArr.push({
                            id: i,
                            radius: ko.observable(entry.stages[i].radius || 0),
                            p: ko.observable(entry.stages[i].p || 0),
                            q: ko.observable(entry.stages[i].q || 1),
                            phase: ko.observable(entry.stages[i].phase || 0)
                        });
                    }
                    self.stages(stagesArr);
                } else {
                    for (var j = 0; j < numStages; j++) {
                        var src = entry.stages[j];
                        var tgt = current[j];
                        if (tgt.radius && ko.isObservable(tgt.radius)) tgt.radius(src.radius || 0);
                        if (tgt.p && ko.isObservable(tgt.p)) tgt.p(src.p || 0);
                        if (tgt.q && ko.isObservable(tgt.q)) tgt.q(src.q || 1);
                        if (tgt.phase && ko.isObservable(tgt.phase)) tgt.phase(src.phase || 0);
                    }
                    self.stages.valueHasMutated();
                }

                if (entry.samples && ko.isObservable(self.geo_points)) {
                    self.geo_points(entry.samples);
                }

                var sel = $("#saved_geo_select");
                if (sel.length) {
                    sel.val(idx);
                }

            } catch (err) {
                console.error("Failed to populate KO values from saved geo:", err);
            }

            var stages = entry.stages.map(function(st) {
                return {
                    id: undefined,
                    radius: st.radius,
                    p: st.p,
                    q: st.q,
                    phase: st.phase
                };
            });
            var samples = entry.samples ? entry.samples : ko.unwrap(self.geo_points);
            OctoPrint.simpleApiCommand("roseengine", "geometric", { stages: stages, samples: samples })
                .done(function() {
                    console.log("Geometric data sent from saved entry");
                })
                .fail(function() {
                    console.error("Failed to send saved geometric");
                });
        };

        self.onBeforeBinding = function () {
            self.settings = self.global_settings.settings.plugins.roseengine;
            self.is_printing(self.global_settings.settings.plugins.latheengraver.is_printing());
            self.is_operational(self.global_settings.settings.plugins.latheengraver.is_operational());

            self.pump_profile = "None";
            self.curve_profile = "None";
            self.fetchSavedGeos();
            self.fetchProfileFiles();
            self.fetchCurveFiles();
            self.fetchRosetteFiles();

            // REMINDER: Use self.X(value) to SET an observable's value.
            //      Using self.X = value replaces the observable with a plain value,
            //      breaking all KO bindings and any code that calls self.X().
            self.a_inc(self.settings.a_inc());
            self.geo_stages(self.settings.geo_stages());
            self.geo_points(self.settings.geo_points());
            self.relative_return(self.settings.relative_return());
            self.mm_rev(self.settings.mm_rev());
            self.curve_stepdown(self.settings.curve_stepdown());
            self.curve_retract(self.settings.curve_retract());
            self.curve_retract_extra(self.settings.curve_retract_extra());
            self.exp(self.settings.exp());

            self.r_radius = self.settings.r_radius();
            self.r_stage = self.settings.r_stage();
            self.r_phase = self.settings.r_phase();
            self.r_phase_v = self.settings.r_phase_v();
            
            var numStages = parseInt(self.geo_stages(), 10); 
            var stagesArr = [];
            for (var i = 0; i < numStages; i++) {
                stagesArr.push({
                    id: i,
                    radius: ko.observable(0),
                    p: ko.observable(1),
                    q: ko.observable(1),
                    phase: ko.observable(0)
                });
            }
            self.stages(stagesArr);

            var po_slider = $('#pump_offset');
            po_slider.attr("step", self.a_inc()); 
        };

        self.fromCurrentData = function(data) {
            self._processStateData(data.state);
        };

        self.fromHistoryData = function(data) {
            self._processStateData(data.state);
        };

        self._processStateData = function(data) {
            self.is_printing(data.flags.printing);
            self.is_operational(data.flags.operational);

            if (self.is_printing() && !self.running()) {
                self.available(false);
            }

            if (!self.is_printing() || self.running()) {
                self.available(true);
            }
        };

        $("#saved_geo_select").on("change", function() {
            var val = $(this).val();
            if (val !== "") {
                self.loadSavedGeo(val);
            }
        });

        $("#saved_geo_select").on("contextmenu", function(e) {
            e.preventDefault();
            var val = $(this).val();
            if (val === "" || val === null) return;
            var entry = self.saved_geos()[parseInt(val, 10)];
            if (!entry) return;
            var currentName = entry.timestamp || ("entry " + val);
            var newName = prompt("Enter new name for this entry:", currentName);
            if (newName === null || newName.trim() === "") return;
            OctoPrint.simpleApiCommand("roseengine", "rename_geo", { index: parseInt(val, 10), name: newName.trim() })
                .done(function() {
                    console.log("Geo entry renamed");
                    self.fetchSavedGeos();
                })
                .fail(function() {
                    console.error("Failed to rename geo entry");
                });
            self.fetchSavedGeos();
        });

        $("#scan_pump_select").on("change", function () {
            var filePath = $("#scan_pump_select option:selected").attr("path");
            var val = $("#scan_pump_select option:selected").attr("value");
            if (!filePath) { val = "none"; }
            if (val === "none") { filePath = "None"; }
            self.pump_profile = filePath;
            console.log(self.pump_profile);
        });

        $("#curve_select").on("change", function () {
            self.curvilinear(false);
            var filePath = $("#curve_select option:selected").attr("path");
            var val = $("#curve_select option:selected").attr("value");
            if (!filePath) { val = "none"; }
            if (val === "none") { filePath = "None"; }
            self.curve_profile = filePath;
            console.log(self.curve_profile);
            if (filePath != "None") {
                self.load_curve(filePath);
                self.curvilinear(true);
            }
        });

        $("#rock_file_select").on("click", function () {
            var filePath = $("#rock_file_select option:selected").attr("path");
            self.name = $("#rock_file_select option:selected").attr("value");
            if (!filePath) return;
            self.load_rosette(filePath, "rock");
        });

        $("#pump_file_select").on("click", function () {
            var filePath = $("#pump_file_select option:selected").attr("path");
            self.name = $("#pump_file_select option:selected").attr("value");
            if (!filePath) return;
            self.load_rosette(filePath, "pump");
        });

        $("#rpm").on("change", function() {
            self.update_rpm();
        });

        $("#moveb").on("change", function() {
            self.update_rpm();
        });

        $("#rockarea").on("click", function() {
            var plotDiv = document.getElementById('rockarea');
            var plotData = plotDiv.data;
            var plotLayout = plotDiv.layout;
            var win = window.open("", "LargeRock", "width=1000,height=800");
            win.document.body.innerHTML = '<div id="largeplot" style="width:900px;height:700px;"></div>';
            var script = win.document.createElement('script');
            script.src = "/plugin/roseengine/static/js/plotly-latest.min.js";
            script.onload = function() {
                win.Plotly.newPlot('largeplot', plotData, plotLayout, {displayModeBar: false});
            };
            win.document.head.appendChild(script);
        });

        $("#pumparea").on("click", function() {
            var plotDiv = document.getElementById('pumparea');
            var plotData = plotDiv.data;
            var plotLayout = plotDiv.layout;
            var win = window.open("", "LargePump", "width=1000,height=800");
            win.document.body.innerHTML = '<div id="largeplot2" style="width:900px;height:700px;"></div>';
            var script = win.document.createElement('script');
            script.src = "/plugin/roseengine/static/js/plotly-latest.min.js";
            script.onload = function() {
                win.Plotly.newPlot('largeplot2', plotData, plotLayout, {displayModeBar: false});
            };
            win.document.head.appendChild(script);
        });

        self.special_warning = function(a, b) {
            var area = b + 'area';
            if (a === "off") {
                $('#' + area).removeClass("shadow-effect");
            } else {
                $('#' + area).addClass("shadow-effect");
            }
        };

        self.distClicked = function(distance) {
            console.log(distance);
            self.dist(parseFloat(distance));
        };

        self.distRightClicked = function(distance, event) {
            event.preventDefault();
            event.stopPropagation();
            var current = distance;
            var input = prompt("Enter new distance value:", current);
            if (input === null) return;
            var val = parseFloat(input);
            if (isNaN(val) || val <= 0) {
                alert("Please enter a valid positive number.");
                return;
            }
            var arr = self.distances();
            var idx = arr.indexOf(current);
            if (idx !== -1) {
                arr[idx] = val;
                self.distances(arr.slice());
            }
            self.dist(val);
            return false;
        };

        self.onEventPLUGIN_LATHEENGRAVER_SEND_LASER = function(payload) {
            console.log("Got laser event");
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

            if (plugin == 'roseengine' && data.reset == 'reset') {
                self.need_reset(false);
                return;
            }

            if (plugin == 'roseengine' && data.type == 'rock') {
                self.radii_rock = data.radii;
                self.angles_rock = data.angles;
                self.special = data.special;
                Plotly.newPlot('rockarea', data.graph.data, data.graph.layout, {displayModeBar: false});
                if (self.special) {
                    self.special_warning("on", "rock");
                } else {
                    self.special_warning("off", "rock");
                }
            }

            if (plugin == 'roseengine' && data.type == 'geo') {
                console.log(data.graph);
                Plotly.newPlot('rockarea', data.graph.data, data.graph.layout, {displayModeBar: false});
            }

            if (plugin == 'roseengine' && data.type == 'curve') {
                const plotDiv = document.getElementById('pumparea');

                Plotly.newPlot(plotDiv, data.graph.data, data.graph.layout, {
                    displayModeBar: false,
                    edits: { shapePosition: true }
                });

                // Default x values from the initial shapes
                let startX = plotDiv._fullLayout.shapes[0].x0.toFixed(1);
                let endX   = plotDiv._fullLayout.shapes[1].x0.toFixed(1);

                // --- Reuse or create label container (avoid duplicates on reload) ---
                let labelContainer = document.getElementById('curve-marker-labels');
                if (!labelContainer) {
                    labelContainer = document.createElement('div');
                    labelContainer.id = 'curve-marker-labels';
                    labelContainer.style.cssText = 'display:flex; gap:16px; font-size:13px; margin-bottom:2px; padding-left:4px;';

                    const startLabel = document.createElement('span');
                    startLabel.id = 'curve-label-start';
                    startLabel.style.color = 'green';

                    const endLabel = document.createElement('span');
                    endLabel.id = 'curve-label-end';
                    endLabel.style.color = 'red';

                    labelContainer.appendChild(startLabel);
                    labelContainer.appendChild(endLabel);
                    plotDiv.parentNode.insertBefore(labelContainer, plotDiv);
                }

                function updateLabels() {
                    document.getElementById('curve-label-start').innerHTML = `<b>Start:</b> ${startX}`;
                    document.getElementById('curve-label-end').innerHTML   = `<b>Stop:</b> ${endX}`;
                    self.curve_start(startX);
                    self.curve_stop(endX);
                }

                updateLabels();

                // --- Update labels when markers are dragged ---
                // Remove any prior listener by replacing the div's plotly binding
                plotDiv.removeAllListeners('plotly_relayout');
                plotDiv.on('plotly_relayout', function (eventData) {
                    if ('shapes[0].x0' in eventData) {
                        startX = parseFloat(eventData['shapes[0].x0']).toFixed(1);
                    }
                    if ('shapes[1].x0' in eventData) {
                        endX = parseFloat(eventData['shapes[1].x0']).toFixed(1);
                    }
                    updateLabels();
                });
            }

            if (plugin == 'roseengine' && data.type == 'pump') {
                self.radii_pump = data.radii;
                self.angles_pump = data.angles;
                self.special = data.special;
                Plotly.newPlot('pumparea', data.graph.data, data.graph.layout, {displayModeBar: false});
                if (self.special) {
                    self.special_warning("on", "pump");
                } else {
                    self.special_warning("off", "pump");
                }
            }

            if (plugin == 'roseengine' && data.func == 'refresh') {
                self.fetchProfileFiles();
                self.fetchRosetteFiles();
                self.fetchSavedGeos();
            }

            if (plugin == 'roseengine' && (data.laser === false || data.laser === true)) {
                self.laser_mode(data.laser);
            }
        };

        self.send_error_message = function(message) {
            OctoPrint.simpleApiCommand("latheengraver", "send_error_message", { message: message })
                .done(function(response) {
                    console.log("Error message sent");
                })
                .fail(function() {
                    console.error("Error message not sent");
                });
        };

        self.load_curve = function(filePath) {
            var data = {
                path: filePath,
                mm_rev: self.mm_rev(),
            };

            OctoPrint.simpleApiCommand("roseengine", "curve", data)
                .done(function(response) {
                    console.log("Curvilinear sent");
                })
                .fail(function() {
                    console.error("Curvilinear failed");
                });
        };

        self.toggle_clutch = function() {
            self.clutch(!self.clutch());
            self.update_rpm();
        };

        self.parametric_rosette = function(type) {
            var data = {
                type: type,
                amp: self.s_amp(),
                peak: self.peak(),
                phase: self.pshift(),
                wave_type: self.wave_type(),
                r_amp: self.r_amp(),
                p_amp: self.p_amp(),
                ecc_offset: self.ecc_offset(),
                default_radius: self.default_radius(),
            };

            OctoPrint.simpleApiCommand("roseengine", "parametric", data)
                .done(function(response) {
                    console.log("Parametric sent");
                })
                .fail(function() {
                    console.error("Parametric failed");
                });
        };

        self.save_geo = function() {
            OctoPrint.simpleApiCommand("roseengine", "save_geo")
                .done(function(response) {
                    console.log("Geometric data saved");
                })
                .fail(function() {
                    console.error("Save failed");
                });
        };

        self.create_geo = function(randomize) {
            var total_radius = 0;
            var stages_data = self.stages().map(function(stage, idx) {
                var spq = (self.r_stage * 2) + 1;
                if (randomize) {
                    var radius = Math.floor(Math.random() * self.r_radius) + 1;
                    var p = Math.floor(Math.random() * spq) - self.r_stage;
                    var q = Math.floor(Math.random() * spq) - self.r_stage;
                    var phase = self.r_phase ? (Math.floor(Math.random() * self.r_phase_v) + 1) : 0;

                    stage.radius(radius);
                    stage.p(p);
                    stage.q(q);
                    stage.phase(phase);
                    total_radius += radius;
                    return { id: stage.id, radius: radius, p: p, q: q, phase: phase };
                } else {
                    var r = ko.unwrap(stage.radius);
                    total_radius += (typeof r === "number" ? r : parseFloat(r) || 0);
                    return {
                        id: stage.id,
                        radius: ko.unwrap(stage.radius),
                        p: ko.unwrap(stage.p),
                        q: ko.unwrap(stage.q),
                        phase: ko.unwrap(stage.phase)
                    };
                }
            });

            var scale = (total_radius !== 0 && self.target_radius() > 0) ? (self.target_radius() / total_radius) : 1.0;
            stages_data = stages_data.map(function(st, i) {
                var scaled = Object.assign({}, st);
                scaled.radius = parseFloat(st.radius) * scale;
                var stageObs = self.stages()[i];
                if (stageObs && ko.isObservable(stageObs.radius)) {
                    stageObs.radius(scaled.radius);
                }
                return scaled;
            });

            // FIX: self.geo_points is an observable — unwrap it with ()
            OctoPrint.simpleApiCommand("roseengine", "geometric", { stages: stages_data, samples: self.geo_points() })
                .done(function(response) {
                    console.log("Geometric data sent");
                })
                .fail(function() {
                    console.error("Geometric failed");
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

        self.toggle_laser = function() {
            OctoPrint.simpleApiCommand("roseengine", "laser")
                .done(function(response) {
                    console.log("Laser toggle sent");
                })
                .fail(function() {
                    console.error("Laser toggle failed");
                });
        };

        self.write_mode = function() {
            self.wm = true;
            self.startjob();
            self.wm = false;
            self.files.requestData({ force: true });
        };

        self.record = function(operation) {
            var data = { op: operation };

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
                        self.recording(false);
                    }
                    if (data.op == 'start' || self.recording()) {
                        self.recording(false);
                    }
                    if (data.op == 'start' || !self.recording()) {
                        self.recording(true);
                    }
                })
                .fail(function() {
                    console.error("Record command failed");
                });
        };

        self.load_rosette = function(filePath, type) {
            var data = {
                filepath: filePath,
                type: type,
                ecc_offset: self.ecc_offset(),
                r_amp: self.r_amp(),
                p_amp: self.p_amp(),
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
            OctoPrint.simpleApiCommand("roseengine", "clear", { type: type })
                .done(function(response) {
                    console.log("Clear transmitted");
                    var toclear = '#' + type + 'area';
                    $(toclear).empty();
                })
                .fail(function() {
                    console.error("clear failed");
                });

            self.fetchProfileFiles();
            self.fetchCurveFiles();
            self.fetchRosetteFiles();
        };

        self.geo_gcode = function() {
            self.gcode_geo(true);
            self.startjob();
            self.files.requestData({ force: true });
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
                moveb: self.moveb(),
                laser_base: self.laser_base(),
                laser_feed: self.laser_feed(),
                radial_depth: self.radial_depth(),
                pump_profile: self.pump_profile,
                gcode_geo: self.gcode_geo(),
                wm: self.wm,
                //curve_dir: self.curve_dir(),
                curve_start: self.curve_start(),
                curve_stop: self.curve_stop(),
                recip: self.recip(),
                helical: self.helical(),
                curve_retract: self.curve_retract(),
                curve_retract_extra: self.curve_retract_extra(),
                curve_stepdown: self.curve_stepdown(),   
                mm_rev: self.mm_rev(),                   
            };

            OctoPrint.simpleApiCommand("roseengine", "start_job", data)
                .done(function(response) {
                    console.log("Start sent");
                    self.running(true);
                    self.need_reset(true);
                })
                .fail(function() {
                    console.error("Start failed");
                });

            self.gcode_geo(false);
        };

        self.stopjob = function() {
            OctoPrint.simpleApiCommand("roseengine", "stop_job", { stop: true })
                .done(function(response) {
                    console.log("Stop sent");
                    self.running(false);
                })
                .fail(function() {
                    console.error("Stop failed");
                });
        };

        self.gotostart = function() {
            OctoPrint.simpleApiCommand("roseengine", "goto_start", { reset: true })
                .done(function(response) {
                    console.log("Reset sent");
                    self.need_reset(false);
                })
                .fail(function() {
                    console.error("Reset failed.");
                });
        };

        self.update_rpm = function() {
            var data = {
                rpm: self.rpm(),
                moveb: self.moveb(),
                clutch: self.clutch(),
            };

            OctoPrint.simpleApiCommand("roseengine", "update_rpm", data)
                .done(function(response) {
                    console.log("RPM updated.");
                })
                .fail(function() {
                    console.error("Failed to update RPM");
                });
        };

        self.keyIsDown = function(data, event) {
            var button = undefined;
            var visualizeClick = true;
            var simulateTouch = false;

            switch (event.which) {
                case 37: button = $("#ctrl-xdown"); break;
                case 38: button = $("#ctrl-zdown"); break;
                case 39: button = $("#ctrl-xup"); break;
                case 40: button = $("#ctrl-zup"); break;
                case 50: case 98:  button = $("#ctrl-distance-0"); break;
                case 51: case 99:  button = $("#ctrl-distance-1"); break;
                case 52: case 100: button = $("#ctrl-distance-2"); break;
                case 53: case 101: button = $("#ctrl-distance-3"); break;
                case 54: case 102: button = $("#ctrl-distance-4"); break;
                case 55: case 103: button = $("#ctrl-distance-5"); break;
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
                    setTimeout(function() { button.removeClass("active"); }, 150);
                }
                if (simulateTouch) {
                    button.mousedown();
                    setTimeout(function() { button.mouseup(); }, 150);
                } else {
                    button.click();
                }
            }
        };

        self.onTabChange = function(current, previous) {
            if (current === "#tab_plugin_roseengine") {
                if (self.pump_profile === "None") { self.fetchProfileFiles(); }
                self.fetchRosetteFiles();
                self.fetchSavedGeos();
                self.fetchCurveFiles();
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
            self.clear_rosette("pump");
            self.clear_rosette("rock");
            var pump_height = $('pump').outerHeight();
            $('#rock').height(pump_height);
            console.log("pump height:" + pump_height);
        });

    }

    OCTOPRINT_VIEWMODELS.push({
        construct: RoseengineViewModel,
        dependencies: ["settingsViewModel", "filesViewModel", "accessViewModel", "loginStateViewModel"],
        elements: ["#tab_plugin_roseengine"]
    });
});
