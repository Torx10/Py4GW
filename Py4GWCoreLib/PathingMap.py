import Py4GW
import PyImGui
import PyPathing
import math

from .Map import Map
from .Py4GWcorelib import Utils
from collections import defaultdict
from typing import Optional


class PathingMap:
    def __init__(self, zplane_filter: Optional[int] = None):
        self.map_boundaries = None
        self.pathing_map = []
        self.trapezoid_id_cache = defaultdict(list)
        self.precomputed_geometry = {}
        self.precomputed_geometry_bounds = None
        self.zplane_filter = zplane_filter
        self.quad_count = 0
        self.module_name = "PMapHandler"

    def _fetch_from_game(self):
        try:
            self.pathing_map = PyPathing.get_pathing_maps()
            self._update_boundaries(PyPathing.get_map_boundaries())
            self._cache_trapezoids()
        except Exception as e:
            Py4GW.Console.Log(self.module_name, f"Failed to fetch pathing data: {str(e)}", Py4GW.Console.MessageType.Error)

    def _update_boundaries(self, vec):
        if vec:
            self.map_boundaries = {
                "x_min": vec[1],
                "y_min": vec[2],
                "x_max": vec[3],
                "y_max": vec[4],
                "unk": vec[0]
            }
            
    def _should_skip_trapezoid(self, map_id, trapezoid):
        map_overrides = {
            116: lambda t: t.YT > 50000 or t.YB > 50000,  # Foible's Fair
            147: lambda t: t.ZPlane > 10,                # Ice Tooth Cave
            221: lambda t: t.YB < -20000,                # Vizunah Square (Foreign)
            # Add more known-bad maps here...
        }
        return map_overrides.get(map_id, lambda t: False)(trapezoid)
    
    def _cache_trapezoids(self):
        self.trapezoid_id_cache.clear()
        for layer in self.pathing_map:
            for trapezoid in layer.trapezoids:
                self.trapezoid_id_cache[layer.zplane].append(trapezoid)

    def scale_coords(self, x, y, width, height, boundaries):
        if not boundaries:
            raise ValueError("Map boundaries not initialized.")
        x_min, x_max = boundaries["x_min"], boundaries["x_max"]
        y_min, y_max = boundaries["y_min"], boundaries["y_max"]
        scale_x = (x - x_min) / (x_max - x_min) * width
        scale_y = (y - y_min) / (y_max - y_min) * height
        return scale_x, scale_y

    def precompute_geometry(self):
        self.precomputed_geometry.clear()
        self.quad_count = 0
        
        if not self.map_boundaries:
            return

        layers = [l for l in self.pathing_map if self.zplane_filter is None or l.zplane == self.zplane_filter]
        if not layers:
            return

        ref_layer = layers[0]
        self.precomputed_geometry_bounds = {
            "x_min": min(t.XTL for t in ref_layer.trapezoids),
            "x_max": max(t.XTR for t in ref_layer.trapezoids),
            "y_min": min(t.YB for t in ref_layer.trapezoids),
            "y_max": max(t.YT for t in ref_layer.trapezoids),
        }
        
        current_map_id = Map.GetMapID()
        for layer in layers:
            geometry = []
            for trap in layer.trapezoids:
                if self._should_skip_trapezoid(current_map_id, trap):
                    continue  # Skip broken trapezoid
                try:
                    geometry.append((
                        (trap.XTL, trap.YT),
                        (trap.XTR, trap.YT),
                        (trap.XBR, trap.YB),
                        (trap.XBL, trap.YB)
                    ))
                    self.quad_count += 1
                except Exception as e:
                    Py4GW.Console.Log(self.module_name, f"Trapezoid render error: {str(e)}", Py4GW.Console.MessageType.Warning)

            self.precomputed_geometry[layer.zplane] = geometry

    def get_geometry(self):
        return self.precomputed_geometry

    def get_quad_count(self):
        return self.quad_count

class PMapDraw:
    def __init__(self, pathing_map: PathingMap):
        self.pmap = pathing_map

    def _transform_world_to_canvas(self, x, y, center_x, center_y, player_x, player_y, zoom, rotation, invert_y):
        dx = x - player_x
        dy = y - player_y
        angle = -rotation + math.pi / 2
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        rx = dx * cos_a - dy * sin_a
        ry = dx * sin_a + dy * cos_a
        if invert_y:
            ry = -ry
        return center_x + rx * zoom, center_y + ry * zoom

    def draw(self, draw_list, width, height, zplane_color_fn=None,
            player_pos=None, rotation=0.0, zoom=1.0, invert_y=False):

        geometry = self.pmap.get_geometry()
        bounds = self.pmap.map_boundaries
        if not geometry or not bounds or player_pos is None:
            return

        px, py = player_pos
        center_x = width / 2
        center_y = height / 2

        for zplane, quads in geometry.items():
            color = zplane_color_fn(zplane) if zplane_color_fn else self.default_color(zplane)
            for quad in quads:
                try:
                    points = [
                        self._transform_world_to_canvas(x, y, center_x, center_y, px, py, zoom, rotation, invert_y)
                        for (x, y) in quad
                    ]
                    draw_list.draw_list_add_quad_filled(
                        points[0][0], points[0][1],
                        points[1][0], points[1][1],
                        points[2][0], points[2][1],
                        points[3][0], points[3][1],
                        color
                    )
                except Exception as e:
                    Py4GW.Console.Log("PMapDraw", f"Draw error: {e}", Py4GW.Console.MessageType.Warning)

    def default_color(self, zplane):
        if zplane == self._get_primary_zplane():
            return Utils.RGBToColor(160, 160, 160, 220)  # More opaque
        return Utils.RGBToColor(127, 191, 255, 220)
    
    def _get_primary_zplane(self):
        if self.pmap.pathing_map:
            return self.pmap.pathing_map[0].zplane
        return 0
