from Py4GWCoreLib import *
from Py4GWCoreLib.PathingMap import PathingMap, PMapDraw

module_name = "Minimap"

class config:
    def __init__(self):
        self.minimap_enabled = True
        self.zoom = 0.03
        self.last_smoothed_yaw = 0.0
        self.rotation_mode = 1  # 0 = Smooth, 1 = Instant
        self.shape_mode = 0  # 0 = Square, 1 = Circle
        self.last_map_id = -1
        self.agent_cache: list[dict] = []
        self.agent_cache_time = 0.0  # last update time
        self.canvas_width = 0.0
        self.canvas_height = 0.0

        
        self._debug_invert_y = True  # Debug-only toggle (default ON to match toolbox)
        
        
config_var = config()
config_window = ImGui.WindowModule(f"Config {module_name}", window_name="Minimap", window_size=(100, 100), window_flags=PyImGui.WindowFlags.AlwaysAutoResize)

minimap_window_flags = (
    PyImGui.WindowFlags.NoTitleBar |
    PyImGui.WindowFlags.NoResize |
    PyImGui.WindowFlags.NoScrollbar |
    PyImGui.WindowFlags.NoScrollWithMouse |
    PyImGui.WindowFlags.NoCollapse |
    PyImGui.WindowFlags.NoBackground |
    PyImGui.WindowFlags.NoSavedSettings
)

pathing_map = PathingMap(zplane_filter=None)
pmap_draw = PMapDraw(pathing_map)

AGENT_COLORS = {
    "eoe": Utils.RGBToColor(0, 255, 0, 50),                # EoE (semi-transparent green)
    "qz": Utils.RGBToColor(0, 0, 255, 50),                 # QZ (semi-transparent blue)
    "winnowing": Utils.RGBToColor(0, 255, 255, 50),        # Winnowing (cyan)
    "target": Utils.RGBToColor(255, 255, 0, 255),          # Target (Yellow)
    "player": Utils.RGBToColor(255, 128, 0, 255),          # Player alive
    "player_dead": Utils.RGBToColor(255, 128, 0, 100),     # Player dead (translucent)
    "signpost": Utils.RGBToColor(0, 0, 200, 255),          # Signpost (Blue)
    "item": Utils.RGBToColor(0, 0, 240, 255),              # Item (Bright Blue)
    "enemy": Utils.RGBToColor(255, 0, 0, 255),             # Hostile >90%
    "enemy_dead": Utils.RGBToColor(50, 0, 0, 255),         # Hostile dead (Dark red)
    "neutral": Utils.RGBToColor(0, 0, 220, 255),           # Neutral (Deep blue)
    "ally_player": Utils.RGBToColor(153, 255, 153, 255),   # Ally (player)
    "ally_npc": Utils.RGBToColor(153, 255, 153, 255),      # Ally (NPC)
    "ally_npc_quest": Utils.RGBToColor(96, 128, 0, 255),   # Ally (Quest Giver)
    "ally_spirit": Utils.RGBToColor(0, 128, 96, 255),      # Ally (spirit)
    "ally_minion": Utils.RGBToColor(0, 100, 0, 255),       # Ally (minion)
    "ally_dead": Utils.RGBToColor(0, 128, 128, 100),       # Ally dead (translucent teal)
    "modifier": Utils.RGBToColor(30, 30, 30, 0),           # Agent modifier
    "modifier_damaged": Utils.RGBToColor(80, 0, 80, 0),    # Damaged modifier
    "marked_target": Utils.RGBToColor(255, 252, 0, 255),   # Marked target (neon yellow)
}

def get_profession_color(prof):
    # Based on GWToolbox border colors
    colors = {
        1:  Utils.RGBToColor(234, 163,   0, 255),  # Warrior - #EA3
        2:  Utils.RGBToColor( 85, 160,   0, 255),  # Ranger  - #5A0
        3:  Utils.RGBToColor( 68,  68, 187, 255),  # Monk    - #44B
        4:  Utils.RGBToColor(  0, 170,  85, 255),  # Necro   - #0A5
        5:  Utils.RGBToColor(128,   0, 170, 255),  # Mesmer  - #80A
        6:  Utils.RGBToColor(187,  51,  51, 255),  # Ele     - #B33
        7:  Utils.RGBToColor(170,   0, 136, 255),  # Assassin- #A08
        8:  Utils.RGBToColor(  0, 170, 170, 255),  # Ritualist-#0AA
        9:  Utils.RGBToColor(153,  96,   0, 255),  # Paragon - #960
        10: Utils.RGBToColor(119, 119, 204, 255),  # Dervish - #77C
    }
    return colors.get(prof, Utils.RGBToColor(102, 102, 102, 255)) 

def lerp_angle(a, b, t):
    delta = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + delta * t

def rotate_and_transform(dx, dy, cos_a, sin_a, flip_y):
    rx = dx * cos_a - dy * sin_a
    ry = dx * sin_a + dy * cos_a
    ry *= flip_y
    return rx, ry

