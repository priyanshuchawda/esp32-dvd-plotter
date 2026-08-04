// Parametric frame for the ESP32 / DVD-drive pen plotter.
//
// Every dimension below is a starting estimate. Measure your own salvaged
// sleds and edit the values before cutting or printing anything.
//
//   openscad -D 'part="assembly"' -o out.png  cad/plotter.scad
//   openscad -D 'part="pen_lift"' -o pen.stl  cad/plotter.scad

part = "assembly"; // [assembly, pen_lift, paper_bed, gantry_upright]

/* [Measured DVD sled] */
sled_length      = 130;  // full length of the salvaged metal chassis
sled_width       = 42;
sled_height      = 12;
sled_travel      = 38;   // usable carriage travel, drives the drawing area
carriage_length  = 30;
carriage_width   = 26;

/* [Frame] */
base_x           = 200;
base_y           = 190;
base_thickness   = 6;
upright_thickness = 6;
upright_width    = 26;

/* [Paper bed] */
bed_x            = 70;
bed_y            = 70;
bed_thickness     = 3;

/* [SG90 servo] */
servo_body_x     = 23.0;
servo_body_y     = 12.2;
servo_body_z     = 22.5;
servo_tab_span   = 32.5;
servo_tab_z      = 4.0;
servo_tab_thick  = 2.5;

/* [Pen] */
pen_diameter     = 10.0;
pen_clearance    = 0.4;
pen_plate_x      = 30;   // bracket back plate width
pen_tube_height  = 20;   // vertical guide the pen slides in
pen_gap          = 8;    // guide sits this far above the paper
pen_mount_zone   = 12;   // clear strip at the top for the carriage screws

/* [Print] */
wall             = 2.4;
$fn              = 48;

// Bracket geometry, derived so the three zones cannot overlap: guide tube at
// the bottom, servo cradle above it, bare screw strip at the top.
pen_bore     = pen_diameter + pen_clearance;
pen_axis_x   = pen_plate_x / 2;
// Sunk half a wall into the plate. Sitting it exactly against the face would
// make the tube tangent to the plate, which is not a manifold solid.
pen_axis_y   = wall / 2 + (pen_bore + 2 * wall) / 2;
cradle_h     = servo_body_z + 2 * wall;
cradle_z     = pen_tube_height + 4;
pen_plate_z  = cradle_z + cradle_h + pen_mount_zone;

// Height of the paper surface above the table.
bed_top          = base_thickness + sled_height + 4 + bed_thickness;
// The bracket bolts to the top of the X carriage and hangs down, so the rail
// height follows from the bracket rather than being guessed. Solving for
// "guide bottom sits pen_gap above the paper" keeps the two consistent when
// any sled dimension is edited.
carriage_top_off = sled_height + 4;
gantry_height    = bed_top + pen_plate_z + pen_gap - carriage_top_off;
carriage_top     = gantry_height + carriage_top_off;

module sled(travel_marker = false) {
    color("#9aa4ad") cube([sled_length, sled_width, sled_height]);
    color("#3d6fd8")
        translate([(sled_length - carriage_length) / 2,
                   (sled_width - carriage_width) / 2,
                   sled_height])
        cube([carriage_length, carriage_width, 4]);
    if (travel_marker)
        color("#d8a13d", 0.35)
            translate([(sled_length - sled_travel) / 2, 0, sled_height + 4])
            cube([sled_travel, sled_width, 0.6]);
}

module base_plate() {
    color("#c8b48a") cube([base_x, base_y, base_thickness]);
}

// Deliberately solid: paper needs continuous support right to the edges.
module paper_bed() {
    cube([bed_x, bed_y, bed_thickness]);
}

module gantry_upright() {
    difference() {
        cube([upright_width, upright_thickness, gantry_height]);
        // Slot lets the gantry height be trimmed after the bed is measured.
        translate([upright_width / 2, -1, gantry_height - 26])
            rotate([-90, 0, 0])
            hull() {
                cylinder(d = 4.5, h = upright_thickness + 2);
                translate([0, 16, 0]) cylinder(d = 4.5, h = upright_thickness + 2);
            }
    }
}

