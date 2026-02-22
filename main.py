"""Raycasting implementation with mirrors and portals."""
# pylint: disable=no-member,no-name-in-module,invalid-name,redefined-outer-name,c-extension-no-member
from __future__ import annotations
from enum import Enum
import math
from typing import Any

import pygame
from pygame.locals import (KEYDOWN, K_ESCAPE, K_SPACE, K_LSHIFT, K_LCTRL, K_c, K_r,
                           QUIT, MOUSEBUTTONDOWN, MOUSEBUTTONUP)

from raycasting import Raycaster
from player import Player
from cells import split_position, get_closest_side, CellMap
from blocks import Wall, Mirror, Portal
from directions import Direction


SCREEN_WIDTH, SCREEN_HEIGHT = 1366, 768
MAP_SIZE = 20  # MAP_SIZE x MAP_SIZE grid of cells
VISIBLE_DISTANCE = 20  # maximum rendering distance in cells
MAP_SCALE = 1/4  # size of map when minimized to corner
PLAYER_RADIUS_SCALE = 1/2  # size of player compared to cell size
COLUMN_WIDTH = 10  # width of screen columns in pixels
FOV = 70  # raycasting field of view (degrees), between 1 and 360
RAY_POINTS_MODE = False  # display rays as connected points (debug)
SHOW_MAP_GRID = True
DIVIDE_COLUMNS = False  # show vertical dividers for screen columns


# maximum length of any ray on the map is along the diagonal
VISIBLE_DISTANCE = int(min(2**1/2*MAP_SIZE, VISIBLE_DISTANCE))

# reduce screen dimensions to conform to configuration
SCREEN_WIDTH -= SCREEN_WIDTH % COLUMN_WIDTH
SQUARE_SIZE = min(SCREEN_WIDTH, SCREEN_HEIGHT) // MAP_SIZE
SCREEN_HEIGHT -= SCREEN_HEIGHT % SQUARE_SIZE

# width and height of map in pixels (square map)
MAP_LENGTH = min(SCREEN_WIDTH, SCREEN_HEIGHT)
RENDER_COLUMNS = SCREEN_WIDTH // COLUMN_WIDTH  # number of screen columns to render
PLAYER_RADIUS = int(SQUARE_SIZE*PLAYER_RADIUS_SCALE/2)


pygame.init()
font = pygame.font.SysFont("arial", 20)


class Mode(Enum):
    """Values for gamemode toggles for the simulation."""
    PLAY = 0
    MAP = 1