def draw_player_circle(center_x, center_y):
    is_alive = Agent.IsAlive(Player.GetAgentID())
    
    color = AGENT_COLORS["player"] if is_alive else AGENT_COLORS["player_dead"]
    
    PyImGui.draw_list_add_circle_filled(
        center_x,
        center_y,
        2.2,
        color,
        16
    )

MAX_AGENT_RENDER_DISTANCE = 5000
AGENT_CACHE_REFRESH_INTERVAL = 0.2

def is_low_priority(agent):
    return Agent.IsMinion(agent) or Agent.IsSpirit(agent)

def get_agent_draw_color(agent, is_alive, is_boss):
    if is_boss:
        prof, _ = Agent.GetProfessionIDs(agent)
        return get_profession_color(prof) if is_alive else AGENT_COLORS["enemy_dead"]

    allegiance = Agent.GetAllegiance(agent)[0]
    if allegiance == Allegiance.Enemy.value:
        return AGENT_COLORS["enemy"] if is_alive else AGENT_COLORS["enemy_dead"]
    if allegiance == Allegiance.Ally.value:
        return AGENT_COLORS["ally_npc"] if is_alive else AGENT_COLORS["ally_dead"]
    if allegiance == Allegiance.SpiritPet.value:
        return AGENT_COLORS["ally_spirit"]
    if allegiance == Allegiance.Minion.value:
        return AGENT_COLORS["ally_minion"]
    if allegiance == Allegiance.NpcMinipet.value:
        return AGENT_COLORS["ally_npc"] if is_alive else AGENT_COLORS["ally_dead"]
    return AGENT_COLORS["neutral"]

def draw_all_agents(center_x, center_y, player_x, player_y, zoom, rotation_angle, invert_y):
    now = time.time()
    cache_expired = now - config_var.agent_cache_time > AGENT_CACHE_REFRESH_INTERVAL

    if cache_expired:
        config_var.agent_cache_time = now
        config_var.agent_cache.clear()

        try:
            for agent in AgentArray.GetAgentArray():
                if agent == Player.GetAgentID():
                    continue
                config_var.agent_cache.append({
                    "agent": agent,
                    "alive": Agent.IsAlive(agent),
                    "boss": Agent.HasBossGlow(agent),
                    "x": Agent.GetXY(agent)[0],
                    "y": Agent.GetXY(agent)[1],
                })
        except:
            return

    flip_y = -1 if config_var._debug_invert_y else 1
    cos_a = math.cos(-rotation_angle + math.pi / 2)
    sin_a = math.sin(-rotation_angle + math.pi / 2)
    half_width = config_var.canvas_width / 2
    half_height = config_var.canvas_height / 2
    
    for entry in config_var.agent_cache:
        agent = entry["agent"]
        x = entry["x"]
        y = entry["y"]
        is_alive = entry["alive"]
        is_boss = entry["boss"]

        dx = x - player_x
        dy = y - player_y

        # Culling
        if dx * dx + dy * dy > MAX_AGENT_RENDER_DISTANCE * MAX_AGENT_RENDER_DISTANCE:
            continue

        # Rotate and transform
        rx, ry = rotate_and_transform(dx, dy, cos_a, sin_a, flip_y)

        cx = center_x + rx * zoom
        cy = center_y + ry * zoom
        
        screen_x = cx + half_width
        screen_y = cy + half_height
        # print(f"cx={cx:.1f}, cy={cy:.1f}, screen_x={screen_x:.1f}, screen_y={screen_y:.1f}")
        # if not (0 <= screen_x <= config_var.canvas_width and 0 <= screen_y <= config_var.canvas_height):
        #     continue

        color = get_agent_draw_color(agent, is_alive, is_boss)
        radius = 3.5 if is_boss else 2.2
        segments = 8 if is_low_priority(agent) else 12

        PyImGui.draw_list_add_circle_filled(cx, cy, radius, color, segments)

def draw_range_circle(center_x, center_y, radius_game_units, zoom, color):
    screen_radius = radius_game_units * zoom
    PyImGui.draw_list_add_circle(
        center_x, center_y,
        screen_radius,
        color,
        64,  # smoothness
        1.5  # line thickness
    )

def draw_all_range_circles(center_x, center_y, zoom):
    draw_range_circle(center_x, center_y, Range.Earshot.value, zoom, Utils.RGBToColor(153, 68, 68, 255))  # Aggro
    draw_range_circle(center_x, center_y, Range.Spellcast.value, zoom, Utils.RGBToColor(17, 119, 119, 255))  # Cast
    draw_range_circle(center_x, center_y, Range.Spirit.value, zoom, Utils.RGBToColor(51, 119, 51, 255))   # Spirit
    draw_range_circle(center_x, center_y, Range.Compass.value, zoom, Utils.RGBToColor(102, 102, 17, 255))  # Compass

