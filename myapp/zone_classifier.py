from shapely.geometry import Point, Polygon
# Zone 1: Outer Zone
ZONE_1_POLY = Polygon([
    (106.8017998, -5.7360109),  # NW
    (106.8017998, -5.9500000),  # SW
    (107.0098827, -5.9500000),  # SE
    (107.0098827, -5.7360109)   # NE
])
# Zone 2: Waiting ZOne
ZONE_2_POLY = Polygon([
    (106.8017998, -5.9500000),  # NW
    (106.8017998, -6.1620722),  # SW
    (107.0098827, -6.1620722),  # SE
    (107.0098827, -5.9500000)   # NE
])
# 14 Berthing Zones
BERTHING_ZONES = [
    Polygon([(106.808955, -6.116746), (106.812119, -6.118700), (106.813216, -6.122455), (106.809758, -6.123178)]),
    Polygon([(106.864981, -6.112964), (106.870709, -6.110084), (106.871016, -6.110833), (106.865453, -6.113890)]),
    Polygon([(106.872741, -6.113826), (106.872097, -6.113813), (106.874645, -6.102099), (106.876431, -6.102282)]),
    Polygon([(106.879329, -6.093095), (106.882230, -6.093601), (106.881324, -6.098608), (106.879049, -6.098731)]),
    Polygon([(106.882634, -6.096039), (106.884124, -6.096143), (106.883865, -6.106432), (106.882170, -6.106362)]),
    Polygon([(106.884219, -6.095554), (106.886221, -6.095615), (106.886320, -6.096405), (106.884297, -6.096307)]),
    Polygon([(106.887001, -6.097435), (106.888284, -6.097517), (106.887949, -6.106564), (106.886664, -6.106537)]),
    Polygon([(106.888387, -6.096501), (106.890964, -6.096556), (106.890950, -6.097332), (106.888308, -6.097230)]),
    Polygon([(106.891018, -6.097515), (106.892722, -6.097529), (106.892453, -6.106858), (106.890691, -6.106784)]),
    Polygon([(106.892843, -6.096579), (106.904797, -6.097356), (106.904818, -6.097868), (106.892781, -6.097333)]),
    Polygon([(106.905147, -6.097799), (106.907761, -6.097646), (106.906876, -6.106920), (106.905252, -6.106710)]),
    Polygon([(106.909105, -6.097634), (106.914725, -6.098047), (106.914599, -6.098962), (106.908888, -6.098989)]),
    Polygon([(106.918930, -6.090441), (106.919958, -6.090297), (106.920175, -6.097994), (106.918623, -6.098120)]),
    Polygon([(106.969110, -6.071408), (106.970230, -6.071169), (106.974141, -6.084647), (106.972722, -6.084910)])
]

from shapely.geometry import Point

SPEED_THRESHOLDS = {
    "stop": 0.4,
    "maneuvering": 6,
    "approaching": 12,
    "arrival": 15
}

def classify_ship_status(lat, lon, speed, prev_phase=None):
    point = Point(lon, lat)
    print(f"[CLASSIFY] Ship at (lat: {lat}, lon: {lon}), speed: {speed}, prev_phase: {prev_phase}")

    # 1 Berthing Zones
    for i, poly in enumerate(BERTHING_ZONES):
        if poly.covers(point):
            if speed <= SPEED_THRESHOLDS["stop"]:
                print(f"→ Status: Berthing (Zone {i+1})")
                return "Berthing"
            else:
                print(f"→ Status: Maneuvering (Zone {i+1})")
                return "Maneuvering"

    # 2 Waiting Zone
    if ZONE_2_POLY.covers(point):
        if speed <= SPEED_THRESHOLDS["stop"]:
            print("→ Status: Anchoring (in Waiting Zone)")
            return "Anchoring"
        elif prev_phase in ["Berthing", "Maneuvering"]:
            print("→ Status: Departure (from Berthing into Waiting Zone)")
            return "Departure"
        else:
            print("→ Status: Approaching (in Waiting Zone)")
            return "Approaching"

    # 3 Outer Zone
    if ZONE_1_POLY.covers(point):
        if speed <= SPEED_THRESHOLDS["stop"]:
            print("→ Status: Postponed (in Outer Zone)")
            return "Postponed"
        elif prev_phase in ["Berthing", "Maneuvering"]:
            print("→ Status: Departure (from Berthing into Outer Zone)")
            return "Departure"
        else:
            print("→ Status: Arrival (in Outer Zone)")
            return "Arrival"

    # 4 Outside Port Area
    print("→ Status: Outside Port Area")
    return "Outside Port Area"