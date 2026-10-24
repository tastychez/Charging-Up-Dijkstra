"""Tesla Supercharger sites between Boston and Dallas.

Coordinates are approximate locations of Supercharger sites along two corridors:
the southern route (I-84, I-81 down the Shenandoah Valley, I-40 across Tennessee and
Arkansas, I-30 into Texas) and a northern alternative (I-70 through Columbus,
Indianapolis and St. Louis, then I-44 and US-69 through Missouri and Oklahoma).
Real driving distances between them come from OSRM, see realmap.road_distances.
"""

START = "Boston, MA"
END = "Dallas, TX"

# name: (latitude, longitude)
STATIONS = {
    START:                  (42.360, -71.059),
    # Southern route: I-84 / I-81 / I-40 / I-30
    "Auburn, MA":           (42.194, -71.836),
    "Hartford, CT":         (41.764, -72.685),
    "Danbury, CT":          (41.394, -73.454),
    "Newburgh, NY":         (41.503, -74.010),
    "Scranton, PA":         (41.420, -75.630),
    "Hazleton, PA":         (40.958, -75.975),
    "Harrisburg, PA":       (40.273, -76.884),
    "Hagerstown, MD":       (39.642, -77.720),
    "Winchester, VA":       (39.186, -78.164),
    "Harrisonburg, VA":     (38.449, -78.869),
    "Roanoke, VA":          (37.271, -79.941),
    "Wytheville, VA":       (36.948, -81.085),
    "Bristol, TN":          (36.595, -82.189),
    "Knoxville, TN":        (35.961, -83.921),
    "Cookeville, TN":       (36.163, -85.502),
    "Nashville, TN":        (36.163, -86.781),
    "Jackson, TN":          (35.615, -88.814),
    "Memphis, TN":          (35.150, -90.049),
    "Forrest City, AR":     (35.008, -90.790),
    "Little Rock, AR":      (34.746, -92.290),
    "Arkadelphia, AR":      (34.121, -93.054),
    "Texarkana, TX":        (33.425, -94.048),
    "Sulphur Springs, TX":  (33.139, -95.601),
    # Northern alternative: I-70 / I-44 / US-69
    "Breezewood, PA":       (40.000, -78.243),
    "Washington, PA":       (40.174, -80.246),
    "Columbus, OH":         (39.961, -82.999),
    "Indianapolis, IN":     (39.768, -86.158),
    "Effingham, IL":        (39.120, -88.543),
    "St. Louis, MO":        (38.627, -90.199),
    "Rolla, MO":            (37.952, -91.771),
    "Springfield, MO":      (37.209, -93.292),
    "Joplin, MO":           (37.084, -94.513),
    "Tulsa, OK":            (36.154, -95.993),
    "McAlester, OK":        (34.933, -95.770),
    "Durant, OK":           (33.994, -96.371),
    END:                    (32.777, -96.797),
}