def draw_static_pmap_quads(center_x, center_y, player_x, player_y, canvas_width, canvas_height, rotation_angle):
    geometry = pathing_map.get_geometry()
    if not geometry:
        return

    cos_a = math.cos(-rotation_angle + math.pi / 2)
    sin_a = math.sin(-rotation_angle + math.pi / 2)
    flip_y = -1 if config_var._debug_invert_y else 1
    zoom = config_var.zoom

    radius = min(canvas_width, canvas_height) / 2

    for zplane, quads in geometry.items():
        color = pmap_draw.default_color(zplane)
        for quad in quads:
            points = []
            all_outside = True
            
            for x, y in quad:
                dx = (x - player_x)
                dy = (y - player_y)

                rx = dx * cos_a - dy * sin_a
                ry = dx * sin_a + dy * cos_a
                ry *= flip_y

                cx = center_x + rx * zoom
                cy = center_y + ry * zoom
                points.append((cx, cy))
                
                dist_sq = (cx - center_x) ** 2 + (cy - center_y) ** 2
                if dist_sq <= radius ** 2:
                    all_outside = False

            if len(points) == 4 and not all_outside:
                x1, y1 = points[0]
                x2, y2 = points[1]
                x3, y3 = points[2]
                x4, y4 = points[3]
                PyImGui.draw_list_add_quad_filled(x1, y1, x2, y2, x3, y3, x4, y4, color)

                
def draw_minimap():
    if not PyImGui.begin("Py4GW Minimap", True, minimap_window_flags):
        PyImGui.end()
        return

    try:
        map_id = Map.GetMapID()
        if map_id != config_var.last_map_id or not pathing_map.map_boundaries:
            pathing_map._fetch_from_game()
            pathing_map.precompute_geometry()
            config_var.last_map_id = map_id

        px, py = Player.GetXY()
        canvas_width, canvas_height = PyImGui.get_content_region_avail()
        canvas_width = max(300, canvas_width - 16)
        canvas_height = max(300, canvas_height - 16)

        PyImGui.set_cursor_pos(8, 8)
        PyImGui.dummy(int(canvas_width), int(canvas_height))
        window_pos = PyImGui.get_window_pos()
        canvas_pos = (window_pos[0] + 8, window_pos[1] + 8)

        center_x = canvas_pos[0] + canvas_width / 2
        center_y = canvas_pos[1] + canvas_height / 2

        # Smooth camera-follow rotation
        current_yaw = Camera.GetCurrentYaw()
        if config_var.rotation_mode == 0:  # Smooth
            smoothed_yaw = lerp_angle(config_var.last_smoothed_yaw, current_yaw, 0.15)
        else:  # Instant
            smoothed_yaw = current_yaw
        config_var.last_smoothed_yaw = smoothed_yaw

        draw_static_pmap_quads(center_x, center_y, px, py, canvas_width, canvas_height, smoothed_yaw)
        config_var.canvas_width = canvas_width
        config_var.canvas_height = canvas_height
        draw_all_agents(center_x, center_y, px, py, config_var.zoom, smoothed_yaw, config_var._debug_invert_y)
        draw_all_range_circles(center_x, center_y, config_var.zoom)       
        draw_player_circle(center_x, center_y)
       

    except Exception as e:
        Py4GW.Console.Log(module_name, f"Minimap draw error: {str(e)}", Py4GW.Console.MessageType.Warning)


def configure():
    if PyImGui.begin(config_window.window_name, config_window.window_flags):
        if PyImGui.button("Enable"):
            config_var.minimap_enabled = True
        PyImGui.same_line(0,5)
        if PyImGui.button("Disable"):
            config_var.minimap_enabled = False
            
        new_zoom = PyImGui.slider_float("Zoom", config_var.zoom, 0.01, 0.1)
        if new_zoom != config_var.zoom:
            config_var.zoom = new_zoom

        rotation_modes = ["Smooth", "Instant"]
        selected = PyImGui.combo("Camera Rotation", config_var.rotation_mode, rotation_modes)
        if selected != config_var.rotation_mode:
            config_var.rotation_mode = selected
            
        # shape_options = ["Square", "Circle"]
        # selected = PyImGui.combo("Minimap Shape", config_var.shape_mode, shape_options)
        # if selected != config_var.shape_mode:
        #     config_var.shape_mode = selected        
            
    PyImGui.end()

def main():
    try:
        if Map.IsMapReady() and Party.IsPartyLoaded() and not UIManager.IsWorldMapShowing():
            if config_var.minimap_enabled:
                draw_minimap()

    except ImportError as e:
        Py4GW.Console.Log('Minimap', f'ImportError encountered: {str(e)}', Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log('Minimap', f'Stack trace: {traceback.format_exc()}', Py4GW.Console.MessageType.Error)
    except ValueError as e:
        Py4GW.Console.Log('Minimap', f'ValueError encountered: {str(e)}', Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log('Minimap', f'Stack trace: {traceback.format_exc()}', Py4GW.Console.MessageType.Error)
    except TypeError as e:
        Py4GW.Console.Log('Minimap', f'TypeError encountered: {str(e)}', Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log('Minimap', f'Stack trace: {traceback.format_exc()}', Py4GW.Console.MessageType.Error)
    except Exception as e:
        Py4GW.Console.Log('Minimap', f'Unexpected error encountered: {str(e)}', Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log('Minimap', f'Stack trace: {traceback.format_exc()}', Py4GW.Console.MessageType.Error)
    finally:
        pass

if __name__ == "__main__":
    main()