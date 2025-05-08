document.addEventListener("DOMContentLoaded", function () {
    // 💡 Define this globally to make sure map is accessible
    if (typeof map === "undefined") {
      console.error("Map is not defined. Make sure Leaflet map is initialized before loading this script.");
      return;
    }
  
    // 🟩 Port Boundary
    const portBoundary = [
      [-5.7360109, 106.8017998], // 1️⃣ NW
      [-5.7360109, 107.0098827], // 2️⃣ NE
      [-6.1620722, 107.0091395], // 3️⃣ SE
      [-6.1607633, 106.8017998]  // 4️⃣ SW
    ];
  
    L.polygon(portBoundary, {
      color: "black",
      weight: 1.3,
      dashArray: "4, 2",
      opacity: 0.6,
      fillOpacity: 0,
      interactive: false,
      pane: "overlayPane"
    }).addTo(map);  
  
    const trialZones = [
      {
          name: "Zone 1: Anchorage",
          coords: [
              [-5.7360109, 106.8017998],
              [-5.7360109, 107.0098827],
              [-5.9500000, 107.0098827],
              [-5.9500000, 106.8017998]
          ],
          color: "blue"
      },
      {
          name: "Zone 2: Fairway",
          coords: [
              [-5.9500000, 106.8017998],
              [-5.9500000, 107.0098827],
              [-6.1620722, 107.0091395],
              [-6.1607633, 106.8017998]
          ],
          color: "lime"
      }
  ];

  trialZones.forEach(zone => {
      L.polygon(zone.coords, {
          color: zone.color,
          fillColor: zone.color,
          fillOpacity: 0.10,
          interactive: false,
          pane: "overlayPane"
      }).addTo(map).bindPopup(zone.name);
  });

    // Zones
    const portZones = [  
      {
        name: "Waiting Zone",
        coords: [
        [-5.984867, 106.893072], // Waiting Zone 6 Coord 1
        [-5.984941, 106.926384], // Waiting Zone 6 Coord 2
        [-6.053075, 106.926548], // Waiting Zone 2 Coord 4
        [-6.058557, 106.893061]  // Waiting Zone 1 Coord 3
        ],
        color: "red"
      },
      {
        name: "Berthing Zone 1",
        coords: [
          [-6.116746, 106.808955],
          [-6.118700, 106.812119],
          [-6.122455, 106.813216],
          [-6.123178, 106.809758]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 2",
        coords: [
          [-6.112964, 106.864981],
          [-6.110084, 106.870709],
          [-6.110833, 106.871016],
          [-6.113890, 106.865453]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 3",
        coords: [
          [-6.113826, 106.872741],
          [-6.113813, 106.872097],
          [-6.102099, 106.874645],
          [-6.102282, 106.876431]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 4",
        coords: [
          [-6.093095, 106.879329],
          [-6.093601, 106.882230],
          [-6.098608, 106.881324],
          [-6.098731, 106.879049]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 5",
        coords: [
          [-6.096039, 106.882634],
          [-6.096143, 106.884124],
          [-6.106432, 106.883865],
          [-6.106362, 106.882170]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 6",
        coords: [
          [-6.095554, 106.884219],
          [-6.095615, 106.886221],
          [-6.096405, 106.886320],
          [-6.096307, 106.884297]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 7",
        coords: [
          [-6.097435, 106.887001],
          [-6.097517, 106.888284],
          [-6.106564, 106.887949],
          [-6.106537, 106.886664]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 8",
        coords: [
          [-6.096501, 106.888387],
          [-6.096556, 106.890964],
          [-6.097332, 106.890950],
          [-6.097230, 106.888308]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 9",
        coords: [
          [-6.097515, 106.891018],
          [-6.097529, 106.892722],
          [-6.106858, 106.892453],
          [-6.106784, 106.890691]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 10",
        coords: [
          [-6.096579, 106.892843],
          [-6.097356, 106.904797],
          [-6.097868, 106.904818],
          [-6.097333, 106.892781]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 11",
        coords: [
          [-6.097799, 106.905147],
          [-6.097646, 106.907761],
          [-6.106920, 106.906876],
          [-6.106710, 106.905252]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 12",
        coords: [
          [-6.097634, 106.909105],
          [-6.098047, 106.914725],
          [-6.098962, 106.914599],
          [-6.098989, 106.908888]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 13",
        coords: [
          [-6.090441, 106.918930],
          [-6.090297, 106.919958],
          [-6.097994, 106.920175],
          [-6.098120, 106.918623]
        ],
        color: "green"
      },
      {
        name: "Berthing Zone 14",
        coords: [
          [-6.071408, 106.969110],
          [-6.071169, 106.970230],
          [-6.084647, 106.974141],
          [-6.084910, 106.972722]
        ],
        color: "green"
      }
    ];
  
    portZones.forEach(zone => {
      L.polygon(zone.coords, {
        color: zone.color,
        fillColor: zone.color,
        fillOpacity: 0.2,
        interactive: false,  // 👈 prevents conflict with ship markers
        pane: "overlayPane"
      }).addTo(map);
    });
  
    console.log("✅ Port boundary + all zones loaded safely!");
  });  