// Bracket that bolts to the X carriage. The pen slides vertically in a guide
// tube; a rubber band pulls it down onto the paper and the servo horn pushes
// a collar on the pen upward to lift it. Origin is the bottom of the guide.
module pen_lift() {
    difference() {
        union() {
            cube([pen_plate_x, wall, pen_plate_z]);

            // Guide tube, braced back to the plate.
            translate([pen_axis_x, pen_axis_y, 0])
                cylinder(d = pen_bore + 2 * wall, h = pen_tube_height);
            hull() {
                translate([pen_axis_x, pen_axis_y, 0])
                    cylinder(d = pen_bore + 2 * wall, h = 3);
                cube([pen_plate_x, wall, 3]);
            }

            // Servo cradle. Starts inside the plate so the union is solid
            // rather than two bodies meeting on a shared face.
            translate([(pen_plate_x - servo_body_x) / 2 - wall, 0, cradle_z])
                difference() {
                    cube([servo_body_x + 2 * wall,
                          wall + servo_body_y + wall,
                          cradle_h]);
                    translate([wall, wall, wall])
                        cube([servo_body_x, servo_body_y, cradle_h]);
                }

            // Rubber-band anchor, rooted in the plate so it is not a
            // free-floating body.
            translate([3, 0, pen_tube_height - 5])
                rotate([-90, 0, 0]) cylinder(d = 4, h = wall + 5);
        }

        // Pen bore, open top and bottom so the pen can protrude.
        translate([pen_axis_x, pen_axis_y, -1])
            cylinder(d = pen_bore, h = pen_tube_height + 2);

        // Mounting holes onto the DVD carriage, in the clear top strip.
        for (x = [5, pen_plate_x - 5])
            translate([x, -1, pen_plate_z - pen_mount_zone / 2])
                rotate([-90, 0, 0]) cylinder(d = 3.2, h = wall + 2);
    }
}

// The two axes must be perpendicular: the Y sled runs front-to-back carrying
// the paper, the X sled runs left-to-right overhead carrying the pen.
y_sled_x0 = (base_x - sled_width) / 2;
y_sled_y0 = (base_y - sled_length) / 2;
x_sled_x0 = (base_x - sled_length) / 2;
x_sled_y0 = (base_y - sled_width) / 2;

module assembly() {
    base_plate();

    // Y axis, long axis along Y.
    translate([y_sled_x0 + sled_width, y_sled_y0, base_thickness])
        rotate([0, 0, 90]) sled(travel_marker = true);
    translate([(base_x - bed_x) / 2, (base_y - bed_y) / 2,
               base_thickness + sled_height + 4])
        color("#f2efe6") paper_bed();

    // Uprights stand under the two ends of the X rail, and must clear the
    // full width of the Y sled between them.
    for (x = [x_sled_x0 + 4, x_sled_x0 + sled_length - upright_width - 4])
        translate([x, (base_y - upright_thickness) / 2, base_thickness])
            color("#c8b48a") gantry_upright();

    // X axis, long axis along X, sitting on the uprights.
    translate([x_sled_x0, x_sled_y0, gantry_height])
        sled(travel_marker = true);

    // Pen bracket bolts to the X carriage and hangs toward the operator.
    translate([base_x / 2 - pen_plate_x / 2, x_sled_y0 - wall,
               carriage_top - pen_plate_z])
        color("#4fb06a") pen_lift();

    // The pen itself, shown reaching the paper.
    color("#22252b")
        translate([base_x / 2, x_sled_y0 - wall + pen_axis_y, bed_top])
        cylinder(d = pen_diameter, h = pen_gap + pen_tube_height + 12);
}

if      (part == "assembly")        assembly();
else if (part == "pen_lift")        pen_lift();
else if (part == "paper_bed")       paper_bed();
else if (part == "gantry_upright")  gantry_upright();