class Sandbox:
    """Raycasting sandbox."""

    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.game_canvas = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        self.map_canvas = pygame.Surface((MAP_LENGTH, MAP_LENGTH), pygame.SRCALPHA)
        self.player = Player(PLAYER_RADIUS, (int(MAP_LENGTH/2), int(MAP_LENGTH/2)))
        self.cell_map = CellMap((MAP_LENGTH, MAP_LENGTH), SQUARE_SIZE)
        self.raycaster = Raycaster(self.player, self.cell_map,
                                   fov=FOV, ray_count=RENDER_COLUMNS)

        self.running, self.mode = True, Mode.PLAY
        self.edited_cells, self.mouse_down = [], False
        self.first_portal: tuple[tuple[int, int], Direction] | None = None

    def run(self):
        """Main execution loop for the sandbox."""
        while self.running:
            pressed_keys, mouse_buttons, mouse_pos = self.collect_inputs()
            for event in self.poll_event():
                self.handle_event(event)
            mouse_cell, closest_side, mouse_pos = (
                self.handle_mouse(pressed_keys, mouse_buttons, mouse_pos)
                if self.mode == Mode.MAP else (None, None, mouse_pos)
                )
            self.draw(pressed_keys)
            self.handle_raycasting()
            if self.mode == Mode.MAP:
                assert mouse_cell and closest_side
                if SHOW_MAP_GRID:
                    self.show_map_grid()
                self.draw_map_overlays(pressed_keys, mouse_cell, closest_side)
            self.render(mouse_pos)

    def collect_inputs(self) -> tuple[Any, tuple[bool, bool, bool], tuple[int, int]]:
        """Get all required inputs from pygame."""
        pressed_keys = pygame.key.get_pressed()
        mouse_buttons = pygame.mouse.get_pressed()
        mouse_pos = pygame.mouse.get_pos()
        return (pressed_keys, mouse_buttons, mouse_pos)

    def handle_event(self, event: pygame.event.Event):
        """Handle a single event from pygame."""
        if event.type == QUIT:
            self.running = False
        elif event.type == KEYDOWN:
            if event.key == K_ESCAPE:
                self.running = False
            elif event.key == K_SPACE:
                self.mode = Mode.MAP if self.mode == Mode.PLAY else Mode.PLAY
            elif event.key == K_c:
                self.cell_map.clear()
            elif event.key == K_r:
                self.player.direction.rotate_ip(180)
        elif event.type == MOUSEBUTTONDOWN:
            self.mouse_down = True
        elif event.type == MOUSEBUTTONUP:
            self.mouse_down = False
            self.edited_cells.clear()

    def handle_mouse(self, pressed_keys: dict, mouse_buttons: tuple[bool, bool, bool],
                      mouse_pos: tuple[int, int]) -> tuple[tuple[int, int],
                                                           Direction, tuple[int, int]]:
        """Handle all mouse inputs for editing the map."""
        # adjust for screen offset of map
        mouse_pos = (int(mouse_pos[0] - (SCREEN_WIDTH/2 - MAP_LENGTH/2)),
                     int(mouse_pos[1] - (SCREEN_HEIGHT/2 - MAP_LENGTH/2)))
        mouse_cell, mouse_cell_pos = split_position(pygame.Vector2(mouse_pos), SQUARE_SIZE)
        mouse_cell = (int(mouse_cell.x), int(mouse_cell.y))
        closest_side = get_closest_side(mouse_cell_pos)
        if mouse_buttons[0]:
            if pressed_keys[K_LSHIFT]:
                set_value = Mirror(Direction.ALL)
            elif pressed_keys[K_LCTRL]:
                set_value = Portal()
            else:
                set_value = Wall.NORMAL
        elif mouse_buttons[2]:
            set_value = False
        else:
            set_value = None
        if set_value is not None:
            player_x, player_y = (self.player.position.x // SQUARE_SIZE,
                                    self.player.position.y // SQUARE_SIZE)
            if (mouse_cell != (player_x, player_y)
                and mouse_cell not in self.edited_cells) and self.mouse_down:
                self.update_cell(set_value, mouse_cell, closest_side)
        return (mouse_cell, closest_side, mouse_pos)

    def update_cell(self, set_value: Wall | Mirror | Portal | bool,
                    mouse_cell: tuple[int, int], closest_side: Direction):
        """Update a cell on the cell map."""
        match set_value:
            case Wall.NORMAL | False:
                self.cell_map.set_cell_type(*mouse_cell, set_value)
                self.edited_cells.append(mouse_cell)
            case Mirror():
                cell = self.cell_map.get_cell(*mouse_cell)
                if isinstance((current_mirror := cell.type_), Mirror):
                    set_value.sides = current_mirror.sides ^ closest_side
                self.cell_map.set_cell_type(*mouse_cell, set_value)
                self.edited_cells.append(mouse_cell)
            case Portal():
                if self.first_portal is None:
                    self.first_portal = (mouse_cell, closest_side)
                    self.edited_cells.append(mouse_cell)
                else:
                    first_position, first_side = self.first_portal
                    second_position, second_side = mouse_cell, closest_side

                    if first_position != second_position or first_side != second_side:
                        self.cell_map.link_sides(first_position, first_side,
                                            second_position, second_side)
                        self.edited_cells.extend([first_position, second_position])

                    self.first_portal = None

    def draw(self, pressed_keys: dict):
        """Draw base textures to the screen."""
        self.game_canvas.fill((0, 0, 0))
        # fill sky and ground
        pygame.draw.rect(self.game_canvas, (200, 200, 200),
                         (0, 0, SCREEN_WIDTH, SCREEN_HEIGHT/2))
        pygame.draw.rect(self.game_canvas, (50, 50, 50),
                         (0, SCREEN_HEIGHT/2, SCREEN_WIDTH, SCREEN_HEIGHT/2))

        self.map_canvas.fill((0, 0, 0))
        self.map_canvas.blit(self.cell_map.surf, self.cell_map.rect)
        self.player.update(pressed_keys, self.cell_map)

    def handle_raycasting(self):
        """Execute raycasting calculations and draw the results."""
        player_angle = pygame.Vector2(1, 0).angle_to(self.player.direction)
        self.raycaster.cast_rays(player_angle, VISIBLE_DISTANCE)

        for ray_data in enumerate(self.raycaster.ray_data.items()):
            i, (angle, ((_, ray_segments), ray_points)) = ray_data
            cumulative_distance = 0
            if RAY_POINTS_MODE:
                self.draw_ray_points(i, ray_points)
            for ray_segment in ray_segments:
                cumulative_distance += ray_segment.distance
                if not RAY_POINTS_MODE:
                    match ray_segment.end_type:
                        case Wall.NORMAL | Mirror() | Portal():
                            color = (255, 0, 0)
                        case Wall.BORDER:
                            color = (0, 0, 255)
                        case _:
                            color = (0, 255, 0)
                    pygame.draw.line(self.map_canvas, color, ray_segment.start_pos,
                                     ray_segment.end_pos, width=1)

            angle_delta = angle - pygame.Vector2(1, 0).angle_to(self.player.direction)
            very_end_type = ray_segments[-1].end_type

            # correct fisheye effect
            corrected_distance = cumulative_distance * math.cos(math.radians(angle_delta))

            if very_end_type in {Wall.NORMAL, Wall.BORDER}:
                self.draw_column(i, very_end_type, corrected_distance)

    def draw_ray_points(self, index: int, ray_points: list[tuple[float, float]]):
        """Draw individual calculated points for rays, with connecting lines."""
        ray_points_len = len(ray_points)
        last_point = None
        for i, point in enumerate(ray_points):
            color = self.interpolate_colors(
                (255, 0, 0), (0, 255, 0), index/self.raycaster.ray_count)
            width = 1 if i in range(ray_points_len-3, ray_points_len) else 0
            pygame.draw.circle(self.map_canvas, color, point, 5, width=width)
            cell_pos = split_position(pygame.Vector2(point),
                                        self.cell_map.square_size)[1]
            if (i not in {0, ray_points_len-1}
                    and self.distance_to_closest_side((cell_pos.x, cell_pos.y)) > 0.05):
                pygame.draw.circle(self.map_canvas, (255, 255, 0), point, 10, width=2)
            if last_point is not None:
                # lines for debugging purposes (points should travel in straight lines)
                delta = (pygame.Vector2(point) - pygame.Vector2(last_point)).magnitude()
                if delta <= (2**0.5)*self.cell_map.square_size:
                    pygame.draw.line(self.map_canvas, color, last_point, point, width=1)
            last_point = point

    def draw_column(self, index: int, very_end_type: Wall, distance: float):
        """Render a single column for a raycasting ray."""
        rectangle_color = ((0, 0, 0) if very_end_type == Wall.BORDER
                            else (255, 255, 255))
        height = self.distance_to_height(distance)
        column_ranges = [(COLUMN_WIDTH*n, COLUMN_WIDTH*(n+1)) for n in range(RENDER_COLUMNS)]
        pygame.draw.rect(
            self.game_canvas, self.dim_with_distance(rectangle_color, distance),
            (column_ranges[index][0], SCREEN_HEIGHT*(0.5-(height/2)),
            column_ranges[index][1]-column_ranges[index][0], SCREEN_HEIGHT*height)
            )

        if DIVIDE_COLUMNS:
            pygame.draw.line(self.game_canvas, (64, 64, 64), (column_ranges[index][0], 0),
                             (column_ranges[index][0], SCREEN_HEIGHT), width=1)

    def show_map_grid(self):
        """Draw a grid on the map to visually divide cells."""
        for x in range(self.cell_map.columns+1):
            pygame.draw.line(self.map_canvas, (255, 255, 255),
                                (x*self.cell_map.square_size-1, 0),
                                (x*self.cell_map.square_size-1, SCREEN_HEIGHT), width=2)
        for y in range(self.cell_map.rows+1):
            pygame.draw.line(self.map_canvas, (255, 255, 255),
                                (0, y*self.cell_map.square_size-1),
                                (SCREEN_WIDTH, y*self.cell_map.square_size-1), width=2)

    def draw_map_overlays(self, pressed_keys: dict,
                         mouse_cell: tuple[int, int], closest_side: Direction):
        """Draw extra dynamic elements onto the map."""
        self.map_canvas.blit(self.player.surf, self.player.rect)
        if mouse_cell and closest_side:
            # draw first portal (unlinked)
            if self.first_portal:
                index = {Direction.UP: 1,
                         Direction.DOWN: 7,
                         Direction.LEFT: 3,
                         Direction.RIGHT: 5}[self.first_portal[1]]
                subrect = self.cell_map.get_cell_subrect(
                    *self.first_portal[0], self.cell_map.square_size, index)
                pygame.draw.rect(self.map_canvas, (128, 0, 255), subrect)
            # draw cursor
            cell_rect = self.cell_map.get_cell_rect(
                *mouse_cell, self.cell_map.square_size)
            pygame.draw.rect(self.map_canvas, (0, 255, 255), cell_rect,
                            width=int(self.cell_map.square_size/8))
            # draw subrect cursor
            index = {Direction.UP: 1,
                     Direction.DOWN: 7,
                     Direction.LEFT: 3,
                     Direction.RIGHT: 5}[closest_side]
            if pressed_keys[K_LSHIFT] or pressed_keys[K_LCTRL]:
                subrect = self.cell_map.get_cell_subrect(
                    *mouse_cell, self.cell_map.square_size, index)
                pygame.draw.rect(self.map_canvas, (0, 255, 255), subrect)

    def render(self, mouse_pos: tuple[int, int]):
        """Render the game and the map to the screen."""
        self.screen.blit(self.game_canvas, (0, 0))

        map_rect = (
            (SCREEN_WIDTH/2-MAP_LENGTH/2, SCREEN_HEIGHT/2-MAP_LENGTH/2, MAP_LENGTH, MAP_LENGTH)
            if self.mode == Mode.MAP else
            (SCREEN_WIDTH-(MAP_LENGTH*MAP_SCALE), SCREEN_HEIGHT-(MAP_LENGTH*MAP_SCALE),
             MAP_LENGTH*MAP_SCALE, MAP_LENGTH*MAP_SCALE)
            )
        self.map_canvas.set_alpha(128)
        scaled = pygame.transform.scale(self.map_canvas, (map_rect[2:]))
        self.screen.blit(scaled, (map_rect[:2]))

        mouse_pos_text = font.render(f"Mouse: {mouse_pos}", True, (0, 0, 0))
        self.screen.blit(mouse_pos_text, (10, 10))
        mouse_cell, mouse_cell_pos = split_position(
            pygame.Vector2(mouse_pos), self.cell_map.square_size)
        mouse_cell_text = font.render(
            f"Cell: {(int(mouse_cell.x), int(mouse_cell.y))}", True, (0, 0, 0))
        self.screen.blit(mouse_cell_text, (10, 35))
        mouse_cell_pos_text = font.render(
            f"Cell Position: {(round(mouse_cell_pos.x, 3), round(mouse_cell_pos.y, 3))}",
            True, (0, 0, 0))
        self.screen.blit(mouse_cell_pos_text, (10, 60))

        pygame.display.flip()

    @staticmethod
    def distance_to_height(distance: float) -> float:
        """Convert measured distance to height for simple rendering of raycasting data."""
        return min(2/distance, 1) if distance > 0 else 1

    @staticmethod
    def dim_with_distance(color: tuple[int, int, int],
                          distance: float) -> tuple[int, int, int]:
        """Scale brightness down with distance to emulate simple lighting."""
        multiplier = min(1/distance + 1/8, 1) if distance > 0 else 1
        return (int(color[0]*multiplier),
                int(color[1]*multiplier),
                int(color[2]*multiplier))

    @staticmethod
    def distance_to_closest_side(cell_pos: tuple[float, float]) -> float:
        """Find the distance to the closest side of a cell given a position inside the cell."""
        return min(cell_pos[1], 1-cell_pos[1], cell_pos[0], 1-cell_pos[0])

    @staticmethod
    def interpolate_colors(
                start_color: tuple[int, int, int],
                end_color: tuple[int, int, int],
                progress: float
            ) -> tuple[int, int, int]:
        """Linearly interpolate between two colors."""
        start, end = pygame.Vector3(start_color), pygame.Vector3(end_color)
        result = start + (end - start)*progress
        return (int(result.x), int(result.y), int(result.z))

    @staticmethod
    def poll_event():
        """Generator for per-frame event handling."""
        if ((next_event := pygame.event.poll()).type
            in {KEYDOWN, MOUSEBUTTONDOWN, MOUSEBUTTONUP, QUIT}):
            yield next_event


Sandbox().run()
